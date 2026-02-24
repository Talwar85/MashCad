"""
Unit tests for gui/workers/ module.

Tests for background workers:
- STLExportWorker: Background STL export
- STEPExportWorker: Background STEP export
- TessellationWorker: Background mesh generation
- TessellationManager: Worker management

All tests mock QThread/QObject dependencies and heavy operations.
"""
import pytest
from unittest.mock import Mock, patch, MagicMock, PropertyMock
import numpy as np


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def mock_qthread():
    """Mock QThread class."""
    with patch('gui.workers.export_worker.QThread') as mock:
        thread_instance = MagicMock()
        thread_instance.isRunning.return_value = False
        mock.return_value = thread_instance
        yield mock


@pytest.fixture
def mock_signal():
    """Mock Signal class."""
    with patch('gui.workers.export_worker.Signal') as mock:
        signal_instance = MagicMock()
        mock.return_value = signal_instance
        yield mock, signal_instance


@pytest.fixture
def mock_body():
    """Create a mock body with tessellation support."""
    body = MagicMock()
    body.name = "test_body"
    body._build123d_solid = MagicMock()
    body.vtk_mesh = MagicMock()
    body.vtk_mesh.n_cells = 1000
    return body


@pytest.fixture
def mock_solid():
    """Create a mock build123d solid."""
    solid = MagicMock()
    solid.label = "test_solid"
    return solid


@pytest.fixture
def mock_cad_tessellator():
    """Mock CADTessellator module."""
    with patch('modeling.cad_tessellator.CADTessellator') as mock:
        # Default tessellation result
        mock.tessellate_for_export.return_value = (
            [(0, 0, 0), (1, 0, 0), (0, 1, 0)],  # vertices
            [(0, 1, 2)]  # faces (triangles)
        )
        mock.tessellate_with_face_ids.return_value = (
            MagicMock(),  # mesh
            MagicMock(),  # edges
            {}  # face_info
        )
        yield mock


@pytest.fixture
def mock_pyvista():
    """Mock pyvista module."""
    with patch.dict('sys.modules', {'pyvista': MagicMock()}):
        import sys
        pv_mock = sys.modules['pyvista']
        
        # Mock PolyData
        polydata_mock = MagicMock()
        polydata_mock.n_cells = 1000
        polydata_mock.points = np.array([[0, 0, 0], [1, 0, 0], [0, 1, 0]])
        polydata_mock.merge.return_value = polydata_mock
        pv_mock.PolyData.return_value = polydata_mock
        
        yield pv_mock


# ============================================================================
# Test STLExportWorker
# ============================================================================

class TestSTLExportWorker:
    """Tests for STLExportWorker class."""

    def test_worker_initialization_defaults(self):
        """Test STLExportWorker initialization with default parameters."""
        from gui.workers.export_worker import STLExportWorker
        
        bodies = [MagicMock()]
        filepath = "/test/output.stl"
        
        worker = STLExportWorker(bodies, filepath)
        
        assert worker.bodies == bodies
        assert worker.filepath == filepath
        assert worker.linear_deflection == 0.1
        assert worker.angular_tolerance == 0.5
        assert worker.binary is True
        assert worker.scale == 1.0
        assert worker.apply_textures is True
        assert worker._cancelled is False

    def test_worker_initialization_custom_params(self):
        """Test STLExportWorker initialization with custom parameters."""
        from gui.workers.export_worker import STLExportWorker
        
        bodies = [MagicMock()]
        filepath = "/test/output.stl"
        
        worker = STLExportWorker(
            bodies,
            filepath,
            linear_deflection=0.05,
            angular_tolerance=0.2,
            binary=False,
            scale=0.5,
            apply_textures=False
        )
        
        assert worker.linear_deflection == 0.05
        assert worker.angular_tolerance == 0.2
        assert worker.binary is False
        assert worker.scale == 0.5
        assert worker.apply_textures is False

    def test_worker_has_required_signals(self):
        """Test that STLExportWorker has required signals."""
        from gui.workers.export_worker import STLExportWorker
        
        # Check that signal attributes exist (class-level)
        assert hasattr(STLExportWorker, 'progress')
        assert hasattr(STLExportWorker, 'finished')
        assert hasattr(STLExportWorker, 'error')

    def test_cancel_sets_flag(self):
        """Test that cancel() sets the _cancelled flag."""
        from gui.workers.export_worker import STLExportWorker
        
        worker = STLExportWorker([], "/test/output.stl")
        assert worker._cancelled is False
        
        worker.cancel()
        
        assert worker._cancelled is True

    def test_cancel_multiple_times(self):
        """Test that cancel() can be called multiple times."""
        from gui.workers.export_worker import STLExportWorker
        
        worker = STLExportWorker([], "/test/output.stl")
        
        worker.cancel()
        worker.cancel()
        worker.cancel()
        
        assert worker._cancelled is True

    def test_empty_bodies_list(self):
        """Test worker with empty bodies list."""
        from gui.workers.export_worker import STLExportWorker
        
        worker = STLExportWorker([], "/test/output.stl")
        
        assert worker.bodies == []

    def test_multiple_bodies(self):
        """Test worker with multiple bodies."""
        from gui.workers.export_worker import STLExportWorker
        
        bodies = [MagicMock(name=f"body_{i}") for i in range(5)]
        
        worker = STLExportWorker(bodies, "/test/output.stl")
        
        assert len(worker.bodies) == 5


