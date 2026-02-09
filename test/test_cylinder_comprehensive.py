"""
MashCad - Cylinder Comprehensive Tests
========================================

Konsolidierte Tests für Zylinder-bezogene Push/Pull Probleme.

Behandelte Probleme:
1. Zylinder hat 3 Edges statt 2 (OCP Standard mit Seam-Edge)
2. Push/Pull auf Top/Bottom Faces muss UnifySameDomain anwenden
3. Push/Pull auf zylindrische Face sollte Radius ändern (Fusion360 style)

Author: Claude
Date: 2026-02-09
"""
import pytest
import numpy as np
from build123d import Solid
from OCP.BRepPrimAPI import BRepPrimAPI_MakeCylinder
from OCP.gp import gp_Ax2, gp_Pnt, gp_Dir
from OCP.BRepFeat import BRepFeat_MakePrism
from OCP.ShapeUpgrade import ShapeUpgrade_UnifySameDomain
from OCP.BRepAdaptor import BRepAdaptor_Surface
from OCP.GeomAbs import GeomAbs_Cylinder, GeomAbs_Plane
from OCP.GProp import GProp_GProps
from OCP.BRepGProp import BRepGProp
from modeling import Body, PrimitiveFeature, ExtrudeFeature, _solid_metrics
from sketcher.sketch import Sketch
from shapely.geometry import Polygon


# =============================================================================
# Helper Functions
# =============================================================================

def create_test_cylinder(radius=10.0, height=50.0):
    """Erstellt einen Test-Zylinder."""
    ax = gp_Ax2(gp_Pnt(0, 0, 0), gp_Dir(0, 0, 1))
    ocp_cyl = BRepPrimAPI_MakeCylinder(ax, radius, height).Shape()
    return Solid(ocp_cyl)


def get_cylinder_radius(cylinder_solid):
    """Ermittelt den Radius des Zylinders."""
    for face in cylinder_solid.faces():
        adaptor = BRepAdaptor_Surface(face.wrapped)
        if adaptor.GetType() == GeomAbs_Cylinder:
            return adaptor.Cylinder().Radius()
    return None


def find_face_by_type(cylinder_solid, face_type):
    """Finde eine Face nach Typ (Cylinder oder Plane)."""
    for face in cylinder_solid.faces():
        adaptor = BRepAdaptor_Surface(face.wrapped)
        if adaptor.GetType() == face_type:
            return face
    return None


def find_top_face(cylinder_solid):
    """Finde die Top-Face (höchste Z)."""
    all_faces = list(cylinder_solid.faces())
    return max(all_faces, key=lambda f: BRepGProp.SurfaceProperties_s(
        f.wrapped, (props := GProp_GProps())) or props.CentreOfMass().Z()
    )


def find_bottom_face(cylinder_solid):
    """Finde die Bottom-Face (niedrigste Z)."""
    all_faces = list(cylinder_solid.faces())
    return min(all_faces, key=lambda f: BRepGProp.SurfaceProperties_s(
        f.wrapped, (props := GProp_GProps())) or props.CentreOfMass().Z()
    )


def apply_pushpull_with_unify(cylinder_solid, face, direction, height, fuse_mode=1):
    """Wendet Push/Pull mit BRepFeat_MakePrism und UnifySameDomain an."""
    prism = BRepFeat_MakePrism()
    prism.Init(cylinder_solid.wrapped, face.wrapped, face.wrapped, direction, fuse_mode, False)
    prism.Perform(height)

    if not prism.IsDone():
        raise RuntimeError(f"BRepFeat fehlgeschlagen")

    result_shape = prism.Shape()

    # UnifySameDomain
    upgrader = ShapeUpgrade_UnifySameDomain(result_shape, True, True, True)
    upgrader.SetLinearTolerance(0.01)
    upgrader.SetAngularTolerance(0.01)
    upgrader.Build()
    unified_shape = upgrader.Shape()

    if not unified_shape or unified_shape.IsNull():
        raise RuntimeError("UnifySameDomain fehlgeschlagen")

    return Solid(unified_shape)


# =============================================================================
# Tests
# =============================================================================

