"""
MashCad - Smart Mesh to BREP Converter V6
==========================================
Hybrid-Ansatz: Kombiniert optisch schöne PyVista-Verarbeitung mit 
sauberer B-Rep Erzeugung durch Feature-Erkennung.

Strategie:
1. Mesh vorbereiten (Clean, Normals, Decimate)
2. Planare Regionen erkennen (Dreiecke mit ähnlicher Normale)
3. Regionen zu echten B-Rep Flächen konvertieren
4. Flächen zusammennähen

Das Ziel: Aus einem STL mit 10.000 Dreiecken ein Solid mit 6-20 echten
planaren Flächen machen (wie ein CAD-Modell).
"""

import numpy as np
from collections import defaultdict
from loguru import logger
from typing import List, Tuple, Dict, Optional
from dataclasses import dataclass

try:
    import pyvista as pv
    HAS_PYVISTA = True
except ImportError:
    HAS_PYVISTA = False

try:
    from scipy.spatial import ConvexHull
    from scipy.cluster.hierarchy import fcluster, linkage
    HAS_SCIPY = True
except ImportError:
    HAS_SCIPY = False

try:
    from OCP.gp import gp_Pnt, gp_Vec, gp_Pln, gp_Dir, gp_Ax3
    from OCP.BRepBuilderAPI import (
        BRepBuilderAPI_MakePolygon,
        BRepBuilderAPI_MakeFace,
        BRepBuilderAPI_Sewing,
        BRepBuilderAPI_MakeSolid
    )
    from OCP.ShapeUpgrade import ShapeUpgrade_UnifySameDomain
    from OCP.TopoDS import TopoDS
    from OCP.TopAbs import TopAbs_SHELL
    from build123d import Solid, Shell, Shape
    HAS_OCP = True
except ImportError:
    HAS_OCP = False
    logger.warning("OCP/build123d nicht verfügbar")


@dataclass
class PlanarRegion:
    """Eine erkannte planare Region im Mesh"""
    cell_ids: List[int]          # Indizes der Dreiecke
    normal: np.ndarray           # Durchschnittliche Normale
    centroid: np.ndarray         # Zentrum der Region
    boundary_points: np.ndarray  # Randpunkte (geordnet)
    area: float                  # Fläche


