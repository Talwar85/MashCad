"""
MashCAD - Bridge Analysis Module
====================================

Distinguishes between bridges (self-supporting horizontal spans) and
overhangs (faces that need support structures).

Bridges are a special case in FDM 3D printing:
- They can span gaps without support due to layer-by-layer deposition
- They have limits based on material and printer settings
- Recognizing bridges avoids unnecessary support generation

Author: Claude (AP 1.2: Bridge-Aware Classification)
Date: 2026-03-02
Branch: feature/tnp5
"""

from dataclasses import dataclass, field
from enum import Enum, auto
from typing import List, Dict, Any, Tuple, Optional, Set
from loguru import logger
import math


class BridgeType(Enum):
    """Type of bridge geometry."""
    FULL_BRIDGE = "full_bridge"           # Classic bridge between two supports
    CANTILEVER = "cantilever"             # Supported on one side only
    ISLAND_BRIDGE = "island_bridge"       # Small island overhang
    NOT_BRIDGE = "not_bridge"             # Regular overhang


@dataclass
class BridgeClassification:
    """
    Classification result for a single face.

    Indicates whether a downward-facing face is a bridge
    (self-supporting) or requires support structures.
    """
    face_index: int
    is_bridge: bool = False
    bridge_type: BridgeType = BridgeType.NOT_BRIDGE

    # Geometric properties
    span_mm: float = 0.0                  # Distance between supports
    support_count: int = 0                # Number of supporting edges
    area_mm2: float = 0.0                  # Face area

    # Normal information
    normal: Tuple[float, float, float] = (0, 0, 0)
    angle_from_horizontal_deg: float = 0.0

    # Support edges (indices of connected faces that provide support)
    supporting_face_indices: List[int] = field(default_factory=list)

    def __post_init__(self):
        """Validate classification."""
        if not self.is_bridge:
            self.bridge_type = BridgeType.NOT_BRIDGE

    def to_dict(self) -> dict:
        """Serialize for caching/UI."""
        return {
            'face_index': self.face_index,
            'is_bridge': self.is_bridge,
            'bridge_type': self.bridge_type.value,
            'span_mm': self.span_mm,
            'support_count': self.support_count,
            'area_mm2': self.area_mm2,
            'normal': self.normal,
            'angle_from_horizontal_deg': self.angle_from_horizontal_deg,
            'supporting_face_indices': self.supporting_face_indices,
        }


@dataclass
class BridgeAnalysisResult:
    """
    Complete bridge analysis for a part.

    Contains classification for all relevant faces and
    summary statistics.
    """
    classifications: Dict[int, BridgeClassification] = field(default_factory=dict)

    # Summary statistics
    total_faces: int = 0
    bridge_faces: int = 0
    overhang_faces: int = 0
    total_bridge_area_mm2: float = 0.0
    total_overhang_area_mm2: float = 0.0

    # Maximum bridge span found
    max_bridge_span_mm: float = 0.0

    # Analysis metadata
    material: str = 'PLA'
    max_bridge_span_mm: float = 50.0  # Material-specific limit
    horizontal_tolerance_deg: float = 15.0  # Max angle from horizontal
    analysis_time_ms: float = 0.0

    def get_summary(self) -> str:
        """Get human-readable summary."""
        lines = [
            f"Bridge Analysis ({self.material}):",
            f"  Total faces analyzed: {self.total_faces}",
            f"  Bridge faces: {self.bridge_faces} ({self.total_bridge_area_mm2:.0f} mm²)",
            f"  Overhang faces: {self.overhang_faces} ({self.total_overhang_area_mm2:.0f} mm²)",
            f"  Max bridge span: {self.max_bridge_span_mm:.1f} mm",
            f"  Max allowed span: {self.max_bridge_span_mm:.1f} mm",
        ]
        return "\n".join(lines)

    def to_dict(self) -> dict:
        """Serialize for caching/UI."""
        return {
            'classifications': {
                idx: cls.to_dict()
                for idx, cls in self.classifications.items()
            },
            'total_faces': self.total_faces,
            'bridge_faces': self.bridge_faces,
            'overhang_faces': self.overhang_faces,
            'total_bridge_area_mm2': self.total_bridge_area_mm2,
            'total_overhang_area_mm2': self.total_overhang_area_mm2,
            'max_bridge_span_mm': self.max_bridge_span_mm,
            'material': self.material,
            'max_bridge_span_mm': self.max_bridge_span_mm,
            'horizontal_tolerance_deg': self.horizontal_tolerance_deg,
            'analysis_time_ms': self.analysis_time_ms,
        }


