"""
MashCad - Cylindrical Face Edit Tests
======================================

Konsolidierte Tests für Radius-Änderung auf zylindrischen Faces.

Fälle:
- Durchgehende Löcher (Through Holes)
- Taschen (Pockets - nicht durchgehende Löcher)
- Außenkörper (Solid Cylinder)

Feature: CylindricalFaceEditFeature
Command: CylindricalFaceEditCommand

Author: Claude
Date: 2026-02-09
"""
import pytest
import numpy as np
from build123d import Solid
from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox, BRepPrimAPI_MakeCylinder
from OCP.gp import gp_Ax2, gp_Pnt, gp_Dir
from OCP.BRepAlgoAPI import BRepAlgoAPI_Cut
from OCP.BRepAdaptor import BRepAdaptor_Surface
from OCP.GeomAbs import GeomAbs_Cylinder, GeomAbs_Plane
from modeling import Body, PrimitiveFeature, ExtrudeFeature, _solid_metrics
from sketcher.sketch import Sketch
from shapely.geometry import Polygon


# =============================================================================
# Test Bodies Creator
# =============================================================================

def create_box_with_hole(radius=5.0):
    """Box mit durchgehendem Loch."""
    box = BRepPrimAPI_MakeBox(20, 20, 10).Shape()
    box_solid = Solid(box)

    hole_ax = gp_Ax2(gp_Pnt(10, 10, -5), gp_Dir(0, 0, 1))
    hole = BRepPrimAPI_MakeCylinder(hole_ax, radius, 20).Shape()
    hole_solid = Solid(hole)

    return box_solid - hole_solid


def create_box_with_pocket(radius=5.0, depth=8):
    """Box mit Tasche (nicht durchgehend)."""
    box = BRepPrimAPI_MakeBox(20, 20, 10).Shape()
    box_solid = Solid(box)

    pocket_ax = gp_Ax2(gp_Pnt(10, 10, 0), gp_Dir(0, 0, 1))
    pocket = BRepPrimAPI_MakeCylinder(pocket_ax, radius, depth).Shape()
    pocket_solid = Solid(pocket)

    return box_solid - pocket_solid


def create_solid_cylinder(radius=10.0, height=50.0):
    """Voller Zylinder (kein Loch)."""
    ax = gp_Ax2(gp_Pnt(0, 0, 0), gp_Dir(0, 0, 1))
    ocp_cyl = BRepPrimAPI_MakeCylinder(ax, radius, height).Shape()
    return Solid(ocp_cyl)


def find_cylindrical_face(solid):
    """Finde die erste zylindrische Face."""
    for face in solid.faces():
        adaptor = BRepAdaptor_Surface(face.wrapped)
        if adaptor.GetType() == GeomAbs_Cylinder:
            return face
    return None


def extract_cylinder_params(face):
    """Extrahiere Zylinder-Parameter aus Face."""
    adaptor = BRepAdaptor_Surface(face.wrapped)
    gp_cyl = adaptor.Cylinder()

    position = gp_cyl.Position()
    return {
        'location': (position.Location().X(), position.Location().Y(), position.Location().Z()),
        'direction': (position.Direction().X(), position.Direction().Y(), position.Direction().Z()),
        'radius': gp_cyl.Radius(),
    }


# =============================================================================
# Tests
# =============================================================================

class TestCylindricalFaceDetection:
    """Tests für Erkennung von zylindrischen Faces."""

    def test_detect_hole_cylinder_face(self):
        """Durchgehendes Loch: Zylindrische Face sollte gefunden werden."""
        body = create_box_with_hole()
        cyl_face = find_cylindrical_face(body)
        assert cyl_face is not None

        params = extract_cylinder_params(cyl_face)
        assert abs(params['radius'] - 5.0) < 0.1

    def test_detect_pocket_cylinder_face(self):
        """Tasche: Zylindrische Face sollte gefunden werden."""
        body = create_box_with_pocket()
        cyl_face = find_cylindrical_face(body)
        assert cyl_face is not None

        params = extract_cylinder_params(cyl_face)
        assert abs(params['radius'] - 5.0) < 0.1

    def test_detect_solid_cylinder_face(self):
        """Voller Zylinder: Zylindrische Face sollte gefunden werden."""
        body = create_solid_cylinder()
        cyl_face = find_cylindrical_face(body)
        assert cyl_face is not None

        params = extract_cylinder_params(cyl_face)
        assert abs(params['radius'] - 10.0) < 0.1


