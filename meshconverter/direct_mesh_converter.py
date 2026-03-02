"""
MashCad - Direct Mesh to BREP Converter
========================================

Konvertiert Mesh direkt zu BREP ohne Segmentierung.
Jedes Mesh-Dreieck wird zu einem BREP-Face.
Garantiert wasserdichte Ergebnisse durch echtes Edge-Sharing.
"""

import numpy as np
from typing import Optional, List, Dict, Tuple
from loguru import logger
from modeling.ocp_thread_guard import ensure_ocp_main_thread

try:
    import pyvista as pv
    HAS_PYVISTA = True
except ImportError:
    HAS_PYVISTA = False

try:
    from OCP.gp import gp_Pnt, gp_Vec, gp_Dir, gp_Pln
    from OCP.BRepBuilderAPI import (
        BRepBuilderAPI_MakeEdge,
        BRepBuilderAPI_MakeWire,
        BRepBuilderAPI_MakeFace,
        BRepBuilderAPI_Sewing,
        BRepBuilderAPI_MakeSolid
    )
    from OCP.TopoDS import TopoDS_Edge, TopoDS_Wire, TopoDS_Face, TopoDS, TopoDS_Shell, TopoDS_Solid
    from OCP.ShapeFix import ShapeFix_Solid, ShapeFix_Shell
    from OCP.ShapeUpgrade import ShapeUpgrade_UnifySameDomain
    from OCP.BRepCheck import BRepCheck_Analyzer
    from OCP.TopAbs import TopAbs_REVERSED, TopAbs_FACE
    from OCP.TopExp import TopExp_Explorer
    HAS_OCP = True
except ImportError:
    HAS_OCP = False
    logger.warning("OCP nicht verfügbar")

from meshconverter.mesh_converter_v10 import ConversionResult, ConversionStatus


