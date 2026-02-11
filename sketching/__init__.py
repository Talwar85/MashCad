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
Date: 2026-02-11
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

# Phase 9: Test Runner
from sketching.test_runner import TestRunner, run_quick_test

# Phase 4: Design Library
from sketching.patterns.design_library import DesignLibrary, create_design_library, DESIGN_PATTERNS

# Phase 10: Mesh Analysis & Reconstruction
from sketching.analysis.mesh_analyzer import MeshAnalyzer
from sketching.analysis.reconstruction_agent import ReconstructionAgent

# Phase 5: Feedback Loop
from sketching.learning.feedback_loop import FeedbackLoop, create_feedback_loop, OperationRecord

# Phase 6: Assembly Agent
from sketching.core.assembly_agent import AssemblyAgent, create_assembly_agent

# Phase 7: Export & Reporting
from sketching.export.exporter import (
    PartExporter, BatchExporter,
    create_part_exporter, create_batch_exporter
)

# Phase 8: Visual Mode
from sketching.visual.visual_agent import VisualSketchAgent, create_visual_agent

__version__ = "1.0.0"
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
    # Phase 5
    "FeedbackLoop",
    "create_feedback_loop",
    "OperationRecord",
    # Phase 6
    "AssemblyAgent",
    "create_assembly_agent",
    # Phase 7
    "PartExporter",
    "BatchExporter",
    "create_part_exporter",
    "create_batch_exporter",
    # Phase 8
    "VisualSketchAgent",
    "create_visual_agent",
]
