"""
MashCad - Mesh Converter Package
================================

Mesh-zu-BREP Konvertierung mit 3 Strategien:

Async Converter (neu):
    SimpleConverter - Einfach, immer zuverlässig (Baseline)
    CurrentConverter - Der V10/Final Converter (bestehend)
    PerfectConverter - Optimiert, perfektes BREP (in Arbeit)

Legacy Converter:
    MeshToBREPConverterV10 - Vollständiger Konverter
    FinalMeshConverter - Zylinder-erhaltend
    DirectMeshConverter - 1:1 Mapping
    FilletAwareConverter - Fillet/Chamfer Erkennung

Convenience-Funktionen:
    convert_stl_to_brep(filepath) - STL zu BREP
    load_and_repair_mesh(filepath) - Mesh laden und reparieren

Usage:
    from meshconverter import SimpleConverter, convert_stl_to_brep

    # Einfach (immer zuverlässig)
    converter = SimpleConverter()
    result = converter.convert_async(mesh, on_progress)

    # Bestehend (V10)
    result = convert_stl_to_brep("part.stl")
"""

# ============================================================================
# Async Base Classes (neu)
# ============================================================================
from meshconverter.base import (
    AsyncMeshConverter,
    ConversionPhase,
    ProgressUpdate,
    ProgressCallback,
)

# ============================================================================
# Async Converter (neu)
# ============================================================================
from meshconverter.simple_converter import (
    SimpleConverter,
    convert_simple,
)

# ============================================================================
# Legacy Converter (bestehend)
# ============================================================================
from meshconverter.mesh_converter_v10 import (
    # Main Converter
    MeshToBREPConverterV10,

    # Result Types
    ConversionStatus,
    ConversionResult,
    LoadStatus,
    LoadResult,

    # Data Classes
    Region,
    DetectedPrimitive,

    # Convenience Functions
    convert_stl_to_brep,
    load_and_repair_mesh,

    # Loader
    MeshLoader,
)

# Fillet-Aware Converter (V9-style detection)
# Note: Fillet conversion is currently disabled, only chamfers work
try:
    from meshconverter.fillet_aware_converter import (
        FilletAwareConverter,
        convert_with_fillets,
    )
    HAS_FILLET_CONVERTER = True
except ImportError:
    # sklearn might not be installed
    FilletAwareConverter = None
    convert_with_fillets = None
    HAS_FILLET_CONVERTER = False

__all__ = [
    # Async Base
    'AsyncMeshConverter',
    'ConversionPhase',
    'ProgressUpdate',
    'ProgressCallback',

    # Async Converter
    'SimpleConverter',
    'convert_simple',

    # Legacy Converter
    'MeshToBREPConverterV10',
    'FilletAwareConverter',

    # Status Enums
    'ConversionStatus',
    'LoadStatus',

    # Result Types
    'ConversionResult',
    'LoadResult',

    # Data Classes
    'Region',
    'DetectedPrimitive',

    # Convenience Functions
    'convert_stl_to_brep',
    'load_and_repair_mesh',
    'convert_simple',
    'convert_with_fillets',

    # Loader
    'MeshLoader',
]

__version__ = '0.2-alpha'
