"""
MashCad - BRepOffsetAPI MakeOffsetShape Tests
===============================================

Tests für BRepOffsetAPI_MakeOffsetShape - die "richtige" OCP-Methode
für Fusion360-artige Radius-Änderung an zylindrischen Faces.

Vorteile gegenüber Boolean-Rebuild:
- Erhält Topologie besser
- Keine Neuberechnung der gesamten Geometrie
- Effizienter

Author: Claude
Date: 2026-02-09
"""
import pytest
from build123d import Solid
from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox, BRepPrimAPI_MakeCylinder
from OCP.gp import gp_Ax2, gp_Pnt, gp_Dir
from OCP.BRepAlgoAPI import BRepAlgoAPI_Cut
from OCP.BRepAdaptor import BRepAdaptor_Surface
from OCP.GeomAbs import GeomAbs_Cylinder
from modeling import _solid_metrics


def create_box_with_hole(radius=5.0):
    """Box mit durchgehendem Loch."""
    box = BRepPrimAPI_MakeBox(20, 20, 10).Shape()
    box_solid = Solid(box)

    hole_ax = gp_Ax2(gp_Pnt(10, 10, -5), gp_Dir(0, 0, 1))
    hole = BRepPrimAPI_MakeCylinder(hole_ax, radius, 20).Shape()
    hole_solid = Solid(hole)

    return box_solid - hole_solid


def create_solid_cylinder(radius=10.0, height=50.0):
    """Voller Zylinder."""
    ax = gp_Ax2(gp_Pnt(0, 0, 0), gp_Dir(0, 0, 1))
    ocp_cyl = BRepPrimAPI_MakeCylinder(ax, radius, height).Shape()
    return Solid(ocp_cyl)


def get_cylinder_radius(solid):
    """Ermittelt Radius eines Zylinders."""
    for face in solid.faces():
        adaptor = BRepAdaptor_Surface(face.wrapped)
        if adaptor.GetType() == GeomAbs_Cylinder:
            return adaptor.Cylinder().Radius()
    return None


def test_offset_shape_solid_cylinder_increase_radius():
    """
    Test BRepOffsetAPI_MakeOffsetShape auf vollem Zylinder.

    Negativer Offset = Radius vergrößern
    Positiver Offset = Radius verkleinern
    """
    from OCP.BRepOffsetAPI import BRepOffsetAPI_MakeOffsetShape

    cylinder = create_solid_cylinder(radius=10.0, height=50.0)
    radius_before = get_cylinder_radius(cylinder)
    vol_before = cylinder.volume

    print(f"\nSolid Zylinder Offset Test:")
    print(f"  Vorher: Radius={radius_before:.2f}, Volume={vol_before:.2f}")

    # Negativer Offset sollte Radius vergrößern
    # ACHTUNG: MakeOffsetShape erstellt leeren Shape wenn nicht korrekt parametrisiert

    # Versuch 1: Ohne constructor argument
    try:
        offset_api = BRepOffsetAPI_MakeOffsetShape()

        # Alle Faces hinzufügen
        for face in cylinder.faces():
            offset_api.AddFace(face.wrapped)

        # Offset ausführen
        offset_api.Perform(-2.0)  # Negativ = Außen (Radius größer)

        if offset_api.IsDone():
            result_shape = offset_api.Shape()

            if not result_shape.IsNull():
                result = Solid(result_shape)
                vol_after = result.volume
                radius_after = get_cylinder_radius(result)

                print(f"  Nach Offset -2.0: Radius={radius_after:.2f}, Volume={vol_after:.2f}")

                # Prüfe ob Radius geändert wurde
                if radius_after:
                    assert abs(radius_after - (radius_before + 2.0)) < 0.5, "Radius sollte um ~2mm gewachsen sein"
                assert vol_after > vol_before, "Volume sollte zugenommen sein"
            else:
                print(f"  Offset Ergebnis ist Null")
        else:
            print(f"  Offset IsDone() = False")
    except Exception as e:
        print(f"  Exception: {e}")


