"""
Comprehensive import regression tests for MashCAD.

Tests all major import paths after package refactoring:
- modeling package (circular import fix for brep_cache)
- gui package (after split into gui/widgets, gui/viewport, etc.)
- sketcher package
- Integration imports (gui -> modeling -> sketcher)

This test validates the fix for the circular import issue where
modeling/body.py used `import modeling.brep_cache as brep_cache`
during package initialization.
"""

import sys
import pytest
from typing import List, Tuple


def _clear_module_cache(prefixes: List[str]):
    """Remove cached modules matching any prefix to force fresh import."""
    for mod in list(sys.modules.keys()):
        if any(mod.startswith(p) for p in prefixes):
            del sys.modules[mod]


class TestModelingImports:
    """Test modeling package imports (circular import fix)."""

    def test_modeling_document_import(self):
        """Verify modeling.Document can be imported without AttributeError."""
        _clear_module_cache(['modeling'])
        from modeling import Document
        assert Document is not None

    def test_modeling_body_import(self):
        """Verify modeling.Body can be imported."""
        _clear_module_cache(['modeling'])
        from modeling import Body
        assert Body is not None

    def test_modeling_brep_cache_via_relative_import(self):
        """Verify modeling.body uses relative import for brep_cache."""
        _clear_module_cache(['modeling'])
        from modeling.body import Body
        assert Body is not None

    def test_modeling_package_exposes_brep_cache(self):
        """Verify brep_cache is accessible from modeling package facade."""
        _clear_module_cache(['modeling'])
        from modeling import brep_cache
        assert brep_cache is not None

    def test_modeling_all_features_importable(self):
        """Verify all feature classes can be imported from modeling."""
        _clear_module_cache(['modeling'])
        from modeling import (
            Feature, FeatureType,
            ExtrudeFeature, PushPullFeature,
            RevolveFeature,
            FilletFeature, ChamferFeature,
            PatternFeature,
            BooleanFeature,
            TransformFeature,
            LoftFeature, SweepFeature, ShellFeature, HoleFeature,
            DraftFeature, SplitFeature, ThreadFeature, HollowFeature,
            NSidedPatchFeature, SurfaceTextureFeature, PrimitiveFeature,
            LatticeFeature,
            ImportFeature,
        )
        assert Feature is not None

    def test_modeling_helper_modules(self):
        """Verify OCP helpers and boolean engine are importable."""
        _clear_module_cache(['modeling'])
        from modeling import (
            OCPExtrudeHelper, OCPFilletHelper, OCPChamferHelper,
            BooleanEngineV4,
            ShapeNamingService, ShapeID, ShapeType, OperationRecord,
            FeatureDependencyGraph, get_dependency_graph,
            OperationResult, BooleanResult, ResultStatus,
        )
        assert BooleanEngineV4 is not None


class TestSketcherImports:
    """Test sketcher package imports."""

    def test_sketcher_sketch_import(self):
        """Verify sketcher.Sketch can be imported."""
        _clear_module_cache(['sketcher', 'modeling'])
        from sketcher.sketch import Sketch
        assert Sketch is not None

    def test_sketch_via_modeling(self):
        """Verify Sketch is re-exported via modeling package."""
        _clear_module_cache(['sketcher', 'modeling'])
        from modeling import Sketch
        assert Sketch is not None


class TestGuiImports:
    """Test gui package imports after refactoring."""

    def test_gui_main_window_import(self):
        """Verify MainWindow can be imported from gui."""
        _clear_module_cache(['gui', 'modeling', 'sketcher'])
        from gui.main_window import MainWindow
        assert MainWindow is not None

    def test_gui_widgets_import(self):
        """Verify gui.widgets submodules are importable."""
        _clear_module_cache(['gui', 'modeling'])
        # Use an existing widget module
        from gui.widgets.notification import NotificationWidget
        assert NotificationWidget is not None

    def test_gui_viewport_import(self):
        """Verify gui.viewport submodules are importable."""
        _clear_module_cache(['gui', 'modeling'])
        # These may have external dependencies (vtk, pyvista), so we test import structure
        try:
            from gui.viewport.transform_gizmo_v3 import TransformGizmoV3
            assert TransformGizmoV3 is not None
        except ImportError:
            # External dependency missing - acceptable in minimal test env
            pytest.skip("External dependency (vtk/pyvista) not available")


class TestIntegrationImports:
    """Test full import chain from main.py to all packages."""

    def test_main_to_gui_to_modeling_chain(self):
        """
        Verify the full import chain: main -> gui.main_window -> modeling.
        This was the original failure path.
        """
        _clear_module_cache(['gui', 'modeling', 'sketcher', 'config', 'meshconverter'])
        
        # Step 1: modeling must be importable first (gui imports from it)
        from modeling import Document
        assert Document is not None
        
        # Step 2: gui.main_window imports Document from modeling
        from gui.main_window import MainWindow
        assert MainWindow is not None

    def test_all_modeling_submodules_importable(self):
        """Verify all modeling submodules have valid import structure."""
        _clear_module_cache(['modeling'])
        
        submodule_imports = [
            'modeling.body',
            'modeling.document',
            'modeling.component',
            'modeling.brep_cache',
            'modeling.cad_tessellator',
            'modeling.boolean_engine_v4',
            'modeling.ocp_helpers',
            'modeling.feature_dependency',
            'modeling.tnp_system',
            'modeling.result_types',
            'modeling.geometry_utils',
            'modeling.shape_builders',
            'modeling.feature_operations',
            'modeling.body_state',
            'modeling.geometry_validator',
            'modeling.geometry_healer',
            'modeling.nurbs',
            'modeling.step_io',
            'modeling.mesh_converter',
        ]
        
        import_errors = []
        for module_name in submodule_imports:
            try:
                __import__(module_name)
            except ImportError as e:
                # Only fail on AttributeError (circular import) or missing module
                if 'AttributeError' in str(e) or module_name.split('.')[-1] in str(e):
                    import_errors.append((module_name, str(e)))
        
        # Allow external dependency failures but not structural import errors
        critical_errors = [
            (mod, err) for mod, err in import_errors
            if 'AttributeError' in err or 'has no attribute' in err
        ]
        
        assert len(critical_errors) == 0, f"Critical import errors: {critical_errors}"


class TestNoCircularImports:
    """Specific tests to prevent circular import regressions."""

    def test_no_modeling_brep_cache_attribute_error(self):
        """
        Verify the original bug is fixed:
        AttributeError: module 'modeling' has no attribute 'brep_cache'
        """
        _clear_module_cache(['modeling'])
        
        # This exact import sequence triggered the original bug
        try:
            from modeling.body import Body, HAS_OCP, HAS_BUILD123D
            assert Body is not None
        except AttributeError as e:
            if 'brep_cache' in str(e):
                pytest.fail(f"Circular import bug not fixed: {e}")
            raise

    def test_relative_import_used_in_body(self):
        """Verify body.py uses relative import for brep_cache."""
        import inspect
        from modeling import body
        
        source = inspect.getsource(body)
        # Should contain relative import, not absolute
        assert 'from . import brep_cache' in source or 'from modeling import brep_cache' in source
        # Should NOT contain the problematic pattern
        assert 'import modeling.brep_cache as brep_cache' not in source


if __name__ == '__main__':
    pytest.main([__file__, '-v', '--tb=short'])
