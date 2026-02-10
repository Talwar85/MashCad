"""
Test Runner - Führt automatisierte Tests mit SketchAgent aus

Test-Arten:
- Stress Test: Viele zufällige Parts generieren
- Regression Test: Feste Test-Fälle
- ML Dataset: Trainingsdaten generieren

Author: Claude (Sketch Agent)
Date: 2026-02-10
"""

import os
import json
import time
from typing import Optional, List, Dict, Any
from datetime import datetime
from loguru import logger

try:
    import psutil
    HAS_PSUTIL = True
except ImportError:
    HAS_PSUTIL = False

from sketching.core.sketch_agent import SketchAgent
from sketching.core.result_types import (
    PartResult, BatchResult, StressTestResult,
    ReconstructionResult
)


class TestRunner:
    """
    Führt automatisierte Tests mit SketchAgent aus.

    Metriken:
    - Success-Rate
    - Durchschnittliche Dauer
    - Fehler-Analyse
    - Memory-Usage
    """

    def __init__(self, agent: Optional[SketchAgent] = None):
        """
        Args:
            agent: SketchAgent Instanz (wird erstellt wenn None)
        """
        self.agent = agent or SketchAgent(mode="adaptive", headless=True)
        self.results: List[PartResult] = []

    def run_stress_test(
        self,
        count: int = 100,
        complexity: str = "medium"
    ) -> StressTestResult:
        """
        Stress-Test mit N zufälligen Parts.

        Args:
            count: Anzahl der zu generierenden Parts
            complexity: Komplexität der Parts

        Returns:
            StressTestResult mit allen Metriken
        """
        logger.info(f"[TestRunner] Stress-Test: {count} Parts")

        start_time = time.time()
        start_memory = psutil.Process().memory_info().rss / 1024 / 1024 if HAS_PSUTIL else 0

        # Batch ausführen
        batch = self.agent.run_batch(count=count, complexity=complexity)

        end_memory = psutil.Process().memory_info().rss / 1024 / 1024 if HAS_PSUTIL else 0
        memory_mb = end_memory - start_memory if HAS_PSUTIL else 0

        # Fehler-Analyse
        error_analysis = self._analyze_errors(batch.results)

        result = StressTestResult(
            batch=batch,
            success_rate=batch.success_rate,
            avg_duration_ms=batch.avg_duration_ms,
            error_analysis=error_analysis,
            memory_mb=memory_mb
        )

        logger.info(f"[TestRunner] Stress-Test abgeschlossen: {batch.success_rate:.1%} Success")
        return result

    def run_regression_test(self) -> Dict[str, Any]:
        """
        Regression-Test mit festen Test-Fällen.

        Testet ob bekannte Patterns noch funktionieren.
        """
        logger.info("[TestRunner] Regression-Test")

        results = {
            "test_name": "regression_test",
            "started_at": datetime.now().isoformat(),
            "tests": []
        }

        # Test-Fälle
        test_cases = [
            {"name": "simple_circle", "complexity": "simple"},
            {"name": "medium_rectangle", "complexity": "medium"},
            {"name": "medium_polygon", "complexity": "medium"},
        ]

        for i, test_case in enumerate(test_cases):
            logger.debug(f"[TestRunner] Test: {test_case['name']}")

            result = self.agent.generate_part(complexity=test_case["complexity"])

            test_result = {
                "name": test_case["name"],
                "success": result.success,
                "duration_ms": result.duration_ms,
                "face_count": result.face_count if result.success else 0,
                "error": result.error
            }

            results["tests"].append(test_result)

        results["finished_at"] = datetime.now().isoformat()
        results["total_tests"] = len(test_cases)
        results["passed_tests"] = sum(1 for t in results["tests"] if t["success"])
        results["success_rate"] = results["passed_tests"] / results["total_tests"]

        logger.info(f"[TestRunner] Regression-Test: {results['success_rate']:.1%} Passed")
        return results

    def generate_ml_dataset(
        self,
        count: int = 100,
        output_dir: str = "ml_data"
    ) -> Dict[str, Any]:
        """
        Generiert ML-Trainingsdaten.

        Format:
        - JSON Files (Metadaten, Tags)
        - STEP Files können separat exportiert werden

        Args:
            count: Anzahl der zu generierenden Parts
            output_dir: Ausgabeverzeichnis

        Returns:
            DatasetInfo mit Statistiken
        """
        logger.info(f"[TestRunner] ML-Dataset: {count} Parts -> {output_dir}")

        os.makedirs(output_dir, exist_ok=True)

        metadata_file = os.path.join(output_dir, "dataset_metadata.json")
        parts_data = []

        start_time = time.time()

        for i in range(count):
            result = self.agent.generate_part(complexity="medium")

            part_metadata = {
                "id": f"part_{i:04d}",
                "success": result.success,
                "operations": result.operations,
                "duration_ms": result.duration_ms,
                "face_count": result.face_count if result.success else 0,
                "volume": result.volume if result.success else 0,
                "metadata": result.metadata,
                "error": result.error
            }

            parts_data.append(part_metadata)

            if (i + 1) % 10 == 0:
                logger.info(f"[TestRunner] {i + 1}/{count} Parts generiert")

        # Metadata speichern
        dataset_metadata = {
            "created_at": datetime.now().isoformat(),
            "total_parts": count,
            "successful_parts": sum(1 for p in parts_data if p["success"]),
            "parts": parts_data
        }

        with open(metadata_file, 'w') as f:
            json.dump(dataset_metadata, f, indent=2)

        duration_ms = (time.time() - start_time) * 1000

        logger.info(f"[TestRunner] ML-Dataset erstellt: {metadata_file}")
        return {
            "count": count,
            "output_dir": output_dir,
            "metadata_file": metadata_file,
            "success_rate": dataset_metadata["successful_parts"] / count,
            "duration_ms": duration_ms
        }

    def test_reconstruction(
        self,
        mesh_path: str,
        interactive: bool = False
    ) -> ReconstructionResult:
        """
        Testet Mesh-Rekonstruktion.

        Args:
            mesh_path: Pfad zur Mesh-Datei
            interactive: Ob visueller Modus

        Returns:
            ReconstructionResult
        """
        logger.info(f"[TestRunner] Reconstruction-Test: {mesh_path}")

        result = self.agent.reconstruct_from_mesh(mesh_path, interactive=interactive)

        logger.info(
            f"[TestRunner] Reconstruction: "
            f"{'Success' if result.success else 'Failed'}, "
            f"{result.completed_steps} steps"
        )

        return result

    def _analyze_errors(self, results: List[PartResult]) -> Dict[str, int]:
        """Analysiert häufige Fehler."""
        error_counts = {}

        for result in results:
            if not result.success and result.error:
                error_key = result.error
                error_counts[error_key] = error_counts.get(error_key, 0) + 1

        return error_counts

    def get_summary(self) -> Dict[str, Any]:
        """Zusammenfassung aller Tests."""
        agent_stats = self.agent.get_stats()

        return {
            "agent_stats": agent_stats,
            "total_results": len(self.results),
            "total_successful": sum(1 for r in self.results if r.success),
            "overall_success_rate": (
                sum(1 for r in self.results if r.success) / len(self.results)
                if self.results else 0
            )
        }


def run_quick_test() -> Dict[str, Any]:
    """
    Führt einen schnellen Test aus (10 Parts).

    Nützlich für schnelle Validierung nach Code-Änderungen.
    """
    runner = TestRunner()
    result = runner.run_stress_test(count=10, complexity="simple")
    return {
        "success_rate": result.success_rate,
        "avg_duration_ms": result.avg_duration_ms,
        "error_analysis": result.error_analysis
    }


if __name__ == "__main__":
    # Schneller Test beim direkten Aufruf
    summary = run_quick_test()
    print(f"Quick Test: {summary['success_rate']:.1%} Success")
    print(f"Avg Duration: {summary['avg_duration_ms']:.2f}ms")