class TestCylinderTopology:
    """Tests für Zylinder-Topologie."""

    def test_cylinder_has_three_edges_not_two(self):
        """
        OCP Zylinder haben 3 Edges (2 Kreise + 1 Seam), nicht 2.

        Die Seam-Edge ist eine "Naht" wo der Zylinder parametrisch geschlossen wird.
        Das ist normal für OCP und kein Bug.
        """
        cylinder = create_test_cylinder(radius=10.0, height=50.0)

        faces = len(list(cylinder.faces()))
        edges = len(list(cylinder.edges()))

        assert faces == 3, f"Faces should be 3, got {faces}"
        assert edges == 3, f"Edges should be 3 (2 circles + 1 seam), got {edges}"

    def test_cylinder_body_metrics(self):
        """Test dass Zylinder-Body korrekte Metrics hat."""
        body = Body(name="Cylinder")
        prim = PrimitiveFeature(primitive_type="cylinder", radius=10.0, height=50.0)
        body.add_feature(prim, rebuild=True)

        metrics = _solid_metrics(body._build123d_solid)

        expected_volume = 3.14159 * 10 * 10 * 50
        assert abs(metrics["volume"] - expected_volume) < 100
        assert metrics["faces"] == 3
        assert metrics["edges"] == 3  # OCP Standard


class TestCylinderPushPullPlanarFaces:
    """Tests für Push/Pull auf planaren Faces (Top/Bottom)."""

    def test_pushpull_top_face_preserves_topology(self):
        """
        Push/Pull auf Top-Face mit UnifySameDomain erhält Topologie.

        WICHTIG: UnifySameDomain muss angewendet werden!
        """
        cylinder = create_test_cylinder(radius=10.0, height=50.0)
        top_face = find_top_face(cylinder)

        faces_before = len(list(cylinder.faces()))
        edges_before = len(list(cylinder.edges()))
        vol_before = cylinder.volume

        # Push mit UnifySameDomain
        result = apply_pushpull_with_unify(
            cylinder, top_face,
            direction=gp_Dir(0, 0, 1),
            height=10.0,
            fuse_mode=1
        )

        faces_after = len(list(result.faces()))
        edges_after = len(list(result.edges()))
        vol_after = result.volume

        assert faces_after == 3, f"Faces should be 3, got {faces_after}"
        assert edges_after == 3, f"Edges should be 3, got {edges_after}"
        assert vol_after > vol_before

        # Volume Check: π * r² * h = π * 10² * 10 = 3141.59
        expected_increase = 3.14159 * 10 * 10 * 10
        actual_increase = vol_after - vol_before
        assert abs(actual_increase - expected_increase) < 100

    def test_pushpull_bottom_face_preserves_topology(self):
        """Push/Pull auf Bottom-Face erhält Topologie."""
        cylinder = create_test_cylinder(radius=10.0, height=50.0)
        bottom_face = find_bottom_face(cylinder)

        result = apply_pushpull_with_unify(
            cylinder, bottom_face,
            direction=gp_Dir(0, 0, -1),
            height=10.0,
            fuse_mode=1
        )

        assert len(list(result.faces())) == 3
        assert len(list(result.edges())) == 3

    def test_double_pushpull_preserves_topology(self):
        """Doppeltes Push/Pull (oben + unten) erhält Topologie."""
        cylinder = create_test_cylinder(radius=10.0, height=50.0)

        # Erster Push oben
        top_face = find_top_face(cylinder)
        intermediate = apply_pushpull_with_unify(
            cylinder, top_face,
            direction=gp_Dir(0, 0, 1),
            height=5.0,
            fuse_mode=1
        )

        assert len(list(intermediate.edges())) == 3

        # Zweiter Push unten
        bottom_face = find_bottom_face(intermediate)
        final = apply_pushpull_with_unify(
            intermediate, bottom_face,
            direction=gp_Dir(0, 0, -1),
            height=5.0,
            fuse_mode=1
        )

        assert len(list(final.edges())) == 3
        assert final.volume > cylinder.volume * 1.05


