"""
Textured Tessellator - Tessellation mit Face-zu-Triangle Mapping.

Dieses Modul ermöglicht die Zuordnung von BREP-Faces zu Mesh-Triangles,
was für die Anwendung von Face-spezifischen Texturen beim Export notwendig ist.

KRITISCH: Das BREP wird NICHT modifiziert. Die Tessellation erzeugt nur
ein Mesh mit Tracking-Informationen.
"""

from dataclasses import dataclass, field
from typing import List, Tuple, Optional, Dict, Any
import numpy as np

from loguru import logger
from modeling.topology_indexing import iter_faces_with_indices

try:
    import pyvista as pv
    HAS_PYVISTA = True
except ImportError:
    HAS_PYVISTA = False

try:
    from OCP.BRep import BRep_Tool
    from OCP.TopLoc import TopLoc_Location
    from OCP.BRepMesh import BRepMesh_IncrementalMesh
    from OCP.BRepGProp import BRepGProp
    from OCP.GProp import GProp_GProps
    from OCP.BRepAdaptor import BRepAdaptor_Surface
    from OCP.GeomAbs import GeomAbs_Plane, GeomAbs_Cylinder, GeomAbs_Cone, GeomAbs_Sphere, GeomAbs_BSplineSurface
    HAS_OCP = True
except ImportError:
    HAS_OCP = False


@dataclass
class FaceTriangleMapping:
    """
    Mapping zwischen einer BREP-Face und den zugehörigen Mesh-Triangles.

    Wird beim Export verwendet, um Face-spezifische Texturen anzuwenden.
    """
    # Face-Identifikation (für GeometricFaceSelector Matching)
    face_index: int                              # Index der Face im Solid
    center: Tuple[float, float, float]           # Zentrum der Face
    normal: Tuple[float, float, float]           # Normale der Face
    area: float                                  # Fläche in mm²
    surface_type: str                            # "plane", "cylinder", "cone", "sphere", "bspline"

    # Triangle-Zuordnung
    triangle_indices: List[int] = field(default_factory=list)  # Indices in mesh.faces

    # UV-Bounds für Texturierung
    uv_min: Tuple[float, float] = (0.0, 0.0)
    uv_max: Tuple[float, float] = (1.0, 1.0)

    def to_selector_dict(self) -> dict:
        """Konvertiert zu GeometricFaceSelector-kompatiblem dict."""
        return {
            "center": self.center,
            "normal": self.normal,
            "area": self.area,
            "surface_type": self.surface_type,
        }

    def matches_selector(self, selector: dict, tolerance: float = 50.0) -> bool:
        """
        Prüft ob diese Mapping zu einem GeometricFaceSelector passt.

        WICHTIG: Normal-Match hat Priorität, da VTK und BREP unterschiedliche
        Zentren berechnen können.
        """
        if not selector:
            return False

        # Normal-Match ist am wichtigsten!
        sel_normal = selector.get("normal")
        if sel_normal:
            n1 = np.array(self.normal)
            n2 = np.array(sel_normal)
            n1 = n1 / (np.linalg.norm(n1) + 1e-10)
            n2 = n2 / (np.linalg.norm(n2) + 1e-10)
            normal_dot = abs(np.dot(n1, n2))

            # Wenn Normalen fast gleich sind (>0.95), ist das ein guter Match
            if normal_dot > 0.95:
                return True

        # Fallback: Score-basiertes Matching
        score = _compute_match_score(self, selector, tolerance)
        return score > 0.3  # Niedrigerer Threshold


