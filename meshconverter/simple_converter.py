"""
SimpleConverter - Baseline Mesh-to-BREP Converter
===================================================

Einfachster, immer zuverlässiger Mesh-to-BREP Konverter.

Strategie: 1:1 Mapping
- Jedes Mesh-Dreieck wird zu einem planaren BREP Face
- Edge-sharing garantiert watertightes Ergebnis
- Keine Heuristik, die fehlschlagen kann

Vorteile:
+ Immer zuverlässig (100% Reproduzierbarkeit)
+ Vorhersagbare Performance
+ Minimale Abhängigkeiten

Nachteile:
- Facettierte Oberfläche (keine glatten Kurven)
- Grössere Dateigröße
- Zylinder sind facettiert (nicht glatt)

Author: Claude (MeshConverter Architecture)
Date: 2026-02-10
"""

import numpy as np
from typing import Optional, List, Dict, Tuple
from loguru import logger

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
    from OCP.TopAbs import TopAbs_REVERSED, TopAbs_FACE, TopAbs_SHELL, TopAbs_COMPOUND
    from OCP.TopExp import TopExp_Explorer
    HAS_OCP = True
except ImportError:
    HAS_OCP = False
    logger.warning("OCP nicht verfügbar")

try:
    from build123d import Solid
    HAS_BUILD123D = True
except ImportError:
    HAS_BUILD123D = False
    Solid = None

from meshconverter.base import (
    AsyncMeshConverter,
    ConversionResult,
    ConversionStatus,
    ConversionPhase,
    ProgressUpdate
)


