"""
MashCAD - Support Structure Estimation
=========================================

Estimates support volume for FDM 3D printing based on:
- Downward-facing faces (overhangs)
- Bridging capability (excludes bridges from support)
- Support contact area and volume

Support structures are needed when:
1. Face normal points downward (angle > critical from horizontal)
2. Face is NOT a bridge (self-supporting span)
3. No geometry exists below the face

Author: Claude (AP 1.3: Support Estimation)
Date: 2026-03-02
Branch: feature/tnp5
"""

from dataclasses import dataclass, field
from enum import Enum, auto
from typing import List, Dict, Any, Tuple, Optional, Set
from loguru import logger
import math


class SupportStrategy(Enum):
    """Support generation strategy."""
    NONE = "none"                       # No support needed
    TREE = "tree"                       # Tree supports (organic)
    LINEAR = "linear"                   # Linear/pillar supports
    GRID = "grid"                       # Grid/hatching supports
    BLOCK = "block"                     # Block/solid supports


@dataclass
class SupportRegion:
    """
    A region of the model that requires support.

    Represents a connected area of downward-facing faces
    that need support structures.
    """
    faces: List[int] = field(default_factory=list)  # Face indices

    # Bounding box of the region
    bbox_min: Tuple[float, float, float] = (0, 0, 0)
    bbox_max: Tuple[float, float, float] = (0, 0, 0)

    # Contact area (area touching the model)
    contact_area_mm2: float = 0.0

    # Estimated support volume
    support_volume_mm3: float = 0.0

    # Minimum Z height of this region
    min_z: float = 0.0
    max_z: float = 0.0

    # Region type
    is_bridge: bool = False
    bridge_span: float = 0.0


@dataclass
class SupportEstimate:
    """
    Complete support estimation for a part.

    Contains all support regions and summary statistics.
    """
    # Support regions
    regions: List[SupportRegion] = field(default_factory=list)

    # Summary statistics
    total_support_volume_mm3: float = 0.0
    total_contact_area_mm2: float = 0.0
    unsupported_area_mm2: float = 0.0  # Area that needs support
    bridged_area_mm2: float = 0.0        # Area that is self-supporting

    # Face-level classifications
    face_needs_support: Dict[int, bool] = field(default_factory=dict)
    face_is_bridge: Dict[int, bool] = field(default_factory=dict)

    # Configuration used
    critical_angle_deg: float = 45.0
    support_gap_mm: float = 0.2          # Gap between support and model
    support_density: float = 0.2         # 20% infill for supports

    # Analysis metadata
    analysis_time_ms: float = 0.0

    def get_summary(self) -> str:
        """Get human-readable summary."""
        lines = [
            f"Support Estimation:",
            f"  Total support volume: {self.total_support_volume_mm3:.0f} mm³",
            f"  Contact area: {self.total_contact_area_mm2:.0f} mm²",
            f"  Unsupported area: {self.unsupported_area_mm2:.0f} mm²",
            f"  Bridged (self-supporting) area: {self.bridged_area_mm2:.0f} mm²",
            f"  Support regions: {len(self.regions)}",
        ]
        return "\n".join(lines)

    def to_dict(self) -> dict:
        """Serialize for caching/UI."""
        return {
            'regions': [
                {
                    'faces': r.faces,
                    'bbox_min': r.bbox_min,
                    'bbox_max': r.bbox_max,
                    'contact_area_mm2': r.contact_area_mm2,
                    'support_volume_mm3': r.support_volume_mm3,
                    'min_z': r.min_z,
                    'max_z': r.max_z,
                    'is_bridge': r.is_bridge,
                    'bridge_span': r.bridge_span,
                }
                for r in self.regions
            ],
            'total_support_volume_mm3': self.total_support_volume_mm3,
            'total_contact_area_mm2': self.total_contact_area_mm2,
            'unsupported_area_mm2': self.unsupported_area_mm2,
            'bridged_area_mm2': self.bridged_area_mm2,
            'critical_angle_deg': self.critical_angle_deg,
            'support_gap_mm': self.support_gap_mm,
            'support_density': self.support_density,
            'analysis_time_ms': self.analysis_time_ms,
        }


