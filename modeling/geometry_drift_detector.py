"""
PI-008: Geometry Drift Early Detection

Detects when small numerical errors accumulate during modeling operations
and cause unexpected behavior. Provides baseline capture, drift measurement,
and threshold-based validation.
"""

from dataclasses import dataclass, field
from typing import List, Optional, Tuple, Dict, Any
import math
import logging

from OCP.TopoDS import TopoDS_Shape
from OCP.BRepAdaptor import BRepAdaptor_Surface, BRepAdaptor_Curve
from OCP.BRepTools import BRepTools
from OCP.Bnd import Bnd_Box
from OCP.BRepBndLib import BRepBndLib
from OCP.GProp import GProp_GProps
from OCP.BRepGProp import BRepGProp
from OCP.TopExp import TopExp_Explorer
from OCP.TopAbs import TopAbs_VERTEX, TopAbs_FACE, TopAbs_EDGE
from OCP.BRep import BRep_Tool
from OCP.gp import gp_Pnt, gp_Vec

logger = logging.getLogger(__name__)


@dataclass
class DriftMetrics:
    """Stores drift measurements between current and baseline geometry.
    
    Attributes:
        vertex_drift: Maximum vertex position change in mm
        normal_drift: Maximum normal deviation in radians
        area_drift: Surface area change as percentage (0.0-1.0)
        volume_drift: Volume change as percentage (0.0-1.0)
        edge_count_delta: Change in edge count
        face_count_delta: Change in face count
        vertex_count_delta: Change in vertex count
        is_valid: Whether the geometry is still valid B-Rep
        timestamp: When these metrics were captured
    """
    vertex_drift: float = 0.0
    normal_drift: float = 0.0
    area_drift: float = 0.0
    volume_drift: float = 0.0
    edge_count_delta: int = 0
    face_count_delta: int = 0
    vertex_count_delta: int = 0
    is_valid: bool = True
    timestamp: float = 0.0
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert metrics to dictionary for serialization."""
        return {
            "vertex_drift": self.vertex_drift,
            "normal_drift": self.normal_drift,
            "area_drift": self.area_drift,
            "volume_drift": self.volume_drift,
            "edge_count_delta": self.edge_count_delta,
            "face_count_delta": self.face_count_delta,
            "vertex_count_delta": self.vertex_count_delta,
            "is_valid": self.is_valid,
            "timestamp": self.timestamp,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "DriftMetrics":
        """Create DriftMetrics from dictionary."""
        return cls(
            vertex_drift=data.get("vertex_drift", 0.0),
            normal_drift=data.get("normal_drift", 0.0),
            area_drift=data.get("area_drift", 0.0),
            volume_drift=data.get("volume_drift", 0.0),
            edge_count_delta=data.get("edge_count_delta", 0),
            face_count_delta=data.get("face_count_delta", 0),
            vertex_count_delta=data.get("vertex_count_delta", 0),
            is_valid=data.get("is_valid", True),
            timestamp=data.get("timestamp", 0.0),
        )


@dataclass
class DriftBaseline:
    """Stores baseline geometry state for drift comparison.
    
    Captures the essential geometric properties of a solid at a point
    in time, allowing subsequent measurements to detect drift.
    """
    vertex_positions: List[Tuple[float, float, float]] = field(default_factory=list)
    face_normals: List[Tuple[float, float, float]] = field(default_factory=list)
    surface_area: float = 0.0
    volume: float = 0.0
    edge_count: int = 0
    face_count: int = 0
    vertex_count: int = 0
    bounding_box: Tuple[float, float, float, float, float, float] = (0, 0, 0, 0, 0, 0)
    shape_hash: str = ""
    timestamp: float = 0.0
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert baseline to dictionary for serialization."""
        return {
            "vertex_positions": self.vertex_positions,
            "face_normals": self.face_normals,
            "surface_area": self.surface_area,
            "volume": self.volume,
            "edge_count": self.edge_count,
            "face_count": self.face_count,
            "vertex_count": self.vertex_count,
            "bounding_box": self.bounding_box,
            "shape_hash": self.shape_hash,
            "timestamp": self.timestamp,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "DriftBaseline":
        """Create DriftBaseline from dictionary."""
        return cls(
            vertex_positions=[tuple(p) for p in data.get("vertex_positions", [])],
            face_normals=[tuple(n) for n in data.get("face_normals", [])],
            surface_area=data.get("surface_area", 0.0),
            volume=data.get("volume", 0.0),
            edge_count=data.get("edge_count", 0),
            face_count=data.get("face_count", 0),
            vertex_count=data.get("vertex_count", 0),
            bounding_box=tuple(data.get("bounding_box", (0, 0, 0, 0, 0, 0))),
            shape_hash=data.get("shape_hash", ""),
            timestamp=data.get("timestamp", 0.0),
        )


@dataclass
class DriftThresholds:
    """Configurable thresholds for drift detection.
    
    Values represent the maximum acceptable drift before a warning
    or error is generated.
    """
    vertex_max: float = 1e-6  # Maximum vertex position drift in mm
    normal_max: float = 1e-4  # Maximum normal deviation in radians
    area_max: float = 0.01    # Maximum area change (1%)
    volume_max: float = 0.01  # Maximum volume change (1%)
    topology_max: int = 0     # Maximum topology count change
    
    @classmethod
    def from_tolerances(cls) -> "DriftThresholds":
        """Create thresholds from centralized Tolerances config."""
        try:
            from config.tolerances import Tolerances
            return cls(
                vertex_max=Tolerances.DRIFT_VERTEX_MAX,
                normal_max=Tolerances.DRIFT_NORMAL_MAX,
                area_max=Tolerances.DRIFT_AREA_MAX,
                volume_max=Tolerances.DRIFT_VOLUME_MAX,
                topology_max=Tolerances.DRIFT_TOPOLOGY_MAX,
            )
        except ImportError:
            logger.warning("Could not import Tolerances, using defaults")
            return cls()


class GeometryDriftDetector:
    """Detects geometry drift during modeling operations.
    
    This class provides methods to:
    - Capture baseline geometry state
    - Detect drift between current and baseline geometry
    - Validate drift against configurable thresholds
    - Generate warnings when drift exceeds acceptable limits
    
    Usage:
        detector = GeometryDriftDetector()
        baseline = detector.capture_baseline(solid)
        # ... perform operations ...
        metrics = detector.detect_drift(solid, baseline)
        if not detector.is_drift_acceptable(metrics):
            warnings = detector.get_drift_warnings(metrics)
            for warning in warnings:
                logger.warning(warning)
    """
    
    def __init__(self, thresholds: Optional[DriftThresholds] = None):
        """Initialize the drift detector.
        
        Args:
            thresholds: Custom drift thresholds. If None, uses defaults
                       from config/tolerances.py.
        """
        self.thresholds = thresholds or DriftThresholds.from_tolerances()
        self._baseline_cache: Dict[str, DriftBaseline] = {}
    
    def capture_baseline(self, solid: TopoDS_Shape, key: str = "") -> DriftBaseline:
        """Capture baseline geometry state for later comparison.
        
        Args:
            solid: The OCP shape to capture
            key: Optional key for caching the baseline
            
        Returns:
            DriftBaseline containing the captured state
        """
        import time
        
        baseline = DriftBaseline()
        baseline.timestamp = time.time()
        
        # Capture topology counts
        baseline.vertex_count = self._count_topo(solid, TopAbs_VERTEX)
        baseline.edge_count = self._count_topo(solid, TopAbs_EDGE)
        baseline.face_count = self._count_topo(solid, TopAbs_FACE)
        
        # Capture vertex positions (sample up to 1000 vertices)
        baseline.vertex_positions = self._capture_vertex_positions(solid, max_vertices=1000)
        
        # Capture face normals (sample up to 100 faces)
        baseline.face_normals = self._capture_face_normals(solid, max_faces=100)
        
        # Capture global properties
        props = GProp_GProps()
        BRepGProp.VolumeProperties_s(solid, props)
        baseline.volume = props.Mass()
        
        BRepGProp.SurfaceProperties_s(solid, props)
        baseline.surface_area = props.Mass()
        
        # Capture bounding box
        bbox = Bnd_Box()
        BRepBndLib.Add_s(solid, bbox)
        xmin, ymin, zmin, xmax, ymax, zmax = bbox.Get()
        baseline.bounding_box = (xmin, ymin, zmin, xmax, ymax, zmax)
        
        # Generate shape hash for quick comparison
        baseline.shape_hash = self._compute_shape_hash(solid)
        
        # Cache if key provided
        if key:
            self._baseline_cache[key] = baseline
            logger.debug(f"Captured baseline '{key}': V={baseline.volume:.6f}, "
                        f"A={baseline.surface_area:.6f}, "
                        f"F={baseline.face_count}, E={baseline.edge_count}")
        
        return baseline
    
    def detect_drift(self, solid: TopoDS_Shape, baseline: DriftBaseline) -> DriftMetrics:
        """Detect drift between current solid and baseline.
        
        Args:
            solid: The current OCP shape
            baseline: The baseline state to compare against
            
        Returns:
            DriftMetrics containing the measured drift
        """
        import time
        
        metrics = DriftMetrics()
        metrics.timestamp = time.time()
        
        # Check validity first
        metrics.is_valid = self._check_validity(solid)
        if not metrics.is_valid:
            logger.warning("Geometry is invalid B-Rep")
            return metrics
        
        # Capture current state
        current = self.capture_baseline(solid)
        
        # Calculate topology deltas
        metrics.vertex_count_delta = current.vertex_count - baseline.vertex_count
        metrics.edge_count_delta = current.edge_count - baseline.edge_count
        metrics.face_count_delta = current.face_count - baseline.face_count
        
        # Calculate vertex drift
        metrics.vertex_drift = self._calculate_vertex_drift(
            current.vertex_positions, 
            baseline.vertex_positions
        )
        
        # Calculate normal drift
        metrics.normal_drift = self._calculate_normal_drift(
            current.face_normals,
            baseline.face_normals
        )
        
        # Calculate area drift (percentage)
        if baseline.surface_area > 0:
            metrics.area_drift = abs(current.surface_area - baseline.surface_area) / baseline.surface_area
        else:
            metrics.area_drift = 0.0 if current.surface_area == 0 else float('inf')
        
        # Calculate volume drift (percentage)
        if baseline.volume > 0:
            metrics.volume_drift = abs(current.volume - baseline.volume) / baseline.volume
        else:
            metrics.volume_drift = 0.0 if current.volume == 0 else float('inf')
        
        logger.debug(f"Drift detected: vertex={metrics.vertex_drift:.2e}, "
                    f"normal={metrics.normal_drift:.2e}, "
                    f"area={metrics.area_drift:.4%}, "
                    f"volume={metrics.volume_drift:.4%}")
        
        return metrics
    
    def is_drift_acceptable(self, metrics: DriftMetrics, 
                            thresholds: Optional[DriftThresholds] = None) -> bool:
        """Check if drift metrics are within acceptable thresholds.
        
        Args:
            metrics: The drift metrics to validate
            thresholds: Custom thresholds (uses instance thresholds if None)
            
        Returns:
            True if all drift values are within thresholds
        """
        if thresholds is None:
            thresholds = self.thresholds
        
        if not metrics.is_valid:
            return False
        
        # Check vertex drift
        if metrics.vertex_drift > thresholds.vertex_max:
            logger.debug(f"Vertex drift {metrics.vertex_drift:.2e} exceeds threshold {thresholds.vertex_max:.2e}")
            return False
        
        # Check normal drift
        if metrics.normal_drift > thresholds.normal_max:
            logger.debug(f"Normal drift {metrics.normal_drift:.2e} exceeds threshold {thresholds.normal_max:.2e}")
            return False
        
        # Check area drift
        if metrics.area_drift > thresholds.area_max:
            logger.debug(f"Area drift {metrics.area_drift:.4%} exceeds threshold {thresholds.area_max:.4%}")
            return False
        
        # Check volume drift
        if metrics.volume_drift > thresholds.volume_max:
            logger.debug(f"Volume drift {metrics.volume_drift:.4%} exceeds threshold {thresholds.volume_max:.4%}")
            return False
        
        # Check topology changes
        if abs(metrics.face_count_delta) > thresholds.topology_max:
            logger.debug(f"Face count delta {metrics.face_count_delta} exceeds threshold {thresholds.topology_max}")
            return False
        
        if abs(metrics.edge_count_delta) > thresholds.topology_max:
            logger.debug(f"Edge count delta {metrics.edge_count_delta} exceeds threshold {thresholds.topology_max}")
            return False
        
        return True
    
    def get_drift_warnings(self, metrics: DriftMetrics,
                          thresholds: Optional[DriftThresholds] = None) -> List[str]:
        """Generate warning messages for drift values exceeding thresholds.
        
        Args:
            metrics: The drift metrics to analyze
            thresholds: Custom thresholds (uses instance thresholds if None)
            
        Returns:
            List of warning message strings
        """
        if thresholds is None:
            thresholds = self.thresholds
        
        warnings = []
        
        if not metrics.is_valid:
            warnings.append("Geometry is invalid B-Rep - cannot measure drift")
            return warnings
        
        if metrics.vertex_drift > thresholds.vertex_max:
            warnings.append(
                f"Vertex drift {metrics.vertex_drift:.2e}mm exceeds threshold "
                f"{thresholds.vertex_max:.2e}mm"
            )
        
        if metrics.normal_drift > thresholds.normal_max:
            warnings.append(
                f"Normal deviation {metrics.normal_drift:.2e}rad exceeds threshold "
                f"{thresholds.normal_max:.2e}rad"
            )
        
        if metrics.area_drift > thresholds.area_max:
            warnings.append(
                f"Surface area drift {metrics.area_drift:.2%} exceeds threshold "
                f"{thresholds.area_max:.2%}"
            )
        
        if metrics.volume_drift > thresholds.volume_max:
            warnings.append(
                f"Volume drift {metrics.volume_drift:.2%} exceeds threshold "
                f"{thresholds.volume_max:.2%}"
            )
        
        if abs(metrics.face_count_delta) > thresholds.topology_max:
            warnings.append(
                f"Face count changed by {metrics.face_count_delta} "
                f"(threshold: {thresholds.topology_max})"
            )
        
        if abs(metrics.edge_count_delta) > thresholds.topology_max:
            warnings.append(
                f"Edge count changed by {metrics.edge_count_delta} "
                f"(threshold: {thresholds.topology_max})"
            )
        
        return warnings
    
    def get_cached_baseline(self, key: str) -> Optional[DriftBaseline]:
        """Retrieve a cached baseline by key.
        
        Args:
            key: The cache key used when capturing the baseline
            
        Returns:
            The cached baseline, or None if not found
        """
        return self._baseline_cache.get(key)
    
    def clear_cached_baseline(self, key: str) -> bool:
        """Remove a cached baseline.
        
        Args:
            key: The cache key to remove
            
        Returns:
            True if the baseline was removed, False if not found
        """
        if key in self._baseline_cache:
            del self._baseline_cache[key]
            return True
        return False
    
    def clear_all_cache(self) -> None:
        """Clear all cached baselines."""
        self._baseline_cache.clear()
    
    # --- Private helper methods ---
    
    def _count_topo(self, shape: TopoDS_Shape, topo_type) -> int:
        """Count topology elements of a specific type."""
        explorer = TopExp_Explorer(shape, topo_type)
        count = 0
        while explorer.More():
            count += 1
            explorer.Next()
        return count
    
    def _capture_vertex_positions(self, shape: TopoDS_Shape, 
                                   max_vertices: int = 1000) -> List[Tuple[float, float, float]]:
        """Capture vertex positions for drift comparison."""
        positions = []
        explorer = TopExp_Explorer(shape, TopAbs_VERTEX)
        
        while explorer.More() and len(positions) < max_vertices:
            vertex = explorer.Current()
            pnt = BRep_Tool.Pnt_s(vertex)
            positions.append((pnt.X(), pnt.Y(), pnt.Z()))
            explorer.Next()
        
        return positions
    
    def _capture_face_normals(self, shape: TopoDS_Shape,
                              max_faces: int = 100) -> List[Tuple[float, float, float]]:
        """Capture face normals for drift comparison."""
        normals = []
        explorer = TopExp_Explorer(shape, TopAbs_FACE)
        
        while explorer.More() and len(normals) < max_faces:
            face = explorer.Current()
            adaptor = BRepAdaptor_Surface(face)
            
            # Get normal at center of face
            u = (adaptor.FirstUParameter() + adaptor.LastUParameter()) / 2
            v = (adaptor.FirstVParameter() + adaptor.LastVParameter()) / 2
            
            try:
                pnt = adaptor.Value(u, v)
                # Calculate normal using partial derivatives
                du = gp_Vec()
                dv = gp_Vec()
                adaptor.D1(u, v, pnt, du, dv)
                normal = du.Crossed(dv)
                if normal.Magnitude() > 1e-10:
                    normal.Normalize()
                    normals.append((normal.X(), normal.Y(), normal.Z()))
            except Exception:
                # Skip faces where normal calculation fails
                pass
            
            explorer.Next()
        
        return normals
    
    def _calculate_vertex_drift(self, current: List[Tuple[float, float, float]],
                                baseline: List[Tuple[float, float, float]]) -> float:
        """Calculate maximum vertex position drift.
        
        Uses nearest-neighbor matching to handle topology changes.
        """
        if not baseline or not current:
            return 0.0
        
        max_drift = 0.0
        
        # For each baseline vertex, find nearest current vertex
        for bx, by, bz in baseline:
            min_dist = float('inf')
            for cx, cy, cz in current:
                dist = math.sqrt((cx - bx)**2 + (cy - by)**2 + (cz - bz)**2)
                min_dist = min(min_dist, dist)
            max_drift = max(max_drift, min_dist)
        
        # Also check for vertices in current not in baseline
        for cx, cy, cz in current:
            min_dist = float('inf')
            for bx, by, bz in baseline:
                dist = math.sqrt((cx - bx)**2 + (cy - by)**2 + (cz - bz)**2)
                min_dist = min(min_dist, dist)
            max_drift = max(max_drift, min_dist)
        
        return max_drift
    
    def _calculate_normal_drift(self, current: List[Tuple[float, float, float]],
                                baseline: List[Tuple[float, float, float]]) -> float:
        """Calculate maximum normal deviation in radians.
        
        Uses nearest-neighbor matching based on normal direction.
        """
        if not baseline or not current:
            return 0.0
        
        max_drift = 0.0
        
        # For each baseline normal, find most similar current normal
        for bn in baseline:
            min_angle = float('inf')
            for cn in current:
                angle = self._angle_between_vectors(bn, cn)
                min_angle = min(min_angle, angle)
            max_drift = max(max_drift, min_angle)
        
        return max_drift
    
    def _angle_between_vectors(self, v1: Tuple[float, float, float],
                               v2: Tuple[float, float, float]) -> float:
        """Calculate angle between two vectors in radians."""
        dot = v1[0]*v2[0] + v1[1]*v2[1] + v1[2]*v2[2]
        
        # Clamp to valid range for acos
        dot = max(-1.0, min(1.0, dot))
        
        return math.acos(dot)
    
    def _check_validity(self, shape: TopoDS_Shape) -> bool:
        """Check if shape is a valid B-Rep."""
        if shape.IsNull():
            return False
        
        # Use BRepTools to check for geometric validity
        # This is a basic check - more sophisticated validation could be added
        try:
            return BRepTools.IsValid_s(shape)
        except Exception:
            return False
    
    def _compute_shape_hash(self, shape: TopoDS_Shape) -> str:
        """Compute a hash string for quick shape comparison."""
        import hashlib
        
        # Combine topology counts and geometric properties
        props = GProp_GProps()
        BRepGProp.VolumeProperties_s(shape, props)
        volume = props.Mass()
        
        BRepGProp.SurfaceProperties_s(shape, props)
        area = props.Mass()
        
        data = (
            f"{self._count_topo(shape, TopAbs_VERTEX)}:"
            f"{self._count_topo(shape, TopAbs_EDGE)}:"
            f"{self._count_topo(shape, TopAbs_FACE)}:"
            f"{volume:.10f}:"
            f"{area:.10f}"
        )
        
        return hashlib.md5(data.encode()).hexdigest()[:16]


# Module-level convenience functions

_detector_instance: Optional[GeometryDriftDetector] = None


def get_detector() -> GeometryDriftDetector:
    """Get or create the global drift detector instance."""
    global _detector_instance
    if _detector_instance is None:
        _detector_instance = GeometryDriftDetector()
    return _detector_instance


def capture_baseline(solid: TopoDS_Shape, key: str = "") -> DriftBaseline:
    """Convenience function to capture baseline using global detector."""
    return get_detector().capture_baseline(solid, key)


def detect_drift(solid: TopoDS_Shape, baseline: DriftBaseline) -> DriftMetrics:
    """Convenience function to detect drift using global detector."""
    return get_detector().detect_drift(solid, baseline)


def is_drift_acceptable(metrics: DriftMetrics) -> bool:
    """Convenience function to check drift acceptability using global detector."""
    return get_detector().is_drift_acceptable(metrics)


def get_drift_warnings(metrics: DriftMetrics) -> List[str]:
    """Convenience function to get drift warnings using global detector."""
    return get_detector().get_drift_warnings(metrics)
