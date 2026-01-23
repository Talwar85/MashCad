"""
MashCad - Geometry Detector
Face and Edge detection for 3D viewport
"""

import numpy as np
import math
from dataclasses import dataclass, field
from typing import List, Optional, Tuple, Dict, Any
from loguru import logger

# Optional Imports
try:
    from shapely.geometry import Polygon, Point
    from shapely.ops import unary_union, polygonize
    HAS_SHAPELY = True
except ImportError:
    HAS_SHAPELY = False

try:
    import pyvista as pv
    import vtk
    HAS_VTK = True
except ImportError:
    HAS_VTK = False


@dataclass
class DetectedEdge:
    id: int
    body_id: str
    edge_type: str # 'boundary' oder 'feature'
    points: List[Tuple[float, float, float]]
    vtk_cells: List[int] # Referenz zur Linie im Edge-Mesh

@dataclass
class SelectionFace:
    id: int
    owner_id: str                # sketch_id oder body_id
    domain_type: str             # 'sketch_shell', 'sketch_hole', 'body_face'

    shapely_poly: Any = None
    plane_origin: Tuple[float, float, float] = (0,0,0)
    plane_normal: Tuple[float, float, float] = (0,0,1)
    plane_x: Tuple[float, float, float] = (1,0,0)
    plane_y: Tuple[float, float, float] = (0,1,0)

    pick_priority: int = 0
    display_mesh: Any = None


