"""
CurrentConverter - Wrapper für bestehende V10/Final Converter
============================================================

Wrapper um die bewährten MeshToBREPConverterV10 und FinalMeshConverter,
der beide Strategien mit Progress Reporting verfügbar macht.

Strategien:
- V10: Segmentierung + Primitive Fitting (Plane, Cylinder, Sphere, Cone)
- Final: Zylinder-erhaltend für STEP Export mit analytischen Surfaces

Author: Claude (MeshConverter Architecture)
Date: 2026-02-10
"""

import numpy as np
from typing import Optional, List, Dict, Tuple
from loguru import logger
from enum import Enum, auto

try:
    import pyvista as pv
    HAS_PYVISTA = True
except ImportError:
    HAS_PYVISTA = False

try:
    from OCP.gp import gp_Pnt, gp_Vec, gp_Dir, gp_Pln
    from OCP.BRepBuilderAPI import (
        BRepBuilderAPI_MakeEdge,
        BRepBuilderAPI_MakeWire,
        BRepBuilderAPI_MakeFace,
        BRepBuilderAPI_Sewing,
        BRepBuilderAPI_MakeSolid
    )
    from OCP.TopoDS import TopoDS_Edge, TopoDS_Wire, TopoDS_Face, TopoDS, TopoDS_Shell, TopoDS_Solid
    from OCP.ShapeFix import ShapeFix_Solid, ShapeFix_Shell
    from OCP.ShapeUpgrade import ShapeUpgrade_UnifySameDomain
    from OCP.BRepCheck import BRepCheck_Analyzer
    from OCP.TopAbs import TopAbs_REVERSED, TopAbs_FACE, TopAbs_SHELL, TopAbs_COMPOUND
    from OCP.TopExp import TopExp_Explorer
    HAS_OCP = True
except ImportError:
    HAS_OCP = False
    logger.warning("OCP nicht verfügbar")

try:
    from build123d import Solid
    HAS_BUILD123D = True
except ImportError:
    HAS_BUILD123D = False
    Solid = None

from meshconverter.base import (
    AsyncMeshConverter,
    ConversionResult,
    ConversionStatus,
    ConversionPhase,
    ProgressUpdate
)

# Importiere bestehende Converter
from meshconverter.mesh_converter_v10 import (
    MeshToBREPConverterV10,
    ConversionResult as V10ConversionResult,
    ConversionStatus as V10ConversionStatus,
    LoadResult,
    LoadStatus
)
from meshconverter.final_mesh_converter import (
    FinalMeshConverter,
    FinalResult
)


class CurrentMode(Enum):
    """Verfügbare Konvertierungs-Modi."""
    AUTO = auto()      # Automatische Wahl basierend auf Mesh
    V10 = auto()       # V10: Segmentierung + Primitive Fitting
    FINAL = auto()     # Final: Zylinder-erhaltend für STEP