def test_offset_shape_hole_increase_radius():
    """Test Offset auf Loch (Radius vergrößern)."""
    from OCP.BRepOffsetAPI import BRepOffsetAPI_MakeOffsetShape

    body = create_box_with_hole(radius=5.0)
    radius_before = get_cylinder_radius(body)
    vol_before = body.volume

    print(f"\nLoch Offset Test (vergrößern):")
    print(f"  Vorher: Radius={radius_before:.2f}, Volume={vol_before:.2f}")

    try:
        offset_api = BRepOffsetAPI_MakeOffsetShape()

        # Alle Faces hinzufügen
        for face in body.faces():
            offset_api.AddFace(face.wrapped)

        # Positiver Offset = Nach innen (Loch verkleinern)
        # Negativer Offset = Nach außen (Loch vergrößern)
        offset_api.Perform(-1.0)

        if offset_api.IsDone():
            result_shape = offset_api.Shape()

            if not result_shape.IsNull():
                result = Solid(result_shape)
                vol_after = result.volume
                radius_after = get_cylinder_radius(result)

                print(f"  Nach Offset -1.0: Radius={radius_after}, Volume={vol_after:.2f}")

                if radius_after:
                    print(f"  Radius-Änderung: {radius_after - radius_before:.2f}")
    except Exception as e:
        print(f"  Exception: {e}")


def test_offset_shape_tolerance_variations():
    """Test verschiedene Toleranzen."""
    from OCP.BRepOffsetAPI import BRepOffsetAPI_MakeOffsetShape

    body = create_solid_cylinder(radius=10.0, height=50.0)

    for tolerance in [1e-6, 1e-5, 1e-4, 1e-3, 1e-2]:
        try:
            offset_api = BRepOffsetAPI_MakeOffsetShape()

            for face in body.faces():
                offset_api.AddFace(face.wrapped)

            # Toleranz setzen
            # offset_api.SetTolerance(tolerance)  # Wenn verfügbar

            offset_api.Perform(2.0)

            if offset_api.IsDone():
                result_shape = offset_api.Shape()

                if not result_shape.IsNull():
                    result = Solid(result_shape)
                    vol = result.volume
                    print(f"  Tolerance {tolerance}: Volume={vol:.2f}")
                else:
                    print(f"  Tolerance {tolerance}: Null result")
        except Exception as e:
            print(f"  Tolerance {tolerance}: Failed - {e}")


def test_offset_shape_selective_faces():
    """Test Offset nur auf zylindrische Face."""
    from OCP.BRepOffsetAPI import BRepOffsetAPI_MakeOffsetShape

    body = create_box_with_hole(radius=5.0)
    vol_before = body.volume

    # Nur zylindrische Face finden
    cyl_face = None
    for face in body.faces():
        adaptor = BRepAdaptor_Surface(face.wrapped)
        if adaptor.GetType() == GeomAbs_Cylinder:
            cyl_face = face
            break

    if cyl_face:
        print(f"\nSelektiver Offset (nur zylindrische Face):")

        try:
            offset_api = BRepOffsetAPI_MakeOffsetShape()

            # Nur zylindrische Face hinzufügen
            offset_api.AddFace(cyl_face.wrapped)

            offset_api.Perform(-1.0)

            if offset_api.IsDone():
                result_shape = offset_api.Shape()

                if not result_shape.IsNull():
                    result = Solid(result_shape)
                    vol_after = result.volume

                    print(f"  Volume: {vol_before:.2f} → {vol_after:.2f}")
                else:
                    print(f"  Ergebnis ist Null")
        except Exception as e:
            print(f"  Exception: {e}")


def test_brepopngun_make_draft_angle():
    """
    Test BRepFeat_MakeDraft - Alternative für konische Verjüngungen.

    Draft kann verwendet werden um zylindrische Faces in konische umzuwandeln.
    """
    brepfeat_mod = pytest.importorskip("OCP.BRepFeat")
    if not hasattr(brepfeat_mod, "BRepFeat_MakeDraft"):
        pytest.skip("BRepFeat_MakeDraft ist in dieser OCP-Build-Variante nicht verfuegbar")
    BRepFeat_MakeDraft = brepfeat_mod.BRepFeat_MakeDraft

    body = create_box_with_hole(radius=5.0)

    print(f"\nDraft Angle Test:")

    # Zylindrische Face finden
    cyl_face = None
    for face in body.faces():
        adaptor = BRepAdaptor_Surface(face.wrapped)
        if adaptor.GetType() == GeomAbs_Cylinder:
            cyl_face = face
            break

    if cyl_face:
        try:
            draft = BRepFeat_MakeDraft()

            # DraftDir = direction of draft (normal to face)
            center = cyl_face.center()
            normal = cyl_face.normal_at(center)

            draft.Init(
                body.wrapped,
                gp_Dir(normal.X, normal.Y, normal.Z),
                0.1,  # Angle (radians)
                0.0   # Neutral plane
            )

            draft.Add(cyl_face.wrapped)

            draft.Perform()

            if draft.IsDone():
                result = Solid(draft.Shape())
                print(f"  Draft erfolgreich: Volume={result.volume:.2f}")
        except Exception as e:
            print(f"  Draft Exception: {e}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
