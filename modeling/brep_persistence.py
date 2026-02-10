"""
MashCAD - BREP Persistenz

Native BREP Persistenz mit TNP v4.1 ShapeID Persistenz.
Speichert BREP-Geometrie im nativen OpenCascade .brep Format
zusammen mit Metadaten (JSON) und TNP ShapeIDs.

Author: Claude (OCP-First Migration Phase 9)
Date: 2026-02-10
"""

import json
from pathlib import Path
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, asdict, field
from datetime import datetime
from loguru import logger


@dataclass
class BREPMetadata:
    """Metadaten für BREP Dateien."""
    shape_id: str  # TNP v4.1 ShapeID
    feature_id: str
    operation_type: str  # "extrude", "fillet", "shell", etc.
    shape_type: str  # "Solid", "Face", "Edge", etc.
    version: str = "1.0"
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    parameters: Dict[str, Any] = field(default_factory=dict)  # Op-Parameter (distance, radius, etc.)

    def to_dict(self) -> Dict[str, Any]:
        """Konvertiert zu Dict für JSON Serialisierung."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'BREPMetadata':
        """Erstellt aus Dict."""
        return cls(**data)


class BREPPersistence:
    """
    Native BREP Persistenz mit TNP Support.

    Speichert BREP-Geometrie im nativen OpenCascade .brep Format
    zusammen mit Metadaten (JSON) und TNP ShapeIDs.
    """

    def __init__(self, base_path: Path = Path("data/breps")):
        """
        BREP Persistenz initialisieren.

        Args:
            base_path: Basis-Pfad für BREP Dateien
        """
        self.base_path = Path(base_path)
        self.base_path.mkdir(parents=True, exist_ok=True)

    def _get_brep_path(self, shape_id: str) -> Path:
        """Pfad zur .brep Datei."""
        return self.base_path / f"{shape_id}.brep"

    def _get_meta_path(self, shape_id: str) -> Path:
        """Pfad zur Metadaten JSON Datei."""
        return self.base_path / f"{shape_id}.meta.json"

    def save_shape(self, shape, metadata: BREPMetadata) -> None:
        """
        Shape als .brep speichern.

        Args:
            shape: Build123d oder OCP Shape
            metadata: Metadaten (inklusive TNP ShapeID)

        Raises:
            RuntimeError: Wenn Speichern fehlschlägt
        """
        if not HAS_OCP:
            raise RuntimeError("OCP nicht verfügbar - BREP Persistenz nicht möglich")

        # OCP Shape extrahieren
        ocp_shape = shape.wrapped if hasattr(shape, 'wrapped') else shape

        # Speichern als .brep
        brep_path = self._get_brep_path(metadata.shape_id)

        try:
            from OCP.BRepTools import BRepTools
            BRepTools.Write_s(ocp_shape, str(brep_path))
        except Exception as e:
            raise RuntimeError(f"BREP Save fehlgeschlagen: {e}") from e

        # Metadaten speichern
        metadata.timestamp = datetime.now().isoformat()
        meta_path = self._get_meta_path(metadata.shape_id)

        with open(meta_path, 'w', encoding='utf-8') as f:
            json.dump(metadata.to_dict(), f, indent=2, ensure_ascii=False)

        if is_enabled("tnp_debug_logging"):
            logger.success(f"BREP gespeichert: {brep_path}")

    def load_shape(self, shape_id: str) -> Optional[Any]:
        """
        Shape aus .brep laden.

        Args:
            shape_id: TNP ShapeID

        Returns:
            Build123d Shape oder None wenn nicht gefunden

        Raises:
            RuntimeError: Wenn Laden fehlschlägt
        """
        if not HAS_OCP:
            raise RuntimeError("OCP nicht verfügbar - BROP Persistenz nicht möglich")

        brep_path = self._get_brep_path(shape_id)

        if not brep_path.exists():
            logger.warning(f"BREP nicht gefunden: {brep_path}")
            return None

        # Laden aus .brep
        try:
            from OCP.BRepTools import BRepTools
            from OCP.TopoDS import TopoDS_Shape
            from OCP.TopAbs import TopAbs_SOLID
            from OCP.BRep import BRep_Builder
            from build123d import Shape, Solid

            target_shape = TopoDS_Shape()
            builder = BRep_Builder()
            success = BRepTools.Read_s(target_shape, str(brep_path), builder)

            if not success:
                raise RuntimeError(f"BRepTools.Read_s gab False zurück")

            # Prüfen ob es ein Solid ist und entsprechenden Typ zurückgeben
            if target_shape.ShapeType() == TopAbs_SOLID:
                return Solid(target_shape)
            else:
                return Shape(target_shape)

        except Exception as e:
            raise RuntimeError(f"BREP Load fehlgeschlagen: {e}") from e

    def load_metadata(self, shape_id: str) -> Optional[BREPMetadata]:
        """
        Metadaten für Shape laden.

        Args:
            shape_id: TNP ShapeID

        Returns:
            BREPMetadata oder None wenn nicht gefunden
        """
        meta_path = self._get_meta_path(shape_id)

        if not meta_path.exists():
            return None

        with open(meta_path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        return BREPMetadata.from_dict(data)

    def delete_shape(self, shape_id: str) -> None:
        """
        Shape und Metadaten löschen.

        Args:
            shape_id: TNP ShapeID
        """
        brep_path = self._get_brep_path(shape_id)
        meta_path = self._get_meta_path(shape_id)

        deleted = False
        if brep_path.exists():
            brep_path.unlink()
            deleted = True

        if meta_path.exists():
            meta_path.unlink()
            deleted = True

        if deleted:
            logger.info(f"BREP gelöscht: {shape_id}")

    def list_shapes(self) -> Dict[str, BREPMetadata]:
        """
        Alle gespeicherten Shapes auflisten.

        Returns:
            Dict von shape_id -> BREPMetadata
        """
        shapes = {}

        for meta_path in self.base_path.glob("*.meta.json"):
            # Dateiname: "shape_id.meta.json" -> shape_id extrahieren
            filename = meta_path.name  # z.B. "test_shape_123.meta.json"
            shape_id = filename.replace(".meta.json", "")

            metadata = self.load_metadata(shape_id)
            if metadata:
                shapes[shape_id] = metadata

        return shapes

    def cleanup_expired(self, ttl_hours: int = 24) -> int:
        """
        Alte BREP Dateien löschen.

        Args:
            ttl_hours: Time-To-Live in Stunden

        Returns:
            Anzahl gelöschter Dateien
        """
        expired_count = 0
        cutoff = datetime.now() - timedelta(hours=ttl_hours)

        for shape_id, metadata in self.list_shapes().items():
            try:
                timestamp = datetime.fromisoformat(metadata.timestamp)
                if timestamp < cutoff:
                    self.delete_shape(shape_id)
                    expired_count += 1
            except Exception as e:
                logger.warning(f"Cleanup error für {shape_id}: {e}")

        logger.info(f"Cleanup: {expired_count} alte BREPs gelöscht")
        return expired_count

    def get_stats(self) -> Dict[str, Any]:
        """
        Statistiken über gespeicherte BREPs.

        Returns:
            Dict mit count, size_bytes, operation_types, etc.
        """
        shapes = self.list_shapes()

        # Grösse berechnen
        total_size = 0
        for shape_id in shapes.keys():
            brep_path = self._get_brep_path(shape_id)
            if brep_path.exists():
                total_size += brep_path.stat().st_size

        # Operation Types
        op_types = {}
        for metadata in shapes.values():
            op_type = metadata.operation_type
            op_types[op_type] = op_types.get(op_type, 0) + 1

        return {
            "count": len(shapes),
            "size_bytes": total_size,
            "size_mb": round(total_size / (1024 * 1024), 2),
            "operation_types": op_types,
            "base_path": str(self.base_path)
        }

    def export_shapes(self, output_path: Path, format: str = "json") -> None:
        """
        Exportiert Metadaten aller Shapes.

        Args:
            output_path: Ausgabedatei
            format: "json" oder "csv"
        """
        shapes = self.list_shapes()

        if format == "json":
            data = {
                "export_timestamp": datetime.now().isoformat(),
                "count": len(shapes),
                "shapes": {sid: m.to_dict() for sid, m in shapes.items()}
            }
            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        else:
            raise ValueError(f"Unsupported format: {format}")

        logger.info(f"Exportiert {len(shapes)} Shapes nach {output_path}")


# Global Instance
_global_persistence: Optional[BREPPersistence] = None


def get_global_persistence() -> BREPPersistence:
    """
    Gibt globale BREP Persistence Instance zurück.

    Returns:
        Singleton BREPPersistence Instance
    """
    global _global_persistence
    if _global_persistence is None:
        _global_persistence = BREPPersistence()
    return _global_persistence


def set_global_persistence(persistence: BREPPersistence) -> None:
    """Setzt globale BREP Persistence Instance."""
    global _global_persistence
    _global_persistence = persistence


# Imports
from datetime import timedelta
from modeling.ocp_helpers import HAS_OCP
from config.feature_flags import is_enabled