class SimpleConverter(AsyncMeshConverter):
    """
    Einfachster Mesh-to-BREP Konverter mit Progress Reporting.

    Strategie: 1:1 Mapping
    - Jedes Dreieck → Ein planares BREP Face
    - Edge-Sharing für watertight Ergebnis
    - Keine Segmentierung oder Primitive-Erkennung

    Usage:
        converter = SimpleConverter()

        def on_progress(update: ProgressUpdate):
            print(f"[{update.phase.value}] {update.progress*100:.0f}% - {update.message}")

        result = converter.convert_async(mesh, on_progress)
    """

    def __init__(
        self,
        sewing_tolerance: float = 1e-6,
        unify_faces: bool = False,
        unify_linear_tol: float = 0.5,
        unify_angular_tol: float = 1.0
    ):
        super().__init__(name="SimpleConverter")
        self.sewing_tol = sewing_tolerance
        self.unify_faces = unify_faces
        self.unify_linear_tol = unify_linear_tol
        self.unify_angular_tol = np.radians(unify_angular_tol)

    def convert_async(
        self,
        mesh: 'pv.PolyData',
        progress_callback: Optional[callable] = None
    ) -> ConversionResult:
        """
        Asynchrone Konvertierung mit Progress Updates.

        Args:
            mesh: PyVista PolyData (muss trianguliert sein)
            progress_callback: Optionale Callback-Funktion

        Returns:
            ConversionResult mit dem erstellten BREP Solid
        """
        if not HAS_OCP:
            return ConversionResult(
                success=False,
                status=ConversionStatus.FAILED,
                message="OCP nicht verfügbar"
            )

        if not HAS_PYVISTA:
            return ConversionResult(
                success=False,
                status=ConversionStatus.FAILED,
                message="PyVista nicht verfügbar"
            )

        if not self._validate_mesh(mesh):
            return ConversionResult(
                success=False,
                status=ConversionStatus.FAILED,
                message="Ungültiges Mesh"
            )

        logger.info(f"SimpleConverter: {mesh.n_points} Punkte, {mesh.n_cells} Faces")

        try:
            # Phase 1: Vertex Pool (0-20%)
            self._emit_progress(
                ConversionPhase.BUILDING, 0.1,
                "Erstelle Vertex Pool...",
                callback=progress_callback
            )
            vertices = self._create_vertex_pool(mesh)

            # Phase 2: Faces mit on-demand Edge-Erstellung (20-80%)
            # Wir erstellen Edges on-demand, um PyVista Grid-Probleme zu vermeiden
            edge_map = {}  # Wird während Face-Erstellung gefüllt

            self._emit_progress(
                ConversionPhase.BUILDING, 0.3,
                f"Erstelle {mesh.n_cells} Faces...",
                callback=progress_callback
            )
            faces = self._create_triangle_faces_simple(mesh, vertices, edge_map, progress_callback)

            if len(faces) == 0:
                return ConversionResult(
                    success=False,
                    status=ConversionStatus.FAILED,
                    message="Keine Faces erstellt"
                )

            # Phase 3: Sewing (80-95%)
            self._emit_progress(
                ConversionPhase.SEWING, 0.85,
                "Sewing Faces...",
                callback=progress_callback
            )
            result = self._sew_and_make_solid(faces)

            # Phase 4: Complete (100%)
            self._emit_progress(
                ConversionPhase.COMPLETE, 1.0,
                "Fertig!",
                f"{result.face_count} Faces",
                callback=progress_callback
            )

            return result

        except Exception as e:
            logger.error(f"SimpleConverter fehlgeschlagen: {e}")
            import traceback
            traceback.print_exc()
            return ConversionResult(
                success=False,
                status=ConversionStatus.FAILED,
                message=f"Fehler: {e}",
                error=e
            )

    def _create_vertex_pool(self, mesh: 'pv.PolyData') -> List['gp_Pnt']:
        """Erstellt OCP Punkte aus Mesh-Vertices."""
        points = mesh.points
        vertices = []

        for i in range(mesh.n_points):
            pnt = gp_Pnt(points[i][0], points[i][1], points[i][2])
            vertices.append(pnt)

        return vertices

    def _create_triangle_faces_simple(
        self,
        mesh: 'pv.PolyData',
        vertices: List['gp_Pnt'],
        edge_map: dict,
        progress_callback: Optional[callable] = None
    ) -> List['TopoDS_Face']:
        """
        Erstellt BREP Faces aus Mesh-Dreiecken mit on-demand Edge-Erstellung.

        Args:
            mesh: PyVista PolyData
            vertices: Vertex Pool
            edge_map: Wird während Face-Erstellung gefüllt
            progress_callback: Optional für Progress Updates

        Returns:
            Liste von TopoDS_Face
        """
        faces = []

        # PyVista STL Faces Format: [3, v0, v1, v2, 3, v0, v1, v2, ...]
        faces_arr = mesh.faces.reshape(-1, 4)  # (n_cells, 4)
        total = faces_arr.shape[0]
        last_progress = 0.3

        for i in range(total):
            # Update Progress
            progress = 0.3 + 0.5 * (i / total)
            if progress - last_progress > 0.05:
                self._emit_progress(
                    ConversionPhase.BUILDING, progress,
                    f"Erstelle Faces...",
                    f"{i}/{total}",
                    callback=progress_callback
                )
                last_progress = progress

            # Hole Vertex IDs: [n_verts, v0, v1, v2]
            row = faces_arr[i]
            n_verts = int(row[0])

            if n_verts != 3:
                continue  # Nur Dreiecke unterstützen

            v0 = int(row[1])
            v1 = int(row[2])
            v2 = int(row[3])

            # Erstelle 3 Edges
            wire_builder = BRepBuilderAPI_MakeWire()

            for (v_a, v_b) in [(v0, v1), (v1, v2), (v2, v0)]:
                # Sortiere für konsistenten Key
                v_key = tuple(sorted([v_a, v_b]))

                if v_key not in edge_map:
                    # Erstelle neue Edge
                    p1 = vertices[v_a]
                    p2 = vertices[v_b]
                    edge_builder = BRepBuilderAPI_MakeEdge(p1, p2)
                    if not edge_builder.IsDone():
                        continue
                    edge = edge_builder.Edge()
                    edge_map[v_key] = edge
                else:
                    edge = edge_map[v_key]

                wire_builder.Add(edge)

            if not wire_builder.IsDone():
                continue

            wire = wire_builder.Wire()

            # Erstelle planares Face
            face_builder = BRepBuilderAPI_MakeFace(wire)
            if not face_builder.IsDone():
                continue

            face = face_builder.Face()
            faces.append(face)

        return faces

    def _sew_and_make_solid(
        self,
        faces: List['TopoDS_Face']
    ) -> ConversionResult:
        """
        Sewing und Solid-Erstellung.

        Args:
            faces: Liste von TopoDS_Face

        Returns:
            ConversionResult mit erstelltem Solid
        """
        # Sewing
        sewing = BRepBuilderAPI_Sewing()
        for face in faces:
            sewing.Add(face)

        sewing.Perform()

        # SewedShape holen (Load ist deprecated/entfernt in neueren OCP)
        shape = sewing.SewedShape()

        if self.unify_faces:
            # Optional: UnifySameDomain für Face-Merging
            unify = ShapeUpgrade_UnifySameDomain(
                shape,
                self.unify_linear_tol,
                self.unify_angular_tol
            )
            unify.AllowInternalEdges(False)
            unify.Build()
            shape = unify.Shape()

        # Validierung
        analyzer = BRepCheck_Analyzer(shape)
        if not analyzer.IsValid():
            logger.warning("Shape ist nicht valid!")

        # Ergebnis: Prüfe ob wir ein gültiges BREP haben (Solid oder Shell)
        # Shell ist auch erfolgreich - es kann immer noch zu Solid konvertiert werden
        try:
            if shape.ShapeType() == TopoDS_Solid:
                solid = Solid(shape)
                status = ConversionStatus.SUCCESS
            elif shape.ShapeType() == TopoDS_Shell:
                # Shell ist OK - kann später zu Solid konvertiert werden
                # Für den Moment geben wir SHELL_ONLY zurück
                solid = None  # build123d Solid kann nicht aus Shell erstellt werden
                status = ConversionStatus.SHELL_ONLY
            else:
                # Compound oder etwas anderes
                solid = None
                status = ConversionStatus.SHELL_ONLY
        except Exception as e:
            logger.warning(f"Konnte keinen Solid erstellen: {e}")
            solid = None
            status = ConversionStatus.SHELL_ONLY

        # Face-Count
        face_count = 0
        explorer = TopExp_Explorer(shape, TopAbs_FACE)
        while explorer.More():
            face_count += 1
            explorer.Next()

        return ConversionResult(
            success=solid is not None,
            solid=solid,
            status=ConversionStatus.SUCCESS if solid else ConversionStatus.SHELL_ONLY,
            message=f"SimpleConverter: {face_count} Faces erstellt",
            face_count=face_count
        )


def convert_simple(mesh: 'pv.PolyData', progress_callback=None) -> ConversionResult:
    """
    Convenience Funktion für SimpleConverter.

    Args:
        mesh: PyVista PolyData
        progress_callback: Optionale Progress-Callback

    Returns:
        ConversionResult
    """
    converter = SimpleConverter()
    return converter.convert_async(mesh, progress_callback)


if __name__ == "__main__":
    # Test
    import pyvista as pv

    # Einfacher Test-Würfel
    cube = pv.Cube().triangulate()
    print(f"Test Mesh: {cube.n_points} Punkte, {cube.n_cells} Faces")

    converter = SimpleConverter()

    def on_progress(update):
        print(f"[{update.phase.value}] {update.progress*100:.0f}% - {update.message}")

    result = converter.convert_async(cube, on_progress)

    print(f"\nResult: {result.status.value}")
    print(f"Face-Count: {result.face_count}")
    if result.solid:
        print(f"Solid: {result.solid}")
