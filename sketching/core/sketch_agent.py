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
from sketching.analysis.reconstruction_agent import ReconstructionAgent
from modeling import Body, ExtrudeFeature, FilletFeature


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
        document=None,
        mode: str = "adaptive",
        headless: bool = True,
        seed: Optional[int] = None
    ):
        self.mode = mode  # "random", "adaptive", "guided"
        self.headless = headless
        self.document = document  # ← Document für Sketch/Body Integration

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
        
        # Viewport (optional, used by Visual subclass)
        self.viewport = None

    def generate_part(
        self,
        complexity: str = "medium"
    ) -> PartResult:
        """
        Generiert ein komplettes Bauteil mit Sketch im Browser.

        Args:
            complexity: "simple", "medium", oder "complex"

        Returns:
            PartResult mit generiertem Solid
        """
        start_time = time.time()
        operations = []
        sketches_created = []

        try:
            logger.info(f"[SketchAgent] Generiere Part (complexity={complexity})")

            # Prüfe ob Document verfügbar
            if self.document is None:
                # Fallback: Kein Document → Solid direkt (headless mode)
                return self._generate_part_headless(complexity, start_time)

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
            operations.append("generate_sketch")

            # Sketch benennen und zum Document hinzufügen
            import uuid
            sketch_name = f"Agent_Sketch_{uuid.uuid4().hex[:8]}"
            sketch.name = sketch_name

            # Sketch zum Document hinzufügen (erscheint im Browser!)
            self.document.sketches.append(sketch)
            self.document.active_sketch = sketch  # Optional: als aktiv setzen
            sketches_created.append(sketch_name)
            logger.info(f"[SketchAgent] Sketch '{sketch_name}' zum Document hinzugefügt")

            # 2. Body erstellen
            body_name = f"AgentBody_{uuid.uuid4().hex[:8]}"
            body = Body(body_name, document=self.document)
            self.document.add_body(body)
            logger.info(f"[SketchAgent] Body '{body_name}' erstellt")

            # 3. Extrusions-Distanz wählen
            distance = self.operations.select_extrude_distance(
                sketch_area=1000,  # Schätzung
                mode=self.mode
            )

            # 4. ExtrudeFeature mit Sketch-Quelle erstellen
            from modeling import ExtrudeFeature
            extrude_feat = ExtrudeFeature(
                sketch=sketch,
                distance=distance,
                operation="New Body"
            )
            body.add_feature(extrude_feat)
            operations.append(f"extrude({distance:.1f}mm)")

            # 5. Zusätzliche Features je nach Komplexität
            self._add_additional_features(
                body=body,
                base_sketch=sketch,
                complexity=complexity,
                sketches_created=sketches_created,
                operations=operations
            )

            # 6. Rebuild → erstellt Solid aus Sketch!

            duration_ms = (time.time() - start_time) * 1000
            logger.info(f"[SketchAgent] Part generiert: {duration_ms:.2f}ms")

            # Stats aktualisieren
            self._parts_generated += 1
            self._parts_successful += 1

            return PartResult(
                success=True,
                solid=body._build123d_solid,
                operations=operations,
                duration_ms=duration_ms,
                sketch_count=len(sketches_created),
                metadata={
                    "complexity": complexity,
                    "distance": distance,
                    "sketch_name": sketch_name,
                    "body_name": body_name
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

    def _add_additional_features(
        self,
        body: Body,
        base_sketch,
        complexity: str,
        sketches_created: list,
        operations: list
    ) -> bool:
        """
        Fügt zusätzliche Features je nach Komplexität hinzu.

        Args:
            body: Der Body mit Features
            base_sketch: Der Basis-Sketch
            complexity: "simple", "medium", "complex"
            sketches_created: Liste der Sketch-Namen
            operations: Liste der Operationen

        Returns:
            True bei Erfolg, False bei Fehler
        """
        import uuid
        from modeling import FilletFeature

        if complexity == "simple":
            # Simple: Keine zusätzlichen Features
            return True

        elif complexity == "medium":
            # Medium: Fillet auf ausgewählten Edges
            try:
                # Edges vom Solid auswählen (z.B. alle vertikalen Edges)
                solid = body._build123d_solid
                if solid is None:
                    return False

                # Finde Kanten für Fillet (z.B. die Seitenkanten)
                edges = list(solid.edges())
                if len(edges) >= 4:
                    # Nimm die ersten 4 Edges für Fillet
                    fillet_edges = edges[:4]
                    fillet_radius = random.uniform(2, 5)

                    # Extrahiere OCP Shapes für FilletFeature
                    ocp_edges = [e.wrapped for e in fillet_edges]

                    fillet_feat = FilletFeature(
                        ocp_edge_shapes=ocp_edges,
                        radius=fillet_radius
                    )
                    body.add_feature(fillet_feat)
                    operations.append(f"fillet({len(fillet_edges)} edges, r={fillet_radius:.1f})")
                    logger.info(f"[SketchAgent] Fillet hinzugefügt: {len(fillet_edges)} edges")

            except Exception as e:
                logger.warning(f"[SketchAgent] Fillet fehlgeschlagen: {e}")

            return True

        elif complexity == "complex":
            # Complex: Mehrere Features
            try:
                solid = body._build123d_solid
                if solid is None:
                    return False

                edges = list(solid.edges())

                # 1. Fillet
                if len(edges) >= 4:
                    fillet_edges = edges[:4]
                    fillet_radius = random.uniform(2, 5)

                    # Extrahiere OCP Shapes für FilletFeature
                    ocp_edges = [e.wrapped for e in fillet_edges]

                    fillet_feat = FilletFeature(
                        ocp_edge_shapes=ocp_edges,
                        radius=fillet_radius
                    )
                    body.add_feature(fillet_feat)
                    operations.append(f"fillet({len(fillet_edges)} edges, r={fillet_radius:.1f})")

                # 2. Zweiter Sketch für zusätzliches Feature (z.B. Bohrung)
                # Erstelle einen neuen Sketch auf einer Face
                faces = list(solid.faces())
                if len(faces) > 0:
                    # Nimm die obere Fläche
                    top_face = faces[0]

                    # Erstelle Sketch für Bohrung mit Sketch.add_circle()
                    from sketcher import Sketch
                    hole_sketch = Sketch(f"Agent_Sketch_{uuid.uuid4().hex[:8]}")

                    # Kreis in der Mitte - add_circle nimmt cx, cy, radius
                    radius = random.uniform(5, 15)
                    hole_sketch.add_circle(0, 0, radius)  # cx, cy, radius
                    hole_sketch.add_fixed(hole_sketch.points[0])  # Center fixieren

                    # Sketch zum Document hinzufügen
                    self.document.sketches.append(hole_sketch)
                    sketches_created.append(hole_sketch.name)
                    operations.append("hole_sketch")

                    logger.info(f"[SketchAgent] Hole-Sketch '{hole_sketch.name}' erstellt")

                    # Cut Feature für Bohrung
                    from modeling import ExtrudeFeature
                    distance = 50  # Tiefe genug zum Cutten
                    cut_feat = ExtrudeFeature(
                        sketch=hole_sketch,
                        distance=distance,
                        operation="Cut"
                    )
                    body.add_feature(cut_feat)
                    operations.append(f"cut_hole(d={distance}mm)")

            except Exception as e:
                logger.warning(f"[SketchAgent] Complex features fehlgeschlagen: {e}")

            return True

        return True

    def _generate_part_headless(self, complexity: str, start_time: float) -> PartResult:
        """
        Fallback: Headless-Modus ohne Document.
        Erstellt Solid direkt ohne Sketch im Browser.
        """
        operations = []

        try:
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
            operations.append("generate_sketch")

            # 2. Extrusions-Distanz wählen
            distance = self.operations.select_extrude_distance(
                sketch_area=1000,
                mode=self.mode
            )

            # 3. Extrudieren (Solid direkt)
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
            logger.info(f"[SketchAgent] Part generiert (headless): {duration_ms:.2f}ms")

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
            logger.error(f"[SketchAgent] Fehler (headless): {e}")
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
        interactive: bool = True,
        analysis=None  # Added analysis
    ) -> ReconstructionResult:
        """
        Rekonstruiert CAD aus Mesh.

        Args:
            mesh_path: Pfad zur STL/OBJ Datei
            interactive: Ob der User zuschauen kann
            analysis: Optional vor-analysiertes Mesh
        """
        # Erstelle ReconstructionAgent für diesen Aufruf
        recon_agent = ReconstructionAgent(
            document=self.document,  # Pass Document!
            viewport=getattr(self, 'viewport', None),
            slow_mode=interactive,
            step_delay=0.5 if interactive else 0.0
        )

        # Callbacks für UI-Updates registrieren
        if self.viewport:
            recon_agent.on_step_start = self._on_reconstruction_step_start
            recon_agent.on_step_complete = self._on_reconstruction_step_complete
            recon_agent.on_progress = self._on_reconstruction_progress

        # Rekonstruktion ausführen
        return recon_agent.reconstruct_from_mesh(mesh_path, interactive, analysis=analysis)

    def _on_reconstruction_step_start(self, step):
        """Callback: Rekonstruktions-Schritt gestartet."""
        logger.info(f"[Reconstruction] Schritt {step.step_id}: {step.description}")

    def _on_reconstruction_step_complete(self, step, result):
        """Callback: Rekonstruktions-Schritt abgeschlossen."""
        logger.info(f"[Reconstruction] Schritt {step.step_id} abgeschlossen")

    def _on_reconstruction_progress(self, progress, message):
        """Callback: Fortschritt aktualisieren."""
        logger.info(f"[Reconstruction] {progress*100:.0f}%: {message}")

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
    document=None,
    mode: str = "adaptive",
    headless: bool = True,
    seed: Optional[int] = None
) -> SketchAgent:
    """
    Factory-Funktion zum Erstellen eines SketchAgent.

    Args:
        document: Document für Sketch/Body Integration (optional)
        mode: "random", "adaptive", oder "guided"
        headless: Ob ohne UI laufen
        seed: Random Seed für Reproduzierbarkeit

    Returns:
        SketchAgent Instanz
    """
    return SketchAgent(document=document, mode=mode, headless=headless, seed=seed)
