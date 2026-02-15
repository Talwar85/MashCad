"""
STL Analysis Module for Feature Detection and Quality Checking.
"""

from .mesh_quality_checker import MeshQualityChecker, MeshQualityReport
from .stl_feature_analyzer import (
    STLFeatureAnalyzer,
    STLFeatureAnalysis,
    HoleInfo,
    PocketInfo,
    PlaneInfo,
    FilletInfo,
    analyze_stl,
)

__all__ = [
    'MeshQualityChecker',
    'MeshQualityReport',
    'STLFeatureAnalyzer',
    'STLFeatureAnalysis',
    'HoleInfo',
    'PocketInfo',
    'PlaneInfo',
    'FilletInfo',
    'analyze_stl',
]
