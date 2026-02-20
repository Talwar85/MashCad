"""
MashCAD Export Corpus Tests
===========================

Tests for the export regression corpus. Each corpus model is loaded,
exported to STL and STEP, and validated.

Run: pytest test/test_export_corpus.py -v

Author: MashCAD Team
Date: 2026-02-20
Branch: feature/v1-roadmap-execution
"""

import pytest
import os
import sys
import tempfile
import importlib.util
from pathlib import Path
from typing import Dict, Any, List, Tuple, Optional

# Try to import dependencies
try:
    from OCP.TopoDS import TopoDS_Shape
    from OCP.BRepCheck import BRepCheck_Analyzer
    from OCP.BRepTools import BRepTools
    OCP_AVAILABLE = True
except ImportError:
    OCP_AVAILABLE = False

try:
    from modeling.export_validator import (
        ExportValidator, ValidationOptions, ValidationCheckType
    )
    VALIDATOR_AVAILABLE = True
except ImportError:
    VALIDATOR_AVAILABLE = False

try:
    from modeling.export_kernel import ExportKernel, ExportOptions, ExportFormat, ExportQuality
    KERNEL_AVAILABLE = True
except ImportError:
    KERNEL_AVAILABLE = False

try:
    from modeling.cad_tessellator import CADTessellator
    TESSELLATOR_AVAILABLE = True
except ImportError:
    TESSELLATOR_AVAILABLE = False


# Skip all tests if core dependencies not available
pytestmark = pytest.mark.skipif(
    not OCP_AVAILABLE,
    reason="OCP dependencies not available"
)

# Corpus configuration
CORPUS_DIR = Path(__file__).parent / "corpus"
CATEGORIES = ["primitives", "operations", "features", "regression"]
OUTPUT_DIR = Path(__file__).parent.parent / "test_output" / "corpus"


def load_corpus_model(module_path: Path) -> Tuple[Optional['TopoDS_Shape'], Dict[str, Any]]:
    """
    Load a corpus model from its Python module.
    
    Args:
        module_path: Path to the corpus model Python file
        
    Returns:
        Tuple of (shape, metadata) or (None, {}) if loading fails
    """
    spec = importlib.util.spec_from_file_location("corpus_model", module_path)
    if spec is None or spec.loader is None:
        return None, {}
    
    module = importlib.util.module_from_spec(spec)
    sys.modules["corpus_model"] = module
    spec.loader.exec_module(module)
    
    shape = module.create_model()
    metadata = module.get_metadata()
    
    return shape, metadata


def get_all_corpus_models() -> List[Tuple[str, str, Path]]:
    """
    Discover all corpus models.
    
    Returns:
        List of (category, model_name, path) tuples
    """
    models = []
    
    for category in CATEGORIES:
        category_path = CORPUS_DIR / category
        if not category_path.exists():
            continue
            
        for model_file in category_path.glob("*.py"):
            if model_file.name.startswith("_"):
                continue
            model_name = model_file.stem
            models.append((category, model_name, model_file))
    
    return models


def validate_shape_is_valid(shape: 'TopoDS_Shape') -> bool:
    """Check if shape is valid using BRepCheck."""
    analyzer = BRepCheck_Analyzer(shape)
    return analyzer.IsValid()


def export_to_stl(shape: 'TopoDS_Shape', output_path: Path) -> bool:
    """Export shape to STL format."""
    if KERNEL_AVAILABLE:
        options = ExportOptions(
            format=ExportFormat.STL,
            quality=ExportQuality.STANDARD,
            binary=True
        )
        result = ExportKernel.export_shape(shape, str(output_path), options)
        return result.success
    else:
        # Fallback: Use OCP directly
        try:
            from OCP.StlAPI import StlAPI_Writer
            writer = StlAPI_Writer()
            writer.Write(shape, output_path)
            return output_path.exists()
        except Exception:
            return False


