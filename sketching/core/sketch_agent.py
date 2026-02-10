"""
Sketch Agent - Haupt-Klasse

Ein intelligenter Agent der wie ein CAD-Experte Sketches zeichnet
und OCP-Operationen durchführt.

Author: Claude (Sketch Agent)
Date: 2026-02-10
"""

import random
import time
from typing import Optional, List
from loguru import logger

from sketching.core.result_types import (
    PartResult, AssemblyResult, BatchResult,
    MeshAnalysis, ReconstructionResult
)


class SketchAgent:
    """
    Haupt-Klasse des Sketch Agents.

    Modes:
    - "random": Zufällige Parameter
    - "adaptive": Lernt aus Ergebnissen
    - "guided": Nutzt Design-Patterns

    Headless vs Visual:
    - headless=True: Läuft ohne UI, speichert Ergebnisse
    - headless=False: Zeigt Fortschritt im Viewport
    """

    def __init__(
        self,
        mode: str = "adaptive",
        headless: bool = True,
        seed: Optional[int] = None
    ):
        self.mode = mode  # "random", "adaptive", "guided"
        self.headless = headless

        # Random Seed für Reproduzierbarkeit
        if seed is not None:
            random.seed(seed)

        # Komponenten importieren
        from sketching.generators.sketch_generator import SketchGenerator
        from sketching.operations.operation_agent import OperationAgent

        self.generator = SketchGenerator(seed=seed)
        self.operations = OperationAgent(seed=seed)
        self.feedback = None    # FeedbackLoop (TODO)
        self.assembly = None    # AssemblyAgent (TODO)

        # Statistiken
        self._parts_generated = 0
        self._parts_successful = 0

    def generate_part(
        self,
        complexity: str = "medium"
    ) -> PartResult:
        """
        Generiert ein komplettes Bauteil.

        Args:
            complexity: "simple", "medium", oder "complex"

        Returns:
            PartResult mit generiertem Solid
        """
        start_time = time.time()
        operations = []

        try:
            logger.info(f"[SketchAgent] Generiere Part (complexity={complexity})")

            # 1. Sketch generieren
            sketch = self.generator.generate_random_profile()
            if sketch is None:
                return PartResult(
                    success=False,
                    solid=None,
                    operations=["generate_sketch"],
                    duration_ms=(time.time() - start_time) * 1000,
                    error="SketchGenerator returned None"
                )
            operations.append(f"generate_sketch({complexity})")

            # 2. Extrusions-Distanz wählen
            # Schätze Sketch-Grösse für adaptive Distanz
            distance = self.operations.select_extrude_distance(
                sketch_area=1000,  # Schätzung
                mode=self.mode
            )
            operations.append(f"select_distance({distance:.1f})")

            # 3. Extrudieren
            solid = self.operations.extrude(sketch, distance)
            operations.append("extrude")

            if solid is None:
                return PartResult(
                    success=False,
                    solid=None,
                    operations=operations,
                    duration_ms=(time.time() - start_time) * 1000,
                    error="Extrusion failed"
                )

            duration_ms = (time.time() - start_time) * 1000
            logger.info(f"[SketchAgent] Part generiert: {duration_ms:.2f}ms")

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
            logger.error(f"[SketchAgent] Fehler: {e}")
            import traceback
            traceback.print_exc()
            return PartResult(
                success=False,
                solid=None,
                operations=operations,
                duration_ms=duration_ms,
                error=str(e)
            )

    def generate_assembly(
        self,
        part_count: int = 3
    ) -> AssemblyResult:
        """
        Generiert eine Assembly mit mehreren Parts.

        Args:
            part_count: Anzahl der Parts

        Returns:
            AssemblyResult
        """
        start_time = time.time()

        try:
            logger.info(f"[SketchAgent] Generiere Assembly ({part_count} Parts)")

            parts = []
            constraints = []

            for i in range(part_count):
                part = self.generate_part(complexity="medium")
                parts.append(part)

            duration_ms = (time.time() - start_time) * 1000

            return AssemblyResult(
                success=True,
                parts=parts,
                constraints=constraints,
                duration_ms=duration_ms
            )

        except Exception as e:
            duration_ms = (time.time() - start_time) * 1000
            return AssemblyResult(
                success=False,
                parts=[],
                constraints=[],
                duration_ms=duration_ms,
                error=str(e)
            )

    def run_batch(
        self,
        count: int = 100,
        complexity: str = "medium"
    ) -> BatchResult:
        """
        Führt Batch-Test aus (headless).

        Args:
            count: Anzahl der zu generierenden Parts
            complexity: Komplexität der Parts

        Returns:
            BatchResult mit allen Results
        """
        from datetime import datetime

        started_at = datetime.now()
        results = []

        logger.info(f"[SketchAgent] Batch-Test: {count} Parts")

        for i in range(count):
            result = self.generate_part(complexity=complexity)
            results.append(result)

            # Stats
            self._parts_generated += 1
            if result.success:
                self._parts_successful += 1

            # Log Progress
            if (i + 1) % 10 == 0:
                logger.info(f"[SketchAgent] {i + 1}/{count} Parts generiert")

        finished_at = datetime.now()

        batch = BatchResult(
            results=results,
            duration_ms=(finished_at - started_at).total_seconds() * 1000,
            started_at=started_at,
            finished_at=finished_at
        )

        logger.info(f"[SketchAgent] Batch abgeschlossen: {batch.success_rate:.1%} Success")

        return batch

    def reconstruct_from_mesh(
        self,
        mesh_path: str,
        interactive: bool = True
    ) -> ReconstructionResult:
        """
        Rekonstruiert CAD aus Mesh.

        Args:
            mesh_path: Pfad zur STL/OBJ Datei
            interactive: Ob der User zuschauen kann

        Returns:
            ReconstructionResult
        """
        start_time = time.time()

        try:
            logger.info(f"[SketchAgent] Rekonstruiere Mesh: {mesh_path}")

            # TODO: Implementiere Rekonstruktion
            # 1. Mesh analysieren
            # 2. Primitives erkennen
            # 3. Features erkennen
            # 4. Schritte planen
            # 5. Schritt-für-Schritt ausführen

            duration_ms = (time.time() - start_time) * 1000

            return ReconstructionResult(
                success=False,
                solid=None,
                analysis=MeshAnalysis([], [], {}, {}, duration_ms),
                executed_steps=[],
                duration_ms=duration_ms,
                error="Not yet implemented"
            )

        except Exception as e:
            duration_ms = (time.time() - start_time) * 1000
            return ReconstructionResult(
                success=False,
                solid=None,
                analysis=MeshAnalysis([], [], {}, {}, duration_ms),
                executed_steps=[],
                duration_ms=duration_ms,
                error=str(e)
            )

    @property
    def success_rate(self) -> float:
        """Erfolgsrate aller generierten Parts."""
        if self._parts_generated == 0:
            return 0.0
        return self._parts_successful / self._parts_generated

    def get_stats(self) -> dict:
        """Statistiken des Agents."""
        return {
            "mode": self.mode,
            "headless": self.headless,
            "parts_generated": self._parts_generated,
            "parts_successful": self._parts_successful,
            "success_rate": self.success_rate
        }


# Factory für kompatible Creation
def create_agent(
    mode: str = "adaptive",
    headless: bool = True,
    seed: Optional[int] = None
) -> SketchAgent:
    """
    Factory-Funktion zum Erstellen eines SketchAgent.

    Args:
        mode: "random", "adaptive", oder "guided"
        headless: Ob ohne UI laufen
        seed: Random Seed für Reproduzierbarkeit

    Returns:
        SketchAgent Instanz
    """
    return SketchAgent(mode=mode, headless=headless, seed=seed)
