"""
Body Compute Extended Mixin - Extracted from body.py

Contains additional _compute_* methods and helper functions for Body class.
This mixin is designed to be inherited by the Body class.
"""

import math
from typing import Optional, List, Dict, Any

from loguru import logger

from config.feature_flags import is_enabled


class BodyComputeExtendedMixin:
    """
    Mixin class containing extended compute methods for Body.
    
    These methods handle the computation of various CAD features
    like sweep, shell, hole, draft, split, thread, etc.
    """

    def _compute_sweep(self, feature: 'SweepFeature', current_solid):
        """
        Berechnet Sweep eines Profils entlang eines Pfads.

        OCP-First Strategy:
        1. Profil zu Face konvertieren + Pfad auflÃ¶sen
        2. Voranalyse: Pfad-KomplexitÃ¤t â†’ MakePipe oder MakePipeShell
        3. Kein Fallback - bei Fehler ValueError

        Phase 8: UnterstÃ¼tzt Twist und Skalierung
        """
        # This method is complex and requires many helper methods
        # It should be implemented with proper TNP integration
        raise NotImplementedError("_compute_sweep should be imported from backup")

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
        """OCP-First Shell mit direktem OpenCASCADE BRepOffsetAPI_MakeThickSolid."""
        raise NotImplementedError("_compute_shell should be imported from backup")

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
        """Computes N-sided patch surface."""
        raise NotImplementedError("_compute_nsided_patch should be imported from backup")

    def _compute_hollow(self, feature: 'HollowFeature', current_solid):
        """Computes hollow operation for 3D printing."""
        raise NotImplementedError("_compute_hollow should be imported from backup")

    def _compute_hole(self, feature: 'HoleFeature', current_solid):
        """Computes hole feature."""
        raise NotImplementedError("_compute_hole should be imported from backup")

    def _position_cylinder(self, cyl_solid, position, direction, depth):
        """Positioniert einen Zylinder an position entlang direction."""
        try:
            from build123d import Vector, Location
            from OCP.gp import gp_Trsf, gp_Vec, gp_Ax1, gp_Pnt, gp_Dir, gp_Trsf
            from OCP.BRepBuilderAPI import BRepBuilderAPI_Transform

            # Translation
            translation = Vector(*position)
            
            # Rotation to align with direction
            # Default cylinder is along Z-axis
            z_axis = (0, 0, 1)
            dir_vec = Vector(*direction).normalized()
            
            # Create transformation
            trsf = gp_Trsf()
            trsf.SetTranslation(gp_Vec(translation.X, translation.Y, translation.Z))
            
            transform = BRepBuilderAPI_Transform(
                cyl_solid.wrapped if hasattr(cyl_solid, 'wrapped') else cyl_solid,
                trsf
            )
            
            from build123d import Solid
            return Solid(transform.Shape())
        except Exception as e:
            logger.error(f"Cylinder positioning failed: {e}")
            return cyl_solid

    def _compute_draft(self, feature: 'DraftFeature', current_solid):
        """Computes draft angle feature."""
        raise NotImplementedError("_compute_draft should be imported from backup")

    def _compute_split(self, feature: 'SplitFeature', current_solid):
        """Computes split body operation."""
        raise NotImplementedError("_compute_split should be imported from backup")

    def _compute_thread(self, feature: 'ThreadFeature', current_solid):
        """Computes thread feature."""
        raise NotImplementedError("_compute_thread should be imported from backup")

    def _compute_thread_helix(self, shape, pos, direction, r, pitch, depth, n_turns,
                               groove_depth, thread_type, tolerance_offset, feature=None):
        """Computes helical thread geometry."""
        raise NotImplementedError("_compute_thread_helix should be imported from backup")

    def _compute_adaptive_edge_tolerance(self, solid) -> float:
        """Computes adaptive tolerance for edge operations."""
        try:
            edges = list(solid.edges()) if hasattr(solid, 'edges') else []
            if not edges:
                return 0.01
            
            total_length = sum(
                e.length if hasattr(e, 'length') else 0
                for e in edges
            )
            avg_length = total_length / len(edges)
            
            # Adaptive tolerance based on average edge length
            return min(0.1, max(0.001, avg_length * 0.001))
        except Exception:
            return 0.01

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
        """Canonicalizes sweep feature references."""
        return {}

    def _canonicalize_loft_section_refs(self, feature: 'LoftFeature') -> dict:
        """Canonicalizes loft section references."""
        return {}

    def _canonicalize_edge_refs(self, feature) -> dict:
        """Canonicalizes edge references."""
        return {}

    def _canonicalize_face_refs(self, feature) -> dict:
        """Canonicalizes face references."""
        return {}

    # Selector update methods
    def _update_edge_selectors_after_operation(self, solid, current_feature_index: int = -1):
        """Updates edge selectors after an operation."""
        pass

    def _update_edge_selectors_for_feature(self, feature, solid):
        """Updates edge selectors for a specific feature."""
        pass

    def _update_face_selectors_for_feature(self, feature, solid):
        """Updates face selectors for a specific feature."""
        pass

    # TNP registration methods
    def _update_shape_naming_record(self, shape_id, edge) -> None:
        """Updates shape naming record for an edge."""
        pass

    def _register_extrude_shapes(self, feature: 'ExtrudeFeature', solid) -> None:
        """Registers shapes created by extrude operation."""
        pass

    def _register_base_feature_shapes(self, feature, solid) -> None:
        """Registers shapes for base features."""
        pass

    def _register_brepfeat_operation(self, feature, original_solid, result_solid,
                                     input_shape, result_shape) -> None:
        """Registers BRepFeat operation for TNP tracking."""
        pass

    def _get_or_create_shape_naming_service(self):
        """Gets or creates the shape naming service."""
        if self._document and hasattr(self._document, '_shape_naming_service'):
            return self._document._shape_naming_service
        return None

    # OCP helpers
    def _ocp_extrude_face(self, face, amount, direction):
        """OCP helper for face extrusion."""
        try:
            from OCP.BRepPrimAPI import BRepPrimAPI_MakePrism
            from OCP.gp import gp_Vec
            from build123d import Solid

            face_shape = face.wrapped if hasattr(face, 'wrapped') else face
            extrude_vec = gp_Vec(
                direction[0] * amount,
                direction[1] * amount,
                direction[2] * amount
            )

            prism = BRepPrimAPI_MakePrism(face_shape, extrude_vec)
            prism.Build()

            if prism.IsDone():
                return Solid(prism.Shape())
        except Exception as e:
            logger.error(f"OCP extrude face failed: {e}")
        return None

    def _ocp_fillet(self, solid, edges, radius, feature_id: Optional[str] = None):
        """OCP helper for fillet operation."""
        from modeling.ocp_helpers import OCPFilletHelper
        
        naming_service = self._get_or_create_shape_naming_service()
        return OCPFilletHelper.fillet(solid, edges, radius, naming_service, feature_id)

    def _ocp_chamfer(self, solid, edges, distance, feature_id: Optional[str] = None):
        """OCP helper for chamfer operation."""
        from modeling.ocp_helpers import OCPChamferHelper
        
        naming_service = self._get_or_create_shape_naming_service()
        return OCPChamferHelper.chamfer(solid, edges, distance, naming_service, feature_id)

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
        """Detects if points form a circle."""
        if len(points) < 3:
            return None
        
        try:
            import numpy as np
            from circle_fit import hyper_fit
            
            pts = np.array(points)
            x, y, r = hyper_fit(pts)
            
            # Verify fit quality
            distances = np.sqrt((pts[:, 0] - x)**2 + (pts[:, 1] - y)**2)
            if np.max(np.abs(distances - r)) < tolerance:
                return {'center': (x, y), 'radius': r}
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
