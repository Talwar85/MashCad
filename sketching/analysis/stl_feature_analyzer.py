"""
STL Feature Analyzer for CAD Feature Detection.

Detects features from STL meshes with confidence scoring.
Uses scikit-learn and scipy for robust detection if available.
"""

import logging
import time
from dataclasses import dataclass, field
from typing import List, Optional, Tuple, Dict, Any, Callable
from pathlib import Path

import numpy as np

try:
    from sklearn.cluster import AgglomerativeClustering
    from sklearn.decomposition import PCA
    HAS_SKLEARN = True
except ImportError:
    HAS_SKLEARN = False

from .mesh_quality_checker import MeshQualityChecker, MeshQualityReport

logger = logging.getLogger(__name__)


@dataclass
class EdgeInfo:
    """Detected feature edge."""
    feature_type: str = "edge"
    points: List[List[float]] = field(default_factory=list) # List of Start/End points or polyline?
    # PyVista returns lines as cells. 
    # Let's store as list of points for now, or segments.
    # To keep it simple: Just points.
    type: str = "sharp" # "sharp" | "boundary"
    length: float = 0.0

@dataclass
class PlaneInfo:
    """Detected base plane."""
    feature_type: str = "base_plane"
    origin: Tuple[float, float, float] = (0.0, 0.0, 0.0)
    normal: Tuple[float, float, float] = (0.0, 0.0, 1.0)
    area: float = 0.0
    face_indices: List[int] = field(default_factory=list)
    boundary_points: List[Tuple[float, float, float]] = field(default_factory=list)
    
    # Confidence
    confidence: float = 0.0
    detection_method: str = "unknown"  # "largest_planar" | "best_fit" | "manual"
    enabled: bool = True
    
    @property
    def is_valid(self) -> bool:
        """Check if plane is valid."""
        return (
            self.area > 0 and
            np.linalg.norm(self.normal) > 0.99 and  # Unit vector
            0.0 <= self.confidence <= 1.0
        )


@dataclass
class HoleInfo:
    """Detected hole with confidence."""
    feature_type: str = "hole"
    center: Tuple[float, float, float] = (0.0, 0.0, 0.0)
    radius: float = 0.0
    depth: float = 0.0
    axis: Tuple[float, float, float] = (0.0, 0.0, 1.0)
    face_indices: List[int] = field(default_factory=list)
    
    # Confidence
    confidence: float = 0.0
    detection_method: str = "unknown"  # "cylinder_fit" | "template_match" | "manual"
    enabled: bool = True
    
    # Fallback hints for manual override
    fallback_hints: Dict[str, Any] = field(default_factory=dict)
    
    # Validation data
    validation_data: Dict[str, Any] = field(default_factory=dict)
    
    @property
    def diameter(self) -> float:
        return self.radius * 2
    
    @property
    def is_valid(self) -> bool:
        """Check if hole parameters are valid."""
        return (
            self.radius > 0.01 and  # > 0.01mm
            self.depth > 0.01 and   # > 0.01mm
            0.5 < np.linalg.norm(self.axis) < 1.5 and  # Valid direction
            0.0 <= self.confidence <= 1.0
        )


@dataclass
class PocketInfo:
    """Detected pocket with confidence."""
    feature_type: str = "pocket"
    center: Tuple[float, float, float] = (0.0, 0.0, 0.0)
    depth: float = 0.0
    boundary_face_indices: List[int] = field(default_factory=list)
    bottom_face_indices: List[int] = field(default_factory=list)
    
    # Confidence
    confidence: float = 0.0
    detection_method: str = "unknown"  # "depression_detection" | "manual"
    enabled: bool = True
    fallback_hints: Dict[str, Any] = field(default_factory=dict)


@dataclass
class FilletInfo:
    """Detected fillet with confidence."""
    feature_type: str = "fillet"
    edge_indices: List[int] = field(default_factory=list)
    radius: float = 0.0
    center: Tuple[float, float, float] = (0.0, 0.0, 0.0)
    
    # Confidence
    confidence: float = 0.0
    detection_method: str = "unknown"  # "edge_curvature" | "manual"
    enabled: bool = True


@dataclass
class STLFeatureAnalysis:
    """Complete feature analysis result."""
    mesh_path: str = ""
    mesh_quality: Optional[MeshQualityReport] = None
    
    # Detected features
    base_plane: Optional[PlaneInfo] = None
    holes: List[HoleInfo] = field(default_factory=list)
    pockets: List[PocketInfo] = field(default_factory=list)
    pockets: List[PocketInfo] = field(default_factory=list)
    fillets: List[FilletInfo] = field(default_factory=list)
    edges: List[EdgeInfo] = field(default_factory=list)
    
    # Global confidence
    overall_confidence: float = 0.0
    requires_user_review: bool = False
    
    # Timing
    duration_ms: float = 0.0
    
    # Metadata
    detection_metadata: Dict[str, Any] = field(default_factory=dict)
    
    def get_features_by_confidence(self, min_confidence: float = 0.7) -> Dict[str, List[Any]]:
        """Get all features above confidence threshold."""
        return {
            "holes": [h for h in self.holes if h.confidence >= min_confidence],
            "pockets": [p for p in self.pockets if p.confidence >= min_confidence],
            "fillets": [f for f in self.fillets if f.confidence >= min_confidence],
        }
    
    def get_low_confidence_features(self, threshold: float = 0.7) -> List[Tuple[str, Any]]:
        """Get all features below confidence threshold."""
        low_conf = []
        for hole in self.holes:
            if hole.confidence < threshold:
                low_conf.append(("hole", hole))
        for pocket in self.pockets:
            if pocket.confidence < threshold:
                low_conf.append(("pocket", pocket))
        for fillet in self.fillets:
            if fillet.confidence < threshold:
                low_conf.append(("fillet", fillet))
        return low_conf


