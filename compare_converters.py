"""Compare FilletAwareConverter vs DirectMeshConverter on all STL files."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from loguru import logger
logger.remove()
logger.add(sys.stderr, level="WARNING")

from meshconverter.fillet_aware_converter import FilletAwareConverter
from meshconverter.direct_mesh_converter import DirectMeshConverter
from meshconverter.brep_optimizer import optimize_brep
from meshconverter.mesh_converter_v10 import ConversionStatus

from OCP.STEPControl import STEPControl_Writer, STEPControl_AsIs
from OCP.IFSelect import IFSelect_RetDone

def export_step(shape, filepath):
    """Export shape to STEP file."""
    writer = STEPControl_Writer()
    if hasattr(shape, 'wrapped'):
        writer.Transfer(shape.wrapped, STEPControl_AsIs)
    else:
        writer.Transfer(shape, STEPControl_AsIs)
    status = writer.Write(str(filepath))
    return status == IFSelect_RetDone

stl_dir = Path(__file__).parent / "stl"
out_dir = Path(__file__).parent / "comparison_output"
out_dir.mkdir(exist_ok=True)

stl_files = list(stl_dir.glob("*.stl"))
print(f"Found {len(stl_files)} STL files\n")

for stl_path in stl_files:
    name = stl_path.stem
    print(f"{'='*60}")
    print(f"Processing: {name}")
    print(f"{'='*60}")

    # 1. FilletAwareConverter
    print(f"\n[FilletAware] Converting...")
    try:
        conv1 = FilletAwareConverter(plane_tolerance=1.0, cylinder_tolerance=3.0)
        result1 = conv1.convert(str(stl_path))

        if result1.solid and result1.status in [ConversionStatus.SUCCESS, ConversionStatus.SHELL_ONLY]:
            out1 = out_dir / f"{name}_filletaware.step"
            if export_step(result1.solid, out1):
                size1 = out1.stat().st_size
                print(f"[FilletAware] OK: {out1.name} ({size1:,} bytes)")
                print(f"             Stats: {result1.stats}")
            else:
                print(f"[FilletAware] STEP export failed")
        else:
            print(f"[FilletAware] Conversion failed: {result1.status.name}")
    except Exception as e:
        print(f"[FilletAware] ERROR: {e}")

    # 2. DirectMeshConverter + optimizer
    print(f"\n[DirectMesh] Converting...")
    try:
        import pyvista as pv
        mesh = pv.read(str(stl_path))

        conv2 = DirectMeshConverter(unify_faces=False)
        result2 = conv2.convert(mesh)

        if result2.solid:
            # Apply optimizer
            optimized, opt_stats = optimize_brep(result2.solid)

            out2 = out_dir / f"{name}_directmesh.step"
            if export_step(optimized, out2):
                size2 = out2.stat().st_size
                print(f"[DirectMesh] OK: {out2.name} ({size2:,} bytes)")
                print(f"             Faces: {opt_stats.get('faces_before', '?')} -> {opt_stats.get('faces_after', '?')}")
            else:
                print(f"[DirectMesh] STEP export failed")
        else:
            print(f"[DirectMesh] Conversion failed: {result2.message}")
    except Exception as e:
        print(f"[DirectMesh] ERROR: {e}")

    print()

print(f"\n{'='*60}")
print(f"Output directory: {out_dir}")
print(f"{'='*60}")
