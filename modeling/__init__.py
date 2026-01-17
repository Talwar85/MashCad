
"""
MashCad - 3D Modeling
Robust B-Rep Implementation with Build123d & Smart Failure Recovery
"""

from dataclasses import dataclass, field
import tempfile
from typing import List, Optional, Tuple, Union
from enum import Enum, auto
import math
import uuid
import sys
import os
import traceback
from loguru import logger 
try:
    from shapely.geometry import LineString, Polygon as ShapelyPoly, Point
    from shapely.ops import polygonize, unary_union
except ImportError:
    logger.warning("Shapely nicht gefunden. Komplexe Skizzen könnten fehlschlagen.")
    
    
# WICHTIG: Unser neuer Helper
from modeling.cad_tessellator import CADTessellator
from modeling.mesh_converter import MeshToBREPConverter # NEU
from modeling.mesh_converter_functional_parts import MeshToBREPV5 # NEU
from modeling.mesh_converter_v6 import SmartMeshConverter # V6 - Feature Detection


# ==================== IMPORTS ====================
HAS_BUILD123D = False
HAS_OCP = False

# OCP wird IMMER geladen (für robuste Boolean Operations)
try:
    from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox, BRepPrimAPI_MakeCylinder, BRepPrimAPI_MakePrism
    from OCP.BRepBuilderAPI import (
        BRepBuilderAPI_MakeEdge, BRepBuilderAPI_MakeWire, BRepBuilderAPI_MakeFace,
        BRepBuilderAPI_MakeSolid, BRepBuilderAPI_Sewing
    )
    from OCP.BRepAlgoAPI import BRepAlgoAPI_Fuse, BRepAlgoAPI_Cut, BRepAlgoAPI_Common
    from OCP.BOPAlgo import BOPAlgo_GlueEnum
    from OCP.BRepOffsetAPI import BRepOffsetAPI_MakePipe
    from OCP.BRepFilletAPI import BRepFilletAPI_MakeFillet, BRepFilletAPI_MakeChamfer
    from OCP.StlAPI import StlAPI_Writer
    from OCP.BRepMesh import BRepMesh_IncrementalMesh
    from OCP.TopoDS import TopoDS_Shape, TopoDS_Solid, TopoDS_Face, TopoDS_Edge, TopoDS_Wire
    from OCP.TopExp import TopExp_Explorer
    from OCP.TopAbs import TopAbs_FACE, TopAbs_EDGE, TopAbs_SOLID
    from OCP.gp import gp_Pnt, gp_Vec, gp_Dir, gp_Ax1, gp_Ax2, gp_Pln, gp_Trsf
    from OCP.BRepBuilderAPI import BRepBuilderAPI_Transform
    from OCP.ShapeFix import ShapeFix_Shape, ShapeFix_Solid
    from OCP.BRepCheck import BRepCheck_Analyzer
    HAS_OCP = True
    logger.success("✓ OCP (OpenCASCADE) geladen.")
except ImportError as e:
    logger.warning(f"! OCP nicht gefunden: {e}")

# Build123d als High-Level API (optional, aber empfohlen)
try:
    from build123d import (
        Box, Cylinder, Sphere, Solid, Shape,
        extrude, revolve, fillet, chamfer,
        Axis, Plane, Locations, Vector,
        BuildPart, BuildSketch, BuildLine,
        Part, Sketch as B123Sketch,
        Rectangle as B123Rect, Circle as B123Circle,
        Polyline, Polygon, make_face, Mode,
        export_stl, export_step,
        GeomType
    )
    HAS_BUILD123D = True
    logger.success("✓ build123d geladen (High-Level API).")
except ImportError as e:
    logger.warning(f"! build123d nicht gefunden: {e}")

# Projektpfad
_project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from sketcher import Sketch

# ==================== DATENSTRUKTUREN ====================

class FeatureType(Enum):
    SKETCH = auto()
    EXTRUDE = auto()
    REVOLVE = auto()
    FILLET = auto()
    CHAMFER = auto()
    TRANSFORM = auto()  # NEU: Für Move/Rotate/Scale/Mirror

@dataclass
class Feature:
    type: FeatureType = None
    name: str = "Feature"
    id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    visible: bool = True
    suppressed: bool = False
    status: str = "OK" # OK, ERROR, WARNING

@dataclass
class ExtrudeFeature(Feature):
    sketch: Sketch = None
    distance: float = 10.0
    direction: int = 1 
    operation: str = "New Body"
    selector: list = None 
    precalculated_polys: list = field(default_factory=list) # NEU: Für Detector-Sync
    
    def __post_init__(self):
        self.type = FeatureType.EXTRUDE
        if not self.name or self.name == "Feature": self.name = "Extrude"

@dataclass
class RevolveFeature(Feature):
    sketch: Sketch = None
    angle: float = 360.0
    axis: Tuple[float, float, float] = (0, 1, 0)
    operation: str = "New Body"
    
    def __post_init__(self):
        self.type = FeatureType.REVOLVE
        if not self.name or self.name == "Feature": self.name = "Revolve"

@dataclass 
class FilletFeature(Feature):
    radius: float = 2.0
    edge_selectors: List = None 
    
    def __post_init__(self):
        self.type = FeatureType.FILLET
        if not self.name or self.name == "Feature": self.name = "Fillet"

@dataclass
class ChamferFeature(Feature):
    distance: float = 2.0
    edge_selectors: List = None

    def __post_init__(self):
        self.type = FeatureType.CHAMFER
        if not self.name or self.name == "Feature": self.name = "Chamfer"

@dataclass
class TransformFeature(Feature):
    """
    Parametric transform stored in feature history.

    Enables:
    - Undo/Redo support
    - Parametric editing
    - Feature tree visibility
    - Body rebuild consistency
    """
    mode: str = "move"  # "move", "rotate", "scale", "mirror"
    data: dict = field(default_factory=dict)
    # data examples:
    # Move: {"translation": [10.0, 0.0, 5.0]}
    # Rotate: {"axis": "Z", "angle": 45.0, "center": [0.0, 0.0, 0.0]}
    # Scale: {"factor": 1.5, "center": [0.0, 0.0, 0.0]}
    # Mirror: {"plane": "XY"}

    def __post_init__(self):
        self.type = FeatureType.TRANSFORM
        if not self.name or self.name == "Feature":
            self.name = f"Transform: {self.mode.capitalize()}"


# ==================== CORE LOGIC ====================

