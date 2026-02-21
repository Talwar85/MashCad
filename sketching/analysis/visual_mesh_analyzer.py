"""
Visual Mesh Analyzer - Computer Vision für 3D-Meshes

Wendet OpenCV-ähnliche Algorithmen auf 3D-Daten an.
Kein "Raten" mehr - echte visuelle Analyse.

Author: Claude (Lead Developer)
Date: 2026-02-14
"""

import logging
from dataclasses import dataclass
from typing import List, Tuple, Optional, Dict, Any
from pathlib import Path

import numpy as np

try:
    import cv2
    HAS_OPENCV = True
    logger = logging.getLogger(__name__)
    logger.info("OpenCV available for visual mesh analysis")
except ImportError:
    HAS_OPENCV = False
    logger = logging.getLogger(__name__)
    logger.info("OpenCV not available - using numpy/scipy fallback")

try:
    from scipy.spatial import Delaunay, ConvexHull
    from scipy.ndimage import binary_erosion, binary_dilation, label
    HAS_SCIPY = True
except ImportError:
    HAS_SCIPY = False
    logger.warning("SciPy not available - limited functionality")

try:
    from shapely.geometry import Polygon, MultiPoint, LineString
    from shapely.ops import unary_union, linemerge
    HAS_SHAPELY = True
except ImportError:
    HAS_SHAPELY = False
    logger.warning("Shapely not available - limited functionality")

logger = logging.getLogger(__name__)


@dataclass
class Projection2D:
    """2D-Projektion eines 3D-Meshes."""
    name: str  # "top", "side", "front"
    axis_normal: Tuple[int, int, int]  # (0,0,1) für Top-View
    axis_up: Tuple[int, int, int]  # (0,1,0) für Up-Richtung
    points_2d: np.ndarray  # (N, 2) Array von 2D-Punkten
    z_values: np.ndarray  # (N,) Array von Z-Werten (Höhe)
    bounds: Tuple[float, float, float, float]  # (min_x, max_x, min_y, max_y)
    mesh_bounds: Tuple[float, float, float, float, float, float]  # 3D-Bounds
    area_2d: float = 0.0
    plane_origin: Tuple[float, float, float] = (0.0, 0.0, 0.0)
    plane_normal: Tuple[float, float, float] = (0.0, 0.0, 1.0)


@dataclass
class ContourInfo:
    """Erkannte Kontur mit Metadaten."""
    points: np.ndarray  # (N, 2) Konturpunkte
    area: float
    perimeter: float
    centroid: Tuple[float, float]
    is_closed: bool = True
    circularity: float = 0.0  # 0 = linear, 1 = perfekt kreisförmig
    convexity: float = 0.0  # 0 = konkav, 1 = konvex
    bounding_box: Tuple[float, float, float, float] = (0.0, 0.0, 0.0, 0.0)  # (min_x, max_x, min_y, max_y)
    equivalent_radius: float = 0.0
    aspect_ratio: float = 0.0
    has_holes: bool = False  # NEW: True wenn Kontur Löcher enthält (z.B. Rechteck mit Loch)


@dataclass
class CircleInfo:
    """Erkannter Kreis mit Parametern."""
    center: Tuple[float, float]  # 2D-Zentrum
    center_3d: Tuple[float, float, float]  # 3D-Zentrum
    radius: float
    confidence: float
    num_points: int = 0
    residual_error: float = 0.0


@dataclass
class RectangleInfo:
    """Erkanntes Rechteck/Oriented Bounding Box."""
    center: Tuple[float, float]
    center_3d: Tuple[float, float, float]
    width: float
    height: float
    angle: float  # Rotation in Grad
    corners_2d: List[Tuple[float, float]]
    corners_3d: List[Tuple[float, float, float]]
    area: float
    confidence: float