class TexturedTessellator:
    """
    Tessellator mit Face-zu-Triangle Mapping.

    Ermöglicht die Anwendung von Face-spezifischen Texturen beim Export.

    KEIN Fallback - schlägt fehl wenn Tessellation fehlschlägt (Fail-Fast).
    """

    @staticmethod
    def tessellate_with_face_map(
        solid,
        quality: float = 0.5,
        angular_tolerance: float = 0.2
    ) -> Tuple[Any, List[FaceTriangleMapping]]:
        """
        Tesselliert Solid mit Face-zu-Triangle Mapping.

        Args:
            solid: Build123d Solid Objekt
            quality: Lineare Abweichung (Chord Height) in mm
            angular_tolerance: Winkel-Abweichung in Radians

        Returns:
            Tuple (mesh: pv.PolyData, mappings: List[FaceTriangleMapping])

        Raises:
            RuntimeError: Wenn Tessellation fehlschlägt (Fail-Fast)
        """
        if not HAS_OCP:
            raise RuntimeError("OCP nicht verfügbar - Tessellation nicht möglich")

        if not HAS_PYVISTA:
            raise RuntimeError("PyVista nicht verfügbar - Mesh-Erstellung nicht möglich")

        if solid is None:
            raise RuntimeError("Solid ist None - Tessellation nicht möglich")

        # OCP Shape extrahieren
        ocp_shape = solid.wrapped if hasattr(solid, 'wrapped') else solid

        # Mesh das gesamte Shape
        try:
            BRepMesh_IncrementalMesh(ocp_shape, quality, False, angular_tolerance, True)
        except Exception as e:
            raise RuntimeError(f"BRepMesh_IncrementalMesh fehlgeschlagen: {e}")

        # Sammle alle Vertices und Triangles
        all_vertices = []
        all_triangles = []
        face_mappings = []
        vertex_offset = 0

        # Iteriere über alle Faces (kanonische Reihenfolge)
        for face_idx, b3d_face in iter_faces_with_indices(solid):
            face = b3d_face.wrapped if hasattr(b3d_face, "wrapped") else b3d_face

            try:
                mapping = TexturedTessellator._process_face(
                    face,
                    face_idx,
                    all_vertices,
                    all_triangles,
                    vertex_offset
                )

                if mapping:
                    face_mappings.append(mapping)
                    vertex_offset = len(all_vertices)

            except Exception as e:
                logger.warning(f"Face {face_idx} Tessellation fehlgeschlagen: {e}")
                # Fail-Fast: Wir brechen nicht komplett ab, aber loggen den Fehler

        if not all_vertices:
            raise RuntimeError("Keine Vertices generiert - Solid ist möglicherweise leer")

        # PyVista Mesh erstellen
        verts = np.array(all_vertices, dtype=np.float64)
        tris = np.array(all_triangles, dtype=np.int64)

        if len(tris) == 0:
            raise RuntimeError("Keine Triangles generiert - Tessellation fehlgeschlagen")

        # PyVista Cell Array Format: [3, v1, v2, v3, 3, v4, v5, v6, ...]
        padding = np.full((tris.shape[0], 1), 3, dtype=np.int64)
        faces_combined = np.hstack((padding, tris)).flatten()

        mesh = pv.PolyData(verts, faces_combined)

        # Normalen berechnen
        mesh.compute_normals(inplace=True)

        logger.info(f"TexturedTessellator: {len(all_vertices)} Vertices, "
                   f"{len(all_triangles)} Triangles, {len(face_mappings)} Faces")

        return mesh, face_mappings

    @staticmethod
    def _process_face(
        face,
        face_idx: int,
        all_vertices: list,
        all_triangles: list,
        vertex_offset: int
    ) -> Optional[FaceTriangleMapping]:
        """
        Verarbeitet eine einzelne Face und extrahiert ihre Triangulation.

        Returns:
            FaceTriangleMapping oder None wenn die Face keine Triangulation hat.
        """
        # Triangulation holen
        location = TopLoc_Location()
        triangulation = BRep_Tool.Triangulation_s(face, location)

        if triangulation is None:
            return None

        n_nodes = triangulation.NbNodes()
        n_triangles = triangulation.NbTriangles()

        if n_nodes == 0 or n_triangles == 0:
            return None

        # Vertices extrahieren
        face_verts = []
        transformation = location.Transformation()

        for i in range(1, n_nodes + 1):
            node = triangulation.Node(i)
            transformed = node.Transformed(transformation)
            face_verts.append([transformed.X(), transformed.Y(), transformed.Z()])

        # Triangles extrahieren
        triangle_start = len(all_triangles)
        face_tris = []

        for i in range(1, n_triangles + 1):
            tri = triangulation.Triangle(i)
            n1, n2, n3 = tri.Get()
            # Indices anpassen für globales Array
            face_tris.append([
                n1 - 1 + vertex_offset,
                n2 - 1 + vertex_offset,
                n3 - 1 + vertex_offset
            ])

        # Zu globalen Arrays hinzufügen
        all_vertices.extend(face_verts)
        all_triangles.extend(face_tris)

        # Face-Eigenschaften berechnen
        center, normal, area = TexturedTessellator._compute_face_properties(face)
        surface_type = TexturedTessellator._get_surface_type(face)

        # UV-Bounds berechnen
        uv_min, uv_max = TexturedTessellator._compute_uv_bounds(triangulation)

        # Mapping erstellen
        return FaceTriangleMapping(
            face_index=face_idx,
            center=center,
            normal=normal,
            area=area,
            surface_type=surface_type,
            triangle_indices=list(range(triangle_start, len(all_triangles))),
            uv_min=uv_min,
            uv_max=uv_max
        )

    @staticmethod
    def _compute_face_properties(face) -> Tuple[Tuple[float, float, float], Tuple[float, float, float], float]:
        """Berechnet Zentrum, Normale und Fläche einer Face."""
        # Fläche und Schwerpunkt berechnen
        props = GProp_GProps()
        BRepGProp.SurfaceProperties_s(face, props)

        area = props.Mass()
        center_pnt = props.CentreOfMass()
        center = (center_pnt.X(), center_pnt.Y(), center_pnt.Z())

        # Normale am Schwerpunkt berechnen
        adaptor = BRepAdaptor_Surface(face)
        u_mid = (adaptor.FirstUParameter() + adaptor.LastUParameter()) / 2
        v_mid = (adaptor.FirstVParameter() + adaptor.LastVParameter()) / 2

        try:
            pnt = adaptor.Value(u_mid, v_mid)

            # D1 gibt Tangenten, Kreuzprodukt gibt Normale
            from OCP.gp import gp_Pnt, gp_Vec
            pnt_out = gp_Pnt()
            d1u = gp_Vec()
            d1v = gp_Vec()
            adaptor.D1(u_mid, v_mid, pnt_out, d1u, d1v)

            normal_vec = d1u.Crossed(d1v)
            if normal_vec.Magnitude() > 1e-10:
                normal_vec.Normalize()
                normal = (normal_vec.X(), normal_vec.Y(), normal_vec.Z())
            else:
                normal = (0, 0, 1)
        except Exception as e:
            logger.debug(f"[textured_tessellator.py] Fehler: {e}")
            normal = (0, 0, 1)

        return center, normal, area

    @staticmethod
    def _get_surface_type(face) -> str:
        """Ermittelt den Oberflächen-Typ der Face."""
        adaptor = BRepAdaptor_Surface(face)
        surface_type = adaptor.GetType()

        type_map = {
            GeomAbs_Plane: "plane",
            GeomAbs_Cylinder: "cylinder",
            GeomAbs_Cone: "cone",
            GeomAbs_Sphere: "sphere",
            GeomAbs_BSplineSurface: "bspline",
        }

        return type_map.get(surface_type, "other")

    @staticmethod
    def _compute_uv_bounds(triangulation) -> Tuple[Tuple[float, float], Tuple[float, float]]:
        """Berechnet UV-Bounds der Triangulation."""
        if not triangulation.HasUVNodes():
            return (0.0, 0.0), (1.0, 1.0)

        u_min, v_min = float('inf'), float('inf')
        u_max, v_max = float('-inf'), float('-inf')

        for i in range(1, triangulation.NbNodes() + 1):
            uv = triangulation.UVNode(i)
            u_min = min(u_min, uv.X())
            v_min = min(v_min, uv.Y())
            u_max = max(u_max, uv.X())
            v_max = max(v_max, uv.Y())

        return (u_min, v_min), (u_max, v_max)