def export_to_step(shape: 'TopoDS_Shape', output_path: Path) -> bool:
    """Export shape to STEP format."""
    if KERNEL_AVAILABLE:
        options = ExportOptions(
            format=ExportFormat.STEP,
            quality=ExportQuality.STANDARD
        )
        result = ExportKernel.export_shape(shape, str(output_path), options)
        return result.success
    else:
        # Fallback: Use OCP directly
        try:
            from OCP.STEPControl import STEPControl_Writer, STEPControl_AsIs
            writer = STEPControl_Writer()
            writer.Transfer(shape, STEPControl_AsIs)
            status = writer.Write(str(output_path))
            return status == 0 and output_path.exists()
        except Exception:
            return False


class CorpusTestResult:
    """Result of a corpus model test."""
    def __init__(self, category: str, model_name: str):
        self.category = category
        self.model_name = model_name
        self.load_success = False
        self.shape_valid = False
        self.stl_export_success = False
        self.step_export_success = False
        self.validation_passed = False
        self.is_manifold = False
        self.errors: List[str] = []
        self.metadata: Dict[str, Any] = {}


@pytest.fixture(scope="session")
def output_directory():
    """Create output directory for test artifacts."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    return OUTPUT_DIR


class TestCorpusModels:
    """Test class for corpus models."""
    
    @pytest.fixture(autouse=True)
    def setup_output_dir(self, output_directory):
        """Ensure output directory exists."""
        self.output_dir = output_directory
    
    @pytest.mark.parametrize("category,model_name,model_path", get_all_corpus_models())
    def test_corpus_model_load(self, category: str, model_name: str, model_path: Path):
        """Test that each corpus model can be loaded."""
        result = CorpusTestResult(category, model_name)
        
        # Load model
        shape, metadata = load_corpus_model(model_path)
        result.metadata = metadata
        
        assert shape is not None, f"Failed to load model: {model_path}"
        assert not shape.IsNull(), f"Shape is null: {model_path}"
        result.load_success = True
        
        # Validate shape
        assert validate_shape_is_valid(shape), f"Shape is invalid: {model_path}"
        result.shape_valid = True
    
    @pytest.mark.parametrize("category,model_name,model_path", get_all_corpus_models())
    def test_corpus_model_stl_export(self, category: str, model_name: str, model_path: Path):
        """Test STL export for each corpus model."""
        # Load model
        shape, metadata = load_corpus_model(model_path)
        assert shape is not None, f"Failed to load model: {model_path}"
        
        # Export to STL
        output_path = self.output_dir / category / f"{model_name}.stl"
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        success = export_to_stl(shape, output_path)
        assert success, f"STL export failed for {model_path}"
        assert output_path.exists(), f"STL file not created: {output_path}"
        assert output_path.stat().st_size > 0, f"STL file is empty: {output_path}"
    
    @pytest.mark.parametrize("category,model_name,model_path", get_all_corpus_models())
    def test_corpus_model_step_export(self, category: str, model_name: str, model_path: Path):
        """Test STEP export for each corpus model."""
        # Load model
        shape, metadata = load_corpus_model(model_path)
        assert shape is not None, f"Failed to load model: {model_path}"
        
        # Export to STEP
        output_path = self.output_dir / category / f"{model_name}.step"
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        success = export_to_step(shape, output_path)
        assert success, f"STEP export failed for {model_path}"
        assert output_path.exists(), f"STEP file not created: {output_path}"
        assert output_path.stat().st_size > 0, f"STEP file is empty: {output_path}"
    
    @pytest.mark.parametrize("category,model_name,model_path", get_all_corpus_models())
    def test_corpus_model_validation(self, category: str, model_name: str, model_path: Path):
        """Test export validation for each corpus model."""
        if not VALIDATOR_AVAILABLE:
            pytest.skip("ExportValidator not available")
        
        # Load model
        shape, metadata = load_corpus_model(model_path)
        assert shape is not None, f"Failed to load model: {model_path}"
        
        # Get expected issues from metadata
        expected_issues = metadata.get("expected_issues", [])
        
        # Validate
        options = ValidationOptions(
            check_manifold=True,
            check_free_bounds=True,
            check_degenerate=True
        )
        result = ExportValidator.validate_for_export(shape, options)
        
        # Check if validation matches expectations
        if "non_manifold" in expected_issues:
            # Expect non-manifold result
            pass  # Don't assert on manifold status
        else:
            # Should be manifold
            assert result.is_closed, f"Model should be manifold: {model_path}, issues: {result.issues}"
        
        # Check for unexpected errors
        error_types = [issue.check_type.value for issue in result.issues 
                       if issue.severity.value == "error"]
        
        for error_type in error_types:
            if error_type not in expected_issues:
                pytest.fail(f"Unexpected error '{error_type}' in {model_path}")


class TestCorpusDiscovery:
    """Tests for corpus discovery and structure."""
    
    def test_corpus_directory_exists(self):
        """Test that corpus directory exists."""
        assert CORPUS_DIR.exists(), f"Corpus directory not found: {CORPUS_DIR}"
    
    def test_corpus_readme_exists(self):
        """Test that corpus README exists."""
        readme_path = CORPUS_DIR / "README.md"
        assert readme_path.exists(), f"Corpus README not found: {readme_path}"
    
    def test_all_categories_exist(self):
        """Test that all category directories exist."""
        for category in CATEGORIES:
            category_path = CORPUS_DIR / category
            assert category_path.exists(), f"Category directory not found: {category_path}"
    
    def test_minimum_model_count(self):
        """Test that we have at least 10 corpus models."""
        models = get_all_corpus_models()
        assert len(models) >= 10, f"Expected at least 10 corpus models, found {len(models)}"
    
    def test_all_models_have_required_functions(self):
        """Test that all corpus models have create_model and get_metadata functions."""
        models = get_all_corpus_models()
        
        for category, model_name, model_path in models:
            spec = importlib.util.spec_from_file_location("test_model", model_path)
            assert spec is not None, f"Could not load spec for {model_path}"
            
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            
            assert hasattr(module, "create_model"), f"Missing create_model() in {model_path}"
            assert hasattr(module, "get_metadata"), f"Missing get_metadata() in {model_path}"
            assert callable(module.create_model), f"create_model not callable in {model_path}"
            assert callable(module.get_metadata), f"get_metadata not callable in {model_path}"


class TestCorpusMetadata:
    """Tests for corpus model metadata."""
    
    @pytest.mark.parametrize("category,model_name,model_path", get_all_corpus_models())
    def test_metadata_structure(self, category: str, model_name: str, model_path: Path):
        """Test that metadata has required fields."""
        _, metadata = load_corpus_model(model_path)
        
        required_fields = ["name", "category", "description", "tags"]
        for field in required_fields:
            assert field in metadata, f"Missing metadata field '{field}' in {model_path}"
    
    @pytest.mark.parametrize("category,model_name,model_path", get_all_corpus_models())
    def test_metadata_category_matches(self, category: str, model_name: str, model_path: Path):
        """Test that metadata category matches directory structure."""
        _, metadata = load_corpus_model(model_path)
        
        assert metadata.get("category") == category, \
            f"Metadata category '{metadata.get('category')}' doesn't match directory '{category}'"
    
    @pytest.mark.parametrize("category,model_name,model_path", get_all_corpus_models())
    def test_metadata_has_bounds(self, category: str, model_name: str, model_path: Path):
        """Test that metadata includes bounds information."""
        _, metadata = load_corpus_model(model_path)
        
        # Bounds are optional but recommended
        if "bounds" in metadata:
            bounds = metadata["bounds"]
            assert "min" in bounds, f"Missing 'min' in bounds for {model_path}"
            assert "max" in bounds, f"Missing 'max' in bounds for {model_path}"


def test_corpus_summary():
    """Generate a summary of all corpus models."""
    models = get_all_corpus_models()
    
    print(f"\n{'='*60}")
    print("CORPUS SUMMARY")
    print(f"{'='*60}")
    print(f"Total models: {len(models)}")
    print(f"\nBy category:")
    
    category_counts: Dict[str, int] = {}
    for category, _, _ in models:
        category_counts[category] = category_counts.get(category, 0) + 1
    
    for category, count in sorted(category_counts.items()):
        print(f"  {category}: {count}")
    
    print(f"\nModels:")
    for category, model_name, _ in sorted(models):
        print(f"  - {category}/{model_name}")
    
    print(f"{'='*60}\n")
    
    # Always pass - this is just for information
    assert True