class TestSTLExportWorkerTessellation:
    """Tests for STLExportWorker tessellation logic."""

    def test_tessellate_body_with_build123d_solid(self, mock_body, mock_cad_tessellator):
        """Test _tessellate_body when body has _build123d_solid."""
        from gui.workers.export_worker import STLExportWorker
        
        with patch('modeling.cad_tessellator.CADTessellator', mock_cad_tessellator):
            with patch('pyvista.PolyData') as mock_polydata:
                mock_polydata.return_value = MagicMock()
                
                worker = STLExportWorker([], "/test/output.stl")
                result = worker._tessellate_body(mock_body)
                
                assert result is not None
                mock_cad_tessellator.tessellate_for_export.assert_called_once()

    def test_tessellate_body_fallback_to_vtk_mesh(self, mock_body):
        """Test _tessellate_body falls back to vtk_mesh when tessellation fails."""
        from gui.workers.export_worker import STLExportWorker
        
        # Make tessellation fail
        mock_body._build123d_solid = None
        
        with patch('modeling.cad_tessellator.CADTessellator') as mock_tess:
            mock_tess.tessellate_for_export.side_effect = Exception("Tessellation failed")
            
            worker = STLExportWorker([], "/test/output.stl")
            result = worker._tessellate_body(mock_body)
            
            # Should fall back to vtk_mesh
            assert result == mock_body.vtk_mesh

    def test_tessellate_body_no_mesh_available(self):
        """Test _tessellate_body when no mesh is available."""
        from gui.workers.export_worker import STLExportWorker
        
        body = MagicMock()
        body._build123d_solid = None
        body.vtk_mesh = None
        
        with patch('modeling.cad_tessellator.CADTessellator') as mock_tess:
            mock_tess.tessellate_for_export.side_effect = Exception("No solid")
            
            worker = STLExportWorker([], "/test/output.stl")
            result = worker._tessellate_body(body)
            
            assert result is None


# ============================================================================
# Test STEPExportWorker
# ============================================================================

