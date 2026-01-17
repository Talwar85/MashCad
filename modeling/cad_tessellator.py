"""
MashCad - CAD Tessellator
Handles optimized conversion from Build123d Solids to PyVista PolyData with Caching.
FIX: Auto-Fallback für korrupte Edge-Daten
FIX: Echte B-Rep Kanten statt Tessellations-Kanten
FIX: Transform invalidiert jetzt auch ocp_tessellate Cache
VERSION: 4 - Cache wird bei Version-Änderung geleert
"""
import numpy as np
import pyvista as pv
from loguru import logger
from typing import Tuple, Optional
from contextlib import contextmanager
import time

# VERSION für Cache-Invalidierung - ERHÖHEN bei Änderungen!
_TESSELLATOR_VERSION = 4

# GLOBAL COUNTER für Cache-Invalidierung bei Transforms
# Wird bei jedem clear_cache() erhöht um ocp_tessellate Cache zu invalidieren
_CACHE_INVALIDATION_COUNTER = 0

HAS_OCP_TESSELLATE = False
try:
    from ocp_tessellate.tessellator import tessellate as ocp_tessellate
    HAS_OCP_TESSELLATE = True
except ImportError:
    pass

# OCP für echte Edge-Extraktion
HAS_OCP = False
try:
    from OCP.TopExp import TopExp_Explorer
    from OCP.TopAbs import TopAbs_EDGE
    from OCP.BRepAdaptor import BRepAdaptor_Curve
    from OCP.GCPnts import GCPnts_TangentialDeflection
    HAS_OCP = True
except ImportError:
    pass


