"""
Body Compute Extended Mixin - Extracted from body.py

Contains additional _compute_* methods and helper functions for Body class.
This mixin is designed to be inherited by the Body class.
"""

import math
import uuid
from typing import Optional, List, Dict, Any

from loguru import logger

from config.feature_flags import is_enabled


class BodyComputeExtendedMixin:
    """
    Mixin class containing extended compute methods for Body.
    
    These methods handle the computation of various CAD features
    like sweep, shell, hole, draft, split, thread, etc.
    """

    def _ensure_ocp_feature_id(self, feature_id: Optional[str], op_name: str) -> str:
        """
        Stellt sicher, dass OCP-First Helper immer eine Feature-ID erhalten.

        Legacy-Pfade rufen _ocp_fillet/_ocp_chamfer teils ohne feature_id auf.
        Für TNP-Tracking wird dann eine deterministische Laufzeit-ID erzeugt.
        """
        if feature_id:
            return feature_id
        generated = f"{op_name}_{str(uuid.uuid4())[:8]}"
        logger.warning(f"{op_name}: feature_id fehlte, verwende generierte ID '{generated}'")
        return generated

    def _compute_sweep(self, feature: 'SweepFeature', current_solid):
        """
        Berechnet Sweep eines Profils entlang eines Pfads.

        OCP-First Strategy:
        1. Profil zu Face konvertieren + Pfad auflösen
        2. Voranalyse: Pfad-Komplexität → MakePipe oder MakePipeShell
        3. Kein Fallback - bei Fehler ValueError

        Phase 8: Unterstützt Twist und Skalierung
        """
        profile_face = None
        shape_service = None
        if self._document and hasattr(self._document, '_shape_naming_service'):
            shape_service = self._document._shape_naming_service

        profile_data = feature.profile_data if isinstance(feature.profile_data, dict) else {}
        profile_source_solid = current_solid
        profile_body_id = profile_data.get("body_id")
        if profile_body_id and self._document and hasattr(self._document, "find_body_by_id"):
            try:
                profile_body = self._document.find_body_by_id(profile_body_id)
                if profile_body is not None and getattr(profile_body, "_build123d_solid", None) is not None:
                    profile_source_solid = profile_body._build123d_solid
            except Exception as e:
                logger.debug(f"Sweep: Konnte Profil-Body '{profile_body_id}' nicht laden: {e}")

        profile_face_index = getattr(feature, "profile_face_index", None)
        try:
            profile_face_index = int(profile_face_index) if profile_face_index is not None else None
        except Exception:
            profile_face_index = None
        if profile_face_index is not None and profile_face_index < 0:
            profile_face_index = None
        feature.profile_face_index = profile_face_index

        has_profile_shape_ref = feature.profile_shape_id is not None
        has_topological_profile_refs = bool(has_profile_shape_ref or profile_face_index is not None)

        def _is_same_face(face_a, face_b) -> bool:
            if face_a is None or face_b is None:
                return False
            try:
                wa = face_a.wrapped if hasattr(face_a, "wrapped") else face_a
                wb = face_b.wrapped if hasattr(face_b, "wrapped") else face_b
                return wa.IsSame(wb)
            except Exception:
                return face_a is face_b

        def _persist_profile_shape_id(face_obj) -> None:
            if (
                face_obj is None
                or not shape_service
                or feature.profile_shape_id is not None
                or not hasattr(face_obj, "wrapped")
            ):
                return
            try:
                from modeling.tnp_system import ShapeType as TNPShapeType
                shape_id = shape_service.find_shape_id_by_face(face_obj)
                if shape_id is None:
                    fc = face_obj.center()
                    area = face_obj.area if hasattr(face_obj, "area") else 0.0
                    shape_id = shape_service.register_shape(
                        ocp_shape=face_obj.wrapped,
                        shape_type=TNPShapeType.FACE,
                        feature_id=feature.id,
                        local_index=max(0, int(profile_face_index) if profile_face_index is not None else 0),
                        geometry_data=(fc.X, fc.Y, fc.Z, area),
                    )
                if shape_id is not None:
                    feature.profile_shape_id = shape_id
            except Exception as e:
                logger.debug(f"Sweep: Konnte Profil-ShapeID nicht persistieren: {e}")

        profile_face_from_index = None
        if profile_source_solid is not None and profile_face_index is not None:
            try:
                from modeling.topology_indexing import face_from_index

                profile_face_from_index = face_from_index(profile_source_solid, profile_face_index)
                if profile_face_from_index is not None:
                    profile_face = profile_face_from_index
                    _persist_profile_shape_id(profile_face_from_index)
                    if is_enabled("tnp_debug_logging"):
                        logger.debug(f"Sweep: Profil via Face-Index aufgelöst (index={profile_face_index})")
            except Exception as e:
                logger.debug(f"Sweep: Profil-Index Auflösung fehlgeschlagen: {e}")

        profile_face_from_shape = None
        profile_shape_resolution_method = ""
        if profile_source_solid is not None and has_profile_shape_ref and shape_service:
            try:
                resolved_ocp, method = shape_service.resolve_shape_with_method(
                    feature.profile_shape_id, profile_source_solid,
                    log_unresolved=False,
                )
                profile_shape_resolution_method = str(method or "").strip().lower()
                if resolved_ocp is not None:
                    from build123d import Face
                    from modeling.topology_indexing import face_index_of

                    profile_face_from_shape = Face(resolved_ocp)
                    resolved_idx = face_index_of(profile_source_solid, profile_face_from_shape)
                    if resolved_idx is not None:
                        feature.profile_face_index = int(resolved_idx)
                    if profile_face is None:
                        profile_face = profile_face_from_shape
                    if is_enabled("tnp_debug_logging"):
                        logger.debug(f"Sweep: Profil via ShapeID aufgelöst (method={method})")
            except Exception as e:
                logger.debug(f"Sweep: Profil-ShapeID Auflösung fehlgeschlagen: {e}")

        if has_profile_shape_ref and profile_face_index is not None:
            single_profile_ref_pair = True
            if profile_face_from_index is None or profile_face_from_shape is None:
                index_resolved = profile_face_from_index is not None
                shape_resolved = profile_face_from_shape is not None
                if single_profile_ref_pair and index_resolved and (not shape_resolved):
                    feature.profile_shape_id = None
                    if profile_face_index is not None:
                        feature.profile_face_index = int(profile_face_index)
                    _persist_profile_shape_id(profile_face_from_index)
                    profile_face = profile_face_from_index
                    if is_enabled("tnp_debug_logging"):
                        logger.warning(
                            "Sweep: single_ref_pair profile ShapeID nicht aufloesbar -> "
                            "verwende index-basiertes Profil."
                        )
                else:
                    self._record_tnp_failure(
                        feature=feature,
                        category="missing_ref",
                        reference_kind="face",
                        reason="sweep_profile_unresolved_topology_reference",
                        expected=2,
                        resolved=int(index_resolved) + int(shape_resolved),
                        strict=True,
                    )
                    raise ValueError(
                        "Sweep: Profil-Referenz ist inkonsistent "
                        "(profile_shape_id/profile_face_index). Bitte Profil neu auswählen."
                    )
            if (
                profile_face_from_index is not None
                and profile_face_from_shape is not None
                and not _is_same_face(profile_face_from_index, profile_face_from_shape)
            ):
                weak_shape_resolution = profile_shape_resolution_method in {"geometric", "geometry_hash"}
                if single_profile_ref_pair and weak_shape_resolution:
                    feature.profile_shape_id = None
                    if profile_face_index is not None:
                        feature.profile_face_index = int(profile_face_index)
                    _persist_profile_shape_id(profile_face_from_index)
                    profile_face = profile_face_from_index
                    self._record_tnp_failure(
                        feature=feature,
                        category="drift",
                        reference_kind="face",
                        reason="single_ref_pair_geometric_shape_conflict_index_preferred",
                        expected=1,
                        resolved=1,
                        strict=False,
                    )
                    if is_enabled("tnp_debug_logging"):
                        logger.warning(
                            "Sweep: single_ref_pair Profile Shape/Index-Konflikt mit schwacher "
                            "Shape-Aufloesung (geometric/hash) -> index-basiertes Profil bevorzugt."
                        )
                else:
                    self._record_tnp_failure(
                        feature=feature,
                        category="mismatch",
                        reference_kind="face",
                        reason="sweep_profile_shape_index_mismatch",
                        expected=2,
                        resolved=2,
                        strict=True,
                    )
                    raise ValueError(
                        "Sweep: Profil-Referenz ist inkonsistent "
                        "(profile_shape_id != profile_face_index). Bitte Profil neu auswählen."
                    )
            profile_face = profile_face_from_index

        if profile_face is None and has_topological_profile_refs:
            logger.warning(
                "Sweep: TNP-Profilreferenz konnte nicht aufgelöst werden "
                "(profile_shape_id/profile_face_index). Kein Geometric-Fallback."
            )
            self._record_tnp_failure(
                feature=feature,
                category="missing_ref",
                reference_kind="face",
                reason="sweep_profile_unresolved_topology_reference",
                expected=1,
                resolved=0,
                strict=True,
            )
            raise ValueError("Sweep: Profil-Referenz ist ungültig. Bitte Profil neu auswählen.")

        # TNP v4.0 Fallback: GeometricFaceSelector (nur wenn keine topologischen Refs vorhanden)
        if profile_face is None and profile_source_solid is not None and feature.profile_geometric_selector:
            try:
                from modeling.geometric_selector import GeometricFaceSelector
                from modeling.topology_indexing import face_index_of

                selectors = [feature.profile_geometric_selector]
                if isinstance(feature.profile_geometric_selector, list):
                    selectors = feature.profile_geometric_selector

                all_faces = list(profile_source_solid.faces()) if hasattr(profile_source_solid, 'faces') else []
                for selector_data in selectors:
                    if isinstance(selector_data, dict):
                        geo_sel = GeometricFaceSelector.from_dict(selector_data)
                    elif hasattr(selector_data, 'find_best_match'):
                        geo_sel = selector_data
                    else:
                        continue

                    best_face = geo_sel.find_best_match(all_faces)
                    if best_face is not None:
                        profile_face = best_face
                        feature.profile_face_index = face_index_of(profile_source_solid, profile_face)
                        _persist_profile_shape_id(profile_face)
                        break
            except Exception as e:
                logger.debug(f"Sweep: Profil über GeometricSelector fehlgeschlagen: {e}")

        # Legacy-Fallback: Profil aus gespeicherten Geometriedaten (Sketch-Profil)
        if profile_face is None:
            profile_face = self._profile_data_to_face(feature.profile_data)
        if profile_face is None:
            raise ValueError("Konnte Profil-Face nicht erstellen")

        # Pfad auflösen
        path_wire = self._resolve_path(feature.path_data, current_solid, feature)
        if path_wire is None:
            raise ValueError("Konnte Pfad nicht auflösen")

        # WICHTIG: Profil zum Pfad-Start verschieben
        profile_face = self._move_profile_to_path_start(profile_face, path_wire, feature)

        # OCP-First Sweep mit Voranalyse für optimale Methode
        twist_angle = getattr(feature, 'twist_angle', 0.0)
        scale_start = getattr(feature, 'scale_start', 1.0)
        scale_end = getattr(feature, 'scale_end', 1.0)
        has_twist_or_scale = (twist_angle != 0.0 or scale_start != 1.0 or scale_end != 1.0)

        logger.debug(f"Sweep OCP-First: Frenet={feature.is_frenet}, Twist={twist_angle}°, Scale={scale_start}->{scale_end}")

        # Voranalyse: Pfad-Komplexität bestimmen
        is_curved_path = self._is_curved_path(path_wire)
        has_spine = hasattr(feature, 'spine') and feature.spine is not None

        # OCP-Importe
        from OCP.BRepOffsetAPI import BRepOffsetAPI_MakePipe, BRepOffsetAPI_MakePipeShell
        from OCP.GeomFill import GeomFill_IsCorrectedFrenet, GeomFill_IsConstantNormal
        from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeWire
        from OCP.TopExp import TopExp_Explorer
        from OCP.TopAbs import TopAbs_EDGE
        from build123d import Solid

        face_shape = profile_face.wrapped if hasattr(profile_face, 'wrapped') else profile_face
        path_shape = path_wire.wrapped if hasattr(path_wire, 'wrapped') else path_wire

        # Validierung: Shape muss OCP-TopoDS_Shape sein
        if path_shape is None:
            raise ValueError("Sweep: Pfad ist None")
        type_name = type(path_shape).__name__
        if 'TopoDS' not in type_name and path_shape.__class__.__module__ != 'OCP.TopoDS':
            raise ValueError(f"Sweep: Pfad ist kein OCP Shape (Typ: {type_name})")

        # Profil-Wire extrahieren (für MakePipeShell)
        profile_wire = None
        if hasattr(profile_face, 'outer_wire'):
            try:
                profile_wire = profile_face.outer_wire()
                if hasattr(profile_wire, 'wrapped'):
                    profile_wire = profile_wire.wrapped
            except Exception as e:
                logger.debug(f"Sweep: outer_wire() fehlgeschlagen: {e}")

        # Fallback: OCP Wire-Building aus Edges
        if profile_wire is None:
            explorer = TopExp_Explorer(face_shape, TopAbs_EDGE)
            profile_wire_builder = BRepBuilderAPI_MakeWire()
            while explorer.More():
                try:
                    profile_wire_builder.Add(explorer.Current())
                except Exception:
                    pass
                explorer.Next()

            if not profile_wire_builder.IsDone():
                raise ValueError("Sweep: Profil-Wire Extraktion fehlgeschlagen")
            profile_wire = profile_wire_builder.Wire()

        # OCP-First: Einziger Pfad mit Methoden-Wahl
        result_shape = None

        # Einfacher Pfad → MakePipe (schneller, zuverlässiger)
        if not is_curved_path and not has_twist_or_scale and not feature.is_frenet and not has_spine:
            logger.debug("Sweep: Verwende MakePipe (einfacher Pfad)")
            pipe_op = BRepOffsetAPI_MakePipe(path_shape, face_shape)
            pipe_op.Build()

            if not pipe_op.IsDone():
                raise ValueError("Sweep MakePipe fehlgeschlagen: IsDone()=False")

            result_shape = pipe_op.Shape()

        # Komplexer Pfad oder Twist/Scale → MakePipeShell
        else:
            logger.debug(f"Sweep: Verwende MakePipeShell (curved={is_curved_path}, frenet={feature.is_frenet}, twist/scale={has_twist_or_scale})")
            pipe_shell = BRepOffsetAPI_MakePipeShell(path_shape)

            # Trihedron-Mode setzen
            if feature.is_frenet:
                pipe_shell.SetMode(GeomFill_IsCorrectedFrenet)
            else:
                pipe_shell.SetMode(GeomFill_IsConstantNormal)

            # Advanced: Twist/Scale mit Law-Funktionen
            if has_twist_or_scale:
                try:
                    from OCP.Law import Law_Linear

                    # Scale-Law erstellen
                    if scale_start != 1.0 or scale_end != 1.0:
                        scale_law = Law_Linear()
                        scale_law.Set(0.0, scale_start, 1.0, scale_end)
                        pipe_shell.SetLaw(profile_wire, scale_law, False, False)
                        logger.debug(f"Sweep: Scale-Law {scale_start}->{scale_end} angewendet")
                    else:
                        pipe_shell.Add(profile_wire, False, False)

                    # Twist wird über Approximation realisiert
                    if twist_angle != 0.0:
                        logger.info(f"Sweep: Twist {twist_angle}° wird approximiert")
                except ImportError:
                    logger.debug("OCP.Law nicht verfügbar, Standard-Add verwenden")
                    pipe_shell.Add(profile_wire, False, False)
            else:
                pipe_shell.Add(profile_wire, False, False)

            pipe_shell.Build()

            if not pipe_shell.IsDone():
                raise ValueError("Sweep MakePipeShell fehlgeschlagen: IsDone()=False")

            try:
                pipe_shell.MakeSolid()
            except Exception:
                pass  # MakeSolid optional für geschlossene Profile

            result_shape = pipe_shell.Shape()

        # Shape-Fix und Validierung
        result_shape = self._fix_shape_ocp(result_shape)
        result = Solid(result_shape)

        if not result.is_valid():
            raise ValueError("Sweep erzeugte keinen gültigen Solid")

        # TNP-Registration wenn naming_service verfügbar
        if self._document and hasattr(self._document, '_shape_naming_service'):
            try:
                naming_service = self._document._shape_naming_service
                feature_id = getattr(feature, 'id', None) or str(id(feature))

                # Alle Faces registrieren
                from modeling.tnp_system import ShapeType
                from OCP.TopExp import TopExp_Explorer
                from OCP.TopAbs import TopAbs_FACE

                explorer = TopExp_Explorer(result_shape, TopAbs_FACE)
                face_idx = 0
                while explorer.More():
                    ocp_face = explorer.Current()
                    fc = self._get_face_center(ocp_face)
                    area = self._get_face_area(ocp_face)
                    naming_service.register_shape(
                        ocp_shape=ocp_face,
                        shape_type=ShapeType.FACE,
                        feature_id=feature_id,
                        local_index=face_idx,
                        geometry_data=(fc.X, fc.Y, fc.Z, area),
                    )
                    face_idx += 1
                    explorer.Next()

                logger.debug(f"Sweep: {face_idx} Faces registriert")
            except Exception as e:
                logger.debug(f"Sweep TNP-Registration fehlgeschlagen: {e}")

        logger.debug("Sweep OCP-First erfolgreich")
        return result

    def _move_profile_to_path_start(self, profile_face, path_wire, feature):
        """
        Verschiebt das Profil zum Startpunkt des Pfads.
        """
        try:
            from build123d import Vector, Location

            path_edges = path_wire.edges() if hasattr(path_wire, 'edges') else []
            if not path_edges:
                logger.warning("Sweep: Pfad hat keine Edges, Ã¼berspringe Profil-Verschiebung")
                return profile_face

            first_edge = path_edges[0]

            if hasattr(first_edge, 'start_point'):
                path_start = first_edge.start_point()
            elif hasattr(first_edge, 'position_at'):
                path_start = first_edge.position_at(0)
            else:
                vertices = first_edge.vertices() if hasattr(first_edge, 'vertices') else []
                if vertices:
                    path_start = vertices[0].center() if hasattr(vertices[0], 'center') else Vector(0, 0, 0)
                else:
                    logger.warning("Sweep: Konnte Pfad-Startpunkt nicht ermitteln")
                    return profile_face

            profile_center = profile_face.center() if hasattr(profile_face, 'center') else None
            if profile_center is None:
                profile_data = feature.profile_data
                origin = profile_data.get('plane_origin', (0, 0, 0))
                profile_center = Vector(*origin)

            if isinstance(path_start, tuple):
                path_start = Vector(*path_start)

            translation = path_start - profile_center

            if translation.length < 0.1:
                logger.debug("Sweep: Profil bereits am Pfad-Start")
                return profile_face

            logger.info(f"Sweep: Verschiebe Profil um {translation.length:.1f}mm zum Pfad-Start")
            moved_face = profile_face.move(Location(translation))

            return moved_face

        except Exception as e:
            logger.warning(f"Sweep: Profil-Verschiebung fehlgeschlagen: {e}, verwende Original")
            return profile_face

    def _is_curved_path(self, path_wire) -> bool:
        """
        Analysiert ob der Pfad gekrÃ¼mmt ist (nicht gerade).
        """
        try:
            edges = list(path_wire.edges()) if hasattr(path_wire, 'edges') else []
            if len(edges) == 0:
                return False
            if len(edges) == 1:
                edge = edges[0]
                try:
                    start_tangent = edge.tangent_at(0) if hasattr(edge, 'tangent_at') else None
                    end_tangent = edge.tangent_at(1) if hasattr(edge, 'tangent_at') else None
                    if start_tangent and end_tangent:
                        dot = (start_tangent.X * end_tangent.X +
                                start_tangent.Y * end_tangent.Y +
                                start_tangent.Z * end_tangent.Z)
                        mag1 = (start_tangent.X**2 + start_tangent.Y**2 + start_tangent.Z**2)**0.5
                        mag2 = (end_tangent.X**2 + end_tangent.Y**2 + end_tangent.Z**2)**0.5
                        if mag1 > 0 and mag2 > 0:
                            cos_angle = dot / (mag1 * mag2)
                            return abs(cos_angle - 1.0) > 0.01
                except Exception:
                    pass
                edge_type = edge.geom_type() if hasattr(edge, 'geom_type') else ''
                return edge_type not in ('LINE', 'FORWARD')

            vertices = []
            for edge in edges:
                verts = list(edge.vertices()) if hasattr(edge, 'vertices') else []
                vertices.extend([v.center() if hasattr(v, 'center') else v for v in verts])
            if len(vertices) < 3:
                return False

            v0 = vertices[0]
            v1 = vertices[-1]
            direction = v1 - v0
            dir_length = (direction.X**2 + direction.Y**2 + direction.Z**2)**0.5
            if dir_length < 1e-6:
                return False
            for vi in vertices[1:-1]:
                vi_v0 = vi - v0
                cross_x = direction.Y * vi_v0.Z - direction.Z * vi_v0.Y
                cross_y = direction.Z * vi_v0.X - direction.X * vi_v0.Z
                cross_z = direction.X * vi_v0.Y - direction.Y * vi_v0.X
                cross_mag = (cross_x**2 + cross_y**2 + cross_z**2)**0.5
                if cross_mag > 0.1:
                    return True
            return False
        except Exception as e:
            logger.debug(f"_is_curved_path Analyse fehlgeschlagen: {e}, assume curved")
            return True

    def _compute_shell(self, feature: 'ShellFeature', current_solid):
        """
        OCP-First Shell mit direktem OpenCASCADE BRepOffsetAPI_MakeThickSolid.

        Unterstützt:
        - Shell mit Öffnungen (faces_to_remove)
        - Geschlossener Hohlkörper (leere faces_to_remove)
        """
        if current_solid is None:
            raise ValueError("Shell benötigt einen existierenden Körper")

        # Öffnungs-Faces auflösen (TNP v4.0)
        opening_faces = self._resolve_feature_faces(feature, current_solid)
        has_opening_refs = bool(
            feature.face_shape_ids
            or feature.face_indices
            or feature.opening_face_selectors
        )
        if has_opening_refs and not opening_faces:
            raise ValueError(
                "Shell: Öffnungs-Faces konnten via TNP v4.0 nicht aufgelöst werden "
                "(ShapeID/face_indices). Kein Geometric-Fallback."
            )

        logger.debug(f"Shell mit Dicke={feature.thickness}mm, {len(opening_faces)} Öffnungen")

        # OCP-First Shell
        from OCP.BRepOffsetAPI import BRepOffsetAPI_MakeThickSolid
        from OCP.TopTools import TopTools_ListOfShape
        from config.tolerances import Tolerances
        from build123d import Solid

        shape = current_solid.wrapped if hasattr(current_solid, 'wrapped') else current_solid

        # Liste der zu entfernenden Faces
        faces_to_remove = TopTools_ListOfShape()
        for face in opening_faces:
            face_shape = face.wrapped if hasattr(face, 'wrapped') else face
            faces_to_remove.Append(face_shape)

        # Shell erstellen (MakeThickSolidByJoin)
        shell_op = BRepOffsetAPI_MakeThickSolid()
        shell_op.MakeThickSolidByJoin(
            shape,
            faces_to_remove,  # Leer = geschlossener Hohlkörper
            -feature.thickness,  # Negativ für nach innen
            Tolerances.SHELL_TOLERANCE
        )
        shell_op.Build()

        if not shell_op.IsDone():
            raise ValueError(f"Shell OCP-Operation fehlgeschlagen: IsDone()=False")

        result_shape = shell_op.Shape()
        result_shape = self._fix_shape_ocp(result_shape)

        # Zu Build123d Solid wrappen
        result = Solid(result_shape)

        if not result.is_valid():
            raise ValueError("Shell erzeugte keinen gültigen Solid")

        # TNP-Registration wenn naming_service verfügbar
        if self._document and hasattr(self._document, '_shape_naming_service'):
            try:
                naming_service = self._document._shape_naming_service
                feature_id = getattr(feature, 'id', None) or str(id(feature))

                # Alle Faces registrieren
                from modeling.tnp_system import ShapeType
                from OCP.TopExp import TopExp_Explorer
                from OCP.TopAbs import TopAbs_FACE

                explorer = TopExp_Explorer(result_shape, TopAbs_FACE)
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
                naming_service.register_solid_edges(result, feature_id)

                if is_enabled("tnp_debug_logging"):
                    logger.success(f"Shell TNP: {face_idx} Faces registriert")

            except Exception as e:
                logger.error(f"Shell TNP Registration fehlgeschlagen: {e}")

        logger.debug(f"OCP Shell erfolgreich ({len(opening_faces)} Öffnungen)")
        return result

    def _unify_same_domain(self, shape, context: str = ""):
        """Unifies same domain faces in a shape."""
        try:
            from OCP.ShapeUpgrade import ShapeUpgrade_UnifySameDomain
            from build123d import Solid

            ocp_shape = shape.wrapped if hasattr(shape, 'wrapped') else shape
            upgrader = ShapeUpgrade_UnifySameDomain(ocp_shape, True, True, True)
            upgrader.SetLinearTolerance(0.1)
            upgrader.SetAngularTolerance(0.1)
            upgrader.Build()
            unified_shape = upgrader.Shape()

            if unified_shape and not unified_shape.IsNull():
                return Solid(unified_shape)
        except Exception as e:
            logger.debug(f"UnifySameDomain fehlgeschlagen ({context}): {e}")
        return shape

    def _compute_nsided_patch(self, feature: 'NSidedPatchFeature', current_solid):
        """
        N-Sided Patch: Boundary-Edges finden und mit BRepFill_Filling füllen.
        Das Ergebnis wird per Sewing an den bestehenden Solid angefügt.
        """
        if current_solid is None:
            raise ValueError("N-Sided Patch benötigt einen existierenden Körper")

        all_edges = current_solid.edges() if hasattr(current_solid, 'edges') else []
        if not all_edges:
            raise ValueError("Solid hat keine Kanten")
        if not feature.edge_shape_ids and not feature.edge_indices and not feature.geometric_selectors:
            raise ValueError("N-Sided Patch benötigt mindestens 3 Kanten-Referenzen")

        resolved_edges = []

        def _is_same_edge(edge_a, edge_b) -> bool:
            try:
                wa = edge_a.wrapped if hasattr(edge_a, 'wrapped') else edge_a
                wb = edge_b.wrapped if hasattr(edge_b, 'wrapped') else edge_b
                return wa.IsSame(wb)
            except Exception:
                return edge_a is edge_b

        def _append_unique(edge_obj) -> None:
            if edge_obj is None:
                return
            for existing in resolved_edges:
                if _is_same_edge(existing, edge_obj):
                    return
            resolved_edges.append(edge_obj)

        # TNP v4.0: Zentraler Resolver (ShapeID / edge_indices / strict Selector-Policy)
        tnp_edges = self._resolve_edges_tnp(current_solid, feature)
        for edge in tnp_edges:
            _append_unique(edge)
        if is_enabled("tnp_debug_logging"):
            logger.debug(
                f"N-Sided Patch: {len(tnp_edges)} Edges via zentralem TNP-Resolver aufgelöst"
            )

        # Für zukünftige Rebuilds ShapeIDs + GeometricSelectors + Edge-Indizes persistieren
        if resolved_edges:
            try:
                resolved_indices = []
                for edge in resolved_edges:
                    for edge_idx, candidate in enumerate(all_edges):
                        if _is_same_edge(candidate, edge):
                            resolved_indices.append(edge_idx)
                            break
                if resolved_indices:
                    feature.edge_indices = resolved_indices
            except Exception as e:
                logger.debug(f"N-Sided Patch: Persistieren von Edge-Indizes fehlgeschlagen: {e}")

        if resolved_edges and self._document and hasattr(self._document, '_shape_naming_service'):
            try:
                from modeling.geometric_selector import GeometricEdgeSelector
                from modeling.tnp_system import ShapeType
                service = self._document._shape_naming_service

                new_shape_ids = []
                new_geo_selectors = []
                for idx, edge in enumerate(resolved_edges):
                    new_geo_selectors.append(GeometricEdgeSelector.from_edge(edge).to_dict())
                    shape_id = service.find_shape_id_by_edge(edge)
                    if shape_id is None and hasattr(edge, 'wrapped'):
                        ec = edge.center()
                        edge_len = edge.length if hasattr(edge, 'length') else 0.0
                        shape_id = service.register_shape(
                            ocp_shape=edge.wrapped,
                            shape_type=ShapeType.EDGE,
                            feature_id=feature.id,
                            local_index=idx,
                            geometry_data=(ec.X, ec.Y, ec.Z, edge_len)
                        )
                    if shape_id is not None:
                        new_shape_ids.append(shape_id)

                if new_shape_ids:
                    feature.edge_shape_ids = new_shape_ids
                if new_geo_selectors:
                    feature.geometric_selectors = new_geo_selectors
            except Exception as e:
                logger.debug(f"N-Sided Patch: Persistieren von ShapeIDs fehlgeschlagen: {e}")

        if len(resolved_edges) < 3:
            expected = (
                len(feature.edge_shape_ids or [])
                or len(feature.edge_indices or [])
                or len(feature.geometric_selectors or [])
            )
            logger.warning(f"Nur {len(resolved_edges)} von {expected} Kanten aufgelöst")
            raise ValueError(f"Nur {len(resolved_edges)} von {expected} Kanten aufgelöst")

        logger.debug(f"N-Sided Patch: {len(resolved_edges)} Kanten, Grad={feature.degree}")

        from modeling.nsided_patch import NSidedPatch

        # Patch erstellen
        patch_face = NSidedPatch.fill_edges(
            resolved_edges,
            tangent_faces=NSidedPatch._find_adjacent_faces(
                current_solid, resolved_edges
            ) if feature.tangent else None,
            degree=feature.degree,
        )

        if patch_face is None:
            raise RuntimeError("N-Sided Patch: BRepFill_Filling fehlgeschlagen")

        # Patch-Face zum Solid hinzufügen
        try:
            from OCP.BRepBuilderAPI import BRepBuilderAPI_Sewing, BRepBuilderAPI_MakeSolid
            from OCP.TopExp import TopExp_Explorer
            from OCP.TopAbs import TopAbs_SHELL, TopAbs_FACE
            from OCP.TopoDS import TopoDS
            from OCP.BRep import BRep_Builder
            from OCP.TopoDS import TopoDS_Shell, TopoDS_Compound
            from build123d import Solid

            shape = current_solid.wrapped if hasattr(current_solid, 'wrapped') else current_solid
            patch_shape = patch_face.wrapped if hasattr(patch_face, 'wrapped') else patch_face

            # Sewing mit größerer Toleranz für bessere Verbindung
            sewing = BRepBuilderAPI_Sewing(0.1)  # 0.1mm Toleranz
            sewing.SetNonManifoldMode(False)  # Manifold-Ergebnis erzwingen

            # Alle Faces des Original-Solids hinzufügen
            face_explorer = TopExp_Explorer(shape, TopAbs_FACE)
            n_faces = 0
            while face_explorer.More():
                sewing.Add(face_explorer.Current())
                n_faces += 1
                face_explorer.Next()

            # Patch-Face hinzufügen
            sewing.Add(patch_shape)
            logger.debug(f"N-Sided Patch: Sewing {n_faces} Original-Faces + 1 Patch-Face")

            sewing.Perform()
            sewn = sewing.SewedShape()

            # Prüfe Sewing-Ergebnis
            n_sewn_faces = 0
            face_exp = TopExp_Explorer(sewn, TopAbs_FACE)
            while face_exp.More():
                n_sewn_faces += 1
                face_exp.Next()
            logger.debug(f"N-Sided Patch: Sewing-Ergebnis hat {n_sewn_faces} Faces (erwartet: {n_faces + 1})")

            # Versuche Solid zu bauen
            shell_explorer = TopExp_Explorer(sewn, TopAbs_SHELL)
            if shell_explorer.More():
                shell = TopoDS.Shell_s(shell_explorer.Current())

                # Prüfe ob Shell geschlossen ist
                from OCP.BRep import BRep_Tool
                from OCP.ShapeAnalysis import ShapeAnalysis_Shell
                analyzer = ShapeAnalysis_Shell()
                analyzer.LoadShells(shell)
                is_closed = not analyzer.HasFreeEdges()
                logger.debug(f"N-Sided Patch: Shell geschlossen = {is_closed}")

                maker = BRepBuilderAPI_MakeSolid(shell)
                maker.Build()

                if maker.IsDone():
                    result = Solid(maker.Shape())
                    result_faces = len(result.faces()) if hasattr(result, 'faces') else 0
                    if hasattr(result, 'is_valid') and result.is_valid():
                        logger.debug(f"N-Sided Patch: Loch geschlossen! ({result_faces} Faces)")
                        return result
                    else:
                        logger.warning(f"N-Sided Patch: Solid mit {result_faces} Faces ungültig, versuche ShapeFix...")
                        try:
                            from OCP.ShapeFix import ShapeFix_Solid
                            fixer = ShapeFix_Solid(maker.Shape())
                            fixer.Perform()
                            if fixer.Shape() and not fixer.Shape().IsNull():
                                fixed = Solid(fixer.Shape())
                                if hasattr(fixed, 'is_valid') and fixed.is_valid():
                                    logger.debug(f"N-Sided Patch: ShapeFix erfolgreich")
                                    return fixed
                        except Exception as fix_err:
                            logger.debug(f"ShapeFix fehlgeschlagen: {fix_err}")
            else:
                logger.warning("N-Sided Patch: Keine Shell im Sewing-Ergebnis")

            # Fallback: Versuche größere Toleranz
            logger.warning("N-Sided Patch: Erster Sewing-Versuch fehlgeschlagen, versuche mit höherer Toleranz...")
            sewing2 = BRepBuilderAPI_Sewing(1.0)  # 1mm Toleranz
            sewing2.SetNonManifoldMode(False)

            face_explorer2 = TopExp_Explorer(shape, TopAbs_FACE)
            while face_explorer2.More():
                sewing2.Add(face_explorer2.Current())
                face_explorer2.Next()
            sewing2.Add(patch_shape)
            sewing2.Perform()
            sewn2 = sewing2.SewedShape()

            shell_exp2 = TopExp_Explorer(sewn2, TopAbs_SHELL)
            if shell_exp2.More():
                shell2 = TopoDS.Shell_s(shell_exp2.Current())
                maker2 = BRepBuilderAPI_MakeSolid(shell2)
                maker2.Build()
                if maker2.IsDone():
                    result2 = Solid(maker2.Shape())
                    if hasattr(result2, 'is_valid') and result2.is_valid():
                        logger.debug(f"N-Sided Patch: Loch geschlossen mit höherer Toleranz!")
                        return result2

            # Letzter Fallback
            logger.warning("N-Sided Patch: Sewing komplett fehlgeschlagen")
            from build123d import Shape
            return Shape(sewn)

        except Exception as e:
            logger.error(f"N-Sided Patch Sewing fehlgeschlagen: {e}")
            raise

    def _compute_hollow(self, feature: 'HollowFeature', current_solid):
        """
        Aushöhlen mit optionalem Drain Hole.
        1. Shell (geschlossen) via _compute_shell-Logik
        2. Optional: Boolean Cut mit Zylinder für Drain Hole
        """
        if current_solid is None:
            raise ValueError("Hollow benötigt einen existierenden Körper")

        from modeling.features.advanced import ShellFeature

        # TNP v4.0: Face-Referenzen vor der Shell-Ausführung aktualisieren
        self._update_face_selectors_for_feature(feature, current_solid)

        # Step 1: Create closed shell (reuse shell logic)
        shell_feat = ShellFeature(
            thickness=feature.wall_thickness,
            opening_face_selectors=feature.opening_face_selectors if feature.opening_face_selectors else []
        )
        # Übertrage Opening-ShapeIDs auf ShellFeature.face_shape_ids (TNP v4.0)
        if feature.opening_face_shape_ids:
            shell_feat.face_shape_ids = list(feature.opening_face_shape_ids)
        if feature.opening_face_indices:
            shell_feat.face_indices = list(feature.opening_face_indices)

        hollowed = self._compute_shell(shell_feat, current_solid)
        if hollowed is None:
            raise ValueError("Shell-Erzeugung fehlgeschlagen")

        # Step 2: Drain hole (optional)
        if feature.drain_hole and feature.drain_diameter > 0:
            try:
                from build123d import Cylinder, Location, Vector, Solid
                import math

                pos = feature.drain_position
                d = feature.drain_direction
                radius = feature.drain_diameter / 2.0

                # Hole must be long enough to pierce through the wall
                bb = hollowed.bounding_box()
                safe_length = 2.0 * max(bb.size.X, bb.size.Y, bb.size.Z)

                cyl = Cylinder(radius, safe_length)

                # Align cylinder along drain direction
                z_axis = Vector(0, 0, 1)
                drain_vec = Vector(*d)
                if drain_vec.length > 1e-9:
                    drain_vec = drain_vec.normalized()
                else:
                    drain_vec = Vector(0, 0, -1)

                from build123d import Pos, Rot
                center = Vector(*pos) - drain_vec * (safe_length / 2)

                # Compute rotation from Z to drain direction
                cross = z_axis.cross(drain_vec)
                dot = z_axis.dot(drain_vec)
                if cross.length > 1e-9:
                    angle = math.degrees(math.acos(max(-1, min(1, dot))))
                    axis = cross.normalized()
                    from build123d import Axis
                    cyl = cyl.rotate(Axis.Z, 0)  # identity
                    from OCP.gp import gp_Ax1, gp_Pnt, gp_Dir, gp_Trsf
                    trsf = gp_Trsf()
                    trsf.SetRotation(
                        gp_Ax1(gp_Pnt(0, 0, 0), gp_Dir(axis.X, axis.Y, axis.Z)),
                        math.radians(angle)
                    )
                    trsf.SetTranslationPart(
                        gp_Pnt(center.X, center.Y, center.Z).XYZ()
                    )
                    from OCP.BRepBuilderAPI import BRepBuilderAPI_Transform
                    builder = BRepBuilderAPI_Transform(cyl.wrapped, trsf, True)
                    builder.Build()
                    cyl = Solid(builder.Shape())
                elif dot < 0:
                    # Anti-parallel: rotate 180° around X
                    from build123d import Axis
                    cyl = cyl.rotate(Axis.X, 180)
                    cyl = cyl.move(Location((center.X, center.Y, center.Z)))
                else:
                    cyl = cyl.move(Location((center.X, center.Y, center.Z)))

                result = hollowed - cyl
                if result and hasattr(result, 'is_valid') and result.is_valid():
                    logger.debug(f"Hollow mit Drain Hole (D{feature.drain_diameter}mm) erfolgreich")
                    return result
                else:
                    logger.warning("Drain Hole Boolean fehlgeschlagen, verwende Shell ohne Drain")
                    return hollowed

            except Exception as e:
                logger.warning(f"Drain Hole fehlgeschlagen: {e}, verwende Shell ohne Drain")
                return hollowed

        logger.debug(f"Hollow (Wandstärke {feature.wall_thickness}mm) erfolgreich")
        return hollowed

    def _compute_hole(self, feature: 'HoleFeature', current_solid):
        """
        Erstellt eine Bohrung.

        Methoden (in Priorität):
        1. BRepFeat_MakeCylindricalHole (für simple holes - saubere Topologie)
        2. Boolean Cut mit Zylinder (für counterbore, countersink, oder Fallback)
        """
        from build123d import Cylinder, Vector, Align
        import math

        if current_solid is None:
            raise ValueError("Hole: Kein gültiges Eingabe-Solid vorhanden")
        if feature.diameter <= 0:
            raise ValueError(f"Hole: Ungültiger Durchmesser {feature.diameter}mm (muss > 0 sein)")
        if feature.depth < 0:
            raise ValueError(f"Hole: Ungültige Tiefe {feature.depth}mm (muss >= 0 sein)")
        if feature.hole_type not in {"simple", "counterbore", "countersink"}:
            raise ValueError(f"Hole: Unbekannter hole_type '{feature.hole_type}'")
        if feature.hole_type == "counterbore":
            if feature.counterbore_diameter <= feature.diameter:
                raise ValueError(
                    f"Hole: Counterbore-Durchmesser {feature.counterbore_diameter}mm "
                    f"muss größer als Bohrungsdurchmesser {feature.diameter}mm sein"
                )
            if feature.counterbore_depth <= 0:
                raise ValueError(f"Hole: Counterbore-Tiefe {feature.counterbore_depth}mm muss > 0 sein")
        if feature.hole_type == "countersink":
            if feature.countersink_angle <= 0 or feature.countersink_angle >= 179:
                raise ValueError(
                    f"Hole: Countersink-Winkel {feature.countersink_angle}° ist ungültig "
                    "(erwartet: 0 < Winkel < 179)"
                )

        # TNP v4.0: Face-Referenzen auflösen/aktualisieren
        target_faces = self._resolve_feature_faces(feature, current_solid)
        has_face_refs = bool(feature.face_shape_ids or feature.face_indices or feature.face_selectors)
        if has_face_refs and not target_faces:
            raise ValueError(
                "Hole: Ziel-Face konnte via TNP v4.0 nicht aufgelöst werden "
                f"(ShapeIDs={len(feature.face_shape_ids or [])}, "
                f"Indices={len(feature.face_indices or [])}, "
                f"Selectors={len(feature.face_selectors or [])})"
            )

        pos = Vector(*feature.position)
        d = Vector(*feature.direction)
        if target_faces:
            # Falls Richtung ungültig ist, aus Face-Normale ableiten
            try:
                face_center = target_faces[0].center()
                face_normal = target_faces[0].normal_at(face_center)
                if d.length < 1e-9:
                    d = Vector(-face_normal.X, -face_normal.Y, -face_normal.Z)
                if pos.length < 1e-9:
                    pos = Vector(face_center.X, face_center.Y, face_center.Z)
            except Exception:
                pass

        if d.length < 1e-9:
            raise ValueError("Hole: Ungültige Bohrungsrichtung (Nullvektor)")

        d = d.normalized()
        radius = feature.diameter / 2.0

        # Tiefe: 0 = through all (verwende große Tiefe)
        depth = feature.depth if feature.depth > 0 else 1000.0

        logger.debug(f"Hole: type={feature.hole_type}, D={feature.diameter}mm, depth={depth}mm at {pos}")

        # === METHODE 1: BRepFeat_MakeCylindricalHole (nur für simple holes) ===
        brepfeat_reason = ""
        if feature.hole_type == "simple":
            try:
                from modeling.brepfeat_operations import brepfeat_cylindrical_hole

                result = brepfeat_cylindrical_hole(
                    base_solid=current_solid,
                    position=(pos.X, pos.Y, pos.Z),
                    direction=(d.X, d.Y, d.Z),
                    diameter=feature.diameter,
                    depth=feature.depth  # 0 = through all
                )

                if result is not None:
                    logger.debug(f"Hole via BRepFeat: D={feature.diameter}mm")
                    return result
                else:
                    brepfeat_reason = "BRepFeat_MakeCylindricalHole lieferte kein Resultat"
                    logger.debug("BRepFeat_MakeCylindricalHole fehlgeschlagen, Fallback auf Boolean")
            except Exception as e:
                brepfeat_reason = f"BRepFeat Fehler: {e}"
                logger.debug(f"BRepFeat Hole: {e}, Fallback auf Boolean")

        # === METHODE 2: Boolean Cut (für counterbore, countersink, oder Fallback) ===

        # Hauptbohrung als Zylinder erstellen
        hole_cyl = Cylinder(radius, depth,
                            align=(Align.CENTER, Align.CENTER, Align.MIN))

        # Zylinder in Position bringen
        hole_shape = self._position_cylinder(hole_cyl, pos, d, depth)
        if hole_shape is None:
            raise ValueError("Hole-Zylinder konnte nicht positioniert werden")

        # Counterbore: zusaetzlicher breiterer Zylinder oben
        if feature.hole_type == "counterbore":
            cb_radius = feature.counterbore_diameter / 2.0
            cb_depth = feature.counterbore_depth
            cb_cyl = Cylinder(cb_radius, cb_depth,
                              align=(Align.CENTER, Align.CENTER, Align.MIN))
            cb_shape = self._position_cylinder(cb_cyl, pos, d, cb_depth)
            if cb_shape is None:
                raise ValueError("Hole: Counterbore-Geometrie konnte nicht positioniert werden")
            hole_shape = hole_shape.fuse(cb_shape)

        # Countersink: Kegel oben
        elif feature.hole_type == "countersink":
            cs_angle_rad = math.radians(feature.countersink_angle / 2.0)
            cs_depth = radius / math.tan(cs_angle_rad) if cs_angle_rad > 0 else 2.0
            from build123d import Cone
            cs_cone = Cone(feature.diameter, 0.01, cs_depth,
                           align=(Align.CENTER, Align.CENTER, Align.MIN))
            cs_shape = self._position_cylinder(cs_cone, pos, d, cs_depth)
            if cs_shape is None:
                raise ValueError("Hole: Countersink-Geometrie konnte nicht positioniert werden")
            hole_shape = hole_shape.fuse(cs_shape)

        # Boolean Cut: Bohrung vom Körper abziehen via BooleanEngineV4 (TNP-safe)
        # Zuerst Tool-Shapes registrieren (damit sie ShapeIDs haben)
        if self._document and hasattr(self._document, '_shape_naming_service'):
            # Wir registrieren das Tool als temporäres Feature oder unter der Hole-ID
            # Da das Hole-Feature das Tool "besitzt", ist es okay, die Faces des Tools
            # unter der Feature-ID zu registrieren.
            self._register_base_feature_shapes(feature, hole_shape)

        # Boolean ausführen
        from modeling.boolean_engine_v4 import BooleanEngineV4
        bool_result = BooleanEngineV4.execute_boolean_on_shapes(
            current_solid, hole_shape, "Cut"
        )

        if bool_result.is_success:
            result = bool_result.value
            self._register_boolean_history(bool_result, feature, operation_name="Hole_Cut")
            logger.debug(f"Hole {feature.hole_type} D={feature.diameter}mm erfolgreich (BooleanV4)")
            return result
        else:
            logger.warning(f"Hole Boolean fehlgeschlagen: {bool_result.message}")
            if brepfeat_reason:
                 raise ValueError(f"Hole fehlgeschlagen. BRepFeat: {brepfeat_reason}. Boolean: {bool_result.message}")
            raise ValueError(f"Hole Boolean fehlgeschlagen: {bool_result.message}")

    def _position_cylinder(self, cyl_solid, position, direction, depth):
        """Positioniert einen Zylinder an position entlang direction."""
        try:
            from build123d import Vector, Location
            import numpy as np

            # Support both tuples and Build123d Vectors
            if hasattr(direction, 'X'):
                d = np.array([direction.X, direction.Y, direction.Z], dtype=float)
            else:
                d = np.array([direction[0], direction[1], direction[2]], dtype=float)
            d_norm = d / (np.linalg.norm(d) + 1e-12)

            # Start etwas vor der Flaeche (damit der Cut sicher durchgeht)
            if hasattr(position, 'X'):
                pos = np.array([position.X, position.Y, position.Z])
            else:
                pos = np.array([position[0], position[1], position[2]])
            start = pos - d_norm * 0.5

            # Rotation berechnen: Z-Achse -> direction
            z_axis = np.array([0, 0, 1.0])
            if abs(np.dot(z_axis, d_norm)) > 0.999:
                # Parallel zu Z - keine Rotation noetig
                rotated = cyl_solid
            else:
                rot_axis = np.cross(z_axis, d_norm)
                rot_axis = rot_axis / (np.linalg.norm(rot_axis) + 1e-12)
                angle = np.arccos(np.clip(np.dot(z_axis, d_norm), -1, 1))

                from OCP.gp import gp_Trsf, gp_Ax1, gp_Pnt, gp_Dir
                from OCP.BRepBuilderAPI import BRepBuilderAPI_Transform
                import math

                trsf = gp_Trsf()
                ax = gp_Ax1(gp_Pnt(0, 0, 0), gp_Dir(rot_axis[0], rot_axis[1], rot_axis[2]))
                trsf.SetRotation(ax, angle)

                shape = cyl_solid.wrapped if hasattr(cyl_solid, 'wrapped') else cyl_solid
                builder = BRepBuilderAPI_Transform(shape, trsf, True)
                builder.Build()
                from build123d import Solid
                rotated = Solid(builder.Shape())

            # Translation
            from OCP.gp import gp_Trsf, gp_Vec as gp_V
            from OCP.BRepBuilderAPI import BRepBuilderAPI_Transform
            trsf2 = gp_Trsf()
            trsf2.SetTranslation(gp_V(start[0], start[1], start[2]))

            shape2 = rotated.wrapped if hasattr(rotated, 'wrapped') else rotated
            builder2 = BRepBuilderAPI_Transform(shape2, trsf2, True)
            builder2.Build()
            from build123d import Solid
            return Solid(builder2.Shape())

        except Exception as e:
            logger.error(f"Zylinder-Positionierung fehlgeschlagen: {e}")
            return None

    def _compute_draft(self, feature: 'DraftFeature', current_solid):
        """
        Wendet Draft/Taper auf selektierte Flächen an.
        Verwendet OCP BRepOffsetAPI_DraftAngle.
        TNP v4.0: Face-Selektion erfolgt über face_shape_ids (ShapeNamingService).
        """
        import math
        from OCP.BRepOffsetAPI import BRepOffsetAPI_DraftAngle
        from OCP.gp import gp_Dir, gp_Pln, gp_Pnt
        from OCP.TopAbs import TopAbs_FACE
        from OCP.TopExp import TopExp_Explorer
        from OCP.TopoDS import TopoDS

        shape = current_solid.wrapped if hasattr(current_solid, 'wrapped') else current_solid

        if current_solid is None:
            raise ValueError("Draft: Kein gültiges Eingabe-Solid vorhanden")
        if abs(feature.draft_angle) >= 89.9:
            raise ValueError(
                f"Draft: Ungültiger Winkel {feature.draft_angle}°. "
                "Erwartet |Winkel| < 89.9°"
            )
        if len(feature.pull_direction) < 3:
            raise ValueError("Draft: Pull-Richtung ist unvollständig")
        px, py, pz = feature.pull_direction[0], feature.pull_direction[1], feature.pull_direction[2]
        if (px * px + py * py + pz * pz) <= 1e-12:
            raise ValueError("Draft: Ungültige Pull-Richtung (Nullvektor)")

        pull_dir = gp_Dir(px, py, pz)
        angle_rad = math.radians(feature.draft_angle)

        # Neutrale Ebene (Basis der Entformung)
        neutral_plane = gp_Pln(gp_Pnt(0, 0, 0), pull_dir)

        target_faces = self._resolve_feature_faces(feature, current_solid)
        has_face_refs = bool(feature.face_shape_ids or feature.face_indices or feature.face_selectors)

        if has_face_refs and not target_faces:
            raise ValueError("Draft: Ziel-Faces konnten via TNP v4.0 nicht aufgelöst werden")

        draft_op = BRepOffsetAPI_DraftAngle(shape)
        face_count = 0
        add_errors = []

        if target_faces:
            for face_idx, target_face in enumerate(target_faces):
                try:
                    topo_face = target_face.wrapped if hasattr(target_face, 'wrapped') else target_face
                    draft_op.Add(TopoDS.Face_s(topo_face), pull_dir, angle_rad, neutral_plane)
                    face_count += 1
                except Exception as e:
                    add_errors.append(f"Face[{face_idx}] konnte nicht hinzugefügt werden: {e}")
        else:
            # Kein explizites Face-Target -> alle Faces draften (Legacy-Verhalten)
            explorer = TopExp_Explorer(shape, TopAbs_FACE)
            all_face_idx = 0
            while explorer.More():
                face = TopoDS.Face_s(explorer.Current())
                try:
                    draft_op.Add(face, pull_dir, angle_rad, neutral_plane)
                    face_count += 1
                except Exception as e:
                    add_errors.append(f"Face[{all_face_idx}] konnte nicht hinzugefügt werden: {e}")
                explorer.Next()
                all_face_idx += 1

        if face_count == 0:
            detail = add_errors[0] if add_errors else "kein kompatibles Ziel-Face gefunden"
            raise ValueError(f"Draft: Keine Flächen konnten gedraftet werden ({detail})")

        draft_op.Build()
        if draft_op.IsDone():
            result_shape = draft_op.Shape()
            result_shape = self._fix_shape_ocp(result_shape)

            # TNP v4.0: History Tracking für Draft
            if self._document and hasattr(self._document, '_shape_naming_service'):
                try:
                    service = self._document._shape_naming_service
                    feature_id = getattr(feature, 'id', None) or str(id(feature))
                    
                    # History tracken (Faces modified/generated)
                    service.track_draft_operation(
                        feature_id=feature_id,
                        source_solid=shape,
                        result_solid=result_shape,
                        occt_history=draft_op,
                        angle=feature.draft_angle
                    )
                except Exception as e:
                    logger.warning(f"Draft TNP tracking fail: {e}")

            from build123d import Solid
            result = Solid(result_shape)
            logger.debug(f"Draft {feature.draft_angle}° auf {face_count} Flächen erfolgreich")
            return result

        raise ValueError("Draft-Operation fehlgeschlagen")

    def _compute_split(self, feature: 'SplitFeature', current_solid):
        """
        Teilt einen Koerper entlang einer Ebene.

        TNP v4.0 / Multi-Body Architecture:
        - Berechnet BEIDE Hälften (above + below)
        - Gibt SplitResult zurück mit beiden Bodies
        - Für legacy keep_side != "both": Gibt nur eine Hälfte als Solid zurück
        """
        from OCP.BRepAlgoAPI import BRepAlgoAPI_Section
        from OCP.gp import gp_Pln, gp_Pnt, gp_Dir
        from OCP.BRepPrimAPI import BRepPrimAPI_MakeHalfSpace
        from OCP.BRepAlgoAPI import BRepAlgoAPI_Cut
        from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeFace
        import numpy as np

        shape = current_solid.wrapped if hasattr(current_solid, 'wrapped') else current_solid

        origin = gp_Pnt(*feature.plane_origin)
        normal = gp_Dir(*feature.plane_normal)
        plane = gp_Pln(origin, normal)

        logger.debug(f"Split: origin={feature.plane_origin}, normal={feature.plane_normal}, keep={feature.keep_side}")

        # === Phase 1: Grosse Ebene als Face erstellen ===
        face_builder = BRepBuilderAPI_MakeFace(plane, -1000, 1000, -1000, 1000)
        face_builder.Build()
        if not face_builder.IsDone():
            raise ValueError("Split-Ebene konnte nicht erstellt werden")

        split_face = face_builder.Face()

        # === Phase 2: Beide HalfSpaces erstellen ===
        n = np.array(feature.plane_normal, dtype=float)
        n = n / (np.linalg.norm(n) + 1e-12)

        # HalfSpace ABOVE (+normal Seite)
        ref_pt_above = np.array(feature.plane_origin) + n * 100.0
        half_space_above = BRepPrimAPI_MakeHalfSpace(split_face, gp_Pnt(*ref_pt_above))
        half_solid_above = half_space_above.Solid()

        # HalfSpace BELOW (-normal Seite)
        ref_pt_below = np.array(feature.plane_origin) - n * 100.0
        half_space_below = BRepPrimAPI_MakeHalfSpace(split_face, gp_Pnt(*ref_pt_below))
        half_solid_below = half_space_below.Solid()

        # === Phase 3: Beide Cuts durchführen ===
        cut_above = BRepAlgoAPI_Cut(shape, half_solid_below)  # Cut away below -> keep above
        cut_below = BRepAlgoAPI_Cut(shape, half_solid_above)  # Cut away above -> keep below

        cut_above.Build()
        cut_below.Build()

        if not (cut_above.IsDone() and cut_below.IsDone()):
            raise ValueError("Split-Operation fehlgeschlagen - einer der Cuts konnte nicht durchgeführt werden")

        # === Phase 4: Beide Solids erstellen ===
        result_above_shape = self._fix_shape_ocp(cut_above.Shape())
        result_below_shape = self._fix_shape_ocp(cut_below.Shape())

        from build123d import Solid
        body_above = Solid(result_above_shape)
        body_below = Solid(result_below_shape)

        # === Phase 5: Legacy vs Multi-Body Mode ===
        if feature.keep_side == "both":
            from modeling.document import SplitResult
            result = SplitResult(
                body_above=body_above,
                body_below=body_below,
                split_plane={
                    "origin": feature.plane_origin,
                    "normal": feature.plane_normal
                }
            )
            logger.debug(f"Split (both) erfolgreich -> 2 Bodies erstellt")
            return result
        elif feature.keep_side == "above":
            logger.debug(f"Split (above) erfolgreich")
            return body_above
        else:
            logger.debug(f"Split (below) erfolgreich")
            return body_below

    def _compute_thread(self, feature: 'ThreadFeature', current_solid):
        """
        Erzeugt ein echtes helikales Gewinde via Helix-Sweep + Boolean.

        Strategy:
        1. ISO 60° Gewindeprofil als Draht erstellen
        2. Helix-Pfad mit Pitch und Tiefe
        3. Sweep Profil entlang Helix -> Thread-Solid
        4. Boolean Cut (extern) oder Fuse (intern)
        """
        import numpy as np

        shape = current_solid.wrapped if hasattr(current_solid, 'wrapped') else current_solid

        # TNP v4.0: Face-Referenz auflösen (ShapeID -> Index -> Selector).
        target_faces = self._resolve_feature_faces(feature, current_solid)
        has_face_refs = bool(
            getattr(feature, "face_shape_id", None) is not None
            or getattr(feature, "face_index", None) is not None
            or getattr(feature, "face_selector", None)
        )
        if has_face_refs and not target_faces:
            raise ValueError("Thread: Ziel-Face konnte via TNP v4.0 nicht aufgelöst werden")

        pos = np.array(feature.position, dtype=float)
        direction = np.array(feature.direction, dtype=float)

        if target_faces:
            target_face = target_faces[0]
            try:
                from OCP.BRepAdaptor import BRepAdaptor_Surface
                from OCP.GeomAbs import GeomAbs_Cylinder

                topo_face = target_face.wrapped if hasattr(target_face, "wrapped") else target_face
                adaptor = BRepAdaptor_Surface(topo_face)
                if adaptor.GetType() != GeomAbs_Cylinder:
                    raise ValueError("ausgewähltes Face ist nicht zylindrisch")

                cyl = adaptor.Cylinder()
                axis = cyl.Axis()
                axis_loc = axis.Location()
                axis_dir = axis.Direction()

                resolved_axis = np.array([axis_dir.X(), axis_dir.Y(), axis_dir.Z()], dtype=float)
                resolved_axis = resolved_axis / (np.linalg.norm(resolved_axis) + 1e-12)
                if np.linalg.norm(direction) > 1e-9 and np.dot(resolved_axis, direction) < 0:
                    resolved_axis = -resolved_axis

                resolved_origin = np.array([axis_loc.X(), axis_loc.Y(), axis_loc.Z()], dtype=float)
                if np.linalg.norm(pos) > 1e-9:
                    pos = resolved_origin + np.dot(pos - resolved_origin, resolved_axis) * resolved_axis
                else:
                    pos = resolved_origin
                direction = resolved_axis
            except Exception as e:
                logger.warning(f"Thread: Face-Referenz nicht als Zylinder nutzbar ({e}); verwende Feature-Parameter")

        if np.linalg.norm(direction) < 1e-9:
            raise ValueError("Thread: Ungültige Gewinderichtung (Nullvektor)")
        direction = direction / (np.linalg.norm(direction) + 1e-12)

        r = max(feature.diameter / 2.0, 1e-6)
        pitch = feature.pitch
        depth = feature.depth
        if pitch <= 1e-9:
            raise ValueError("Thread: Pitch muss > 0 sein")
        if depth <= 0:
            raise ValueError("Thread: Depth muss > 0 sein")
        n_turns = depth / pitch

        # Thread groove depth (ISO 60° metric: H = 0.8660 * P, groove = 5/8 * H)
        H = 0.8660254 * pitch
        groove_depth = 0.625 * H

        return self._compute_thread_helix(
            shape, pos, direction, r, pitch, depth, n_turns,
            groove_depth, feature.thread_type, feature.tolerance_offset,
            feature=feature
        )

    def _compute_thread_helix(self, shape, pos, direction, r, pitch, depth, n_turns,
                               groove_depth, thread_type, tolerance_offset, feature=None):
        """Echtes Gewinde via Helix + Sweep mit korrekter Profil-Orientierung.

        Das Profil wird senkrecht zum Helix-Tangenten am Startpunkt platziert
        (nicht auf Plane.XZ!). Dadurch entsteht saubere Geometrie mit wenigen
        Faces/Edges -> schnelle Tessellation ohne Lag.
        """
        import numpy as np
        from build123d import (Helix, Solid, Polyline, BuildSketch, BuildLine,
                               Plane, make_face, sweep, Vector)
        from modeling.boolean_engine_v4 import BooleanEngineV4

        logger.debug(f"[THREAD] Helix sweep: r={r:.2f}, pitch={pitch}, depth={depth}, "
                     f"type={thread_type}, groove={groove_depth:.3f}")

        # Helix-Radius: Mitte der Gewinderille
        if thread_type == "external":
            helix_r = r - groove_depth / 2
        else:
            helix_r = r + groove_depth / 2

        # 1. Helix-Pfad via build123d
        helix = Helix(
            pitch=pitch,
            height=depth,
            radius=helix_r,
            center=tuple(pos),
            direction=tuple(direction)
        )

        # 2. ISO 60° Dreiecksprofil senkrecht zum Helix-Tangenten am Startpunkt
        half_w = pitch * 0.3

        # Profil-Plane senkrecht zur Helix-Tangente am Startpunkt
        start_pt = helix.position_at(0)
        tangent = helix.tangent_at(0)
        profile_plane = Plane(origin=start_pt, z_dir=tangent)

        with BuildSketch(profile_plane) as profile_sk:
            with BuildLine():
                Polyline(
                    (-groove_depth / 2, -half_w),
                    (groove_depth / 2, 0),
                    (-groove_depth / 2, half_w),
                    close=True
                )
            make_face()

        # 3. Sweep Profil entlang Helix
        thread_solid = sweep(profile_sk.sketch, path=helix)
        thread_ocp = thread_solid.wrapped if hasattr(thread_solid, 'wrapped') else thread_solid

        # 4. Boolean Operation via BooleanEngineV4 (TNP-safe)
        bool_op_type = "Cut" if thread_type == "external" else "Fuse"

        # Tool-Shapes registrieren (optional, aber gut für Debugging/Picking)
        if feature and self._document and hasattr(self._document, '_shape_naming_service'):
            try:
                self._register_base_feature_shapes(feature, thread_solid)
            except Exception:
                pass

        current_solid_b123d = Solid(shape)

        bool_result = BooleanEngineV4.execute_boolean_on_shapes(
            current_solid_b123d, thread_solid, bool_op_type
        )

        if bool_result.is_success:
            result = bool_result.value
            if feature:
                self._register_boolean_history(bool_result, feature, operation_name=f"Thread_{bool_op_type}")
            logger.debug(f"[THREAD] Helix sweep completed successfully (BooleanV4)")
            return result
        else:
            raise RuntimeError(f"Thread boolean via V4 failed: {bool_result.message}")

    def _compute_adaptive_edge_tolerance(self, solid) -> float:
        """
        Berechnet adaptive Toleranz für Edge-Matching basierend auf Solid-Größe.

        Max: 15mm (statt 50mm) - verhindert dass völlig falsche Edges gematcht werden.
        """
        try:
            bbox = solid.bounding_box()
            max_dim = max(
                bbox.max.X - bbox.min.X,
                bbox.max.Y - bbox.min.Y,
                bbox.max.Z - bbox.min.Z
            )
            # Adaptive Toleranz = 5% der größten Dimension, min 5mm, max 15mm
            tolerance = max_dim / 20.0
            return max(5.0, min(tolerance, 15.0))
        except Exception:
            return 10.0

    def _profile_data_to_face(self, profile_data: dict):
        """Konvertiert Profil-Daten zu Build123d Face."""
        if not profile_data:
            return None

        try:
            from build123d import Face, Wire, Vector, Plane, make_face
            import numpy as np

            profile_type = profile_data.get('type', 'polygon')
            
            if profile_type == 'polygon':
                coords = profile_data.get('coords', [])
                if len(coords) < 3:
                    return None
                
                plane_origin = profile_data.get('plane_origin', (0, 0, 0))
                plane_normal = profile_data.get('plane_normal', (0, 0, 1))
                
                plane = Plane(
                    origin=Vector(*plane_origin),
                    z_dir=Vector(*plane_normal)
                )
                
                pts_3d = [plane.from_local_coords((p[0], p[1])) for p in coords]
                wire = Wire.make_polygon(pts_3d)
                return make_face(wire)
                
            elif profile_type == 'circle':
                from build123d import Wire
                center = profile_data.get('center', (0, 0))
                radius = profile_data.get('radius', 10)
                plane_origin = profile_data.get('plane_origin', (0, 0, 0))
                plane_normal = profile_data.get('plane_normal', (0, 0, 1))
                
                plane = Plane(
                    origin=Vector(*plane_origin),
                    z_dir=Vector(*plane_normal)
                )
                center_3d = plane.from_local_coords(center)
                
                circle_plane = Plane(origin=center_3d, z_dir=plane.z_dir)
                wire = Wire.make_circle(radius, circle_plane)
                return make_face(wire)
                
        except Exception as e:
            logger.debug(f"Profile data to face conversion failed: {e}")
            return None

    # Canonicalization methods
    def _canonicalize_sweep_refs(self, feature: 'SweepFeature') -> dict:
        """
        Task 1: Deterministic Reference Canonicalization for Sweep.

        Returns kanonisch sortierte Referenzen für:
        - profile_face_index + profile_shape_id
        - path edge_indices + path_shape_id
        """
        result = {
            "profile_canonical": None,
            "path_canonical": None,
        }

        # Profile Referenzen kanonisieren
        profile_index = getattr(feature, 'profile_face_index', None)
        profile_shape_id = getattr(feature, 'profile_shape_id', None)
        if profile_index is not None or profile_shape_id is not None:
            result["profile_canonical"] = {
                "index": int(profile_index) if profile_index is not None else None,
                "shape_id_uuid": str(profile_shape_id.uuid) if hasattr(profile_shape_id, 'uuid') else None,
            }

        # Path Referenzen kanonisieren
        path_data = getattr(feature, 'path_data', {}) or {}
        edge_indices = list(path_data.get('edge_indices', []) or [])
        path_shape_id = getattr(feature, 'path_shape_id', None)

        # Edge-Indizes deterministisch sortieren (keine Duplikate, aufsteigend)
        canonical_indices = sorted({int(idx) for idx in edge_indices if isinstance(idx, (int, float)) and int(idx) >= 0})

        if canonical_indices or path_shape_id is not None:
            result["path_canonical"] = {
                "edge_indices": canonical_indices,
                "shape_id_uuid": str(path_shape_id.uuid) if hasattr(path_shape_id, 'uuid') else None,
            }

        return result

    def _canonicalize_loft_section_refs(self, feature: 'LoftFeature') -> dict:
        """
        Task 1: Deterministic Reference Canonicalization for Loft.

        Loft sections können durch face_indices oder section_shape_ids referenziert werden.
        """
        result = {
            "sections_canonical": [],
        }

        section_indices = list(getattr(feature, 'section_indices', []) or [])
        section_shape_ids = list(getattr(feature, 'section_shape_ids', []) or [])

        # Paare von (index, shape_id) erstellen
        section_pairs = []
        for i, idx in enumerate(section_indices):
            shape_id = section_shape_ids[i] if i < len(section_shape_ids) else None
            section_pairs.append((int(idx) if idx is not None else -1, shape_id))

        # Nach Index sortieren für deterministische Reihenfolge
        section_pairs.sort(key=lambda x: x[0])

        for idx, shape_id in section_pairs:
            result["sections_canonical"].append({
                "index": idx if idx >= 0 else None,
                "shape_id_uuid": str(shape_id.uuid) if hasattr(shape_id, 'uuid') else None,
            })

        return result

    def _canonicalize_edge_refs(self, feature) -> dict:
        """
        Task 1: Deterministic Reference Canonicalization for Edge Features.

        Kanonische Sortierung für Fillet/Chamfer Edge-Referenzen.
        """
        result = {
            "edge_indices_canonical": [],
            "shape_ids_canonical": [],
        }

        edge_indices = list(getattr(feature, 'edge_indices', []) or [])
        edge_shape_ids = list(getattr(feature, 'edge_shape_ids', []) or [])

        # Edge-Indizes deterministisch sortieren
        result["edge_indices_canonical"] = sorted({
            int(idx) for idx in edge_indices
            if isinstance(idx, (int, float)) and int(idx) >= 0
        })

        # Shape-IDs in stabiler Reihenfolge
        for shape_id in edge_shape_ids:
            if hasattr(shape_id, 'uuid'):
                result["shape_ids_canonical"].append(str(shape_id.uuid))

        result["shape_ids_canonical"].sort()

        return result

    def _canonicalize_face_refs(self, feature) -> dict:
        """
        Task 1: Deterministic Reference Canonicalization for Face Features.

        Kanonische Sortierung für Features mit Face-Referenzen.
        """
        result = {
            "face_indices_canonical": [],
            "shape_ids_canonical": [],
        }

        # Verschiedene Attribut-Namen für Face-Features
        face_indices_attrs = ['face_indices', 'opening_face_indices']
        face_shape_ids_attrs = ['face_shape_ids', 'opening_face_shape_ids']

        face_indices = []
        face_shape_ids = []

        for attr in face_indices_attrs:
            if hasattr(feature, attr):
                val = getattr(feature, attr)
                if val is not None:
                    face_indices = list(val) if not isinstance(val, (int, float)) else [val]
                    break

        for attr in face_shape_ids_attrs:
            if hasattr(feature, attr):
                val = getattr(feature, attr)
                if val is not None:
                    face_shape_ids = list(val) if not isinstance(val, (int, float)) else [val]
                    break

        # Face-Indizes deterministisch sortieren
        result["face_indices_canonical"] = sorted({
            int(idx) for idx in face_indices
            if isinstance(idx, (int, float)) and int(idx) >= 0
        })

        # Shape-IDs in stabiler Reihenfolge
        for shape_id in face_shape_ids:
            if hasattr(shape_id, 'uuid'):
                result["shape_ids_canonical"].append(str(shape_id.uuid))

        result["shape_ids_canonical"].sort()

        return result

    # Selector update methods
    def _update_edge_selectors_after_operation(self, solid, current_feature_index: int = -1):
        """
        Aktualisiert Edge-Selektoren in Fillet/Chamfer Features nach Geometrie-Operation.

        Nach Push/Pull oder Boolean ändern sich Edge-Positionen. Diese Methode
        findet die neuen Edges und aktualisiert die gespeicherten GeometricEdgeSelectors.

        Args:
            solid: Das neue Solid nach der Operation
            current_feature_index: Index des aktuell angewandten Features im Rebuild.
                -1 = alle aktualisieren.
        """
        if not solid or not hasattr(solid, 'edges'):
            return

        all_edges = list(solid.edges())
        if not all_edges:
            return

        from modeling.geometric_selector import GeometricEdgeSelector
        from modeling.features import FilletFeature, ChamferFeature

        adaptive_tolerance = None  # Lazy-computed bei Bedarf

        updated_count = 0
        for feat_idx, feature in enumerate(self.features):
            if current_feature_index >= 0 and feat_idx >= current_feature_index:
                continue
            if not isinstance(feature, (FilletFeature, ChamferFeature)):
                continue

            geometric_selectors = getattr(feature, 'geometric_selectors', [])
            if not geometric_selectors:
                continue

            edge_shape_ids = getattr(feature, 'edge_shape_ids', [])

            new_selectors = []
            for idx, selector in enumerate(geometric_selectors):
                try:
                    if isinstance(selector, dict):
                        geo_sel = GeometricEdgeSelector.from_dict(selector)
                    elif hasattr(selector, 'find_best_match'):
                        geo_sel = selector
                    else:
                        continue

                    best_edge = geo_sel.find_best_match(all_edges)

                    if best_edge is None:
                        if adaptive_tolerance is None:
                            adaptive_tolerance = self._compute_adaptive_edge_tolerance(solid)

                        if adaptive_tolerance > geo_sel.tolerance:
                            adaptive_sel = GeometricEdgeSelector(
                                center=geo_sel.center,
                                direction=geo_sel.direction,
                                length=geo_sel.length,
                                curve_type=geo_sel.curve_type,
                                tolerance=adaptive_tolerance
                            )
                            best_edge = adaptive_sel.find_best_match(all_edges)
                            if best_edge is not None:
                                logger.debug(f"Edge via adaptive Toleranz ({adaptive_tolerance:.1f}mm) gefunden")

                    if best_edge is not None:
                        new_selector = GeometricEdgeSelector.from_edge(best_edge)
                        new_selectors.append(new_selector)
                        updated_count += 1

                        if idx < len(edge_shape_ids):
                            self._update_shape_naming_record(edge_shape_ids[idx], best_edge)

                        try:
                            edge_indices = getattr(feature, "edge_indices", None)
                            if edge_indices is not None and idx < len(edge_indices):
                                for edge_idx, candidate in enumerate(all_edges):
                                    if self._is_same_edge(candidate, best_edge):
                                        edge_indices[idx] = edge_idx
                                        break
                        except Exception:
                            pass
                    else:
                        logger.warning(f"Edge nicht gefunden nach Operation für {feature.name}")
                        new_selectors.append(geo_sel)
                except Exception as e:
                    logger.debug(f"Edge-Selector Update fehlgeschlagen: {e}")
                    if isinstance(selector, dict):
                        new_selectors.append(GeometricEdgeSelector.from_dict(selector))
                    else:
                        new_selectors.append(selector)

            feature.geometric_selectors = new_selectors

        if updated_count > 0:
            logger.info(f"Aktualisiert {updated_count} Edge-Selektoren nach Geometrie-Operation")

    def _update_edge_selectors_for_feature(self, feature, solid):
        """
        Aktualisiert Edge-Selektoren eines SPEZIFISCHEN Features vor Ausführung.

        TNP-CRITICAL: Muss BEVOR Fillet/Chamfer ausgeführt werden.
        """
        if not solid or not hasattr(solid, 'edges'):
            return

        all_edges = list(solid.edges())
        if not all_edges:
            return

        from modeling.geometric_selector import GeometricEdgeSelector
        from modeling.tnp_system import ShapeType

        geometric_selectors = getattr(feature, 'geometric_selectors', [])
        if not geometric_selectors:
            return

        edge_shape_ids = getattr(feature, 'edge_shape_ids', [])
        adaptive_tolerance = None

        updated_count = 0
        new_selectors = []

        for idx, selector in enumerate(geometric_selectors):
            try:
                if isinstance(selector, dict):
                    geo_sel = GeometricEdgeSelector.from_dict(selector)
                elif hasattr(selector, 'find_best_match'):
                    geo_sel = selector
                else:
                    new_selectors.append(selector)
                    continue

                best_edge = geo_sel.find_best_match(all_edges)

                if best_edge is None:
                    if adaptive_tolerance is None:
                        adaptive_tolerance = self._compute_adaptive_edge_tolerance(solid)

                    if adaptive_tolerance > geo_sel.tolerance:
                        adaptive_sel = GeometricEdgeSelector(
                            center=geo_sel.center,
                            direction=geo_sel.direction,
                            length=geo_sel.length,
                            curve_type=geo_sel.curve_type,
                            tolerance=adaptive_tolerance
                        )
                        best_edge = adaptive_sel.find_best_match(all_edges)
                        if best_edge is not None:
                            logger.debug(f"Edge via adaptive Toleranz ({adaptive_tolerance:.1f}mm) gefunden")

                if best_edge is not None:
                    new_selector = GeometricEdgeSelector.from_edge(best_edge)
                    new_selectors.append(new_selector)
                    updated_count += 1

                    if idx < len(edge_shape_ids):
                        old_sid = edge_shape_ids[idx]
                        self._update_shape_naming_record(old_sid, best_edge)

                        if (self._document
                                and hasattr(self._document, '_shape_naming_service')):
                            svc = self._document._shape_naming_service
                            if hasattr(old_sid, 'uuid') and old_sid.uuid not in svc._shapes:
                                new_sid = svc.register_shape(
                                    ocp_shape=best_edge.wrapped if hasattr(best_edge, 'wrapped') else best_edge,
                                    shape_type=ShapeType.EDGE,
                                    feature_id=getattr(old_sid, 'feature_id', getattr(feature, 'id', '')),
                                    local_index=getattr(old_sid, 'local_index', idx),
                                )
                                edge_shape_ids[idx] = new_sid
                                if is_enabled("tnp_debug_logging"):
                                    logger.debug(
                                        f"ShapeID erneuert nach Rebuild: "
                                        f"{old_sid.uuid[:8]} -> {new_sid.uuid[:8]}"
                                    )

                    try:
                        edge_indices = getattr(feature, "edge_indices", None)
                        if edge_indices is not None and idx < len(edge_indices):
                            for edge_idx, candidate in enumerate(all_edges):
                                if self._is_same_edge(candidate, best_edge):
                                    edge_indices[idx] = edge_idx
                                    break
                    except Exception:
                        pass
                else:
                    logger.debug(f"Edge nicht gefunden für Feature {feature.name}, behalte alten Selector")
                    new_selectors.append(geo_sel)
            except Exception as e:
                logger.debug(f"Edge-Selector Update fehlgeschlagen: {e}")
                new_selectors.append(selector)

        feature.geometric_selectors = new_selectors

        if updated_count > 0:
            logger.debug(f"Feature '{feature.name}': {updated_count}/{len(geometric_selectors)} Edges aktualisiert")

    def _update_face_selectors_for_feature(self, feature, solid):
        """
        TNP v4.0: Aktualisiert Face-Referenzen eines Features vor Ausführung.

        Primary: ShapeIDs via ShapeNamingService
        Secondary: Face-Indizes via topology_indexing.face_from_index
        Fallback: GeometricFaceSelector (nur Legacy-Recovery)
        """
        if not solid:
            return

        from modeling.features.advanced import (
            ShellFeature, HoleFeature, DraftFeature, HollowFeature,
            ThreadFeature, SurfaceTextureFeature,
        )
        from modeling.features.extrude import ExtrudeFeature

        if not isinstance(
            feature,
            (
                ShellFeature,
                HoleFeature,
                DraftFeature,
                HollowFeature,
                ThreadFeature,
                SurfaceTextureFeature,
                ExtrudeFeature,
            ),
        ):
            return

        resolved_faces = self._resolve_feature_faces(feature, solid)
        if is_enabled("tnp_debug_logging"):
            logger.debug(f"{feature.name}: {len(resolved_faces)} Face-Referenzen aufgelöst (TNP v4.0)")

    # TNP registration methods
    def _update_shape_naming_record(self, shape_id, edge) -> None:
        """
        Aktualisiert einen ShapeNamingService Record mit neuer Edge-Geometrie.
        """
        if not self._document or not hasattr(self._document, '_shape_naming_service'):
            return

        try:
            service = self._document._shape_naming_service

            if not hasattr(shape_id, 'uuid') or shape_id.uuid not in service._shapes:
                return

            record = service._shapes[shape_id.uuid]

            # OCP Shape aktualisieren
            record.ocp_shape = edge.wrapped
            record.is_valid = True

            # Geometric Signature neu berechnen
            old_sig = record.geometric_signature.copy() if record.geometric_signature else {}
            record.geometric_signature = record.compute_signature()

            # Spatial Index aktualisieren
            shape_type = record.shape_id.shape_type
            if 'center' in record.geometric_signature:
                import numpy as np
                new_center = np.array(record.geometric_signature['center'])

                # Alten Eintrag entfernen
                service._spatial_index[shape_type] = [
                    (pos, sid) for pos, sid in service._spatial_index[shape_type]
                    if sid.uuid != shape_id.uuid
                ]
                # Neuen Eintrag hinzufügen
                service._spatial_index[shape_type].append((new_center, record.shape_id))

            if is_enabled("tnp_debug_logging"):
                logger.debug(f"TNP Record {shape_id.uuid[:8]} aktualisiert nach Parameter-Änderung")

        except Exception as e:
            logger.debug(f"Shape Naming Record Update fehlgeschlagen: {e}")

    def _register_extrude_shapes(self, feature: 'ExtrudeFeature', solid) -> None:
        """
        TNP v4.0: Registriert alle Edges und Faces eines Extrude-Solids im NamingService.
        """
        if not self._document or not hasattr(self._document, '_shape_naming_service'):
            return

        if not solid or not hasattr(solid, 'edges'):
            return

        try:
            from modeling.tnp_system import ShapeType, OperationRecord
            from OCP.TopAbs import TopAbs_FACE

            service = self._document._shape_naming_service
            edges = list(solid.edges())

            shape_ids = []
            for i, edge in enumerate(edges):
                center = edge.center()
                length = edge.length if hasattr(edge, 'length') else 0.0
                geometry_data = (center.X, center.Y, center.Z, length)

                shape_id = service.register_shape(
                    ocp_shape=edge.wrapped,
                    shape_type=ShapeType.EDGE,
                    feature_id=feature.id,
                    local_index=i,
                    geometry_data=geometry_data
                )
                shape_ids.append(shape_id)

            # Faces registrieren
            face_count = 0
            try:
                from OCP.TopTools import TopTools_IndexedMapOfShape
                from OCP.TopExp import TopExp
                from OCP.TopoDS import TopoDS

                solid_wrapped = solid.wrapped if hasattr(solid, 'wrapped') else solid
                face_map = TopTools_IndexedMapOfShape()
                TopExp.MapShapes_s(solid_wrapped, TopAbs_FACE, face_map)

                for fi in range(1, face_map.Extent() + 1):
                    face = TopoDS.Face_s(face_map.FindKey(fi))
                    service.register_shape(face, ShapeType.FACE, feature.id, fi - 1)
                    face_count += 1
            except Exception as e:
                if is_enabled("tnp_debug_logging"):
                    logger.debug(f"TNP v4.0: Extrude Face-Registrierung fehlgeschlagen: {e}")

            # Operation aufzeichnen
            service.record_operation(
                OperationRecord(
                    operation_id=feature.id,
                    operation_type="EXTRUDE",
                    feature_id=feature.id,
                    input_shape_ids=[],
                    output_shape_ids=shape_ids
                )
            )

            if is_enabled("tnp_debug_logging"):
                logger.info(f"TNP v4.0: {len(shape_ids)} Edges, {face_count} Faces für Extrude '{feature.name}' registriert")

        except Exception as e:
            if is_enabled("tnp_debug_logging"):
                logger.warning(f"TNP v4.0: Extrude-Registrierung fehlgeschlagen: {e}")

    def _register_base_feature_shapes(self, feature, solid) -> None:
        """
        TNP v4.0: Registriert alle Edges UND Faces eines neu erzeugten Solids fuer Basis-Features
        (Loft, Revolve, Sweep, Primitive, Import). Nur einmal pro Feature-ID.
        """
        if not self._document or not hasattr(self._document, '_shape_naming_service'):
            return
        if not solid or not hasattr(solid, 'edges'):
            return

        try:
            from modeling.tnp_system import ShapeType
            from OCP.TopAbs import TopAbs_FACE

            service = self._document._shape_naming_service
            if service.get_shapes_by_feature(feature.id):
                return

            # Edges registrieren
            edge_count = service.register_solid_edges(solid, feature.id)

            # Faces registrieren
            face_count = 0
            try:
                from OCP.TopTools import TopTools_IndexedMapOfShape
                from OCP.TopExp import TopExp
                from OCP.TopoDS import TopoDS

                solid_wrapped = solid.wrapped if hasattr(solid, 'wrapped') else solid
                face_map = TopTools_IndexedMapOfShape()
                TopExp.MapShapes_s(solid_wrapped, TopAbs_FACE, face_map)

                for i in range(1, face_map.Extent() + 1):
                    face = TopoDS.Face_s(face_map.FindKey(i))
                    service.register_shape(face, ShapeType.FACE, feature.id, i - 1)
                    face_count += 1
            except Exception as e:
                if is_enabled("tnp_debug_logging"):
                    logger.debug(f"TNP v4.0: Face-Registrierung fehlgeschlagen: {e}")

            if is_enabled("tnp_debug_logging"):
                logger.info(f"TNP v4.0: Base-Feature '{feature.id[:8]}': {edge_count} Edges, {face_count} Faces registriert")
        except Exception as e:
            if is_enabled("tnp_debug_logging"):
                logger.debug(f"TNP v4.0: Base-Feature Registrierung fehlgeschlagen: {e}")

    def _register_brepfeat_operation(self, feature, original_solid, result_solid,
                                     input_shape, result_shape) -> None:
        """
        TNP v4.0: Registriert eine BRepFeat-Operation mit Edge-Mappings.
        """
        if not self._document or not hasattr(self._document, '_shape_naming_service'):
            return

        try:
            from modeling.tnp_system import ShapeType, OperationRecord
            import numpy as np

            service = self._document._shape_naming_service

            # 1. Alle Original-Edges registrieren (falls noch nicht geschehen)
            input_shape_ids = []
            if original_solid and hasattr(original_solid, 'edges'):
                for i, edge in enumerate(original_solid.edges()):
                    center = edge.center()
                    length = edge.length if hasattr(edge, 'length') else 0.0
                    geometry_data = (center.X, center.Y, center.Z, length)

                    shape_id = service.register_shape(
                        ocp_shape=edge.wrapped,
                        shape_type=ShapeType.EDGE,
                        feature_id=feature.id,
                        local_index=i,
                        geometry_data=geometry_data
                    )
                    input_shape_ids.append(shape_id)

            # 2. Alle Result-Edges registrieren
            output_shape_ids = []
            if result_solid and hasattr(result_solid, 'edges'):
                for i, edge in enumerate(result_solid.edges()):
                    center = edge.center()
                    length = edge.length if hasattr(edge, 'length') else 0.0
                    geometry_data = (center.X, center.Y, center.Z, length)

                    shape_id = service.register_shape(
                        ocp_shape=edge.wrapped,
                        shape_type=ShapeType.EDGE,
                        feature_id=feature.id,
                        local_index=i + len(input_shape_ids),
                        geometry_data=geometry_data
                    )
                    output_shape_ids.append(shape_id)

            # 3. Manuelle Mappings erstellen (geometrisches Matching)
            manual_mappings = {}

            if original_solid and result_solid:
                orig_edges = list(original_solid.edges())
                result_edges = list(result_solid.edges())

                for i, orig_edge in enumerate(orig_edges):
                    orig_center = orig_edge.center()
                    orig_pos = np.array([orig_center.X, orig_center.Y, orig_center.Z])
                    orig_len = orig_edge.length if hasattr(orig_edge, 'length') else 0

                    best_match_idx = -1
                    best_score = float('inf')

                    for j, result_edge in enumerate(result_edges):
                        result_center = result_edge.center()
                        result_pos = np.array([result_center.X, result_center.Y, result_center.Z])
                        result_len = result_edge.length if hasattr(result_edge, 'length') else 0

                        dist = np.linalg.norm(orig_pos - result_pos)
                        len_diff = abs(orig_len - result_len) if orig_len > 0 else 0
                        score = dist + len_diff * 0.1

                        if score < best_score and score < 1.0:
                            best_score = score
                            best_match_idx = j

                    if best_match_idx >= 0 and i < len(input_shape_ids):
                        orig_id = input_shape_ids[i].uuid
                        mapped_id = output_shape_ids[best_match_idx].uuid
                        manual_mappings[orig_id] = [mapped_id]

            # 4. Operation aufzeichnen
            service.record_operation(
                OperationRecord(
                    operation_id=feature.id,
                    operation_type="BREPFEAT_PRISM",
                    feature_id=feature.id,
                    input_shape_ids=input_shape_ids,
                    output_shape_ids=output_shape_ids,
                    manual_mappings=manual_mappings
                )
            )

            if is_enabled("tnp_debug_logging"):
                logger.info(f"TNP v4.0: BRepFeat '{feature.name}' registriert - "
                           f"{len(input_shape_ids)} in, {len(output_shape_ids)} out, "
                           f"{len(manual_mappings)} mappings")

        except Exception as e:
            if is_enabled("tnp_debug_logging"):
                logger.warning(f"TNP v4.0: BRepFeat-Registrierung fehlgeschlagen: {e}")
                import traceback
                logger.debug(traceback.format_exc())

    def _get_or_create_shape_naming_service(self):
        """
        Liefert den aktiven ShapeNamingService oder erstellt einen temporären.
        """
        if self._document and hasattr(self._document, "_shape_naming_service"):
            service = self._document._shape_naming_service
            if service is not None:
                return service
        from modeling.tnp_system import ShapeNamingService
        return ShapeNamingService()

    # OCP helpers
    def _ocp_fillet(self, solid, edges, radius, feature_id: Optional[str] = None):
        """OCP helper for fillet operation."""
        from modeling.ocp_helpers import OCPFilletHelper
        
        naming_service = self._get_or_create_shape_naming_service()
        op_feature_id = self._ensure_ocp_feature_id(feature_id, "fillet")
        return OCPFilletHelper.fillet(solid, edges, radius, naming_service, op_feature_id)

    def _ocp_chamfer(self, solid, edges, distance, feature_id: Optional[str] = None):
        """OCP helper for chamfer operation."""
        from modeling.ocp_helpers import OCPChamferHelper
        
        naming_service = self._get_or_create_shape_naming_service()
        op_feature_id = self._ensure_ocp_feature_id(feature_id, "chamfer")
        return OCPChamferHelper.chamfer(solid, edges, distance, naming_service, op_feature_id)

    # Transform
    def _apply_transform_feature(self, solid, feature):
        """Applies transform feature to solid."""
        try:
            from OCP.gp import gp_Trsf, gp_Vec, gp_Quaternion
            from OCP.BRepBuilderAPI import BRepBuilderAPI_Transform
            from build123d import Solid

            trsf = gp_Trsf()
            
            # Translation
            if hasattr(feature, 'translation') and feature.translation:
                t = feature.translation
                trsf.SetTranslation(gp_Vec(t[0], t[1], t[2]))
            
            # Rotation
            if hasattr(feature, 'rotation') and feature.rotation:
                r = feature.rotation
                # Rotation in degrees around axis
                # This is simplified - full implementation would handle axis
                pass
            
            ocp_solid = solid.wrapped if hasattr(solid, 'wrapped') else solid
            transform = BRepBuilderAPI_Transform(ocp_solid, trsf)
            
            if transform.IsDone():
                return Solid(transform.Shape())
        except Exception as e:
            logger.error(f"Transform feature failed: {e}")
        return solid

    # Profile helpers
    def _detect_circle_from_points(self, points, tolerance=0.02):
        """Detects if points form a circle via algebraic least-squares fit."""
        if len(points) < 8:
            return None

        try:
            import numpy as np
            pts = np.array(points)
            if pts.shape[1] < 2:
                return None

            # Algebraic circle fit: (x-cx)^2 + (y-cy)^2 = r^2
            # Rewrite as: 2*cx*x + 2*cy*y + (r^2 - cx^2 - cy^2) = x^2 + y^2
            A = np.column_stack([pts[:, 0], pts[:, 1], np.ones(len(pts))])
            b = pts[:, 0]**2 + pts[:, 1]**2
            result, _, _, _ = np.linalg.lstsq(A, b, rcond=None)

            cx = result[0] / 2
            cy = result[1] / 2
            r_sq = result[2] + cx**2 + cy**2
            if r_sq <= 0:
                return None
            r = np.sqrt(r_sq)

            distances = np.sqrt((pts[:, 0] - cx)**2 + (pts[:, 1] - cy)**2)
            if np.max(np.abs(distances - r)) < tolerance * max(r, 1.0):
                return {'center': (float(cx), float(cy)), 'radius': float(r)}
        except Exception:
            pass
        return None

    def _create_faces_from_native_circles(self, sketch, plane, profile_selector=None):
        """Creates faces from native sketch circles."""
        return []

    def _create_faces_from_native_arcs(self, sketch, plane, profile_selector=None):
        """Creates faces from native sketch arcs."""
        return []

    def _detect_matching_native_spline(self, coords, sketch, tolerance=0.5):
        """Detects matching native spline for coordinates."""
        return None

    def _create_wire_from_native_spline(self, spline, plane):
        """Creates wire from native spline."""
        return None

    def _create_wire_from_mixed_geometry(self, geometry_list, outer_coords, plane):
        """Creates wire from mixed geometry types."""
        return None


__all__ = ['BodyComputeExtendedMixin']
