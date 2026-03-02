"""
MashCAD - Support Fin Generation
=================================

Generates support fin geometry for on-edge 3D printing.

Support fins are thin vertical walls that enable printing parts at
45° or 60° angles. They provide a temporary support surface that:
1. Breaks away easily from the finished part
2. Allows printing steep overhangs without supports
3. Improves surface quality on the "finned" side

Reference: https://www.printables.com/model/788155-support-fins

Author: Claude (AP 1.4: Support Fin Generation)
Date: 2026-03-02
Branch: feature/tnp5
"""

from dataclasses import dataclass, field
from enum import Enum, auto
from typing import List, Dict, Any, Tuple, Optional
from loguru import logger
import math


class FinOrientation(Enum):
    """Standard fin orientations for on-edge printing."""
    DEG_45 = 45      # 45° rotation - most common
    DEG_60 = 60      # 60° rotation - for steeper overhangs


@dataclass
class FinConfig:
    """Configuration for support fin generation."""
    # Fin geometry
    thickness_mm: float = 0.8           # Fin thickness (layer width)
    height_mm: float = 3.0              # Fin height above part
    spacing_mm: float = 5.0             # Distance between fins

    # Fin placement
    orientation: FinOrientation = FinOrientation.DEG_45
    offset_from_part_mm: float = 0.2    # Gap between fin and part

    # Fin bonding
    base_height_mm: float = 1.0         # Height of fin base on build plate
    top_chamfer_mm: float = 0.5         # Chamfer at top for easy removal

    # Performance
    min_overhang_angle_deg: float = 45.0  # Only fin overhangs steeper than this


@dataclass
class FinRegion:
    """
    A region where support fins should be generated.

    Defined by a boundary curve and orientation.
    """
    # Boundary of the region (points in XY plane)
    boundary_points: List[Tuple[float, float, float]] = field(default_factory=list)

    # Region properties
    length_mm: float = 0.0                # Length along the overhang
    width_mm: float = 0.0                 # Width of the overhang
    start_height_mm: float = 0.0          # Z height where fins start
    end_height_mm: float = 0.0            # Z height where fins end

    # Fin parameters for this region
    num_fins: int = 0
    fin_height_mm: float = 0.0

    # Orientation
    along_x: bool = True                  # True = fins along X, False = along Y


@dataclass
class FinProposal:
    """
    Complete proposal for support fins on a part.

    Contains all fin regions and can generate the actual geometry.
    """
    # Fin regions
    regions: List[FinRegion] = field(default_factory=list)

    # Configuration used
    config: FinConfig = field(default_factory=FinConfig)

    # Statistics
    total_fins: int = 0
    total_fin_volume_mm3: float = 0.0
    estimated_print_time_increase: float = 0.0  # Minutes

    # Metadata
    target_orientation: Tuple[float, float, float] = (0, 0, 0)  # Rotation axis
    target_angle_deg: float = 45.0
    requires_bed_rotation: bool = True

    analysis_time_ms: float = 0.0

    def get_summary(self) -> str:
        """Get human-readable summary."""
        lines = [
            f"Fin Proposal ({self.target_angle_deg}° rotation):",
            f"  Regions: {len(self.regions)}",
            f"  Total fins: {self.total_fins}",
            f"  Fin volume: {self.total_fin_volume_mm3:.0f} mm³",
            f"  Estimated time increase: {self.estimated_print_time_increase:.1f} min",
        ]
        return "\n".join(lines)