class VisualMeshAnalyzer:
    """
    Wendet Computer-Vision-Algorithmen auf 3D-Meshes an.

    Konzept:
    1. 3D-Mesh → 2D-Projektionen (Top, Side, Front)
    2. 2D-Bilder → Kontur-Extraktion
    3. Konturen → Feature-Erkennung (Kreise, Rechtecke, Polygone)
    4. 2D-Features → 3D-Rückprojektion
    """

    def __init__(self, mesh=None):
        """
        Args:
            mesh: PyVista PolyData Objekt
        """
        self.mesh = mesh
        self.points = None
        self.normals = None
        self.bounds = None

        if mesh is not None:
            self.points = mesh.points
            try:
                self.normals = mesh.cell_normals
            except Exception:
                self.normals = None
            self.bounds = mesh.bounds

        # Konfiguration
        self.pixel_resolution = 0.5  # mm per Pixel
        self.min_contour_area = 1.0  # mm²
        self.min_hole_radius = 0.5  # mm
        self.max_hole_radius = 100.0  # mm

    def analyze_mesh(self, mesh) -> Dict[str, Any]:
        """
        Hauptfunktion: Analysiert Mesh mit visuellen Algorithmen.

        Returns:
            Dict mit:
            - projections: Liste von Projection2D
            - contours: Liste von Konturen pro Projektion
            - circles: Liste von erkannten Kreisen
            - base_plane: Erkannte Base-Plane
        """
        self.mesh = mesh
        self.points = mesh.points
        self.bounds = mesh.bounds

        # 1. 2D-Projektionen erstellen
        projections = self._create_2d_projections()

        # 2. Konturen extrahieren
        contours_by_view = {}
        for proj in projections:
            contours = self._extract_contours_from_projection(proj)
            contours_by_view[proj.name] = contours

        # 3. Kreise erkennen
        circles_by_view = {}
        for proj in projections:
            circles = self._detect_circles_in_projection(proj)
            circles_by_view[proj.name] = circles

        return {
            "projections": projections,
            "contours": contours_by_view,
            "circles": circles_by_view,
            "mesh_bounds": self.bounds,
        }

    def _create_2d_projections(self) -> List[Projection2D]:
        """Erstellt 2D-Projektionen (Top, Side, Front)."""
        if self.points is None:
            return []

        projections = []
        bounds = self.bounds
        points = self.points

        # 1. Top-View (Projektion auf XY-Ebene)
        # axis_normal = (0, 0, 1), schauen von oben
        # axis_up = (0, 1, 0), Y ist oben
        top_points = points[:, [0, 1]]  # X, Y
        top_z = points[:, 2]  # Z für Höheninformation
        proj_top = Projection2D(
            name="top",
            axis_normal=(0, 0, 1),
            axis_up=(0, 1, 0),
            points_2d=top_points,
            z_values=top_z,
            bounds=(bounds[0], bounds[1], bounds[2], bounds[3]),
            mesh_bounds=bounds,
            plane_origin=(0.0, 0.0, bounds[4]),  # Z-min
            plane_normal=(0.0, 0.0, 1.0),
        )
        proj_top.area_2d = (bounds[1] - bounds[0]) * (bounds[3] - bounds[2])
        projections.append(proj_top)

        # 2. Front-View (Projektion auf XZ-Ebene)
        # axis_normal = (0, 1, 0), schauen von vorne
        # axis_up = (0, 0, 1), Z ist oben
        front_points = points[:, [0, 2]]  # X, Z
        front_z = points[:, 1]  # Y für Höheninformation
        proj_front = Projection2D(
            name="front",
            axis_normal=(0, 1, 0),
            axis_up=(0, 0, 1),
            points_2d=front_points,
            z_values=front_z,
            bounds=(bounds[0], bounds[1], bounds[4], bounds[5]),
            mesh_bounds=bounds,
            plane_origin=(0.0, bounds[2], 0.0),  # Y-min
            plane_normal=(0.0, 1.0, 0.0),
        )
        proj_front.area_2d = (bounds[1] - bounds[0]) * (bounds[5] - bounds[4])
        projections.append(proj_front)

        # 3. Side-View (Projektion auf YZ-Ebene)
        # axis_normal = (1, 0, 0), schauen von rechts
        # axis_up = (0, 0, 1), Z ist oben
        side_points = points[:, [1, 2]]  # Y, Z
        side_z = points[:, 0]  # X für Höheninformation
        proj_side = Projection2D(
            name="side",
            axis_normal=(1, 0, 0),
            axis_up=(0, 0, 1),
            points_2d=side_points,
            z_values=side_z,
            bounds=(bounds[2], bounds[3], bounds[4], bounds[5]),
            mesh_bounds=bounds,
            plane_origin=(bounds[0], 0.0, 0.0),  # X-min
            plane_normal=(1.0, 0.0, 0.0),
        )
        proj_side.area_2d = (bounds[3] - bounds[2]) * (bounds[5] - bounds[4])
        projections.append(proj_side)

        return projections

    def _extract_contours_from_projection(self, proj: Projection2D) -> List[ContourInfo]:
        """Extrahiert Konturen aus 2D-Projektion."""
        contours = []

        try:
            # 1. Binärbild erstellen
            binary, extent = self._points_to_binary_image(proj)

            if binary is None:
                return contours

            # 2. Konturen extrahieren
            if HAS_OPENCV:
                contours = self._extract_contours_opencv(binary, extent)
            else:
                contours = self._extract_contours_scipy(binary, extent)

            # 3. Konturen filtern und analysieren
            valid_contours = []
            for contour in contours:
                if contour.area >= self.min_contour_area:
                    contour.circularity = self._calculate_circularity(contour)
                    contour.convexity = self._calculate_convexity(contour)
                    contour.equivalent_radius = np.sqrt(contour.area / np.pi)
                    valid_contours.append(contour)

            return valid_contours

        except Exception as e:
            logger.warning(f"Contour extraction failed for {proj.name}: {e}")
            return contours

    def _points_to_binary_image(self, proj: Projection2D) -> Tuple[Optional[np.ndarray], Tuple[float, float, float, float]]:
        """Konvertiert 2D-Punkte in Binärbild."""
        try:
            points_2d = proj.points_2d
            bounds_2d = proj.bounds

            # Bildgröße berechnen
            width = bounds_2d[1] - bounds_2d[0]
            height = bounds_2d[3] - bounds_2d[2]

            if width <= 0 or height <= 0:
                return None, bounds_2d

            # Pixelgröße berechnen
            nx = int(np.ceil(width / self.pixel_resolution)) + 1
            ny = int(np.ceil(height / self.pixel_resolution)) + 1

            # Binärbild erstellen
            binary = np.zeros((ny, nx), dtype=bool)

            # Punkte zu Pixel kovertieren
            pixel_x = ((points_2d[:, 0] - bounds_2d[0]) / self.pixel_resolution).astype(int)
            pixel_y = ((points_2d[:, 1] - bounds_2d[2]) / self.pixel_resolution).astype(int)

            # Clip zu Bildgrenzen
            pixel_x = np.clip(pixel_x, 0, nx - 1)
            pixel_y = np.clip(pixel_y, 0, ny - 1)

            # Pixel setzen
            binary[pixel_y, pixel_x] = True

            # Morphologische Operationen ( Closing um Lücken zu füllen )
            if HAS_SCIPY:
                from scipy.ndimage import binary_closing
                binary = binary_closing(binary, structure=np.ones((3, 3)))

            return binary, bounds_2d

        except Exception as e:
            logger.warning(f"Binary image creation failed: {e}")
            return None, proj.bounds

    def _extract_contours_opencv(self, binary: np.ndarray, extent: Tuple[float, float, float, float]) -> List[ContourInfo]:
        """Extrahiert Konturen mit OpenCV."""
        contours = []

        try:
            # OpenCV erwartet uint8
            binary_uint8 = binary.astype(np.uint8) * 255

            # Konturen finden
            contours_cv, hierarchy = cv2.findContours(
                binary_uint8,
                cv2.RETR_EXTERNAL,
                cv2.CHAIN_APPROX_TC89_KCOS
            )

            res_x = self.pixel_resolution
            res_y = self.pixel_resolution
            offset_x, offset_y = extent[0], extent[2]

            for contour in contours_cv:
                # Approximieren
                epsilon = 0.005 * cv2.arcLength(contour, True)
                approx = cv2.approxPolyDP(contour, epsilon, True)

                # Zu Weltkoordinaten zurückkonvertieren
                points_2d = contour.reshape(-1, 2).astype(float)
                points_2d[:, 0] = points_2d[:, 0] * res_x + offset_x
                points_2d[:, 1] = points_2d[:, 1] * res_y + offset_y

                # Metriken berechnen
                area = cv2.contourArea(contour) * res_x * res_y
                perimeter = cv2.arcLength(contour, True) * res_x
                centroid = self._calculate_centroid(points_2d)

                # Bounding Box
                x_coords = points_2d[:, 0]
                y_coords = points_2d[:, 1]
                bounding_box = (x_coords.min(), x_coords.max(), y_coords.min(), y_coords.max())

                contours.append(ContourInfo(
                    points=points_2d,
                    area=float(area),
                    perimeter=float(perimeter),
                    centroid=tuple(centroid),
                    is_closed=True,
                    bounding_box=tuple(map(float, bounding_box)),
                ))

        except Exception as e:
            logger.warning(f"OpenCV contour extraction failed: {e}")

        return contours

    def _extract_contours_scipy(self, binary: np.ndarray, extent: Tuple[float, float, float, float]) -> List[ContourInfo]:
        """Extrahiert Konturen mit SciPy/Shapely (Fallback)."""
        contours = []

        try:
            if not HAS_SHAPELY:
                return contours

            # Punkte aus Binärbild extrahieren
            y_coords, x_coords = np.where(binary)
            if len(x_coords) == 0:
                return contours

            res_x = self.pixel_resolution
            res_y = self.pixel_resolution
            offset_x, offset_y = extent[0], extent[2]

            # Zu Weltkoordinaten konvertieren
            points_2d = np.column_stack((
                x_coords * res_x + offset_x,
                y_coords * res_y + offset_y
            ))

            # Alpha Shape (Concave Hull)
            try:
                from scipy.spatial import Delaunay
                mp = MultiPoint(points_2d.tolist())
                triangles = Delaunay(mp)

                # Filter triangles by edge length
                max_edge_len = 15.0  # mm
                valid_triangles = []
                for tri in triangles.geoms:
                    if tri.area < 1e-6:
                        continue
                    coords = list(tri.exterior.coords)
                    is_valid = True
                    for k in range(3):
                        p1 = np.array(coords[k])
                        p2 = np.array(coords[(k + 1) % 3])
                        dist = np.linalg.norm(p1 - p2)
                        if dist > max_edge_len:
                            is_valid = False
                            break
                    if is_valid:
                        valid_triangles.append(tri)

                if valid_triangles:
                    # Union of valid triangles = Concave Hull
                    poly = unary_union(valid_triangles)

                    # Handle MultiPolygon
                    if poly.geom_type == 'MultiPolygon':
                        poly = max(poly.geoms, key=lambda p: p.area)

                    # Simplify
                    poly = poly.simplify(0.5, preserve_topology=True)

                    if not poly.is_empty:
                        exterior_coords = list(poly.exterior.coords)[:-1]  # Remove duplicate end
                        points_2d = np.array(exterior_coords)

                        area = poly.area
                        perimeter = poly.length
                        centroid = poly.centroid.coords[0]
                        x, y = zip(*exterior_coords)

                        # Check for interiors (holes) - filter them out
                        has_holes = hasattr(poly, 'interiors') and len(poly.interiors) > 0

                        contours.append(ContourInfo(
                            points=points_2d,
                            area=float(area),
                            perimeter=float(perimeter),
                            centroid=centroid,
                            is_closed=True,
                            bounding_box=(min(x), max(x), min(y), max(y)),
                            has_holes=has_holes,  # NEW: Track holes in contour
                        ))

            except Exception as e:
                logger.warning(f"Alpha shape calculation failed: {e}")

                # Fallback: Convex Hull
                try:
                    from scipy.spatial import ConvexHull
                    hull = ConvexHull(points_2d)
                    hull_points = points_2d[hull.vertices]

                    # Schließen
                    hull_points = np.vstack([hull_points, hull_points[0]])

                    area = hull.volume  # Für 2D: volume = area
                    perimeter = np.sum(np.linalg.norm(
                        np.diff(hull_points, axis=0), axis=1
                    ))
                    centroid = np.mean(hull_points, axis=0)

                    contours.append(ContourInfo(
                        points=hull_points,
                        area=float(area),
                        perimeter=float(perimeter),
                        centroid=tuple(centroid),
                        is_closed=True,
                    ))

                except Exception as e2:
                    logger.warning(f"Convex hull fallback failed: {e2}")

        except Exception as e:
            logger.warning(f"SciPy contour extraction failed: {e}")

        return contours

    def _detect_circles_in_projection(self, proj: Projection2D) -> List[CircleInfo]:
        """Erkennt Kreise in einer Projektion."""
        circles = []

        try:
            # Konturen extrahieren
            contours = self._extract_contours_from_projection(proj)

            for contour in contours:
                # Check if circular
                if contour.circularity > 0.7:  # Schwellenwert
                    radius = contour.equivalent_radius

                    if self.min_hole_radius <= radius <= self.max_hole_radius:
                        # 3D-Zentrum berechnen
                        center_3d = self._project_2d_to_3d(
                            contour.centroid,
                            proj,
                            np.mean(proj.z_values)  # Durchschnittliche Höhe
                        )

                        circles.append(CircleInfo(
                            center=contour.centroid,
                            center_3d=tuple(center_3d),
                            radius=radius,
                            confidence=contour.circularity,
                            num_points=len(contour.points),
                        ))

        except Exception as e:
            logger.warning(f"Circle detection failed for {proj.name}: {e}")

        return circles

    def _detect_min_area_rect(self, proj: Projection2D) -> Optional[RectangleInfo]:
        """Erkennt minimales Bounding-Rectangle (wie OpenCV minAreaRect)."""
        try:
            # Äußere Kontur finden
            contours = self._extract_contours_from_projection(proj)

            if not contours:
                return None

            # Größte Kontur nehmen
            outer_contour = max(contours, key=lambda c: c.area)

            if HAS_OPENCV:
                return self._min_area_rect_opencv(outer_contour, proj)
            else:
                return self._min_area_rect_pca(outer_contour, proj)

        except Exception as e:
            logger.warning(f"Min area rect detection failed: {e}")
            return None

    def _min_area_rect_opencv(self, contour: ContourInfo, proj: Projection2D) -> Optional[RectangleInfo]:
        """OpenCV minAreaRect."""
        try:
            # Zu Pixel-Koordinaten für OpenCV
            res_x, res_y = self.pixel_resolution, self.pixel_resolution
            offset_x, offset_y = proj.bounds[0], proj.bounds[2]

            points_pixel = ((contour.points - [offset_x, offset_y]) / [res_x, res_y]).astype(np.float32)

            # MinAreaRect
            rect = cv2.minAreaRect(points_pixel)
            center, size, angle = rect

            # Eckpunkte berechnen
            corners = cv2.boxPoints(rect)
            corners = corners.astype(np.float32)

            # Zurück zu Weltkoordinaten
            center_2d = center * [res_x, res_y] + [offset_x, offset_y]
            width, height = size * res_x, size[1] * res_y
            corners_2d = corners * [res_x, res_y] + [offset_x, offset_y]

            # 3D-Eckpunkte
            corners_3d = [
                self._project_2d_to_3d(tuple(c), proj, np.mean(proj.z_values))
                for c in corners_2d
            ]
            center_3d = self._project_2d_to_3d(tuple(center_2d), proj, np.mean(proj.z_values))

            return RectangleInfo(
                center=tuple(center_2d),
                center_3d=tuple(center_3d),
                width=float(width),
                height=float(height),
                angle=float(angle),
                corners_2d=[tuple(c) for c in corners_2d],
                corners_3d=[tuple(c) for c in corners_3d],
                area=float(width * height),
                confidence=0.9,
            )

        except Exception as e:
            logger.warning(f"OpenCV minAreaRect failed: {e}")
            return None

    def _min_area_rect_pca(self, contour: ContourInfo, proj: Projection2D) -> Optional[RectangleInfo]:
        """PCA-basiertes MinAreaRect (Fallback ohne OpenCV)."""
        try:
            points = contour.points

            # PCA
            centered = points - np.mean(points, axis=0)
            cov = np.cov(centered.T)
            eigenvalues, eigenvectors = np.linalg.eig(cov)

            # Sortieren
            idx = eigenvalues.argsort()[::-1]
            eigenvectors = eigenvectors[:, idx]
            eigenvalues = eigenvalues[idx]

            # Hauptachsen
            axis_0 = eigenvectors[:, 0]
            axis_1 = eigenvectors[:, 1]

            # Punkte auf Hauptachsen projizieren
            proj_0 = np.dot(centered, axis_0)
            proj_1 = np.dot(centered, axis_1)

            # Ausdehnung
            width = proj_0.max() - proj_0.min()
            height = proj_1.max() - proj_1.min()

            # Zentrum
            center_2d = tuple(np.mean(points, axis=0))

            # Winkel (in Grad)
            angle = np.degrees(np.arctan2(axis_0[1], axis_0[0]))

            # Eckpunkte
            half_w = width / 2
            half_h = height / 2
            corners_local = np.array([
                [-half_w, -half_h],
                [half_w, -half_h],
                [half_w, half_h],
                [-half_w, half_h]
            ])

            # Rotieren und translieren
            rot_matrix = np.column_stack([axis_0, axis_1])
            corners_2d = np.dot(corners_local, rot_matrix.T) + center_2d

            # 3D-Eckpunkte
            corners_3d = [
                self._project_2d_to_3d(tuple(c), proj, np.mean(proj.z_values))
                for c in corners_2d
            ]
            center_3d = self._project_2d_to_3d(center_2d, proj, np.mean(proj.z_values))

            return RectangleInfo(
                center=center_2d,
                center_3d=tuple(center_3d),
                width=float(width),
                height=float(height),
                angle=float(angle),
                corners_2d=[tuple(c) for c in corners_2d],
                corners_3d=[tuple(c) for c in corners_3d],
                area=float(width * height),
                confidence=0.8,  # PCA etwas weniger konfident als OpenCV
            )

        except Exception as e:
            logger.warning(f"PCA minAreaRect failed: {e}")
            return None

    def _calculate_centroid(self, points: np.ndarray) -> np.ndarray:
        """Berechnet Zentroid von Punkten."""
        return np.mean(points, axis=0)

    def _calculate_circularity(self, contour: ContourInfo) -> float:
        """
        Berechnet Kreisförmigkeit (0 = linear, 1 = perfekt kreisförmig).

        Formula: C = 4*pi*Area / Perimeter^2
        """
        if contour.perimeter < 1e-6:
            return 0.0

        circularity = 4 * np.pi * contour.area / (contour.perimeter ** 2)
        return float(np.clip(circularity, 0.0, 1.0))

    def _calculate_convexity(self, contour: ContourInfo) -> float:
        """Berechnet Konvexität (0 = konkav, 1 = konvex)."""
        if not HAS_SCIPY or len(contour.points) < 3:
            return 1.0  # Annahme: konvex

        try:
            from scipy.spatial import ConvexHull
            hull = ConvexHull(contour.points)
            hull_area = hull.volume  # volume = area für 2D
            convexity = contour.area / hull_area if hull_area > 0 else 0.0
            return float(np.clip(convexity, 0.0, 1.0))
        except Exception:
            return 1.0

    def _project_2d_to_3d(self, point_2d: Tuple[float, float],
                           proj: Projection2D, z_value: float) -> Tuple[float, float, float]:
        """Projiziert 2D-Punkt zurück zu 3D."""
        # Je nach Projektionstyp
        if proj.name == "top":
            # X, Y sind aus point_2d, Z ist z_value
            return (point_2d[0], point_2d[1], z_value)
        elif proj.name == "front":
            # X, Z sind aus point_2d, Y ist z_value
            return (point_2d[0], z_value, point_2d[1])
        else:  # side
            # Y, Z sind aus point_2d, X ist z_value
            return (z_value, point_2d[0], point_2d[1])

    def backproject_contour_to_3d(self, contour: ContourInfo,
                                proj: Projection2D) -> List[Tuple[float, float, float]]:
        """Backprojiziert gesamte Kontur zu 3D."""
        points_3d = []
        for point in contour.points:
            point_3d = self._project_2d_to_3d(tuple(point), proj, proj.plane_origin[2])
            points_3d.append(point_3d)
        return points_3d

    def measure_hole_depth_ray_cast(self, mesh, base_plane, center_2d: Tuple[float, float],
                                  radius: float, proj: Projection2D) -> float:
        """
        MESS TIEFE MIT RAY-CASTING (kein Raten mehr!)

        Strategy:
        1. Ray von center entlang normal schießen
        2. Alle Mesh-Intersectionen finden
        3. Tiefe = Distanz von erster zu letzter Intersection

        Args:
            mesh: PyVista Mesh
            base_plane: PlaneInfo
            center_2d: 2D-Zentrum des Lochs
            radius: Radius des Lochs
            proj: Projektion für 3D-Rückprojektion

        Returns:
            Echte Tiefe in mm
        """
        try:
            center_3d = self._project_2d_to_3d(center_2d, proj, base_plane.origin[2])
            origin = np.array(center_3d)
            direction = np.array(base_plane.normal)

            # PyVista Ray-Casting
            # Die intersection_line Methode kann verwendet werden
            # Wir erstellen eine Linie die durch das gesamte Mesh geht
            bounds = mesh.bounds
            line_length = max(
                bounds[1] - bounds[0],
                bounds[3] - bounds[2],
                bounds[5] - bounds[4]
            ) * 2

            start = origin - direction * line_length / 2
            end = origin + direction * line_length / 2

            # Sample points entlang der Linie
            n_samples = 100
            t_values = np.linspace(0, 1, n_samples)
            line_points = np.outer(1 - t_values, start) + np.outer(t_values, end)

            # Für jeden Punkt: prüfen ob er im Mesh ist
            # Wir nutzen mesh.select_enclosed_points für innere Punkte
            inside_points = mesh.select_enclosed_points(line_points)
            inside_mask = inside_points["enclosed_points"]

            if np.sum(inside_mask) == 0:
                # Kein Schnitt - Rückfall zu Radius*2 (nur als letzter Ausweg)
                logger.warning(f"Ray-cast found no intersection, using fallback")
                return radius * 2

            # Erster und letzter innerer Punkt
            first_idx = np.where(inside_mask)[0][0]
            last_idx = np.where(inside_mask)[0][-1]

            first_point = line_points[first_idx]
            last_point = line_points[last_idx]

            depth = np.linalg.norm(last_point - first_point)

            return float(depth)

        except Exception as e:
            logger.warning(f"Ray-casting depth measurement failed: {e}")
            # Letzter Fallback: radius * 2 (besser als nichts)
            return radius * 2


