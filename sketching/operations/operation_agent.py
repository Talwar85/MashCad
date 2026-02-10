"""
Operation Agent - Führt CAD-Operationen auf Sketches/Solids aus

Wrapper um OCP-Operationen:
- Extrude
- Fillet / Chamfer
- Boolean (Cut, Union)
- Shell
- Revolve

Author: Claude (Sketch Agent)
Date: 2026-02-10
"""

import random
import time
from typing import Optional, List, Any, Tuple
from loguru import logger

# Importiere Modeling-Klassen
try:
    from modeling import (
        Body, Document, ExtrudeFeature, FilletFeature, ChamferFeature,
        RevolveFeature, ShellFeature, HoleFeature
    )
    from sketcher import Sketch
except ImportError:
    Body = Document = None


class OperationAgent:
    """
    Führt CAD-Operationen auf Sketches/Solids aus.

    Verwendet die MashCad Modeling-Klassen für alle Operationen.
    """

    def __init__(self, seed: Optional[int] = None):
        if seed is not None:
            random.seed(seed)

        # Statistiken
        self._operations_performed = 0
        self._operations_successful = 0

    def extrude(
        self,
        sketch: 'Sketch',
        distance: float,
        operation: str = "New Body"
    ) -> Optional[Any]:
        """
        Extrudiert einen Sketch zu einem Solid.

        Args:
            sketch: Zu extrudierender Sketch
            distance: Extrusionsdistanz
            operation: "New Body", "Join", "Cut", oder "Intersection"

        Returns:
            build123d Solid oder None bei Fehler
        """
        if Body is None:
            logger.warning("[OperationAgent] Modeling nicht verfügbar")
            return None

        start_time = time.time()

        try:
            logger.debug(f"[OperationAgent] Extrude: distance={distance}, op={operation}")

            # Document und Body erstellen
            doc = Document("AgentDoc")
            body = Body("AgentBody", document=doc)
            doc.add_body(body)

            # ExtrudeFeature erstellen
            feature = ExtrudeFeature(
                sketch=sketch,
                distance=distance,
                operation=operation
            )
            body.add_feature(feature)

            # Solid holen
            solid = body._build123d_solid

            duration_ms = (time.time() - start_time) * 1000
            self._operations_performed += 1
            if solid is not None:
                self._operations_successful += 1
                logger.debug(f"[OperationAgent] Extrude Success: {duration_ms:.2f}ms")
            else:
                logger.warning("[OperationAgent] Extrude gab None zurück")

            return solid

        except Exception as e:
            duration_ms = (time.time() - start_time) * 1000
            logger.error(f"[OperationAgent] Extrude Error: {e}")
            return None

    def fillet(
        self,
        solid: Any,
        radius: float,
        edge_indices: Optional[List[int]] = None
    ) -> Optional[Any]:
        """
        Rundet Kanten ab.

        Args:
            solid: Eingabe-Solid
            radius: Fillet-Radius
            edge_indices: Indizes der Kanten (None = alle Kanten)

        Returns:
            Neuer Solid mit Fillets oder None
        """
        if Body is None or solid is None:
            return None

        start_time = time.time()

        try:
            logger.debug(f"[OperationAgent] Fillet: radius={radius}, edges={edge_indices}")

            # Wenn keine edges angegeben, nimm erste 4
            if edge_indices is None:
                edge_indices = [0, 1, 2, 3]

            # Document und Body erstellen
            doc = Document("AgentDoc")
            body = Body("AgentBody", document=doc)
            doc.add_body(body)

            # Basis-Solid setzen (über ImportFeature)
            # TODO: Implementiere Import für Solid
            # Für jetzt: None zurückgeben
            logger.warning("[OperationAgent] Fillet noch nicht vollständig implementiert")

            return None

        except Exception as e:
            logger.error(f"[OperationAgent] Fillet Error: {e}")
            return None

    def chamfer(
        self,
        solid: Any,
        distance: float,
        edge_indices: Optional[List[int]] = None
    ) -> Optional[Any]:
        """Fasst Kanten ab."""
        if solid is None:
            return None

        logger.debug(f"[OperationAgent] Chamfer: distance={distance}")
        # TODO: Implementieren
        return None

    def boolean_cut(
        self,
        base_solid: Any,
        tool_solid: Any
    ) -> Optional[Any]:
        """
        Subtrahiert Tool von Base.

        Args:
            base_solid: Basis-Solid
            tool_solid: Werkzeug-Solid (wird subtrahiert)

        Returns:
            Resultat-Solid oder None
        """
        if base_solid is None or tool_solid is None:
            return None

        logger.debug("[OperationAgent] Boolean Cut")
        # TODO: Implementieren
        return None

    def boolean_union(
        self,
        solid1: Any,
        solid2: Any
    ) -> Optional[Any]:
        """Vereint zwei Solids."""
        if solid1 is None or solid2 is None:
            return None

        logger.debug("[OperationAgent] Boolean Union")
        # TODO: Implementieren
        return None

    def shell(
        self,
        solid: Any,
        thickness: float,
        face_indices: Optional[List[int]] = None
    ) -> Optional[Any]:
        """
        Erstellt Hohlkörper.

        Args:
            solid: Eingabe-Solid
            thickness: Wandstärke
            face_indices: Zu öffnende Faces

        Returns:
            Gehäuse-Solid oder None
        """
        if solid is None:
            return None

        logger.debug(f"[OperationAgent] Shell: thickness={thickness}")
        # TODO: Implementieren
        return None

    def revolve(
        self,
        sketch: 'Sketch',
        angle: float = 360.0
    ) -> Optional[Any]:
        """
        Rotiert Sketch um Achse.

        Args:
            sketch: Zu rotierender Sketch
            angle: Rotationswinkel in Grad

        Returns:
            Rotations-Solid oder None
        """
        if sketch is None:
            return None

        logger.debug(f"[OperationAgent] Revolve: angle={angle}")
        # TODO: Implementieren
        return None

    # === Adaptive Parameter Selection ===

    def select_extrude_distance(
        self,
        sketch_area: float,
        mode: str = "adaptive"
    ) -> float:
        """
        Wählt Extrusions-Distanz basierend auf Sketch-Grösse.

        Heuristik:
        - Distanz sollte im Verhältnis zur Sketch-Grösse stehen
        - Zu dünn: unstable
        - Zu dick: unnötig viel Material

        Args:
            sketch_area: Fläche des Sketches
            mode: "random", "adaptive", oder "conservative"

        Returns:
            Gewählte Distanz
        """
        if mode == "random":
            return random.uniform(5, 100)

        # Adaptive: Distanz ~ 10-50% der Sketch-Dimension
        base_size = (sketch_area ** 0.5) if sketch_area > 0 else 10

        if mode == "conservative":
            return base_size * random.uniform(0.1, 0.3)
        else:  # adaptive
            return base_size * random.uniform(0.2, 0.8)

    def select_fillet_radius(
        self,
        edge_length: float,
        mode: str = "adaptive"
    ) -> float:
        """
        Wählt Fillet-Radius basierend auf Kantenlänge.

        Heuristik:
        - Radius sollte 5-20% der Kantenlänge sein
        - Zu gross: Fehler
        - Zu klein: unsichtbar

        Args:
            edge_length: Länge der Kante
            mode: "random", "adaptive", oder "conservative"

        Returns:
            Gewählter Radius
        """
        if mode == "random":
            return random.uniform(1, 10)

        # Adaptive: Radius ~ 5-15% der edge length
        if mode == "conservative":
            return edge_length * random.uniform(0.02, 0.08)
        else:  # adaptive
            return edge_length * random.uniform(0.05, 0.15)

    @property
    def success_rate(self) -> float:
        """Erfolgsrate der Operationen."""
        if self._operations_performed == 0:
            return 0.0
        return self._operations_successful / self._operations_performed

    def get_stats(self) -> dict:
        """Statistiken des OperationAgent."""
        return {
            "operations_performed": self._operations_performed,
            "operations_successful": self._operations_successful,
            "success_rate": self.success_rate
        }