class Body:
    """
    3D-Körper (Body) mit RobustPartBuilder Logik.
    """
    
    def __init__(self, name: str = "Body"):
        self.name = name
        self.id = str(uuid.uuid4())[:8]
        self.features: List[Feature] = []
        
        # CAD Kernel Objekte
        self._build123d_solid = None  
        self.shape = None             
        
        # PyVista/VTK Objekte (Cache)
        self.vtk_mesh = None       # pv.PolyData (Faces)
        self.vtk_edges = None      # pv.PolyData (Edges)
        
        # Legacy Visualisierungs-Daten (Nur als Fallback)
        self._mesh_vertices: List[Tuple[float, float, float]] = []
        self._mesh_triangles: List[Tuple[int, int, int]] = []
        self._mesh_normals = [] 
        self._mesh_edges = []
        
    def add_feature(self, feature: Feature):
        """Feature hinzufügen und Geometrie neu berechnen"""
        self.features.append(feature)
        self._rebuild()
    
    def remove_feature(self, feature: Feature):
        if feature in self.features:
            self.features.remove(feature)
            self._rebuild()
            
    def convert_to_brep(self, mode: str = "hybrid"):
        """
        Wandelt Mesh in CAD-Solid um.
        :param mode: 'hybrid' (Auto - EMPFOHLEN), 'v7' (RANSAC Primitives), 'v6' (Smart/Planar)
        """
        if self._build123d_solid is not None:
            logger.info(f"Body '{self.name}' ist bereits BREP.")
            return True

        if self.vtk_mesh is None:
            logger.warning("Keine Mesh-Daten vorhanden.")
            return False

        solid = None

        # --- MODUS HYBRID: AUTOMATISCHE WAHL (EMPFOHLEN) ---
        if mode == "hybrid":
            logger.info("Starte Konvertierung mit Hybrid (Automatische Wahl)...")
            try:
                from modeling.mesh_converter_hybrid import HybridMeshConverter
                converter = HybridMeshConverter(
                    ransac_min_coverage=0.80,   # 80% Coverage für RANSAC-Erfolg
                    use_v7=True,                # V7 (RANSAC) aktiviert
                    use_v6_fallback=True,       # V6 als Fallback
                    use_v1_fallback=True        # V1 als letzter Fallback
                )
                solid = converter.convert(self.vtk_mesh)

            except Exception as e:
                logger.error(f"Hybrid Konvertierung fehlgeschlagen: {e}")
                traceback.print_exc()
                return False

        # --- MODUS V7: RANSAC PRIMITIVES ---
        elif mode == "v7":
            logger.info("Starte Konvertierung mit V7 (RANSAC Primitives)...")
            try:
                from modeling.mesh_converter_primitives import RANSACPrimitiveConverter
                converter = RANSACPrimitiveConverter(
                    angle_tolerance=5.0,        # 5° für Region-Clustering
                    ransac_threshold=0.5,       # 0.5mm Inlier-Toleranz
                    min_inlier_ratio=0.70,      # 70% Inliers minimum
                    min_region_faces=10,
                    sewing_tolerance=0.1
                )
                solid = converter.convert(self.vtk_mesh)

            except Exception as e:
                logger.error(f"V7 Konvertierung fehlgeschlagen: {e}")
                traceback.print_exc()
                return False

        # --- MODUS V6: SMART / FEATURE DETECTION ---
        elif mode == "v6":
            logger.info("Starte Konvertierung mit V6 (Smart Feature Detection)...")
            try:
                converter = SmartMeshConverter(
                    angle_tolerance=5.0,      # 5° für planare Erkennung
                    min_region_faces=3,
                    decimate_target=5000,
                    sewing_tolerance=0.1
                )
                solid = converter.convert(self.vtk_mesh, method="smart")

            except Exception as e:
                logger.error(f"V6 Konvertierung fehlgeschlagen: {e}")
                traceback.print_exc()
                return False

        # --- UNGÜLTIGER MODUS ---
        else:
            logger.error(f"Ungültiger Modus: {mode}")
            logger.info("Verfügbare Modi: 'hybrid', 'v7', 'v6'")
            return False

        # --- ERGEBNIS VERARBEITEN ---
        if solid and hasattr(solid, 'wrapped') and not solid.wrapped.IsNull():
            self._build123d_solid = solid
            self.shape = solid.wrapped
            
            logger.success(f"Body '{self.name}' erfolgreich mit [{mode.upper()}] konvertiert.")
            
            # Mesh neu berechnen (diesmal vom BREP abgeleitet für Konsistenz)
            self._update_mesh_from_solid(solid)
            return True
        else:
            logger.warning(f"Konvertierung mit [{mode.upper()}] lieferte kein gültiges Solid.")
            return False
            
    def _safe_operation(self, op_name, op_func, fallback_func=None):
        """
        Wrapper für kritische CAD-Operationen.
        Fängt Crashes ab und erlaubt Fallbacks.
        """
        try:
            result = op_func()
            
            if result is None:
                raise ValueError("Operation returned None")
            
            if hasattr(result, 'is_valid') and not result.is_valid():
                raise ValueError("Result geometry is invalid")
                
            return result, "OK"
            
        except Exception as e:
            logger.warning(f"Feature '{op_name}' fehlgeschlagen: {e}")
            
            if fallback_func:
                logger.info(f"→ Versuche Fallback für '{op_name}'...")
                try:
                    res_fallback = fallback_func()
                    if res_fallback:
                        logger.success(f"✓ Fallback für '{op_name}' erfolgreich.")
                        return res_fallback, "WARNING"
                except Exception as e2:
                    logger.error(f"✗ Auch Fallback fehlgeschlagen: {e2}")
            
            return None, "ERROR"

    def _safe_boolean_operation(self, solid1, solid2, operation: str):
        """
        Robuste Boolean Operation mit direkter OCP-API (wie Fusion360/OnShape).

        Args:
            solid1: Erstes Solid (aktueller Body)
            solid2: Zweites Solid (neues Teil)
            operation: "Join", "Cut", oder "Intersect"

        Returns:
            (result_solid, success: bool)
        """
        if not HAS_OCP:
            logger.error("OCP nicht verfügbar - Boolean Operations nicht möglich")
            return solid1, False

        try:
            # 1. Validiere Eingaben
            if solid1 is None or solid2 is None:
                logger.error(f"Boolean {operation}: Eines der Solids ist None")
                return solid1, False

            # 2. Extrahiere TopoDS_Shape (OCP-Kern)
            shape1 = solid1.wrapped if hasattr(solid1, 'wrapped') else solid1
            shape2 = solid2.wrapped if hasattr(solid2, 'wrapped') else solid2

            # 3. Repariere Shapes VOR Boolean (kritisch für Erfolg!)
            shape1 = self._fix_shape_ocp(shape1)
            shape2 = self._fix_shape_ocp(shape2)

            if shape1 is None or shape2 is None:
                logger.error("Shape-Reparatur fehlgeschlagen")
                return solid1, False

            # 4. Führe Boolean Operation aus (OCP-API)
            logger.info(f"OCP Boolean: {operation}...")
            result_shape = None

            # Toleranzen für robuste Operationen
            FUZZY_VALUE = 1e-5  # 0.01mm - größer = toleranter

            if operation == "Join":
                result_shape = self._ocp_fuse(shape1, shape2, FUZZY_VALUE)
            elif operation == "Cut":
                result_shape = self._ocp_cut(shape1, shape2, FUZZY_VALUE)
            elif operation == "Intersect":
                result_shape = self._ocp_common(shape1, shape2, FUZZY_VALUE)
            else:
                logger.error(f"Unbekannte Operation: {operation}")
                return solid1, False

            # 5. Validiere und repariere Resultat
            if result_shape is None:
                logger.error(f"{operation} produzierte None")
                return solid1, False

            # Repariere Resultat
            result_shape = self._fix_shape_ocp(result_shape)

            if result_shape is None:
                logger.error(f"{operation} Resultat-Reparatur fehlgeschlagen")
                return solid1, False

            # 6. Wrap zurück zu Build123d Solid
            try:
                from build123d import Solid, Shape
                try:
                    result = Solid(result_shape)
                except:
                    result = Shape(result_shape)

                if hasattr(result, 'is_valid') and result.is_valid():
                    logger.success(f"✅ {operation} erfolgreich")
                    return result, True
                else:
                    logger.warning(f"{operation} Resultat invalid nach Wrap")
                    # Versuche Build123d fix()
                    try:
                        result = result.fix()
                        if result.is_valid():
                            logger.success(f"✅ {operation} erfolgreich (nach fix)")
                            return result, True
                    except:
                        pass
                    return solid1, False
            except Exception as e:
                logger.error(f"Wrap zu Build123d fehlgeschlagen: {e}")
                return solid1, False

        except Exception as e:
            logger.error(f"Boolean {operation} Fehler: {e}")
            import traceback
            traceback.print_exc()
            return solid1, False

    def _fix_shape_ocp(self, shape):
        """Repariert einen TopoDS_Shape mit OCP ShapeFix."""
        try:
            from OCP.ShapeFix import ShapeFix_Shape, ShapeFix_Solid
            from OCP.BRepCheck import BRepCheck_Analyzer

            # Prüfe ob Shape valide ist
            analyzer = BRepCheck_Analyzer(shape)
            if analyzer.IsValid():
                return shape

            logger.debug("Shape invalid, starte Reparatur...")

            # ShapeFix_Shape für allgemeine Reparaturen
            fixer = ShapeFix_Shape(shape)
            fixer.SetPrecision(1e-6)
            fixer.SetMaxTolerance(1e-3)
            fixer.SetMinTolerance(1e-7)

            # Aktiviere alle Reparaturen
            fixer.FixSolidMode()
            fixer.FixShellMode()
            fixer.FixFaceMode()
            fixer.FixWireMode()
            fixer.FixEdgeMode()

            if fixer.Perform():
                fixed_shape = fixer.Shape()

                # Validiere repariertes Shape
                analyzer2 = BRepCheck_Analyzer(fixed_shape)
                if analyzer2.IsValid():
                    logger.debug("✓ Shape repariert")
                    return fixed_shape
                else:
                    logger.warning("Shape nach Reparatur immer noch invalid")
                    # Gib es trotzdem zurück - manchmal funktioniert es dennoch
                    return fixed_shape
            else:
                logger.warning("ShapeFix Perform() fehlgeschlagen")
                return shape  # Gib Original zurück

        except Exception as e:
            logger.warning(f"Shape-Reparatur Fehler: {e}")
            return shape  # Gib Original zurück

    def _ocp_fuse(self, shape1, shape2, fuzzy_value):
        """OCP Fuse (Join) mit optimalen Parametern."""
        try:
            from OCP.BRepAlgoAPI import BRepAlgoAPI_Fuse
            from OCP.BOPAlgo import BOPAlgo_GlueEnum
            from OCP.TopTools import TopTools_ListOfShape

            # Methode 1: Standard Fuse mit Fuzzy
            fuse_op = BRepAlgoAPI_Fuse()

            # Setze Argumente (WICHTIG: VOR Build!)
            args = TopTools_ListOfShape()
            args.Append(shape1)
            fuse_op.SetArguments(args)

            tools = TopTools_ListOfShape()
            tools.Append(shape2)
            fuse_op.SetTools(tools)

            # Setze Parameter für robustes Fuse
            fuse_op.SetFuzzyValue(fuzzy_value)
            fuse_op.SetRunParallel(True)
            fuse_op.SetNonDestructive(True)  # Behält Original-Shapes
            fuse_op.SetGlue(BOPAlgo_GlueEnum.BOPAlgo_GlueFull)  # Besseres Gluing

            # Build
            fuse_op.Build()

            if fuse_op.IsDone():
                return fuse_op.Shape()
            else:
                # Fallback: Einfacher Konstruktor
                logger.info("Versuche Fuse Fallback...")
                fuse_simple = BRepAlgoAPI_Fuse(shape1, shape2)
                fuse_simple.Build()
                if fuse_simple.IsDone():
                    return fuse_simple.Shape()

                return None
        except Exception as e:
            logger.error(f"OCP Fuse Fehler: {e}")
            return None

    def _ocp_cut(self, shape1, shape2, fuzzy_value):
        """OCP Cut mit optimalen Parametern (wie Fusion360)."""
        try:
            from OCP.BRepAlgoAPI import BRepAlgoAPI_Cut
            from OCP.BOPAlgo import BOPAlgo_GlueEnum
            from OCP.TopTools import TopTools_ListOfShape

            # Methode 1: Erweiterte Cut-API
            cut_op = BRepAlgoAPI_Cut()

            # Setze Argumente (shape1 = Basis, shape2 = Tool zum Schneiden)
            args = TopTools_ListOfShape()
            args.Append(shape1)
            cut_op.SetArguments(args)

            tools = TopTools_ListOfShape()
            tools.Append(shape2)
            cut_op.SetTools(tools)

            # Parameter für robustes Cut
            cut_op.SetFuzzyValue(fuzzy_value)
            cut_op.SetRunParallel(True)
            cut_op.SetNonDestructive(True)

            # GlueShift ist wichtig für koplanare Flächen!
            cut_op.SetGlue(BOPAlgo_GlueEnum.BOPAlgo_GlueShift)

            # Build
            cut_op.Build()

            if cut_op.IsDone():
                return cut_op.Shape()

            # Fallback 1: Ohne GlueShift
            logger.info("Versuche Cut Fallback 1 (ohne GlueShift)...")
            cut_op2 = BRepAlgoAPI_Cut()
            args2 = TopTools_ListOfShape()
            args2.Append(shape1)
            cut_op2.SetArguments(args2)
            tools2 = TopTools_ListOfShape()
            tools2.Append(shape2)
            cut_op2.SetTools(tools2)
            cut_op2.SetFuzzyValue(fuzzy_value * 10)  # Größere Toleranz
            cut_op2.Build()

            if cut_op2.IsDone():
                return cut_op2.Shape()

            # Fallback 2: Einfacher Konstruktor
            logger.info("Versuche Cut Fallback 2 (simple)...")
            cut_simple = BRepAlgoAPI_Cut(shape1, shape2)
            cut_simple.Build()
            if cut_simple.IsDone():
                return cut_simple.Shape()

            return None
        except Exception as e:
            logger.error(f"OCP Cut Fehler: {e}")
            return None

    def _ocp_common(self, shape1, shape2, fuzzy_value):
        """OCP Common (Intersect) mit optimalen Parametern."""
        try:
            from OCP.BRepAlgoAPI import BRepAlgoAPI_Common
            from OCP.TopTools import TopTools_ListOfShape

            common_op = BRepAlgoAPI_Common()

            args = TopTools_ListOfShape()
            args.Append(shape1)
            common_op.SetArguments(args)

            tools = TopTools_ListOfShape()
            tools.Append(shape2)
            common_op.SetTools(tools)

            common_op.SetFuzzyValue(fuzzy_value)
            common_op.SetRunParallel(True)
            common_op.SetNonDestructive(True)

            common_op.Build()

            if common_op.IsDone():
                return common_op.Shape()

            # Fallback
            logger.info("Versuche Common Fallback...")
            common_simple = BRepAlgoAPI_Common(shape1, shape2)
            common_simple.Build()
            if common_simple.IsDone():
                return common_simple.Shape()

            return None
        except Exception as e:
            logger.error(f"OCP Common Fehler: {e}")
            return None

    def _ocp_fillet(self, solid, edges, radius):
        """
        OCP-basiertes Fillet (robuster als Build123d).

        Args:
            solid: Build123d Solid
            edges: Liste von Edges
            radius: Fillet-Radius

        Returns:
            Build123d Solid oder None
        """
        if not HAS_OCP:
            return None

        try:
            from OCP.BRepFilletAPI import BRepFilletAPI_MakeFillet
            from OCP.BRepCheck import BRepCheck_Analyzer

            # Extrahiere TopoDS_Shape
            shape = solid.wrapped if hasattr(solid, 'wrapped') else solid

            # Erstelle Fillet-Operator
            fillet_op = BRepFilletAPI_MakeFillet(shape)

            # Füge Edges hinzu
            for edge in edges:
                edge_shape = edge.wrapped if hasattr(edge, 'wrapped') else edge
                fillet_op.Add(radius, edge_shape)

            # Build
            fillet_op.Build()

            if not fillet_op.IsDone():
                logger.warning("OCP Fillet IsDone() = False")
                return None

            result_shape = fillet_op.Shape()

            # Validiere
            analyzer = BRepCheck_Analyzer(result_shape)
            if not analyzer.IsValid():
                logger.warning("OCP Fillet produzierte ungültiges Shape, versuche Reparatur...")
                result_shape = self._fix_shape_ocp(result_shape)

            # Wrap zu Build123d
            try:
                from build123d import Solid, Shape
                try:
                    result = Solid(result_shape)
                except:
                    result = Shape(result_shape)

                if hasattr(result, 'is_valid') and result.is_valid():
                    logger.debug("OCP Fillet erfolgreich")
                    return result
                else:
                    return None
            except:
                return None

        except Exception as e:
            logger.debug(f"OCP Fillet Fehler: {e}")
            return None

    def _ocp_chamfer(self, solid, edges, distance):
        """
        OCP-basiertes Chamfer (robuster als Build123d).

        Args:
            solid: Build123d Solid
            edges: Liste von Edges
            distance: Chamfer-Distanz

        Returns:
            Build123d Solid oder None
        """
        if not HAS_OCP:
            return None

        try:
            from OCP.BRepFilletAPI import BRepFilletAPI_MakeChamfer
            from OCP.BRepCheck import BRepCheck_Analyzer
            from OCP.TopExp import TopExp_Explorer
            from OCP.TopAbs import TopAbs_FACE

            # Extrahiere TopoDS_Shape
            shape = solid.wrapped if hasattr(solid, 'wrapped') else solid

            # Erstelle Chamfer-Operator
            chamfer_op = BRepFilletAPI_MakeChamfer(shape)

            # Für Chamfer brauchen wir auch angrenzende Faces
            for edge in edges:
                edge_shape = edge.wrapped if hasattr(edge, 'wrapped') else edge

                # Finde angrenzende Face
                explorer = TopExp_Explorer(shape, TopAbs_FACE)
                while explorer.More():
                    face = explorer.Current()
                    # Versuche Chamfer mit symmetrischer Distanz
                    try:
                        chamfer_op.Add(distance, edge_shape, face)
                        break
                    except:
                        pass
                    explorer.Next()

            # Build
            chamfer_op.Build()

            if not chamfer_op.IsDone():
                logger.warning("OCP Chamfer IsDone() = False")
                return None

            result_shape = chamfer_op.Shape()

            # Validiere
            analyzer = BRepCheck_Analyzer(result_shape)
            if not analyzer.IsValid():
                logger.warning("OCP Chamfer produzierte ungültiges Shape")
                result_shape = self._fix_shape_ocp(result_shape)

            # Wrap zu Build123d
            try:
                from build123d import Solid, Shape
                try:
                    result = Solid(result_shape)
                except:
                    result = Shape(result_shape)

                if hasattr(result, 'is_valid') and result.is_valid():
                    logger.debug("OCP Chamfer erfolgreich")
                    return result
                else:
                    return None
            except:
                return None

        except Exception as e:
            logger.debug(f"OCP Chamfer Fehler: {e}")
            return None

    def _ocp_extrude_face(self, face, amount, direction):
        """
        Extrusion eines Faces - nutzt Build123d primär, OCP als Fallback.

        Args:
            face: Build123d Face oder TopoDS_Face
            amount: Extrusions-Distanz (positiv oder negativ)
            direction: Richtungsvektor (Build123d Vector oder Tuple)

        Returns:
            Build123d Solid oder None
        """
        # PRIMÄR: Build123d extrude (bewährt und stabil)
        try:
            from build123d import extrude
            result = extrude(face, amount=amount, dir=direction)
            if result and hasattr(result, 'is_valid') and result.is_valid():
                return result
            elif result:
                # Versuche Reparatur
                try:
                    result = result.fix()
                    if result.is_valid():
                        return result
                except:
                    pass
        except Exception as e:
            logger.debug(f"Build123d extrude fehlgeschlagen: {e}")

        # FALLBACK: OCP MakePrism
        if not HAS_OCP:
            return None

        try:
            from OCP.BRepPrimAPI import BRepPrimAPI_MakePrism
            from OCP.gp import gp_Vec
            from OCP.BRepCheck import BRepCheck_Analyzer

            logger.debug("Versuche OCP Extrude Fallback...")

            # Extrahiere TopoDS_Face
            if hasattr(face, 'wrapped'):
                topo_face = face.wrapped
            else:
                topo_face = face

            # Erstelle Richtungsvektor
            try:
                if hasattr(direction, 'X'):
                    # Build123d Vector (property mit Großbuchstaben)
                    vec = gp_Vec(direction.X * amount, direction.Y * amount, direction.Z * amount)
                elif hasattr(direction, 'x'):
                    # Objekt mit x, y, z Attributen (Kleinbuchstaben)
                    vec = gp_Vec(direction.x * amount, direction.y * amount, direction.z * amount)
                elif isinstance(direction, (list, tuple)) and len(direction) == 3:
                    vec = gp_Vec(direction[0] * amount, direction[1] * amount, direction[2] * amount)
                else:
                    logger.error(f"Unbekannter direction-Typ: {type(direction)}")
                    return None
            except Exception as e:
                logger.error(f"Fehler bei Vektor-Konvertierung: {e}")
                return None

            # OCP Prism (Extrusion)
            prism = BRepPrimAPI_MakePrism(topo_face, vec)
            prism.Build()

            if not prism.IsDone():
                logger.warning("OCP MakePrism IsDone() = False")
                return None

            result_shape = prism.Shape()

            # Validiere
            analyzer = BRepCheck_Analyzer(result_shape)
            if not analyzer.IsValid():
                logger.warning("OCP Extrude produzierte ungültiges Shape, versuche Reparatur...")
                result_shape = self._fix_shape_ocp(result_shape)

            # Wrap zu Build123d Solid
            try:
                from build123d import Solid, Shape
                try:
                    result = Solid(result_shape)
                except:
                    result = Shape(result_shape)

                if hasattr(result, 'is_valid') and result.is_valid():
                    return result
                else:
                    # Versuche fix()
                    try:
                        result = result.fix()
                        if result.is_valid():
                            return result
                    except:
                        pass
                    logger.warning("OCP Extrude Resultat invalid")
                    return None
            except Exception as e:
                logger.error(f"Wrap zu Build123d fehlgeschlagen: {e}")
                return None

        except Exception as e:
            logger.error(f"OCP Extrude Fehler: {e}")
            import traceback
            traceback.print_exc()
            return None

    def _rebuild(self):
        """
        Robuster Rebuild-Prozess (History-basiert).
        """
        logger.info(f"Rebuilding Body '{self.name}' ({len(self.features)} Features)...")
        
        # Reset Cache
        self.vtk_mesh = None
        self.vtk_edges = None
        self._mesh_vertices.clear()
        self._mesh_triangles.clear()
        
        current_solid = None
        
        for i, feature in enumerate(self.features):
            if feature.suppressed:
                feature.status = "SUPPRESSED"
                continue
            
            new_solid = None
            status = "OK"
            
            # ================= EXTRUDE =================
            if isinstance(feature, ExtrudeFeature):
                def op_extrude():
                    return self._compute_extrude_part(feature)
                
                part_geometry, status = self._safe_operation(f"Extrude_{i}", op_extrude)

                if part_geometry:
                    if current_solid is None or feature.operation == "New Body":
                        new_solid = part_geometry
                    else:
                        # Boolean Operation mit sicherer Helper-Methode
                        result, success = self._safe_boolean_operation(
                            current_solid, part_geometry, feature.operation
                        )

                        if success:
                            new_solid = result
                        else:
                            logger.warning(f"⚠️ {feature.operation} fehlgeschlagen - Body bleibt unverändert")
                            status = "ERROR"
                            # Behalte current_solid (keine Änderung)
                            continue

            # ================= FILLET =================
            elif isinstance(feature, FilletFeature):
                if current_solid:
                    def op_fillet(rad=feature.radius):
                        edges_to_fillet = self._resolve_edges(current_solid, feature.edge_selectors)
                        if not edges_to_fillet:
                            raise ValueError("No edges selected")
                        # Versuche OCP Fillet
                        result = self._ocp_fillet(current_solid, edges_to_fillet, rad)
                        if result is not None:
                            return result
                        # Fallback zu Build123d
                        return fillet(edges_to_fillet, radius=rad)

                    def fallback_fillet():
                        try:
                            return op_fillet(feature.radius * 0.99)
                        except:
                            return op_fillet(feature.radius * 0.5)

                    new_solid, status = self._safe_operation(f"Fillet_{i}", op_fillet, fallback_fillet)
                    if new_solid is None:
                        new_solid = current_solid
                        status = "ERROR"

            # ================= CHAMFER =================
            elif isinstance(feature, ChamferFeature):
                if current_solid:
                    def op_chamfer(dist=feature.distance):
                        edges = self._resolve_edges(current_solid, feature.edge_selectors)
                        if not edges:
                            raise ValueError("No edges")
                        # Versuche OCP Chamfer
                        result = self._ocp_chamfer(current_solid, edges, dist)
                        if result is not None:
                            return result
                        # Fallback zu Build123d
                        return chamfer(edges, length=dist)

                    def fallback_chamfer():
                        return op_chamfer(feature.distance * 0.5)

                    new_solid, status = self._safe_operation(f"Chamfer_{i}", op_chamfer, fallback_chamfer)
                    if new_solid is None:
                        new_solid = current_solid
                        status = "ERROR"

            # ================= TRANSFORM (NEU) =================
            elif isinstance(feature, TransformFeature):
                if current_solid:
                    def op_transform():
                        return self._apply_transform_feature(current_solid, feature)

                    new_solid, status = self._safe_operation(f"Transform_{i}", op_transform)
                    if new_solid is None:
                        new_solid = current_solid
                        status = "ERROR"

            feature.status = status
            
            if new_solid is not None:
                current_solid = new_solid
                
        if current_solid:
            self._build123d_solid = current_solid
            if hasattr(current_solid, 'wrapped'):
                self.shape = current_solid.wrapped 
            
            # UPDATE MESH via Helper
            self._update_mesh_from_solid(current_solid)
            
            # B-Rep Faces zählen (echte CAD-Faces, nicht Tessellations-Dreiecke)
            from modeling.cad_tessellator import CADTessellator
            n_faces = CADTessellator.count_brep_faces(current_solid)
            if n_faces == 0:
                # Fallback
                n_faces = len(current_solid.faces()) if hasattr(current_solid, 'faces') else 0
            logger.success(f"✓ {self.name}: BREP Valid ({n_faces} Faces)")
        else:
            logger.warning(f"Body '{self.name}' is empty after rebuild.")

    def _resolve_edges(self, solid, selectors):
        """Versucht, Kanten basierend auf Selektoren zu finden (Topological Naming Fallback)."""
        if not selectors:
            return solid.edges() 
        
        found_edges = []
        all_edges = solid.edges()
        
        for sel in selectors:
            best_edge = None
            min_dist = float('inf')
            
            try:
                p_sel = Vector(sel)
                for edge in all_edges:
                    try:
                        dist = (edge.center() - p_sel).length
                        if dist < min_dist:
                            min_dist = dist
                            best_edge = edge
                    except: pass
                
                if best_edge and min_dist < 20.0:
                    found_edges.append(best_edge)
                    
            except Exception:
                pass
                
        return found_edges

    def _apply_transform_feature(self, solid, feature: TransformFeature):
        """
        Wendet ein TransformFeature auf einen Solid an.

        Args:
            solid: build123d Solid
            feature: TransformFeature mit mode und data

        Returns:
            Transformierter Solid
        """
        from build123d import Location, Axis, Plane as B123Plane

        mode = feature.mode
        data = feature.data

        try:
            if mode == "move":
                # Translation: [dx, dy, dz]
                translation = data.get("translation", [0, 0, 0])
                tx, ty, tz = translation
                return solid.move(Location((tx, ty, tz)))

            elif mode == "rotate":
                # Rotation: {"axis": "X/Y/Z", "angle": degrees, "center": [x, y, z]}
                axis_name = data.get("axis", "Z")
                angle = data.get("angle", 0)
                center = data.get("center", [0, 0, 0])

                # Build123d Axis Mapping
                axis_map = {
                    "X": Axis.X,
                    "Y": Axis.Y,
                    "Z": Axis.Z
                }
                axis = axis_map.get(axis_name, Axis.Z)

                # Rotation um beliebigen Punkt:
                # 1. Move to origin
                # 2. Rotate
                # 3. Move back
                cx, cy, cz = center
                solid = solid.move(Location((-cx, -cy, -cz)))
                solid = solid.rotate(axis, angle)
                solid = solid.move(Location((cx, cy, cz)))
                return solid

            elif mode == "scale":
                # Scale: {"factor": float, "center": [x, y, z]}
                factor = data.get("factor", 1.0)
                center = data.get("center", [0, 0, 0])

                cx, cy, cz = center
                solid = solid.move(Location((-cx, -cy, -cz)))
                solid = solid.scale(factor)
                solid = solid.move(Location((cx, cy, cz)))
                return solid

            elif mode == "mirror":
                # Mirror: {"plane": "XY/XZ/YZ"}
                plane_name = data.get("plane", "XY")

                # Build123d Plane Mapping
                plane_map = {
                    "XY": B123Plane.XY,
                    "XZ": B123Plane.XZ,
                    "YZ": B123Plane.YZ
                }
                plane = plane_map.get(plane_name, B123Plane.XY)

                return solid.mirror(plane)

            else:
                logger.warning(f"Unbekannter Transform-Modus: {mode}")
                return solid

        except Exception as e:
            logger.error(f"Transform-Feature-Fehler ({mode}): {e}")
            raise

    def _compute_extrude_part(self, feature: ExtrudeFeature):
        """
        Kombiniert "What you see is what you get" (Detector) mit 
        robuster Fallback-Berechnung (Alter Code).
        """
        if not HAS_BUILD123D or not feature.sketch: return None
        
        try:
            from build123d import make_face, Wire, Compound
            from shapely.geometry import Polygon as ShapelyPoly
            
            sketch = feature.sketch
            plane = self._get_plane_from_sketch(sketch)
            solids = []
            
            # === PFAD A: Exakte Polygone vom Detector (Neu & Stabil) ===
            # Das löst das Hexagon-Loch-Problem, weil wir genau den "Ring" bekommen, 
            # den der Detector berechnet hat.
            if hasattr(feature, 'precalculated_polys') and feature.precalculated_polys:
                logger.info(f"Extrude: Nutze {len(feature.precalculated_polys)} vorausgewählte Profile.")
                
                faces_to_extrude = []
                for idx, poly in enumerate(feature.precalculated_polys):
                    try:
                        # DEBUG: Polygon-Info loggen
                        n_interiors = len(list(poly.interiors)) if hasattr(poly, 'interiors') else 0
                        logger.debug(f"  Polygon {idx}: area={poly.area:.1f}, interiors={n_interiors}")
                        
                        # 1. Außenkontur - Prüfen ob es ein Kreis ist!
                        outer_coords = list(poly.exterior.coords)[:-1]  # Ohne Schlusspunkt
                        logger.debug(f"  Außenkontur: {len(outer_coords)} Punkte")
                        
                        # FIX: Prüfen ob die Außenkontur ein Kreis ist!
                        outer_circle_info = self._detect_circle_from_points(outer_coords)
                        logger.debug(f"  Außenkontur Kreis-Check: {outer_circle_info is not None}")
                        
                        if outer_circle_info and n_interiors == 0:
                            # Die Außenkontur IST ein Kreis (standalone Kreis ohne Löcher)
                            cx, cy, radius = outer_circle_info
                            logger.info(f"  → Außenkontur als ECHTER KREIS: r={radius:.2f} at ({cx:.2f}, {cy:.2f})")
                            
                            center_3d = plane.from_local_coords((cx, cy))
                            from build123d import Plane as B3DPlane
                            circle_plane = B3DPlane(origin=center_3d, z_dir=plane.z_dir)
                            circle_wire = Wire.make_circle(radius, circle_plane)
                            face = make_face(circle_wire)
                        else:
                            # Normale Polygon-Außenkontur (Rechteck, Hexagon, etc.)
                            outer_pts = [plane.from_local_coords((p[0], p[1])) for p in outer_coords]
                            face = make_face(Wire.make_polygon(outer_pts))
                        
                        # 2. Löcher abziehen (Shapely Interiors)
                        for int_idx, interior in enumerate(poly.interiors):
                            inner_coords = list(interior.coords)[:-1]  # Ohne Schlusspunkt
                            logger.debug(f"  Interior {int_idx}: {len(inner_coords)} Punkte")
                            
                            # FIX: Prüfen ob das Loch ein Kreis ist!
                            circle_info = self._detect_circle_from_points(inner_coords)
                            
                            if circle_info:
                                # Echten Kreis verwenden für saubere B-Rep Topologie!
                                cx, cy, radius = circle_info
                                logger.info(f"  → Loch als ECHTER KREIS: r={radius:.2f} at ({cx:.2f}, {cy:.2f})")
                                
                                # Kreis-Wire auf der richtigen Ebene erstellen
                                center_3d = plane.from_local_coords((cx, cy))
                                from build123d import Plane as B3DPlane
                                circle_plane = B3DPlane(origin=center_3d, z_dir=plane.z_dir)
                                circle_wire = Wire.make_circle(radius, circle_plane)
                                circle_face = make_face(circle_wire)
                                face -= circle_face
                            else:
                                # Normales Polygon-Loch
                                logger.warning(f"  → Loch als POLYGON ({len(inner_coords)} Punkte) - kein Kreis erkannt!")
                                inner_pts = [plane.from_local_coords((p[0], p[1])) for p in inner_coords]
                                face -= make_face(Wire.make_polygon(inner_pts))
                            
                        faces_to_extrude.append(face)
                    except Exception as e:
                        logger.warning(f"Fehler bei Face-Konvertierung: {e}")
                        import traceback
                        traceback.print_exc()

                # Extrudieren mit OCP für bessere Robustheit
                amount = feature.distance * feature.direction
                for f in faces_to_extrude:
                    s = self._ocp_extrude_face(f, amount, plane.z_dir)
                    if s is not None:
                        solids.append(s)

            # === PFAD B: Fallback auf "Alten Code" (Rebuild / Scripting) ===
            if not solids:
                logger.info("Extrude: Starte Auto-Detection (Legacy Mode)...")
                # ... [HIER FÜGST DU DEINEN GELIEFERTEN ALTEN CODE EIN] ...
                # Ich rufe hier eine interne Methode auf, die deinen alten Code enthält, 
                # um diesen Block übersichtlich zu halten.
                return self._compute_extrude_legacy(feature, plane)
            
            if not solids: return None
            return solids[0] if len(solids) == 1 else Compound(children=solids)
            
        except Exception as e:
            logger.error(f"Extrude Fehler: {e}")
            return None

    def _detect_circle_from_points(self, points, tolerance=0.02):
        """
        Erkennt ob ein Polygon eigentlich ein Kreis ist.
        
        Args:
            points: Liste von (x, y) Tupeln
            tolerance: Relative Toleranz für Radius-Varianz (2% default)
            
        Returns:
            (cx, cy, radius) wenn es ein Kreis ist, sonst None
        """
        import numpy as np
        
        if len(points) < 8:  # Minimum für Kreis-Erkennung
            return None
        
        pts = np.array(points)
        
        # Schwerpunkt berechnen
        cx = np.mean(pts[:, 0])
        cy = np.mean(pts[:, 1])
        
        # Abstände zum Schwerpunkt
        distances = np.sqrt((pts[:, 0] - cx)**2 + (pts[:, 1] - cy)**2)
        
        # Mittlerer Radius
        radius = np.mean(distances)
        
        if radius < 0.1:  # Zu klein
            return None
        
        # Varianz prüfen (sollte sehr klein sein für Kreis)
        variance = np.std(distances) / radius
        
        logger.debug(f"_detect_circle: {len(points)} Punkte, r={radius:.2f}, varianz={variance:.6f}")
        
        if variance < tolerance:
            # Es ist ein Kreis!
            return (float(cx), float(cy), float(radius))
        
        return None

    def _compute_extrude_legacy(self, feature, plane):
        """
        Legacy-Logik für Extrusion (Auto-Detection von Löchern etc.),
        falls keine vorausberechneten Polygone vorhanden sind.
        Entspricht exakt der alten, robusten Implementierung.
        """
        if not HAS_BUILD123D or not feature.sketch: return None
        
        try:
            from shapely.geometry import LineString, Point, Polygon as ShapelyPoly
            from shapely.ops import unary_union, polygonize
            from build123d import make_face, Vector, Wire, Compound, Shape
            import math
            
            logger.info(f"--- Starte Legacy Extrusion: {feature.name} ---")
            
            sketch = feature.sketch
            # plane ist bereits übergeben
            
            # --- 1. Segmente sammeln ---
            all_segments = []
            def rnd(val): return round(val, 5)
            
            for l in sketch.lines:
                if not l.construction:
                    all_segments.append(LineString([(rnd(l.start.x), rnd(l.start.y)), (rnd(l.end.x), rnd(l.end.y))]))
            for c in sketch.circles:
                if not c.construction:
                    pts = [(rnd(c.center.x + c.radius * math.cos(i * 2 * math.pi / 64)), 
                            rnd(c.center.y + c.radius * math.sin(i * 2 * math.pi / 64))) for i in range(65)]
                    all_segments.append(LineString(pts))
            for arc in sketch.arcs:
                 if not arc.construction:
                    pts = []
                    start, end = arc.start_angle, arc.end_angle
                    sweep = end - start
                    if sweep < 0.1: sweep += 360
                    steps = max(12, int(sweep / 5))
                    for i in range(steps + 1):
                        t = math.radians(start + sweep * i / steps)
                        x = arc.center.x + arc.radius * math.cos(t)
                        y = arc.center.y + arc.radius * math.sin(t)
                        pts.append((rnd(x), rnd(y)))
                    if len(pts) >= 2: all_segments.append(LineString(pts))
            for spline in getattr(sketch, 'splines', []):
                 if not getattr(spline, 'construction', False):
                     pts_raw = []
                     if hasattr(spline, 'get_curve_points'):
                         pts_raw = spline.get_curve_points(segments_per_span=16)
                     elif hasattr(spline, 'to_lines'):
                         lines = spline.to_lines(segments_per_span=16)
                         if lines:
                             pts_raw.append((lines[0].start.x, lines[0].start.y))
                             for ln in lines: pts_raw.append((ln.end.x, ln.end.y))
                     pts = [(rnd(p[0]), rnd(p[1])) for p in pts_raw]
                     if len(pts) >= 2: all_segments.append(LineString(pts))

            if not all_segments: return None

            # --- 2. Polygonize & Deduplizierung ---
            try:
                merged = unary_union(all_segments)
                raw_candidates = list(polygonize(merged))
                
                candidates = []
                for rc in raw_candidates:
                    clean_poly = rc.buffer(0) # Reparatur
                    is_dup = False
                    for existing in candidates:
                        if abs(clean_poly.area - existing.area) < 1e-4 and clean_poly.centroid.distance(existing.centroid) < 1e-4:
                            is_dup = True
                            break
                    if not is_dup:
                        candidates.append(clean_poly)
                
                logger.info(f"Kandidaten (Unique): {len(candidates)}")
            except Exception as e:
                logger.error(f"Polygonize failed: {e}")
                return None
            
            if not candidates: return None

            # --- 3. Selektion ---
            selected_indices = set()
            if feature.selector:
                selectors = feature.selector
                if isinstance(selectors, tuple) and len(selectors) == 2 and isinstance(selectors[0], (int, float)):
                    selectors = [selectors]
                
                for sel_pt in selectors:
                    pt = Point(sel_pt)
                    matches = []
                    for i, poly in enumerate(candidates):
                        if poly.contains(pt) or poly.distance(pt) < 1e-2:
                            matches.append(i)
                    if matches:
                        best = min(matches, key=lambda i: candidates[i].area)
                        selected_indices.add(best)
            else:
                selected_indices = set(range(len(candidates)))

            if not selected_indices: return None

            # --- 4. Faces bauen ---
            faces_to_extrude = []

            def to_3d_wire(shapely_poly):
                try:
                    pts_2d = list(shapely_poly.exterior.coords[:-1])
                    if len(pts_2d) < 3: return None
                    pts_3d = [plane.from_local_coords((p[0], p[1])) for p in pts_2d]
                    return Wire.make_polygon(pts_3d)
                except: return None

            for outer_idx in selected_indices:
                try:
                    outer_poly = candidates[outer_idx]
                    outer_wire = to_3d_wire(outer_poly)
                    if not outer_wire: continue
                    
                    main_face = make_face(outer_wire)
                    
                    # Löcher suchen
                    for i, potential_hole in enumerate(candidates):
                        if i == outer_idx: continue
                        
                        # WICHTIG 1: Ein Loch muss kleiner sein!
                        if potential_hole.area >= outer_poly.area * 0.99:
                            continue

                        # Check: Ist es drinnen?
                        is_inside = False
                        reason = ""
                        
                        try:
                            # A) Konzentrisch (Sehr starkes Indiz für Loch)
                            if outer_poly.centroid.distance(potential_hole.centroid) < 1e-3:
                                is_inside = True; reason = "Concentric"
                            
                            # B) Intersection
                            elif not is_inside:
                                intersect = outer_poly.intersection(potential_hole)
                                ratio = intersect.area / potential_hole.area if potential_hole.area > 0 else 0
                                if ratio > 0.9: 
                                    is_inside = True; reason = f"Overlap {ratio:.2f}"
                            
                            # C) Centroid Check
                            if not is_inside:
                                if outer_poly.contains(potential_hole.centroid):
                                    is_inside = True; reason = "Centroid"
                        except: pass

                        if is_inside:
                            # Nur schneiden, wenn nicht selbst ausgewählt
                            if i not in selected_indices:
                                logger.info(f"  -> Schneide Loch #{i} ({reason})")
                                hole_wire = to_3d_wire(potential_hole)
                                if hole_wire:
                                    try:
                                        hole_face = make_face(hole_wire)
                                        main_face = main_face - hole_face
                                    except Exception as e:
                                        logger.warning(f"Cut failed: {e}")

                    faces_to_extrude.append(main_face)
                except Exception as e:
                    logger.error(f"Face construction error: {e}")

            if not faces_to_extrude: return None

            # --- 5. Extrudieren mit OCP ---
            solids = []
            amount = feature.distance * feature.direction
            direction_vec = plane.z_dir

            for f in faces_to_extrude:
                s = self._ocp_extrude_face(f, amount, direction_vec)
                if s is not None:
                    solids.append(s)
                else:
                    logger.warning(f"Extrude für Face fehlgeschlagen")

            if not solids: 
                logger.warning("Keine Solids erzeugt!")
                return None
            
            logger.success(f"Legacy Extrusion OK: {len(solids)} Solids erzeugt.")

            if len(solids) == 1:
                return solids[0]
            else:
                return Compound(children=solids)
            
        except Exception as e:
            logger.error(f"Legacy Extrude CRASH: {e}")
            raise e


        
    
    
    def _get_plane_from_sketch(self, sketch):
        origin = getattr(sketch, 'plane_origin', (0,0,0))
        normal = getattr(sketch, 'plane_normal', (0,0,1))
        x_dir = getattr(sketch, 'plane_x_dir', None)
        if x_dir:
            return Plane(origin=origin, x_dir=x_dir, z_dir=normal)
        return Plane(origin=origin, z_dir=normal)

    def _update_mesh_from_solid(self, solid):
        """
        Generiert Mesh-Daten via Tessellator.
        Ersetzt den alten komplexen Code durch einen einfachen Helper-Aufruf.
        """
        if not solid: return

        # Cache leeren bei erstem Aufruf (falls nicht beim Start geschehen)
        if not CADTessellator._cache_cleared:
            CADTessellator.clear_cache()

        # 1. High-Performance Tessellierung mit Cache
        self.vtk_mesh, self.vtk_edges = CADTessellator.tessellate(solid)
        
        # Debug: Edge-Info loggen
        if self.vtk_edges is not None:
            logger.debug(f"Body '{self.name}': {self.vtk_edges.n_lines} Edge-Linien")
        
        # 2. Legacy Support leeren
        self._mesh_vertices = []
        self._mesh_triangles = []

    def export_stl(self, filename: str) -> bool:
        """STL Export: Versucht Build123d, dann VTK, dann Legacy."""
        
        # 1. build123d Export (Analytisch sauber)
        if HAS_BUILD123D and self.shape is not None:
            try:
                export_stl(self._build123d_solid, filename)
                return True
            except Exception as e:
                logger.error(f"Build123d STL export failed, trying mesh fallback: {e}")
        
        # 2. VTK Mesh Export (Schnell und robust)
        if self.vtk_mesh is not None:
            try:
                self.vtk_mesh.save(filename)
                return True
            except Exception as e:
                logger.error(f"VTK STL export failed: {e}")

        # 3. Legacy Fallback
        if self._mesh_vertices and self._mesh_triangles:
            return self._export_stl_simple(filename)
            
        return False

    def _export_stl_simple(self, filename: str) -> bool:
        """Primitiver STL Export aus Mesh-Daten (Letzter Ausweg)"""
        try:
            with open(filename, 'w') as f:
                f.write(f"solid {self.name}\n")
                for tri in self._mesh_triangles:
                    v0 = self._mesh_vertices[tri[0]]
                    v1 = self._mesh_vertices[tri[1]]
                    v2 = self._mesh_vertices[tri[2]]
                    f.write(f"  facet normal 0 0 1\n")
                    f.write(f"    outer loop\n")
                    f.write(f"      vertex {v0[0]} {v0[1]} {v0[2]}\n")
                    f.write(f"      vertex {v1[0]} {v1[1]} {v1[2]}\n")
                    f.write(f"      vertex {v2[0]} {v2[1]} {v2[2]}\n")
                    f.write(f"    endloop\n")
                    f.write(f"  endfacet\n")
                f.write(f"endsolid {self.name}\n")
            return True
        except:
            return False

class Document:
    def __init__(self, name="Doc"):
        self.bodies: List[Body] = []
        self.sketches: List[Sketch] = []
        self.name = name
        self.active_body: Optional[Body] = None
        self.active_sketch: Optional[Sketch] = None
    
    def new_body(self, name=None):
        b = Body(name or f"Body{len(self.bodies)+1}")
        self.bodies.append(b)
        self.active_body = b
        return b
        
    def new_sketch(self, name=None):
        s = Sketch(name or f"Sketch{len(self.sketches)+1}")
        self.sketches.append(s)
        self.active_sketch = s
        return s