def find_matching_mapping(
    selector: dict,
    face_mappings: List[FaceTriangleMapping],
    tolerance: float = 50.0  # Erhöht von 10.0 - VTK und BREP haben unterschiedliche Zentren
) -> Optional[FaceTriangleMapping]:
    """
    Findet die FaceTriangleMapping die am besten zu einem Selector passt.

    Args:
        selector: GeometricFaceSelector.to_dict() oder ähnliches dict
        face_mappings: Liste der verfügbaren Mappings
        tolerance: Toleranz für Matching (mm)

    Returns:
        Beste passende Mapping oder None
    """
    best_mapping = None
    best_score = 0.0

    sel_center = selector.get("center", (0, 0, 0))
    sel_normal = selector.get("normal", (0, 0, 1))

    logger.debug(f"Suche Face mit Center={sel_center}, Normal={sel_normal}")

    for mapping in face_mappings:
        # Berechne Score direkt (ohne Threshold-Check)
        score = _compute_match_score(mapping, selector, tolerance)

        # Debug-Log für alle Kandidaten
        center_dist = np.linalg.norm(np.array(mapping.center) - np.array(sel_center))
        normal_dot = abs(np.dot(np.array(mapping.normal), np.array(sel_normal))) if sel_normal else 0

        logger.debug(f"  Face {mapping.face_index}: score={score:.3f}, "
                    f"center_dist={center_dist:.1f}mm, normal_dot={normal_dot:.3f}, "
                    f"center={mapping.center}")

        if score > best_score:
            best_score = score
            best_mapping = mapping

    # WICHTIG: Niedrigerer Threshold (0.3 statt 0.6) - Normal-Match ist am wichtigsten
    if best_mapping and best_score >= 0.3:
        logger.info(f"Face gefunden: Index={best_mapping.face_index}, Score={best_score:.3f}")
        return best_mapping

    logger.warning(f"Keine passende Face gefunden (best_score={best_score:.3f})")
    return None