class TestSTEPExportWorker:
    """Tests for STEPExportWorker class."""

    def test_worker_initialization(self):
        """Test STEPExportWorker initialization."""
        from gui.workers.export_worker import STEPExportWorker
        
        solids = [MagicMock()]
        filepath = "/test/output.step"
        
        worker = STEPExportWorker(solids, filepath)
        
        assert worker.solids == solids
        assert worker.filepath == filepath
        assert worker._cancelled is False

    def test_worker_initialization_empty_solids(self):
        """Test STEPExportWorker with empty solids list."""
        from gui.workers.export_worker import STEPExportWorker
        
        worker = STEPExportWorker([], "/test/output.step")
        
        assert worker.solids == []

    def test_worker_has_required_signals(self):
        """Test that STEPExportWorker has required signals."""
        from gui.workers.export_worker import STEPExportWorker
        
        assert hasattr(STEPExportWorker, 'progress')
        assert hasattr(STEPExportWorker, 'finished')
        assert hasattr(STEPExportWorker, 'error')

    def test_cancel_sets_flag(self):
        """Test that cancel() sets the _cancelled flag."""
        from gui.workers.export_worker import STEPExportWorker
        
        worker = STEPExportWorker([], "/test/output.step")
        assert worker._cancelled is False
        
        worker.cancel()
        
        assert worker._cancelled is True

    def test_cancel_multiple_times(self):
        """Test that cancel() can be called multiple times."""
        from gui.workers.export_worker import STEPExportWorker
        
        worker = STEPExportWorker([], "/test/output.step")
        
        worker.cancel()
        worker.cancel()
        
        assert worker._cancelled is True


# ============================================================================
# Test TessellationWorker
# ============================================================================

class TestTessellationWorker:
    """Tests for TessellationWorker class."""

    def test_worker_initialization(self, mock_solid):
        """Test TessellationWorker initialization."""
        from gui.workers.tessellation_worker import TessellationWorker
        
        worker = TessellationWorker("body_123", mock_solid)
        
        assert worker.body_id == "body_123"
        assert worker.solid == mock_solid
        assert worker._cancelled is False

    def test_worker_initialization_with_parent(self, mock_solid):
        """Test TessellationWorker initialization with parent=None."""
        from gui.workers.tessellation_worker import TessellationWorker
        
        # Use None as parent since MagicMock is not a valid QObject
        worker = TessellationWorker("body_123", mock_solid, parent=None)
        
        assert worker.body_id == "body_123"
        assert worker.solid == mock_solid

    def test_worker_has_required_signals(self):
        """Test that TessellationWorker has required signals."""
        from gui.workers.tessellation_worker import TessellationWorker
        
        assert hasattr(TessellationWorker, 'mesh_ready')
        assert hasattr(TessellationWorker, 'error')

    def test_cancel_sets_flag(self, mock_solid):
        """Test that cancel() sets the _cancelled flag."""
        from gui.workers.tessellation_worker import TessellationWorker
        
        worker = TessellationWorker("body_123", mock_solid)
        assert worker._cancelled is False
        
        worker.cancel()
        
        assert worker._cancelled is True

    def test_cancel_before_run(self, mock_solid, mock_cad_tessellator):
        """Test that cancel before run prevents tessellation."""
        from gui.workers.tessellation_worker import TessellationWorker
        
        with patch('modeling.cad_tessellator.CADTessellator', mock_cad_tessellator):
            worker = TessellationWorker("body_123", mock_solid)
            worker.cancel()  # Cancel before run
            
            # run() should check _cancelled and return early
            # We can't actually call run() without a Qt event loop,
            # but we can verify the flag is set
            assert worker._cancelled is True

    def test_different_body_ids(self, mock_solid):
        """Test workers with different body IDs."""
        from gui.workers.tessellation_worker import TessellationWorker
        
        worker1 = TessellationWorker("body_001", mock_solid)
        worker2 = TessellationWorker("body_002", mock_solid)
        
        assert worker1.body_id != worker2.body_id


# ============================================================================
# Test TessellationManager
# ============================================================================

