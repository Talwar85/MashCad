"""
Body Compute Mixin - Extracted from body.py

Contains _compute_* methods for Body class.
This mixin is designed to be inherited by the Body class.
"""

from typing import Optional, List, Any
import math

from loguru import logger

from config.feature_flags import is_enabled


class BodyComputeMixin:
    """
    Mixin class containing compute methods for Body.
    
    These methods handle the computation of various CAD features
    like revolve, loft, sweep, shell, etc.
    """

    def _compute_revolve(self, feature: 'RevolveFeature'):
        """
        OCP-First Revolve mit direktem OpenCASCADE BRepPrimAPI_MakeRevol.

        CAD Kernel First: Profile werden IMMER aus dem Sketch abgeleitet.

        Architektur:
        1. Mit Sketch: Profile aus sketch.closed_profiles (immer aktuell)
           - profile_selector filtert welche Profile gewÃ¤hlt wurden
        2. Ohne Sketch: precalculated_polys als Geometrie-Quelle (Legacy)
        """
        from build123d import Plane, make_face, Wire, Vector, Solid
        from OCP.BRepPrimAPI import BRepPrimAPI_MakeRevol
        from OCP.gp import gp_Ax1, gp_Dir, gp_Pnt

        sketch = feature.sketch
        if not sketch:
            raise ValueError("Revolve: Kein Sketch vorhanden")

        # Sketch-Plane bestimmen
        plane_origin = getattr(sketch, 'plane_origin', (0, 0, 0))
        plane_normal = getattr(sketch, 'plane_normal', (0, 0, 1))
        x_dir = getattr(sketch, 'plane_x_dir', None)

        # Validate plane_normal is not zero
        norm_len = math.sqrt(sum(c*c for c in plane_normal))
        if norm_len < 1e-9:
            logger.warning("Revolve: plane_normal ist Null-Vektor, Fallback auf (0,0,1)")
            plane_normal = (0, 0, 1)

        plane = Plane(
            origin=Vector(*plane_origin),
            z_dir=Vector(*plane_normal),
            x_dir=Vector(*x_dir) if x_dir else None
        )

        # === CAD KERNEL FIRST: Profile-Bestimmung ===
        polys_to_revolve = []

        # KERNEL FIRST: Profile aus Sketch ableiten (nicht aus Cache!)
        sketch_profiles = getattr(sketch, 'closed_profiles', [])
        profile_selector = getattr(feature, 'profile_selector', [])

        if sketch_profiles and profile_selector:
            # Selektor-Match (CAD KERNEL FIRST - KEINE FALLBACKS!)
            polys_to_revolve = self._filter_profiles_by_selector(
                sketch_profiles, profile_selector
            )
            if polys_to_revolve:
                logger.info(f"Revolve: {len(polys_to_revolve)}/{len(sketch_profiles)} Profile via Selektor")
            else:
                # Selektor hat nicht gematcht â†’ Fehler, kein Fallback!
                logger.error(f"Revolve: Selektor-Match fehlgeschlagen! Selector: {profile_selector}")
                logger.error(f"Revolve: VerfÃ¼gbare Profile: {[(p.centroid.x, p.centroid.y) for p in sketch_profiles]}")
                raise ValueError("Revolve: Selektor-Match fehlgeschlagen")
        elif sketch_profiles:
            # Kein Selektor â†’ alle Profile verwenden (Legacy/Import)
            polys_to_revolve = list(sketch_profiles)
            logger.info(f"Revolve: Alle {len(polys_to_revolve)} Profile (kein Selektor)")
        else:
            # Sketch hat keine closed_profiles
            raise ValueError("Revolve: Sketch hat keine closed_profiles")

        # Profile zu Build123d Faces konvertieren
        faces_to_revolve = []
        for poly in polys_to_revolve:
            try:
                coords = list(poly.exterior.coords)[:-1]  # Shapely schlieÃŸt Polygon
                if len(coords) < 3:
                    continue
                pts_3d = [plane.from_local_coords((p[0], p[1])) for p in coords]
                wire = Wire.make_polygon([Vector(*p) for p in pts_3d])
                faces_to_revolve.append(make_face(wire))
            except Exception as e:
                logger.debug(f"Revolve: Polygon-Konvertierung fehlgeschlagen: {e}")

        if not faces_to_revolve:
            raise ValueError("Revolve: Keine gÃ¼ltigen Profile gefunden")

        # Achse bestimmen (OCP gp_Ax1)
        axis_vec = feature.axis
        axis_origin_vec = feature.axis_origin if feature.axis_origin else (0, 0, 0)

        # OCP Achse erstellen
        ocp_origin = gp_Pnt(axis_origin_vec[0], axis_origin_vec[1], axis_origin_vec[2])
        ocp_direction = gp_Dir(axis_vec[0], axis_vec[1], axis_vec[2])
        ocp_axis = gp_Ax1(ocp_origin, ocp_direction)

        # Winkel in BogenmaÃŸ
        angle_rad = math.radians(feature.angle)

        # OCP-First Revolve (alle Faces revolve und Union)
        result_solid = None
        for i, face in enumerate(faces_to_revolve):
            revolve_op = BRepPrimAPI_MakeRevol(face.wrapped, ocp_axis, angle_rad)
            revolve_op.Build()

            if not revolve_op.IsDone():
                raise ValueError(f"Revolve fehlgeschlagen fÃ¼r Face {i+1}/{len(faces_to_revolve)}")

            revolved_shape = revolve_op.Shape()
            revolved = Solid(revolved_shape)

            if result_solid is None:
                result_solid = revolved
            else:
                # Union mehrerer Revolve-Ergebnisse
                result_solid = result_solid.fuse(revolved)

        if result_solid is None or result_solid.is_null():
            raise ValueError("Revolve erzeugte keine Geometrie")

        # TNP-Registration wenn naming_service verfÃ¼gbar
        if self._document and hasattr(self._document, '_shape_naming_service'):
            try:
                naming_service = self._document._shape_naming_service
                feature_id = getattr(feature, 'id', None) or str(id(feature))

                # Alle Faces registrieren
                from modeling.tnp_system import ShapeType
                from OCP.TopExp import TopExp_Explorer
                from OCP.TopAbs import TopAbs_FACE

                explorer = TopExp_Explorer(result_solid.wrapped, TopAbs_FACE)
                face_idx = 0
                while explorer.More():
                    face_shape = explorer.Current()
                    naming_service.register_shape(
                        ocp_shape=face_shape,
                        shape_type=ShapeType.FACE,
                        feature_id=feature_id,
                        local_index=face_idx
                    )
                    face_idx += 1
                    explorer.Next()

                # Alle Edges registrieren
                naming_service.register_solid_edges(result_solid, feature_id)

                if is_enabled("tnp_debug_logging"):
                    logger.success(f"Revolve TNP: {face_idx} Faces registriert")

            except Exception as e:
                logger.error(f"Revolve TNP Registration fehlgeschlagen: {e}")

        logger.info(f"Revolve: {feature.angle}Â° um {feature.axis}")
        return result_solid

    def _compute_loft(self, feature: 'LoftFeature'):
        """
        OCP-First Loft mit direktem OpenCASCADE BRepOffsetAPI_ThruSections.

        Phase 8: UnterstÃ¼tzt G0/G1/G2 KontinuitÃ¤t.
        """
        if len(feature.profile_data) < 2:
            raise ValueError("Loft benÃ¶tigt mindestens 2 Profile")

        # Profile zu Faces konvertieren
        sections = []
        for prof_data in feature.profile_data:
            face = self._profile_data_to_face(prof_data)
            if face is not None:
                sections.append(face)

        if len(sections) < 2:
            raise ValueError(f"Konnte nur {len(sections)} gÃ¼ltige Faces erstellen")

        # KontinuitÃ¤ts-Info
        start_cont = getattr(feature, 'start_continuity', 'G0')
        end_cont = getattr(feature, 'end_continuity', 'G0')

        logger.info(f"Loft mit {len(sections)} Profilen (ruled={feature.ruled}, start={start_cont}, end={end_cont})")

        # OCP-First Loft
        from OCP.BRepOffsetAPI import BRepOffsetAPI_ThruSections
        from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeWire
        from OCP.TopExp import TopExp_Explorer
        from OCP.TopAbs import TopAbs_EDGE
        from OCP.TopoDS import TopoDS
        from OCP.Approx import Approx_ParametrizationType
        from build123d import Solid

        # ThruSections: (isSolid, isRuled)
        is_ruled = feature.ruled
        loft_builder = BRepOffsetAPI_ThruSections(True, is_ruled)

        # Smoothing fÃ¼r G1/G2 KontinuitÃ¤t
        if not is_ruled and (start_cont != 'G0' or end_cont != 'G0'):
            loft_builder.SetSmoothing(True)
            # Parametrisierung fÃ¼r bessere KontinuitÃ¤t
            if start_cont == 'G2' or end_cont == 'G2':
                loft_builder.SetParType(Approx_ParametrizationType.Approx_Centripetal)
            else:
                loft_builder.SetParType(Approx_ParametrizationType.Approx_ChordLength)

        # Profile als Wires hinzufÃ¼gen
        for i, face in enumerate(sections):
            try:
                # Extrahiere Ã¤uÃŸeren Wire aus Face
                explorer = TopExp_Explorer(face.wrapped, TopAbs_EDGE)
                edges = []
                while explorer.More():
                    edges.append(explorer.Current())
                    explorer.Next()
                
                if edges:
                    wire_builder = BRepBuilderAPI_MakeWire()
                    for edge in edges:
                        wire_builder.Add(TopoDS.Edge_s(edge))
                    wire_builder.Build()
                    if wire_builder.IsDone():
                        loft_builder.AddWire(wire_builder.Wire())
            except Exception as e:
                logger.warning(f"Loft: Wire {i} fehlgeschlagen: {e}")

        # Loft ausfÃ¼hren
        loft_builder.Build()
        if not loft_builder.IsDone():
            raise ValueError("Loft fehlgeschlagen")

        result_shape = loft_builder.Shape()
        result_solid = Solid(result_shape)

        if result_solid.is_null():
            raise ValueError("Loft erzeugte keine gÃ¼ltige Geometrie")

        # TNP-Registration
        if self._document and hasattr(self._document, '_shape_naming_service'):
            try:
                naming_service = self._document._shape_naming_service
                feature_id = getattr(feature, 'id', None) or str(id(feature))
                naming_service.register_solid_faces(result_solid, feature_id)
                naming_service.register_solid_edges(result_solid, feature_id)
            except Exception as e:
                logger.error(f"Loft TNP Registration fehlgeschlagen: {e}")

        logger.info(f"Loft: {len(sections)} Profile verarbeitet")
        return result_solid


__all__ = ['BodyComputeMixin']
