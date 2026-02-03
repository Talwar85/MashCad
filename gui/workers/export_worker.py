"""
MashCAD - Async Export Worker
=============================

PERFORMANCE (Phase 6): Background thread für File-Export.

Problem: STL/STEP Export mit großen Meshes blockiert die UI (Freeze).
Lösung: QThread-basierter Worker mit Progress-Callbacks.

Features:
- Non-blocking Export (UI bleibt responsiv)
- Progress-Updates (für ProgressBar)
- Cancel-Support
- Error-Handling mit Signal

Autor: Claude (Performance Optimization)
Datum: 2026-01-30
"""

import numpy as np
from typing import List, Optional, Callable
from loguru import logger

from PySide6.QtCore import QThread, Signal


class STLExportWorker(QThread):
    """
    Background Worker für STL Export.

    Signals:
        progress: (int, str) - Prozent (0-100) und Status-Text
        finished: str - Erfolgreicher Export, enthält Dateipfad
        error: str - Fehlermeldung bei Fehler

    Usage:
        worker = STLExportWorker(bodies, filepath, quality_settings)
        worker.progress.connect(update_progress_bar)
        worker.finished.connect(on_export_complete)
        worker.error.connect(on_export_error)
        worker.start()
    """

    progress = Signal(int, str)
    finished = Signal(str)
    error = Signal(str)

    def __init__(
        self,
        bodies: List,
        filepath: str,
        linear_deflection: float = 0.1,
        angular_tolerance: float = 0.5,
        binary: bool = True,
        scale: float = 1.0,
        apply_textures: bool = True
    ):
        super().__init__()
        self.bodies = bodies
        self.filepath = filepath
        self.linear_deflection = linear_deflection
        self.angular_tolerance = angular_tolerance
        self.binary = binary
        self.scale = scale
        self.apply_textures = apply_textures
        self._cancelled = False

    def cancel(self):
        """Request cancellation of export."""
        self._cancelled = True
        logger.info("STL Export cancelled by user")

    def run(self):
        """Main export logic (runs in background thread)."""
        try:
            import pyvista as pv

            merged_polydata = None
            total_bodies = len(self.bodies)

            for i, body in enumerate(self.bodies):
                if self._cancelled:
                    self.error.emit("Export abgebrochen")
                    return

                # Progress: Tessellating body N of M
                progress_pct = int((i / total_bodies) * 80)  # 0-80% for tessellation
                self.progress.emit(progress_pct, f"Tesselliere Body {i + 1}/{total_bodies}...")

                mesh_to_add = self._tessellate_body(body)

                if mesh_to_add is not None:
                    if merged_polydata is None:
                        merged_polydata = mesh_to_add
                    else:
                        merged_polydata = merged_polydata.merge(mesh_to_add)

            if self._cancelled:
                self.error.emit("Export abgebrochen")
                return

            if merged_polydata is None:
                self.error.emit("Keine Mesh-Daten generiert")
                return

            # Apply scale if needed
            self.progress.emit(85, "Skaliere Mesh...")
            if abs(self.scale - 1.0) > 1e-6:
                merged_polydata.points *= self.scale

            # Save to file
            self.progress.emit(90, "Schreibe Datei...")
            merged_polydata.save(self.filepath, binary=self.binary)

            self.progress.emit(100, "Fertig!")
            n_triangles = merged_polydata.n_cells
            self.finished.emit(f"{self.filepath} ({n_triangles:,} Dreiecke)")

        except Exception as e:
            import traceback
            traceback.print_exc()
            self.error.emit(f"Export Fehler: {str(e)}")

    def _tessellate_body(self, body) -> Optional['pv.PolyData']:
        """Tessellate a single body (may include texture application)."""
        import pyvista as pv
        from modeling.cad_tessellator import CADTessellator

        mesh_to_add = None

        try:
            # Phase 6: Performance - Use export cache
            if hasattr(body, '_build123d_solid') and body._build123d_solid:
                verts, faces = CADTessellator.tessellate_for_export(
                    body._build123d_solid,
                    linear_deflection=self.linear_deflection,
                    angular_tolerance=self.angular_tolerance
                )

                if verts and faces:
                    # Convert to PyVista format
                    faces_pv = []
                    for t in faces:
                        faces_pv.extend([3] + list(t))
                    mesh_to_add = pv.PolyData(np.array(verts), np.array(faces_pv))

        except Exception as e:
            logger.warning(f"Build123d tessellation failed for {body.name}: {e}")

        # Fallback: Use cached vtk_mesh
        if mesh_to_add is None:
            if hasattr(body, 'vtk_mesh') and body.vtk_mesh is not None:
                mesh_to_add = body.vtk_mesh

        return mesh_to_add


class STEPExportWorker(QThread):
    """
    Background Worker für STEP Export.

    STEP ist schneller als STL (kein Tessellieren nötig),
    aber für große Assemblies kann es trotzdem dauern.
    """

    progress = Signal(int, str)
    finished = Signal(str)
    error = Signal(str)

    def __init__(self, solids: List, filepath: str):
        super().__init__()
        self.solids = solids
        self.filepath = filepath
        self._cancelled = False

    def cancel(self):
        self._cancelled = True

    def run(self):
        try:
            from build123d import Compound, export_step

            self.progress.emit(20, "Erstelle Compound...")

            if len(self.solids) == 1:
                shape_to_export = self.solids[0]
            else:
                shape_to_export = Compound(children=self.solids)

            if self._cancelled:
                self.error.emit("Export abgebrochen")
                return

            self.progress.emit(50, "Exportiere STEP...")
            export_step(shape_to_export, self.filepath)

            self.progress.emit(100, "Fertig!")
            self.finished.emit(self.filepath)

        except Exception as e:
            import traceback
            traceback.print_exc()
            self.error.emit(f"STEP Export Fehler: {str(e)}")
