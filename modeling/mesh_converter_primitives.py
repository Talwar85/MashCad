"""
MashCad - RANSAC Primitive Detector (V7)
=========================================
Intelligente Mesh-zu-BREP Konvertierung durch geometrische Primitive-Erkennung.

Strategie:
1. Mesh in Regionen segmentieren (ähnlich V6)
2. RANSAC-Fitting pro Region:
   - Plane (gp_Pln)
   - Cylinder (gp_Cylinder)
   - Sphere (gp_Sphere)
   - Cone (gp_Cone) - optional
3. OCP-Primitive-Faces erstellen
4. Faces zusammennähen zu Solid

Resultat: 10-100 analytische Faces statt 10.000 Dreiecke
→ Vollständig editierbar (Fillet, Boolean, Extrude)
"""

import numpy as np
from loguru import logger
from typing import List, Tuple, Dict, Optional
from dataclasses import dataclass

try:
    import pyvista as pv
    HAS_PYVISTA = True
except ImportError:
    HAS_PYVISTA = False
    logger.warning("PyVista nicht verfügbar")

try:
    import pyransac3d as pyrsc
    HAS_RANSAC = True
except ImportError:
    HAS_RANSAC = False
    logger.warning("pyransac3d nicht verfügbar - V7 Converter nicht nutzbar")

try:
    from scipy.cluster.hierarchy import fcluster, linkage
    HAS_SCIPY = True
except ImportError:
    HAS_SCIPY = False
    logger.warning("scipy nicht verfügbar - Clustering eingeschränkt")

try:
    from OCP.gp import gp_Pnt, gp_Vec, gp_Pln, gp_Dir, gp_Ax3, gp_Ax2, gp_Cylinder, gp_Sphere, gp_Cone
    from OCP.BRepBuilderAPI import (
        BRepBuilderAPI_MakePolygon,
        BRepBuilderAPI_MakeFace,
        BRepBuilderAPI_Sewing,
        BRepBuilderAPI_MakeSolid,
        BRepBuilderAPI_MakeEdge,
        BRepBuilderAPI_MakeWire
    )
    from OCP.BRepPrimAPI import BRepPrimAPI_MakeCylinder
    from OCP.Geom import Geom_CylindricalSurface, Geom_SphericalSurface, Geom_Plane
    from OCP.GeomAPI import GeomAPI_PointsToBSpline
    from OCP.TColgp import TColgp_HArray1OfPnt
    from OCP.GeomAbs import GeomAbs_C2
    from OCP.TopoDS import TopoDS_Face, TopoDS_Edge, TopoDS_Wire, TopoDS_Shape
    from OCP.TopAbs import TopAbs_SHELL, TopAbs_FACE
    from OCP.TopExp import TopExp_Explorer
    from build123d import Solid, Shell, Shape
    HAS_OCP = True
except ImportError:
    HAS_OCP = False
    logger.warning("OCP/build123d nicht verfügbar")


@dataclass
class GeometricPrimitive:
    """Erkanntes geometrisches Primitiv"""
    type: str  # "plane", "cylinder", "sphere", "cone", "bspline"
    params: Dict  # Typ-spezifische Parameter
    points: np.ndarray  # Zugehörige Punkte
    inliers: np.ndarray  # Inlier-Indizes
    confidence: float  # 0-1, Anteil Inliers


