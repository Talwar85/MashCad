"""
LiteCAD - CAD Tessellator
Handles optimized conversion from Build123d Solids to PyVista PolyData with Caching.
FIX: Auto-Fallback für korrupte Edge-Daten
"""
import numpy as np
import pyvista as pv
from loguru import logger
from typing import Tuple, Optional

HAS_OCP_TESSELLATE = False
try:
    from ocp_tessellate.tessellator import tessellate as ocp_tessellate
    HAS_OCP_TESSELLATE = True
except ImportError:
    pass

class CADTessellator:
    """
    Singleton-ähnlicher Manager für Tessellierung.
    Nutzt LRU-Caching Strategie.
    """
    _mesh_cache = {}  # { "id_quality": (poly_mesh, poly_edges) }

    @staticmethod
    def clear_cache():
        CADTessellator._mesh_cache.clear()

    @staticmethod
    def tessellate(solid, quality=0.01, angular_tolerance=0.2) -> Tuple[Optional[pv.PolyData], Optional[pv.PolyData]]:
        """
        Konvertiert build123d Solid zu (FaceMesh, EdgeMesh).
        """
        if not solid:
            return None, None

        shape_id = id(solid.wrapped)
        cache_key = f"{shape_id}_{quality}_{angular_tolerance}"

        if cache_key in CADTessellator._mesh_cache:
            return CADTessellator._mesh_cache[cache_key]

        mesh = None
        edge_mesh = None

        try:
            if HAS_OCP_TESSELLATE:
                # OCP Tessellation aufrufen
                result = ocp_tessellate(
                    solid.wrapped,
                    cache_key,
                    deviation=quality,
                    quality=quality,
                    angular_tolerance=angular_tolerance,
                    compute_faces=True,
                    compute_edges=True,
                    debug=False
                )
                
                # --- A. FACES (Trianguliert) ---
                if "vertices" in result and "triangles" in result:
                    verts = np.array(result["vertices"], dtype=np.float32).reshape(-1, 3)
                    tris = np.array(result["triangles"], dtype=np.int32).reshape(-1, 3)
                    normals = result.get("normals")

                    # PyVista Cell Array: [3, v1, v2, v3, 3, v4...]
                    padding = np.full((tris.shape[0], 1), 3, dtype=np.int32)
                    faces_combined = np.hstack((padding, tris)).flatten()

                    mesh = pv.PolyData(verts, faces_combined)
                    
                    if normals is not None:
                        try:
                            normals = np.array(normals, dtype=np.float32).reshape(-1, 3)
                            if len(normals) == len(verts):
                                mesh.point_data["Normals"] = normals
                        except: pass

                # --- B. EDGES (Versuche OCP, Fallback auf PyVista) ---
                edges_coords = result.get("edges")
                
                # Versuch 1: OCP Daten nutzen
                if edges_coords is not None and len(edges_coords) > 0:
                    try:
                        edges_flat = np.array(edges_coords, dtype=np.float32)
                        if len(edges_flat) % 3 == 0:
                            points = edges_flat.reshape(-1, 3)
                            n_points = len(points)
                            n_lines = n_points // 2
                            indices = np.arange(n_points, dtype=np.int32).reshape(-1, 2)
                            padding_e = np.full((n_lines, 1), 2, dtype=np.int32)
                            lines_combined = np.hstack((padding_e, indices)).flatten()
                            edge_mesh = pv.PolyData(points, lines=lines_combined)
                        else:
                            logger.warning(f"OCP Edge data corrupted (len {len(edges_flat)}). using fallback.")
                    except Exception as e:
                         logger.warning(f"OCP Edge processing failed: {e}")

            # --- FALLBACK --- 
            # Wenn OCP nicht da ist ODER die Edges oben fehlgeschlagen sind (None)
            
            # Wenn wir gar kein Mesh haben (OCP totalausfall), nutzen wir native Methode
            if mesh is None:
                mesh_data = solid.tessellate(tolerance=quality)
                verts = np.array([(v.X, v.Y, v.Z) for v in mesh_data[0]], dtype=np.float32)
                tris = np.array(mesh_data[1], dtype=np.int32)
                padding = np.full((tris.shape[0], 1), 3, dtype=np.int32)
                faces_combined = np.hstack((padding, tris)).flatten()
                mesh = pv.PolyData(verts, faces_combined)

            # Wenn Edge Mesh immer noch fehlt (wegen Korruption oben), berechnen wir es aus dem Face Mesh
            if edge_mesh is None and mesh is not None:
                # Das ist der Retter: Extrahiert "scharfe Kanten" (>60 Grad) direkt aus der Geometrie
                edge_mesh = mesh.extract_feature_edges(feature_angle=60, boundary_edges=True, non_manifold_edges=True)

            CADTessellator._mesh_cache[cache_key] = (mesh, edge_mesh)
            return mesh, edge_mesh

        except Exception as e:
            logger.error(f"Tessellation critical error: {e}")
            return None, None