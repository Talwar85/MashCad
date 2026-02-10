"""
Sketch Agent - Automatische CAD-Generierung und Mesh-Rekonstruktion

Ein intelligenter Agent der wie ein CAD-Experte Sketches zeichnet
und OCP-Operationen durchführt.

Use Cases:
- 🧪 Automatisiertes Testing (Bug-Discovery, Regression-Tests)
- 🎨 Design-Exploration (Kreative zufällige Designs)
- 📊 ML-Training-Data (Trainingsdaten für CAD-ML-Modelle)
- 🔧 Mesh-to-CAD (STL → Editierbares CAD mit User-Interaction)

Author: Claude (Sketch Agent)
Date: 2026-02-10
"""

from sketching.core.sketch_agent import SketchAgent, create_agent
from sketching.core.result_types import (
    PartResult,
    AssemblyResult,
    BatchResult,
    MeshAnalysis,
    ReconstructionResult,
    PrimitiveInfo,
    FeatureInfo,
    PatternInfo
)

# New exports
from sketching.test_runner import TestRunner, run_quick_test
from sketching.patterns.design_library import DesignLibrary, create_design_library, DESIGN_PATTERNS
from sketching.analysis.mesh_analyzer import MeshAnalyzer
from sketching.analysis.reconstruction_agent import ReconstructionAgent

__version__ = "0.2.0"
__all__ = [
    "SketchAgent",
    "create_agent",
    "PartResult",
    "AssemblyResult",
    "BatchResult",
    "MeshAnalysis",
    "ReconstructionResult",
    "PrimitiveInfo",
    "FeatureInfo",
    "PatternInfo",
    # Phase 9
    "TestRunner",
    "run_quick_test",
    # Phase 4
    "DesignLibrary",
    "create_design_library",
    "DESIGN_PATTERNS",
    # Phase 10
    "MeshAnalyzer",
    "ReconstructionAgent",
]