class FinGenerator:
    """
    Generates support fin geometry for on-edge printing.

    Algorithm:
    1. Identify steep overhangs (angle > 45° from horizontal)
    2. Group overhangs into fin regions
    3. Calculate optimal fin placement
    4. Generate fin geometry (can be added as separate body)
    """

    # Standard fin configurations
    DEFAULT_CONFIG_45 = FinConfig(
        thickness_mm=0.8,
        height_mm=3.0,
        spacing_mm=5.0,
        orientation=FinOrientation.DEG_45,
        min_overhang_angle_deg=45.0
    )

    DEFAULT_CONFIG_60 = FinConfig(
        thickness_mm=0.8,
        height_mm=2.0,
        spacing_mm=4.0,
        orientation=FinOrientation.DEG_60,
        min_overhang_angle_deg=60.0
    )

    def __init__(self, config: Optional[FinConfig] = None):
        """
        Initialize the fin generator.

        Args:
            config: Fin configuration (uses 45° default if None)
        """
        self.config = config or self.DEFAULT_CONFIG_45

    def analyze(
        self,
        solid: Any,
        orientation_angle_deg: float = 45.0
    ) -> FinProposal:
        """
        Analyze a solid and propose support fins.

        Args:
            solid: Build123d Solid or OCP TopoDS_Shape
            orientation_angle_deg: Target rotation angle (45 or 60)

        Returns:
            FinProposal with regions and statistics
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

        proposal = FinProposal(
            config=self.config,
            target_angle_deg=orientation_angle_deg,
            requires_bed_rotation=orientation_angle_deg > 0
        )

        # Extract OCP shape
        ocp_shape = solid.wrapped if hasattr(solid, 'wrapped') else solid

        if ocp_shape is None:
            return proposal

        try:
            # Get bounding box
            bbox = Bnd_Box()
            BRepBndLib.Add_s(ocp_shape, bbox)
            xmin, ymin, zmin, xmax, ymax, zmax = bbox.Get()

            # Find steep overhangs that could benefit from fins
            steep_overhangs = []

            explorer = TopExp_Explorer(ocp_shape, TopAbs_FACE)

            while explorer.More():
                face = TopoDS.Face_s(explorer.Current())

                # Get face data
                face_props = GProp_GProps()
                BRepGProp.SurfaceProperties_s(face, face_props)
                area = face_props.Mass()
                center = face_props.CentreOfMass()

                # Get normal
                normal = (0, 0, 1)
                angle_from_horizontal = 0
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
                        # Angle from horizontal (0° = horizontal, 90° = vertical)
                        angle_from_horizontal = math.degrees(math.asin(min(1.0, max(-1.0, nz))))
                        is_downward = nz < 0

                except Exception:
                    pass

                # Check if this is a steep overhang that could benefit from fins
                if is_downward and angle_from_horizontal > self.config.min_overhang_angle_deg:
                    # Not on build plate
                    if abs(center.Z() - zmin) > 1.0:
                        steep_overhangs.append({
                            'center': (center.X(), center.Y(), center.Z()),
                            'area': area,
                            'normal': normal,
                            'angle': angle_from_horizontal,
                            'z_height': center.Z(),
                        })

                explorer.Next()

            # Group overhangs into fin regions
            if steep_overhangs:
                proposal.regions = self._group_fin_regions(
                    steep_overhangs, (xmin, ymin, zmin), (xmax, ymax, zmax)
                )

                # Calculate statistics
                for region in proposal.regions:
                    region.num_fins = max(1, int(region.length_mm / self.config.spacing_mm))
                    region.fin_height_mm = self.config.height_mm

                    proposal.total_fins += region.num_fins

                    # Fin volume = thickness × height × length × num_fins
                    fin_volume = (
                        self.config.thickness_mm *
                        region.fin_height_mm *
                        region.length_mm *
                        region.num_fins
                    )
                    proposal.total_fin_volume_mm3 += fin_volume

                # Estimate time increase (rough heuristic: 1 mm³ ≈ 0.5 sec)
                proposal.estimated_print_time_increase = (
                    proposal.total_fin_volume_mm3 * 0.5 / 60
                )

        except Exception as e:
            logger.exception(f"Fin analysis failed: {e}")

        proposal.analysis_time_ms = (time.perf_counter() - start_time) * 1000

        logger.debug(f"Fin analysis completed in {proposal.analysis_time_ms:.1f}ms: "
                    f"regions={len(proposal.regions)}, fins={proposal.total_fins}")

        return proposal

    def _group_fin_regions(
        self,
        overhangs: List[dict],
        bbox_min: Tuple[float, float, float],
        bbox_max: Tuple[float, float, float]
    ) -> List[FinRegion]:
        """
        Group overhangs into fin regions.

        Creates regions based on the dominant orientation of overhangs.
        Fins run perpendicular to the overhang direction.
        """
        if not overhangs:
            return []

        regions = []

        # Sort overhangs by Z height
        sorted_overhangs = sorted(overhangs, key=lambda o: o['z_height'])

        # Group by proximity and orientation
        used = set()
        proximity_threshold = 20.0  # mm

        for i, overhang in enumerate(sorted_overhangs):
            if i in used:
                continue

            # Start new region
            region_overhangs = [overhang]
            used.add(i)

            # Find nearby overhangs
            for j, other in enumerate(sorted_overhangs):
                if j in used or j == i:
                    continue

                dx = other['center'][0] - overhang['center'][0]
                dy = other['center'][1] - overhang['center'][1]
                dz = other['z_height'] - overhang['z_height']
                dist = math.sqrt(dx*dx + dy*dy + dz*dz)

                if dist < proximity_threshold:
                    region_overhangs.append(other)
                    used.add(j)

            # Calculate region properties
            total_area = sum(o['area'] for o in region_overhangs)

            # Find bounding extent
            points = [o['center'] for o in region_overhangs]
            xs = [p[0] for p in points]
            ys = [p[1] for p in points]
            zs = [p[2] for p in points]

            # Determine dominant direction
            extent_x = max(xs) - min(xs)
            extent_y = max(ys) - min(ys)

            # Fins run along the longer dimension
            along_x = extent_x > extent_y

            length = extent_x if along_x else extent_y
            width = extent_y if along_x else extent_x

            region = FinRegion(
                boundary_points=[(p[0], p[1], p[2]) for p in points],
                length_mm=length,
                width_mm=width,
                start_height_mm=min(zs),
                end_height_mm=max(zs),
                along_x=along_x,
            )

            regions.append(region)

        return regions

    def generate_fin_geometry(
        self,
        proposal: FinProposal,
        bbox_min: Tuple[float, float, float],
        bbox_max: Tuple[float, float, float]
    ) -> List[Any]:
        """
        Generate the actual fin geometry as Build123d objects.

        Args:
            proposal: Fin proposal from analyze()
            bbox_min: Bounding box minimum of the part
            bbox_max: Bounding box maximum of the part

        Returns:
            List of Build123d Solid objects representing fins
        """
        from build123d import Box, Location

        fins = []

        for region in proposal.regions:
            num_fins = max(1, int(region.length_mm / self.config.spacing_mm))

            # Calculate fin positions
            if region.along_x:
                # Fins run along X
                start_pos = region.boundary_points[0] if region.boundary_points else (0, 0, 0)
                for i in range(num_fins):
                    offset = i * self.config.spacing_mm

                    fin = Box(
                        region.length_mm,
                        self.config.thickness_mm,
                        self.config.height_mm
                    )

                    # Position the fin
                    fin_pos = Location((
                        start_pos[0],
                        start_pos[1] + offset - region.width_mm / 2,
                        region.end_height_mm
                    ))

                    fins.append(fin.located(fin_pos))
            else:
                # Fins run along Y
                start_pos = region.boundary_points[0] if region.boundary_points else (0, 0, 0)
                for i in range(num_fins):
                    offset = i * self.config.spacing_mm

                    fin = Box(
                        self.config.thickness_mm,
                        region.length_mm,
                        self.config.height_mm
                    )

                    # Position the fin
                    fin_pos = Location((
                        start_pos[0] + offset - region.width_mm / 2,
                        start_pos[1],
                        region.end_height_mm
                    ))

                    fins.append(fin.located(fin_pos))

        return fins


def analyze_fins(
    solid: Any,
    orientation_angle_deg: float = 45.0,
    config: Optional[FinConfig] = None
) -> FinProposal:
    """
    Convenience function to analyze support fins for a solid.

    Args:
        solid: Build123d Solid or OCP TopoDS_Shape
        orientation_angle_deg: Target rotation angle (45 or 60)
        config: Fin configuration (uses default if None)

    Returns:
        FinProposal with regions and statistics
    """
    generator = FinGenerator(config)
    return generator.analyze(solid, orientation_angle_deg)


def generate_fins(
    solid: Any,
    proposal: FinProposal
) -> List[Any]:
    """
    Convenience function to generate fin geometry.

    Args:
        solid: Original part (for bounding box)
        proposal: Fin proposal from analyze_fins()

    Returns:
        List of Build123d Solid objects representing fins
    """
    from OCP.Bnd import Bnd_Box
    from OCP.BRepBndLib import BRepBndLib

    ocp_shape = solid.wrapped if hasattr(solid, 'wrapped') else solid

    bbox = Bnd_Box()
    BRepBndLib.Add_s(ocp_shape, bbox)
    xmin, ymin, zmin, xmax, ymax, zmax = bbox.Get()

    generator = FinGenerator(proposal.config)
    return generator.generate_fin_geometry(proposal, (xmin, ymin, zmin), (xmax, ymax, zmax))