class SupportEstimator:
    """
    Estimates support structures needed for 3D printing.

    Algorithm:
    1. Find all downward-facing faces (angle > critical)
    2. Exclude bridges using bridge classification
    3. Group adjacent faces into support regions
    4. Calculate volume for each region based on height and area
    """

    # Default support parameters
    DEFAULT_CRITICAL_ANGLE = 45.0  # Degrees from vertical
    DEFAULT_SUPPORT_GAP = 0.2      # mm gap between support and model
    DEFAULT_SUPPORT_DENSITY = 0.2  # 20% infill

    def __init__(
        self,
        critical_angle_deg: float = DEFAULT_CRITICAL_ANGLE,
        support_gap_mm: float = DEFAULT_SUPPORT_GAP,
        support_density: float = DEFAULT_SUPPORT_DENSITY,
        max_bridge_span_mm: float = 50.0
    ):
        """
        Initialize the support estimator.

        Args:
            critical_angle_deg: Angle threshold for overhang detection
            support_gap_mm: Gap between support structure and model
            support_density: Density of support infill (0-1)
            max_bridge_span_mm: Maximum span for self-supporting bridges
        """
        self.critical_angle_deg = critical_angle_deg
        self.support_gap_mm = support_gap_mm
        self.support_density = support_density
        self.max_bridge_span_mm = max_bridge_span_mm
        self.critical_angle_rad = math.radians(critical_angle_deg)

    def estimate(
        self,
        solid: Any,
        use_bridge_classification: bool = True
    ) -> SupportEstimate:
        """
        Estimate support requirements for a solid.

        Args:
            solid: Build123d Solid or OCP TopoDS_Shape
            use_bridge_classification: Whether to use bridge-aware classification

        Returns:
            SupportEstimate with complete support analysis
        """
        import time
        from OCP.TopExp import TopExp_Explorer
        from OCP.TopAbs import TopAbs_FACE
        from OCP.TopoDS import TopoDS
        from OCP.BRepGProp import BRepGProp
        from OCP.GProp import GProp_GProps
        from OCP.BRepAdaptor import BRepAdaptor_Surface
        from OCP.BRepLProp import BRepLProp_SLProps
        from OCP.TopAbs import TopAbs_REVERSED
        from OCP.Bnd import Bnd_Box
        from OCP.BRepBndLib import BRepBndLib

        start_time = time.perf_counter()

        estimate = SupportEstimate(
            critical_angle_deg=self.critical_angle_deg,
            support_gap_mm=self.support_gap_mm,
            support_density=self.support_density
        )

        # Extract OCP shape
        ocp_shape = solid.wrapped if hasattr(solid, 'wrapped') else solid

        if ocp_shape is None:
            return estimate

        try:
            # Get bounding box
            bbox = Bnd_Box()
            BRepBndLib.Add_s(ocp_shape, bbox)
            xmin, ymin, zmin, xmax, ymax, zmax = bbox.Get()

            # Collect face data
            face_data = []
            unsupported_faces = []
            bridge_faces = []

            explorer = TopExp_Explorer(ocp_shape, TopAbs_FACE)
            face_idx = 0

            while explorer.More():
                face = TopoDS.Face_s(explorer.Current())

                # Get face data
                face_props = GProp_GProps()
                BRepGProp.SurfaceProperties_s(face, face_props)
                area = face_props.Mass()
                center = face_props.CentreOfMass()

                # Get normal and check if downward-facing
                normal = (0, 0, 1)
                angle_from_vertical = 0
                is_downward = False

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
                        angle_from_vertical = math.degrees(math.acos(min(1.0, max(-1.0, nz))))
                        is_downward = nz < 0  # Pointing down

                except Exception:
                    pass

                # Check if face is on build plate
                is_on_build_plate = abs(center.Z() - zmin) < 0.5

                face_info = {
                    'index': face_idx,
                    'area': area,
                    'center': (center.X(), center.Y(), center.Z()),
                    'normal': normal,
                    'angle_from_vertical': angle_from_vertical,
                    'is_downward': is_downward,
                    'is_on_build_plate': is_on_build_plate,
                }

                face_data.append(face_info)

                # Check if face needs support
                needs_support = False
                is_bridge = False

                if is_downward and not is_on_build_plate:
                    if angle_from_vertical > self.critical_angle_deg:
                        # Critical overhang - needs support
                        needs_support = True
                        unsupported_faces.append(face_idx)
                    elif abs(angle_from_vertical) < 15:  # Near horizontal
                        # Could be a bridge - check
                        is_bridge = self._check_if_bridge(
                            face_info, face_data, zmin, face_idx
                        )

                        if not is_bridge:
                            needs_support = True
                            unsupported_faces.append(face_idx)
                        else:
                            bridge_faces.append(face_idx)

                estimate.face_needs_support[face_idx] = needs_support
                estimate.face_is_bridge[face_idx] = is_bridge

                face_idx += 1
                explorer.Next()

            # Calculate support statistics
            for idx in unsupported_faces:
                estimate.unsupported_area_mm2 += face_data[idx]['area']

            for idx in bridge_faces:
                estimate.bridged_area_mm2 += face_data[idx]['area']

            # Group faces into support regions
            if unsupported_faces:
                estimate.regions = self._group_support_regions(
                    unsupported_faces, face_data, zmin, zmax
                )

            # Calculate volumes
            for region in estimate.regions:
                region_height = region.max_z - region.min_z
                # Support volume = contact area × height × density
                region.support_volume_mm3 = (
                    region.contact_area_mm2 * region_height * self.support_density
                )
                estimate.total_support_volume_mm3 += region.support_volume_mm3
                estimate.total_contact_area_mm2 += region.contact_area_mm2

        except Exception as e:
            logger.exception(f"Support estimation failed: {e}")

        estimate.analysis_time_ms = (time.perf_counter() - start_time) * 1000

        logger.debug(f"Support estimation completed in {estimate.analysis_time_ms:.1f}ms: "
                    f"volume={estimate.total_support_volume_mm3:.0f}mm³, "
                    f"regions={len(estimate.regions)}")

        return estimate

    def _check_if_bridge(
        self,
        face_info: dict,
        all_faces: list,
        zmin: float,
        current_idx: int
    ) -> bool:
        """
        Check if a face is a bridge (self-supporting span).

        Simple heuristic: a horizontal face with supporting geometry below.
        """
        face_center = face_info['center']
        face_z = face_center[2]

        # Count supporting faces below
        support_count = 0
        max_span = 0.0

        for i, other in enumerate(all_faces):
            if i == current_idx:
                continue

            other_z = other['center'][2]

            # Check if other face is below
            if other_z < face_z - 1.0:
                # Check horizontal distance
                dx = other['center'][0] - face_center[0]
                dy = other['center'][1] - face_center[1]
                dist = math.sqrt(dx*dx + dy*dy)

                if dist < 50:  # Within potential span range
                    # Check if other face could provide support (points up)
                    if other['normal'][2] > 0.5:
                        support_count += 1
                        max_span = max(max_span, dist)

        # Bridge if has sufficient supports and span is within limits
        return support_count >= 2 and max_span <= self.max_bridge_span_mm

    def _group_support_regions(
        self,
        face_indices: List[int],
        face_data: List[dict],
        zmin: float,
        zmax: float
    ) -> List[SupportRegion]:
        """
        Group adjacent faces into support regions.

        Simple grouping based on proximity - faces that are close
        to each other are grouped into the same region.
        """
        if not face_indices:
            return []

        regions = []
        used = set()

        # Group by proximity (simple clustering)
        proximity_threshold = 20.0  # mm

        for idx in face_indices:
            if idx in used:
                continue

            # Start new region
            region_faces = [idx]
            used.add(idx)

            face = face_data[idx]
            region_min = face['center']
            region_max = face['center']

            # Find nearby faces
            for other_idx in face_indices:
                if other_idx in used or other_idx == idx:
                    continue

                other = face_data[other_idx]

                # Check distance
                dx = other['center'][0] - face['center'][0]
                dy = other['center'][1] - face['center'][1]
                dz = other['center'][2] - face['center'][2]
                dist = math.sqrt(dx*dx + dy*dy + dz*dz)

                if dist < proximity_threshold:
                    region_faces.append(other_idx)
                    used.add(other_idx)

                    # Update bbox
                    region_min = (
                        min(region_min[0], other['center'][0]),
                        min(region_min[1], other['center'][1]),
                        min(region_min[2], other['center'][2]),
                    )
                    region_max = (
                        max(region_max[0], other['center'][0]),
                        max(region_max[1], other['center'][1]),
                        max(region_max[2], other['center'][2]),
                    )

            # Calculate region properties
            contact_area = sum(face_data[i]['area'] for i in region_faces)

            region = SupportRegion(
                faces=region_faces,
                bbox_min=region_min,
                bbox_max=region_max,
                contact_area_mm2=contact_area,
                min_z=region_min[2],
                max_z=region_max[2],
            )

            regions.append(region)

        return regions