class BridgeClassifier:
    """
    Classifies faces as bridges or overhangs.

    Algorithm:
    1. Find all downward-facing faces (angle from horizontal < tolerance)
    2. For each candidate face, find its edges
    3. Check which edges connect to supporting faces below
    4. Count supporting faces and measure span
    5. Classify based on support count and span length
    """

    # Material-specific bridge span limits (conservative values)
    MATERIAL_SPANS = {
        'PLA': 50.0,
        'ABS': 45.0,
        'PETG': 55.0,
        'TPU': 30.0,
        'NYLON': 40.0,
    }

    def __init__(
        self,
        material: str = 'PLA',
        max_span_mm: Optional[float] = None,
        horizontal_tolerance_deg: float = 15.0
    ):
        """
        Initialize the bridge classifier.

        Args:
            material: Material preset for bridge span limits
            max_span_mm: Override max bridge span (if None, uses material default)
            horizontal_tolerance_deg: Max angle from horizontal to consider as bridge
        """
        self.material = material
        self.horizontal_tolerance_deg = horizontal_tolerance_deg

        if max_span_mm is not None:
            self.max_span_mm = max_span_mm
        else:
            self.max_span_mm = self.MATERIAL_SPANS.get(material, 50.0)

        self.horizontal_tolerance_rad = math.radians(horizontal_tolerance_deg)

    def classify(
        self,
        solid: Any,
        critical_angle_deg: float = 45.0
    ) -> BridgeAnalysisResult:
        """
        Classify all faces in a solid as bridges or overhangs.

        Args:
            solid: Build123d Solid or OCP TopoDS_Shape
            critical_angle_deg: Angle threshold for downward-facing faces

        Returns:
            BridgeAnalysisResult with all classifications
        """
        import time
        from OCP.TopExp import TopExp_Explorer
        from OCP.TopAbs import TopAbs_FACE, TopAbs_EDGE
        from OCP.TopoDS import TopoDS
        from OCP.BRepGProp import BRepGProp
        from OCP.GProp import GProp_GProps
        from OCP.BRepAdaptor import BRepAdaptor_Surface
        from OCP.BRepLProp import BRepLProp_SLProps
        from OCP.TopAbs import TopAbs_REVERSED
        from OCP.BRep import BRep_Tool
        from OCP.TopExp import TopExp
        from OCP.TopTools import TopTools_IndexedDataMapOfShapeListOfShape
        from OCP.TopAbs import TopAbs_EDGE, TopAbs_FACE

        start_time = time.perf_counter()

        result = BridgeAnalysisResult(
            material=self.material,
            max_bridge_span_mm=self.max_span_mm,
            horizontal_tolerance_deg=self.horizontal_tolerance_deg
        )

        # Extract OCP shape
        ocp_shape = solid.wrapped if hasattr(solid, 'wrapped') else solid

        if ocp_shape is None:
            return result

        try:
            # Build face data structures
            face_list = []
            face_data = []

            explorer = TopExp_Explorer(ocp_shape, TopAbs_FACE)
            face_idx = 0

            while explorer.More():
                face = TopoDS.Face_s(explorer.Current())
                face_list.append(face)

                # Get face data
                face_props = GProp_GProps()
                BRepGProp.SurfaceProperties_s(face, face_props)
                area = face_props.Mass()
                center = face_props.CentreOfMass()

                # Get normal
                normal = (0, 0, 1)
                angle_from_horizontal = 0
                try:
                    adaptor = BRepAdaptor_Surface(face)
                    u_min = adaptor.FirstUParameter()
                    u_max = adaptor.LastUParameter()
                    v_min = adaptor.FirstVParameter()
                    v_max = adaptor.LastVParameter()

                    u_center = (u_min + u_max) / 2
                    v_center = (v_min + v_max) / 2

                    slprops = BRepLProp_SLProps(adaptor, u_center, v_center, 1, 0.01)

                    if slprops.IsNormalDefined():
                        n = slprops.Normal()
                        nx, ny, nz = n.X(), n.Y(), n.Z()

                        if face.Orientation() == TopAbs_REVERSED:
                            nx, ny, nz = -nx, -ny, -nz

                        normal = (nx, ny, nz)
                        # Angle from horizontal plane (0° = horizontal)
                        angle_from_horizontal = math.degrees(math.asin(min(1.0, max(-1.0, nz))))
                except Exception:
                    pass

                face_data.append({
                    'area': area,
                    'center': (center.X(), center.Y(), center.Z()),
                    'normal': normal,
                    'angle_from_horizontal': angle_from_horizontal,
                    'z_min': center.Z(),  # Simplified - use center for now
                    'z_max': center.Z(),
                })

                face_idx += 1
                explorer.Next()

            result.total_faces = face_idx

            # Build edge-face connectivity map
            edge_face_map = TopTools_IndexedDataMapOfShapeListOfShape()
            TopExp.MapShapesAndAncestors_s(ocp_shape, TopAbs_EDGE, TopAbs_FACE, edge_face_map)

            # Get bounding box for reference
            from OCP.Bnd import Bnd_Box
            from OCP.BRepBndLib import BRepBndLib
            bbox = Bnd_Box()
            BRepBndLib.Add_s(ocp_shape, bbox)
            _, _, zmin, _, _, zmax = bbox.Get()

            # Classify each face
            explorer = TopExp_Explorer(ocp_shape, TopAbs_FACE)
            face_idx = 0

            while explorer.More():
                face = TopoDS.Face_s(explorer.Current())
                data = face_data[face_idx]

                # Check if face is a bridge candidate (downward-facing, near horizontal)
                is_downward = data['normal'][2] < 0  # Pointing down
                is_near_horizontal = data['angle_from_horizontal'] < self.horizontal_tolerance_deg

                if is_downward and is_near_horizontal:
                    classification = self._classify_bridge_face(
                        face_idx=face_idx,
                        face=face,
                        face_data=data,
                        all_faces=face_list,
                        all_face_data=face_data,
                        zmin=zmin
                    )

                    result.classifications[face_idx] = classification

                    if classification.is_bridge:
                        result.bridge_faces += 1
                        result.total_bridge_area_mm2 += classification.area_mm2
                        result.max_bridge_span_mm = max(
                            result.max_bridge_span_mm,
                            classification.span_mm
                        )
                    else:
                        result.overhang_faces += 1
                        result.total_overhang_area_mm2 += classification.area_mm2

                elif is_downward and data['angle_from_horizontal'] > critical_angle_deg:
                    # Steep overhang - definitely needs support
                    result.overhang_faces += 1
                    result.total_overhang_area_mm2 += data['area']

                face_idx += 1
                explorer.Next()

        except Exception as e:
            logger.exception(f"Bridge classification failed: {e}")

        result.analysis_time_ms = (time.perf_counter() - start_time) * 1000

        logger.debug(f"Bridge analysis completed in {result.analysis_time_ms:.1f}ms: "
                    f"{result.bridge_faces} bridges, {result.overhang_faces} overhangs")

        return result

    def _classify_bridge_face(
        self,
        face_idx: int,
        face: Any,
        face_data: dict,
        all_faces: list,
        all_face_data: list,
        zmin: float
    ) -> BridgeClassification:
        """
        Classify a single face as bridge or overhang.

        A face is a bridge if:
        1. It has at least 2 supporting faces below
        2. The span between supports is within limits
        """
        face_center = face_data['center']
        face_z = face_center[2]
        supporting_faces = []

        # Check for supporting faces below by examining nearby faces
        for i, other_data in enumerate(all_face_data):
            if i == face_idx:
                continue

            # Check if other face is below and could provide support
            other_z = other_data['center'][2]
            if other_z < face_z - 1.0:  # At least 1mm below
                # Check horizontal distance
                dx = other_data['center'][0] - face_center[0]
                dy = other_data['center'][1] - face_center[1]
                horizontal_dist = math.sqrt(dx*dx + dy*dy)

                if horizontal_dist < 50:  # Within potential span range
                    # Check if other face points up (could provide support)
                    if other_data['normal'][2] > 0.5:  # Pointing up
                        supporting_faces.append(i)

        support_count = len(set(supporting_faces))

        # Compute span (max distance between supporting faces)
        span = 0.0
        if support_count >= 2:
            # Find max distance between supporting faces
            for i in range(len(supporting_faces)):
                for j in range(i + 1, len(supporting_faces)):
                    idx1, idx2 = supporting_faces[i], supporting_faces[j]
                    p1 = all_face_data[idx1]['center']
                    p2 = all_face_data[idx2]['center']
                    dx = p1[0] - p2[0]
                    dy = p1[1] - p2[1]
                    dist = math.sqrt(dx*dx + dy*dy)
                    span = max(span, dist)

        # Determine bridge type
        is_bridge = False
        bridge_type = BridgeType.NOT_BRIDGE

        if support_count >= 2 and span <= self.max_span_mm:
            is_bridge = True
            bridge_type = BridgeType.FULL_BRIDGE
        elif support_count == 1 and span <= self.max_span_mm / 2:
            is_bridge = True
            bridge_type = BridgeType.CANTILEVER
        elif face_data['area'] < 100:  # Small island
            is_bridge = True
            bridge_type = BridgeType.ISLAND_BRIDGE
            span = math.sqrt(face_data['area'])  # Approximate span as sqrt of area

        return BridgeClassification(
            face_index=face_idx,
            is_bridge=is_bridge,
            bridge_type=bridge_type,
            span_mm=span,
            support_count=support_count,
            area_mm2=face_data['area'],
            normal=face_data['normal'],
            angle_from_horizontal_deg=face_data['angle_from_horizontal'],
            supporting_face_indices=supporting_faces
        )


def classify_bridges(
    solid: Any,
    material: str = 'PLA',
    max_span_mm: Optional[float] = None,
    critical_angle_deg: float = 45.0
) -> BridgeAnalysisResult:
    """
    Convenience function to classify bridges in a solid.

    Args:
        solid: Build123d Solid or OCP TopoDS_Shape
        material: Material preset for bridge span limits
        max_span_mm: Override max bridge span
        critical_angle_deg: Angle threshold for downward-facing faces

    Returns:
        BridgeAnalysisResult with all classifications
    """
    classifier = BridgeClassifier(
        material=material,
        max_span_mm=max_span_mm
    )

    return classifier.classify(solid, critical_angle_deg)