class SmartMeshConverter:
    """
    Intelligenter Mesh-zu-BREP Converter.
    Erkennt planare Regionen und erzeugt saubere B-Rep Flächen.
    """
    
    def __init__(self, 
                 angle_tolerance: float = 5.0,      # Grad - Normale muss ähnlich sein
                 min_region_faces: int = 3,         # Minimum Dreiecke pro Region
                 decimate_target: int = 5000,       # Ziel-Anzahl Dreiecke
                 sewing_tolerance: float = 0.1):    # mm
        """
        Args:
            angle_tolerance: Maximale Winkelabweichung für gleiche Ebene (Grad)
            min_region_faces: Minimum Faces um als Region zu gelten
            decimate_target: Ziel für Mesh-Reduktion (0 = keine Reduktion)
            sewing_tolerance: Toleranz für das Zusammennähen
        """
        self.angle_tol = np.radians(angle_tolerance)
        self.min_faces = min_region_faces
        self.decimate_target = decimate_target
        self.sewing_tol = sewing_tolerance
        
    def convert(self, mesh: 'pv.PolyData', method: str = "smart") -> Optional['Shape']:
        """
        Konvertiert ein PyVista Mesh zu einem Build123d Solid.
        
        Args:
            mesh: PyVista PolyData Objekt
            method: 'smart' (Feature Detection), 'direct' (alle Dreiecke), 
                    'simplified' (UnifySameDomain)
        """
        if not HAS_PYVISTA or not HAS_OCP:
            logger.error("Abhängigkeiten fehlen (PyVista, OCP)")
            return None
            
        logger.info(f"=== SmartMeshConverter V6 ===")
        logger.info(f"Input: {mesh.n_cells} Faces, Methode: {method}")
        
        # 1. Mesh vorbereiten
        mesh = self._prepare_mesh(mesh)
        if mesh is None:
            return None
            
        # 2. Je nach Methode konvertieren
        if method == "smart":
            return self._convert_smart(mesh)
        elif method == "direct":
            return self._convert_direct(mesh)
        elif method == "simplified":
            return self._convert_simplified(mesh)
        else:
            logger.warning(f"Unbekannte Methode: {method}, nutze 'smart'")
            return self._convert_smart(mesh)
    
    def _prepare_mesh(self, mesh: 'pv.PolyData') -> Optional['pv.PolyData']:
        """Bereitet das Mesh vor: Triangulate, Clean, Normals, Decimate"""
        try:
            # Triangulieren falls nötig
            if not mesh.is_all_triangles:
                mesh = mesh.triangulate()
            
            # Duplikate entfernen
            mesh = mesh.clean(tolerance=1e-6)
            
            # Normalen berechnen
            if 'Normals' not in mesh.cell_data:
                mesh.compute_normals(cell_normals=True, point_normals=False, inplace=True)
            
            # Dezimierung falls zu viele Faces
            if self.decimate_target > 0 and mesh.n_cells > self.decimate_target:
                ratio = self.decimate_target / mesh.n_cells
                mesh = mesh.decimate(ratio, progress_bar=False)
                logger.info(f"Dezimiert auf {mesh.n_cells} Faces")
            
            logger.info(f"Mesh vorbereitet: {mesh.n_cells} Faces, {mesh.n_points} Punkte")
            return mesh
            
        except Exception as e:
            logger.error(f"Mesh-Vorbereitung fehlgeschlagen: {e}")
            return None
    
    def _convert_smart(self, mesh: 'pv.PolyData') -> Optional['Shape']:
        """
        Intelligente Konvertierung mit Feature-Erkennung.
        Gruppiert Dreiecke nach Normale und erzeugt echte planare Flächen.
        """
        try:
            # 1. Planare Regionen erkennen
            regions = self._detect_planar_regions(mesh)
            logger.info(f"Erkannt: {len(regions)} planare Regionen")
            
            if not regions:
                logger.warning("Keine Regionen erkannt, fallback zu direct")
                return self._convert_direct(mesh)
            
            # 2. Regionen zu B-Rep Flächen konvertieren
            sewer = BRepBuilderAPI_Sewing(self.sewing_tol)
            face_count = 0
            
            for i, region in enumerate(regions):
                ocp_face = self._region_to_brep_face(region, mesh)
                if ocp_face:
                    sewer.Add(ocp_face)
                    face_count += 1
            
            logger.info(f"Erzeuge BREP aus {face_count} Flächen...")
            
            # 3. Zusammennähen
            sewer.Perform()
            sewed_shape = sewer.SewedShape()
            
            if sewed_shape.IsNull():
                logger.error("Sewing fehlgeschlagen")
                return self._convert_direct(mesh)
            
            # 4. Zu Solid machen
            return self._shape_to_solid(sewed_shape)
            
        except Exception as e:
            logger.error(f"Smart Conversion fehlgeschlagen: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    def _detect_planar_regions(self, mesh: 'pv.PolyData') -> List[PlanarRegion]:
        """
        Erkennt planare Regionen durch Normalen-Clustering.
        Verwendet hierarchisches Clustering um ähnliche Normalen zu gruppieren.
        """
        normals = mesh.cell_data['Normals']
        n_cells = mesh.n_cells
        
        if not HAS_SCIPY:
            # Fallback: Einfaches Grid-basiertes Clustering
            return self._detect_planar_regions_simple(mesh, normals)
        
        # Normalisieren
        norms = np.linalg.norm(normals, axis=1, keepdims=True)
        norms[norms < 1e-6] = 1.0
        normals_normalized = normals / norms
        
        # Hierarchisches Clustering basierend auf Normalen-Ähnlichkeit
        # Distanz = 1 - |dot(n1, n2)| (0 = gleich, 1 = senkrecht)
        # Für große Meshes: Sampling
        
        if n_cells > 10000:
            # Sample für Clustering
            sample_idx = np.random.choice(n_cells, 5000, replace=False)
            sample_normals = normals_normalized[sample_idx]
        else:
            sample_idx = np.arange(n_cells)
            sample_normals = normals_normalized
        
        # Linkage Matrix berechnen
        # Wir nutzen 'average' Linkage und 'cosine' Distanz
        try:
            Z = linkage(sample_normals, method='average', metric='cosine')
            
            # Cluster mit Winkel-Toleranz
            # cosine_dist = 1 - cos(angle), bei 5° ist das ca. 0.004
            threshold = 1 - np.cos(self.angle_tol)
            labels = fcluster(Z, threshold, criterion='distance')
        except Exception as e:
            logger.warning(f"Clustering fehlgeschlagen: {e}")
            return self._detect_planar_regions_simple(mesh, normals)
        
        # Labels auf alle Zellen übertragen (bei Sampling)
        if len(sample_idx) < n_cells:
            all_labels = np.zeros(n_cells, dtype=int)
            all_labels[sample_idx] = labels
            
            # Restliche Zellen dem nächsten Cluster zuordnen
            cluster_normals = {}
            for label in np.unique(labels):
                mask = labels == label
                cluster_normals[label] = np.mean(sample_normals[mask], axis=0)
            
            for i in range(n_cells):
                if i not in sample_idx:
                    n = normals_normalized[i]
                    best_label = 1
                    best_dot = -1
                    for label, cn in cluster_normals.items():
                        dot = abs(np.dot(n, cn))
                        if dot > best_dot:
                            best_dot = dot
                            best_label = label
                    all_labels[i] = best_label
            labels = all_labels
        else:
            # Labels für alle Zellen erweitern
            full_labels = np.zeros(n_cells, dtype=int)
            full_labels[sample_idx] = labels
            labels = full_labels
        
        # Regionen aus Clustern erstellen
        regions = []
        for label in np.unique(labels):
            if label == 0:
                continue  # Unzugeordnete überspringen
                
            cell_ids = np.where(labels == label)[0].tolist()
            
            if len(cell_ids) < self.min_faces:
                continue
            
            # Durchschnittliche Normale
            region_normals = normals_normalized[cell_ids]
            avg_normal = np.mean(region_normals, axis=0)
            avg_normal /= np.linalg.norm(avg_normal)
            
            # Centroid und Boundary
            region_mesh = mesh.extract_cells(cell_ids)
            centroid = np.mean(region_mesh.points, axis=0)
            
            # Boundary-Punkte extrahieren
            boundary_pts = self._extract_boundary_points(region_mesh, avg_normal)
            
            if len(boundary_pts) >= 3:
                # Fläche berechnen
                area = region_mesh.area
                
                regions.append(PlanarRegion(
                    cell_ids=cell_ids,
                    normal=avg_normal,
                    centroid=centroid,
                    boundary_points=boundary_pts,
                    area=area
                ))
        
        # Nach Fläche sortieren (große zuerst)
        regions.sort(key=lambda r: r.area, reverse=True)
        
        return regions
    
    def _detect_planar_regions_simple(self, mesh: 'pv.PolyData', normals: np.ndarray) -> List[PlanarRegion]:
        """Einfache Regionenerkennung ohne SciPy (Grid-basiert)"""
        # Normalen auf Einheitskugel diskretisieren
        # Wir nutzen ein grobes Grid
        
        grid_size = 20  # 20x20 Grid auf der Hemisphäre
        
        # Normalen zu Grid-Index
        def normal_to_key(n):
            # Konvertiere zu Kugelkoordinaten
            n = n / (np.linalg.norm(n) + 1e-9)
            theta = np.arccos(np.clip(n[2], -1, 1))
            phi = np.arctan2(n[1], n[0])
            
            # Quantisiere
            ti = int(theta / np.pi * grid_size)
            pi = int((phi + np.pi) / (2 * np.pi) * grid_size)
            return (ti, pi)
        
        # Gruppieren
        groups = defaultdict(list)
        for i, n in enumerate(normals):
            key = normal_to_key(n)
            groups[key].append(i)
        
        # Zu Regionen konvertieren
        regions = []
        for key, cell_ids in groups.items():
            if len(cell_ids) < self.min_faces:
                continue
            
            region_normals = normals[cell_ids]
            avg_normal = np.mean(region_normals, axis=0)
            avg_normal /= np.linalg.norm(avg_normal) + 1e-9
            
            region_mesh = mesh.extract_cells(cell_ids)
            centroid = np.mean(region_mesh.points, axis=0)
            
            boundary_pts = self._extract_boundary_points(region_mesh, avg_normal)
            
            if len(boundary_pts) >= 3:
                regions.append(PlanarRegion(
                    cell_ids=cell_ids,
                    normal=avg_normal,
                    centroid=centroid,
                    boundary_points=boundary_pts,
                    area=region_mesh.area
                ))
        
        regions.sort(key=lambda r: r.area, reverse=True)
        return regions
    
    def _extract_boundary_points(self, region_mesh: 'pv.PolyData', normal: np.ndarray) -> np.ndarray:
        """
        Extrahiert die Randpunkte einer Region und ordnet sie.
        """
        try:
            # Boundary Edges extrahieren
            edges = region_mesh.extract_feature_edges(
                boundary_edges=True,
                feature_edges=False,
                manifold_edges=False,
                non_manifold_edges=False
            )
            
            if edges.n_points < 3:
                # Fallback: Alle Punkte projizieren und ConvexHull
                return self._boundary_via_convex_hull(region_mesh, normal)
            
            # Punkte ordnen (entlang der Boundary)
            points = edges.points
            
            # Sortieren mit nearest-neighbor
            ordered = [0]
            remaining = set(range(1, len(points)))
            
            while remaining:
                current = ordered[-1]
                nearest = min(remaining, key=lambda i: np.linalg.norm(points[i] - points[current]))
                ordered.append(nearest)
                remaining.remove(nearest)
            
            return points[ordered]
            
        except Exception:
            return self._boundary_via_convex_hull(region_mesh, normal)
    
    def _boundary_via_convex_hull(self, region_mesh: 'pv.PolyData', normal: np.ndarray) -> np.ndarray:
        """Fallback: 2D Convex Hull in der Ebene"""
        try:
            points = region_mesh.points
            
            # Lokales Koordinatensystem
            n = normal / np.linalg.norm(normal)
            
            if abs(n[2]) < 0.9:
                u = np.cross(n, [0, 0, 1])
            else:
                u = np.cross(n, [1, 0, 0])
            u /= np.linalg.norm(u)
            v = np.cross(n, u)
            
            # Projizieren
            centroid = np.mean(points, axis=0)
            local_pts = points - centroid
            pts_2d = np.column_stack([
                np.dot(local_pts, u),
                np.dot(local_pts, v)
            ])
            
            if HAS_SCIPY and len(pts_2d) >= 3:
                hull = ConvexHull(pts_2d)
                hull_pts_3d = points[hull.vertices]
                return hull_pts_3d
            else:
                # Ohne Hull: Einfach alle Punkte
                return points
                
        except Exception:
            return region_mesh.points
    
    def _region_to_brep_face(self, region: PlanarRegion, mesh: 'pv.PolyData') -> Optional['TopoDS_Face']:
        """
        Konvertiert eine planare Region zu einer OCP Face.
        Nutzt die Boundary-Punkte um ein Polygon/Wire zu erstellen.
        """
        try:
            pts = region.boundary_points
            if len(pts) < 3:
                return None
            
            # Wire erstellen
            poly = BRepBuilderAPI_MakePolygon()
            for p in pts:
                poly.Add(gp_Pnt(float(p[0]), float(p[1]), float(p[2])))
            poly.Close()
            
            if not poly.IsDone():
                return None
            
            # Face erstellen (mit Ebene für planare Fläche)
            n = region.normal
            c = region.centroid
            
            # gp_Pln benötigt Ax3 (Koordinatensystem)
            origin = gp_Pnt(float(c[0]), float(c[1]), float(c[2]))
            direction = gp_Dir(float(n[0]), float(n[1]), float(n[2]))
            plane = gp_Pln(origin, direction)
            
            face_builder = BRepBuilderAPI_MakeFace(plane, poly.Wire())
            
            if face_builder.IsDone():
                return face_builder.Face()
            
            # Fallback: Face ohne Plane
            face_builder2 = BRepBuilderAPI_MakeFace(poly.Wire())
            if face_builder2.IsDone():
                return face_builder2.Face()
                
            return None
            
        except Exception as e:
            logger.debug(f"Face-Erzeugung fehlgeschlagen: {e}")
            return None
    
    def _convert_direct(self, mesh: 'pv.PolyData') -> Optional['Shape']:
        """
        Direkte Konvertierung: Jedes Dreieck wird zu einer Face.
        Dann UnifySameDomain um coplanare zu verschmelzen.
        """
        try:
            verts = mesh.points
            faces = mesh.faces.reshape(-1, 4)[:, 1:4]
            
            sewer = BRepBuilderAPI_Sewing(self.sewing_tol)
            
            for face_idx in faces:
                try:
                    p0 = gp_Pnt(*[float(c) for c in verts[face_idx[0]]])
                    p1 = gp_Pnt(*[float(c) for c in verts[face_idx[1]]])
                    p2 = gp_Pnt(*[float(c) for c in verts[face_idx[2]]])
                    
                    poly = BRepBuilderAPI_MakePolygon()
                    poly.Add(p0)
                    poly.Add(p1)
                    poly.Add(p2)
                    poly.Close()
                    
                    if poly.IsDone():
                        face_builder = BRepBuilderAPI_MakeFace(poly.Wire())
                        if face_builder.IsDone():
                            sewer.Add(face_builder.Face())
                except:
                    continue
            
            sewer.Perform()
            sewed_shape = sewer.SewedShape()
            
            if sewed_shape.IsNull():
                return None
            
            return self._shape_to_solid(sewed_shape)
            
        except Exception as e:
            logger.error(f"Direct Conversion fehlgeschlagen: {e}")
            return None
    
    def _convert_simplified(self, mesh: 'pv.PolyData') -> Optional['Shape']:
        """
        Konvertiert direkt und wendet dann UnifySameDomain an.
        """
        shape = self._convert_direct(mesh)
        if shape is None:
            return None
        
        try:
            # UnifySameDomain verschmilzt coplanare Flächen
            upgrader = ShapeUpgrade_UnifySameDomain(shape.wrapped, True, True, True)
            upgrader.SetLinearTolerance(0.1)
            upgrader.SetAngularTolerance(np.radians(1.0))
            upgrader.Build()
            
            simplified = upgrader.Shape()
            return Shape(simplified)
            
        except Exception as e:
            logger.warning(f"Simplification fehlgeschlagen: {e}")
            return shape
    
    def _shape_to_solid(self, ocp_shape) -> Optional['Shape']:
        """Versucht aus einem Shape ein Solid zu machen"""
        try:
            shape_type = ocp_shape.ShapeType()
            
            if shape_type == TopAbs_SHELL:
                ocp_shell = TopoDS.Shell_s(ocp_shape)
                
                # Versuche direkt ein Solid zu machen
                try:
                    maker = BRepBuilderAPI_MakeSolid(ocp_shell)
                    if maker.IsDone():
                        logger.success("Solid erfolgreich erstellt")
                        return Solid(maker.Solid())
                except Exception as e:
                    logger.debug(f"MakeSolid fehlgeschlagen: {e}")
                
                logger.warning("Shell nicht wasserdicht, gebe Shell zurück")
                return Shell(ocp_shell)
            else:
                # Compound oder anderes
                return Shape(ocp_shape)
                
        except Exception as e:
            logger.error(f"Solid-Erzeugung fehlgeschlagen: {e}")
            return Shape(ocp_shape)


# Convenience Funktion
def convert_mesh_to_solid(mesh: 'pv.PolyData', 
                          method: str = "smart",
                          angle_tolerance: float = 5.0) -> Optional['Shape']:
    """
    Konvertiert ein PyVista Mesh zu einem Build123d Solid.
    
    Args:
        mesh: PyVista PolyData
        method: 'smart', 'direct', oder 'simplified'
        angle_tolerance: Winkeltoleranz für planare Erkennung (Grad)
    
    Returns:
        Build123d Shape (Solid, Shell, oder None)
    """
    converter = SmartMeshConverter(angle_tolerance=angle_tolerance)
    return converter.convert(mesh, method=method)


# Test
if __name__ == "__main__":
    import sys
    
    if len(sys.argv) < 2:
        print("Usage: python mesh_converter_v6.py <file.stl>")
        sys.exit(1)
    
    mesh = pv.read(sys.argv[1])
    print(f"Loaded: {mesh.n_cells} faces")
    
    converter = SmartMeshConverter()
    solid = converter.convert(mesh, method="smart")
    
    if solid:
        out = sys.argv[1].replace(".stl", "_v6.step")
        solid.export_step(out)
        print(f"Exported: {out}")
    else:
        print("Conversion failed")