class CurrentConverter(AsyncMeshConverter):
    """
    Wrapper für bestehende V10/Final Converter mit Progress Reporting.

    Strategien:
    - V10: Vollständige Segmentierung + Primitive Fitting
    - Final: Zylinder-erhaltend (CYLINDRICAL_SURFACE)

    Usage:
        converter = CurrentConverter(mode=CurrentMode.V10)

        def on_progress(update: ProgressUpdate):
            print(f"[{update.phase.value}] {update.progress*100:.0f}% - {update.message}")

        result = converter.convert_async(mesh, on_progress)
    """

    def __init__(
        self,
        mode: CurrentMode = CurrentMode.AUTO,
        # V10 Parameter
        preserve_topology: bool = False,
        enable_nurbs: bool = True,
        # Final Parameter
        preserve_cylinders: bool = True,
        angle_threshold: float = 12.0,
        min_cylinder_faces: int = 20,
        cylinder_fit_tolerance: float = 0.3
    ):
        super().__init__(name="CurrentConverter")
        self.mode = mode
        self.preserve_topology = preserve_topology
        self.enable_nurbs = enable_nurbs
        self.preserve_cylinders = preserve_cylinders
        self.angle_threshold = angle_threshold
        self.min_cylinder_faces = min_cylinder_faces
        self.cylinder_fit_tolerance = cylinder_fit_tolerance

        # Erstelle Converter-Instanzen
        self._v10_converter = MeshToBREPConverterV10(
            preserve_topology=preserve_topology,
            enable_nurbs=enable_nurbs
        )
        self._final_converter = FinalMeshConverter(
            preserve_cylinders=preserve_cylinders,
            angle_threshold=angle_threshold,
            min_cylinder_faces=min_cylinder_faces,
            cylinder_fit_tolerance=cylinder_fit_tolerance
        )

    def convert_async(
        self,
        mesh: 'pv.PolyData',
        progress_callback: Optional[callable] = None
    ) -> ConversionResult:
        """
        Asynchrone Konvertierung mit Progress Updates.

        Args:
            mesh: PyVista PolyData (muss trianguliert sein)
            progress_callback: Optionale Callback-Funktion

        Returns:
            ConversionResult mit dem erstellten BREP Solid
        """
        if not HAS_OCP:
            return ConversionResult(
                success=False,
                status=ConversionStatus.FAILED,
                message="OCP nicht verfügbar"
            )

        if not HAS_PYVISTA:
            return ConversionResult(
                success=False,
                status=ConversionStatus.FAILED,
                message="PyVista nicht verfügbar"
            )

        if not self._validate_mesh(mesh):
            return ConversionResult(
                success=False,
                status=ConversionStatus.FAILED,
                message="Ungültiges Mesh"
            )

        logger.info(f"CurrentConverter: {mesh.n_points} Punkte, {mesh.n_cells} Faces")

        try:
            # Wähle Strategie
            if self.mode == CurrentMode.AUTO:
                # Auto: Final für Zylinder-reiche Meshes, V10 sonst
                use_final = self._should_use_final(mesh)
            else:
                use_final = (self.mode == CurrentMode.FINAL)

            strategy_name = "Final (Zylinder-erhaltend)" if use_final else "V10 (Segmentierung)"
            logger.info(f"Strategie: {strategy_name}")

            # Phase 1: Loading (0-10%)
            self._emit_progress(
                ConversionPhase.LOADING, 0.05,
                f"Lade Mesh ({strategy_name})...",
                callback=progress_callback
            )

            # Phase 2: Vorbereitung (10-20%)
            self._emit_progress(
                ConversionPhase.REPAIRING, 0.15,
                "Bereite Konvertierung vor...",
                callback=progress_callback
            )

            if use_final:
                # Final Converter
                return self._convert_with_final(mesh, progress_callback)
            else:
                # V10 Converter
                return self._convert_with_v10(mesh, progress_callback)

        except Exception as e:
            logger.error(f"CurrentConverter fehlgeschlagen: {e}")
            import traceback
            traceback.print_exc()
            return ConversionResult(
                success=False,
                status=ConversionStatus.FAILED,
                message=f"Fehler: {e}",
                error=e
            )

    def _should_use_final(self, mesh: 'pv.PolyData') -> bool:
        """
        Heuristik: Soll Final Converter verwendet werden?

        Final ist besser für:
        - Meshes mit vielen Zylindern (Bohrungen, runde Features)
        - STEP Export mit analytischen Zylindern
        """
        # Einfache Heuristik: Wenn Mesh > 500 Faces, probier Final
        # (Zylinder-reiche Meshes haben typischerweise viele Facetten)
        return mesh.n_cells > 500

    def _convert_with_v10(
        self,
        mesh: 'pv.PolyData',
        progress_callback: Optional[callable] = None
    ) -> ConversionResult:
        """
        Konvertierung mit V10 Converter + Progress Wrapper.

        V10 macht intern kein Progress Reporting, also wrappen wir
        die Phasen mit estimates.
        """
        # Phase 3: Segmentierung (20-40%)
        self._emit_progress(
            ConversionPhase.SEGMENTING, 0.3,
            "Segmentiere Oberflächen...",
            callback=progress_callback
        )

        # Phase 4: Primitive Detection (40-60%)
        self._emit_progress(
            ConversionPhase.DETECTING, 0.5,
            "Erkenne Primitive (Plane, Cylinder, Sphere)...",
            callback=progress_callback
        )

        # Phase 5: BREP Building (60-85%)
        self._emit_progress(
            ConversionPhase.BUILDING, 0.7,
            "Erstelle BREP Geometrie...",
            callback=progress_callback
        )

        # Führe V10 Konvertierung aus
        v10_result = self._v10_converter.convert_mesh(mesh)

        # Map V10 Result zu unserem Result
        return self._map_v10_result(v10_result)

    def _convert_with_final(
        self,
        mesh: 'pv.PolyData',
        progress_callback: Optional[callable] = None
    ) -> ConversionResult:
        """
        Konvertierung mit Final Converter + Progress Wrapper.
        """
        # Phase 3: Zylinder Detection (20-50%)
        self._emit_progress(
            ConversionPhase.DETECTING, 0.35,
            "Erkenne Zylinder...",
            callback=progress_callback
        )

        # Phase 4: BREP Building (50-80%)
        self._emit_progress(
            ConversionPhase.BUILDING, 0.65,
            "Erstelle analytische Zylinder-Surfaces...",
            callback=progress_callback
        )

        # Führe Final Konvertierung aus
        final_result = self._final_converter.convert(mesh)

        # Map Final Result zu unserem Result
        return self._map_final_result(final_result)

    def _map_v10_result(self, v10_result: 'V10ConversionResult') -> ConversionResult:
        """Mappt V10 ConversionResult zu unserem Result."""
        # Map Status
        status_map = {
            V10ConversionStatus.SUCCESS: ConversionStatus.SUCCESS,
            V10ConversionStatus.PARTIAL: ConversionStatus.PARTIAL,
            V10ConversionStatus.SHELL_ONLY: ConversionStatus.SHELL_ONLY,
            V10ConversionStatus.FAILED: ConversionStatus.FAILED,
        }
        status = status_map.get(v10_result.status, ConversionStatus.FAILED)

        # Face-Count aus Stats extrahieren
        face_count = v10_result.stats.get('faces_converted', 0)

        return ConversionResult(
            success=status == ConversionStatus.SUCCESS,
            solid=v10_result.solid,
            status=status,
            message=v10_result.message or "V10 Konvertierung",
            face_count=face_count
        )

    def _map_final_result(self, final_result: 'FinalResult') -> ConversionResult:
        """Mappt FinalResult zu unserem Result."""
        # Map Status
        if final_result.status == "SUCCESS":
            if final_result.is_solid:
                status = ConversionStatus.SUCCESS
            else:
                status = ConversionStatus.SHELL_ONLY
        else:
            status = ConversionStatus.FAILED

        # Face-Count aus Stats extrahieren
        face_count = final_result.stats.get('total_faces', 0)

        # Solid aus OCP Shape erstellen
        solid = None
        if final_result.shape is not None:
            try:
                solid = Solid(final_result.shape)
            except Exception as e:
                logger.warning(f"Konnte keinen Solid erstellen: {e}")

        return ConversionResult(
            success=status == ConversionStatus.SUCCESS,
            solid=solid,
            status=status,
            message=f"Final Converter: {final_result.status}",
            face_count=face_count
        )


