
import sys
import os
import logging
import numpy as np

# Add parent directory to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../../")))

# CRITICAL: Mock modeling to prevent pyvista crash in broken env
from unittest.mock import MagicMock

# Mock modules
sys.modules["modeling"] = MagicMock()
sys.modules["modeling.cad_tessellator"] = MagicMock()

# Mock ALL sketching submodules to avoid Python 3.6 SyntaxErrors and heavy imports
sys.modules["sketching.core"] = MagicMock()
sys.modules["sketching.core.sketch_agent"] = MagicMock()
sys.modules["sketching.core.result_types"] = MagicMock()
sys.modules["sketching.core.assembly_agent"] = MagicMock()
sys.modules["sketching.test_runner"] = MagicMock()
sys.modules["sketching.patterns"] = MagicMock()
sys.modules["sketching.patterns.design_library"] = MagicMock()
sys.modules["sketching.learning"] = MagicMock()
sys.modules["sketching.learning.feedback_loop"] = MagicMock()
sys.modules["sketching.export"] = MagicMock()
sys.modules["sketching.export.exporter"] = MagicMock()
sys.modules["sketching.visual"] = MagicMock()
sys.modules["sketching.visual.visual_agent"] = MagicMock()

sys.modules["sketching.reconstruction"] = MagicMock()
sys.modules["sketching.reconstruction.mesh_reconstructor"] = MagicMock()
sys.modules["sketching.analysis.reconstruction_agent"] = MagicMock()
sys.modules["sketching.analysis.mesh_analyzer"] = MagicMock()

from sketching.analysis.stl_feature_analyzer import STLFeatureAnalyzer

def debug_v1():
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger("DebugV1")
    
    stl_path = r"c:\LiteCad\stl\V1.stl"
    
    if not os.path.exists(stl_path):
        logger.error(f"File not found: {stl_path}")
        return

    analyzer = STLFeatureAnalyzer()
    
    if hasattr(analyzer, 'HAS_SKLEARN') and analyzer.HAS_SKLEARN:
        logger.info("Using scikit-learn for analysis")
    else:
        logger.warning("Using heuristic analysis (scikit-learn not found/loaded)")

    logger.info(f"Analyzing {stl_path}...")
    result = analyzer.analyze(stl_path, skip_quality_check=True)
    
    logger.info("-" * 30)
    logger.info(f"Overall Confidence: {result.overall_confidence:.2f}")
    
    # Analyze Base Plane
    if result.base_plane:
        bp = result.base_plane
        logger.info(f"Base Plane Detected:")
        logger.info(f"  Normal: {bp.normal}")
        logger.info(f"  Origin: {bp.origin}")
        logger.info(f"  Area:   {bp.area:.2f}")
        logger.info(f"  Conf:   {bp.confidence:.2f}")
        
        # Check alignment with Z
        if abs(bp.normal[2]) > 0.9:
            logger.info("  -> Aligned with Z axis (Top/Bottom)")
        elif abs(bp.normal[1]) > 0.9:
            logger.info("  -> Aligned with Y axis (Front/Back)")
        elif abs(bp.normal[0]) > 0.9:
            logger.info("  -> Aligned with X axis (Left/Right)")
        else:
            logger.warning("  -> Skewed orientation!")
    else:
        logger.error("No Base Plane Detected!")
        
    # Analyze Holes
    logger.info(f"Holes Detected: {len(result.holes)}")
    for i, h in enumerate(result.holes):
        logger.info(f"  Hole {i}: R={h.radius:.2f}, D={h.depth:.2f}, Axis={h.axis}, Conf={h.confidence:.2f}")
        
    # (Future) Analyze Edges
    if hasattr(result, 'edges'):
        logger.info(f"Edges Detected: {len(result.edges)}")
    else:
        logger.info("Edges not yet implemented in result structure")

if __name__ == "__main__":
    debug_v1()