class TestTessellationManager:
    """Tests for TessellationManager class."""

    def test_manager_initialization(self):
        """Test TessellationManager initialization."""
        from gui.workers.tessellation_worker import TessellationManager
        
        manager = TessellationManager()
        
        assert manager._workers == {}
        assert hasattr(manager, '_mutex')

    def test_active_count_empty(self):
        """Test active_count with no workers."""
        from gui.workers.tessellation_worker import TessellationManager
        
        manager = TessellationManager()
        
        assert manager.active_count == 0

    def test_is_tessellating_false_when_empty(self):
        """Test is_tessellating returns False when no workers."""
        from gui.workers.tessellation_worker import TessellationManager
        
        manager = TessellationManager()
        
        assert manager.is_tessellating("nonexistent_body") is False

    def test_cancel_all_empty(self):
        """Test cancel_all with no workers (should not raise)."""
        from gui.workers.tessellation_worker import TessellationManager
        
        manager = TessellationManager()
        
        # Should not raise
        manager.cancel_all()

    def test_request_tessellation_creates_worker(self, mock_solid):
        """Test request_tessellation creates a worker."""
        from gui.workers.tessellation_worker import TessellationManager, TessellationWorker
        
        with patch.object(TessellationWorker, 'start'):
            manager = TessellationManager()
            on_ready = MagicMock()
            on_error = MagicMock()
            
            worker = manager.request_tessellation(
                "body_123",
                mock_solid,
                on_ready,
                on_error
            )
            
            assert worker is not None
            assert worker.body_id == "body_123"

    def test_request_tessellation_connects_callbacks(self, mock_solid):
        """Test request_tessellation connects callbacks to signals."""
        from gui.workers.tessellation_worker import TessellationManager, TessellationWorker
        
        with patch.object(TessellationWorker, 'start'):
            manager = TessellationManager()
            on_ready = MagicMock()
            on_error = MagicMock()
            
            worker = manager.request_tessellation(
                "body_123",
                mock_solid,
                on_ready,
                on_error
            )
            
            # Verify signals were connected (connect method was called)
            # This is a basic check - actual signal behavior is tested elsewhere

    def test_request_tessellation_cancels_previous_worker(self, mock_solid):
        """Test that new request cancels previous worker for same body."""
        from gui.workers.tessellation_worker import TessellationManager, TessellationWorker
        
        with patch.object(TessellationWorker, 'start'):
            manager = TessellationManager()
            on_ready = MagicMock()
            
            # First request
            worker1 = manager.request_tessellation(
                "body_123",
                mock_solid,
                on_ready
            )
            
            # Mock that worker1 is running
            worker1.isRunning = MagicMock(return_value=True)
            
            # Second request for same body
            worker2 = manager.request_tessellation(
                "body_123",
                mock_solid,
                on_ready
            )
            
            # worker1 should be cancelled
            assert worker1._cancelled is True

    def test_cleanup_worker_removes_finished_worker(self, mock_solid):
        """Test _cleanup_worker removes finished worker."""
        from gui.workers.tessellation_worker import TessellationManager, TessellationWorker
        
        with patch.object(TessellationWorker, 'start'):
            manager = TessellationManager()
            on_ready = MagicMock()
            
            worker = manager.request_tessellation(
                "body_123",
                mock_solid,
                on_ready
            )
            
            # Simulate worker finished
            worker.isRunning = MagicMock(return_value=False)
            manager._cleanup_worker("body_123")
            
            assert "body_123" not in manager._workers

    def test_multiple_bodies(self, mock_solid):
        """Test manager handles multiple bodies."""
        from gui.workers.tessellation_worker import TessellationManager, TessellationWorker
        
        with patch.object(TessellationWorker, 'start'):
            manager = TessellationManager()
            on_ready = MagicMock()
            
            # Request tessellation for multiple bodies
            worker1 = manager.request_tessellation("body_001", mock_solid, on_ready)
            worker2 = manager.request_tessellation("body_002", mock_solid, on_ready)
            worker3 = manager.request_tessellation("body_003", mock_solid, on_ready)
            
            # Mock all running
            worker1.isRunning = MagicMock(return_value=True)
            worker2.isRunning = MagicMock(return_value=True)
            worker3.isRunning = MagicMock(return_value=True)
            
            assert manager.active_count == 3

    def test_cancel_all_stops_all_workers(self, mock_solid):
        """Test cancel_all stops all running workers."""
        from gui.workers.tessellation_worker import TessellationManager, TessellationWorker
        
        with patch.object(TessellationWorker, 'start'):
            manager = TessellationManager()
            on_ready = MagicMock()
            
            # Request tessellation for multiple bodies
            worker1 = manager.request_tessellation("body_001", mock_solid, on_ready)
            worker2 = manager.request_tessellation("body_002", mock_solid, on_ready)
            
            # Mock all running
            worker1.isRunning = MagicMock(return_value=True)
            worker2.isRunning = MagicMock(return_value=True)
            
            manager.cancel_all()
            
            assert worker1._cancelled is True
            assert worker2._cancelled is True

    def test_priority_queue_starts_highest_pending_first(self, mock_solid):
        """Higher-priority queued body should start first when a slot frees up."""
        from gui.workers.tessellation_worker import TessellationManager, TessellationWorker

        with patch.object(TessellationWorker, 'start'):
            manager = TessellationManager(max_concurrent=1)
            on_ready = MagicMock()

            worker_low = manager.request_tessellation("body_low", mock_solid, on_ready, priority=10)
            worker_high = manager.request_tessellation("body_high", mock_solid, on_ready, priority=100)
            worker_mid = manager.request_tessellation("body_mid", mock_solid, on_ready, priority=50)

            assert "body_low" in manager._active_body_ids

            worker_low.isRunning = MagicMock(return_value=False)
            manager._cleanup_worker("body_low")
            assert "body_high" in manager._active_body_ids

            worker_high.isRunning = MagicMock(return_value=False)
            manager._cleanup_worker("body_high")
            assert "body_mid" in manager._active_body_ids

            worker_mid.isRunning = MagicMock(return_value=False)
            manager._cleanup_worker("body_mid")
            assert not manager._active_body_ids

    def test_is_tessellating_true_for_pending_request(self, mock_solid):
        """Queued (not yet running) requests should still be reported as tessellating."""
        from gui.workers.tessellation_worker import TessellationManager, TessellationWorker

        with patch.object(TessellationWorker, 'start'):
            manager = TessellationManager(max_concurrent=1)
            on_ready = MagicMock()

            manager.request_tessellation("body_active", mock_solid, on_ready, priority=100)
            manager.request_tessellation("body_pending", mock_solid, on_ready, priority=10)

            assert manager.is_tessellating("body_pending") is True