def _compute_match_score(mapping: FaceTriangleMapping, selector: dict, tolerance: float) -> float:
    """
    Berechnet detaillierten Match-Score.

    WICHTIG: Normal-Match hat höchste Priorität, da VTK und BREP unterschiedliche
    Zentren berechnen können, aber Normalen sind konsistent.
    """
    score = 0.0

    # Normal-Match (50%) - HÖCHSTE PRIORITÄT
    # Normalen sind am zuverlässigsten zwischen VTK und BREP
    sel_normal = selector.get("normal")
    if sel_normal:
        n1 = np.array(mapping.normal)
        n2 = np.array(sel_normal)
        # Normalisieren
        n1 = n1 / (np.linalg.norm(n1) + 1e-10)
        n2 = n2 / (np.linalg.norm(n2) + 1e-10)
        dot = abs(np.dot(n1, n2))
        score += 0.5 * dot

    # Center (30%) - Mit größerer Toleranz
    sel_center = selector.get("center", (0, 0, 0))
    center_dist = np.linalg.norm(np.array(mapping.center) - np.array(sel_center))
    if center_dist < tolerance:
        score += 0.3 * (1.0 - center_dist / tolerance)
    elif center_dist < tolerance * 2:
        # Teilpunkte auch bei größerer Distanz
        score += 0.15 * (1.0 - center_dist / (tolerance * 2))

    # Area (15%)
    sel_area = selector.get("area", 0)
    if sel_area > 0 and mapping.area > 0:
        area_ratio = min(mapping.area, sel_area) / max(mapping.area, sel_area)
        score += 0.15 * area_ratio

    # Type (5%)
    if selector.get("surface_type", "") == mapping.surface_type:
        score += 0.05

    return score
