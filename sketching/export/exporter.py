"""
Export Module - Exportiert generierte Parts

Export-Funktionen:
- STEP Export
- Screenshot (via PyVista)
- Metadata JSON
- Batch Export

Author: Claude (Sketch Agent)
Date: 2026-02-11
"""

import os
import json
import time
from typing import Optional, List, Dict, Any
from datetime import datetime
from loguru import logger

try:
    import pyvista as pv
    HAS_PYVISTA = True
except ImportError:
    HAS_PYVISTA = False
    logger.warning("PyVista nicht verfügbar")


class PartExporter:
    """Exportiert generierte Parts."""

    def export_step(self, solid: Any, path: str) -> bool:
        """
        Exportiert als STEP.

        Args:
            solid: build123d Solid
            path: Ausgabepfad

        Returns:
            True bei Erfolg
        """
        try:
            from build123d import export_step

            # Verzeichnis erstellen
            os.makedirs(os.path.dirname(path), exist_ok=True)

            # Export
            export_step(solid.wrapped, path)

            logger.debug(f"[PartExporter] STEP exportiert: {path}")
            return True

        except Exception as e:
            logger.error(f"[PartExporter] STEP-Export fehlgeschlagen: {e}")
            return False

    def export_screenshot(self, solid: Any, path: str) -> bool:
        """
        Erstellt Screenshot (PyVista).

        Args:
            solid: build123d Solid
            path: Ausgabepfad (.png)

        Returns:
            True bei Erfolg
        """
        if not HAS_PYVISTA:
            logger.warning("[PartExporter] PyVista nicht verfügbar für Screenshot")
            return False

        try:
            # Solid zu PyVista Mesh konvertieren
            import build123d as bd
            mesh = pv.PolyData(solid.wrapped)

            # Screenshot speichern
            plotter = pv.Plotter(off_screen=True)
            plotter.add_mesh(mesh, color='lightblue')
            plotter.screenshot(path)
            plotter.close()

            logger.debug(f"[PartExporter] Screenshot gespeichert: {path}")
            return True

        except Exception as e:
            logger.error(f"[PartExporter] Screenshot fehlgeschlagen: {e}")
            return False

    def export_metadata(
        self,
        result: Any,
        path: str,
        additional_info: Optional[Dict] = None
    ) -> bool:
        """
        Exportiert Metadaten als JSON.

        Args:
            result: PartResult oder ähnliches
            path: Ausgabepfad
            additional_info: Zusätzliche Info

        Returns:
            True bei Erfolg
        """
        try:
            metadata = {
                "timestamp": datetime.now().isoformat(),
                "success": getattr(result, 'success', False),
                "operations": getattr(result, 'operations', []),
                "duration_ms": getattr(result, 'duration_ms', 0),
                "error": getattr(result, 'error', None),
                "face_count": getattr(result, 'face_count', 0),
                "volume": getattr(result, 'volume', 0),
                "metadata": getattr(result, 'metadata', {})
            }

            if additional_info:
                metadata["additional"] = additional_info

            # Speichern
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, 'w') as f:
                json.dump(metadata, f, indent=2)

            logger.debug(f"[PartExporter] Metadata exportiert: {path}")
            return True

        except Exception as e:
            logger.error(f"[PartExporter] Metadata-Export fehlgeschlagen: {e}")
            return False


class BatchExporter:
    """Exportiert Batch-Ergebnisse."""

    def export_batch(
        self,
        results: List[Any],
        output_dir: str,
        export_step: bool = True,
        export_screenshot: bool = False,
        export_metadata: bool = True
    ) -> Dict[str, Any]:
        """
        Exportiert alle Results eines Batches.

        Struktur:
        output_dir/
        ├── part_001.step
        ├── part_001.png
        ├── part_001.json
        ├── part_002.step
        ...
        └── batch_summary.json

        Args:
            results: Liste der PartResult
            output_dir: Ausgabeverzeichnis
            export_step: STEP exportieren
            export_screenshot: Screenshot erstellen
            export_metadata: Metadata exportieren

        Returns:
            Zusammenfassung des Exports
        """
        os.makedirs(output_dir, exist_ok_ok=True)

        summary = {
            "exported_at": datetime.now().isoformat(),
            "total_results": len(results),
            "successful": 0,
            "failed": 0,
            "parts": []
        }

        exporter = PartExporter()

        for i, result in enumerate(results):
            part_id = f"part_{i + 1:04d}"
            base_path = os.path.join(output_dir, part_id)

            # Metadata
            if export_metadata:
                meta_path = base_path + ".json"
                exporter.export_metadata(result, meta_path)

            # STEP
            step_exported = False
            if export_step and hasattr(result, 'solid') and result.solid:
                step_path = base_path + ".step"
                step_exported = exporter.export_step(result.solid, step_path)

            # Screenshot
            screenshot_exported = False
            if export_screenshot and hasattr(result, 'solid') and result.solid:
                png_path = base_path + ".png"
                screenshot_exported = exporter.export_screenshot(result.solid, png_path)

            # Zusammenfassung
            part_summary = {
                "id": part_id,
                "success": getattr(result, 'success', False),
                "step_exported": step_exported,
                "screenshot_exported": screenshot_exported,
                "face_count": getattr(result, 'face_count', 0)
            }
            summary["parts"].append(part_summary)

            if result.success:
                summary["successful"] += 1
            else:
                summary["failed"] += 1

        # Batch-Summary speichern
        summary_path = os.path.join(output_dir, "batch_summary.json")
        with open(summary_path, 'w') as f:
            json.dump(summary, f, indent=2)

        logger.info(f"[BatchExporter] Batch exportiert: {output_dir}")
        return summary


def create_part_exporter() -> PartExporter:
    """Factory für PartExporter."""
    return PartExporter()


def create_batch_exporter() -> BatchExporter:
    """Factory für BatchExporter."""
    return BatchExporter()