class CADTessellator:
    """
    Singleton-ähnlicher Manager für Tessellierung.
    Nutzt LRU-Caching Strategie mit Version-Tag.
    """
    _mesh_cache = {}  # { "id_quality_version": (poly_mesh, poly_edges) }
    _cache_version = _TESSELLATOR_VERSION
    _cache_cleared = False  # Flag um mehrfaches Clearen zu vermeiden

    @staticmethod
    def clear_cache():
        global _CACHE_INVALIDATION_COUNTER
        _CACHE_INVALIDATION_COUNTER += 1
        CADTessellator._mesh_cache.clear()
        CADTessellator._cache_cleared = True
        logger.info(f"CADTessellator Cache geleert (Version {_TESSELLATOR_VERSION}, Counter {_CACHE_INVALIDATION_COUNTER})")

    @staticmethod
    @contextmanager
    def invalidate_cache():
        """
        Context Manager für automatische Cache-Invalidierung.

        Usage:
            with CADTessellator.invalidate_cache():
                # Transform operations
                body._build123d_solid = body._build123d_solid.move(...)
        """
        CADTessellator.clear_cache()
        try:
            yield
        finally:
            # Optional: Post-processing hier möglich
            pass

    @staticmethod
    def extract_brep_edges(solid, deflection=0.1) -> Optional[pv.PolyData]:
        """
        Extrahiert die ECHTEN B-Rep Kanten aus einem Solid.
        Diese sind die CAD-Kanten (wie in Fusion), nicht die Tessellations-Kanten.
        """
        if not HAS_OCP or solid is None:
            return None
        
        try:
            from OCP.TopoDS import TopoDS
            
            all_points = []
            all_lines = []
            point_offset = 0
            
            explorer = TopExp_Explorer(solid.wrapped, TopAbs_EDGE)
            
            while explorer.More():
                edge_shape = explorer.Current()
                
                try:
                    # Explizit zu TopoDS_Edge casten
                    edge = TopoDS.Edge_s(edge_shape)
                    
                    # Kante in Kurve konvertieren
                    adaptor = BRepAdaptor_Curve(edge)
                    first = adaptor.FirstParameter()
                    last = adaptor.LastParameter()
                    
                    # Punkte entlang der Kante samplen
                    discretizer = GCPnts_TangentialDeflection(adaptor, deflection, 0.1)
                    
                    n_points = discretizer.NbPoints()
                    if n_points < 2:
                        explorer.Next()
                        continue
                    
                    edge_points = []
                    for i in range(1, n_points + 1):
                        pnt = discretizer.Value(i)
                        edge_points.append([pnt.X(), pnt.Y(), pnt.Z()])
                    
                    # Punkte hinzufügen
                    all_points.extend(edge_points)
                    
                    # Linien-Segmente für diese Kante
                    for i in range(len(edge_points) - 1):
                        all_lines.append([2, point_offset + i, point_offset + i + 1])
                    
                    point_offset += len(edge_points)
                    
                except Exception as e:
                    logger.debug(f"Edge extraction error: {e}")
                
                explorer.Next()
            
            if not all_points:
                return None
            
            points = np.array(all_points, dtype=np.float32)
            lines = np.array(all_lines, dtype=np.int32).flatten()
            
            logger.debug(f"B-Rep Edges extrahiert: {len(all_lines)} Linien")
            return pv.PolyData(points, lines=lines)
            
        except Exception as e:
            logger.debug(f"B-Rep Edge extraction failed: {e}")
            return None

    @staticmethod
    def tessellate(solid, quality=0.01, angular_tolerance=0.2) -> Tuple[Optional[pv.PolyData], Optional[pv.PolyData]]:
        """
        Konvertiert build123d Solid zu (FaceMesh, EdgeMesh).
        EdgeMesh enthält jetzt echte B-Rep Kanten!
        """
        if not solid:
            return None, None

        shape_id = id(solid.wrapped)
        # Cache-Key mit Version UND Counter für Auto-Invalidierung
        # Der Counter stellt sicher dass ocp_tessellate auch neu berechnet
        cache_key = f"{shape_id}_{quality}_{angular_tolerance}_v{_TESSELLATOR_VERSION}_c{_CACHE_INVALIDATION_COUNTER}"

        if cache_key in CADTessellator._mesh_cache:
            logger.debug(f"Tessellator: Cache HIT für {cache_key[:20]}...")
            return CADTessellator._mesh_cache[cache_key]
        
        logger.debug(f"Tessellator: Cache MISS - generiere neu für {cache_key[:20]}...")

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

            # --- FALLBACK für Mesh --- 
            if mesh is None:
                mesh_data = solid.tessellate(tolerance=quality)
                verts = np.array([(v.X, v.Y, v.Z) for v in mesh_data[0]], dtype=np.float32)
                tris = np.array(mesh_data[1], dtype=np.int32)
                padding = np.full((tris.shape[0], 1), 3, dtype=np.int32)
                faces_combined = np.hstack((padding, tris)).flatten()
                mesh = pv.PolyData(verts, faces_combined)

            # --- B. EDGES - Echte B-Rep Kanten! ---
            # Priorität 1: Echte B-Rep Kanten extrahieren
            edge_mesh = CADTessellator.extract_brep_edges(solid, deflection=quality * 10)
            
            # Fallback: Feature Edges (nur wenn B-Rep Extraktion fehlschlägt)
            if edge_mesh is None and mesh is not None:
                edge_mesh = mesh.extract_feature_edges(feature_angle=30, boundary_edges=True)
                logger.debug(f"Fallback zu Feature-Edges: {edge_mesh.n_lines} Linien")
            elif edge_mesh is not None:
                # Vergleich für Debug
                if mesh is not None:
                    old_count = mesh.extract_feature_edges(feature_angle=30).n_lines
                    logger.debug(f"B-Rep Edges: {edge_mesh.n_lines} Linien (statt {old_count} Tessellations-Kanten)")

            CADTessellator._mesh_cache[cache_key] = (mesh, edge_mesh)
            return mesh, edge_mesh

        except Exception as e:
            logger.error(f"Tessellation critical error: {e}")
            return None, None
    
    @staticmethod
    def count_brep_faces(solid) -> int:
        """Zählt die echten B-Rep Faces (nicht Tessellations-Dreiecke)"""
        if not HAS_OCP or solid is None:
            return 0
        try:
            from OCP.TopAbs import TopAbs_FACE
            explorer = TopExp_Explorer(solid.wrapped, TopAbs_FACE)
            count = 0
            while explorer.More():
                count += 1
                explorer.Next()
            return count
        except:
            return 0