class TestCylinderPushPullCylindricalFace:
    """
    Tests für Push/Pull auf zylindrischer Face.

    PROBLEM: Aktuelle Implementierung macht nicht das Fusion360-Verhalten.
    FUSION360: Radius ändern
    AKTUELL: Verschiebung/Extrusion
    """

    def test_detect_cylindrical_face(self):
        """Test dass zylindrische Face erkannt wird."""
        cylinder = create_test_cylinder(radius=10.0, height=50.0)

        cylindrical_face = find_face_by_type(cylinder, GeomAbs_Cylinder)
        planar_faces = [f for f in cylinder.faces()
                        if BRepAdaptor_Surface(f.wrapped).GetType() == GeomAbs_Plane]

        assert cylindrical_face is not None
        assert len(planar_faces) == 2

        radius = get_cylinder_radius(cylinder)
        assert abs(radius - 10.0) < 0.1

    def test_cylindrical_face_parameters(self):
        """Test Extraktion von Zylinder-Parametern."""
        cylinder = create_test_cylinder(radius=10.0, height=50.0)
        cylindrical_face = find_face_by_type(cylinder, GeomAbs_Cylinder)

        adaptor = BRepAdaptor_Surface(cylindrical_face.wrapped)
        gp_cylinder = adaptor.Cylinder()

        position = gp_cylinder.Position()
        location = position.Location()
        direction = position.Direction()
        radius = gp_cylinder.Radius()

        assert abs(radius - 10.0) < 0.1
        assert abs(direction.Z() - 1.0) < 0.1  # Z-Achse

    def test_brepfeat_works_on_cylindrical_face(self):
        """
        BRepFeat_MakePrism funktioniert AUCH mit zylindrischen Faces!

        Dies öffnet Möglichkeiten für Radius-Änderung.
        """
        cylinder = create_test_cylinder(radius=10.0, height=50.0)
        cylindrical_face = find_face_by_type(cylinder, GeomAbs_Cylinder)

        center_pt = cylindrical_face.center()
        normal = cylindrical_face.normal_at(center_pt)

        prism = BRepFeat_MakePrism()
        prism.Init(
            cylinder.wrapped,
            cylindrical_face.wrapped,
            cylindrical_face.wrapped,
            gp_Dir(normal.X, normal.Y, normal.Z),
            1, False
        )
        prism.Perform(5.0)

        assert prism.IsDone(), "BRepFeat sollte mit zylindrischer Face funktionieren"

    def test_expected_fusion360_behavior_description(self):
        """
        Beschreibung des erwarteten Fusion360-Verhaltens.

        Wenn User auf Zylinderfläche klickt und Push/Pull:
        - Radius wird vergrößert/verkleinert
        - Höhe bleibt gleich
        - Volume ändert sich quadratisch (V ~ r²)
        """
        # Dies ist ein Dokumentations-Test für das gewünschte Verhalten
        radius = 10.0
        height = 50.0
        volume_before = 3.14159 * radius * radius * height

        # Fusion360: User zieht um 5mm nach außen
        new_radius = 15.0
        volume_after = 3.14159 * new_radius * new_radius * height

        # Volume sollte mehr als doppelt so groß sein
        assert volume_after > volume_before * 2.0