# Convenience Functions
def analyze_mesh_visual(mesh, pixel_resolution: float = 0.5) -> Dict[str, Any]:
    """
    Analysiert Mesh mit visuellen Algorithmen.

    Args:
        mesh: PyVista PolyData
        pixel_resolution: mm per Pixel

    Returns:
        Dict mit Analysedaten
    """
    analyzer = VisualMeshAnalyzer(mesh)
    analyzer.pixel_resolution = pixel_resolution
    return analyzer.analyze_mesh(mesh)


def detect_base_plane_visual(mesh) -> Optional[Dict[str, Any]]:
    """
    Erkennt Base-Plane mit visuellen Algorithmen.

    Args:
        mesh: PyVista PolyData

    Returns:
        Dict mit base_plane Daten oder None
    """
    analyzer = VisualMeshAnalyzer(mesh)
    result = analyzer.analyze_mesh(mesh)

    # Dominante Projektion finden (größte Fläche)
    projections = result["projections"]
    if not projections:
        return None

    dominant_proj = max(projections, key=lambda p: p.area_2d)

    # MinAreaRect für dominante Projektion
    rect = analyzer._detect_min_area_rect(dominant_proj)

    if rect is None:
        # Fallback: Convex Hull / Alpha Shape
        contours = result["contours"].get(dominant_proj.name, [])
        if contours:
            # IMPORTANT: Filter out contours WITH holes!
            # A rectangle with a hole has has_holes=True - we want the SOLID base plane
            # Priority: 1) No holes (solid), 2) Largest area
            solid_contours = [c for c in contours if not c.has_holes]
            if solid_contours:
                outer_contour = max(solid_contours, key=lambda c: c.area)
                logger.info(f"Visual detection: Using SOLID contour (area={outer_contour.area:.0f}mm²)")
            else:
                # All contours have holes - take largest but warn
                outer_contour = max(contours, key=lambda c: c.area)
                logger.warning(f"Visual detection: All contours have holes! Taking largest (area={outer_contour.area:.0f}mm²)")
            boundary_points = analyzer.backproject_contour_to_3d(outer_contour, dominant_proj)
        else:
            boundary_points = []
    else:
        boundary_points = rect.corners_3d

    return {
        "plane_origin": dominant_proj.plane_origin,
        "plane_normal": dominant_proj.plane_normal,
        "area": dominant_proj.area_2d,
        "boundary_points": boundary_points,
        "projection_name": dominant_proj.name,
        "confidence": 0.95,
        "detection_method": "visual_projection",
    }