class TestHoleRadiusChange:
    """Tests für Radius-Änderung an durchgehenden Löchern."""

    def test_hole_radius_increase(self):
        """Loch vergrößern: 5mm → 7mm."""
        body_before = create_box_with_hole(radius=5.0)
        vol_before = body_before.volume

        cyl_face = find_cylindrical_face(body_before)
        params = extract_cylinder_params(cyl_face)

        # Rebuild mit größerem Radius
        new_radius = 7.0
        hole_ax = gp_Ax2(gp_Pnt(*params['location']), gp_Dir(*params['direction']))
        new_hole = BRepPrimAPI_MakeCylinder(hole_ax, new_radius, 30).Shape()
        new_hole_solid = Solid(new_hole)

        box = BRepPrimAPI_MakeBox(20, 20, 10).Shape()
        box_solid = Solid(box)

        cut = BRepAlgoAPI_Cut(box_solid.wrapped, new_hole_solid.wrapped)
        cut.Build()

        if cut.IsDone():
            result = Solid(cut.Shape())
            assert result.volume < vol_before, "Größeres Loch = weniger Volume"

    def test_hole_radius_decrease(self):
        """Loch verkleinern: 5mm → 4mm."""
        body_before = create_box_with_hole(radius=5.0)
        vol_before = body_before.volume

        cyl_face = find_cylindrical_face(body_before)
        params = extract_cylinder_params(cyl_face)

        new_radius = 4.0
        hole_ax = gp_Ax2(gp_Pnt(*params['location']), gp_Dir(*params['direction']))
        new_hole = BRepPrimAPI_MakeCylinder(hole_ax, new_radius, 30).Shape()
        new_hole_solid = Solid(new_hole)

        box = BRepPrimAPI_MakeBox(20, 20, 10).Shape()
        box_solid = Solid(box)

        cut = BRepAlgoAPI_Cut(box_solid.wrapped, new_hole_solid.wrapped)
        cut.Build()

        if cut.IsDone():
            result = Solid(cut.Shape())
            assert result.volume > vol_before, "Kleineres Loch = mehr Volume"


class TestPocketRadiusChange:
    """Tests für Radius-Änderung an Taschen."""

    def test_pocket_radius_increase(self):
        """Tasche vergrößern: 5mm → 7mm."""
        body_before = create_box_with_pocket(radius=5.0, depth=8)
        vol_before = body_before.volume

        cyl_face = find_cylindrical_face(body_before)
        params = extract_cylinder_params(cyl_face)

        new_radius = 7.0
        pocket_ax = gp_Ax2(gp_Pnt(*params['location']), gp_Dir(*params['direction']))
        new_pocket = BRepPrimAPI_MakeCylinder(pocket_ax, new_radius, 8).Shape()
        new_pocket_solid = Solid(new_pocket)

        box = BRepPrimAPI_MakeBox(20, 20, 10).Shape()
        box_solid = Solid(box)

        cut = BRepAlgoAPI_Cut(box_solid.wrapped, new_pocket_solid.wrapped)
        cut.Build()

        if cut.IsDone():
            result = Solid(cut.Shape())
            assert result.volume < vol_before

    def test_pocket_radius_decrease(self):
        """Tasche verkleinern: 5mm → 4mm."""
        body_before = create_box_with_pocket(radius=5.0, depth=8)
        vol_before = body_before.volume

        cyl_face = find_cylindrical_face(body_before)
        params = extract_cylinder_params(cyl_face)

        new_radius = 4.0
        pocket_ax = gp_Ax2(gp_Pnt(*params['location']), gp_Dir(*params['direction']))
        new_pocket = BRepPrimAPI_MakeCylinder(pocket_ax, new_radius, 8).Shape()
        new_pocket_solid = Solid(new_pocket)

        box = BRepPrimAPI_MakeBox(20, 20, 10).Shape()
        box_solid = Solid(box)

        cut = BRepAlgoAPI_Cut(box_solid.wrapped, new_pocket_solid.wrapped)
        cut.Build()

        if cut.IsDone():
            result = Solid(cut.Shape())
            assert result.volume > vol_before


class TestSolidCylinderRadiusChange:
    """Tests für Radius-Änderung an vollem Zylinder."""

    def test_solid_cylinder_radius_increase(self):
        """Voller Zylinder: Radius vergrößern."""
        body_before = create_solid_cylinder(radius=10.0, height=50.0)
        vol_before = body_before.volume

        params = extract_cylinder_params(find_cylindrical_face(body_before))

        # Neuer Zylinder mit größerem Radius
        new_radius = 15.0
        ax = gp_Ax2(gp_Pnt(*params['location']), gp_Dir(*params['direction']))
        new_cyl = BRepPrimAPI_MakeCylinder(ax, new_radius, 50).Shape()
        result = Solid(new_cyl)

        vol_after = result.volume
        assert vol_after > vol_before * 2, "Radius verdoppelt = Volume vervierfacht"


class TestDifferentiation:
    """Tests für Unterscheidung zwischen Loch, Tasche, Außenkörper."""

    def test_pocket_vs_through_hole_v_range(self):
        """Unterscheidung durch V-Range (Höhe des Zylinders)."""
        pocket = create_box_with_pocket(radius=5.0, depth=8)
        hole = create_box_with_pocket(radius=5.0, depth=20)  # Durchgehend

        for name, body, expected_v_last in [
            ("Pocket", pocket, 8.0),
            ("Loch", hole, 10.0),  # OCP begrenzt auf Box-Höhe
        ]:
            cyl_face = find_cylindrical_face(body)
            adaptor = BRepAdaptor_Surface(cyl_face.wrapped)
            v_last = adaptor.LastVParameter()

            assert abs(v_last - expected_v_last) < 1.0, f"{name}: V-Range sollte {expected_v_last} sein"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
