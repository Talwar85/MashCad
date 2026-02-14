"""
STL Feature Analyzer for CAD Feature Detection.

Detects features from STL meshes with confidence scoring.
No external library modifications - only standard PyVista/numpy.
"""

import logging
import time
from dataclasses import dataclass, field
from typing import List, Optional, Tuple, Dict, Any, Callable
from pathlib import Path

import numpy as np

from .mesh_quality_checker import MeshQualityChecker, MeshQualityReport

logger = logging.getLogger(__name__)


@dataclass
class PlaneInfo:
    """Detected base plane."""
    feature_type: str = "base_plane"
    origin: Tuple[float, float, float] = (0.0, 0.0, 0.0)
    normal: Tuple[float, float, float] = (0.0, 0.0, 1.0)
    area: float = 0.0
    face_indices: List[int] = field(default_factory=list)
    
    # Confidence
    confidence: float = 0.0
    detection_method: str = "unknown"  # "largest_planar" | "best_fit" | "manual"
    
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


@dataclass
class STLFeatureAnalysis:
    """Complete feature analysis result."""
    mesh_path: str = ""
    mesh_quality: Optional[MeshQualityReport] = None
    
    # Detected features
    base_plane: Optional[PlaneInfo] = None
    holes: List[HoleInfo] = field(default_factory=list)
    pockets: List[PocketInfo] = field(default_factory=list)
    fillets: List[FilletInfo] = field(default_factory=list)
    
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
    
    No library changes - only standard PyVista/numpy functions.
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
            logger.info("Detecting holes...")
            analysis.holes = self._detect_holes(mesh, analysis.base_plane)
            
            # 4. Detect pockets (simplified version)
            logger.info("Detecting pockets...")
            analysis.pockets = self._detect_pockets_simple(mesh, analysis.base_plane)
            
            # 5. Calculate overall confidence
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
    
    def _detect_base_plane(self, mesh) -> Optional[PlaneInfo]:
        """
        Detect base plane (largest planar surface).
        
        Strategy:
        1. Compute face normals
        2. Cluster faces by normal direction
        3. Find largest cluster
        4. Fit plane to cluster
        """
        try:
            import pyvista as pv
            
            # Get face centers and normals
            centers = mesh.cell_centers().points
            normals = mesh.cell_normals
            
            if len(centers) == 0 or len(normals) == 0:
                logger.warning("No face centers or normals found")
                return None
            
            # Find dominant normal direction (base plane is usually large)
            # Use simple clustering: group by similar normals
            normal_clusters = self._cluster_normals(normals, angle_threshold=10.0)
            
            if not normal_clusters:
                logger.warning("Could not cluster normals")
                return None
            
            # Find largest cluster
            largest_cluster_idx = max(normal_clusters.keys(), 
                                     key=lambda k: len(normal_clusters[k]))
            largest_cluster = normal_clusters[largest_cluster_idx]
            
            # Get faces in cluster
            cluster_face_indices = largest_cluster
            cluster_centers = centers[cluster_face_indices]
            cluster_normal = np.mean(normals[cluster_face_indices], axis=0)
            cluster_normal = cluster_normal / np.linalg.norm(cluster_normal)
            
            # Fit plane
            origin = np.mean(cluster_centers, axis=0)
            
            # Calculate area (approximate from face sizes)
            areas = mesh.compute_cell_sizes()["Area"]
            total_area = np.sum(areas[cluster_face_indices])
            
            # Calculate confidence
            confidence = self._calculate_plane_confidence(
                len(cluster_face_indices), 
                len(centers),
                cluster_normal,
                normals[cluster_face_indices]
            )
            
            plane = PlaneInfo(
                origin=tuple(origin),
                normal=tuple(cluster_normal),
                area=float(total_area),
                face_indices=cluster_face_indices.tolist(),
                confidence=confidence,
                detection_method="largest_planar"
            )
            
            logger.info(f"Base plane detected: area={plane.area:.2f}, "
                       f"confidence={plane.confidence:.2f}")
            
            return plane
            
        except Exception as e:
            logger.error(f"Base plane detection failed: {e}")
            return None
    
    def _cluster_normals(self, normals: np.ndarray, 
                        angle_threshold: float = 10.0) -> Dict[int, np.ndarray]:
        """
        Cluster normals by similar direction.
        
        Args:
            normals: Array of normal vectors (N, 3)
            angle_threshold: Max angle difference in degrees
            
        Returns:
            Dict mapping cluster_id to array of indices
        """
        threshold_cos = np.cos(np.radians(angle_threshold))
        n_normals = len(normals)
        
        if n_normals == 0:
            return {}
        
        # Normalize normals
        normals_norm = normals / np.linalg.norm(normals, axis=1, keepdims=True)
        
        # Simple clustering: use first normal as reference, find similar ones
        # This is a simplified version - could use proper clustering for complex meshes
        clusters = {}
        used = set()
        
        for i in range(n_normals):
            if i in used:
                continue
            
            # Find all normals similar to this one
            similarity = np.dot(normals_norm, normals_norm[i])
            similar_indices = np.where(similarity > threshold_cos)[0]
            
            cluster_id = len(clusters)
            clusters[cluster_id] = similar_indices
            used.update(similar_indices)
        
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
        
        Strategy:
        1. Find cylindrical surfaces
        2. Check if they go through the base plane
        3. Validate hole parameters
        4. Calculate confidence
        """
        holes = []
        
        try:
            # Get face centers and normals
            centers = mesh.cell_centers().points
            normals = mesh.cell_normals
            
            # Find potential cylindrical faces
            cylindrical_candidates = self._find_cylindrical_faces(
                mesh, centers, normals
            )
            
            logger.info(f"Found {len(cylindrical_candidates)} cylindrical candidates")
            
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
    
    def _find_cylindrical_faces(self, mesh, centers: np.ndarray, 
                                normals: np.ndarray) -> List[int]:
        """
        Find faces that could be part of a cylinder.
        
        A cylindrical face has:
        - Normal perpendicular to radial direction from cylinder axis
        - Consistent curvature
        """
        candidates = []
        
        try:
            # Compute curvature (approximation)
            # For each face, check if normal points away from some center line
            # This is simplified - proper cylinder fitting would be more complex
            
            n_faces = len(centers)
            
            # Use face neighborhoods to detect curvature
            for i in range(n_faces):
                # Simple heuristic: faces with normals not aligned with 
                # the vector to mesh center might be cylindrical
                center_to_face = centers[i] - np.mean(centers, axis=0)
                center_to_face = center_to_face / (np.linalg.norm(center_to_face) + 1e-10)
                
                # If normal is perpendicular to radial direction, it might be cylindrical
                alignment = abs(np.dot(normals[i], center_to_face))
                
                if alignment < 0.3:  # Roughly perpendicular
                    candidates.append(i)
            
        except Exception as e:
            logger.debug(f"Cylindrical face detection failed: {e}")
        
        return candidates
    
    def _group_cylindrical_faces(self, candidates: List[int], 
                                 centers: np.ndarray) -> Dict[int, np.ndarray]:
        """Group cylindrical faces by proximity."""
        if not candidates:
            return {}
        
        # Simple grouping by spatial clustering
        candidate_centers = centers[candidates]
        
        # Use distance-based clustering
        groups = {}
        used = set()
        
        for i, idx in enumerate(candidates):
            if idx in used:
                continue
            
            center_i = candidate_centers[i]
            
            # Find all candidates within distance threshold
            distances = np.linalg.norm(candidate_centers - center_i, axis=1)
            nearby_mask = distances < 10.0  # 10mm threshold - should be relative to mesh size
            nearby_indices = np.array(candidates)[nearby_mask]
            
            group_id = len(groups)
            groups[group_id] = nearby_indices
            used.update(nearby_indices)
        
        return groups
    
    def _fit_hole_to_faces(self, mesh, face_indices: np.ndarray,
                          centers: np.ndarray,
                          base_plane: Optional[PlaneInfo]) -> Optional[HoleInfo]:
        """
        Fit a hole to a group of faces.
        
        Estimates:
        - Center (from face centers)
        - Radius (from spread of faces)
        - Axis (from face normals)
        - Depth (from extent along axis)
        """
        if len(face_indices) < 3:
            return None
        
        try:
            face_centers = centers[face_indices]
            
            # Estimate center as mean of face centers
            center = np.mean(face_centers, axis=0)
            
            # Estimate axis from face normals (should be roughly parallel)
            face_normals = mesh.cell_normals[face_indices]
            axis = np.mean(face_normals, axis=0)
            axis_norm = np.linalg.norm(axis)
            if axis_norm < 0.01:
                return None
            axis = axis / axis_norm
            
            # Estimate radius from distance of face centers to axis
            # Project centers onto plane perpendicular to axis
            center_to_faces = face_centers - center
            projections = center_to_faces - np.outer(
                np.dot(center_to_faces, axis), axis
            )
            distances = np.linalg.norm(projections, axis=1)
            radius = np.median(distances)
            
            if radius < self.MIN_HOLE_RADIUS or radius > self.MAX_HOLE_RADIUS:
                return None
            
            # Estimate depth from extent along axis
            axis_projections = np.dot(face_centers - center, axis)
            depth = np.max(axis_projections) - np.min(axis_projections)
            
            if depth < self.MIN_HOLE_DEPTH:
                depth = self.MIN_HOLE_DEPTH  # Minimum depth
            
            # Calculate confidence
            confidence = self._calculate_hole_confidence(
                face_indices, centers, radius, axis, face_normals, base_plane
            )
            
            # Validation data
            validation_data = {
                "face_count": len(face_indices),
                "radius_std": float(np.std(distances)),
                "axis_variance": float(np.var(np.dot(face_normals, axis))),
            }
            
            hole = HoleInfo(
                center=tuple(center),
                radius=float(radius),
                depth=float(depth),
                axis=tuple(axis),
                face_indices=face_indices.tolist(),
                confidence=confidence,
                detection_method="cylinder_fit",
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
    
    def _calculate_hole_confidence(self, face_indices: np.ndarray,
                                   centers: np.ndarray,
                                   radius: float,
                                   axis: np.ndarray,
                                   face_normals: np.ndarray,
                                   base_plane: Optional[PlaneInfo]) -> float:
        """
        Calculate confidence for hole detection.
        
        Factors:
        1. Cylinder fit quality (radius consistency)
        2. Plane connectivity (goes through base plane)
        3. Orientation (axis reasonable)
        4. Size plausibility
        """
        # Factor 1: Radius consistency
        face_centers = centers[face_indices]
        center = np.mean(face_centers, axis=0)
        center_to_faces = face_centers - center
        projections = center_to_faces - np.outer(np.dot(center_to_faces, axis), axis)
        distances = np.linalg.norm(projections, axis=1)
        radius_consistency = 1.0 - min(1.0, np.std(distances) / (radius + 0.001))
        
        # Factor 2: Normal consistency (cylinder normals should be perpendicular to axis)
        normal_alignment = np.abs(np.dot(face_normals, axis))
        normal_consistency = 1.0 - np.mean(normal_alignment)
        
        # Factor 3: Plane connectivity
        plane_connectivity = 0.5  # Default if no base plane
        if base_plane is not None:
            # Check if hole center projects onto base plane
            center_to_plane = np.dot(np.array(base_plane.origin) - center, 
                                    np.array(base_plane.normal))
            if abs(center_to_plane) < radius * 2:  # Within reasonable distance
                plane_connectivity = 0.9
            else:
                plane_connectivity = 0.3
        
        # Factor 4: Size plausibility
        size_score = 1.0
        if radius < 1.0 or radius > 50.0:
            size_score = 0.7
        
        # Weighted combination
        confidence = (
            radius_consistency * 0.35 +
            normal_consistency * 0.25 +
            plane_connectivity * 0.25 +
            size_score * 0.15
        )
        
        return float(np.clip(confidence, 0.0, 1.0))
    
    def _detect_pockets_simple(self, mesh, 
                               base_plane: Optional[PlaneInfo]) -> List[PocketInfo]:
        """
        Simple pocket detection.
        
        Strategy:
        1. Find depressed areas (faces pointing "inward")
        2. Group by proximity
        3. Estimate depth
        
        Note: This is a simplified version. Full pocket detection would require
        more sophisticated surface analysis.
        """
        pockets = []
        
        try:
            # For now, return empty list - pockets are complex
            # Would need proper surface segmentation
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
        """
        Quick analysis returning only essential info.
        
        Args:
            mesh_path: Path to STL file
            
        Returns:
            Dict with summary info
        """
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
    """
    Quick analysis of STL file.
    
    Args:
        mesh_path: Path to STL file
        quality_checker: Optional quality checker instance
        
    Returns:
        STLFeatureAnalysis
    """
    analyzer = STLFeatureAnalyzer(quality_checker)
    return analyzer.analyze(mesh_path)
