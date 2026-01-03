"""
LiteCAD - 3D Modeling
Extrude, Revolve, Boolean Operations via OpenCascade
"""

from dataclasses import dataclass, field
from typing import List, Optional, Tuple, Union
from enum import Enum, auto
import math
import uuid

# Versuche build123d zu importieren, sonst Fallback
HAS_BUILD123D = False
HAS_OCP = False

try:
    # Basis-Imports die in allen Versionen existieren sollten
    from build123d import (
        Box, Cylinder, Sphere,
        extrude, 
        Axis, Plane, Location, Vector,
        BuildPart, BuildSketch, BuildLine,
        Part
    )
    
    # Optionale Imports (nicht in allen Versionen)
    try:
        from build123d import Cone
    except ImportError:
        Cone = None
    
    try:
        from build123d import export_stl, export_step
    except ImportError:
        export_stl = None
        export_step = None
    
    try:
        from build123d import fillet, chamfer
    except ImportError:
        fillet = None
        chamfer = None
    
    try:
        from build123d import add, cut, intersect
    except ImportError:
        add = None
        cut = None
        intersect = None
    
    try:
        from build123d import make_face
    except ImportError:
        make_face = None
    
    try:
        from build123d import Sketch as B123Sketch, Rectangle as B123Rect, Circle as B123Circle
        from build123d import Line as B123Line, Polyline
    except ImportError:
        B123Sketch = None
        B123Rect = None
        B123Circle = None
        B123Line = None
        Polyline = None
    
    try:
        from build123d import revolve, sweep, loft
    except ImportError:
        revolve = None
        sweep = None
        loft = None
    
    HAS_BUILD123D = True
    print("Info: build123d erfolgreich geladen.")
    
except Exception as e:
    # Fange alle Fehler ab, nicht nur ImportError
    print(f"Info: build123d nicht verfügbar ({type(e).__name__}: {e}). Verwende einfachen Mesh-Export.")

# Fallback: OCP direkt (nur wenn build123d nicht funktioniert)
if not HAS_BUILD123D:
    try:
        from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox, BRepPrimAPI_MakeCylinder, BRepPrimAPI_MakePrism
        from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeEdge, BRepBuilderAPI_MakeWire, BRepBuilderAPI_MakeFace
        from OCP.BRepAlgoAPI import BRepAlgoAPI_Fuse, BRepAlgoAPI_Cut, BRepAlgoAPI_Common
        from OCP.gp import gp_Pnt, gp_Vec, gp_Dir, gp_Ax1, gp_Ax2
        from OCP.TopoDS import TopoDS_Shape
        from OCP.StlAPI import StlAPI_Writer
        from OCP.BRepMesh import BRepMesh_IncrementalMesh
        HAS_OCP = True
    except Exception:
        pass

import sys
import os

# Projektpfad hinzufügen
_project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from sketcher import Sketch, Line2D, Circle2D, Arc2D, Point2D


class FeatureType(Enum):
    """Feature-Typen"""
    SKETCH = auto()
    EXTRUDE = auto()
    REVOLVE = auto()
    SWEEP = auto()
    LOFT = auto()
    FILLET = auto()
    CHAMFER = auto()
    BOOLEAN_UNION = auto()
    BOOLEAN_CUT = auto()
    BOOLEAN_INTERSECT = auto()
    PRIMITIVE_BOX = auto()
    PRIMITIVE_CYLINDER = auto()
    PRIMITIVE_SPHERE = auto()


@dataclass
class Feature:
    """Basis-Feature"""
    type: FeatureType
    name: str
    id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    visible: bool = True
    suppressed: bool = False


@dataclass
class ExtrudeFeature(Feature):
    """Extrude-Feature"""
    sketch: Sketch = None
    distance: float = 10.0
    direction: int = 1  # 1 = positiv, -1 = negativ, 0 = symmetrisch
    operation: str = "add"  # "add", "cut", "intersect"
    
    def __post_init__(self):
        self.type = FeatureType.EXTRUDE
        if not self.name:
            self.name = "Extrude"


@dataclass
class RevolveFeature(Feature):
    """Revolve-Feature"""
    sketch: Sketch = None
    angle: float = 360.0
    axis: Tuple[float, float, float] = (0, 1, 0)  # Rotationsachse
    operation: str = "add"
    
    def __post_init__(self):
        self.type = FeatureType.REVOLVE
        if not self.name:
            self.name = "Revolve"