def estimate_support(
    solid: Any,
    critical_angle_deg: float = 45.0,
    support_gap_mm: float = 0.2,
    support_density: float = 0.2,
    max_bridge_span_mm: float = 50.0
) -> SupportEstimate:
    """
    Convenience function to estimate support for a solid.

    Args:
        solid: Build123d Solid or OCP TopoDS_Shape
        critical_angle_deg: Angle threshold for overhang detection
        support_gap_mm: Gap between support structure and model
        support_density: Density of support infill (0-1)
        max_bridge_span_mm: Maximum span for self-supporting bridges

    Returns:
        SupportEstimate with complete support analysis
    """
    estimator = SupportEstimator(
        critical_angle_deg=critical_angle_deg,
        support_gap_mm=support_gap_mm,
        support_density=support_density,
        max_bridge_span_mm=max_bridge_span_mm
    )

    return estimator.estimate(solid)


def calculate_support_score(estimate: SupportEstimate) -> float:
    """
    Calculate a score for how much support is needed.

    Lower is better (0 = no support needed).

    Score is based on:
    - Support volume (primary factor)
    - Contact area
    - Number of regions (more regions = more complex)

    Returns:
        Score between 0 and 1, where 0 is no support needed
    """
    if estimate.total_support_volume_mm3 <= 0:
        return 0.0

    # Normalize factors (heuristic)
    # 1000 mm³ of support is considered "significant"
    volume_factor = min(1.0, estimate.total_support_volume_mm3 / 1000.0)

    # 1000 mm² contact area is "significant"
    area_factor = min(1.0, estimate.total_contact_area_mm2 / 1000.0)

    # More regions = slightly worse (complexity penalty)
    region_factor = min(1.0, len(estimate.regions) / 10.0)

    # Weighted combination
    score = 0.6 * volume_factor + 0.3 * area_factor + 0.1 * region_factor

    return min(1.0, score)