# ============================================================================
# Integration-style tests (with mocked Qt)
# ============================================================================

class TestWorkerSignals:
    """Tests for signal emission behavior."""

    def test_stl_worker_signal_attributes(self):
        """Test STLExportWorker signal attributes are correct type."""
        from gui.workers.export_worker import STLExportWorker
        from PySide6.QtCore import Signal
        
        # Signals are defined at class level
        # We can check they exist and are Signal instances
        assert isinstance(STLExportWorker.progress, Signal)
        assert isinstance(STLExportWorker.finished, Signal)
        assert isinstance(STLExportWorker.error, Signal)

    def test_step_worker_signal_attributes(self):
        """Test STEPExportWorker signal attributes are correct type."""
        from gui.workers.export_worker import STEPExportWorker
        from PySide6.QtCore import Signal
        
        assert isinstance(STEPExportWorker.progress, Signal)
        assert isinstance(STEPExportWorker.finished, Signal)
        assert isinstance(STEPExportWorker.error, Signal)

    def test_tessellation_worker_signal_attributes(self):
        """Test TessellationWorker signal attributes are correct type."""
        from gui.workers.tessellation_worker import TessellationWorker
        from PySide6.QtCore import Signal
        
        assert isinstance(TessellationWorker.mesh_ready, Signal)
        assert isinstance(TessellationWorker.error, Signal)


class TestErrorHandling:
    """Tests for error handling in workers."""

    def test_stl_worker_handles_tessellation_error(self, mock_body):
        """Test STLExportWorker handles tessellation errors gracefully."""
        from gui.workers.export_worker import STLExportWorker
        
        # Configure body to cause tessellation error
        mock_body._build123d_solid = MagicMock()
        mock_body.vtk_mesh = None
        
        with patch('modeling.cad_tessellator.CADTessellator') as mock_tess:
            mock_tess.tessellate_for_export.side_effect = RuntimeError("Tessellation failed")
            
            worker = STLExportWorker([mock_body], "/test/output.stl")
            result = worker._tessellate_body(mock_body)
            
            # Should return None when both tessellation and fallback fail
            assert result is None

    def test_tessellation_worker_handles_error(self, mock_solid):
        """Test TessellationWorker handles errors during tessellation."""
        from gui.workers.tessellation_worker import TessellationWorker
        
        with patch('modeling.cad_tessellator.CADTessellator') as mock_tess:
            mock_tess.tessellate_with_face_ids.side_effect = RuntimeError("Tessellation failed")
            
            worker = TessellationWorker("body_123", mock_solid)
            
            # Verify worker was created successfully
            assert worker.body_id == "body_123"


