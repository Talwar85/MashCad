"""
MashCad - Lattice Generator
Beam-based lattice structures for 3D printing (lightweight, material-saving).

Unit cell types: BCC, FCC, Octet, Diamond
Strategy: Define unit cell edges → repeat over bounding box → sweep with circle → fuse → intersect with body.
"""

from dataclasses import dataclass, field
from typing import List, Tuple, Optional
from loguru import logger


# Unit cell definitions: list of (start, end) pairs as fractional coordinates [0,1]^3
UNIT_CELLS = {
    "BCC": [
        # Body center to all 8 corners
        ((0.5, 0.5, 0.5), (0, 0, 0)),
        ((0.5, 0.5, 0.5), (1, 0, 0)),
        ((0.5, 0.5, 0.5), (0, 1, 0)),
        ((0.5, 0.5, 0.5), (1, 1, 0)),
        ((0.5, 0.5, 0.5), (0, 0, 1)),
        ((0.5, 0.5, 0.5), (1, 0, 1)),
        ((0.5, 0.5, 0.5), (0, 1, 1)),
        ((0.5, 0.5, 0.5), (1, 1, 1)),
    ],
    "FCC": [
        # Face centers to corners (12 edges per cell)
        ((0.5, 0.5, 0), (0, 0, 0)), ((0.5, 0.5, 0), (1, 0, 0)),
        ((0.5, 0.5, 0), (0, 1, 0)), ((0.5, 0.5, 0), (1, 1, 0)),
        ((0.5, 0, 0.5), (0, 0, 0)), ((0.5, 0, 0.5), (1, 0, 0)),
        ((0.5, 0, 0.5), (0, 0, 1)), ((0.5, 0, 0.5), (1, 0, 1)),
        ((0, 0.5, 0.5), (0, 0, 0)), ((0, 0.5, 0.5), (0, 1, 0)),
        ((0, 0.5, 0.5), (0, 0, 1)), ((0, 0.5, 0.5), (0, 1, 1)),
    ],
    "Octet": [
        # Octet truss: FCC + cross braces (very stiff)
        # FCC edges
        ((0.5, 0.5, 0), (0, 0, 0)), ((0.5, 0.5, 0), (1, 0, 0)),
        ((0.5, 0.5, 0), (0, 1, 0)), ((0.5, 0.5, 0), (1, 1, 0)),
        ((0.5, 0, 0.5), (0, 0, 0)), ((0.5, 0, 0.5), (1, 0, 0)),
        ((0.5, 0, 0.5), (0, 0, 1)), ((0.5, 0, 0.5), (1, 0, 1)),
        ((0, 0.5, 0.5), (0, 0, 0)), ((0, 0.5, 0.5), (0, 1, 0)),
        ((0, 0.5, 0.5), (0, 0, 1)), ((0, 0.5, 0.5), (0, 1, 1)),
        # Cross connections between face centers
        ((0.5, 0.5, 0), (0.5, 0, 0.5)),
        ((0.5, 0.5, 0), (0, 0.5, 0.5)),
        ((0.5, 0, 0.5), (0, 0.5, 0.5)),
    ],
    "Diamond": [
        # Diamond cubic: tetrahedral connections (flexible)
        ((0.25, 0.25, 0.25), (0, 0, 0)),
        ((0.25, 0.25, 0.25), (0.5, 0.5, 0)),
        ((0.25, 0.25, 0.25), (0.5, 0, 0.5)),
        ((0.25, 0.25, 0.25), (0, 0.5, 0.5)),
        ((0.75, 0.75, 0.75), (1, 1, 1)),
        ((0.75, 0.75, 0.75), (0.5, 0.5, 1)),
        ((0.75, 0.75, 0.75), (0.5, 1, 0.5)),
        ((0.75, 0.75, 0.75), (1, 0.5, 0.5)),
    ],
}