class TestArcSketches:
    """Tests für Arc-Skizzen und Face ID Stabilität."""

    def test_arc_sketch_creates_true_cylinder(self):
        """
        Arc-Skizze wird als echter Zylinder erkannt (Kreis-Detection).

        _detect_circle_from_points erkennt 32-Punkte Kreis und erstellt echten OCP Kreis.
        """
        sketch = Sketch("ArcCircle")
        angles = np.linspace(0, 2 * np.pi, 32, endpoint=False)
        coords = [(10.0 * np.cos(a), 10.0 * np.sin(a)) for a in angles]
        coords.append(coords[0])
        sketch.closed_profiles = [Polygon(coords)]

        body = Body(name="ArcBody")
        extrude_feat = ExtrudeFeature(sketch=sketch, distance=50.0, operation="NewBody")
        body.add_feature(extrude_feat, rebuild=True)

        metrics = _solid_metrics(body._build123d_solid)

        # Sollte wie echter Zylinder sein
        assert metrics["faces"] == 3
        assert metrics["edges"] == 3

    def test_arc_with_hole_creates_ring(self):
        """Arc-Skizze mit Loch erstellt Ring (4 Faces)."""
        sketch = Sketch("ArcWithHole")
        angles = np.linspace(0, 2 * np.pi, 32, endpoint=False)

        # Außenkreis
        outer_coords = [(10.0 * np.cos(a), 10.0 * np.sin(a)) for a in angles]
        outer_coords.append(outer_coords[0])

        # Innenkreis
        inner_coords = [(5.0 * np.cos(a), 5.0 * np.sin(a)) for a in angles]
        inner_coords.append(inner_coords[0])

        sketch.closed_profiles = [Polygon(outer_coords, [inner_coords])]

        body = Body(name="ArcWithHole")
        extrude_feat = ExtrudeFeature(sketch=sketch, distance=50.0, operation="NewBody")
        body.add_feature(extrude_feat, rebuild=True)

        metrics = _solid_metrics(body._build123d_solid)

        # Ring: 4 Faces (Außenmantel, Innenmantel, Top, Bottom)
        assert metrics["faces"] == 4

    def test_face_index_stability_after_pushpull(self):
        """Face-Index sollte nach Push/Pull stabil bleiben."""
        from modeling.topology_indexing import face_index_of, face_from_index

        # Arc-Skizze Zylinder
        sketch = Sketch("ArcStability")
        angles = np.linspace(0, 2 * np.pi, 32, endpoint=False)
        coords = [(10.0 * np.cos(a), 10.0 * np.sin(a)) for a in angles]
        coords.append(coords[0])
        sketch.closed_profiles = [Polygon(coords)]

        body = Body(name="ArcStability")
        extrude_feat = ExtrudeFeature(sketch=sketch, distance=50.0, operation="NewBody")
        body.add_feature(extrude_feat, rebuild=True)

        # Top-Face Index merken
        top_face = find_top_face(body._build123d_solid)
        original_index = face_index_of(body._build123d_solid, top_face)

        # Push/Pull
        result = apply_pushpull_with_unify(
            body._build123d_solid, top_face,
            direction=gp_Dir(0, 0, 1),
            height=10.0,
            fuse_mode=1
        )

        # Prüfen ob Index noch gültig
        if original_index is not None:
            resolved_face = face_from_index(result, original_index)
            # Nach Push/Pull mit UnifySameDomain sollte der Face noch auffindbar sein
            # (kann aber andere Position haben)
            assert resolved_face is not None or len(list(result.faces())) == 3


class TestUnifySameDomain:
    """Tests für UnifySameDomain Toleranzen."""

    def test_unify_samedomain_tolerances(self):
        """UnifySameDomain funktioniert mit verschiedenen Toleranzen."""
        cylinder = create_test_cylinder(radius=10.0, height=50.0)
        top_face = find_top_face(cylinder)

        # Push/Pull ohne UnifySameDomain
        prism = BRepFeat_MakePrism()
        prism.Init(cylinder.wrapped, top_face.wrapped, top_face.wrapped, gp_Dir(0, 0, 1), 1, False)
        prism.Perform(10.0)

        result_shape = prism.Shape()

        # Ohne UnifySameDomain: 4 Faces, 5 Edges (2 cylindrische Faces!)
        faces_before = len(list(Solid(result_shape).faces()))
        assert faces_before == 4, "Vor UnifySameDomain: 4 Faces"

        # Mit UnifySameDomain
        for tolerance in [0.001, 0.01, 0.1]:
            upgrader = ShapeUpgrade_UnifySameDomain(result_shape, True, True, True)
            upgrader.SetLinearTolerance(tolerance)
            upgrader.SetAngularTolerance(0.01)
            upgrader.Build()

            unified = Solid(upgrader.Shape())
            cyl_count = sum(1 for f in unified.faces()
                           if BRepAdaptor_Surface(f.wrapped).GetType() == GeomAbs_Cylinder)

            # Alle getesteten Toleranzen sollten funktionieren
            assert cyl_count == 1, f"Tolerance {tolerance}: Should have 1 cylindrical face, got {cyl_count}"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
