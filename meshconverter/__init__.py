"""
MashCad - Mesh Converter Package
================================

Mesh-zu-BREP Konvertierung mit intelligenter Oberflächenerkennung.

Hauptklasse:
    MeshToBREPConverterV10 - Vollständiger Konverter

Convenience-Funktionen:
    convert_stl_to_brep(filepath) - STL zu BREP
    load_and_repair_mesh(filepath) - Mesh laden und reparieren

Usage:
    from meshconverter import convert_stl_to_brep, ConversionStatus

    result = convert_stl_to_brep("part.stl")
    if result.status == ConversionStatus.SUCCESS:
        solid = result.solid
"""

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

__all__ = [
    # Main
    'MeshToBREPConverterV10',

    # Status Enums
    'ConversionStatus',
    'LoadStatus',

    # Result Types
    'ConversionResult',
    'LoadResult',

    # Data Classes
    'Region',
    'DetectedPrimitive',

    # Functions
    'convert_stl_to_brep',
    'load_and_repair_mesh',

    # Loader
    'MeshLoader',
]

__version__ = '10.0.0'