class LatticeGenerator:
    """
    Generates beam-based lattice structures within a bounding shape.

    Performance note: For large cell counts this can be slow due to O(n) boolean fuse.
    Recommend max ~500 beams for interactive use.
    """

    @staticmethod
    def generate(solid, cell_type: str = "BCC", cell_size: float = 5.0,
                 beam_radius: float = 0.5, max_cells: int = 500,
                 progress_callback=None):
        """
        Generate a lattice structure within the bounding box of the solid,
        then intersect with the original solid.

        Args:
            solid: Build123d Solid to fill with lattice
            cell_type: One of "BCC", "FCC", "Octet", "Diamond"
            cell_size: Size of each unit cell in mm
            beam_radius: Radius of each beam strut in mm
            max_cells: Maximum number of cells (safety limit)
            progress_callback: Optional callable(percent: int, message: str)

        Returns:
            Build123d Solid of the lattice, or None on failure
        """
        if cell_type not in UNIT_CELLS:
            raise ValueError(f"Unknown cell type: {cell_type}. Use: {list(UNIT_CELLS.keys())}")

        try:
            from OCP.gp import gp_Pnt, gp_Dir, gp_Ax2, gp_Vec
            from OCP.BRepPrimAPI import BRepPrimAPI_MakeCylinder
            from OCP.BRepAlgoAPI import BRepAlgoAPI_Fuse, BRepAlgoAPI_Common
            from OCP.BRepBuilderAPI import BRepBuilderAPI_Transform
            from OCP.gp import gp_Trsf
            import math

            shape = solid.wrapped if hasattr(solid, 'wrapped') else solid

            # Get bounding box
            bb = solid.bounding_box()
            x_min, y_min, z_min = bb.min.X, bb.min.Y, bb.min.Z
            x_max, y_max, z_max = bb.max.X, bb.max.Y, bb.max.Z

            # Calculate cell counts
            nx = max(1, int(math.ceil((x_max - x_min) / cell_size)))
            ny = max(1, int(math.ceil((y_max - y_min) / cell_size)))
            nz = max(1, int(math.ceil((z_max - z_min) / cell_size)))

            total_cells = nx * ny * nz
            if total_cells > max_cells:
                logger.warning(
                    f"Lattice would need {total_cells} cells, limiting to {max_cells}. "
                    f"Increase cell_size or reduce body size."
                )
                # Scale down
                scale = (max_cells / total_cells) ** (1/3)
                nx = max(1, int(nx * scale))
                ny = max(1, int(ny * scale))
                nz = max(1, int(nz * scale))

            cell_edges = UNIT_CELLS[cell_type]
            logger.info(f"Lattice: {cell_type} {nx}x{ny}x{nz} cells, "
                        f"{len(cell_edges)} edges/cell, beam_r={beam_radius}mm")

            # Generate all beams
            beam_shapes = []
            for ix in range(nx):
                for iy in range(ny):
                    for iz in range(nz):
                        # Cell origin in world space
                        ox = x_min + ix * cell_size
                        oy = y_min + iy * cell_size
                        oz = z_min + iz * cell_size

                        for (sx, sy, sz), (ex, ey, ez) in cell_edges:
                            # World coordinates
                            p1 = (ox + sx * cell_size, oy + sy * cell_size, oz + sz * cell_size)
                            p2 = (ox + ex * cell_size, oy + ey * cell_size, oz + ez * cell_size)

                            beam = LatticeGenerator._make_beam(p1, p2, beam_radius)
                            if beam is not None:
                                beam_shapes.append(beam)

            if not beam_shapes:
                raise RuntimeError("No beams generated")

            total_beams = len(beam_shapes)
            logger.info(f"Fusing {total_beams} beams...")
            if progress_callback:
                progress_callback(5, f"Fusing {total_beams} beams...")

            # Fuse all beams
            result = beam_shapes[0]
            for i, beam in enumerate(beam_shapes[1:], 1):
                fuse = BRepAlgoAPI_Fuse(result, beam)
                fuse.SetFuzzyValue(1e-3)
                fuse.Build()
                if fuse.IsDone():
                    result = fuse.Shape()
                if i % 50 == 0:
                    pct = int(5 + 85 * i / total_beams)
                    logger.debug(f"Fused {i}/{total_beams} beams")
                    if progress_callback:
                        progress_callback(pct, f"Fusing beams {i}/{total_beams}...")

            # Intersect with original body
            logger.info("Intersecting lattice with body...")
            if progress_callback:
                progress_callback(92, "Intersecting with body...")
            common = BRepAlgoAPI_Common(result, shape)
            common.SetFuzzyValue(1e-3)
            common.Build()

            if not common.IsDone():
                raise RuntimeError("Boolean Common (lattice ∩ body) failed")

            from build123d import Solid
            lattice_solid = Solid(common.Shape())

            if hasattr(lattice_solid, 'is_valid') and lattice_solid.is_valid():
                logger.success(f"Lattice generated: {cell_type}, {len(beam_shapes)} beams")
                return lattice_solid
            else:
                logger.warning("Lattice result is invalid, returning raw shape")
                from build123d import Shape
                return Shape(common.Shape())

        except Exception as e:
            logger.error(f"Lattice generation failed: {e}")
            raise

    @staticmethod
    def _make_beam(p1, p2, radius):
        """Create a cylinder beam between two points."""
        import math
        from OCP.gp import gp_Pnt, gp_Dir, gp_Ax2, gp_Trsf, gp_Vec
        from OCP.BRepPrimAPI import BRepPrimAPI_MakeCylinder
        from OCP.BRepBuilderAPI import BRepBuilderAPI_Transform

        dx = p2[0] - p1[0]
        dy = p2[1] - p1[1]
        dz = p2[2] - p1[2]
        length = math.sqrt(dx*dx + dy*dy + dz*dz)

        if length < 1e-6:
            return None

        # Cylinder along direction
        direction = gp_Dir(dx/length, dy/length, dz/length)
        origin = gp_Pnt(p1[0], p1[1], p1[2])
        ax = gp_Ax2(origin, direction)

        cyl = BRepPrimAPI_MakeCylinder(ax, radius, length)
        cyl.Build()
        if cyl.IsDone():
            return cyl.Shape()
        return None