@dataclass 
class FilletFeature(Feature):
    """Verrundung"""
    radius: float = 2.0
    edges: List = field(default_factory=list)  # Kanten-IDs
    
    def __post_init__(self):
        self.type = FeatureType.FILLET
        if not self.name:
            self.name = "Fillet"


@dataclass
class ChamferFeature(Feature):
    """Fase"""
    distance: float = 2.0
    edges: List = field(default_factory=list)
    
    def __post_init__(self):
        self.type = FeatureType.CHAMFER
        if not self.name:
            self.name = "Chamfer"


class Body:
    """
    3D-Körper (Body)
    Enthält Features und den resultierenden Shape
    """
    
    def __init__(self, name: str = "Body"):
        self.name = name
        self.id = str(uuid.uuid4())[:8]
        self.features: List[Feature] = []
        self.shape = None  # OpenCascade Shape
        self._mesh_vertices: List[Tuple[float, float, float]] = []
        self._mesh_triangles: List[Tuple[int, int, int]] = []
    
    def add_feature(self, feature: Feature):
        """Feature hinzufügen"""
        self.features.append(feature)
        self._rebuild()
    
    def remove_feature(self, feature: Feature):
        """Feature entfernen"""
        if feature in self.features:
            self.features.remove(feature)
            self._rebuild()
    
    def _rebuild(self):
        """Körper neu berechnen"""
        self.shape = None
        self._mesh_vertices.clear()
        self._mesh_triangles.clear()
        
        for feature in self.features:
            if feature.suppressed:
                continue
            
            if isinstance(feature, ExtrudeFeature):
                self._apply_extrude(feature)
            elif isinstance(feature, RevolveFeature):
                self._apply_revolve(feature)
            elif isinstance(feature, FilletFeature):
                self._apply_fillet(feature)
            elif isinstance(feature, ChamferFeature):
                self._apply_chamfer(feature)
    
    def _apply_extrude(self, feature: ExtrudeFeature):
        """Extrude anwenden"""
        if not feature.sketch:
            return
        
        if HAS_BUILD123D:
            self._extrude_build123d(feature)
        elif HAS_OCP:
            self._extrude_ocp(feature)
        else:
            self._extrude_simple(feature)
    
    def _extrude_build123d(self, feature: ExtrudeFeature):
        """Extrude mit build123d"""
        sketch = feature.sketch
        
        try:
            with BuildPart() as part:
                with BuildSketch():
                    # Konvertiere Sketch-Geometrie
                    profiles = sketch.find_closed_profiles()
                    
                    if profiles:
                        # Verwende erstes geschlossenes Profil
                        profile = profiles[0]
                        points = []
                        for line in profile:
                            points.append((line.start.x, line.start.y))
                        points.append(points[0])  # Schließen
                        Polyline(points)
                        make_face()
                    
                    elif sketch.circles:
                        # Verwende ersten Kreis
                        circle = sketch.circles[0]
                        B123Circle(circle.radius)
                    
                    else:
                        # Fallback: Rechteck aus Linien-Bounding-Box
                        if sketch.lines:
                            min_x = min(l.start.x for l in sketch.lines)
                            max_x = max(l.end.x for l in sketch.lines)
                            min_y = min(l.start.y for l in sketch.lines)
                            max_y = max(l.end.y for l in sketch.lines)
                            B123Rect(max_x - min_x, max_y - min_y)
                
                # Extrude
                distance = feature.distance * feature.direction
                extrude(amount=distance)
            
            self.shape = part.part
            
        except Exception as e:
            print(f"build123d extrude error: {e}")
            self._extrude_simple(feature)
    
    def _extrude_ocp(self, feature: ExtrudeFeature):
        """Extrude mit OCP direkt"""
        sketch = feature.sketch
        
        try:
            # Erstelle Wire aus Sketch
            profiles = sketch.find_closed_profiles()
            
            if not profiles and not sketch.circles:
                return
            
            if sketch.circles:
                # Kreis extrudieren
                circle = sketch.circles[0]
                from OCP.BRepPrimAPI import BRepPrimAPI_MakeCylinder
                from OCP.gp import gp_Ax2, gp_Pnt, gp_Dir
                
                ax = gp_Ax2(gp_Pnt(circle.center.x, circle.center.y, 0), gp_Dir(0, 0, 1))
                shape = BRepPrimAPI_MakeCylinder(ax, circle.radius, feature.distance).Shape()
                
            else:
                # Polygon extrudieren
                profile = profiles[0]
                
                # Wire erstellen
                from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeWire, BRepBuilderAPI_MakeEdge, BRepBuilderAPI_MakeFace
                from OCP.gp import gp_Pnt
                
                wire_builder = BRepBuilderAPI_MakeWire()
                for line in profile:
                    p1 = gp_Pnt(line.start.x, line.start.y, 0)
                    p2 = gp_Pnt(line.end.x, line.end.y, 0)
                    edge = BRepBuilderAPI_MakeEdge(p1, p2).Edge()
                    wire_builder.Add(edge)
                
                wire = wire_builder.Wire()
                face = BRepBuilderAPI_MakeFace(wire).Face()
                
                # Prism
                vec = gp_Vec(0, 0, feature.distance * feature.direction)
                shape = BRepPrimAPI_MakePrism(face, vec).Shape()
            
            # Boolean
            if self.shape is None:
                self.shape = shape
            else:
                if feature.operation == "add":
                    self.shape = BRepAlgoAPI_Fuse(self.shape, shape).Shape()
                elif feature.operation == "cut":
                    self.shape = BRepAlgoAPI_Cut(self.shape, shape).Shape()
                elif feature.operation == "intersect":
                    self.shape = BRepAlgoAPI_Common(self.shape, shape).Shape()
                    
        except Exception as e:
            print(f"OCP extrude error: {e}")
            self._extrude_simple(feature)
    
    def _extrude_simple(self, feature: ExtrudeFeature):
        """Einfaches Extrude ohne OpenCascade (nur Mesh)"""
        sketch = feature.sketch
        height = feature.distance * feature.direction
        
        profiles = sketch.find_closed_profiles()
        
        if profiles:
            # Polygon extrudieren
            profile = profiles[0]
            points_2d = [(line.start.x, line.start.y) for line in profile]
            self._create_extruded_mesh(points_2d, height)
        
        elif sketch.circles:
            # Kreis -> Zylinder
            circle = sketch.circles[0]
            self._create_cylinder_mesh(circle.center.x, circle.center.y, circle.radius, height)
        
        elif sketch.lines:
            # Bounding Box als Fallback
            min_x = min(min(l.start.x, l.end.x) for l in sketch.lines)
            max_x = max(max(l.start.x, l.end.x) for l in sketch.lines)
            min_y = min(min(l.start.y, l.end.y) for l in sketch.lines)
            max_y = max(max(l.start.y, l.end.y) for l in sketch.lines)
            
            points_2d = [
                (min_x, min_y),
                (max_x, min_y),
                (max_x, max_y),
                (min_x, max_y)
            ]
            self._create_extruded_mesh(points_2d, height)
    
    def _create_extruded_mesh(self, points_2d: List[Tuple[float, float]], height: float):
        """Erstellt Mesh für extrudiertes Polygon"""
        n = len(points_2d)
        if n < 3:
            return
        
        # Vertices: Boden + Deckel
        base_idx = len(self._mesh_vertices)
        
        for x, y in points_2d:
            self._mesh_vertices.append((x, y, 0))
        for x, y in points_2d:
            self._mesh_vertices.append((x, y, height))
        
        # Boden-Triangles (Fan)
        for i in range(1, n - 1):
            self._mesh_triangles.append((base_idx, base_idx + i + 1, base_idx + i))
        
        # Deckel-Triangles (Fan, umgekehrte Reihenfolge)
        top_idx = base_idx + n
        for i in range(1, n - 1):
            self._mesh_triangles.append((top_idx, top_idx + i, top_idx + i + 1))
        
        # Seitenflächen
        for i in range(n):
            next_i = (i + 1) % n
            # Zwei Dreiecke pro Seite
            self._mesh_triangles.append((base_idx + i, base_idx + next_i, top_idx + i))
            self._mesh_triangles.append((base_idx + next_i, top_idx + next_i, top_idx + i))
    
    def _create_cylinder_mesh(self, cx: float, cy: float, radius: float, height: float, segments: int = 32):
        """Erstellt Mesh für Zylinder"""
        base_idx = len(self._mesh_vertices)
        
        # Zentrum unten/oben
        self._mesh_vertices.append((cx, cy, 0))
        self._mesh_vertices.append((cx, cy, height))
        center_bottom = base_idx
        center_top = base_idx + 1
        
        # Randpunkte
        for i in range(segments):
            angle = 2 * math.pi * i / segments
            x = cx + radius * math.cos(angle)
            y = cy + radius * math.sin(angle)
            self._mesh_vertices.append((x, y, 0))
            self._mesh_vertices.append((x, y, height))
        
        # Boden
        for i in range(segments):
            next_i = (i + 1) % segments
            self._mesh_triangles.append((
                center_bottom,
                base_idx + 2 + next_i * 2,
                base_idx + 2 + i * 2
            ))
        
        # Deckel
        for i in range(segments):
            next_i = (i + 1) % segments
            self._mesh_triangles.append((
                center_top,
                base_idx + 3 + i * 2,
                base_idx + 3 + next_i * 2
            ))
        
        # Mantel
        for i in range(segments):
            next_i = (i + 1) % segments
            b1 = base_idx + 2 + i * 2
            b2 = base_idx + 2 + next_i * 2
            t1 = b1 + 1
            t2 = b2 + 1
            self._mesh_triangles.append((b1, b2, t1))
            self._mesh_triangles.append((b2, t2, t1))
    
    def _apply_revolve(self, feature: RevolveFeature):
        """Revolve anwenden"""
        # TODO: Implementieren
        pass
    
    def _apply_fillet(self, feature: FilletFeature):
        """Fillet anwenden"""
        if not HAS_BUILD123D and not HAS_OCP:
            return
        # TODO: Implementieren
        pass
    
    def _apply_chamfer(self, feature: ChamferFeature):
        """Chamfer anwenden"""
        if not HAS_BUILD123D and not HAS_OCP:
            return
        # TODO: Implementieren
        pass
    
    def export_stl(self, filename: str, linear_deflection: float = 0.1):
        """STL exportieren"""
        if HAS_BUILD123D and self.shape is not None:
            try:
                export_stl(self.shape, filename)
                return True
            except:
                pass
        
        if HAS_OCP and self.shape is not None:
            try:
                mesh = BRepMesh_IncrementalMesh(self.shape, linear_deflection)
                mesh.Perform()
                
                writer = StlAPI_Writer()
                writer.Write(self.shape, filename)
                return True
            except:
                pass
        
        # Fallback: Eigenes Mesh exportieren
        if self._mesh_vertices and self._mesh_triangles:
            return self._export_stl_simple(filename)
        
        return False
    
    def _export_stl_simple(self, filename: str) -> bool:
        """Einfacher STL-Export aus internem Mesh"""
        try:
            with open(filename, 'w') as f:
                f.write(f"solid {self.name}\n")
                
                for tri in self._mesh_triangles:
                    v0 = self._mesh_vertices[tri[0]]
                    v1 = self._mesh_vertices[tri[1]]
                    v2 = self._mesh_vertices[tri[2]]
                    
                    # Normale berechnen
                    ux, uy, uz = v1[0]-v0[0], v1[1]-v0[1], v1[2]-v0[2]
                    vx, vy, vz = v2[0]-v0[0], v2[1]-v0[1], v2[2]-v0[2]
                    nx = uy*vz - uz*vy
                    ny = uz*vx - ux*vz
                    nz = ux*vy - uy*vx
                    length = math.sqrt(nx*nx + ny*ny + nz*nz)
                    if length > 0:
                        nx, ny, nz = nx/length, ny/length, nz/length
                    
                    f.write(f"  facet normal {nx} {ny} {nz}\n")
                    f.write(f"    outer loop\n")
                    f.write(f"      vertex {v0[0]} {v0[1]} {v0[2]}\n")
                    f.write(f"      vertex {v1[0]} {v1[1]} {v1[2]}\n")
                    f.write(f"      vertex {v2[0]} {v2[1]} {v2[2]}\n")
                    f.write(f"    endloop\n")
                    f.write(f"  endfacet\n")
                
                f.write(f"endsolid {self.name}\n")
            
            return True
        except Exception as e:
            print(f"STL export error: {e}")
            return False
    
    def export_step(self, filename: str):
        """STEP exportieren"""
        if HAS_BUILD123D and self.shape is not None:
            try:
                export_step(self.shape, filename)
                return True
            except:
                pass
        return False
    
    def get_mesh_data(self) -> Tuple[List, List]:
        """Gibt Mesh-Daten zurück (für Rendering)"""
        if HAS_OCP and self.shape is not None:
            # Mesh aus Shape extrahieren
            try:
                from OCP.BRepMesh import BRepMesh_IncrementalMesh
                from OCP.TopExp import TopExp_Explorer
                from OCP.TopAbs import TopAbs_FACE
                from OCP.BRep import BRep_Tool
                from OCP.TopLoc import TopLoc_Location
                
                mesh = BRepMesh_IncrementalMesh(self.shape, 0.5)
                mesh.Perform()
                
                vertices = []
                triangles = []
                
                explorer = TopExp_Explorer(self.shape, TopAbs_FACE)
                while explorer.More():
                    face = explorer.Current()
                    location = TopLoc_Location()
                    triangulation = BRep_Tool.Triangulation_s(face, location)
                    
                    if triangulation:
                        # Vertices
                        base_idx = len(vertices)
                        for i in range(1, triangulation.NbNodes() + 1):
                            node = triangulation.Node(i)
                            vertices.append((node.X(), node.Y(), node.Z()))
                        
                        # Triangles
                        for i in range(1, triangulation.NbTriangles() + 1):
                            tri = triangulation.Triangle(i)
                            n1, n2, n3 = tri.Get()
                            triangles.append((base_idx + n1 - 1, base_idx + n2 - 1, base_idx + n3 - 1))
                    
                    explorer.Next()
                
                if vertices:
                    return vertices, triangles
            except:
                pass
        
        return self._mesh_vertices, self._mesh_triangles


