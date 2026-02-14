"""
Standalone Test für Mesh Reconstructor.
Testet Logik ohne vollständige CAD-Abhängigkeiten.
"""

import sys
import os
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional
from enum import Enum


class StepStatus(Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    ROLLED_BACK = "rolled_back"


@dataclass
class MockStep:
    step_number: int
    name: str
    status: StepStatus = StepStatus.PENDING
    error_message: str = ""


@dataclass
class MockAnalysis:
    base_plane: Optional[Dict] = None
    holes: List[Dict] = field(default_factory=list)
    overall_confidence: float = 0.0


@dataclass
class MockResult:
    success: bool = False
    steps_completed: int = 0
    steps_total: int = 0
    steps_failed: List[int] = field(default_factory=list)


class MockReconstructor:
    """Mock reconstructor für Logik-Tests."""
    
    MIN_SKETCH_AREA = 0.01
    MIN_SOLID_VOLUME = 0.001
    
    def __init__(self, use_tnp: bool = False):
        self.use_tnp = use_tnp
        self.steps: List[MockStep] = []
        self.completed_steps: List[MockStep] = []
        self.progress_log: List[tuple] = []
    
    def set_progress_callback(self, callback):
        self.progress_callback = callback
    
    def _report_progress(self, percent: int, message: str):
        self.progress_log.append((percent, message))
        if hasattr(self, 'progress_callback') and self.progress_callback:
            self.progress_callback(percent, message)
    
    def create_reconstruction_plan(self, analysis: MockAnalysis) -> List[MockStep]:
        """Create reconstruction plan."""
        steps = []
        step_num = 1
        
        if analysis.base_plane:
            steps.append(MockStep(step_num, "base_sketch"))
            step_num += 1
            steps.append(MockStep(step_num, "base_extrude"))
            step_num += 1
        
        for i, hole in enumerate(analysis.holes):
            if hole.get("confidence", 0) < 0.5:
                continue
            steps.append(MockStep(step_num, f"hole_{i+1}_sketch"))
            step_num += 1
            steps.append(MockStep(step_num, f"hole_{i+1}_cut"))
            step_num += 1
        
        steps.append(MockStep(step_num, "final_validation"))
        
        return steps
    
    def _execute_step(self, step: MockStep) -> bool:
        """Execute a step (mock)."""
        step.status = StepStatus.RUNNING
        
        # Simulate failure for testing
        if step.name == "hole_2_cut":  # Simulate second hole cut fails
            step.status = StepStatus.FAILED
            step.error_message = "Cut failed - feature intersection"
            return False
        
        step.status = StepStatus.SUCCESS
        self.completed_steps.append(step)
        return True
    
    def _rollback_from_step(self, failed_index: int):
        """Rollback steps."""
        for i in range(failed_index - 1, -1, -1):
            step = self.steps[i]
            if step.status == StepStatus.SUCCESS:
                step.status = StepStatus.ROLLED_BACK
    
    def reconstruct(self, analysis: MockAnalysis) -> MockResult:
        """Run reconstruction."""
        result = MockResult()
        
        self.steps = self.create_reconstruction_plan(analysis)
        result.steps_total = len(self.steps)
        
        if not self.steps:
            result.success = False
            result.message = "No reconstruction steps created"
            return result
        
        for i, step in enumerate(self.steps):
            progress = int((i / len(self.steps)) * 100)
            self._report_progress(progress, f"Step {step.step_number}: {step.name}")
            
            success = self._execute_step(step)
            
            if not success:
                result.steps_failed.append(step.step_number)
                result.success = False
                self._rollback_from_step(i)
                return result
            
            result.steps_completed += 1
        
        result.success = True
        self._report_progress(100, "Complete!")
        return result
    
    def validate_hole_parameters(self, hole: Dict) -> bool:
        """Validate hole parameters."""
        radius = hole.get("radius", 0)
        depth = hole.get("depth", 0)
        confidence = hole.get("confidence", 0)
        
        return (
            radius > 0.01 and
            depth > 0.01 and
            0.0 <= confidence <= 1.0
        )


# Tests
def test_plan_creation():
    """Test reconstruction plan creation."""
    recon = MockReconstructor()
    
    analysis = MockAnalysis(
        base_plane={"area": 100.0, "confidence": 0.95},
        holes=[
            {"confidence": 0.9, "radius": 5.0, "depth": 10.0},
            {"confidence": 0.8, "radius": 3.0, "depth": 8.0},
            {"confidence": 0.4, "radius": 2.0, "depth": 5.0},  # Low confidence - skip
        ]
    )
    
    steps = recon.create_reconstruction_plan(analysis)
    
    # Should have: base_sketch, base_extrude, hole1_sketch, hole1_cut, hole2_sketch, hole2_cut, final
    # = 7 steps (hole 3 skipped due to low confidence)
    assert len(steps) == 7
    assert steps[0].name == "base_sketch"
    assert steps[1].name == "base_extrude"
    assert steps[2].name == "hole_1_sketch"
    assert steps[6].name == "final_validation"
    
    print("[OK] Plan creation test passed")


def test_successful_reconstruction():
    """Test successful reconstruction flow."""
    recon = MockReconstructor()
    
    # Analysis with only 1 hole (to avoid simulated failure)
    analysis = MockAnalysis(
        base_plane={"confidence": 0.95},
        holes=[{"confidence": 0.9, "radius": 5.0, "depth": 10.0}]
    )
    
    result = recon.reconstruct(analysis)
    
    assert result.success
    assert result.steps_completed == 5  # base sketch, extrude, hole sketch, cut, validation
    assert result.steps_total == 5
    assert len(result.steps_failed) == 0
    
    print("[OK] Successful reconstruction test passed")


def test_failed_reconstruction_with_rollback():
    """Test failed reconstruction with rollback."""
    recon = MockReconstructor()
    
    # This will trigger the simulated failure in hole_2_cut
    analysis = MockAnalysis(
        base_plane={"confidence": 0.95},
        holes=[
            {"confidence": 0.9, "radius": 5.0, "depth": 10.0},
            {"confidence": 0.8, "radius": 3.0, "depth": 8.0},  # Will fail at cut
        ]
    )
    
    result = recon.reconstruct(analysis)
    
    assert not result.success
    assert len(result.steps_failed) == 1
    
    # Check rollbacks happened
    rolled_back = [s for s in recon.steps if s.status == StepStatus.ROLLED_BACK]
    assert len(rolled_back) > 0  # Should have rolled back some steps
    
    print("[OK] Failed reconstruction with rollback test passed")


def test_progress_reporting():
    """Test progress callback."""
    recon = MockReconstructor()
    progress_calls = []
    
    def callback(percent, message):
        progress_calls.append((percent, message))
    
    recon.set_progress_callback(callback)
    
    analysis = MockAnalysis(
        base_plane={"confidence": 0.95},
        holes=[{"confidence": 0.9}]
    )
    
    result = recon.reconstruct(analysis)
    
    assert len(progress_calls) > 0
    assert progress_calls[0][0] == 0  # Starts at 0%
    assert progress_calls[-1][0] == 100  # Ends at 100%
    
    print("[OK] Progress reporting test passed")


def test_hole_validation():
    """Test hole parameter validation."""
    recon = MockReconstructor()
    
    # Valid hole
    valid_hole = {"radius": 5.0, "depth": 10.0, "confidence": 0.9}
    assert recon.validate_hole_parameters(valid_hole)
    
    # Invalid - radius too small
    invalid_hole1 = {"radius": 0.001, "depth": 10.0, "confidence": 0.9}
    assert not recon.validate_hole_parameters(invalid_hole1)
    
    # Invalid - depth too small
    invalid_hole2 = {"radius": 5.0, "depth": 0.001, "confidence": 0.9}
    assert not recon.validate_hole_parameters(invalid_hole2)
    
    # Invalid - confidence out of range
    invalid_hole3 = {"radius": 5.0, "depth": 10.0, "confidence": 1.5}
    assert not recon.validate_hole_parameters(invalid_hole3)
    
    print("[OK] Hole validation test passed")


def test_tnp_disabled_by_default():
    """Test TNP is disabled by default."""
    recon = MockReconstructor()  # Default use_tnp=False
    assert not recon.use_tnp
    
    recon_with_tnp = MockReconstructor(use_tnp=True)
    assert recon_with_tnp.use_tnp
    
    print("[OK] TNP disabled by default test passed")


def test_empty_analysis():
    """Test with empty analysis."""
    recon = MockReconstructor()
    
    analysis = MockAnalysis()  # No base plane, no holes
    
    # Check plan creation - should have at least final_validation
    steps = recon.create_reconstruction_plan(analysis)
    assert len(steps) == 1  # Only final_validation
    
    # Reconstruction should handle this gracefully
    result = recon.reconstruct(analysis)
    assert result.steps_total == 1
    
    print("[OK] Empty analysis test passed")


if __name__ == "__main__":
    print("Running Mesh Reconstructor Tests...")
    print("-" * 50)
    
    try:
        test_plan_creation()
        test_successful_reconstruction()
        test_failed_reconstruction_with_rollback()
        test_progress_reporting()
        test_hole_validation()
        test_tnp_disabled_by_default()
        test_empty_analysis()
        
        print("-" * 50)
        print("All tests passed!")
        
    except AssertionError as e:
        print(f"[FAIL] Test failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    except Exception as e:
        print(f"[ERROR] Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
