"""
Test: Sketch Agent - 100x Stress Test
Prüft Stabilität und Fehlerhäufigkeit bei 100 Durchläufen.
"""

import sys
import os
import time
from datetime import datetime

# Pfad zu LiteCad hinzufügen
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from loguru import logger


def run_100x_test():
    """Führt 100 Sketch-Agent Generierungen aus."""
    logger.info("=" * 60)
    logger.info("SKETCH AGENT - 100x STRESS TEST")
    logger.info("=" * 60)

    from sketching import create_agent
    from modeling import Document

    # Test-Konfiguration
    iterations = 100
    complexities = ["simple", "medium", "complex"]

    # Statistiken
    stats = {
        "total": iterations,
        "success": 0,
        "failed": 0,
        "errors": {},
        "complexity_stats": {c: {"success": 0, "failed": 0} for c in complexities},
        "durations": [],
        "sketch_counts": [],
    }

    started_at = datetime.now()
    start_time = time.time()

    for i in range(iterations):
        iteration_start = time.time()

        # Zufällige Komplexität
        import random
        complexity = random.choice(complexities)

        try:
            # Neues Document für jeden Durchlauf (saubere Umgebung)
            doc = Document(f"Test_{i}")

            # Agent erstellen
            agent = create_agent(
                document=doc,
                mode="adaptive",
                headless=True,
                seed=None  # Jeder Durchlauf zufällig
            )

            # Part generieren
            result = agent.generate_part(complexity=complexity)

            iteration_duration = (time.time() - iteration_start) * 1000

            if result.success:
                stats["success"] += 1
                stats["complexity_stats"][complexity]["success"] += 1
                stats["durations"].append(result.duration_ms)
                stats["sketch_counts"].append(result.sketch_count)

                if (i + 1) % 10 == 0:
                    logger.info(f"[{i+1}/{iterations}] OK - {complexity} - {result.duration_ms:.1f}ms - {result.sketch_count} sketches")

            else:
                stats["failed"] += 1
                stats["complexity_stats"][complexity]["failed"] += 1
                error_msg = result.error or "Unknown error"
                stats["errors"][error_msg] = stats["errors"].get(error_msg, 0) + 1
                logger.error(f"[{i+1}/{iterations}] FAILED - {complexity} - {error_msg}")

        except Exception as e:
            stats["failed"] += 1
            stats["complexity_stats"][complexity]["failed"] += 1
            error_msg = str(e)
            stats["errors"][error_msg] = stats["errors"].get(error_msg, 0) + 1
            logger.error(f"[{i+1}/{iterations}] EXCEPTION - {complexity} - {error_msg}")
            import traceback
            traceback.print_exc()

    finished_at = datetime.now()
    total_duration = (time.time() - start_time) * 1000

    # Ergebnisbericht
    logger.info("=" * 60)
    logger.info("ERGEBNISBERICHT")
    logger.info("=" * 60)

    success_rate = (stats["success"] / stats["total"]) * 100

    logger.info(f"Gesamt:          {stats['total']} Durchläufe")
    logger.info(f"Erfolgreich:     {stats['success']} ({success_rate:.1f}%)")
    logger.info(f"Fehlgeschlagen:  {stats['failed']}")
    logger.info(f"Dauer gesamt:    {total_duration/1000:.1f}s")

    if stats["durations"]:
        avg_duration = sum(stats["durations"]) / len(stats["durations"])
        min_duration = min(stats["durations"])
        max_duration = max(stats["durations"])
        logger.info(f"Durchschnitt:    {avg_duration:.1f}ms")
        logger.info(f"Min/Max:         {min_duration:.1f}ms / {max_duration:.1f}ms")

    if stats["sketch_counts"]:
        avg_sketches = sum(stats["sketch_counts"]) / len(stats["sketch_counts"])
        logger.info(f"∅ Sketches/Part: {avg_sketches:.1f}")

    logger.info("-" * 60)
    logger.info("Nach Komplexität:")
    for complexity in complexities:
        c_stats = stats["complexity_stats"][complexity]
        total = c_stats["success"] + c_stats["failed"]
        if total > 0:
            rate = (c_stats["success"] / total) * 100
            logger.info(f"  {complexity:8s}: {c_stats['success']:3d}/{total:<3d} ({rate:5.1f}%)")

    if stats["errors"]:
        logger.info("-" * 60)
        logger.info("Fehler-Häufigkeit:")
        for error, count in sorted(stats["errors"].items(), key=lambda x: -x[1]):
            logger.info(f"  [{count}x] {error}")

    logger.info("=" * 60)

    # Bewertung
    if success_rate >= 95:
        logger.success("EXCELLENT: Success Rate >= 95%")
        return 0
    elif success_rate >= 80:
        logger.warning("GOOD: Success Rate >= 80%")
        return 0
    elif success_rate >= 50:
        logger.error("POOR: Success Rate < 80%")
        return 1
    else:
        logger.error("CRITICAL: Success Rate < 50%")
        return 1


if __name__ == "__main__":
    exit_code = run_100x_test()
    sys.exit(exit_code)
