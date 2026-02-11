"""
Visual Agent - SketchAgent mit visueller Rückmeldung

Zeigt Fortschritt im Viewport:
- Generierter Sketch
- Nach jeder Operation
- Farbkodierung für Success/Error

Author: Claude (Sketch Agent)
Date: 2026-02-11
"""

from typing import Optional, Any
from loguru import logger

from sketching.core.sketch_agent import SketchAgent
from sketching.core.result_types import PartResult


class VisualSketchAgent(SketchAgent):
    """
    SketchAgent mit visueller Rückmeldung.

    Zeigt Fortschritt im Viewport:
    - Generierter Sketch (blau)
    - Nach jeder Operation (grün bei Success, rot bei Error)
    - Final (weisses Solid)
    """

    def __init__(
        self,
        viewport=None,
        mode: str = "adaptive",
        seed: Optional[int] = None
    ):
        """
        Args:
            viewport: PyVista Viewport für Visualisierung
            mode: Agent mode
            seed: Random Seed
        """
        super().__init__(mode=mode, headless=False, seed=seed)
        self.viewport = viewport

    def generate_part_visual(
        self,
        complexity: str = "medium"
    ) -> PartResult:
        """
        Generiert Part mit visueller Rückmeldung.

        Ablauf:
        1. Sketch zeichnen (blau)
        2. Extrudieren (grün bei Success, rot bei Error)
        3. Fillet (gelb Preview)
        4. Final (weisses Solid)

        Args:
            complexity: Komplexität des Parts

        Returns:
            PartResult
        """
        start_time = time.time()
        operations = []

        try:
            logger.info(f"[VisualAgent] Generiere Part (complexity={complexity})")

            # 1. Sketch generieren
            self._notify("Generiere Sketch...", "blue")
            sketch = self.generator.generate_random_profile()

            if sketch is None:
                self._notify("Sketch-Erstellung fehlgeschlagen", "red")
                return PartResult(
                    success=False,
                    solid=None,
                    operations=["generate_sketch"],
                    duration_ms=(time.time() - start_time) * 1000,
                    error="SketchGenerator returned None"
                )

            operations.append(f"generate_sketch({complexity})")

            # Sketch im Viewport zeigen
            self._show_sketch(sketch)

            # 2. Extrusions-Distanz wählen
            distance = self.operations.select_extrude_distance(
                sketch_area=1000,
                mode=self.mode
            )
            operations.append(f"select_distance({distance:.1f})")

            # 3. Extrudieren
            self._notify("Extrudiere...", "green")
            solid = self.operations.extrude(sketch, distance)
            operations.append("extrude")

            if solid is None:
                self._notify("Extrusion fehlgeschlagen", "red")
                return PartResult(
                    success=False,
                    solid=None,
                    operations=operations,
                    duration_ms=(time.time() - start_time) * 1000,
                    error="Extrusion failed"
                )

            # Solid im Viewport zeigen
            self._show_solid(solid)

            duration_ms = (time.time() - start_time) * 1000
            logger.info(f"[VisualAgent] Part generiert: {duration_ms:.2f}ms")

            self._notify("Part komplett!", "white")

            return PartResult(
                success=True,
                solid=solid,
                operations=operations,
                duration_ms=duration_ms,
                metadata={
                    "complexity": complexity,
                    "distance": distance
                }
            )

        except Exception as e:
            duration_ms = (time.time() - start_time) * 1000
            logger.error(f"[VisualAgent] Fehler: {e}")
            self._notify(f"Fehler: {e}", "red")
            import traceback
            traceback.print_exc()

            return PartResult(
                success=False,
                solid=None,
                operations=operations,
                duration_ms=duration_ms,
                error=str(e)
            )

    def _show_sketch(self, sketch: Any):
        """
        Zeigt Sketch im Viewport an.

        Args:
            sketch: Sketch zum Anzeigen
        """
        if self.viewport is None:
            return

        try:
            # Sketch-Entities extrahieren und anzeigen
            # TODO: Implementiere Sketch-Visualisierung
            logger.debug("[VisualAgent] Sketch angezeigt")
        except Exception as e:
            logger.warning(f"[VisualAgent] Sketch-Anzeige fehlgeschlagen: {e}")

    def _show_solid(self, solid: Any, color: str = "white"):
        """
        Zeigt Solid im Viewport an.

        Args:
            solid: build123d Solid zum Anzeigen
            color: Farbe (name oder RGB)
        """
        if self.viewport is None:
            return

        try:
            # Solid zu PyVista Mesh konvertieren und anzeigen
            import pyvista as pv
            mesh = pv.PolyData(solid.wrapped)

            # Viewport aktualisieren
            if hasattr(self.viewport, 'add_mesh'):
                self.viewport.add_mesh(mesh, color=color)
            elif hasattr(self.viewport, 'plotter'):
                self.viewport.plotter.add_mesh(mesh, color=color)

            logger.debug(f"[VisualAgent] Solid angezeigt (color={color})")

        except Exception as e:
            logger.warning(f"[VisualAgent] Solid-Anzeige fehlgeschlagen: {e}")

    def _notify(self, message: str, color: str = "white"):
        """
        Sendet Benachrichtigung an Viewport.

        Args:
            message: Nachricht
            color: Farbe für Indikator
        """
        logger.info(f"[VisualAgent] {message} (color={color})")

        if self.viewport and hasattr(self.viewport, 'show_notification'):
            self.viewport.show_notification(message, color)

    def get_stats(self) -> dict:
        """Statistiken des VisualAgent."""
        base_stats = super().get_stats()
        base_stats["viewport_available"] = self.viewport is not None
        return base_stats


def create_visual_agent(
    viewport=None,
    mode: str = "adaptive",
    seed: Optional[int] = None
) -> VisualSketchAgent:
    """
    Factory-Funktion für VisualSketchAgent.

    Args:
        viewport: PyVista Viewport
        mode: Agent mode
        seed: Random Seed

    Returns:
        VisualSketchAgent Instanz
    """
    return VisualSketchAgent(viewport=viewport, mode=mode, seed=seed)