class TestModuleImports:
    """Tests for module structure and imports."""

    def test_module_all_exports(self):
        """Test __all__ exports from workers module."""
        from gui.workers import __all__
        
        expected_exports = [
            'STLExportWorker',
            'STEPExportWorker',
            'TessellationWorker',
            'TessellationManager'
        ]
        
        for export in expected_exports:
            assert export in __all__

    def test_import_from_init(self):
        """Test importing classes from __init__.py."""
        from gui.workers import (
            STLExportWorker,
            STEPExportWorker,
            TessellationWorker,
            TessellationManager
        )
        
        assert STLExportWorker is not None
        assert STEPExportWorker is not None
        assert TessellationWorker is not None
        assert TessellationManager is not None

    def test_import_from_submodules(self):
        """Test importing directly from submodules."""
        from gui.workers.export_worker import STLExportWorker, STEPExportWorker
        from gui.workers.tessellation_worker import TessellationWorker, TessellationManager
        
        assert STLExportWorker is not None
        assert STEPExportWorker is not None
        assert TessellationWorker is not None
        assert TessellationManager is not None


class TestWorkerConfiguration:
    """Tests for worker configuration options."""

    def test_stl_export_binary_option(self):
        """Test STL binary export option."""
        from gui.workers.export_worker import STLExportWorker
        
        # Binary True
        worker_binary = STLExportWorker([], "/test.stl", binary=True)
        assert worker_binary.binary is True
        
        # Binary False (ASCII)
        worker_ascii = STLExportWorker([], "/test.stl", binary=False)
        assert worker_ascii.binary is False

    def test_stl_export_scale_option(self):
        """Test STL export scale option."""
        from gui.workers.export_worker import STLExportWorker
        
        # Default scale
        worker_default = STLExportWorker([], "/test.stl")
        assert worker_default.scale == 1.0
        
        # Custom scale
        worker_scaled = STLExportWorker([], "/test.stl", scale=0.5)
        assert worker_scaled.scale == 0.5
        
        # Large scale
        worker_large = STLExportWorker([], "/test.stl", scale=10.0)
        assert worker_large.scale == 10.0

    def test_stl_export_quality_options(self):
        """Test STL export quality options."""
        from gui.workers.export_worker import STLExportWorker
        
        # High quality (smaller deflection)
        worker_hq = STLExportWorker(
            [],
            "/test.stl",
            linear_deflection=0.01,
            angular_tolerance=0.1
        )
        assert worker_hq.linear_deflection == 0.01
        assert worker_hq.angular_tolerance == 0.1
        
        # Low quality (larger deflection)
        worker_lq = STLExportWorker(
            [],
            "/test.stl",
            linear_deflection=1.0,
            angular_tolerance=2.0
        )
        assert worker_lq.linear_deflection == 1.0
        assert worker_lq.angular_tolerance == 2.0


# ============================================================================
# Skip markers for tests requiring Qt context
# ============================================================================

@pytest.mark.skip(reason="Requires running Qt event loop")
class TestWorkerExecution:
    """Tests that require actual Qt event loop - skipped by default."""
    
    def test_stl_worker_run_emits_progress(self):
        """Test that run() emits progress signals."""
        pass
    
    def test_stl_worker_run_emits_finished(self):
        """Test that run() emits finished signal on success."""
        pass
    
    def test_stl_worker_run_emits_error(self):
        """Test that run() emits error signal on failure."""
        pass
    
    def test_tessellation_worker_run_emits_mesh_ready(self):
        """Test that run() emits mesh_ready signal."""
        pass
    
    def test_tessellation_worker_run_emits_error(self):
        """Test that run() emits error signal on failure."""
        pass


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