class Document:
    """
    CAD-Dokument
    Enthält Bodies, Sketches und Feature-History
    """
    
    def __init__(self, name: str = "Unbenannt"):
        self.name = name
        self.id = str(uuid.uuid4())[:8]
        self.bodies: List[Body] = []
        self.sketches: List[Sketch] = []
        self.active_body: Optional[Body] = None
        self.active_sketch: Optional[Sketch] = None
    
    def new_body(self, name: str = None) -> Body:
        """Neuen Body erstellen"""
        if name is None:
            name = f"Body{len(self.bodies) + 1}"
        body = Body(name)
        self.bodies.append(body)
        self.active_body = body
        return body
    
    def new_sketch(self, name: str = None) -> Sketch:
        """Neuen Sketch erstellen"""
        if name is None:
            name = f"Sketch{len(self.sketches) + 1}"
        sketch = Sketch(name)
        self.sketches.append(sketch)
        self.active_sketch = sketch
        return sketch
    
    def extrude(self, sketch: Sketch, distance: float, operation: str = "add") -> ExtrudeFeature:
        """Sketch extrudieren"""
        if self.active_body is None:
            self.new_body()
        
        feature = ExtrudeFeature(
            type=FeatureType.EXTRUDE,
            name=f"Extrude{len(self.active_body.features) + 1}",
            sketch=sketch,
            distance=distance,
            operation=operation
        )
        
        self.active_body.add_feature(feature)
        return feature
    
    def export_stl(self, filename: str) -> bool:
        """Alle Bodies als STL exportieren"""
        if not self.bodies:
            return False
        
        # Einfach: Exportiere ersten Body
        return self.bodies[0].export_stl(filename)


# === Test ===

def test_modeling():
    """Test der Modeling-Funktionen"""
    print("=" * 50)
    print("LiteCAD Modeling Test")
    print(f"build123d available: {HAS_BUILD123D}")
    print(f"OCP available: {HAS_OCP}")
    print("=" * 50)
    
    # Dokument erstellen
    doc = Document("Test")
    
    # Sketch erstellen
    sketch = doc.new_sketch("Sketch1")
    sketch.add_rectangle(0, 0, 30, 20)
    sketch.add_fixed(sketch.lines[0].start)
    sketch.solve()
    
    print(f"\nSketch: {sketch}")
    print(f"Closed profiles: {len(sketch.find_closed_profiles())}")
    
    # Extrudieren
    feature = doc.extrude(sketch, 15)
    print(f"\nFeature: {feature.name}")
    
    body = doc.active_body
    vertices, triangles = body.get_mesh_data()
    print(f"Mesh: {len(vertices)} vertices, {len(triangles)} triangles")
    
    # STL Export
    stl_file = "/tmp/test_litecad.stl"
    if body.export_stl(stl_file):
        print(f"\nSTL exported: {stl_file}")
    
    print("\n" + "=" * 50)
    print("Test completed!")


if __name__ == "__main__":
    test_modeling()
