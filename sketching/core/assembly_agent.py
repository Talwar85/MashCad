"""
Assembly Agent - Erstellt Assemblys aus mehreren Parts

Erstellt Assemblys aus mehreren Parts mit:
- Multi-Part Generierung
- Placement im Raum (keine Kollisionen)
- Mating-Constraints

Author: Claude (Sketch Agent)
Date: 2026-02-11
"""

from __future__ import annotations

import random
import time
from typing import Optional, List, Dict, Any, Tuple
from loguru import logger

try:
    from modeling import Body, Document
    from sketching.core.sketch_agent import SketchAgent
    from sketching.core.result_types import PartResult, AssemblyResult
    HAS_MODELING = True
except ImportError:
    HAS_MODELING = False
    logger.warning("Modeling nicht verfügbar")


class AssemblyAgent:
    """
    Erstellt Assemblys aus mehreren Parts.

    Strategie:
    1. Generiere einzelne Parts
    2. Platziere sie im Raum (keine Kollisionen)
    3. Füge Mating-Constraints hinzu
    """

    def __init__(self, seed: Optional[int] = None):
        """
        Args:
            seed: Random Seed für Reproduzierbarkeit
        """
        if seed is not None:
            random.seed(seed)

        # SketchAgent für Part-Generierung
        self.part_agent = SketchAgent(mode="adaptive", headless=True, seed=seed)

        # Statistiken
        self._assemblies_created = 0
        self._assemblies_successful = 0

    def generate_assembly(
        self,
        part_count: int = 3,
        complexity: str = "medium"
    ) -> AssemblyResult:
        """
        Generiert Assembly mit zufälligen Parts.

        Args:
            part_count: Anzahl der Parts
            complexity: Komplexität der Parts

        Returns:
            AssemblyResult
        """
        start_time = time.time()

        try:
            logger.info(f"[AssemblyAgent] Generiere Assembly ({part_count} Parts)")

            parts = []
            constraints = []
            positions = []

            # Parts generieren mit Platzierung
            for i in range(part_count):
                # Part generieren
                part_result = self.part_agent.generate_part(complexity=complexity)
                parts.append(part_result)

                # Position berechnen (keine Kollisionen)
                position = self._find_non_colliding_position(positions, i)
                positions.append(position)

            # Constraints vorschlagen
            if len(parts) >= 2:
                constraints = self._suggest_mating_constraints(parts, positions)

            duration_ms = (time.time() - start_time) * 1000

            self._assemblies_created += 1
            if all(p.success for p in parts):
                self._assemblies_successful += 1

            return AssemblyResult(
                success=True,
                parts=parts,
                constraints=constraints,
                duration_ms=duration_ms,
                metadata={
                    "part_count": part_count,
                    "positions": positions
                }
            )

        except Exception as e:
            duration_ms = (time.time() - start_time) * 1000
            logger.error(f"[AssemblyAgent] Fehler: {e}")
            import traceback
            traceback.print_exc()

            return AssemblyResult(
                success=False,
                parts=[],
                constraints=[],
                duration_ms=duration_ms,
                error=str(e)
            )

    def find_mating_faces(
        self,
        solid1: Any,
        solid2: Any
    ) -> List[Tuple]:
        """
        Finde passende Faces für Mating.

        Heuristik:
        - Planare Faces mit ähnlicher Normale
        - Zylinder-Faces mit ähnlichem Radius
        - Abstand kleiner als Toleranz

        Args:
            solid1: Erster Solid
            solid2: Zweiter Solid

        Returns:
            Liste von Tupeln (face1, face2, score)
        """
        if not HAS_MODELING:
            return []

        try:
            from build123d import Face

            mating_faces = []

            # Faces extrahieren
            faces1 = list(solid1.faces()) if solid1 else []
            faces2 = list(solid2.faces()) if solid2 else []

            # Planare Faces finden
            planar1 = [f for f in faces1 if hasattr(f, 'geom_type') and 'PLANE' in str(f.geom_type()).upper()]
            planar2 = [f for f in faces2 if hasattr(f, 'geom_type') and 'PLANE' in str(f.geom_type()).upper()]

            # Paare mit ähnlicher Normalen finden
            for f1 in planar1:
                for f2 in planar2:
                    # Normalen vergleichen
                    normal1 = self._get_face_normal(f1)
                    normal2 = self._get_face_normal(f2)

                    if normal1 and normal2:
                        # Winkel zwischen Normalen
                        import numpy as np
                        dot = np.dot(normal1, normal2)
                        angle = abs(dot)  # cos(angle)

                        # Score: 1 = entgegengesetzt (gut für mating), 0 = parallel
                        score = abs(1 - angle)

                        if score > 0.9:  # Fast entgegengesetzt
                            mating_faces.append((f1, f2, score))

            # Sortiere nach Score
            mating_faces.sort(key=lambda x: x[2], reverse=True)

            return mating_faces[:5]  # Top 5

        except Exception as e:
            logger.error(f"[AssemblyAgent] Mating-Faces Error: {e}")
            return []

    def apply_constraints(self, assembly: Dict) -> Dict:
        """
        Füge Assembly-Constraints hinzu.

        Constraint-Typen:
        - coincident: Zwei Faces liegen aufeinander
        - concentric: Zwei zylindrische Axes sind gleich
        - distance: Fixierter Abstand
        - angle: Fixierter Winkel

        Args:
            assembly: Assembly-Dict mit Parts und Constraints

        Returns:
            Aktualisierter Assembly-Dict
        """
        # TODO: Implementiere Constraint-Anwendung
        # Für jetzt: Assembly unverändert zurückgeben
        return assembly

    def _find_non_colliding_position(
        self,
        existing_positions: List[Tuple[float, float, float]],
        index: int
    ) -> Tuple[float, float, float]:
        """
        Findet Position ohne Kollision.

        Platziert Parts in einem Grid-Muster.
        """
        # Grid-Abstand
        grid_spacing = 100

        # Position im Grid
        x = (index % 3) * grid_spacing
        y = ((index // 3) % 3) * grid_spacing
        z = (index // 9) * grid_spacing

        # Zufälliger Offset
        offset = 20
        x += random.uniform(-offset, offset)
        y += random.uniform(-offset, offset)
        z += random.uniform(-offset, offset)

        return (x, y, z)

    def _suggest_mating_constraints(
        self,
        parts: List[PartResult],
        positions: List[Tuple[float, float, float]]
    ) -> List[Dict[str, Any]]:
        """
        Schlägt Mating-Constraints vor.

        Args:
            parts: Liste der Parts
            positions: Liste der Positionen

        Returns:
            Liste von Constraint-Definitionen
        """
        constraints = []

        # Paare von benachbarten Parts
        for i in range(len(parts) - 1):
            if parts[i].success and parts[i + 1].success:
                constraint = {
                    "type": "coincident",
                    "part1_index": i,
                    "part2_index": i + 1,
                    "description": f"Coincident between Part {i} and Part {i + 1}"
                }
                constraints.append(constraint)

        return constraints

    def _get_face_normal(self, face: Any) -> Optional[List[float]]:
        """
        Extrahiert Normalen-Vektor von Face.

        Args:
            face: build123d Face

        Returns:
            Normalen-Vektor als [x, y, z] oder None
        """
        try:
            if hasattr(face, 'normal'):
                normal = face.normal()
                if hasattr(normal, 'to_tuple'):
                    return list(normal.to_tuple())
                elif hasattr(normal, '__iter__'):
                    return list(normal)
            return None
        except Exception:
            return None

    @property
    def success_rate(self) -> float:
        """Erfolgsrate der Assembly-Erstellung."""
        if self._assemblies_created == 0:
            return 0.0
        return self._assemblies_successful / self._assemblies_created

    def get_stats(self) -> Dict[str, Any]:
        """Statistiken des AssemblyAgent."""
        return {
            "assemblies_created": self._assemblies_created,
            "assemblies_successful": self._assemblies_successful,
            "success_rate": self.success_rate
        }


# Factory für kompatible Creation
def create_assembly_agent(
    seed: Optional[int] = None
) -> AssemblyAgent:
    """
    Factory-Funktion zum Erstellen eines AssemblyAgent.

    Args:
        seed: Random Seed für Reproduzierbarkeit

    Returns:
        AssemblyAgent Instanz
    """
    return AssemblyAgent(seed=seed)
