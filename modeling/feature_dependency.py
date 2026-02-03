"""
MashCad - Feature Dependency Graph
==================================

Phase 7: Inkrementeller Rebuild durch Dependency-Tracking.

Das Problem:
- Aktuelles Rebuild geht IMMER durch alle Features (O(n))
- Wenn Feature N geändert wird, müssen Features 0 bis N-1 NICHT neu berechnet werden

Die Lösung:
- Dependency Graph trackt Abhängigkeiten zwischen Features
- Checkpoints speichern Intermediate-Solids an strategischen Punkten
- Rebuild startet vom nächsten Checkpoint VOR der Änderung

Author: Claude (Phase 7 Performance)
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple, TYPE_CHECKING
from enum import Enum, auto
from loguru import logger
import hashlib

if TYPE_CHECKING:
    from modeling import Feature, Body


class DependencyType(Enum):
    """Arten von Feature-Abhängigkeiten."""
    SEQUENTIAL = auto()      # Standard: Feature N braucht Solid von Feature N-1
    EDGE_REFERENCE = auto()  # Feature referenziert Kanten (Fillet, Chamfer)
    FACE_REFERENCE = auto()  # Feature referenziert Flächen (Shell, Draft)
    SKETCH_REFERENCE = auto()  # Feature nutzt Sketch (Extrude, Revolve)
    BODY_REFERENCE = auto()    # Feature referenziert anderen Body (Boolean)


@dataclass
class FeatureDependency:
    """Eine einzelne Abhängigkeit zwischen zwei Features."""
    source_id: str           # Feature das abhängt
    target_id: str           # Feature von dem es abhängt
    dependency_type: DependencyType
    description: str = ""    # Z.B. "Edge 3 from Extrude"


@dataclass
class RebuildCheckpoint:
    """
    Ein gecachter Zustand des Solids nach einem Feature.

    Ermöglicht schnellen Restart des Rebuilds von diesem Punkt.
    """
    feature_index: int       # Index des Features NACH dem der Checkpoint erstellt wurde
    feature_id: str          # ID des Features
    solid_brep: Optional[str] = None  # Serialisiertes BREP (für Persistenz)
    solid_hash: str = ""     # Hash des Solids für Validierung
    is_valid: bool = True    # False wenn das Solid sich geändert hat

    def invalidate(self):
        """Markiert Checkpoint als ungültig."""
        self.is_valid = False
        self.solid_brep = None


class FeatureDependencyGraph:
    """
    Verwaltet Abhängigkeiten zwischen Features für optimierten Rebuild.

    Kernkonzepte:
    1. Dependency Graph: Welches Feature hängt von welchem ab
    2. Checkpoints: Gecachte Solids an strategischen Punkten
    3. Dirty Tracking: Welche Features müssen neu berechnet werden

    Usage:
        graph = FeatureDependencyGraph()
        graph.add_feature("extrude_1", dependencies=[])
        graph.add_feature("fillet_1", dependencies=[("extrude_1", DependencyType.EDGE_REFERENCE)])

        # Wenn extrude_1 geändert wird:
        affected = graph.get_affected_features("extrude_1")
        # -> ["extrude_1", "fillet_1"]
    """

    def __init__(self):
        # Feature ID -> Liste von Dependencies
        self._dependencies: Dict[str, List[FeatureDependency]] = {}

        # Feature ID -> Set von Features die davon abhängen (reverse lookup)
        self._dependents: Dict[str, Set[str]] = {}

        # Feature Index -> Checkpoint (nur für wichtige Punkte)
        self._checkpoints: Dict[int, RebuildCheckpoint] = {}

        # Set von Feature-IDs die als "dirty" markiert sind
        self._dirty_features: Set[str] = set()

        # Mapping Feature ID -> Index (für schnellen Lookup)
        self._feature_index: Dict[str, int] = {}

        # Checkpoint-Strategie: Alle N Features einen Checkpoint
        self.checkpoint_interval: int = 5

        logger.debug("FeatureDependencyGraph initialisiert")

    def clear(self):
        """Setzt den Graph zurück."""
        self._dependencies.clear()
        self._dependents.clear()
        self._checkpoints.clear()
        self._dirty_features.clear()
        self._feature_index.clear()

    def add_feature(self, feature_id: str, index: int,
                    dependencies: Optional[List[Tuple[str, DependencyType]]] = None):
        """
        Fügt ein Feature zum Graph hinzu.

        Args:
            feature_id: Eindeutige Feature-ID
            index: Position in der Feature-Liste
            dependencies: Liste von (target_id, type) Tupeln
        """
        self._feature_index[feature_id] = index
        self._dependencies[feature_id] = []

        if feature_id not in self._dependents:
            self._dependents[feature_id] = set()

        # Sequentielle Abhängigkeit zum vorherigen Feature (wenn vorhanden)
        if index > 0:
            prev_id = self._get_feature_at_index(index - 1)
            if prev_id:
                self._add_dependency(feature_id, prev_id, DependencyType.SEQUENTIAL)

        # Explizite Abhängigkeiten hinzufügen
        if dependencies:
            for target_id, dep_type in dependencies:
                self._add_dependency(feature_id, target_id, dep_type)

        logger.debug(f"Feature '{feature_id}' hinzugefügt (Index {index})")

    def _add_dependency(self, source_id: str, target_id: str, dep_type: DependencyType):
        """Fügt eine Abhängigkeit hinzu."""
        dep = FeatureDependency(
            source_id=source_id,
            target_id=target_id,
            dependency_type=dep_type
        )
        self._dependencies[source_id].append(dep)

        if target_id not in self._dependents:
            self._dependents[target_id] = set()
        self._dependents[target_id].add(source_id)

    def remove_feature(self, feature_id: str):
        """Entfernt ein Feature aus dem Graph."""
        if feature_id in self._dependencies:
            # Entferne aus Dependents der Targets
            for dep in self._dependencies[feature_id]:
                if dep.target_id in self._dependents:
                    self._dependents[dep.target_id].discard(feature_id)

            del self._dependencies[feature_id]

        if feature_id in self._dependents:
            del self._dependents[feature_id]

        if feature_id in self._feature_index:
            del self._feature_index[feature_id]

        self._dirty_features.discard(feature_id)

        # Alle Checkpoints nach diesem Feature invalidieren
        index = self._feature_index.get(feature_id, -1)
        if index >= 0:
            self._invalidate_checkpoints_from(index)

    def _get_feature_at_index(self, index: int) -> Optional[str]:
        """Findet Feature-ID für einen Index."""
        for fid, idx in self._feature_index.items():
            if idx == index:
                return fid
        return None

    def mark_dirty(self, feature_id: str):
        """
        Markiert ein Feature als geändert.

        Alle abhängigen Features werden ebenfalls als dirty markiert.
        """
        if feature_id not in self._feature_index:
            return

        # Dieses Feature ist dirty
        self._dirty_features.add(feature_id)

        # Alle Features die davon abhängen sind auch dirty (rekursiv)
        self._propagate_dirty(feature_id)

        # Checkpoints nach diesem Feature invalidieren
        index = self._feature_index[feature_id]
        self._invalidate_checkpoints_from(index)

        logger.debug(f"Feature '{feature_id}' als dirty markiert, {len(self._dirty_features)} total dirty")

    def _propagate_dirty(self, feature_id: str, visited: Optional[Set[str]] = None):
        """Propagiert dirty-Status zu allen Abhängigen."""
        if visited is None:
            visited = set()

        if feature_id in visited:
            return
        visited.add(feature_id)

        dependents = self._dependents.get(feature_id, set())
        for dep_id in dependents:
            self._dirty_features.add(dep_id)
            self._propagate_dirty(dep_id, visited)

    def get_affected_features(self, feature_id: str) -> List[str]:
        """
        Gibt alle Features zurück die neu berechnet werden müssen.

        Sortiert nach Index (Rebuild-Reihenfolge).
        """
        self.mark_dirty(feature_id)

        # Sortiere nach Index
        affected = sorted(
            self._dirty_features,
            key=lambda fid: self._feature_index.get(fid, 999)
        )

        return affected

    def get_rebuild_start_index(self, changed_feature_id: str) -> int:
        """
        Bestimmt den optimalen Start-Index für Rebuild.

        Sucht den nächsten validen Checkpoint VOR dem geänderten Feature.

        Returns:
            Index ab dem der Rebuild starten soll (0 wenn kein Checkpoint)
        """
        changed_index = self._feature_index.get(changed_feature_id, 0)

        # Suche den höchsten validen Checkpoint VOR changed_index
        best_checkpoint_index = -1

        for cp_index, checkpoint in self._checkpoints.items():
            if checkpoint.is_valid and cp_index < changed_index:
                if cp_index > best_checkpoint_index:
                    best_checkpoint_index = cp_index

        if best_checkpoint_index >= 0:
            # Rebuild ab dem Feature NACH dem Checkpoint
            return best_checkpoint_index + 1

        return 0  # Kein Checkpoint, starte von 0

    def get_checkpoint(self, index: int) -> Optional[RebuildCheckpoint]:
        """Holt einen Checkpoint für einen Index."""
        return self._checkpoints.get(index)

    def should_create_checkpoint(self, index: int) -> bool:
        """
        Entscheidet ob für diesen Index ein Checkpoint erstellt werden soll.

        Strategie: Alle N Features (checkpoint_interval).
        """
        return (index + 1) % self.checkpoint_interval == 0

    def create_checkpoint(self, index: int, feature_id: str, solid) -> Optional[RebuildCheckpoint]:
        """
        Erstellt einen Checkpoint für ein Solid.

        Args:
            index: Feature-Index
            feature_id: Feature-ID
            solid: Build123d Solid

        Returns:
            RebuildCheckpoint oder None bei Fehler
        """
        if solid is None:
            return None

        try:
            # Berechne Hash des Solids für Validierung
            solid_hash = self._compute_solid_hash(solid)

            checkpoint = RebuildCheckpoint(
                feature_index=index,
                feature_id=feature_id,
                solid_hash=solid_hash,
                is_valid=True
            )

            # Optional: BREP serialisieren für Persistenz (Phase 8)
            # checkpoint.solid_brep = self._serialize_solid(solid)

            self._checkpoints[index] = checkpoint
            logger.debug(f"Checkpoint erstellt nach Feature {index} ('{feature_id}')")

            return checkpoint

        except Exception as e:
            logger.debug(f"Checkpoint-Erstellung fehlgeschlagen: {e}")
            return None

    def _compute_solid_hash(self, solid) -> str:
        """Berechnet einen Hash für ein Solid."""
        try:
            # Einfacher Hash basierend auf geometrischen Eigenschaften
            data = []

            if hasattr(solid, 'volume'):
                data.append(f"v:{solid.volume:.6f}")

            if hasattr(solid, 'faces'):
                data.append(f"f:{len(solid.faces())}")

            if hasattr(solid, 'edges'):
                data.append(f"e:{len(solid.edges())}")

            if hasattr(solid, 'center') and solid.center:
                c = solid.center()
                data.append(f"c:{c.X:.4f},{c.Y:.4f},{c.Z:.4f}")

            hash_str = "|".join(data)
            return hashlib.md5(hash_str.encode()).hexdigest()[:16]

        except Exception:
            return ""

    def _invalidate_checkpoints_from(self, index: int):
        """Invalidiert alle Checkpoints ab einem Index."""
        for cp_index in list(self._checkpoints.keys()):
            if cp_index >= index:
                self._checkpoints[cp_index].invalidate()
                logger.debug(f"Checkpoint {cp_index} invalidiert")

    def clear_dirty(self):
        """Löscht alle dirty-Markierungen nach erfolgreichem Rebuild."""
        self._dirty_features.clear()

    def rebuild_feature_index(self, features: List['Feature']):
        """
        Baut den Index aus einer Feature-Liste neu auf.

        Sollte aufgerufen werden wenn Features hinzugefügt/entfernt werden.
        """
        self._feature_index.clear()
        self._dependencies.clear()
        self._dependents.clear()

        for i, feature in enumerate(features):
            feature_id = feature.id
            self._feature_index[feature_id] = i
            self._dependencies[feature_id] = []

            if feature_id not in self._dependents:
                self._dependents[feature_id] = set()

            # Sequentielle Abhängigkeit zum vorherigen Feature
            if i > 0:
                prev_feature = features[i - 1]
                self._add_dependency(feature_id, prev_feature.id, DependencyType.SEQUENTIAL)

            # Feature-spezifische Abhängigkeiten
            self._add_feature_specific_dependencies(feature, features[:i])

    def _add_feature_specific_dependencies(self, feature: 'Feature', prior_features: List['Feature']):
        """Fügt feature-spezifische Abhängigkeiten hinzu."""
        from modeling import (
            FilletFeature, ChamferFeature, ShellFeature, DraftFeature,
            ExtrudeFeature, RevolveFeature
        )

        # Fillet/Chamfer: Kanten-Referenz
        if isinstance(feature, (FilletFeature, ChamferFeature)):
            if hasattr(feature, 'depends_on_feature_id') and feature.depends_on_feature_id:
                self._add_dependency(
                    feature.id,
                    feature.depends_on_feature_id,
                    DependencyType.EDGE_REFERENCE
                )

        # Shell/Draft: Flächen-Referenz
        if isinstance(feature, (ShellFeature, DraftFeature)):
            # Diese referenzieren implizit das vorherige Solid
            pass  # Bereits durch SEQUENTIAL abgedeckt

        # Extrude/Revolve mit Sketch: Sketch-Referenz
        if isinstance(feature, (ExtrudeFeature, RevolveFeature)):
            if hasattr(feature, 'sketch') and feature.sketch:
                # Sketch ist kein Feature, aber wir tracken es
                pass

    def get_statistics(self) -> dict:
        """Gibt Statistiken über den Graph zurück."""
        return {
            'total_features': len(self._feature_index),
            'total_dependencies': sum(len(deps) for deps in self._dependencies.values()),
            'dirty_features': len(self._dirty_features),
            'valid_checkpoints': sum(1 for cp in self._checkpoints.values() if cp.is_valid),
            'total_checkpoints': len(self._checkpoints),
        }


# Singleton-Instance für globalen Zugriff
_global_dependency_graph: Optional[FeatureDependencyGraph] = None


def get_dependency_graph() -> FeatureDependencyGraph:
    """Holt die globale Dependency-Graph Instance."""
    global _global_dependency_graph
    if _global_dependency_graph is None:
        _global_dependency_graph = FeatureDependencyGraph()
    return _global_dependency_graph