class GeometryDetector:
    class SelectionFilter:
        # FIX: "sketch_profile" hinzufügen!
        ALL = {"sketch_shell", "sketch_hole", "body_face", "sketch_profile"}
        
        # Profile (die Ringe) gehören logisch zu den Skizzen
        SKETCH = {"sketch_shell", "sketch_hole", "sketch_profile"}
        
        # Löcher bleiben Löcher
        HOLE = {"sketch_hole"}
        
        # Faces sind Shells, Profile (Ringe) und Body-Flächen
        FACE = {"sketch_shell", "body_face", "sketch_profile"}
        
    def __init__(self):
        self.selection_faces: List[SelectionFace] = []
        self._counter = 0
        

    def clear(self):
        self.selection_faces.clear()
        self._counter = 0
        
        
    
    def process_sketch(self, sketch, plane_origin, plane_normal, plane_x_dir, plane_y_dir=None):
        """
        Analysiert Sketch-Linien und erkennt verschachtelte Regionen (Inseln).
        Löst das Problem: Kreis im Hexagon -> Erkennt Ring und Kern separat.
        """
        if not HAS_SHAPELY: return

        from shapely.geometry import LineString, Polygon
        from shapely.ops import unary_union, polygonize

        if plane_y_dir is None:
             # Fallback Berechnung
             n = np.array(plane_normal)
             x = np.array(plane_x_dir)
             y = np.cross(n, x)
             plane_y_dir = tuple(y)

        # 1. Linien in Shapely konvertieren
        lines = []
        standalone_circles = []  # Kreise die eigenständig sind
        def rnd(val): return round(val, 5)

        # Lines
        for l in getattr(sketch, 'lines', []):
            if not l.construction:
                lines.append(LineString([(rnd(l.start.x), rnd(l.start.y)), (rnd(l.end.x), rnd(l.end.y))]))
        
        # Circles - Mit mehr Segmenten für bessere Präzision
        for c in getattr(sketch, 'circles', []):
            if not c.construction:
                # 128 Segmente für glattere Kreise
                num_segments = 128
                pts = []
                for i in range(num_segments + 1):
                    angle = i * 2 * math.pi / num_segments
                    pts.append((
                        rnd(c.center.x + c.radius * math.cos(angle)),
                        rnd(c.center.y + c.radius * math.sin(angle))
                    ))
                circle_line = LineString(pts)
                lines.append(circle_line)
                
                # Speichere als eigenständiges Polygon für den Fall dass polygonize fehlschlägt
                standalone_circles.append(Polygon(pts[:-1]))
        
        # Arcs
        for a in getattr(sketch, 'arcs', []):
            if not a.construction:
                # Arc-Winkel berechnen
                start_angle = getattr(a, 'start_angle', 0)
                end_angle = getattr(a, 'end_angle', 360)
                
                # Falls arc_size statt end_angle
                if hasattr(a, 'arc_size'):
                    end_angle = start_angle + a.arc_size
                
                # Normalisiere Winkel
                if end_angle < start_angle:
                    end_angle += 360
                    
                num_segments = max(32, int(abs(end_angle - start_angle) / 3))
                pts = []
                for i in range(num_segments + 1):
                    angle = math.radians(start_angle + (end_angle - start_angle) * i / num_segments)
                    pts.append((
                        rnd(a.center.x + a.radius * math.cos(angle)),
                        rnd(a.center.y + a.radius * math.sin(angle))
                    ))
                if len(pts) >= 2:
                    lines.append(LineString(pts))
        
        # Splines
        for s in getattr(sketch, 'splines', []):
            if not s.construction and hasattr(s, 'points') and len(s.points) >= 2:
                pts = [(rnd(p.x), rnd(p.y)) for p in s.points]
                lines.append(LineString(pts))
        
        # Polygons (falls vorhanden)
        for p in getattr(sketch, 'polygons', []):
            if not p.construction and hasattr(p, 'points') and len(p.points) >= 3:
                pts = [(rnd(pt.x), rnd(pt.y)) for pt in p.points]
                pts.append(pts[0])  # Schließen
                lines.append(LineString(pts))

        if not lines and not standalone_circles: 
            return

        # 2. Polygonize -> Findet alle geschlossenen Loops
        raw_polys = []
        try:
            if lines:
                merged = unary_union(lines)
                raw_polys = list(polygonize(merged))
        except Exception as e:
            logger.debug(f"Polygonize failed: {e}")
        
        # WICHTIG: Wenn polygonize keine Ergebnisse liefert aber wir eigenständige Kreise haben
        if not raw_polys and standalone_circles:
            raw_polys = standalone_circles
        elif standalone_circles:
            # Füge Kreise hinzu die nicht in raw_polys sind
            for circle in standalone_circles:
                already_found = False
                for poly in raw_polys:
                    # Prüfe ob der Kreis bereits als Polygon existiert (ähnliche Fläche)
                    if abs(poly.area - circle.area) < circle.area * 0.1:
                        already_found = True
                        break
                if not already_found:
                    raw_polys.append(circle)
        
        if not raw_polys:
            return

        # 3. Containment Analyse (Wer liegt in wem?)
        # Wir sortieren nach Fläche (groß zuerst), um Parents vor Children zu finden
        raw_polys.sort(key=lambda p: p.area, reverse=True)
        
        # Struktur: poly_info = { index: {'poly': p, 'children': [], 'parent': None} }
        poly_info = {i: {'poly': p, 'children': [], 'parent': None} for i, p in enumerate(raw_polys)}

        for i in range(len(raw_polys)):
            parent = raw_polys[i]
            for j in range(len(raw_polys)):
                if i == j: continue
                child = raw_polys[j]
                
                # Wenn Child im Parent liegt
                if parent.contains(child):
                    # Checken ob es ein direkter Parent ist (kein anderer Parent dazwischen)
                    # Wir weisen es erstmal zu, und verfeinern später oder nutzen einfache Logik:
                    # Da wir sortiert haben, ist der erste Container der größte.
                    # Bessere Logik: Das kleinste Polygon, das mich enthält, ist mein Parent.
                    pass

        # Einfachere, robuste Methode für "Hexagon mit Kreis":
        # Wir erzeugen SelectionFaces für die "Differenz".
        
        processed_indices = set()
        
        # A. Finde Polygone, die andere enthalten (Parents)
        for i, parent in enumerate(raw_polys):
            if i in processed_indices: continue
            
            # Suche direkte Löcher (Polygone die IN diesem Parent liegen)
            holes = []
            for j, child in enumerate(raw_polys):
                if i == j: continue
                # Ein echtes geometrisches Loch
                if parent.contains(child):
                    # Prüfen ob dieses Child nicht schon in einem Loch dieses Parents liegt (Nested Holes)
                    # Für einfache CAD-Fälle (Level 1 Nesting) reicht dies:
                    is_nested = False
                    for existing_hole in holes:
                        if existing_hole.contains(child):
                            is_nested = True; break
                    if not is_nested:
                        holes.append(child)

            # B. Erzeuge die "Ring"-Fläche (Parent minus alle direkten Holes)
            shell_poly = parent
            logger.debug(f"Parent Polygon {i}: area={parent.area:.1f}, holes_found={len(holes)}")
            
            for h in holes:
                logger.debug(f"  Subtrahiere Loch: area={h.area:.1f}")
                shell_poly = shell_poly.difference(h)
            
            # DEBUG: Prüfen ob Interiors erstellt wurden
            n_interiors = len(list(shell_poly.interiors)) if hasattr(shell_poly, 'interiors') else 0
            logger.info(f"  → Shell nach difference: area={shell_poly.area:.1f}, interiors={n_interiors}")
            
            if n_interiors > 0:
                for idx, interior in enumerate(shell_poly.interiors):
                    logger.debug(f"    Interior {idx}: {len(list(interior.coords))} Punkte")
            
            # Erzeuge SelectionFace für den Ring (Hexagon ohne Kreis)
            self.selection_faces.append(
                self._create_selection_face(
                    owner_id=sketch.id,
                    domain_type="sketch_profile", # Neu: Profile statt Shell
                    poly=shell_poly,
                    plane_origin=plane_origin,
                    plane_normal=plane_normal,
                    plane_x=plane_x_dir,
                    plane_y=plane_y_dir,
                    priority=10
                )
            )
            
            # C. Erzeuge SelectionFaces für die Löcher selbst (damit man den Kreis wieder füllen kann)
            # Das ist wichtig: Das Loch ist jetzt eine eigenständige, klickbare Fläche
            for h in holes:
                self.selection_faces.append(
                    self._create_selection_face(
                        owner_id=sketch.id,
                        domain_type="sketch_profile",
                        poly=h,
                        plane_origin=plane_origin,
                        plane_normal=plane_normal,
                        plane_x=plane_x_dir,
                        plane_y=plane_y_dir,
                        priority=20 # Höhere Prio für innere Teile
                    )
                )
                
            # Alle verarbeiteten markieren (eigentlich müssten wir holes markieren, aber 
            # durch die Logik oben werden Löcher auch als Parents geprüft. 
            # Da sie niemanden enthalten, fallen sie durch und werden im nächsten Loop als "Solid" erzeugt.
            # Um Duplikate zu vermeiden, müssen wir aufpassen.
            # FIX: Wenn wir Holes als Faces erzeugen, dürfen sie im Hauptloop nicht nochmal als Parent erzeugt werden?
            # Doch, wenn das Loch selbst wieder etwas enthält. 
            # Aber Shapely 'polygonize' liefert atomare Teile.
            # KORREKTUR: polygonize liefert NICHT atomare Teile bei Verschachtelung, es liefert "Filled" Polygons.
            
            # Daher: Wir müssen `holes` aus dem Hauptloop entfernen?
            # Nein, die einfache Logik ist: 
            # Wenn ein Polygon im Detector angelegt wird, ist es klickbar.
            # Wir haben oben Shell und Holes angelegt. 
            # Die Holes sind ja auch in `raw_polys`. Wenn der Loop bei einem Hole ankommt (als `parent`), 
            # findet er keine Kinder. Er würde das Hole nochmal als Shell anlegen. 
            # Das ist OK, solange wir Duplikate vermeiden.
            
            # Optimierung: Wir merken uns, welche `raw_polys` als Holes verwendet wurden
            # und überspringen diese im Hauptloop NICHT, sondern lassen sie durchlaufen,
            # ABER wir müssen verhindern, dass wir die Fläche doppelt addieren.
            
            # Da `shell_poly` (Ring) geometrisch neu ist, ist es ok.
            # Das `hole` (Kreis) ist identisch mit `raw_polys[j]`.
            
        # Um es simpel und stabil zu halten (Dein Wunsch):
        # Wir löschen die Faces vorher (in clear) und bauen sie hier auf.
        # Wir nutzen eine Hilfsliste, um Überlappung zu vermeiden.
        
        # RESET: Neue Logik, ganz sauber.
        # 1. Wir berechnen für jedes Polygon seinen "Level" der Verschachtelung.
        #    Level 0: Außen. Level 1: Im Außen (Loch). Level 2: Im Loch (Insel).
        # 2. Wir erzeugen Faces immer als (Poly - Direkte Kinder).
        
        pass # Der Code oben war "Denkprozess". Hier ist die Implementierung:
        
        # --- IMPLEMENTIERUNG ---
        self.selection_faces = [f for f in self.selection_faces if f.owner_id != sketch.id] # Alte löschen

        # Hierarchy Building
        # hierarchy[i] = [list of indices that are strictly inside i]
        hierarchy = {i: [] for i in range(len(raw_polys))}
        for i, p_out in enumerate(raw_polys):
            for j, p_in in enumerate(raw_polys):
                if i == j: continue
                if p_out.contains(p_in):
                    hierarchy[i].append(j)
        
        # Bestimme direkte Kinder (Direct Children)
        # Ein Kind K ist direktes Kind von P, wenn es keinen Zwischen-Parent Z gibt, der in P liegt und K enthält.
        direct_children = {i: [] for i in range(len(raw_polys))}
        
        for parent_idx, all_children in hierarchy.items():
            for child_idx in all_children:
                is_direct = True
                for other_child in all_children:
                    if child_idx == other_child: continue
                    if raw_polys[other_child].contains(raw_polys[child_idx]):
                        is_direct = False
                        break
                if is_direct:
                    direct_children[parent_idx].append(child_idx)

        # Nun erzeugen wir die "Ringe" (Profile)
        # Ein Profil ist immer: Polygon minus seine direkten Kinder.
        processed_indices = set()
        
        for i in range(len(raw_polys)):
            poly = raw_polys[i]
            children_indices = direct_children[i]
            
            # Subtrahiere alle direkten Kinder
            display_poly = poly
            for child_idx in children_indices:
                display_poly = display_poly.difference(raw_polys[child_idx])
            
            if not display_poly.is_empty and display_poly.area > 0.0001:
                self.selection_faces.append(
                    self._create_selection_face(
                        owner_id=sketch.id,
                        domain_type="sketch_profile",
                        poly=display_poly, # Das ist der Ring (oder der Kreis, wenn er keine Kinder hat)
                        plane_origin=plane_origin,
                        plane_normal=plane_normal,
                        plane_x=plane_x_dir,
                        plane_y=plane_y_dir,
                        priority=10 + len(children_indices) # Ringe bevorzugen
                    )
                )

    def _create_selection_face(self, owner_id, domain_type, poly, plane_origin, plane_normal, plane_x, plane_y, priority):
        # FIX: Hier fehlte die Weitergabe von plane_y an _shapely_to_pv_mesh
        display_mesh = self._shapely_to_pv_mesh(
            poly, 
            plane_origin, 
            plane_normal, 
            plane_x, 
            plane_y # <--- Neu übergeben
        )

        face = SelectionFace(
            id=self._counter,
            owner_id=owner_id,
            domain_type=domain_type,
            shapely_poly=poly,
            plane_origin=plane_origin,
            plane_normal=plane_normal,
            plane_x=plane_x,
            plane_y=plane_y,
            pick_priority=priority,
            display_mesh=display_mesh
        )
        self._counter += 1
        return face
    
    def pick(self, ray_origin, ray_dir, selection_filter=SelectionFilter.ALL):
        hits = []
        logger.debug(f"Pick Ray: {ray_origin} -> {ray_dir}")
        logger.debug(f"Active Filter: {selection_filter}")
        for face in self.selection_faces:
            if face.domain_type not in selection_filter:
                logger.debug(f"Ignoriere Face {face.id} ({face.domain_type}) wegen Filter")
                continue

            # Sketch-Faces → analytisch
            if face.domain_type.startswith("sketch"):
                hit = self._intersect_ray_plane(
                    ray_origin, ray_dir,
                    face.plane_origin,
                    face.plane_normal
                )
                if hit is None:
                    continue

                x, y = self._project_point_2d(
                    hit,
                    face.plane_origin,
                    face.plane_x,
                    face.plane_y
                )

                if face.shapely_poly.contains(Point(x, y)):
                    dist = np.linalg.norm(np.array(hit) - np.array(ray_origin))
                    hits.append((face.pick_priority, dist, face.id))

            # Body-Faces → Mesh-Ray
            elif face.domain_type == "body_face":
                mesh = face.display_mesh
                pts, _ = mesh.ray_trace(
                    ray_origin,
                    np.array(ray_origin) + np.array(ray_dir) * 10000
                )
                if len(pts) > 0:
                    dist = np.linalg.norm(pts[0] - ray_origin)
                    hits.append((face.pick_priority, dist, face.id))

        if not hits:
            return -1

        hits.sort(key=lambda h: (-h[0], h[1]))
        return hits[0][2]


    def _calculate_plane_axes(self, plane_normal):
        """
        Erzeugt ein stabiles, rechtshändiges Koordinatensystem
        (x_dir, y_dir) für eine Ebene mit gegebener Normalenrichtung.
        """

        n = np.array(plane_normal, dtype=float)
        n /= np.linalg.norm(n)

        # Wähle eine Hilfsachse, die nicht parallel zur Normalen ist
        if abs(n[2]) < 0.9:
            helper = np.array([0, 0, 1], dtype=float)
        else:
            helper = np.array([1, 0, 0], dtype=float)

        x_dir = np.cross(helper, n)
        x_len = np.linalg.norm(x_dir)
        if x_len < 1e-6:
            # Fallback (extremer Sonderfall)
            helper = np.array([0, 1, 0], dtype=float)
            x_dir = np.cross(helper, n)
            x_len = np.linalg.norm(x_dir)

        x_dir /= x_len
        y_dir = np.cross(n, x_dir)

        return tuple(x_dir), tuple(y_dir)

        
    def _intersect_ray_plane(self, ray_o, ray_d, plane_o, plane_n):
        ray_o = np.array(ray_o)
        ray_d = np.array(ray_d)
        plane_o = np.array(plane_o)
        plane_n = np.array(plane_n)

        denom = np.dot(plane_n, ray_d)
        if abs(denom) < 1e-6:
            return None

        t = np.dot(plane_o - ray_o, plane_n) / denom
        if t < 0:
            return None

        return ray_o + ray_d * t


    def _project_point_2d(self, pt, origin, x_dir, y_dir):
        v = np.array(pt) - np.array(origin)
        return np.dot(v, x_dir), np.dot(v, y_dir)
    
    
    

    def process_body_mesh(self, body_id, vtk_mesh, extrude_mode=False):
        """
        Zerlegt das Body-Mesh in planare Flächen.
        FIX: Bessere Normalen-Gruppierung für zylindrische Flächen

        Performance Optimization Phase 2.2: Dynamic Face-Pick-Priority
        Im Extrude-Mode bekommen Faces höhere Priorität für besseres Picking.

        Args:
            body_id: ID des Bodies
            vtk_mesh: PyVista Mesh
            extrude_mode: True wenn Viewport im Extrude-Mode ist (Default: False)
        """
        # Speichere extrude_mode für _add_body_face
        self._current_extrude_mode = extrude_mode
        if not HAS_VTK or vtk_mesh is None:
            return

        if not vtk_mesh.is_all_triangles:
            vtk_mesh = vtk_mesh.triangulate()

        if 'Normals' not in vtk_mesh.cell_data:
            vtk_mesh.compute_normals(cell_normals=True, inplace=True)

        # FIX: Gröbere Rundung (1 Dezimalstelle) für bessere Gruppierung
        # Das fasst Dreiecke mit ähnlicher Normale zusammen (z.B. Zylinder-Mantel)
        normals = np.round(vtk_mesh.cell_data['Normals'], 1)
        unique_normals, groups = np.unique(normals, axis=0, return_inverse=True)
        
        logger.debug(f"Body {body_id}: {len(unique_normals)} Normalen-Gruppen aus {vtk_mesh.n_cells} Dreiecken")

        for group_idx, normal in enumerate(unique_normals):
            cell_ids = np.where(groups == group_idx)[0]
            if len(cell_ids) < 1: continue

            # Sub-Mesh extrahieren
            group_mesh_ugrid = vtk_mesh.extract_cells(cell_ids)
            group_mesh = group_mesh_ugrid.extract_surface()

            try:
                # 2. Connectivity Check (Inseln trennen)
                conn = group_mesh.connectivity(extraction_mode='all')
                
                # FIX: Array direkt holen statt get_data_range()
                region_ids = None
                if 'RegionId' in conn.point_data:
                    region_ids = conn.point_data['RegionId']
                elif 'RegionId' in conn.cell_data:
                    region_ids = conn.cell_data['RegionId']
                
                if region_ids is None:
                    # Keine Regionen gefunden -> Alles ist eine Fläche
                    self._add_single_face(body_id, group_mesh, normal)
                    continue

                # Min/Max direkt aus den Daten holen
                min_id, max_id = region_ids.min(), region_ids.max()
                
                for i in range(int(min_id), int(max_id) + 1):
                    region = conn.threshold([i, i], scalars='RegionId')
                    region_surf = region.extract_surface()
                    
                    if region_surf.n_points < 3: continue
                    self._add_single_face(body_id, region_surf, normal)

            except Exception as e:
                # Fallback bei Fehler
                logger.warning(f"Connectivity Fallback: {e}")
                self._add_single_face(body_id, group_mesh, normal)

    def _add_single_face(self, body_id, mesh, normal):
        if mesh.n_points < 3: return
        center = np.mean(mesh.points, axis=0)
        
        # Triangulieren für sauberes Rendering/Bounds
        if not mesh.is_all_triangles:
            mesh = mesh.triangulate()
            
        self._add_body_face(body_id, center, normal, mesh)
    
    def _add_body_face(self, body_id, center, normal, mesh):
        # Performance Optimization Phase 2.2: Dynamic Priority
        # Im Extrude-Mode: Faces bekommen HÖCHSTE Priorität (50) für besseres Picking
        # Normal-Mode: Niedrige Priorität (5) damit Body-Mesh nicht stört
        extrude_mode = getattr(self, '_current_extrude_mode', False)
        face_priority = 50 if extrude_mode else 5

        face = SelectionFace(
            id=self._counter,
            owner_id=body_id,
            domain_type="body_face",
            plane_origin=tuple(center),
            plane_normal=tuple(normal),
            pick_priority=face_priority,  # DYNAMIC!
            display_mesh=mesh
        )
        self.selection_faces.append(face)
        self._counter += 1

    def detect_edges(self, body_id, vtk_mesh):
        """Erkennt Kanten für Fillet/Chamfer"""
        if vtk_mesh is None: return
        
        feature_edges = vtk_mesh.extract_feature_edges(feature_angle=30)
        
        # Auch hier: Connectivity, um einzelne Kanten-Loops zu finden
        conn = feature_edges.connectivity(extraction_mode='all')
        
        # Wir speichern das gesamte Edge-Mesh, aber segmentiert wäre besser
        # Vereinfacht:
        edge = DetectedEdge(
            id=self._counter,
            body_id=body_id,
            edge_type='feature',
            points=feature_edges.points.tolist(),
            vtk_cells=[]
        )
        self.edges.append(edge)
        self._counter += 1

    

    # --- Helper ---
    def _transform_2d_3d(self, x, y, origin, x_dir, y_dir):
        """
        Wandelt 2D (x,y) der Skizze in globale 3D Koordinaten um.
        FIX: Nutzt direkt die Basisvektoren ohne Neuberechnung.
        """
        ox, oy, oz = origin
        ux, uy, uz = x_dir
        vx, vy, vz = y_dir
        
        # P_global = Origin + x * BasisX + y * BasisY
        px = ox + x * ux + y * vx
        py = oy + x * uy + y * vy
        pz = oz + x * uz + y * vz
        
        return (px, py, pz)
    
    def _shapely_to_pv_mesh(self, poly, o, n, x_dir, plane_y_dir=None):
        """
        Erstellt ein PyVista Mesh aus einem Shapely Polygon.
        FIX: Mit Puffer-Logik, damit Kreise sauber erkannt werden.
        """
        if not HAS_VTK: return None
        
        # Vektoren vorbereiten
        import numpy as np
        
        if plane_y_dir is None:
             n_vec = np.array(n)
             x_vec = np.array(x_dir)
             y_vec = np.cross(n_vec, x_vec)
        else:
             x_vec = np.array(x_dir)
             y_vec = np.array(plane_y_dir)

        import shapely.ops
        try:
            # FIX 1: Polygon bereinigen (Selbstüberschneidungen reparieren)
            if not poly.is_valid:
                poly = poly.buffer(0)

            # Triangulierung im 2D Raum
            tris = shapely.ops.triangulate(poly)
            
            # FIX 2: Robustere Prüfung für Kreise/Rundungen
            # Wir nutzen einen minimalen Puffer (1e-5), um Rundungsfehler
            # an den Rändern abzufangen.
            buffered_poly = poly.buffer(1e-5)

            # FIX 3: Holes (Interior-Ringe) als Exclusion-Zonen
            # Dreiecke die im Hole liegen, müssen ausgeschlossen werden
            from shapely.geometry import Polygon as ShapelyPolygon
            hole_polys = []
            for interior in poly.interiors:
                hole_poly = ShapelyPolygon(interior).buffer(-1e-5)  # Leicht nach innen puffern
                if hole_poly.is_valid and not hole_poly.is_empty:
                    hole_polys.append(hole_poly)

            valid_tris = []
            for t in tris:
                centroid = t.centroid

                # Prüfen ob Zentroid in einem Hole liegt -> SKIP
                in_hole = False
                for hole in hole_polys:
                    if hole.contains(centroid):
                        in_hole = True
                        break

                if in_hole:
                    continue  # Dreieck liegt im Hole, nicht hinzufügen

                # Prüfen, ob der Schwerpunkt im (gepufferten) Polygon liegt
                if buffered_poly.contains(centroid):
                    valid_tris.append(t)
                # Fallback: Wenn Schwerpunkt knapp draußen, aber Dreieck schneidet
                # (Wichtig für schmale Randstücke bei Kreisen)
                elif buffered_poly.intersects(t):
                    valid_tris.append(t)
            
            # Notfall-Fallback: Wenn Filterung alles gelöscht hat (z.B. bei sehr kleinen Kreisen),
            # aber Dreiecke da waren, nehmen wir alle.
            if not valid_tris and len(tris) > 0 and poly.area > 0:
                 valid_tris = tris
            
            if not valid_tris:
                return None
            
            points = []
            faces = []
            c = 0
            
            for t in valid_tris:
                # 2D Koordinaten des Dreiecks holen
                xx, yy = t.exterior.coords.xy
                
                # Die ersten 3 Punkte des Dreiecks transformieren
                p1 = self._transform_2d_3d(xx[0], yy[0], o, x_vec, y_vec)
                p2 = self._transform_2d_3d(xx[1], yy[1], o, x_vec, y_vec)
                p3 = self._transform_2d_3d(xx[2], yy[2], o, x_vec, y_vec)
                
                points.extend([p1, p2, p3])
                # PyVista Face Format: [AnzahlPunkte, id1, id2, id3]
                faces.extend([3, c, c+1, c+2])
                c += 3
            
            # Mesh erstellen
            mesh = pv.PolyData(points, faces)
            return mesh

        except Exception as e:
            logger.error(f"Mesh generation error: {e}")
            return None
            
    def _shapely_to_pv_mesh_old(self, poly, o, n, x_dir, plane_y_dir=None): # <--- plane_y_dir hinzugefügt
        """
        Erstellt ein PyVista Mesh aus einem Shapely Polygon.
        FIX: Nutzt explizit übergebene X/Y Vektoren für exakte Deckungsgleichheit mit der Skizze.
        """
        if not HAS_VTK: return None
        
        # Vektoren vorbereiten
        import numpy as np
        
        # Wenn Y nicht übergeben wurde, berechnen (Fallback)
        if plane_y_dir is None:
             n_vec = np.array(n)
             x_vec = np.array(x_dir)
             y_vec = np.cross(n_vec, x_vec)
        else:
             x_vec = np.array(x_dir)
             y_vec = np.array(plane_y_dir) # <--- WICHTIG: Das übergebene Y nutzen!

        import shapely.ops
        try:
            # Triangulierung im 2D Raum
            tris = shapely.ops.triangulate(poly)
            # Nur Dreiecke behalten, die wirklich im Polygon liegen
            valid_tris = [t for t in tris if poly.contains(t.centroid)]
            
            if not valid_tris:
                return None
            
            points = []
            faces = []
            c = 0
            
            for t in valid_tris:
                # 2D Koordinaten des Dreiecks holen
                xx, yy = t.exterior.coords.xy
                
                # Die ersten 3 Punkte des Dreiecks transformieren
                # WICHTIG: Wir übergeben hier x_vec und y_vec explizit an _transform_2d_3d
                p1 = self._transform_2d_3d(xx[0], yy[0], o, x_vec, y_vec)
                p2 = self._transform_2d_3d(xx[1], yy[1], o, x_vec, y_vec)
                p3 = self._transform_2d_3d(xx[2], yy[2], o, x_vec, y_vec)
                
                points.extend([p1, p2, p3])
                # PyVista Face Format: [AnzahlPunkte, id1, id2, id3]
                faces.extend([3, c, c+1, c+2])
                c += 3
            
            # Mesh erstellen
            mesh = pv.PolyData(points, faces)
            return mesh
        except Exception as e:
            logger.error(f"Mesh generation error: {e}")
            return None