class STLFeatureAnalyzer:
    """
    Analyzes STL mesh and detects CAD features.
    
    Leverages scikit-learn/scipy for robust detection if available,
    falls back to heuristic methods otherwise.
    """
    
    # Detection thresholds
    MIN_HOLE_RADIUS = 0.5  # mm
    MAX_HOLE_RADIUS = 100.0  # mm
    MIN_HOLE_DEPTH = 0.5  # mm
    MAX_HOLE_DEPTH = 500.0  # mm
    
    # Confidence thresholds
    HIGH_CONFIDENCE = 0.9
    MEDIUM_CONFIDENCE = 0.7
    LOW_CONFIDENCE = 0.5
    
    def __init__(self, quality_checker: Optional[MeshQualityChecker] = None):
        """Initialize analyzer."""
        self.quality_checker = quality_checker or MeshQualityChecker()
        self.pyvista_available = self.quality_checker.pyvista_available
        
        # Detection parameters
        self.hole_detection_params = {
            "cylinder_tolerance": 0.1,  # Max deviation from perfect cylinder
            "min_inlier_ratio": 0.8,    # Min ratio of points fitting cylinder
            "axis_alignment_threshold": 0.95,  # Cosine similarity for axis alignment
        }
        
        if HAS_SKLEARN:
            logger.info("STLFeatureAnalyzer initialized with scikit-learn support")
        else:
            logger.warning("scikit-learn not found - using basic heuristic detection")
    
    def analyze(self, mesh_path: str, 
                skip_quality_check: bool = False) -> STLFeatureAnalysis:
        """
        Main analysis function.
        
        Workflow:
        1. Quality Check (if not skipped)
        2. Load mesh
        3. Detect base plane
        4. Detect holes
        5. Detect pockets (optional)
        6. Calculate overall confidence
        
        Args:
            mesh_path: Path to STL file
            skip_quality_check: Skip quality check if already done
            
        Returns:
            STLFeatureAnalysis with all detected features
        """
        start_time = time.time()
        analysis = STLFeatureAnalysis(mesh_path=mesh_path)
        
        if not self.pyvista_available:
            logger.error("PyVista not available - cannot analyze")
            analysis.overall_confidence = 0.0
            return analysis
        
        try:
            import pyvista as pv
            
            # 1. Quality Check
            if not skip_quality_check:
                logger.info("Running mesh quality check...")
                analysis.mesh_quality = self.quality_checker.check(mesh_path)
                
                if analysis.mesh_quality.recommended_action == "reject":
                    logger.error("Mesh quality check failed - rejecting")
                    return analysis
                
                if analysis.mesh_quality.recommended_action == "repair":
                    logger.warning("Mesh needs repair - attempting...")
                    # Load repaired mesh
                    mesh = self._load_repaired_mesh(mesh_path)
                else:
                    mesh = pv.read(mesh_path)
            else:
                mesh = pv.read(mesh_path)
            
            if mesh is None or mesh.n_cells == 0:
                logger.error("Failed to load mesh")
                return analysis
            
            logger.info(f"Analyzing mesh: {mesh.n_cells} cells, {mesh.n_points} points")
            
            # 2. Detect base plane
            logger.info("Detecting base plane...")
            analysis.base_plane = self._detect_base_plane(mesh)
            
            # 3. Detect holes
            # 3. Detect holes
            logger.info("Detecting holes...")
            # Hybrid approach: Face clustering + Edge Loops
            face_holes = self._detect_holes(mesh, analysis.base_plane)
            edge_holes = self._detect_holes_via_edges(mesh, analysis.base_plane)
            
            # Merge holes
            # Prefer edge holes as they are simpler and more robust for "clean" CAD
            # Use spatial hashing/KDTree to merge duplicates
            analysis.holes = self._merge_holes(face_holes, edge_holes)
            
            # 4. Detect pockets (simplified version)
            logger.info("Detecting pockets...")
            analysis.pockets = self._detect_pockets_simple(mesh, analysis.base_plane)
            
            # 5. Detect edges
            logger.info("Detecting edges...")
            analysis.edges = self._detect_edges(mesh)
            
            # 6. Calculate overall confidence
            analysis = self._calculate_overall_confidence(analysis)
            
            # 6. Determine if user review needed
            low_conf_count = len(analysis.get_low_confidence_features(self.MEDIUM_CONFIDENCE))
            analysis.requires_user_review = (
                low_conf_count > 0 or
                analysis.overall_confidence < self.MEDIUM_CONFIDENCE
            )
            
            # Timing
            analysis.duration_ms = (time.time() - start_time) * 1000
            
            logger.info(f"Analysis complete: {len(analysis.holes)} holes, "
                       f"{len(analysis.pockets)} pockets, "
                       f"confidence={analysis.overall_confidence:.2f}")
            
        except Exception as e:
            logger.error(f"Analysis failed: {e}", exc_info=True)
            analysis.overall_confidence = 0.0
        
        return analysis
    
    def _load_repaired_mesh(self, mesh_path: str) -> Any:
        """Load and auto-repair mesh."""
        import pyvista as pv
        mesh = pv.read(mesh_path)
        return self.quality_checker.auto_repair(mesh)
    
    def _detect_base_plane(self, mesh: 'pyvista.PolyData') -> Optional[PlaneInfo]:
        """
        Detects the base plane (bottom or top face with largest area).
        
        For parts like V1.stl: Finds the large rectangular face at the bottom/top,
        not side faces. Returns exact contour from mesh.
        """
        try:
            import pyvista as pv
            
            # Get mesh bounds
            bounds = mesh.bounds
            min_x, max_x = bounds[0], bounds[1]
            min_y, max_y = bounds[2], bounds[3]
            min_z, max_z = bounds[4], bounds[5]
            
            # Calculate dimensions
            dim_x = max_x - min_x
            dim_y = max_y - min_y  
            dim_z = max_z - min_z
            
            # Determine which dimension is smallest (thickness direction)
            # The base planes are perpendicular to this direction
            dims = [(dim_x, 'x'), (dim_y, 'y'), (dim_z, 'z')]
            dims.sort(key=lambda x: x[0])
            
            # The base plane is perpendicular to the smallest dimension
            thickness_dir = dims[0][1]
            logger.info(f"Detected thickness direction: {thickness_dir}")
            
            # Get face centers and normals
            centers = mesh.cell_centers().points
            normals = mesh.cell_normals
            
            # Find faces at bottom and top of thickness direction
            if thickness_dir == 'z':
                bottom_z = min_z + dim_z * 0.1  # Bottom 10%
                top_z = max_z - dim_z * 0.1     # Top 10%
                
                # Find faces at bottom (normal pointing down)
                bottom_faces = []
                for i, (center, normal) in enumerate(zip(centers, normals)):
                    if center[2] < bottom_z and normal[2] < -0.8:  # Normal points down
                        bottom_faces.append(i)
                
                # Find faces at top (normal pointing up)  
                top_faces = []
                for i, (center, normal) in enumerate(zip(centers, normals)):
                    if center[2] > top_z and normal[2] > 0.8:  # Normal points up
                        top_faces.append(i)
                
                # Choose the one with more faces (usually the machined/base side)
                if len(bottom_faces) > len(top_faces):
                    face_indices = bottom_faces
                    normal = (0, 0, -1)
                    origin = (0, 0, min_z)
                else:
                    face_indices = top_faces
                    normal = (0, 0, 1)
                    origin = (0, 0, max_z)
                    
            elif thickness_dir == 'x':
                # Similar logic for X-thickness
                bottom_x = min_x + dim_x * 0.1
                bottom_faces = []
                for i, (center, normal) in enumerate(zip(centers, normals)):
                    if center[0] < bottom_x and normal[0] < -0.8:
                        bottom_faces.append(i)
                
                face_indices = bottom_faces
                normal = (-1, 0, 0)
                origin = (min_x, 0, 0)
                
            else:  # thickness_dir == 'y'
                bottom_y = min_y + dim_y * 0.1
                bottom_faces = []
                for i, (center, normal) in enumerate(zip(centers, normals)):
                    if center[1] < bottom_y and normal[1] < -0.8:
                        bottom_faces.append(i)
                
                face_indices = bottom_faces
                normal = (0, -1, 0)
                origin = (0, min_y, 0)
            
            if not face_indices:
                logger.warning("No base plane faces found, using fallback")
                return self._detect_base_plane_legacy(mesh)
            
            # Calculate area from face sizes
            areas = mesh.compute_cell_sizes()["Area"]
            total_area = np.sum([areas[i] for i in face_indices])
            
            # Calculate centroid
            face_centers = [centers[i] for i in face_indices]
            origin = tuple(np.mean(face_centers, axis=0))
            
            plane = PlaneInfo(
                origin=origin,
                normal=normal,
                area=float(total_area),
                face_indices=face_indices,
                confidence=0.85,  # High confidence for this method
                detection_method="bounding_box_base"
            )
            
            logger.info(f"Base plane detected: {len(face_indices)} faces, "
                       f"area={total_area:.2f}mm², normal={normal}")
            
            return plane
            
        except Exception as e:
            logger.error(f"Base plane detection failed: {e}")
            return self._detect_base_plane_legacy(mesh)

    def _detect_plane_ransac(self, mesh: 'pyvista.PolyData') -> Optional[PlaneInfo]:
        """
        Detektiert eine Ebene mittels RANSAC (Random Sample Consensus).
        Ideal für verrauschte oder komplexe STLs.
        """
        try:
            from sklearn.linear_model import RANSACRegressor
            
            # Hole Faces und deren Center/Normals
            # Wir nutzen Face-Centers als Punktwolke für RANSAC
            # Das ist schneller als alle Vertices
            centers = mesh.cell_centers().points
            normals = mesh.cell_normals # Use cell_normals for face normals
            
            if len(centers) < 10:
                return None
                
            # RANSAC fitting: z = ax + by + d
            # Wir müssen aufpassen bei vertikalen Ebenen!
            # Besser: PCA für Hauptrichtung, dann RANSAC in lokalem KOS
            # ODER: Wir nehmen einfach die größte planare Fläche via Clustering als "Seed"
            
            # Simple approach: Suche dominante Ebene
            # Wir testen 3 Hypothesen: Z=f(x,y), X=f(y,z), Y=f(x,z)
            # und nehmen den besten Inlier-Score
            
            best_plane = None
            best_score = -1
            best_inliers = None
            
            # Helper for fitting
            def fit_ransac(X, y):
                ransac = RANSACRegressor(random_state=42, residual_threshold=1.0) # 1mm Toleranz
                ransac.fit(X, y)
                return ransac, ransac.inlier_mask_
            
            # Case 1: Z-Plane (z = ax + by + c)
            try:
                X = centers[:, :2] # x,y
                y = centers[:, 2]  # z
                model_z, inliers_z = fit_ransac(X, y)
                score_z = np.sum(inliers_z)
                
                if score_z > best_score:
                    best_score = score_z
                    best_inliers = inliers_z
                    # Normal calculation from ax + by - z + c = 0
                    a, b = model_z.estimator_.coef_
                    length = np.sqrt(a**2 + b**2 + 1)
                    best_normal = np.array([a, b, -1]) / length
                    if best_normal[2] < 0: best_normal = -best_normal # Point up
                    best_plane = (model_z, 'z', best_normal)
            except Exception: pass
            
            # Wenn wir dominante Ebene haben
            if best_plane and best_score > (len(centers) * 0.1): # Min 10% Inliers
                model, axis_type, normal = best_plane
                
                # Sammle face indices
                inlier_indices = np.where(best_inliers)[0]
                
                # Area calculation
                # Sum area of inlier faces
                total_area = 0
                sizes = mesh.compute_cell_sizes()
                areas = sizes.cell_data['Area']
                total_area = np.sum(areas[inlier_indices])
                
                # Boundary Extraction
                # Wir müssen die "Outline" dieser Face-Menge finden
                boundary_points = []
                try:
                    # Create submesh
                    submesh = mesh.extract_cells(inlier_indices)
                    
                    # Extract boundary edges
                    edges = submesh.extract_feature_edges(
                        boundary_edges=True,
                        non_manifold_edges=False,
                        manifold_edges=False,
                        feature_edges=False
                    )
                    
                    if edges.n_cells > 0:
                       # Extract loops
                       lines_cells = edges.lines.reshape(-1, 3)[:, 1:]
                       points = edges.points
                       loops = self._extract_edge_loops(lines_cells)
                       
                       if loops:
                           # Find longest loop (perimeter)
                           longest_loop = max(loops, key=len)
                           
                           # Get points
                           boundary_points = [tuple(points[idx]) for idx in longest_loop]
                except Exception as e:
                    logger.warning(f"RANSAC Boundary extraction failed: {e}")
                
                # Origin: Centroid of inliers
                origin = np.mean(centers[inlier_indices], axis=0)
                
                return PlaneInfo(
                    origin=tuple(origin),
                    normal=tuple(normal),
                    area=float(total_area),
                    face_indices=inlier_indices.tolist(),
                    confidence=float(best_score / len(centers)),
                    detection_method="ransac_sklearn",
                    boundary_points=boundary_points
                )
                
            return None
            
        except Exception as e:
            logger.error(f"RANSAC failed: {e}")
            return None

    def _detect_base_plane_legacy(self, mesh: 'pyvista.PolyData') -> Optional[PlaneInfo]:
        """
        Detect base plane using 6-sided bounding box strategy (RANSAC-like).
        
        Strategy:
        1. Get Bounding Box of mesh
        2. Define 6 candidate planes from BB faces (Min/Max X, Y, Z)
        3. Project all mesh faces onto these 6 candidates
        4. Score based on:
           - Total Area of coplanar faces (within tolerance)
           - Normal alignment
        5. Return best candidate
        """
        try:
            import pyvista as pv
            
            # 1. Get Bounding Box
            bounds = mesh.bounds # (xmin, xmax, ymin, ymax, zmin, zmax)
            centers = mesh.cell_centers().points
            normals = mesh.cell_normals
            areas = mesh.compute_cell_sizes()["Area"]
            
            if len(centers) == 0:
                return None

            # 2. Define 6 Candidates: (Normal, Origin, Name)
            candidates = [
                (np.array([-1, 0, 0]), np.array([bounds[0], 0, 0]), "Left (-X)"),
                (np.array([ 1, 0, 0]), np.array([bounds[1], 0, 0]), "Right (+X)"),
                (np.array([ 0,-1, 0]), np.array([0, bounds[2], 0]), "Front (-Y)"),
                (np.array([ 0, 1, 0]), np.array([0, bounds[3], 0]), "Back (+Y)"),
                (np.array([ 0, 0,-1]), np.array([0, 0, bounds[4]]), "Bottom (-Z)"),
                (np.array([ 0, 0, 1]), np.array([0, 0, bounds[5]]), "Top (+Z)"),
            ]
            
            best_score = -1.0
            best_plane = None
            
            # Tolerances
            dist_tolerance = (bounds[1]-bounds[0] + bounds[3]-bounds[2] + bounds[5]-bounds[4]) / 3 * 0.01 # 1% of avg dim
            if dist_tolerance < 0.1: dist_tolerance = 0.1
            angle_tolerance = 5.0 # degrees
            cos_threshold = np.cos(np.radians(angle_tolerance))
            
            for normal, origin, name in candidates:
                # 3. Check faces against this candidate
                
                # Caclulate vector from face center to plane origin
                # dist = dot(center - origin, normal)
                # But origin is just a point on the plane.
                # For X-min plane, origin x is bounds[0]. 
                # dist = (center.x - bounds[0]) * (-1)
                
                # Vectorized distance check
                # d = (P - O) . N
                vec = centers - origin
                dists = np.abs(np.dot(vec, normal))
                
                # Vectorized angle check
                # dot(face_normal, plane_normal)
                dots = np.dot(normals, normal)
                # We care about alignment, so dot should be close to 1.0 (normals point same way)
                # If normals point opposite, it's an interior face or wrong winding? 
                # For a solid, normals point OUT. 
                # For "Bottom" plane (Normal 0,0,-1), faces on bottom should have normal (0,0,-1).
                # So dot should be ~1.0.
                
                mask = (dists < dist_tolerance) & (dots > cos_threshold)
                
                # 4. Score
                matched_indices = np.where(mask)[0]
                if len(matched_indices) == 0:
                    continue
                    
                matched_area = np.sum(areas[matched_indices])
                start_time = time.time() # Just for a seed
                
                # Score = Area * weighting
                # Prefer Z planes slightly for "Base"
                score = matched_area
                if abs(normal[2]) > 0.9: # Z axis
                    score *= 1.2 
                elif abs(normal[1]) > 0.9: # Y axis
                    score *= 1.0
                
                if score > best_score:
                    best_score = score
                    
                    # Refine origin to be the mean of matched faces? 
                    # No, usually we want the bounding box limit or the average level of the faces.
                    # Let's use the average 'level' of the matched faces to be more precise than BB
                    # projected_dist = np.mean(np.dot(centers[matched_indices] - origin, normal))
                    # refined_origin = origin + normal * projected_dist
                    
                    # Actually, for "Base Plane", we often want the geometric extremum (BB) 
                    # OR the actual physical surface average.
                    # Let's use the average of the faces to be safe (avoids noise outliers defining BB)
                    avg_center = np.mean(centers[matched_indices], axis=0)
                    
                    # Extract boundary loop
                    boundary_points = []
                    try:
                        # Create submesh
                        submesh = mesh.extract_cells(matched_indices)
                        
                        # Extract boundary edges
                        edges = submesh.extract_feature_edges(
                            boundary_edges=True,
                            non_manifold_edges=False,
                            manifold_edges=False,
                            feature_edges=False
                        )
                        
                        if edges.n_cells > 0:
                           # Extract loops
                           lines_cells = edges.lines.reshape(-1, 3)[:, 1:]
                           points = edges.points
                           loops = self._extract_edge_loops(lines_cells)
                           
                           if loops:
                               # Find longest loop (perimeter)
                               # Or largest area? Length is easier.
                               longest_loop = max(loops, key=len)
                               
                               # Get points
                               boundary_points = [tuple(points[idx]) for idx in longest_loop]
                               # Ensure closed? Usually loop logic ensures it.
                    except Exception as e:
                        logger.warning(f"Failed to extract boundary: {e}")

                    best_plane = PlaneInfo(
                        origin=tuple(avg_center),
                        normal=tuple(normal),
                        area=float(matched_area),
                        face_indices=matched_indices.tolist(),
                        boundary_points=boundary_points,
                        confidence=min(1.0, float(len(matched_indices) / len(centers)) * 5), # Boost confidence
                        detection_method=f"6-sided_bbox ({name})"
                    )
            
            if best_plane:
                logger.info(f"Base plane detected via 6-sided analysis: {best_plane.detection_method}, Area={best_plane.area:.2f}")
                return best_plane
            
            # Fallback to clustering if 6-sided failed (unlikely for CAD parts)
            logger.warning("6-sided analysis failed to find dominant plane, falling back to clustering...")
            return self._detect_base_plane_clustering(mesh)
            
        except Exception as e:
            logger.error(f"Base plane detection failed: {e}")
            return None

    def _detect_base_plane_clustering(self, mesh) -> Optional[PlaneInfo]:
        """Original clustering strategy as fallback."""
        try:
            centers = mesh.cell_centers().points
            normals = mesh.cell_normals
            
            if len(centers) == 0 or len(normals) == 0:
                return None
            
            if HAS_SKLEARN:
                normal_clusters = self._cluster_normals_sklearn(normals, angle_threshold=5.0)
            else:
                normal_clusters = self._cluster_normals_simple(normals, angle_threshold=10.0)
            
            if not normal_clusters:
                return None
            
            largest_cluster_idx = max(normal_clusters.keys(), key=lambda k: len(normal_clusters[k]))
            cluster_face_indices = normal_clusters[largest_cluster_idx]
            cluster_centers = centers[cluster_face_indices]
            
            cluster_normal = np.mean(normals[cluster_face_indices], axis=0)
            cluster_normal = cluster_normal / np.linalg.norm(cluster_normal)
            origin = np.mean(cluster_centers, axis=0)
            
            areas = mesh.compute_cell_sizes()["Area"]
            total_area = np.sum(areas[cluster_face_indices])
            
            confidence = self._calculate_plane_confidence(
                len(cluster_face_indices), len(centers), cluster_normal, normals[cluster_face_indices]
            )
            
            return PlaneInfo(
                origin=tuple(origin),
                normal=tuple(cluster_normal),
                area=float(total_area),
                face_indices=cluster_face_indices.tolist(),
                confidence=confidence,
                detection_method="clustering_fallback"
            )
        except Exception as e:
            logger.error(f"Clustering fallback failed: {e}")
            return None
    
    def _cluster_normals_sklearn(self, normals: np.ndarray, 
                                angle_threshold: float = 5.0) -> Dict[int, np.ndarray]:
        """
        Cluster normals using AgglomerativeClustering.
        Much more robust than grid-based binning.
        """
        try:
            # Normalize normals
            norms = np.linalg.norm(normals, axis=1, keepdims=True)
            norms[norms < 1e-10] = 1.0
            normals_norm = normals / norms
            
            # Downsample for speed if too many faces
            n_samples = len(normals)
            if n_samples > 5000:
                indices = np.random.choice(n_samples, 5000, replace=False)
                sample_normals = normals_norm[indices]
            else:
                indices = np.arange(n_samples)
                sample_normals = normals_norm
                
            # Distance threshold: 1 - cos(angle)
            # For 5 degrees: cos(5) = 0.99619 -> dist = 0.0038
            dist_threshold = 1.0 - np.cos(np.radians(angle_threshold))
            
            # Use cosine distance for clustering
            clustering = AgglomerativeClustering(
                n_clusters=None,
                distance_threshold=dist_threshold,
                metric='cosine',
                linkage='average'
            )
            labels = clustering.fit_predict(sample_normals)
            
            # Map back to clusters
            clusters = {}
            for i, label in enumerate(labels):
                if label not in clusters:
                    clusters[label] = []
                clusters[label].append(indices[i])
            
            # If we downsampled, we should assign remaining points (nearest neighbor)
            # For now, simplistic approach: just use what we have or re-run on full set if critical
            # In production: k-NN assignment for non-samples
            
            return {k: np.array(v) for k, v in clusters.items()}
            
        except Exception as e:
            logger.warning(f"Sklearn clustering failed: {e}, falling back to simple")
            return self._cluster_normals_simple(normals, angle_threshold)

    def _cluster_normals_simple(self, normals: np.ndarray, 
                               angle_threshold: float = 10.0) -> Dict[int, np.ndarray]:
        """
        Cluster normals by similar direction (Simple Grid/Binning).
        """
        # Normalize normals
        norms = np.linalg.norm(normals, axis=1, keepdims=True)
        norms[norms < 1e-10] = 1.0
        normals_norm = normals / norms
        
        threshold_cos = np.cos(np.radians(angle_threshold))
        
        clusters = {}
        used = set()
        
        # Simple greedy clustering
        # Iterate and group neighbors
        # This is slow O(N^2) worst case - should use Grid Binning in production
        # Implementation simplified for backup
        
        # Use simple quantization
        for i in range(len(normals)):
            if i in used:
                continue
            
            # Find all compatible
            ref = normals_norm[i]
            sim = np.dot(normals_norm, ref)
            matches = np.where(sim > threshold_cos)[0]
            
            # Only take matches not used
            # Actually with greedy, we can overlap, but let's be strict
            new_matches = [idx for idx in matches if idx not in used]
            
            if new_matches:
                cluster_id = len(clusters)
                clusters[cluster_id] = np.array(new_matches)
                used.update(new_matches)
                
        return clusters
    
    def _calculate_plane_confidence(self, cluster_size: int, total_faces: int,
                                   mean_normal: np.ndarray, 
                                   cluster_normals: np.ndarray) -> float:
        """Calculate confidence for plane detection."""
        # Factor 1: Size ratio (larger = more confident)
        size_ratio = cluster_size / total_faces if total_faces > 0 else 0
        size_score = min(1.0, size_ratio * 2)  # 50% of faces = 1.0
        
        # Factor 2: Normal consistency
        normal_deviations = 1.0 - np.dot(cluster_normals, mean_normal)
        consistency_score = 1.0 - np.mean(normal_deviations)
        
        # Weighted combination
        confidence = (
            size_score * 0.6 +
            consistency_score * 0.4
        )
        
        return float(np.clip(confidence, 0.0, 1.0))
    
    def _detect_holes(self, mesh, base_plane: Optional[PlaneInfo]) -> List[HoleInfo]:
        """
        Detect holes in the mesh.
        """
        holes = []
        
        try:
            # Get face centers and normals
            centers = mesh.cell_centers().points
            normals = mesh.cell_normals
            
            # Find potential cylindrical faces
            # optimization: Exclude base plane faces
            excluded_indices = set()
            if base_plane:
                excluded_indices.update(base_plane.face_indices)
            
            cylindrical_candidates = self._find_cylindrical_faces(
                mesh, centers, normals
            )
            
            # Filter candidates
            cylindrical_candidates = [
                idx for idx in cylindrical_candidates 
                if idx not in excluded_indices
            ]
            
            logger.info(f"Found {len(cylindrical_candidates)} cylindrical candidates after filtering planars")
            
            # Group candidates into holes
            hole_groups = self._group_cylindrical_faces(cylindrical_candidates, centers)
            
            for group_idx, face_indices in hole_groups.items():
                try:
                    hole = self._fit_hole_to_faces(mesh, face_indices, centers, base_plane)
                    if hole and hole.is_valid:
                        holes.append(hole)
                        logger.debug(f"Hole {len(holes)}: r={hole.radius:.2f}, "
                                    f"depth={hole.depth:.2f}, conf={hole.confidence:.2f}")
                except Exception as e:
                    logger.debug(f"Failed to fit hole to group {group_idx}: {e}")
                    continue
            
        except Exception as e:
            logger.error(f"Hole detection failed: {e}")
        
        return holes
    
    def _detect_holes_via_edges(self, mesh, base_plane: Optional[PlaneInfo]) -> List[HoleInfo]:
        """
        Detect holes by analyzing feature edge loops.
        Much more robust for clean CAD meshes than face clustering.
        """
        holes = []
        try:
            # 1. Extract feature edges
            # angle=30 is standard for sharp edges
            edges = mesh.extract_feature_edges(
                feature_angle=30.0,
                boundary_edges=True,
                non_manifold_edges=False,
                manifold_edges=False
            )
            
            if edges.n_cells == 0:
                return []
                
            # 2. Extract Loops
            # Convert lines to adjacency graph
            lines_cells = edges.lines.reshape(-1, 3)[:, 1:] # Skip size param
            points = edges.points
            
            loops = self._extract_edge_loops(lines_cells)
            logger.info(f"Extracted {len(loops)} edge loops from feature edges")
            
            # 3. Filter Circular Loops
            circular_loops = []
            for loop_indices in loops:
                is_circ, params = self._is_circular_loop(loop_indices, points)
                if is_circ:
                    circular_loops.append(params) # (center, normal, radius)
            
            logger.info(f"Found {len(circular_loops)} circular loops")
            
            # 4. Pair Loops to form Cylinders/Holes
            # A hole usually has 2 loops (top/bottom) or 1 loop (blind/surface)
            # We group by Axis and Radius
            
            # Simple greedy grouping
            used_loops = set()
            
            for i in range(len(circular_loops)):
                if i in used_loops: continue
                
                c1, n1, r1 = circular_loops[i]
                
                # Look for partner
                best_partner = -1
                
                for j in range(i + 1, len(circular_loops)):
                    if j in used_loops: continue
                    
                    c2, n2, r2 = circular_loops[j]
                    
                    # Check radius similarity
                    if abs(r1 - r2) > 0.1 * r1: continue # 10% diff
                    
                    # Check normal alignment (should be parallel or anti-parallel)
                    if abs(np.dot(n1, n2)) < 0.9: continue
                    
                    # Check coaxial alignment
                    # Vector between centers should be parallel to normal
                    center_vec = c2 - c1
                    dist = np.linalg.norm(center_vec)
                    
                    if dist < 0.1: # Same position (duplicate?)
                        continue
                        
                    center_dir = center_vec / dist
                    if abs(np.dot(center_dir, n1)) < 0.9: continue
                    
                    best_partner = j
                    break
                
                if best_partner != -1:
                    # Found a Through Hole!
                    c2, n2, r2 = circular_loops[best_partner]
                    
                    # Average parameters
                    avg_radius = (r1 + r2) / 2
                    axis = n1
                    if np.dot(axis, c2 - c1) < 0: axis = -axis # Point towards c2
                    
                    depth = np.linalg.norm(c2 - c1)
                    center = (c1 + c2) / 2
                    
                    # Check base plane alignment
                    if base_plane:
                         # Holes usually perpendicular to base or parallel
                         pass
                    
                    hole = HoleInfo(
                        center=tuple(center),
                        radius=float(avg_radius),
                        depth=float(depth),
                        axis=tuple(axis),
                        confidence=0.95, # High confidence for edge match
                        detection_method="edge_loop_pair"
                    )
                    holes.append(hole)
                    used_loops.add(i)
                    used_loops.add(best_partner)
                    
                else:
                    # Single Loop - Blind Hole or just a Circle
                    # We assume it's a hole with some default depth or check geometry
                    # For V1.stl, holes might be single loops if other side is obscured?
                    # Or maybe we just add it with lower confidence
                    
                    # Heuristic: If normal is perpendicular to Base Plane, it's a hole on the plane.
                    hole = HoleInfo(
                        center=tuple(c1),
                        radius=float(r1),
                        depth=float(r1)*2, # Guess depth
                        axis=tuple(n1),
                        confidence=0.6,
                        detection_method="single_edge_loop"
                    )
                    holes.append(hole)
                    used_loops.add(i)

        except Exception as e:
            logger.error(f"Edge-based hole detection failed: {e}")
            
        return holes

    def _extract_edge_loops(self, lines: np.ndarray) -> List[List[int]]:
        """Extract closed loops from lines array."""
        try:
            from collections import defaultdict
            adj = defaultdict(list)
            for i, (u, v) in enumerate(lines):
                adj[u].append((v, i))
                adj[v].append((u, i))
                
            visited_edges = set()
            loops = []
            
            for i, (u, v) in enumerate(lines):
                if i in visited_edges: continue
                
                path = [u]
                curr = v
                path_edges = {i}
                
                while True:
                    path.append(curr)
                    neighbors = adj[curr]
                    
                    # Find unvisited active edge
                    next_step = None
                    for n_node, n_edge in neighbors:
                        if n_edge in path_edges: continue
                        
                        # Stop at junctions? Simple holes have deg=2
                        # If deg > 2, logic is complex. 
                        # We just pick first valid, assuming simple loops.
                        next_step = (n_node, n_edge)
                        break
                    
                    if next_step:
                        n_node, n_edge = next_step
                        path_edges.add(n_edge)
                        curr = n_node
                        
                        if curr == path[0]: # Closed
                            visited_edges.update(path_edges)
                            loops.append(path)
                            break
                    else:
                        visited_edges.update(path_edges)
                        break # Dead end
            return loops
        except Exception as e:
            logger.error(f"Loop extraction error: {e}")
            return []

    def _is_circular_loop(self, loop_indices: List[int], points: np.ndarray) -> Tuple[bool, Any]:
        """Check if loop is circular."""
        try:
           pts = points[loop_indices]
           if len(pts) < 10: return False, None # Too few points
           
           # 1. Planarity (SVD)
           centroid = np.mean(pts, axis=0)
           centered = pts - centroid
           U, S, Vt = np.linalg.svd(centered)
           normal = Vt[-1]
           
           # Check thickness (smallest singular value)
           # S values are sqrt of eigenvalues. 
           # Ratio of smallest to largest gives flatness.
           if S[0] > 0 and S[-1]/S[0] > 0.05: return False, None # Not planar
           
           # 2. Circularity
           dists = np.linalg.norm(centered, axis=1)
           mean_r = np.mean(dists)
           std_r = np.std(dists)
           
           if std_r / mean_r < 0.1: # 10% deviation
               return True, (centroid, normal, mean_r)
               
           return False, None
        except:
           return False, None
    
    def _merge_holes(self, holes1: List[HoleInfo], holes2: List[HoleInfo]) -> List[HoleInfo]:
        """Merge two lists of holes, preferring the second list (edge-based)."""
        merged = []
        if holes2:
            merged.extend(holes2)
        
        if not holes1:
            return merged
            
        for h1 in holes1:
            # Check if duplicate in merged
            is_dup = False
            for h2 in merged:
                dist = np.linalg.norm(np.array(h1.center) - np.array(h2.center))
                # If centers are close and radii are similar
                if dist < h1.radius and abs(h1.radius - h2.radius) < h1.radius * 0.5:
                     is_dup = True
                     break
            
            if not is_dup:
                merged.append(h1)
                
        return merged
    
    def _find_cylindrical_faces(self, mesh, centers: np.ndarray, 
                                normals: np.ndarray) -> List[int]:
        """
        Find faces that could be part of a cylinder.
        """
        candidates = []
        n_faces = len(centers)
        
        # Optimization: Try to use curvature if available in PyVista
        # Otherwise use simple normal heuristic
        
        # Simple heuristic:
        # Cylinders have curvature in one direction only.
        # This is hard to detect locally without curvature filter.
        # Fallback: Detect if normal is perpendicular to Principal Direction of global mesh? No.
        
        # We'll stick to the existing heuristic but allow more tolerance
        # Ideally: Use discrete curvatures
        try:
            # if mesh has 'Mean_Curvature', use it
            if 'Mean_Curvature' in mesh.point_data:
                # Map to cells
                pass 
                
            # Basic geometric check
            # This needs spatial queries which are expensive
            # For now, assumes we are looking for holes roughly aligned with World Z or X/Y
            # OR we check relative to local neighborhood.
            pass
            
            # Reusing original logic for now as 'find candidates'
            # Enhanced logic:
            # Check adjacent faces. If angle is large (>20 deg) and edges are shared?
            # Actually, `mesh_converter` uses region segmentation first.
            # We will assume `surface_segmenter` logic is superior but too complex to fully inline here.
            # We stick to a simplified check:
            
            # Return all faces for now to let grouping/fitting do the work? Too slow.
            # Let's assume input is simple or used mesh quality checker to filter.
            
            # Using the mock implementation from Plan
            for i in range(n_faces):
                candidates.append(i) # ! Placeholder to test robust fitting
                
        except Exception as e:
            logger.debug(f"Cylindrical face detection failed: {e}")
            
        return list(range(n_faces)) # Placeholder: try fitting on clusters
    
    def _group_cylindrical_faces(self, candidates: List[int], 
                                 centers: np.ndarray) -> Dict[int, np.ndarray]:
        """Group cylindrical faces by proximity."""
        if not candidates:
            return {}
        
        # If we have too many candidates (loop above returned all), we MUST cluster
        if len(candidates) > 5000:
             # Just take a subset or use grid
             candidates = candidates[:5000]
             
        candidate_centers = centers[candidates]
        
        if HAS_SKLEARN:
            from sklearn.cluster import DBSCAN
            # Determine suitable epsilon based on mesh scale
            db = DBSCAN(eps=5.0, min_samples=3).fit(candidate_centers)
            labels = db.labels_
        else:
            # Simple distance clustering
            return {0: np.array(candidates)}
            
        groups = {}
        for i, label in enumerate(labels):
            if label == -1: continue
            if label not in groups: groups[label] = []
            groups[label].append(candidates[i])
            
        return {k: np.array(v) for k, v in groups.items()}
    
    def _fit_hole_to_faces(self, mesh, face_indices: np.ndarray,
                          centers: np.ndarray,
                          base_plane: Optional[PlaneInfo]) -> Optional[HoleInfo]:
        """
        Fit a hole to a group of faces.
        
        Enhanced with PCA and Circle Fitting.
        """
        if len(face_indices) < 10: # Need enough points for cylinder
            return None
        
        try:
            face_centers = centers[face_indices]
            
            # 1. Determine Axis via PCA
            # For a cylinder shell, largest variance is not necessarily axis (it's a ring)
            # Actually for a tube:
            # - Axis 1 & 2: Circle plane (similar eigenvalues)
            # - Axis 3: Tube height (if long) OR Thickness (if short ring)
            
            # Better: Fit plane to points -> Normal is axis (if hole is cut in planar surface)
            # OR SVD on centered points.
            
            centroid = np.mean(face_centers, axis=0)
            centered = face_centers - centroid
            
            if HAS_SKLEARN:
                pca = PCA(n_components=3)
                pca.fit(centered)
                # Components are sorted by variance.
                # If it's a hole (ring-like), points lie on cylinder surface.
                # If hole is short (ring), min variance direction is radial? No.
                
                # Robust approach from mesh_converter:
                # 1. Estimate normal from average face normal (if they curve around, avg might be 0)
                # 2. But for a hole, normals point "inward" to axis.
                #    So they all intersect the axis.
                
                # Let's try to find vector perpendicular to all normals?
                face_normals = mesh.cell_normals[face_indices]
                
                # SVD on normals matrix n x 3
                # The null space of normals matrix is the cylinder axis!
                # i.e. dot(n, axis) ~ 0
                U, S, Vt = np.linalg.svd(face_normals, full_matrices=False)
                axis = Vt[-1] # Direction with least variance in normals = perpedicular to all normals
                
            else:
                # Fallback: use average of abs normals? bad.
                # Fallback: Assume Z axis if aligned
                axis = np.array([0., 0., 1.])

            axis = axis / np.linalg.norm(axis)
            
            # Check axis alignment with base plane normal (holes usually distinct)
            if base_plane:
                dot = abs(np.dot(axis, np.array(base_plane.normal)))
                if dot < 0.8: # Not aligned
                    # Maybe it's a cross-hole.
                    pass
                else:
                    # Align direction
                    if np.dot(axis, base_plane.normal) < 0:
                        axis = -axis

            # 2. Project to 2D plane perpendicular to axis
            # Create basis
            z_axis = axis
            if abs(z_axis[0]) < 0.9:
                x_axis = np.cross(z_axis, [1, 0, 0])
            else:
                x_axis = np.cross(z_axis, [0, 1, 0])
            x_axis /= np.linalg.norm(x_axis)
            y_axis = np.cross(z_axis, x_axis)
            
            # Project
            u = np.dot(centered, x_axis)
            v = np.dot(centered, y_axis)
            h = np.dot(centered, z_axis) # height
            
            # 3. Fit Circle in 2D (u,v)
            # Simple least squares: (u-uc)^2 + (v-vc)^2 = R^2
            # u^2 + v^2 - 2u*uc - 2v*vc + (uc^2+vc^2-R^2) = 0
            # A*x = B
            # A = [2u, 2v, 1]
            # x = [uc, vc, C]
            # B = u^2 + v^2
            
            A = np.column_stack((2*u, 2*v, np.ones_like(u)))
            B = u**2 + v**2
            result, _, _, _ = np.linalg.lstsq(A, B, rcond=None)
            uc, vc, C = result
            
            radius = np.sqrt(C + uc**2 + vc**2)
            
            # Valid radius?
            if radius < self.MIN_HOLE_RADIUS or radius > self.MAX_HOLE_RADIUS:
                return None
            
            # 4. Refine Center
            center_offset = uc * x_axis + vc * y_axis
            center = centroid + center_offset
            
            # Project center back to 'start' of hole using depth/base plane?
            # For now keep it at centroid level or adjust to base plane surface
            if base_plane:
                # Move center to lie on base plane surface (intersection of axis line and plane)
                # Line: P(t) = C + t*A
                # Plane: (P - P0) . N = 0
                # (C + tA - P0) . N = 0 => t = (P0 - C).N / (A.N)
                p0 = np.array(base_plane.origin)
                pn = np.array(base_plane.normal)
                
                denom = np.dot(axis, pn)
                if abs(denom) > 1e-6:
                    t = np.dot(p0 - center, pn) / denom
                    center = center + t * axis
            
            # 5. Calculate Depth
            min_h, max_h = np.min(h), np.max(h)
            depth = max_h - min_h
            if depth < self.MIN_HOLE_DEPTH: 
                depth = self.MIN_HOLE_DEPTH

            # 6. Confidence
            # Calculate residual error of circle fit
            # distances from center in 2D
            dists = np.sqrt((u - uc)**2 + (v - vc)**2)
            residuals = np.abs(dists - radius)
            mean_error = np.mean(residuals)
            
            # Confidence score
            confidence = 1.0 - min(1.0, mean_error / (radius * 0.2)) # 20% tolerance
            
            validation_data = {
                "face_count": len(face_indices),
                "residual_mean": float(mean_error),
                "radius_std": float(np.std(dists)),
            }
            
            hole = HoleInfo(
                center=tuple(center),
                radius=float(radius),
                depth=float(depth),
                axis=tuple(axis),
                face_indices=face_indices.tolist(),
                confidence=float(confidence),
                detection_method="pca_lsq",
                validation_data=validation_data,
                fallback_hints={
                    "alternative_axes": [],
                    "radius_range": (float(radius * 0.9), float(radius * 1.1)),
                }
            )
            
            return hole
            
        except Exception as e:
            logger.debug(f"Hole fitting failed: {e}")
            return None
    
    def _detect_edges(self, mesh) -> List[EdgeInfo]:
        """
        Detect sharp/feature edges.
        """
        edges = []
        try:
            # Feature Edges: Boundary (open) + Feature (sharp)
            # angle defaults to 30 deg
            feature_edges = mesh.extract_feature_edges(
                feature_angle=30.0,
                boundary_edges=True,
                non_manifold_edges=False, 
                manifold_edges=False 
            )
            
            if feature_edges.n_cells > 0:
                pts = feature_edges.points.tolist()
                
                # In a real impl, we would separate into connected chains?
                # For now just one blob
                edge_info = EdgeInfo(
                    feature_type="feature_edges",
                    points=pts, 
                    type="sharp",
                    length=0.0 
                )
                edges.append(edge_info)
                
        except Exception as e:
            logger.warning(f"Feature edge detection failed (VTK/PyVista issue?): {e}")
            
        return edges

    def _detect_pockets_simple(self, mesh, 
                               base_plane: Optional[PlaneInfo]) -> List[PocketInfo]:
        """
        Simple pocket detection.
        """
        pockets = []
        try:
            logger.debug("Pocket detection not fully implemented")
        except Exception as e:
            logger.error(f"Pocket detection failed: {e}")
        
        return pockets
    
    def _calculate_overall_confidence(self, analysis: STLFeatureAnalysis) -> STLFeatureAnalysis:
        """Calculate overall confidence score."""
        scores = []
        
        # Base plane confidence
        if analysis.base_plane:
            scores.append(analysis.base_plane.confidence)
        
        # Hole confidences
        for hole in analysis.holes:
            scores.append(hole.confidence)
        
        # If no features detected, confidence is 0
        if not scores:
            analysis.overall_confidence = 0.0
            return analysis
        
        # Weighted average: base plane is 40%, holes are 60%
        if analysis.base_plane:
            base_score = analysis.base_plane.confidence * 0.4
            hole_scores = [h.confidence for h in analysis.holes]
            hole_avg = np.mean(hole_scores) if hole_scores else 0.0
            analysis.overall_confidence = base_score + hole_avg * 0.6
        else:
            analysis.overall_confidence = np.mean(scores)
        
        return analysis
    
    def quick_analyze(self, mesh_path: str) -> Dict[str, Any]:
        """Quick analysis returning only essential info."""
        analysis = self.analyze(mesh_path)
        
        return {
            "path": mesh_path,
            "valid": analysis.mesh_quality.is_valid if analysis.mesh_quality else False,
            "holes_found": len(analysis.holes),
            "pockets_found": len(analysis.pockets),
            "overall_confidence": analysis.overall_confidence,
            "needs_review": analysis.requires_user_review,
            "duration_ms": analysis.duration_ms,
        }


# Convenience function
def analyze_stl(mesh_path: str, 
                quality_checker: Optional[MeshQualityChecker] = None) -> STLFeatureAnalysis:
    """Quick analysis of STL file."""
    analyzer = STLFeatureAnalyzer(quality_checker)
    return analyzer.analyze(mesh_path)
