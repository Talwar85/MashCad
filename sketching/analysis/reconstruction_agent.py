"""
Reconstruction Agent - Rekonstruiert CAD aus Mesh

Interaktiver Agent der:
1. Mesh analysiert
2. Schritte plant
3. Schritt-für-Schritt ausführt mit visueller Rückmeldung

Author: Claude (Sketch Agent)
Date: 2026-02-10
"""

import time
import numpy as np
from typing import Optional, List, Any, Callable
from loguru import logger

from sketching.core.result_types import ReconstructionResult, PartResult, MeshAnalysis
from sketching.analysis.mesh_analyzer import MeshAnalyzer, ReconstructionStep


class ReconstructionAgent:
    """
    Agent der Meshes zu CAD rekonstruiert.

    Interaktiv + Visual:
    - User sieht jeden Schritt
    - Agent erklärt was er tut
    - User kann eingreifen/pausieren
    """

    def __init__(
        self,
        document=None,  # Added document
        viewport=None,
        slow_mode: bool = True,
        step_delay: float = 0.5
    ):
        """
        Args:
            document: Target CAD Document
            viewport: PyVista Viewport für Visualisierung
            slow_mode: Ob Delays zwischen Schritten eingefügt werden
            step_delay: Delay in Sekunden zwischen Schritten
        """
        self.document = document
        self.analyzer = MeshAnalyzer()
        self.viewport = viewport
        self.slow_mode = slow_mode
        self.step_delay = step_delay

        # Callbacks für UI-Updates
        self.on_step_start: Optional[Callable[[ReconstructionStep], None]] = None
        self.on_step_complete: Optional[Callable[[ReconstructionStep, Any], None]] = None
        self.on_progress: Optional[Callable[[float, str], None]] = None

    def reconstruct_from_mesh(
        self,
        mesh_path: str,
        interactive: bool = True,
        analysis: Optional[MeshAnalysis] = None  # Added analysis
    ) -> ReconstructionResult:
        """
        Rekonstruiert CAD aus Mesh.

        Ablauf (interaktiv):
        1. Mesh analysieren (oder existierende Analyse nutzen)
        2. Schritte planen
        3. Schritt-für-Schritt ausführen:
           - Sketch erstellen (User sieht)
           - Extrudieren (User sieht Animation)
           - Fillets (User sieht Vorschau)

        Args:
            mesh_path: Pfad zur STL/OBJ Datei
            interactive: Ob User zuschauen kann
            analysis: Optional vor-analysiertes Mesh (z.B. aus UI)

        Returns:
            ReconstructionResult
        """
        start_time = time.time()
        steps = []
        solid = None
        current_sketch = None

        try:
            logger.info(f"[ReconstructionAgent] Rekonstruiere Mesh: {mesh_path}")

            # 1. Mesh analysieren (wenn nicht übergeben)
            if analysis is None:
                if self.on_progress:
                    self.on_progress(0.1, "Analysiere Mesh...")

                self._notify("Starte Mesh-Analyse...")
                analysis = self.analyzer.analyze(mesh_path)
            else:
                 logger.info("Verwende existierende Analyse")

            if self.slow_mode:
                time.sleep(self.step_delay)

            # 2. Schritte planen (falls nötig, MeshAnalysis hat steps)
            if self.on_progress:
                self.on_progress(0.3, "Plane Rekonstruktion...")

            if hasattr(analysis, 'primitive_count'):
                self._notify(f"Analyse abgeschlossen: {analysis.primitive_count} Primitives")
            elif hasattr(analysis, 'holes'):
                count = len(analysis.holes) + (1 if analysis.base_plane else 0)
                self._notify(f"Analyse abgeschlossen: {count} Features (STL)")
            else:
                self._notify("Analyse abgeschlossen")

            # 2. Schritte planen
            step_data_list = []
            
            # Check if analysis is STLFeatureAnalysis (duck typing or check class name)
            is_stl_analysis = hasattr(analysis, 'base_plane') and hasattr(analysis, 'holes')
            
            if is_stl_analysis:
                logger.info("Konvertiere STLFeatureAnalysis in Rekonstruktions-Schritte")
                step_data_list = self._convert_stl_analysis_to_steps(analysis)
            elif hasattr(analysis, 'suggested_steps'):
                 step_data_list = analysis.suggested_steps
            else:
                 logger.warning("Unbekanntes Analyse-Format")
                 step_data_list = []
            
            if self.on_progress:
                self.on_progress(0.3, f"Plane Rekonstruktion ({len(step_data_list)} Schritte)...")

            # 3. Schritte ausführen
            step_id = 0
            total_steps = len(step_data_list)

            for step_data in step_data_list:
                # Convert dict to ReconstructionStep if needed
                if isinstance(step_data, dict):
                    step = ReconstructionStep(**step_data)
                else:
                    step = step_data # Already a Step object?
                
                # Schritt-Start Callback
                if self.on_step_start:
                    self.on_step_start(step)

                self._notify(f"Schritt {step_id + 1}/{total_steps}: {step.description}")

                # Schritt ausführen mit Kontext
                result = self._execute_step_with_context(
                    step,
                    sketch=current_sketch,
                    solid=solid
                )

                # Kontext aktualisieren
                if step.operation == "create_profile" and result is not None:
                    current_sketch = result
                elif step.operation == "extrude" and result is not None:
                    solid = result
                    current_sketch = None  # Sketch wurde verbraucht
                elif step.operation == "fillet" and result is not None:
                    solid = result

                if result:
                    steps.append(step)

                    # Schritt-Complete Callback
                    if self.on_step_complete:
                        self.on_step_complete(step, result)

                # Fortschritt
                progress = 0.3 + (0.7 * (step_id + 1) / total_steps)
                if self.on_progress:
                    self.on_progress(progress, f"Schritt {step_id + 1}/{total_steps}")

                if self.slow_mode:
                    time.sleep(self.step_delay)

                step_id += 1

            duration_ms = (time.time() - start_time) * 1000

            return ReconstructionResult(
                success=solid is not None,
                solid=solid,
                analysis=analysis,
                executed_steps=[s.to_dict() for s in steps],
                duration_ms=duration_ms,
                error=None if solid is not None else "Rekonstruktion ohne Solid-Ergebnis"
            )

        except Exception as e:
            duration_ms = (time.time() - start_time) * 1000
            logger.error(f"[ReconstructionAgent] Fehler: {e}")
            import traceback
            traceback.print_exc()

            return ReconstructionResult(
                success=False,
                solid=None,
                analysis=MeshAnalysis([], [], {}, {}, 0),
                executed_steps=[],
                duration_ms=duration_ms,
                error=str(e)
            )

    def _execute_step(self, step: ReconstructionStep) -> Optional[Any]:
        """
        Führt einen einzelnen Rekonstruktions-Schritt aus.

        Args:
            step: ReconstructionStep mit operation und params

        Returns:
            Ergebnis des Schritts
        """
        return self._execute_step_with_context(step, sketch=None, solid=None)

    def _execute_step_with_context(
        self,
        step: ReconstructionStep,
        sketch: Optional[Any] = None,
        solid: Optional[Any] = None
    ) -> Optional[Any]:
        """
        Führt einen Schritt mit Kontext aus.

        Args:
            step: ReconstructionStep mit operation und params
            sketch: Aktueller Sketch (von vorherigen create_profile)
            solid: Aktuelles Solid (von vorherigen extrude/fillet)

        Returns:
            Ergebnis des Schritts
        """
        logger.debug(f"[ReconstructionAgent] Führe aus: {step.operation}")

        # Params mit Kontext anreichern
        enriched_params = dict(step.params)

        if step.operation == "create_plane":
            return self._create_plane(enriched_params)

        elif step.operation == "create_profile":
            return self._create_profile(enriched_params)

        elif step.operation == "extrude":
            # Sketch hinzufügen wenn vorhanden
            if sketch is not None:
                enriched_params["sketch"] = sketch
            return self._extrude(enriched_params)

        elif step.operation == "fillet":
            # Solid hinzufügen
            if solid is not None:
                enriched_params["solid"] = solid
            return self._add_fillet(enriched_params)

        elif step.operation == "error":
            logger.error(step.description)
            return None

        else:
            logger.warning(f"[ReconstructionAgent] Unbekannte Operation: {step.operation}")
            return None

    # === Interne Schritt-Implementierung ===

    def _create_plane(self, params: dict) -> Any:
        """
        Erstellt Base-Plane.

        In MashCad ist die Base-Plane implizit (XY-Plane).
        Diese Methode dient nur der Dokumentation.
        """
        plane_info = params.get("plane", {})
        logger.debug(f"[ReconstructionAgent] Base-Plane: {plane_info}")
        return {"type": "plane", "info": plane_info}

    def _create_profile(self, params: dict) -> Any:
        """
        Erstellt 2D-Profil im Sketch.

        Unterstützte Profile-Typen:
        - circle: Kreis mit radius (using polygon approximation for closed_profile)
        - rectangle: Rechteck mit width, height
        - polygon: Polygon mit sides, radius

        Args:
            params: Dict mit 'type' und typ-spezifischen Parametern
        """
        try:
            from sketcher import Sketch

            profile_type = params.get("type", "circle")
            sketch_name = f"reconstruction_profile_{profile_type}"

            sketch = Sketch(sketch_name)
            
            # Set plane if provided
            if "plane_origin" in params:
                 sketch.plane_origin = params["plane_origin"]
            if "plane_normal" in params:
                 sketch.plane_normal = params["plane_normal"]

            if profile_type == "circle":
                # Circle wird als Polygon mit vielen Seiten approximiert
                # damit closed_profiles funktioniert
                radius = params.get("radius", 10)
                center = params.get("center", (0, 0))
                # 32 Seiten = glatter Kreis
                sketch.add_regular_polygon(center[0], center[1], radius, 32)

            elif profile_type == "rectangle":
                width = params.get("width", 20)
                height = params.get("height", 20)
                center = params.get("center", (0, 0))
                # Rechteck zentriert erstellen
                x = center[0] - width / 2
                y = center[1] - height / 2
                sketch.add_rectangle(x, y, width, height)

            elif profile_type == "polygon":
                points = params.get("points")
                if points:
                    # Case 1: Explicit points (3D global)
                    # We must project them to the sketch plane
                    
                    # Get Plane Info
                    origin = np.array(params.get("plane_origin", (0,0,0)))
                    normal = np.array(params.get("plane_normal", (0,0,1)))
                    
                    # Check if normal is valid
                    if np.linalg.norm(normal) < 1e-6:
                        normal = np.array((0,0,1))
                    
                    # Compute X/Y directions
                    # X-Dir: Perpendicular to Normal
                    if abs(normal[2]) < 0.99:
                        x_dir = np.cross((0,0,1), normal)
                    else:
                        x_dir = np.cross((1,0,0), normal)
                    x_dir = x_dir / np.linalg.norm(x_dir)
                    
                    # Y-Dir: Normal x X-Dir
                    y_dir = np.cross(normal, x_dir)
                    y_dir = y_dir / np.linalg.norm(y_dir)
                    
                    # Set Sketch Plane info explicitely
                    sketch.plane_origin = tuple(origin)
                    sketch.plane_normal = tuple(normal)
                    sketch.plane_x_dir = tuple(x_dir)
                    sketch.plane_y_dir = tuple(y_dir)
                    
                    # Project Points
                    projected_points = []
                    for p in points:
                        vec = np.array(p) - origin
                        u = np.dot(vec, x_dir)
                        v = np.dot(vec, y_dir)
                        projected_points.append((u, v))
                        
                    sketch.add_polygon(projected_points)
                    
                else:
                    # Case 2: Regular Polygon (sides/radius)
                    sides = params.get("sides", 6)
                    radius = params.get("radius", 10)
                    center = params.get("center", (0, 0))
                    sketch.add_regular_polygon(center[0], center[1], radius, sides)

            else:
                logger.warning(f"[ReconstructionAgent] Unbekannter Profil-Typ: {profile_type}")
                return None

            # Prüfe ob Profile geschlossen sind
            if sketch.closed_profiles:
                logger.debug(f"[ReconstructionAgent] Profil erstellt: {profile_type}")
                return sketch
            else:
                logger.warning(f"[ReconstructionAgent] Profil nicht geschlossen: {profile_type}")
                return None

        except ImportError:
            logger.error("[ReconstructionAgent] Sketcher nicht verfügbar")
            return None
        except Exception as e:
            logger.error(f"[ReconstructionAgent] Profil-Erstellung fehlgeschlagen: {e}")
            return None

    def _extrude(self, params: dict) -> Any:
        """
        Extrudiert Profil zu Solid.

        Benötigt:
        - sketch: Der zu extrudierende Sketch
        - distance: Extrusionsdistanz

        Args:
            params: Dict mit Sketch und Distanz
        """
        try:
            from modeling import Body, Document, ExtrudeFeature

            sketch = params.get("sketch")
            distance = params.get("distance", 20)

            if sketch is None:
                logger.warning("[ReconstructionAgent] Kein Sketch für Extrusion")
                return None

            # Document und Body erstellen/nutzen
            if self.document:
                doc = self.document
                # Prüfen ob wir schon einen Body für dieses Part haben
                # Für vereinfachte Rekonstruktion erstellen wir einen neuen
                import uuid
                body_name = f"Reconstructed_{uuid.uuid4().hex[:6]}"
                body = Body(body_name, document=doc)
                doc.add_body(body)
                
                # Sketch auch zum Doc hinzufügen falls noch nicht dort
                if sketch not in doc.sketches:
                    doc.sketches.append(sketch)
            else:
                # Standalone Mode
                doc = Document("ReconstructionDoc")
                body = Body("ReconstructionBody", document=doc)
                doc.add_body(body)

            # ExtrudeFeature erstellen
            op_str = params.get("operation", "New Body")
            feature = ExtrudeFeature(
                sketch=sketch,
                distance=distance,
                operation=op_str
            )
            body.add_feature(feature)

            # Solid holen
            solid = body._build123d_solid

            if solid is not None:
                logger.debug(f"[ReconstructionAgent] Extrudiert: {distance}mm")
                return solid
            else:
                logger.warning("[ReconstructionAgent] Extrusion gab None zurück")
                return None

        except ImportError:
            logger.error("[ReconstructionAgent] Modeling nicht verfügbar")
            return None
        except Exception as e:
            logger.error(f"[ReconstructionAgent] Extrusion fehlgeschlagen: {e}")
            import traceback
            traceback.print_exc()
            return None

    def _add_fillet(self, params: dict) -> Any:
        """
        Fügt Fillets zu Kanten hinzu.

        Benötigt:
        - solid: Der zu bearbeitende Solid
        - radius: Fillet-Radius
        - edges: Liste der Kanten (optional, bei None = alle Außenkanten)

        Args:
            params: Dict mit Solid und Fillet-Parametern
        """
        try:
            from build123d import fillet

            solid = params.get("solid")
            radius = params.get("radius", 2)
            edge_indices = params.get("edges", None)

            if solid is None:
                logger.warning("[ReconstructionAgent] Kein Solid für Fillet")
                return None

            # Finde Kanten
            if edge_indices is None:
                # Nimm alle Außenkanten
                edges = list(solid.edges())
            else:
                # Spezifische Kanten
                all_edges = list(solid.edges())
                edges = [all_edges[i] for i in edge_indices if i < len(all_edges)]

            if not edges:
                logger.warning("[ReconstructionAgent] Keine Kanten für Fillet gefunden")
                return None

            # Fillet anwenden
            result = fillet(edges, radius)

            logger.debug(f"[ReconstructionAgent] Fillet: r={radius}, {len(edges)} Kanten")
            return result

        except ImportError:
            logger.error("[ReconstructionAgent] build123d nicht verfügbar")
            return None
        except Exception as e:
            logger.error(f"[ReconstructionAgent] Fillet fehlgeschlagen: {e}")
            return None

    def _notify(self, message: str):
        """Sendet Benachrichtigung (z.B. an UI)."""
        logger.info(f"[ReconstructionAgent] {message}")

        # Wenn Viewport verfügbar, zeige Nachricht
        if self.viewport and hasattr(self.viewport, 'show_notification'):
            self.viewport.show_notification(message)

    def _convert_stl_analysis_to_steps(self, analysis: Any) -> List[Any]:
        """
        Konvertiert STLFeatureAnalysis in ReconstructionSteps.
        """
        steps = []
        step_id = 0
        
        # 1. Base Plane
        if analysis.base_plane:
            # Check enabled status
            if hasattr(analysis.base_plane, 'enabled') and not analysis.base_plane.enabled:
                logger.info("Base Plane disabled by user - skipping")
            else:
                steps.append({
                    "step_id": step_id,
                    "operation": "create_plane",
                    "description": f"Base-Plane erkannt: {analysis.base_plane.area:.0f}mm²",
                    "params": {"plane": analysis.base_plane}
                })
                step_id += 1
                
                # Base Sketch (Profil)
                if analysis.base_plane.boundary_points:
                    # Use extracted boundary
                    steps.append({
                        "step_id": step_id,
                        "operation": "create_profile",
                        "description": "Erstelle Base-Profil (Polygonal)",
                        "params": {
                            "type": "polygon",
                            "points": analysis.base_plane.boundary_points,
                            "plane_origin": analysis.base_plane.origin,
                            "plane_normal": analysis.base_plane.normal
                        }
                    })
                else:
                    # Approximiere Rechteck aus Fläche
                    size = (analysis.base_plane.area ** 0.5)
                    steps.append({
                        "step_id": step_id,
                        "operation": "create_profile",
                        "description": "Erstelle Base-Profil (Rechteck)",
                        "params": {
                            "type": "rectangle",
                            "width": size,
                            "height": size,
                            "center": (0, 0), # Local center on plane
                            "plane_origin": analysis.base_plane.origin,
                            "plane_normal": analysis.base_plane.normal
                        }
                    })
                step_id += 1
                
                # Extrude Base
                # Höhe schätzen oder Default
                # Verwende max Tiefe von Löchern/Pockets als Hinweis oder Default 10
                depth = 10.0
                if analysis.holes:
                    max_hole_depth = max(h.depth for h in analysis.holes)
                    if max_hole_depth > depth:
                        depth = max_hole_depth
                
                steps.append({
                    "step_id": step_id,
                    "operation": "extrude",
                    "description": f"Extrudiere Base: {depth:.1f}mm",
                    "params": {
                        "distance": depth,
                        "operation": "New Body"
                    }
                })
                step_id += 1
            
        # 2. Holes (als Cuts)
        for i, hole in enumerate(analysis.holes):
            if hasattr(hole, 'enabled') and not hole.enabled:
                continue

            # Sketch für Loch
            steps.append({
                "step_id": step_id,
                "operation": "create_profile",
                "description": f"Hole #{i+1} Profil (r={hole.radius:.1f}mm)",
                "params": {
                    "type": "circle",
                    "radius": hole.radius,
                    "center": (0, 0), # Local center
                    "plane_origin": hole.center,
                    "plane_normal": hole.axis
                }
            })
            step_id += 1
            
            # Cut
            steps.append({
                "step_id": step_id,
                "operation": "extrude",
                "description": f"Hole #{i+1} Cut (d={hole.depth:.1f}mm)",
                "params": {
                    "distance": hole.depth,
                    "operation": "Cut"
                }
            })
            step_id += 1
            
        return steps

    def get_stats(self) -> dict:
        """Statistiken des ReconstructionAgent."""
        return {
            "slow_mode": self.slow_mode,
            "step_delay": self.step_delay
        }
