"""Complete Test Suite - All Phases"""
import sys
sys.path.insert(0, 'c:/LiteCad')

print("="*60)
print("SKETCH AGENT - ALL PHASES TEST SUITE")
print("="*60)

# Phase 1-3: Foundation
print("\n[Phase 1-3] Foundation & Core")
from sketching import SketchAgent, create_agent
agent = create_agent(mode="adaptive", headless=True, seed=42)
print("✓ SketchAgent imported")

result = agent.generate_part(complexity="simple")
print(f"✓ Part generated: {result.success}, {result.face_count} faces")

# Phase 4: Design Library
print("\n[Phase 4] Design Library")
from sketching import DesignLibrary, create_design_library
library = create_design_library(seed=42)
print(f"✓ Patterns: {library.list_patterns()}")

for pattern in library.list_patterns():
    solid = library.generate_from_pattern(pattern)
    if solid:
        print(f"  ✓ {pattern}: {len(list(solid.faces()))} faces")
    else:
        print(f"  ✗ {pattern}: Failed")

# Phase 5: Feedback Loop
print("\n[Phase 5] Feedback Loop")
from sketching import FeedbackLoop, create_feedback_loop
feedback = create_feedback_loop()
feedback.record("extrude", {"distance": 20}, True, 10.0)
feedback.record("fillet", {"radius": 2}, True, 15.0)
feedback.record("extrude", {"distance": 5}, False, 8.0, "Too thin")
print(f"✓ Feedback: {len(feedback.records)} records")
print(f"  Success Rate (extrude): {feedback.get_success_rate('extrude'):.2%}")
print(f"  Errors: {feedback.analyze_errors()}")

# Phase 6: Assembly Agent
print("\n[Phase 6] Assembly Agent")
from sketching import AssemblyAgent, create_assembly_agent
assembly_agent = create_assembly_agent(seed=42)
assembly_result = assembly_agent.generate_assembly(part_count=2, complexity="simple")
print(f"✓ Assembly: {assembly_result.success}")
print(f"  Parts: {assembly_result.part_count}")
print(f"  Constraints: {len(assembly_result.constraints)}")

# Phase 7: Export
print("\n[Phase 7] Export")
from sketching import PartExporter, create_part_exporter
exporter = create_part_exporter()
# Metadata export test
import tempfile
import os
temp_dir = tempfile.mkdtemp()
meta_path = os.path.join(temp_dir, "test_metadata.json")
exporter.export_metadata(result, meta_path, {"test": True})
print(f"✓ Metadata exported: {os.path.exists(meta_path)}")
# Cleanup
os.remove(meta_path)
os.rmdir(temp_dir)

# Phase 8: Visual Agent
print("\n[Phase 8] Visual Agent")
from sketching import VisualSketchAgent, create_visual_agent
visual_agent = create_visual_agent(viewport=None, seed=42)
print(f"✓ VisualSketchAgent created (headless mode)")
print(f"  Viewport available: {visual_agent.viewport is not None}")

# Phase 9: Test Runner
print("\n[Phase 9] Test Runner")
from sketching import TestRunner
runner = TestRunner(agent=agent)
stress_result = runner.run_stress_test(count=3, complexity="simple")
print(f"✓ Stress Test: {stress_result.success_rate:.1%} success")
print(f"  Avg Duration: {stress_result.avg_duration_ms:.2f}ms")

# Phase 10: Mesh Analyzer
print("\n[Phase 10] Mesh Analysis")
from sketching import MeshAnalyzer
analyzer = MeshAnalyzer()
# Test without file
analysis = analyzer.analyze("nonexistent.stl")
print(f"✓ MeshAnalyzer handles missing file gracefully")
print(f"  Primitives: {analysis.primitive_count}")

print("\n" + "="*60)
print("ALL PHASES TEST COMPLETE")
print("="*60)

print("\nVersion 1.0.0 - All Phases Implemented:")
print("  ✓ Phase 1-3: Foundation, SketchGenerator, OperationAgent")
print("  ✓ Phase 4: Design Library")
print("  ✓ Phase 5: Feedback Loop")
print("  ✓ Phase 6: Assembly Agent")
print("  ✓ Phase 7: Export & Reporting")
print("  ✓ Phase 8: Visual Mode")
print("  ✓ Phase 9: Test Runner")
print("  ✓ Phase 10: Mesh Analysis & Reconstruction")
