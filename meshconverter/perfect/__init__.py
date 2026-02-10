"""
Perfect Converter Module
========================

Erweiterte Mesh-to-BREP Konvertierung mit:
- Analytischen Surfaces
- Feature Recognition
- Optimiertem Ergebnis
"""

from .primitive_detector import (
    PrimitiveDetector,
    DetectedPrimitive,
    PrimitiveType
)
from .feature_detector import (
    FeatureDetector,
    DetectedFeature,
    FeatureType
)
from .brep_builder import (
    BREPBuilder,
    build_analytical_cylinder
)

__all__ = [
    'PrimitiveDetector',
    'DetectedPrimitive',
    'PrimitiveType',
    'FeatureDetector',
    'DetectedFeature',
    'FeatureType',
    'BREPBuilder',
    'build_analytical_cylinder',
]
