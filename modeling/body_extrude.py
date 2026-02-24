"""
Body Extrude Mixin - Extracted from body.py

Contains _extrude_* and _compute_extrude_* methods for Body class.
This mixin is designed to be inherited by the Body class.
"""

import math
import tempfile
import os
from typing import List, Optional

from loguru import logger

from config.feature_flags import is_enabled
from modeling.geometry_utils import normalize_plane_axes


class BodyExtrudeMixin:
    """
    Mixin class containing extrude-related methods for Body.
    
    These methods handle the computation of extrude features including
    OCP-first extrusion, legacy extrusion, and BRepFeat-based push/pull.
    """

    def _extrude_from_face_brep(self, feature):
        """
        Extrudiert eine Face aus gespeicherten BREP-Daten.

        Wird verwendet fÃ¼r Push/Pull auf nicht-planaren FlÃ¤chen (Zylinder, etc.),
        wo keine Polygon-Extraktion mÃ¶glich ist.

        Delegiert an OCPExtrudeHelper.extrude() als kanonische BRepPrimAPI-Implementierung.
        """
        try:
            from OCP.BRepTools import BRepTools
            from OCP.TopoDS import TopoDS_Shape
            from OCP.BRep import BRep_Builder
            from build123d import Face, Vector
            from modeling.ocp_helpers import OCPExtrudeHelper
            from modeling.tnp_system import ShapeNamingService

            face_brep = feature.face_brep
            if not face_brep:
                logger.error("Extrude: face_brep ist leer!")
                return None

            with tempfile.NamedTemporaryFile(mode='w', suffix='.brep', delete=False) as f:
                f.write(face_brep)
                temp_path = f.name

            builder = BRep_Builder()
            face_shape = TopoDS_Shape()
            BRepTools.Read_s(face_shape, temp_path, builder)
            os.unlink(temp_path)

            if face_shape.IsNull():
                logger.error("Extrude: Face aus BREP konnte nicht gelesen werden!")
                return None

            normal = feature.plane_normal
            amount = feature.distance * feature.direction
            direction = Vector(normal[0], normal[1], normal[2])

            naming_service = None
            if self._document and hasattr(self._document, '_shape_naming_service'):
                naming_service = self._document._shape_naming_service
            if naming_service is None:
                naming_service = ShapeNamingService()

            feature_id = getattr(feature, 'id', None) or 'face_brep_extrude'

            solid = OCPExtrudeHelper.extrude(
                face=Face(face_shape),
                direction=direction,
                distance=amount,
                naming_service=naming_service,
                feature_id=feature_id,
            )

            logger.info(f"Extrude: Face aus BREP erfolgreich extrudiert (type={feature.face_type}, vol={solid.volume:.2f})")
            return solid

        except Exception as e:
            logger.error(f"Extrude aus Face-BREP fehlgeschlagen: {e}")
            import traceback
            traceback.print_exc()
            return None

    def _compute_extrude_part(self, feature):
        """
        Phase 2-3: OCP-First ExtrudeFeature Implementation.

        Architektur:
        - Nutzt OCPExtrudeHelper mit TNP Integration

        TNP v4.0 Integration:
        1. Mit Sketch: Profile aus sketch.closed_profiles (immer aktuell)
        2. Ohne Sketch (Push/Pull): BRepFeat_MakePrism (MANDATORY OCP-First)
        3. Ohne Sketch (Face aus BREP): OCP MakePrism direkte Extrusion
        """
        return self._compute_extrude_part_ocp_first(feature)

    def _compute_extrude_part_ocp_first(self, feature):
        """
        OCP-First Pfad: Nutzt OCPExtrudeHelper mit TNP Integration.

        Dieser Pfad verwendet den OCPExtrudeHelper der:
        - OCP-PRIMARY ist (kein Build123d Fallback)
        - Verbindliche TNP Integration durchfÃ¼hrt
        - Alle Faces/Edges im ShapeNamingService registriert
        """
        from modeling.tnp_system import ShapeNamingService
        
        # Phase 2: PrÃ¼fe Geometrie-Quelle
        has_sketch = feature.sketch is not None
        has_polys = hasattr(feature, 'precalculated_polys') and feature.precalculated_polys
        has_face_brep = hasattr(feature, 'face_brep') and feature.face_brep
        has_face_refs = (hasattr(feature, 'face_shape_id') and feature.face_shape_id is not None)

        if is_enabled("extrude_debug"):
            logger.debug(f"[OCP-FIRST] has_sketch={has_sketch}, has_polys={has_polys}, "
                       f"has_face_brep={has_face_brep}, has_face_refs={has_face_refs}")

        # Phase 2: KEINE Geometry-Quelle ohne Sketch = ERROR
        if not has_sketch and not has_polys and not has_face_brep:
            raise ValueError("ExtrudeFeature: Keine Geometrie-Quelle "
                           "(Sketch oder precalculated_polys oder face_brep erforderlich)")

        # Feature-ID sicherstellen
        if not hasattr(feature, 'id') or feature.id is None:
            import uuid
            feature.id = str(uuid.uuid4())[:8]
            logger.debug(f"[OCP-FIRST] Generated ID for ExtrudeFeature: {feature.id}")

        # TNP Service holen
        naming_service = None
        if self._document and hasattr(self._document, '_shape_naming_service'):
            naming_service = self._document._shape_naming_service

        if naming_service is None:
            # Legacy-Compat: Extrude ohne Document soll weiterhin laufen
            naming_service = ShapeNamingService()
            logger.debug(
                "[OCP-FIRST] Kein Document-ShapeNamingService vorhanden; "
                "verwende temporaeren Service fuer Extrude."
            )

        try:
            from build123d import make_face, Wire, Compound
            from shapely.geometry import Polygon as ShapelyPoly

            sketch = feature.sketch
            if sketch:
                plane = self._get_plane_from_sketch(sketch)
            else:
                # Reconstruct plane from saved feature data (Push/Pull ohne Sketch)
                from build123d import Plane as B3DPlane, Vector
                origin = Vector(*feature.plane_origin)
                normal = Vector(*feature.plane_normal)
                if feature.plane_x_dir:
                    x_dir = Vector(*feature.plane_x_dir)
                    plane = B3DPlane(origin=origin, z_dir=normal, x_dir=x_dir)
                else:
                    plane = B3DPlane(origin=origin, z_dir=normal)
            solids = []

            # === OCP-FIRST: Nutze OCPExtrudeHelper mit TNP Integration ===
            # Profile-Bestimmung (gleich wie Legacy)
            polys_to_extrude = []

            if has_sketch:
                # KERNEL FIRST: Profile aus Sketch ableiten (nicht aus Cache!)
                sketch_profiles = getattr(sketch, 'closed_profiles', [])
                profile_selector = getattr(feature, 'profile_selector', [])

                if sketch_profiles and profile_selector:
                    # Selektor-Match (CAD KERNEL FIRST - KEINE FALLBACKS!)
                    shapely_profiles = self._convert_line_profiles_to_polygons(sketch_profiles)
                    polys_to_extrude = self._filter_profiles_by_selector(
                        shapely_profiles, profile_selector
                    )
                    if polys_to_extrude:
                        logger.info(f"[OCP-FIRST] {len(polys_to_extrude)}/{len(sketch_profiles)} Profile via Selektor")
                    else:
                        logger.error(f"[OCP-FIRST] Selektor-Match fehlgeschlagen! Selector: {profile_selector}")
                        raise ValueError("Profile-Selektor hat kein Match - keine Extrusion mÃ¶glich")
                elif sketch_profiles:
                    polys_to_extrude = self._convert_line_profiles_to_polygons(sketch_profiles)
                    logger.info(f"[OCP-FIRST] Alle {len(polys_to_extrude)} Profile (kein Selektor)")
                else:
                    logger.warning(f"[OCP-FIRST] Sketch hat keine closed_profiles!")
            else:
                # Phase 2: Ohne Sketch (Push/Pull): precalculated_polys oder face_brep
                if has_polys:
                    polys_to_extrude = list(feature.precalculated_polys)
                    logger.info(f"[OCP-FIRST] {len(polys_to_extrude)} Profile (Push/Pull Mode)")
                elif has_face_brep:
                    logger.info(f"[OCP-FIRST] Face aus BREP (Push/Pull auf {feature.face_type})")
                    return self._extrude_from_face_brep(feature)

            # === TNP v4.1: Native Circle Path ===
            if has_sketch and hasattr(sketch, 'circles') and sketch.circles:
                native_faces = self._create_faces_from_native_circles(sketch, plane, getattr(feature, 'profile_selector', None))
                if native_faces:
                    for face in native_faces:
                        solid = self._extrude_single_face(face, feature, plane, naming_service)
                        if solid:
                            solids.append(solid)

            # === TNP v4.1: Native Arc Path ===
            if has_sketch and hasattr(sketch, 'arcs') and sketch.arcs:
                native_arc_faces = self._create_faces_from_native_arcs(sketch, plane, getattr(feature, 'profile_selector', None))
                if native_arc_faces:
                    for face in native_arc_faces:
                        solid = self._extrude_single_face(face, feature, plane, naming_service)
                        if solid:
                            solids.append(solid)

            # === TNP v4.1: Native Ellipse Path ===
            if has_sketch and hasattr(sketch, 'ellipses') and sketch.ellipses:
                ellipse_faces = self._extrude_sketch_ellipses(sketch, plane, getattr(feature, 'profile_selector', None))
                if ellipse_faces:
                    for face in ellipse_faces:
                        solid = self._extrude_single_face(face, feature, plane, naming_service)
                        if solid:
                            solids.append(solid)

            # === Polygon-basierte Extrusion ===
            for poly in polys_to_extrude:
                try:
                    # Skip dict profiles (ellipse, circle, slot) - handled by native paths
                    if isinstance(poly, dict):
                        continue

                    coords = list(poly.exterior.coords)[:-1]  # Shapely schlieÃŸt Polygon
                    if len(coords) < 3:
                        continue

                    # Circle-Detection: Polygon-Punkte auf Kreis prüfen
                    circle_info = self._detect_circle_from_points(coords)
                    if circle_info and len(coords) >= 8:
                        cx, cy = circle_info['center']
                        radius = circle_info['radius']
                        try:
                            from build123d import Plane as B3DPlane
                            center_3d = plane.from_local_coords((cx, cy))
                            circle_plane = B3DPlane(origin=center_3d, z_dir=plane.z_dir)
                            outer_wire = Wire.make_circle(radius, circle_plane)
                            
                            # Handle holes (interiors) for ring shapes
                            hole_wires = []
                            if hasattr(poly, 'interiors') and poly.interiors:
                                for interior in poly.interiors:
                                    hole_coords = list(interior.coords)[:-1]
                                    if len(hole_coords) >= 8:
                                        hole_circle_info = self._detect_circle_from_points(hole_coords)
                                        if hole_circle_info:
                                            hcx, hcy = hole_circle_info['center']
                                            hradius = hole_circle_info['radius']
                                            hole_center_3d = plane.from_local_coords((hcx, hcy))
                                            hole_plane = B3DPlane(origin=hole_center_3d, z_dir=plane.z_dir)
                                            # Create hole circle with reversed orientation
                                            hole_wire = Wire.make_circle(hradius, hole_plane)
                                            hole_wires.append(hole_wire)
                                        else:
                                            # Reverse polygon points for hole orientation
                                            hole_pts_3d = [plane.from_local_coords((p[0], p[1])) for p in reversed(hole_coords)]
                                            hole_wires.append(Wire.make_polygon(hole_pts_3d))
                            
                            if hole_wires:
                                # Use Face constructor for proper hole handling
                                from build123d import Face
                                face = Face(outer_wire, hole_wires)
                                logger.info(f"[OCP-FIRST] Ring erkannt: outer_r={radius:.2f}, {len(hole_wires)} holes")
                            else:
                                face = make_face(outer_wire)
                                logger.info(f"[OCP-FIRST] Kreis erkannt: center=({cx:.2f},{cy:.2f}), r={radius:.2f}, {len(coords)} Punkte")
                        except Exception as e:
                            logger.debug(f"[OCP-FIRST] Native Kreis-Erstellung fehlgeschlagen, Polygon-Fallback: {e}")
                            pts_3d = [plane.from_local_coords((p[0], p[1])) for p in coords]
                            wire = Wire.make_polygon(pts_3d)
                            face = make_face(wire)
                    else:
                        pts_3d = [plane.from_local_coords((p[0], p[1])) for p in coords]
                        outer_wire = Wire.make_polygon(pts_3d)
                        
                        # Handle holes for non-circle polygons
                        hole_wires = []
                        if hasattr(poly, 'interiors') and poly.interiors:
                            for interior in poly.interiors:
                                hole_coords = list(interior.coords)[:-1]
                                if len(hole_coords) >= 3:
                                    # Reverse points for hole orientation
                                    hole_pts_3d = [plane.from_local_coords((p[0], p[1])) for p in reversed(hole_coords)]
                                    hole_wires.append(Wire.make_polygon(hole_pts_3d))
                        
                        if hole_wires:
                            # Use Face constructor for proper hole handling
                            from build123d import Face
                            face = Face(outer_wire, hole_wires)
                        else:
                            face = make_face(outer_wire)

                    solid = self._extrude_single_face(face, feature, plane, naming_service)
                    if solid:
                        solids.append(solid)

                except Exception as e:
                    logger.debug(f"[OCP-FIRST] Polygon-Extrusion fehlgeschlagen: {e}")

            # Combine solids
            if not solids:
                return None

            result = solids[0]
            for s in solids[1:]:
                fused = result.fuse(s)
                # Handle ShapeList return from fuse()
                if hasattr(fused, '__iter__') and not isinstance(fused, type(result)):
                    # Extract the first solid from ShapeList
                    solids_list = list(fused)
                    if solids_list:
                        result = solids_list[0]
                else:
                    result = fused

            return result

        except Exception as e:
            logger.error(f"[OCP-FIRST] Extrusion fehlgeschlagen: {e}")
            return None

    def _extrude_single_face(self, face, feature, plane, naming_service):
        """
        Extrudiert eine einzelne Face mit OCP-First.
        """
        from modeling.ocp_helpers import OCPExtrudeHelper
        from build123d import Solid

        try:
            # Die OCPExtrudeHelper Methode erwartet einen Richtungsvektor
            dir_vec = plane.z_dir * getattr(feature, 'direction', 1)
            
            # OCPExtrudeHelper verwenden
            result = OCPExtrudeHelper.extrude(
                face=face,
                distance=feature.distance,
                direction=dir_vec,
                naming_service=naming_service,
                feature_id=feature.id
            )
            return result
        except Exception as e:
            logger.debug(f"Single face extrusion failed: {e}")
            return None


    def _compute_extrude_part_brepfeat(self, feature, current_solid):
        """
        Push/Pull Extrusion fÃ¼r Body-Faces mit BRepFeat_MakePrism.
        
        Delegiert an die kanonische brepfeat_prism() Implementierung
        in brepfeat_operations.py fÃ¼r konsistente Normal-Berechnung
        und Sketch-Face-Erkennung.
        """
        from modeling.brepfeat_operations import brepfeat_prism
        from OCP.TopoDS import TopoDS_Shape
        from build123d import Face
        import uuid

        if current_solid is None:
            raise ValueError("Push/Pull Extrusion benÃ¶tigt einen aktuellen Solid")

        # Feature-ID sicherstellen
        if not hasattr(feature, 'id') or feature.id is None:
            feature.id = str(uuid.uuid4())[:8]

        # Face-Referenz auflÃ¶sen
        face_to_extrude = None
        resolved_face_index = None  # Track resolved index for healing
        
        # 1. Versuche Face Ã¼ber ShapeID
        if hasattr(feature, 'face_shape_id') and feature.face_shape_id:
            if self._document and hasattr(self._document, '_shape_naming_service'):
                try:
                    service = self._document._shape_naming_service
                    resolved_ocp, method = service.resolve_shape_with_method(
                        feature.face_shape_id, current_solid,
                        log_unresolved=False,
                    )
                    if resolved_ocp is not None:
                        face_to_extrude = Face(resolved_ocp)
                        # TNP v4.2: Heal stale face_index by finding actual index
                        try:
                            from modeling.topology_indexing import face_index_of
                            resolved_face_index = face_index_of(current_solid, face_to_extrude)
                            if resolved_face_index is not None:
                                feature.face_index = resolved_face_index
                        except Exception:
                            pass  # Index healing is optional
                except Exception as e:
                    logger.debug(f"Push/Pull: Face-ShapeID AuflÃ¶sung fehlgeschlagen: {e}")

        # 2. Versuche Face Ã¼ber Index
        if face_to_extrude is None and hasattr(feature, 'face_index') and feature.face_index is not None:
            try:
                from modeling.topology_indexing import face_from_index
                face_to_extrude = face_from_index(current_solid, int(feature.face_index))
            except Exception as e:
                logger.debug(f"Push/Pull: Face-Index AuflÃ¶sung fehlgeschlagen: {e}")

        # 3. Versuche Face aus BREP
        if face_to_extrude is None and hasattr(feature, 'face_brep') and feature.face_brep:
            try:
                from OCP.BRepTools import BRepTools
                from OCP.BRep import BRep_Builder
                from OCP.TopoDS import TopoDS_Shape
                
                with tempfile.NamedTemporaryFile(mode='w', suffix='.brep', delete=False) as f:
                    f.write(feature.face_brep)
                    temp_path = f.name

                builder = BRep_Builder()
                face_shape = TopoDS_Shape()
                BRepTools.Read_s(face_shape, temp_path, builder)
                os.unlink(temp_path)

                if not face_shape.IsNull():
                    face_to_extrude = Face(face_shape)
            except Exception as e:
                logger.debug(f"Push/Pull: Face-BREP Deserialisierung fehlgeschlagen: {e}")

        if face_to_extrude is None:
            raise ValueError("Push/Pull: Keine Face-Referenz auflÃ¶sbar")

        # OCP Face extrahieren
        ocp_face = face_to_extrude.wrapped if hasattr(face_to_extrude, 'wrapped') else face_to_extrude

        # Fuse-Modus aus Feature-Direction bestimmen
        # direction=1 -> Join (fuse=True), direction=-1 -> Cut (fuse=False)
        fuse_mode = getattr(feature, 'direction', 1) >= 0
        height = abs(feature.distance)

        # Kanonische brepfeat_prism() verwenden
        result_solid = brepfeat_prism(
            base_solid=current_solid,
            face=ocp_face,
            height=height,
            fuse=fuse_mode,
            unify=True
        )

        if result_solid is None:
            raise ValueError("BRepFeat_MakePrism fehlgeschlagen")

        # TNP-Registrierung
        if self._document and hasattr(self._document, '_shape_naming_service'):
            try:
                service = self._document._shape_naming_service
                service.register_solid_faces(result_solid, feature.id)
                service.register_solid_edges(result_solid, feature.id)
            except Exception as e:
                logger.debug(f"Push/Pull TNP-Registrierung fehlgeschlagen: {e}")

        return result_solid
    def _extrude_sketch_ellipses(self, sketch, plane, profile_selector=None):
        """
        TNP v4.1: Erstellt native OCP Ellipse Faces aus Sketch-Ellipsen.

        Ellipsen sind geschlossene Kurven. Wir erstellen eine planare Face
        aus der vollen Ellipse fÃ¼r Extrusion.
        """
        from build123d import Face, Vector
        from OCP.GC import GC_MakeEllipse
        from OCP.gp import gp_Ax2, gp_Pnt, gp_Dir
        from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeEdge, BRepBuilderAPI_MakeWire, BRepBuilderAPI_MakeFace

        faces = []
        
        if not hasattr(sketch, 'ellipses') or not sketch.ellipses:
            return faces
        
        ellipses_to_extrude = [
            e for e in sketch.ellipses
            if not e.construction
        ]

        if not ellipses_to_extrude:
            return faces

        logger.info(f"[TNP v4.1] {len(ellipses_to_extrude)} Ellipsen zur Extrusion")

        for ellipse in ellipses_to_extrude:
            if hasattr(ellipse, 'native_ocp_data') and ellipse.native_ocp_data:
                ocp_data = ellipse.native_ocp_data
                cx, cy = ocp_data['center']
                radius_x = ocp_data['radius_x']
                radius_y = ocp_data['radius_y']
                rotation = ocp_data.get('rotation', 0.0)
            else:
                cx, cy = ellipse.center.x, ellipse.center.y
                radius_x = ellipse.radius_x
                radius_y = ellipse.radius_y
                rotation = ellipse.rotation

            if profile_selector:
                ellipse_centroid = (cx, cy)
                if not any(
                    abs(ellipse_centroid[0] - sel[0]) < 0.1 and
                    abs(ellipse_centroid[1] - sel[1]) < 0.1
                    for sel in profile_selector
                ):
                    continue

            origin = Vector(*sketch.plane_origin)
            z_norm, x_norm, y_norm = normalize_plane_axes(
                getattr(sketch, "plane_normal", (0, 0, 1)),
                getattr(sketch, "plane_x_dir", None),
                getattr(sketch, "plane_y_dir", None),
            )
            z_dir = Vector(*z_norm)
            x_dir = Vector(*x_norm)
            y_dir = Vector(*y_norm)

            center_3d = origin + x_dir * cx + y_dir * cy

            rot_rad = math.radians(rotation)
            cos_rot = math.cos(rot_rad)
            sin_rot = math.sin(rot_rad)

            major_dir = x_dir * cos_rot + y_dir * sin_rot
            minor_dir = -x_dir * sin_rot + y_dir * cos_rot

            gp_center = gp_Pnt(center_3d.X, center_3d.Y, center_3d.Z)
            gp_major_dir = gp_Dir(major_dir.X, major_dir.Y, major_dir.Z)
            gp_minor_dir = gp_Dir(minor_dir.X, minor_dir.Y, minor_dir.Z)

            gp_normal = gp_Dir(
                gp_major_dir.Y() * gp_minor_dir.Z() - gp_major_dir.Z() * gp_minor_dir.Y(),
                gp_major_dir.Z() * gp_minor_dir.X() - gp_major_dir.X() * gp_minor_dir.Z(),
                gp_major_dir.X() * gp_minor_dir.Y() - gp_major_dir.Y() * gp_minor_dir.X()
            )

            ellipse_axis = gp_Ax2(gp_center, gp_normal, gp_major_dir)
            ellipse_maker = GC_MakeEllipse(ellipse_axis, radius_x, radius_y)
            
            if ellipse_maker.IsDone():
                ellipse_geom = ellipse_maker.Value()
                edge_maker = BRepBuilderAPI_MakeEdge(ellipse_geom)
                
                if edge_maker.IsDone():
                    ellipse_edge = edge_maker.Edge()
                    wire_maker = BRepBuilderAPI_MakeWire()
                    wire_maker.Add(ellipse_edge)
                    wire_maker.Build()
                    
                    if wire_maker.IsDone():
                        ocp_wire = wire_maker.Wire()
                        face_maker = BRepBuilderAPI_MakeFace(ocp_wire)
                        
                        if face_maker.IsDone():
                            ocp_face = face_maker.Face()
                            face = Face(ocp_face)
                            faces.append(face)
                            logger.info(f"[TNP v4.1] Native Ellipse Face erstellt: rx={radius_x:.2f}, ry={radius_y:.2f}")

        return faces

    def _extrude_single_ellipse(self, ellipse, plane):
        """
        TNP v4.1: Erstellt eine native OCP Ellipse Face aus einer einzelnen Ellipse2D.
        """
        from build123d import Face, Vector
        from OCP.GC import GC_MakeEllipse
        from OCP.gp import gp_Ax2, gp_Pnt, gp_Dir
        from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeFace, BRepBuilderAPI_MakeEdge, BRepBuilderAPI_MakeWire

        faces = []

        cx, cy = ellipse.center.x, ellipse.center.y
        radius_x = ellipse.radius_x
        radius_y = ellipse.radius_y
        rotation = ellipse.rotation

        origin = plane.origin
        z_dir = plane.z_dir
        x_dir = plane.x_dir
        y_dir = plane.y_dir

        center_3d = origin + x_dir * cx + y_dir * cy

        rot_rad = math.radians(rotation)
        cos_rot = math.cos(rot_rad)
        sin_rot = math.sin(rot_rad)

        major_dir = x_dir * cos_rot + y_dir * sin_rot
        minor_dir = -x_dir * sin_rot + y_dir * cos_rot

        gp_center = gp_Pnt(center_3d.X, center_3d.Y, center_3d.Z)
        gp_major_dir = gp_Dir(major_dir.X, major_dir.Y, major_dir.Z)
        gp_minor_dir = gp_Dir(minor_dir.X, minor_dir.Y, minor_dir.Z)

        gp_normal = gp_Dir(
            gp_major_dir.Y() * gp_minor_dir.Z() - gp_major_dir.Z() * gp_minor_dir.Y(),
            gp_major_dir.Z() * gp_minor_dir.X() - gp_major_dir.X() * gp_minor_dir.Z(),
            gp_major_dir.X() * gp_minor_dir.Y() - gp_major_dir.Y() * gp_minor_dir.X()
        )

        ellipse_axis = gp_Ax2(gp_center, gp_normal, gp_major_dir)
        ellipse_maker = GC_MakeEllipse(ellipse_axis, radius_x, radius_y)

        if ellipse_maker.IsDone():
            ellipse_geom = ellipse_maker.Value()
            edge = BRepBuilderAPI_MakeEdge(ellipse_geom).Edge()
            wire = BRepBuilderAPI_MakeWire(edge).Wire()
            if wire.Closed():
                face = BRepBuilderAPI_MakeFace(wire).Face()
                faces.append(Face(face))
                logger.debug(f"[TNP v4.1] Ellipse Face erstellt: rx={radius_x:.2f}, ry={radius_y:.2f}")

        return faces

    def _extrude_single_circle(self, circle, plane):
        """
        TNP v4.1: Erstellt eine native OCP Circle Face aus einer einzelnen Circle2D.
        """
        from build123d import Face, Wire, make_face
        from build123d import Plane as B3DPlane

        faces = []

        cx, cy = circle.center.x, circle.center.y
        radius = circle.radius

        center_3d = plane.from_local_coords((cx, cy))
        circle_plane = B3DPlane(origin=center_3d, z_dir=plane.z_dir)

        try:
            face = make_face(Wire.make_circle(radius, circle_plane))
            faces.append(face)
        except Exception as e:
            logger.warning(f"[TNP v4.1] Circle Face Erstellung fehlgeschlagen: {e}")

        return faces

    def _extrude_single_slot(self, slot_data, plane):
        """
        W34: Erstellt eine native OCP Slot Face aus Slot-Komponenten.
        """
        from build123d import Face
        from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeWire, BRepBuilderAPI_MakeEdge, BRepBuilderAPI_MakeFace
        from OCP.GC import GC_MakeArcOfCircle
        from OCP.gp import gp_Pnt, gp_Dir, gp_Ax2

        faces = []
        arcs = slot_data.get('arcs', [])
        lines = slot_data.get('lines', [])

        if len(arcs) != 2 or len(lines) < 2:
            logger.warning(f"[W34] UngÃ¼ltige Slot-Struktur: {len(arcs)} Arcs, {len(lines)} Linien")
            return faces

        try:
            edges = []

            for line in lines[:2]:
                p1_3d = plane.from_local_coords((line.start.x, line.start.y))
                p2_3d = plane.from_local_coords((line.end.x, line.end.y))
                gp1 = gp_Pnt(p1_3d.X, p1_3d.Y, p1_3d.Z)
                gp2 = gp_Pnt(p2_3d.X, p2_3d.Y, p2_3d.Z)
                edge = BRepBuilderAPI_MakeEdge(gp1, gp2).Edge()
                edges.append(edge)

            for arc in arcs:
                center_3d = plane.from_local_coords((arc.center.x, arc.center.y))
                radius = arc.radius
                start_angle = math.radians(arc.start_angle)
                end_angle = math.radians(arc.end_angle)

                gp_center = gp_Pnt(center_3d.X, center_3d.Y, center_3d.Z)
                gp_z = gp_Dir(plane.z_dir.X, plane.z_dir.Y, plane.z_dir.Z)
                gp_x = gp_Dir(plane.x_dir.X, plane.x_dir.Y, plane.x_dir.Z)
                arc_axis = gp_Ax2(gp_center, gp_z, gp_x)

                arc_maker = GC_MakeArcOfCircle(arc_axis, radius, start_angle, end_angle)

                if arc_maker.IsDone():
                    arc_geom = arc_maker.Value()
                    edge = BRepBuilderAPI_MakeEdge(arc_geom).Edge()
                    edges.append(edge)

            if len(edges) >= 4:
                wire_maker = BRepBuilderAPI_MakeWire()
                for edge in edges:
                    wire_maker.Add(edge)

                if wire_maker.IsDone():
                    wire = wire_maker.Wire()
                    if wire.Closed():
                        face_maker = BRepBuilderAPI_MakeFace(wire)
                        if face_maker.IsDone():
                            face = Face(face_maker.Face())
                            faces.append(face)
                            logger.debug(f"[W34] Slot Face erstellt: {len(edges)} edges")

        except Exception as e:
            logger.warning(f"[W34] Slot Face Erstellung fehlgeschlagen: {e}")

        return faces

    def _create_faces_from_native_circles(self, sketch, plane, profile_selector=None):
        """Create native OCP circle faces from sketch circles."""
        from build123d import Face, Wire, make_face
        
        faces = []
        if not hasattr(sketch, 'circles') or not sketch.circles:
            return faces

        for circle in sketch.circles:
            if getattr(circle, 'construction', False):
                continue

            cx, cy = circle.center.x, circle.center.y
            radius = circle.radius

            if profile_selector:
                if not any(abs(cx - sel[0]) < 0.1 and abs(cy - sel[1]) < 0.1 for sel in profile_selector):
                    continue

            try:
                center_3d = plane.from_local_coords((cx, cy))
                from build123d import Plane as B3DPlane
                circle_plane = B3DPlane(origin=center_3d, z_dir=plane.z_dir)
                face = make_face(Wire.make_circle(radius, circle_plane))
                faces.append(face)
            except Exception as e:
                logger.debug(f"Native circle face creation failed: {e}")

        return faces

    def _create_faces_from_native_arcs(self, sketch, plane, profile_selector=None):
        """Create faces from native sketch arcs (closed arc loops)."""
        faces = []
        if not hasattr(sketch, 'arcs') or not sketch.arcs:
            return faces

        # This would require more complex logic to detect closed arc loops
        # For now, return empty - arcs are typically part of polygons
        return faces

    def _heal_brepfeat_result(self, shape):
        """
        OCP-First Geometry Healing for BRepFeat_MakePrism results.
        
        BRepFeat_MakePrism can create edges with degenerate tangent vectors
        at junction points, which causes chamfer operations to fail with
        "gp_Vec::Normalize() - vector has zero norm" errors.
        
        This method uses OCP's ShapeFix utilities to clean up the geometry.
        
        Args:
            shape: TopoDS_Shape from BRepFeat_MakePrism
            
        Returns:
            Healed TopoDS_Shape with valid edge geometry
        """
        from OCP.ShapeFix import ShapeFix_Shape
        from OCP.BRepTools import BRepTools
        
        try:
            # Step 1: Basic shape fix
            fix = ShapeFix_Shape(shape)
            fix.Perform()
            healed_shape = fix.Shape()
            
            # Step 2: Cleanup redundant representations
            BRepTools.Clean_s(healed_shape)
            
            # Step 3: Final shape fix pass
            fix2 = ShapeFix_Shape(healed_shape)
            fix2.Perform()
            healed_shape = fix2.Shape()
            
            # Note: ShapeFix_Shape already handles wire fixing internally,
            # so explicit per-face wire fixing is not needed
            
            logger.debug(f"[_heal_brepfeat_result] Healing complete, shape valid: {not healed_shape.IsNull()}")
            return healed_shape
            
        except Exception as e:
            logger.warning(f"[_heal_brepfeat_result] Healing failed, returning original: {e}")
            return shape


__all__ = ['BodyExtrudeMixin']