# Convenience Functions
# =============================================================================

def convert_with_current(
    mesh: 'pv.PolyData',
    mode: CurrentMode = CurrentMode.AUTO,
    progress_callback=None
) -> ConversionResult:
    """
    Convenience Funktion für CurrentConverter.

    Args:
        mesh: PyVista PolyData
        mode: Konvertierungs-Modus (AUTO, V10, FINAL)
        progress_callback: Optionale Progress-Callback

    Returns:
        ConversionResult
    """
    converter = CurrentConverter(mode=mode)
    return converter.convert_async(mesh, progress_callback)


def convert_v10(mesh: 'pv.PolyData', progress_callback=None) -> ConversionResult:
    """Convenience für V10 Mode."""
    return convert_with_current(mesh, CurrentMode.V10, progress_callback)


def convert_final(mesh: 'pv.PolyData', progress_callback=None) -> ConversionResult:
    """Convenience für Final Mode."""
    return convert_with_current(mesh, CurrentMode.FINAL, progress_callback)


if __name__ == "__main__":
    # Test
    import pyvista as pv

    # Einfacher Test-Würfel
    cube = pv.Cube().triangulate()
    print(f"Test Mesh: {cube.n_points} Punkte, {cube.n_cells} Faces")

    converter = CurrentConverter(mode=CurrentMode.V10)

    def on_progress(update):
        print(f"[{update.phase.value}] {update.progress*100:.0f}% - {update.message}")

    result = converter.convert_async(cube, on_progress)

    print(f"\nResult: {result.status.value if result.status else 'N/A'}")
    print(f"Face-Count: {result.face_count}")
    if result.solid:
        print(f"Solid: {result.solid}")