class RANSACPrimitiveConverter:
    """
    RANSAC-basierter Mesh-zu-BREP Converter.
    Erkennt Primitive (Plane, Cylinder, Sphere) und erzeugt analytische Flächen.
    """

    def __init__(self,
                 angle_tolerance: float = 5.0,       # Grad - für planare Regionen
                 ransac_threshold: float = 0.5,      # mm - RANSAC Inlier-Toleranz
                 min_inlier_ratio: float = 0.70,     # 70% Inliers für gültiges Primitiv
                 min_region_faces: int = 10,         # Minimum Dreiecke pro Region
                 sewing_tolerance: float = 0.1):     # mm
        """
        Args:
            angle_tolerance: Winkeltoleranz für Region-Clustering (Grad)
            ransac_threshold: Maximale Distanz für RANSAC-Inliers (mm)
            min_inlier_ratio: Minimum Inlier-Ratio für gültiges Primitiv
            min_region_faces: Minimum Faces pro Region
            sewing_tolerance: Toleranz für Sewing
        """
        self.angle_tol = np.radians(angle_tolerance)
        self.ransac_thresh = ransac_threshold
        self.min_inlier_ratio = min_inlier_ratio
        self.min_faces = min_region_faces
        self.sewing_tol = sewing_tolerance

    def convert(self, mesh: 'pv.PolyData') -> Optional['Shape']:
        """
        Konvertiert PyVista Mesh zu Build123d Solid mit RANSAC-basierten Primitiven.

        Args:
            mesh: PyVista PolyData Objekt

        Returns:
            Build123d Solid oder None bei Fehler
        """
        if not HAS_PYVISTA or not HAS_OCP or not HAS_RANSAC:
            logger.error("Abhängigkeiten fehlen (PyVista, OCP, pyransac3d)")
            return None

        logger.info("=== RANSAC Primitive Converter V7 ===")
        logger.info(f"Input: {mesh.n_points} Punkte, {mesh.n_cells} Faces")

        try:
            # 1. Mesh vorbereiten (Normals berechnen)
            if 'Normals' not in mesh.cell_data:
                mesh = mesh.compute_normals(cell_normals=True, point_normals=False)

            # 2. Regionen segmentieren (wie V6)
            regions = self._segment_regions(mesh)
            logger.info(f"Segmentiert: {regions} Regionen")

            if len(regions) == 0:
                logger.warning("Keine Regionen erkannt")
                return None

            # 3. Pro Region: Primitive fitten
            primitives = []
            total_regions = len(regions)
            for idx, (region_id, cell_ids) in enumerate(regions.items(), 1):
                points = self._extract_region_points(mesh, cell_ids)

                if len(points) < 10:
                    logger.debug(f"Region {idx}/{total_regions}: zu wenige Punkte ({len(points)})")
                    continue

                logger.debug(f"Region {idx}/{total_regions}: {len(points)} Punkte, fitting...")
                primitive = self._fit_primitive(points, mesh, cell_ids)
                if primitive:
                    primitives.append(primitive)
                    logger.info(f"  ✓ Region {idx}: {primitive.type} "
                              f"({primitive.confidence*100:.1f}% confidence)")
                else:
                    logger.debug(f"  ✗ Region {idx}: kein Primitiv erkannt")

            logger.info(f"Erkannt: {len(primitives)}/{total_regions} Primitive")

            if len(primitives) == 0:
                logger.error("Keine Primitive erkannt")
                return None

            # 4. Primitive zu OCP-Faces konvertieren
            sewer = BRepBuilderAPI_Sewing(self.sewing_tol)
            face_count = 0

            for i, prim in enumerate(primitives):
                try:
                    ocp_face = self._primitive_to_face(prim)
                    if ocp_face and not ocp_face.IsNull():
                        sewer.Add(ocp_face)
                        face_count += 1
                except Exception as e:
                    logger.warning(f"Primitive {i} zu Face fehlgeschlagen: {e}")

            logger.info(f"Erzeuge BREP aus {face_count} Faces...")

            # 5. Sewing
            sewer.Perform()
            sewed_shape = sewer.SewedShape()

            if sewed_shape.IsNull():
                logger.error("Sewing fehlgeschlagen")
                return None

            # 6. Zu Solid machen
            return self._shape_to_solid(sewed_shape)

        except Exception as e:
            logger.error(f"RANSAC Conversion fehlgeschlagen: {e}")
            import traceback
            traceback.print_exc()
            return None

    def _segment_regions(self, mesh: 'pv.PolyData') -> Dict[int, List[int]]:
        """
        Segmentiert Mesh in Regionen basierend auf Normalen-Ähnlichkeit.
        Wiederverwendet V6-Logik.

        Returns:
            Dict {region_id: [cell_ids]}
        """
        normals = mesh.cell_data['Normals']
        n_cells = mesh.n_cells

        # Normalisieren
        norms = np.linalg.norm(normals, axis=1, keepdims=True)
        norms[norms < 1e-6] = 1.0
        normals_normalized = normals / norms

        if not HAS_SCIPY or n_cells < 100:
            # Einfaches Clustering ohne scipy
            return self._segment_regions_simple(normals_normalized)

        # Hierarchisches Clustering
        try:
            # Sampling für große Meshes
            if n_cells > 10000:
                sample_idx = np.random.choice(n_cells, 5000, replace=False)
                sample_normals = normals_normalized[sample_idx]
            else:
                sample_idx = np.arange(n_cells)
                sample_normals = normals_normalized

            Z = linkage(sample_normals, method='average', metric='cosine')
            threshold = 1 - np.cos(self.angle_tol)
            labels = fcluster(Z, threshold, criterion='distance')

            # Labels auf alle Zellen übertragen
            if len(sample_idx) < n_cells:
                all_labels = np.zeros(n_cells, dtype=int)
                all_labels[sample_idx] = labels

                # Cluster-Normalen berechnen
                cluster_normals = {}
                for label in np.unique(labels):
                    mask = labels == label
                    cluster_normals[label] = np.mean(sample_normals[mask], axis=0)

                # Restliche zuordnen
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

            # Dict erstellen
            regions = {}
            for label in np.unique(labels):
                if label == 0:
                    continue
                mask = labels == label
                cell_ids = np.where(mask)[0].tolist()
                if len(cell_ids) >= self.min_faces:
                    regions[int(label)] = cell_ids

            return regions

        except Exception as e:
            logger.warning(f"Hierarchisches Clustering fehlgeschlagen: {e}")
            return self._segment_regions_simple(normals_normalized)

    def _segment_regions_simple(self, normals: np.ndarray) -> Dict[int, List[int]]:
        """Einfaches Grid-basiertes Clustering (Fallback ohne scipy)"""
        # Discretize normals to grid
        n_bins = 20
        discretized = np.round(normals * n_bins).astype(int)

        # Group by discretized normal
        regions = {}
        region_id = 1
        seen = set()

        for i, dn in enumerate(discretized):
            key = tuple(dn)
            if key not in seen:
                # Neue Region
                mask = np.all(discretized == dn, axis=1)
                cell_ids = np.where(mask)[0].tolist()
                if len(cell_ids) >= self.min_faces:
                    regions[region_id] = cell_ids
                    region_id += 1
                seen.add(key)

        return regions

    def _extract_region_points(self, mesh: 'pv.PolyData', cell_ids: List[int]) -> np.ndarray:
        """Extrahiert alle Punkte einer Region"""
        points_list = []
        for cell_id in cell_ids:
            cell = mesh.get_cell(cell_id)
            point_ids = cell.point_ids
            for pid in point_ids:
                points_list.append(mesh.points[pid])

        # Unique points
        points = np.array(points_list)
        if len(points) > 0:
            points = np.unique(points, axis=0)

        return points

    def _fit_primitive(self, points: np.ndarray, mesh: 'pv.PolyData',
                      cell_ids: List[int]) -> Optional[GeometricPrimitive]:
        """
        Fittet geometrisches Primitiv auf Punktwolke mit RANSAC.
        Probiert: Plane, Cylinder, Sphere
        """
        if len(points) < 10:
            return None

        best_primitive = None
        best_confidence = 0.0

        # 1. Plane Fitting
        try:
            plane_model = pyrsc.Plane()
            best_eq, inliers = plane_model.fit(points, thresh=self.ransac_thresh)
            confidence = len(inliers) / len(points)

            if confidence > best_confidence and confidence >= self.min_inlier_ratio:
                # Plane parameters: [a, b, c, d] -> ax + by + cz + d = 0
                best_primitive = GeometricPrimitive(
                    type="plane",
                    params={"equation": best_eq},
                    points=points[inliers],
                    inliers=inliers,
                    confidence=confidence
                )
                best_confidence = confidence
        except Exception as e:
            logger.debug(f"Plane fitting fehlgeschlagen: {e}")

        # 2. Cylinder Fitting (nur wenn nicht schon gute Plane)
        if best_confidence < 0.85:
            try:
                cyl_model = pyrsc.Cylinder()
                result = cyl_model.fit(points, thresh=self.ransac_thresh)

                # API kann variieren: (params, inliers) oder nur params
                if isinstance(result, tuple) and len(result) == 2:
                    best_cyl, inliers = result
                else:
                    best_cyl = result
                    inliers = np.arange(len(points))  # Fallback: alle Punkte

                confidence = len(inliers) / len(points) if len(inliers) > 0 else 0.0

                if confidence > best_confidence and confidence >= self.min_inlier_ratio:
                    # best_cyl kann verschiedene Formate haben
                    center, axis, radius = None, None, None

                    if isinstance(best_cyl, dict):
                        center = best_cyl.get('center')
                        axis = best_cyl.get('axis')
                        radius = best_cyl.get('radius')
                    elif isinstance(best_cyl, (list, tuple)) and len(best_cyl) >= 3:
                        center, axis, radius = best_cyl[0], best_cyl[1], best_cyl[2]

                    if center is not None and axis is not None and radius is not None:
                        # Height aus Bounding Box schätzen
                        inlier_points = points[inliers]
                        projected = np.dot(inlier_points - center, axis)
                        height = max(projected.max() - projected.min(), 1.0)

                        best_primitive = GeometricPrimitive(
                            type="cylinder",
                            params={
                                "center": center,
                                "axis": axis,
                                "radius": radius,
                                "height": height
                            },
                            points=inlier_points,
                            inliers=inliers,
                            confidence=confidence
                        )
                        best_confidence = confidence
            except Exception as e:
                logger.debug(f"Cylinder fitting fehlgeschlagen: {e}")

        # 3. Sphere Fitting (nur wenn weder Plane noch Cylinder gut)
        if best_confidence < 0.85:
            try:
                sphere_model = pyrsc.Sphere()
                result = sphere_model.fit(points, thresh=self.ransac_thresh)

                # API kann variieren
                if isinstance(result, tuple) and len(result) == 2:
                    best_sphere, inliers = result
                else:
                    best_sphere = result
                    inliers = np.arange(len(points))

                confidence = len(inliers) / len(points) if len(inliers) > 0 else 0.0

                if confidence > best_confidence and confidence >= self.min_inlier_ratio:
                    center, radius = None, None

                    if isinstance(best_sphere, dict):
                        center = best_sphere.get('center')
                        radius = best_sphere.get('radius')
                    elif isinstance(best_sphere, (list, tuple)) and len(best_sphere) >= 2:
                        center, radius = best_sphere[0], best_sphere[1]

                    if center is not None and radius is not None:
                        best_primitive = GeometricPrimitive(
                            type="sphere",
                            params={
                                "center": center,
                                "radius": radius
                            },
                            points=points[inliers],
                            inliers=inliers,
                            confidence=confidence
                        )
                        best_confidence = confidence
            except Exception as e:
                logger.debug(f"Sphere fitting fehlgeschlagen: {e}")

        return best_primitive

    def _primitive_to_face(self, prim: GeometricPrimitive) -> Optional[TopoDS_Face]:
        """Konvertiert GeometricPrimitive zu OCP TopoDS_Face"""
        try:
            if prim.type == "plane":
                return self._create_planar_face(prim)
            elif prim.type == "cylinder":
                return self._create_cylindrical_face(prim)
            elif prim.type == "sphere":
                return self._create_spherical_face(prim)
            else:
                logger.warning(f"Unbekannter Primitiv-Typ: {prim.type}")
                return None
        except Exception as e:
            logger.warning(f"Face-Erzeugung fehlgeschlagen ({prim.type}): {e}")
            return None

    def _create_planar_face(self, prim: GeometricPrimitive) -> Optional[TopoDS_Face]:
        """Erstellt planare Fläche aus Plane-Primitiv"""
        eq = prim.params["equation"]  # [a, b, c, d]
        a, b, c, d = eq

        # Normale normalisieren
        normal_len = np.sqrt(a*a + b*b + c*c)
        if normal_len < 1e-6:
            return None

        normal = np.array([a, b, c]) / normal_len
        d_norm = d / normal_len

        # Punkt auf Ebene finden
        # Wenn c != 0: z = -d/c bei x=0, y=0
        if abs(c) > 1e-6:
            origin = np.array([0, 0, -d_norm/normal[2]])
        elif abs(b) > 1e-6:
            origin = np.array([0, -d_norm/normal[1], 0])
        else:
            origin = np.array([-d_norm/normal[0], 0, 0])

        # OCP Plane erstellen
        gp_origin = gp_Pnt(*origin)
        gp_normal = gp_Dir(*normal)
        plane = gp_Pln(gp_origin, gp_normal)

        # Boundary aus Punkten extrahieren (ConvexHull)
        try:
            # Projiziere Punkte auf Ebene
            points_3d = prim.points
            if len(points_3d) < 3:
                return None

            projected = points_3d - np.dot(points_3d - origin, normal)[:, None] * normal

            # 2D Koordinaten (lokales Koordinatensystem auf Ebene)
            u = np.cross([0, 0, 1], normal)
            if np.linalg.norm(u) < 1e-6:
                u = np.cross([0, 1, 0], normal)
            u = u / np.linalg.norm(u)
            v = np.cross(normal, u)

            points_2d = np.column_stack([
                np.dot(projected - origin, u),
                np.dot(projected - origin, v)
            ])

            # ConvexHull für Boundary (mit scipy wenn verfügbar)
            boundary_2d = None
            try:
                from scipy.spatial import ConvexHull
                hull = ConvexHull(points_2d)
                boundary_2d = points_2d[hull.vertices]
            except ImportError:
                # Fallback: Nutze einfach Bounding Box
                min_x, max_x = points_2d[:, 0].min(), points_2d[:, 0].max()
                min_y, max_y = points_2d[:, 1].min(), points_2d[:, 1].max()
                boundary_2d = np.array([
                    [min_x, min_y],
                    [max_x, min_y],
                    [max_x, max_y],
                    [min_x, max_y]
                ])

            if boundary_2d is None or len(boundary_2d) < 3:
                return None

            # Zurück zu 3D
            boundary_3d = origin + boundary_2d[:, 0:1] * u + boundary_2d[:, 1:2] * v

            # Polygon aus Boundary erstellen
            polygon = BRepBuilderAPI_MakePolygon()
            for pt in boundary_3d:
                polygon.Add(gp_Pnt(float(pt[0]), float(pt[1]), float(pt[2])))
            polygon.Close()

            if not polygon.IsDone():
                return None

            # Face aus Plane und Wire
            wire = polygon.Wire()
            face_builder = BRepBuilderAPI_MakeFace(plane, wire)

            if face_builder.IsDone():
                return face_builder.Face()

        except Exception as e:
            logger.debug(f"Planar face Erstellung fehlgeschlagen: {e}")

        return None

    def _create_cylindrical_face(self, prim: GeometricPrimitive) -> Optional[TopoDS_Face]:
        """Erstellt zylindrische Fläche aus Cylinder-Primitiv"""
        try:
            center = np.array(prim.params["center"], dtype=float)
            axis = np.array(prim.params["axis"], dtype=float)
            radius = float(prim.params["radius"])
            height = float(prim.params["height"])

            # Validierung
            if radius <= 0 or height <= 0:
                return None

            # Achse normalisieren
            axis_len = np.linalg.norm(axis)
            if axis_len < 1e-6:
                return None
            axis = axis / axis_len

            # OCP Cylinder
            gp_center = gp_Pnt(float(center[0]), float(center[1]), float(center[2]))
            gp_axis = gp_Dir(float(axis[0]), float(axis[1]), float(axis[2]))
            ax3 = gp_Ax3(gp_center, gp_axis)

            # Mantel-Fläche (ohne Deckel)
            face_builder = BRepBuilderAPI_MakeFace(
                Geom_CylindricalSurface(ax3, radius).GetHandle(),
                0.0, 2 * np.pi,  # U-range
                0.0, height,      # V-range
                1e-6
            )

            if face_builder.IsDone():
                return face_builder.Face()

        except Exception as e:
            logger.debug(f"Cylindrical face Erstellung fehlgeschlagen: {e}")

        return None

    def _create_spherical_face(self, prim: GeometricPrimitive) -> Optional[TopoDS_Face]:
        """Erstellt sphärische Fläche aus Sphere-Primitiv"""
        try:
            center = np.array(prim.params["center"], dtype=float)
            radius = float(prim.params["radius"])

            # Validierung
            if radius <= 0:
                return None

            # OCP Sphere
            gp_center = gp_Pnt(float(center[0]), float(center[1]), float(center[2]))

            # Ganze Kugel: u=[0, 2*pi], v=[-pi/2, pi/2]
            face_builder = BRepBuilderAPI_MakeFace(
                Geom_SphericalSurface(gp_Ax3(gp_center, gp_Dir(0, 0, 1)), radius).GetHandle(),
                0.0, 2 * np.pi,        # U
                -np.pi/2, np.pi/2,     # V
                1e-6
            )

            if face_builder.IsDone():
                return face_builder.Face()

        except Exception as e:
            logger.debug(f"Spherical face Erstellung fehlgeschlagen: {e}")

        return None

    def _shape_to_solid(self, shape: TopoDS_Shape) -> Optional['Solid']:
        """Konvertiert TopoDS_Shape zu Build123d Solid"""
        try:
            # Prüfen ob Shell
            if shape.ShapeType() == TopAbs_SHELL:
                # Shell zu Solid
                solid_builder = BRepBuilderAPI_MakeSolid()
                solid_builder.Add(shape)

                if solid_builder.IsDone():
                    solid_shape = solid_builder.Solid()
                    return Solid(solid_shape)

            # Direkt als Shape wrappen
            wrapped = Shape.cast(shape)
            if isinstance(wrapped, Solid):
                return wrapped
            elif isinstance(wrapped, Shell):
                # Shell zu Solid
                solid_builder = BRepBuilderAPI_MakeSolid()
                solid_builder.Add(wrapped.wrapped)
                if solid_builder.IsDone():
                    return Solid(solid_builder.Solid())

            logger.warning(f"Shape ist kein Solid/Shell: {shape.ShapeType()}")
            return None

        except Exception as e:
            logger.error(f"Shape zu Solid Konvertierung fehlgeschlagen: {e}")
            return None