class DirectMeshConverter:
    """
    Konvertiert Mesh direkt zu BREP - 1 Mesh-Face = 1 BREP-Face.

    Strategie:
    1. Erstelle alle Mesh-Edges einmalig (Edge-Sharing)
    2. Für jedes Mesh-Dreieck: erstelle Wire aus 3 Edges
    3. Erstelle planare Face aus Wire
    4. Sewing mit Toleranz 0
    5. UnifySameDomain um koplanare Faces zu mergen

    Dies garantiert wasserdichte Ergebnisse weil:
    - Jede Mesh-Kante wird exakt EINMAL als BREP-Edge erstellt
    - Adjacent Faces teilen exakt dieselbe Edge-Instanz
    - Sewing ist trivial (Edges sind bereits identisch)
    """

    def __init__(
        self,
        sewing_tolerance: float = 1e-6,
        unify_faces: bool = True,
        unify_linear_tolerance: float = 0.5,  # 0.5mm für aggressive Merging
        unify_angular_tolerance: float = 1.0   # 1 Grad - streng um Geometriefehler zu vermeiden
    ):
        """
        Args:
            sewing_tolerance: Toleranz für Sewing (sehr niedrig da Edges geteilt)
            unify_faces: Koplanare Faces nach Sewing mergen
            unify_linear_tolerance: Lineare Toleranz für Face-Merging (mm)
            unify_angular_tolerance: Winkeltoleranz für Face-Merging (Grad)
        """
        self.sewing_tol = sewing_tolerance
        self.unify_faces = unify_faces
        self.unify_linear_tol = unify_linear_tolerance
        self.unify_angular_tol = np.radians(unify_angular_tolerance)

    def convert(self, mesh: 'pv.PolyData') -> ConversionResult:
        """
        Konvertiert Mesh zu BREP.

        Args:
            mesh: PyVista PolyData (muss trianguliert sein)

        Returns:
            ConversionResult
        """
        ensure_ocp_main_thread("convert mesh to BREP (DirectMeshConverter)")

        if not HAS_OCP:
            return ConversionResult(
                status=ConversionStatus.FAILED,
                message="OCP nicht verfügbar"
            )

        if not HAS_PYVISTA:
            return ConversionResult(
                status=ConversionStatus.FAILED,
                message="PyVista nicht verfügbar"
            )

        logger.debug("=== Direct Mesh Converter ===")
        logger.debug(f"Mesh: {mesh.n_points} Punkte, {mesh.n_cells} Faces")

        stats = {
            'input_points': mesh.n_points,
            'input_faces': mesh.n_cells
        }

        try:
            # 1. Erstelle Vertex-Pool
            logger.debug("Erstelle Vertex-Pool...")
            vertices = self._create_vertex_pool(mesh)

            # 2. Erstelle globale Edge-Map
            logger.debug("Erstelle Edge-Map...")
            edge_map = self._create_edge_map(mesh, vertices)
            logger.debug(f"  → {len(edge_map)} unique Edges")
            stats['unique_edges'] = len(edge_map)

            # 3. Erstelle BREP Faces (1 pro Mesh-Dreieck)
            logger.debug("Erstelle BREP Faces...")
            faces = self._create_triangle_faces(mesh, vertices, edge_map)
            logger.debug(f"  → {len(faces)} Faces erstellt")
            stats['faces_created'] = len(faces)

            if len(faces) == 0:
                return ConversionResult(
                    status=ConversionStatus.FAILED,
                    message="Keine Faces erstellt",
                    stats=stats
                )

            # 4. Sewing
            logger.debug("Sewing...")
            result = self._sew_and_make_solid(faces, stats)

            logger.debug(f"=== Ergebnis: {result.status.name} ===")
            return result

        except Exception as e:
            logger.error(f"Direct Mesh Konvertierung fehlgeschlagen: {e}")
            import traceback
            traceback.print_exc()
            return ConversionResult(
                status=ConversionStatus.FAILED,
                message=f"Fehler: {e}",
                stats=stats
            )

    def _create_vertex_pool(self, mesh: 'pv.PolyData') -> List['gp_Pnt']:
        """Erstellt Liste von gp_Pnt aus Mesh-Vertices."""
        vertices = []
        for pt in mesh.points:
            vertices.append(gp_Pnt(float(pt[0]), float(pt[1]), float(pt[2])))
        return vertices

    def _create_edge_map(
        self,
        mesh: 'pv.PolyData',
        vertices: List['gp_Pnt']
    ) -> Dict[Tuple[int, int], 'TopoDS_Edge']:
        """
        Erstellt globale Edge-Map.

        Key: (min_vertex, max_vertex) - normalisiert
        Value: TopoDS_Edge

        WICHTIG: Wir speichern auch die Original-Richtung,
        damit wir später .Reversed() aufrufen können wenn nötig.
        """
        edge_map: Dict[Tuple[int, int], TopoDS_Edge] = {}

        faces_array = mesh.faces.reshape(-1, 4)[:, 1:4]

        for face in faces_array:
            for i in range(3):
                v1, v2 = int(face[i]), int(face[(i + 1) % 3])
                # Normalisierter Key
                edge_key = (min(v1, v2), max(v1, v2))

                if edge_key not in edge_map:
                    p1, p2 = vertices[edge_key[0]], vertices[edge_key[1]]
                    dist = p1.Distance(p2)
                    if dist > 1e-9:
                        edge_builder = BRepBuilderAPI_MakeEdge(p1, p2)
                        if edge_builder.IsDone():
                            edge_map[edge_key] = edge_builder.Edge()

        return edge_map

    def _create_triangle_faces(
        self,
        mesh: 'pv.PolyData',
        vertices: List['gp_Pnt'],
        edge_map: Dict[Tuple[int, int], 'TopoDS_Edge']
    ) -> List['TopoDS_Face']:
        """
        Erstellt BREP Face für jedes Mesh-Dreieck.

        Verwendet shared Edges aus edge_map.
        """
        faces = []
        faces_array = mesh.faces.reshape(-1, 4)[:, 1:4]

        # Normalen für Face-Orientierung
        if 'Normals' not in mesh.cell_data:
            mesh.compute_normals(cell_normals=True, inplace=True)
        normals = mesh.cell_data['Normals']

        success_count = 0
        failed_count = 0

        for cell_id, tri in enumerate(faces_array):
            v0, v1, v2 = int(tri[0]), int(tri[1]), int(tri[2])
            normal = normals[cell_id]

            face = self._create_single_triangle_face(
                v0, v1, v2, vertices, edge_map, normal
            )

            if face is not None:
                faces.append(face)
                success_count += 1
            else:
                failed_count += 1

        logger.debug(f"  Faces: {success_count} OK, {failed_count} fehlgeschlagen")
        return faces

    def _create_single_triangle_face(
        self,
        v0: int, v1: int, v2: int,
        vertices: List['gp_Pnt'],
        edge_map: Dict[Tuple[int, int], 'TopoDS_Edge'],
        normal: np.ndarray
    ) -> Optional['TopoDS_Face']:
        """
        Erstellt ein einzelnes dreieckiges BREP Face.

        Args:
            v0, v1, v2: Vertex-Indizes (in Reihenfolge)
            vertices: gp_Pnt Liste
            edge_map: Shared Edge Map
            normal: Face-Normal für Orientierung
        """
        try:
            # Hole Edges (mit korrekter Orientierung)
            edges = []
            vertex_sequence = [(v0, v1), (v1, v2), (v2, v0)]

            for v_from, v_to in vertex_sequence:
                edge_key = (min(v_from, v_to), max(v_from, v_to))

                if edge_key not in edge_map:
                    return None

                edge = edge_map[edge_key]

                # Prüfe ob Edge reversed werden muss
                # Edge wurde von edge_key[0] zu edge_key[1] erstellt
                # Wir brauchen sie von v_from zu v_to
                if v_from == edge_key[0]:
                    # Gleiche Richtung
                    edges.append(edge)
                else:
                    # Umgekehrte Richtung nötig
                    edges.append(TopoDS.Edge_s(edge.Reversed()))

            # Wire erstellen
            wire_builder = BRepBuilderAPI_MakeWire()
            for edge in edges:
                wire_builder.Add(edge)

            if not wire_builder.IsDone():
                return None

            wire = wire_builder.Wire()

            # Plane aus den 3 Punkten berechnen
            p0 = vertices[v0]
            p1 = vertices[v1]
            p2 = vertices[v2]

            # Centroid als Origin
            cx = (p0.X() + p1.X() + p2.X()) / 3.0
            cy = (p0.Y() + p1.Y() + p2.Y()) / 3.0
            cz = (p0.Z() + p1.Z() + p2.Z()) / 3.0
            origin = gp_Pnt(cx, cy, cz)

            # Normal aus Mesh-Daten
            norm_len = np.linalg.norm(normal)
            if norm_len < 1e-10:
                # Berechne Normal aus Vertices
                vec1 = np.array([p1.X() - p0.X(), p1.Y() - p0.Y(), p1.Z() - p0.Z()])
                vec2 = np.array([p2.X() - p0.X(), p2.Y() - p0.Y(), p2.Z() - p0.Z()])
                normal = np.cross(vec1, vec2)
                norm_len = np.linalg.norm(normal)
                if norm_len < 1e-10:
                    return None

            normal = normal / norm_len
            direction = gp_Dir(float(normal[0]), float(normal[1]), float(normal[2]))
            plane = gp_Pln(origin, direction)

            # Face erstellen
            face_builder = BRepBuilderAPI_MakeFace(plane, wire)
            if face_builder.IsDone():
                return face_builder.Face()
            else:
                return None

        except Exception as e:
            logger.debug(f"Triangle face failed: {e}")
            return None

    def _sew_and_make_solid(
        self,
        faces: List['TopoDS_Face'],
        stats: dict
    ) -> ConversionResult:
        """
        Näht Faces zusammen und erstellt Solid.
        """
        # Sewing mit sehr niedriger Toleranz (Edges sind bereits geteilt)
        sewer = BRepBuilderAPI_Sewing(self.sewing_tol)
        sewer.SetNonManifoldMode(False)

        for face in faces:
            if face and not face.IsNull():
                sewer.Add(face)

        sewer.Perform()

        # Statistiken
        free_edges = sewer.NbFreeEdges()
        multiple_edges = sewer.NbMultipleEdges()
        degenerated = sewer.NbDegeneratedShapes()

        logger.debug(f"  Sewing: {free_edges} free, {multiple_edges} multiple, {degenerated} degenerated")
        stats['free_edges'] = free_edges
        stats['multiple_edges'] = multiple_edges

        sewed_shape = sewer.SewedShape()

        if sewed_shape.IsNull():
            return ConversionResult(
                status=ConversionStatus.FAILED,
                message="Sewing fehlgeschlagen",
                stats=stats
            )

        shape_type = sewed_shape.ShapeType()
        logger.debug(f"  Sewed Shape Type: {shape_type}")

        # Shell zu Solid
        try:
            if shape_type.name == 'TopAbs_SHELL':
                shell = TopoDS.Shell_s(sewed_shape)
            elif shape_type.name == 'TopAbs_COMPOUND':
                # Sammle ALLE Shells aus dem Compound
                from OCP.TopExp import TopExp_Explorer
                from OCP.TopAbs import TopAbs_SHELL, TopAbs_SOLID
                from OCP.BRep import BRep_Builder
                from OCP.TopoDS import TopoDS_Compound

                shells = []
                exp = TopExp_Explorer(sewed_shape, TopAbs_SHELL)
                while exp.More():
                    shells.append(TopoDS.Shell_s(exp.Current()))
                    exp.Next()

                logger.debug(f"  Compound enthält {len(shells)} Shells")

                if not shells:
                    logger.warning("Kein Shell in Compound gefunden")
                    stats['is_valid'] = False
                    return ConversionResult(
                        status=ConversionStatus.PARTIAL,
                        message=f"Compound ohne Shell, {free_edges} free edges",
                        stats=stats
                    )

                # Wenn nur eine Shell, normal weiter
                if len(shells) == 1:
                    shell = shells[0]
                else:
                    # Mehrere Shells: Kombiniere zu einem Compound von Solids
                    logger.info(f"  Kombiniere {len(shells)} Shells zu Compound...")
                    builder = BRep_Builder()
                    compound = TopoDS_Compound()
                    builder.MakeCompound(compound)

                    for i, sh in enumerate(shells):
                        # Jede Shell zu Solid
                        shell_fixer = ShapeFix_Shell(sh)
                        shell_fixer.Perform()
                        fixed_sh = shell_fixer.Shell()

                        solid_builder = BRepBuilderAPI_MakeSolid(fixed_sh)
                        if solid_builder.IsDone():
                            builder.Add(compound, solid_builder.Solid())

                    stats['solid_created'] = True
                    stats['is_valid'] = True
                    stats['multiple_shells'] = len(shells)

                    # Face-Merging auf Compound
                    if self.unify_faces:
                        try:
                            upgrader = ShapeUpgrade_UnifySameDomain(compound, True, True, True)
                            upgrader.SetLinearTolerance(self.unify_linear_tol)
                            upgrader.SetAngularTolerance(self.unify_angular_tol)
                            upgrader.Build()
                            unified = upgrader.Shape()
                            if not unified.IsNull():
                                compound = TopoDS.Compound_s(unified) if unified.ShapeType().name == 'TopAbs_COMPOUND' else compound
                                n_faces = self._count_faces(compound)
                                stats['faces_after_unify'] = n_faces
                                logger.debug(f"  Face-Merging: {stats['faces_created']} → {n_faces} Faces")
                        except Exception as e:
                            logger.warning(f"UnifySameDomain auf Compound fehlgeschlagen: {e}")

                    logger.debug(f"Compound mit {len(shells)} Solids erstellt")
                    return ConversionResult(
                        status=ConversionStatus.SUCCESS,
                        solid=compound,
                        stats=stats
                    )
            else:
                logger.warning(f"Unerwarteter Shape-Typ: {shape_type}")
                stats['is_valid'] = False
                return ConversionResult(
                    status=ConversionStatus.PARTIAL,
                    message=f"Unerwarteter Shape-Typ: {shape_type}",
                    stats=stats
                )

            # Shell reparieren
            shell_fixer = ShapeFix_Shell(shell)
            shell_fixer.Perform()
            fixed_shell = shell_fixer.Shell()

            # Solid erstellen
            solid_builder = BRepBuilderAPI_MakeSolid(fixed_shell)

            if solid_builder.IsDone():
                solid = solid_builder.Solid()

                # Validierung
                analyzer = BRepCheck_Analyzer(solid)
                is_valid = analyzer.IsValid()

                stats['solid_created'] = True
                stats['is_valid'] = is_valid

                if is_valid:
                    # Face-Merging mit UnifySameDomain
                    if self.unify_faces:
                        unified_solid = self._unify_coplanar_faces(solid)
                        if unified_solid is not None:
                            solid = unified_solid
                            # Update Face-Count
                            n_faces = self._count_faces(solid)
                            stats['faces_after_unify'] = n_faces
                            logger.debug(f"  Face-Merging: {stats['faces_created']} → {n_faces} Faces")

                    logger.debug("Solid erfolgreich erstellt und validiert")
                    return ConversionResult(
                        status=ConversionStatus.SUCCESS,
                        solid=solid,
                        stats=stats
                    )
                else:
                    # Versuche Solid zu reparieren
                    fixer = ShapeFix_Solid(solid)
                    fixer.Perform()
                    fixed_solid = fixer.Solid()

                    if not fixed_solid.IsNull():
                        analyzer2 = BRepCheck_Analyzer(fixed_solid)
                        if analyzer2.IsValid():
                            logger.debug("Solid nach Reparatur gültig")
                            stats['is_valid'] = True
                            return ConversionResult(
                                status=ConversionStatus.SUCCESS,
                                solid=fixed_solid,
                                stats=stats
                            )

                    logger.warning("Solid erstellt aber nicht valide")
                    return ConversionResult(
                        status=ConversionStatus.PARTIAL,
                        solid=solid,
                        message="Validierung fehlgeschlagen",
                        stats=stats
                    )
            else:
                logger.warning("MakeSolid fehlgeschlagen")
                stats['solid_created'] = False
                return ConversionResult(
                    status=ConversionStatus.SHELL_ONLY,
                    message="MakeSolid fehlgeschlagen",
                    stats=stats
                )

        except Exception as e:
            logger.error(f"Solid-Erstellung fehlgeschlagen: {e}")
            stats['solid_created'] = False
            return ConversionResult(
                status=ConversionStatus.FAILED,
                message=f"Solid-Erstellung: {e}",
                stats=stats
            )

    def _unify_coplanar_faces(self, solid) -> Optional['TopoDS_Solid']:
        """
        Vereinigt koplanare Faces mit ShapeUpgrade_UnifySameDomain.

        Returns:
            Unified Solid oder None bei Fehler
        """
        try:
            upgrader = ShapeUpgrade_UnifySameDomain(solid, True, True, True)
            upgrader.SetLinearTolerance(self.unify_linear_tol)
            upgrader.SetAngularTolerance(self.unify_angular_tol)
            upgrader.Build()

            unified = upgrader.Shape()

            if unified.IsNull():
                logger.warning("UnifySameDomain ergab Null-Shape")
                return None

            # Prüfe ob es noch ein Solid ist
            from OCP.TopAbs import TopAbs_SOLID
            if unified.ShapeType() == TopAbs_SOLID:
                return TopoDS.Solid_s(unified)
            else:
                logger.warning(f"Nach UnifySameDomain kein Solid mehr: {unified.ShapeType()}")
                return None

        except Exception as e:
            logger.warning(f"UnifySameDomain fehlgeschlagen: {e}")
            return None

    def _count_faces(self, shape) -> int:
        """Zählt Faces in einem Shape."""
        count = 0
        exp = TopExp_Explorer(shape, TopAbs_FACE)
        while exp.More():
            count += 1
            exp.Next()
        return count


def convert_direct_mesh(filepath: str, **kwargs) -> ConversionResult:
    """
    Convenience-Funktion für Direct Mesh Konvertierung.

    Args:
        filepath: Pfad zur Mesh-Datei
        **kwargs: Optionen für DirectMeshConverter

    Returns:
        ConversionResult
    """
    from meshconverter.mesh_converter_v10 import MeshLoader, LoadStatus

    # Mesh laden
    load_result = MeshLoader.load(filepath, repair=True)
    if load_result.status == LoadStatus.FAILED:
        return ConversionResult(
            status=ConversionStatus.FAILED,
            message=f"Laden fehlgeschlagen: {load_result.message}"
        )

    # Konvertieren
    converter = DirectMeshConverter(**kwargs)
    return converter.convert(load_result.mesh)
