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
        Rundet Kanten ab via OCPFilletHelper.

        Args:
            solid: Eingabe-Solid (build123d Solid)
            radius: Fillet-Radius
            edge_indices: Indizes der Kanten (None = alle Kanten)

        Returns:
            Neuer Solid mit Fillets oder None

        Note:
            Verwendet OCPFilletHelper mit minimalem TNP-Support.
            Für volle TNP-Integration FilletFeature über Body verwenden.
        """
        if solid is None:
            return None

        start_time = time.time()

        try:
            from modeling.ocp_helpers import OCPFilletHelper
            from build123d import Edge
            from OCP.BRepFilletAPI import BRepFilletAPI_MakeFillet

            logger.debug(f"[OperationAgent] Fillet: radius={radius}, edges={edge_indices}")

            # Edges aus Solid extrahieren
            edges = list(solid.edges())
            if not edges:
                logger.warning("[OperationAgent] Fillet: Keine Edges im Solid gefunden")
                return None

            # Edge-Selektion anwenden
            if edge_indices is not None:
                selected_edges = [edges[i] for i in edge_indices if i < len(edges)]
            else:
                selected_edges = edges[:4]  # Default: erste 4 Edges

            if not selected_edges:
                logger.warning("[OperationAgent] Fillet: Keine gültigen Edges ausgewählt")
                return None

            # Direkter OCP-Aufruf (ohne TNP für OperationAgent)
            shape = solid.wrapped if hasattr(solid, 'wrapped') else solid
            fillet_op = BRepFilletAPI_MakeFillet(shape)

            for edge in selected_edges:
                edge_ocp = edge.wrapped if hasattr(edge, 'wrapped') else edge
                fillet_op.Add(radius, edge_ocp)

            fillet_op.Build()

            if not fillet_op.IsDone():
                logger.error("[OperationAgent] Fillet OCP-Operation fehlgeschlagen")
                return None

            from build123d import Solid
            result = Solid(fillet_op.Shape())

            duration_ms = (time.time() - start_time) * 1000
            self._operations_performed += 1
            self._operations_successful += 1
            logger.debug(f"[OperationAgent] Fillet Success: {duration_ms:.2f}ms")

            return result

        except ImportError as e:
            logger.error(f"[OperationAgent] Fillet Import Error: {e}")
            return None
        except Exception as e:
            duration_ms = (time.time() - start_time) * 1000
            logger.error(f"[OperationAgent] Fillet Error: {e}")
            return None

    def chamfer(
        self,
        solid: Any,
        distance: float,
        edge_indices: Optional[List[int]] = None
    ) -> Optional[Any]:
        """
        Fasst Kanten ab via OCPChamferHelper.

        Args:
            solid: Eingabe-Solid (build123d Solid)
            distance: Chamfer-Abstand
            edge_indices: Indizes der Kanten (None = alle Kanten)

        Returns:
            Neuer Solid mit Chamfers oder None

        Note:
            Verwendet direkten OCP-Aufruf ohne TNP.
            Für volle TNP-Integration ChamferFeature über Body verwenden.
        """
        if solid is None:
            return None

        start_time = time.time()

        try:
            from OCP.BRepFilletAPI import BRepFilletAPI_MakeChamfer
            from build123d import Solid

            logger.debug(f"[OperationAgent] Chamfer: distance={distance}, edges={edge_indices}")

            # Edges aus Solid extrahieren
            edges = list(solid.edges())
            if not edges:
                logger.warning("[OperationAgent] Chamfer: Keine Edges im Solid gefunden")
                return None

            # Edge-Selektion anwenden
            if edge_indices is not None:
                selected_edges = [edges[i] for i in edge_indices if i < len(edges)]
            else:
                selected_edges = edges[:4]  # Default: erste 4 Edges

            if not selected_edges:
                logger.warning("[OperationAgent] Chamfer: Keine gültigen Edges ausgewählt")
                return None

            # Direkter OCP-Aufruf
            shape = solid.wrapped if hasattr(solid, 'wrapped') else solid
            chamfer_op = BRepFilletAPI_MakeChamfer(shape)

            for edge in selected_edges:
                edge_ocp = edge.wrapped if hasattr(edge, 'wrapped') else edge
                chamfer_op.Add(distance, edge_ocp)

            chamfer_op.Build()

            if not chamfer_op.IsDone():
                logger.error("[OperationAgent] Chamfer OCP-Operation fehlgeschlagen")
                return None

            result = Solid(chamfer_op.Shape())

            duration_ms = (time.time() - start_time) * 1000
            self._operations_performed += 1
            self._operations_successful += 1
            logger.debug(f"[OperationAgent] Chamfer Success: {duration_ms:.2f}ms")

            return result

        except ImportError as e:
            logger.error(f"[OperationAgent] Chamfer Import Error: {e}")
            return None
        except Exception as e:
            duration_ms = (time.time() - start_time) * 1000
            logger.error(f"[OperationAgent] Chamfer Error: {e}")
            return None

    def boolean_cut(
        self,
        base_solid: Any,
        tool_solid: Any
    ) -> Optional[Any]:
        """
        Subtrahiert Tool von Base via BooleanEngineV4.

        Args:
            base_solid: Basis-Solid (build123d Solid)
            tool_solid: Werkzeug-Solid (wird subtrahiert)

        Returns:
            Resultat-Solid oder None
        """
        return self._execute_boolean(base_solid, tool_solid, "Cut")

    def boolean_union(
        self,
        solid1: Any,
        solid2: Any
    ) -> Optional[Any]:
        """
        Vereint zwei Solids via BooleanEngineV4.

        Args:
            solid1: Erstes Solid (build123d Solid)
            solid2: Zweites Solid (build123d Solid)

        Returns:
            Resultat-Solid oder None
        """
        return self._execute_boolean(solid1, solid2, "Join")

    def _execute_boolean(
        self,
        solid1: Any,
        solid2: Any,
        operation: str
    ) -> Optional[Any]:
        """
        Führt Boolean-Operation via BooleanEngineV4 aus.

        Args:
            solid1: Erstes Solid
            solid2: Zweites Solid
            operation: "Join", "Cut", oder "Intersect"

        Returns:
            Resultat-Solid oder None
        """
        if solid1 is None or solid2 is None:
            return None

        start_time = time.time()

        try:
            from modeling.boolean_engine_v4 import BooleanEngineV4

            logger.debug(f"[OperationAgent] Boolean {operation}")

            result = BooleanEngineV4.execute_boolean_on_shapes(
                solid1=solid1,
                solid2=solid2,
                operation=operation
            )

            if result is None or not hasattr(result, 'status'):
                logger.error("[OperationAgent] Boolean: Ungültiges Resultat")
                return None

            if result.status.value != "success":
                logger.error(f"[OperationAgent] Boolean Error: {result.message}")
                return None

            duration_ms = (time.time() - start_time) * 1000
            self._operations_performed += 1
            self._operations_successful += 1
            logger.debug(f"[OperationAgent] Boolean {operation} Success: {duration_ms:.2f}ms")

            return result.value

        except ImportError as e:
            logger.error(f"[OperationAgent] Boolean Import Error: {e}")
            return None
        except Exception as e:
            duration_ms = (time.time() - start_time) * 1000
            logger.error(f"[OperationAgent] Boolean Error: {e}")
            return None

    def shell(
        self,
        solid: Any,
        thickness: float,
        face_indices: Optional[List[int]] = None
    ) -> Optional[Any]:
        """
        Erstellt Hohlkörper via OCP BRepOffsetAPI_MakeThickSolid.

        Args:
            solid: Eingabe-Solid (build123d Solid)
            thickness: Wandstärke (positiv = nach aussen, negativ = nach innen)
            face_indices: Indizes der zu öffnenden Faces (None = geschlossener Hohlkörper)

        Returns:
            Gehäuse-Solid oder None

        Note:
            Für volle TNP-Integration ShellFeature über Body verwenden.
        """
        if solid is None:
            return None

        start_time = time.time()

        try:
            from OCP.BRepOffsetAPI import BRepOffsetAPI_MakeThickSolid
            from OCP.TopTools import TopTools_ListOfShape
            from build123d import Solid
            from config.tolerances import Tolerances

            logger.debug(f"[OperationAgent] Shell: thickness={thickness}, faces={face_indices}")

            shape = solid.wrapped if hasattr(solid, 'wrapped') else solid

            # Faces zum Öffnen sammeln
            faces_to_remove = TopTools_ListOfShape()
            if face_indices is not None:
                all_faces = list(solid.faces())
                for idx in face_indices:
                    if idx < len(all_faces):
                        face = all_faces[idx]
                        face_shape = face.wrapped if hasattr(face, 'wrapped') else face
                        faces_to_remove.Append(face_shape)

            # Shell erstellen
            shell_op = BRepOffsetAPI_MakeThickSolid()
            shell_op.MakeThickSolidByJoin(
                shape,
                faces_to_remove,
                -abs(thickness),  # Negativ für nach innen
                Tolerances.SHELL_TOLERANCE
            )
            shell_op.Build()

            if not shell_op.IsDone():
                logger.error("[OperationAgent] Shell OCP-Operation fehlgeschlagen")
                return None

            result = Solid(shell_op.Shape())

            if not result.is_valid():
                logger.error("[OperationAgent] Shell erzeugte keinen gültigen Solid")
                return None

            duration_ms = (time.time() - start_time) * 1000
            self._operations_performed += 1
            self._operations_successful += 1
            logger.debug(f"[OperationAgent] Shell Success: {duration_ms:.2f}ms")

            return result

        except ImportError as e:
            logger.error(f"[OperationAgent] Shell Import Error: {e}")
            return None
        except Exception as e:
            duration_ms = (time.time() - start_time) * 1000
            logger.error(f"[OperationAgent] Shell Error: {e}")
            return None

    def revolve(
        self,
        sketch: 'Sketch',
        angle: float = 360.0,
        axis: Optional[Tuple[Tuple[float, float, float], Tuple[float, float, float]]] = None
    ) -> Optional[Any]:
        """
        Rotiert Sketch um Achse via OCP BRepPrimAPI_MakeRevol.

        Args:
            sketch: Zu rotierender Sketch (mit closed_profiles)
            angle: Rotationswinkel in Grad (default: 360 = voller Kreis)
            axis: Optional ((origin_x, origin_y, origin_z), (dir_x, dir_y, dir_z))
                  Default: Y-Achse durch Sketch-Origin

        Returns:
            Rotations-Solid oder None

        Note:
            Für volle TNP-Integration RevolveFeature über Body verwenden.
        """
        if sketch is None:
            return None

        start_time = time.time()

        try:
            from OCP.BRepPrimAPI import BRepPrimAPI_MakeRevol
            from OCP.gp import gp_Ax1, gp_Dir, gp_Pnt
            from OCP.TopAbs import TopAbs_FACE
            from OCP.TopExp import TopExp_Explorer
            from build123d import Solid, Plane, Vector, Wire, make_face
            import math

            logger.debug(f"[OperationAgent] Revolve: angle={angle}")

            # Sketch-Plane bestimmen
            plane_origin = getattr(sketch, 'plane_origin', (0, 0, 0))
            plane_normal = getattr(sketch, 'plane_normal', (0, 0, 1))
            x_dir = getattr(sketch, 'plane_x_dir', None)

            # Validate plane_normal
            norm_len = math.sqrt(sum(c*c for c in plane_normal))
            if norm_len < 1e-9:
                logger.warning("[OperationAgent] Revolve: plane_normal ist Null-Vektor, Fallback auf (0,0,1)")
                plane_normal = (0, 0, 1)

            plane = Plane(
                origin=Vector(*plane_origin),
                z_dir=Vector(*plane_normal),
                x_dir=Vector(*x_dir) if x_dir else None
            )

            # Profile aus Sketch holen
            sketch_profiles = getattr(sketch, 'closed_profiles', [])
            if not sketch_profiles:
                logger.warning("[OperationAgent] Revolve: Sketch hat keine closed_profiles")
                return None

            # Achse bestimmen
            if axis is None:
                # Default: Y-Achse durch Sketch-Origin
                axis_origin = gp_Pnt(plane_origin[0], plane_origin[1], plane_origin[2])
                axis_dir = gp_Dir(0, 1, 0)  # Y-Achse
            else:
                origin, direction = axis
                axis_origin = gp_Pnt(origin[0], origin[1], origin[2])
                axis_dir = gp_Dir(direction[0], direction[1], direction[2])

            revol_axis = gp_Ax1(axis_origin, axis_dir)
            angle_rad = math.radians(angle)

            # Alle Profile zu Faces konvertieren und revolven
            result_solids = []
            for poly in sketch_profiles:
                try:
                    coords = list(poly.exterior.coords)[:-1]  # Shapely schliesst Polygon
                    if len(coords) < 3:
                        continue

                    pts_3d = [plane.from_local_coords((p[0], p[1])) for p in coords]
                    wire = Wire.make_polygon([Vector(*p) for p in pts_3d])
                    face = make_face(wire)

                    # OCP Revolve
                    face_ocp = face.wrapped
                    revol_op = BRepPrimAPI_MakeRevol(face_ocp, revol_axis, angle_rad)
                    revol_op.Build()

                    if revol_op.IsDone():
                        result_shape = revol_op.Shape()
                        result_solids.append(Solid(result_shape))

                except Exception as e:
                    logger.debug(f"[OperationAgent] Revolve: Polygon-Konvertierung fehlgeschlagen: {e}")
                    continue

            if not result_solids:
                logger.warning("[OperationAgent] Revolve: Keine gültigen Solids erzeugt")
                return None

            # Bei mehreren Solids: union
            if len(result_solids) == 1:
                result = result_solids[0]
            else:
                result = result_solids[0]
                for s in result_solids[1:]:
                    union_result = self._execute_boolean(result, s, "Join")
                    if union_result:
                        result = union_result

            duration_ms = (time.time() - start_time) * 1000
            self._operations_performed += 1
            self._operations_successful += 1
            logger.debug(f"[OperationAgent] Revolve Success: {duration_ms:.2f}ms")

            return result

        except ImportError as e:
            logger.error(f"[OperationAgent] Revolve Import Error: {e}")
            return None
        except Exception as e:
            duration_ms = (time.time() - start_time) * 1000
            logger.error(f"[OperationAgent] Revolve Error: {e}")
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
