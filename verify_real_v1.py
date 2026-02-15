import sys
import os
import logging

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(levelname)s:%(name)s:%(message)s')
logger = logging.getLogger("VerifyV1")

# Add project root to path
sys.path.insert(0, r"c:\LiteCad")

try:
    from sketching.analysis.stl_feature_analyzer import STLFeatureAnalyzer
except ImportError as e:
    logger.error(f"Failed to import modules: {e}")
    sys.exit(1)

def verify():
    stl_path = r"c:\LiteCad\stl\V1.stl"
    
    if not os.path.exists(stl_path):
        logger.error(f"File not found: {stl_path}")
        return

    logger.info(f"Analyzing {stl_path}...")
    
    try:
        analyzer = STLFeatureAnalyzer()
        # Force skip quality check to avoid potential display/plotter issues in headless mode
        # although we want to test robustness.
        analysis = analyzer.analyze(stl_path, skip_quality_check=False)
        
        logger.info("-" * 30)
        logger.info(f"Overall Confidence: {analysis.overall_confidence:.2f}")
        
        if analysis.base_plane:
            bp = analysis.base_plane
            logger.info(f"Base Plane Detected: {bp.detection_method}")
            logger.info(f"  Origin: {bp.origin}")
            logger.info(f"  Normal: {bp.normal}")
            logger.info(f"  Area:   {bp.area:.2f}")
        else:
            logger.error("No Base Plane Detected!")
            
        logger.info(f"Holes Detected: {len(analysis.holes)}")
        for i, hole in enumerate(analysis.holes):
             logger.info(f"  Hole #{i+1}: r={hole.radius:.2f}, d={hole.depth:.2f}, center={hole.center}")

        logger.info(f"Edges Detected: {len(analysis.edges)}")
        if analysis.edges:
            logger.info(f"  First edge points count: {len(analysis.edges[0].points)}")

    except Exception as e:
        logger.error(f"Analysis failed: {e}", exc_info=True)

if __name__ == "__main__":
    verify()
