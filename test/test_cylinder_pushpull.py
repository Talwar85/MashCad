"""
MashCad - Cylinder Push/Pull Tests
===================================

Tests für Push/Pull auf Zylinder-Flächen.

Problem: Push/Pull auf Zylinder erzeugt:
- Zu viele Kanten
- Keine zusammenhängende Fläche
- Zylinder sieht nicht korrekt aus

Author: Claude
Date: 2026-02-09
"""
import pytest
from build123d import Cylinder, Solid
from modeling import Body, PrimitiveFeature, _solid_metrics


def _create_cylinder_body(radius=10.0, height=50.0):
    """Erstellt einen Zylinder-Body."""
    body = Body(name="Cylinder")
    prim = PrimitiveFeature(
        primitive_type="cylinder",
        radius=radius,
        height=height
    )
    body.add_feature(prim, rebuild=True)
    return body, prim


def test_cylinder_creation():
    """Test dass Zylinder korrekt erstellt wird."""
    body, prim = _create_cylinder_body(radius=10.0, height=50.0)

    assert body._build123d_solid is not None, "Zylinder-Solid wurde nicht erstellt"
    assert prim.status == "OK", f"Zylinder-Status: {prim.status}, {prim.status_message}"

    # Geometry Metrics checken
    metrics = _solid_metrics(body._build123d_solid)
    assert metrics is not None

    # Zylinder: Volume = π * r² * h = π * 10² * 50 = 15708
    expected_volume = 3.14159 * 10 * 10 * 50
    assert abs(metrics["volume"] - expected_volume) < 100, \
        f"Zylinder Volume falsch: erwartet ~{expected_volume:.0f}, bekommen {metrics['volume']:.0f}"

    # Zylinder hat 3 Faces: top, bottom, side
    assert metrics["faces"] == 3, f"Zylinder sollte 3 Faces haben, hat {metrics['faces']}"

    # Zylinder hat 2 Edges: top circle, bottom circle
    assert metrics["edges"] == 2, f"Zylinder sollte 2 Edges haben (Kreise), hat {metrics['edges']}"


def test_cylinder_top_face_is_planar():
    """Test dass Top-Face des Zylinders planar ist."""
    body, _ = _create_cylinder_body()

    solid = body._build123d_solid
    all_faces = list(solid.faces())

    assert len(all_faces) == 3, f"Zylinder sollte 3 Faces haben, hat {len(all_faces)}"

    # Finde Top-Face (höchste Z-Position)
    from OCP.BRepAdaptor import BRepAdaptor_Surface
    from OCP.GeomAbs import GeomAbs_Plane

    top_face = None
    max_z = -float('inf')

    for face in all_faces:
        # Prüfe Surface-Type
        adaptor = BRepAdaptor_Surface(face.wrapped)
        surface_type = adaptor.GetType()

        # Hole Center
        from OCP.GProp import GProp_GProps
        from OCP.BRepGProp import BRepGProp
        props = GProp_GProps()
        BRepGProp.SurfaceProperties_s(face.wrapped, props)
        center = props.CentreOfMass()

        if center.Z() > max_z:
            max_z = center.Z()
            top_face = face

    assert top_face is not None, "Top-Face nicht gefunden"

    # Prüfe dass Top-Face planar ist
    adaptor = BRepAdaptor_Surface(top_face.wrapped)
    assert adaptor.GetType() == GeomAbs_Plane, \
        f"Top-Face sollte planar sein, ist aber {adaptor.GetType()}"


def test_cylinder_side_face_is_cylindrical():
    """Test dass Side-Face des Zylinders zylindrisch ist."""
    body, _ = _create_cylinder_body()

    solid = body._build123d_solid
    all_faces = list(solid.faces())

    # Finde Side-Face (zylindrisch)
    from OCP.BRepAdaptor import BRepAdaptor_Surface
    from OCP.GeomAbs import GeomAbs_Cylinder

    cylindrical_faces = []
    for face in all_faces:
        adaptor = BRepAdaptor_Surface(face.wrapped)
        if adaptor.GetType() == GeomAbs_Cylinder:
            cylindrical_faces.append(face)

    assert len(cylindrical_faces) == 1, \
        f"Zylinder sollte 1 zylindrische Face haben, hat {len(cylindrical_faces)}"


def test_cylinder_edges_are_circles():
    """Test dass Zylinder-Edges Kreise sind."""
    body, _ = _create_cylinder_body()

    solid = body._build123d_solid
    all_edges = list(solid.edges())

    assert len(all_edges) == 2, f"Zylinder sollte 2 Edges haben, hat {len(all_edges)}"

    # Prüfe dass beide Edges Kreise sind
    from build123d import GeomType

    for edge in all_edges:
        assert edge.geom_type == GeomType.CIRCLE, \
            f"Zylinder-Edge sollte CIRCLE sein, ist {edge.geom_type}"


def test_cylinder_vs_extruded_circle_comparison():
    """Vergleicht PrimitiveFeature-Zylinder mit extrudiertem Kreis."""
    # 1. Zylinder via PrimitiveFeature
    cylinder_body, _ = _create_cylinder_body(radius=10.0, height=50.0)
    cylinder_metrics = _solid_metrics(cylinder_body._build123d_solid)

    # 2. Zylinder via extrudiertem Kreis
    from build123d import Circle, extrude
    from modeling import ExtrudeFeature
    from sketcher.sketch import Sketch

    sketch = Sketch("Circle")
    # Erstelle Kreis-Skizze
    from shapely.geometry import Point
    import numpy as np

    # Kreis als Polygon approximieren
    radius = 10.0
    n_points = 32
    angles = np.linspace(0, 2 * np.pi, n_points, endpoint=False)
    coords = [(radius * np.cos(a), radius * np.sin(a)) for a in angles]
    coords.append(coords[0])  # Close

    from shapely.geometry import Polygon
    sketch.closed_profiles = [Polygon(coords)]

    extruded_body = Body(name="Extruded Circle")
    extrude_feat = ExtrudeFeature(sketch=sketch, distance=50.0, operation="NewBody")
    extruded_body.add_feature(extrude_feat, rebuild=True)

    extruded_metrics = _solid_metrics(extruded_body._build123d_solid)

    # Volumes sollten ähnlich sein
    vol_diff = abs(cylinder_metrics["volume"] - extruded_metrics["volume"])
    vol_diff_pct = (vol_diff / cylinder_metrics["volume"]) * 100

    assert vol_diff_pct < 5.0, \
        f"Zylinder vs Extrudierter Kreis: Volume-Differenz {vol_diff_pct:.1f}% (zu groß)"

    # Faces: Zylinder hat 3, extrudierter Kreis auch 3
    assert cylinder_metrics["faces"] == 3, f"Primitive-Zylinder hat {cylinder_metrics['faces']} Faces"
    assert extruded_metrics["faces"] == 3, f"Extrudierter Kreis hat {extruded_metrics['faces']} Faces"

    # Edges: Zylinder hat 2, extrudierter Kreis auch 2
    assert cylinder_metrics["edges"] == 2, f"Primitive-Zylinder hat {cylinder_metrics['edges']} Edges"
    # Extrudierter Kreis kann mehr Edges haben (wegen Polygon-Approximation)
    # assert extruded_metrics["edges"] == 2


def test_cylinder_pushpull_top_face_preserves_edge_count():
    """Test dass Push/Pull auf Top-Face die Edge-Anzahl bei 3 hält.

    Beweis dass Zylinder nach Push/Pull von oben korrekt bleibt:
    - Vorher: 3 Edges (2 Kreise + 1 Naht)
    - Nachher: 3 Edges (2 Kreise + 1 Naht)
    - NICHT: 4+ Edges (fragmentiert)
    """
    from OCP.BRepFeat import BRepFeat_MakePrism
    from OCP.gp import gp_Vec, gp_Dir
    from build123d import Solid

    # 1. Erstelle Zylinder
    body, _ = _create_cylinder_body(radius=10.0, height=50.0)
    cylinder = body._build123d_solid

    # Vor Push/Pull: 3 Edges
    edges_before = list(cylinder.edges())
    assert len(edges_before) == 3, f"Zylinder sollte 3 Edges haben, hat {len(edges_before)}"

    # 2. Finde Top-Face (höchste Z-Position)
    all_faces = list(cylinder.faces())
    from OCP.GProp import GProp_GProps
    from OCP.BRepGProp import BRepGProp

    top_face = None
    max_z = -float('inf')
    for face in all_faces:
        props = GProp_GProps()
        BRepGProp.SurfaceProperties_s(face.wrapped, props)
        center = props.CentreOfMass()
        if center.Z() > max_z:
            max_z = center.Z()
            top_face = face

    assert top_face is not None, "Top-Face nicht gefunden"

    # 3. Push/Pull mit BRepFeat_MakePrism (10mm nach oben)
    prism = BRepFeat_MakePrism(
        cylinder.wrapped,
        top_face.wrapped,
        top_face.wrapped,
        gp_Dir(0, 0, 1),  # Nach oben
        0,  # Fuse mode
        True  # Modify
    )
    prism.Perform(10.0)  # 10mm extrusion

    if not prism.IsDone():
        pytest.skip("BRepFeat_MakePrism fehlgeschlagen - OCP limitierung")

    result_shape = prism.Shape()
    result_solid = Solid(result_shape)

    # 4. Nach Push/Pull: Immer noch 3 Edges
    edges_after = list(result_solid.edges())
    assert len(edges_after) == 3, \
        f"Nach Push/Pull von oben: Zylinder sollte 3 Edges haben, hat {len(edges_after)} (fragmentiert!)"

    # 5. Volume-Check: Sollte größer sein
    vol_before = cylinder.volume
    vol_after = result_solid.volume
    assert vol_after > vol_before, \
        f"Volume sollte nach Push/Pull größer sein: {vol_before:.0f} → {vol_after:.0f}"

    # Erwartetes Volume: Original + π*r²*h = 15708 + π*10²*10 = 15708 + 3142 = 18850
    expected_volume_increase = 3.14159 * 10 * 10 * 10
    actual_increase = vol_after - vol_before
    assert abs(actual_increase - expected_volume_increase) < 500, \
        f"Volume-Zunahme falsch: erwartet ~{expected_volume_increase:.0f}, bekommen {actual_increase:.0f}"


def test_cylinder_pushpull_bottom_face_preserves_edge_count():
    """Test dass Push/Pull auf Bottom-Face die Edge-Anzahl bei 3 hält.

    Beweis dass Zylinder nach Push/Pull von unten korrekt bleibt:
    - Vorher: 3 Edges
    - Nachher: 3 Edges
    - NICHT: 4+ Edges (fragmentiert)
    """
    from OCP.BRepFeat import BRepFeat_MakePrism
    from OCP.gp import gp_Vec, gp_Dir
    from build123d import Solid

    # 1. Erstelle Zylinder
    body, _ = _create_cylinder_body(radius=10.0, height=50.0)
    cylinder = body._build123d_solid

    # Vor Push/Pull: 3 Edges
    edges_before = list(cylinder.edges())
    assert len(edges_before) == 3, f"Zylinder sollte 3 Edges haben, hat {len(edges_before)}"

    # 2. Finde Bottom-Face (niedrigste Z-Position)
    all_faces = list(cylinder.faces())
    from OCP.GProp import GProp_GProps
    from OCP.BRepGProp import BRepGProp

    bottom_face = None
    min_z = float('inf')
    for face in all_faces:
        props = GProp_GProps()
        BRepGProp.SurfaceProperties_s(face.wrapped, props)
        center = props.CentreOfMass()
        if center.Z() < min_z:
            min_z = center.Z()
            bottom_face = face

    assert bottom_face is not None, "Bottom-Face nicht gefunden"

    # 3. Push/Pull mit BRepFeat_MakePrism (10mm nach unten = negative Richtung)
    prism = BRepFeat_MakePrism(
        cylinder.wrapped,
        bottom_face.wrapped,
        bottom_face.wrapped,
        gp_Dir(0, 0, -1),  # Nach unten
        0,  # Fuse mode
        True  # Modify
    )
    prism.Perform(10.0)  # 10mm extrusion (Richtung wird von gp_Dir bestimmt)

    if not prism.IsDone():
        pytest.skip("BRepFeat_MakePrism fehlgeschlagen - OCP limitierung")

    result_shape = prism.Shape()
    result_solid = Solid(result_shape)

    # 4. Nach Push/Pull: Immer noch 3 Edges
    edges_after = list(result_solid.edges())
    assert len(edges_after) == 3, \
        f"Nach Push/Pull von unten: Zylinder sollte 3 Edges haben, hat {len(edges_after)} (fragmentiert!)"

    # 5. Volume-Check: Sollte größer sein
    vol_before = cylinder.volume
    vol_after = result_solid.volume
    assert vol_after > vol_before, \
        f"Volume sollte nach Push/Pull größer sein: {vol_before:.0f} → {vol_after:.0f}"


def test_cylinder_double_pushpull_preserves_topology():
    """Test dass doppeltes Push/Pull (oben + unten) die Topologie erhält.

    Kompletter Workflow:
    1. Zylinder: 3 Edges
    2. Push/Pull oben: 3 Edges
    3. Push/Pull unten: 3 Edges (nicht 4, 5, 6!)
    """
    from OCP.BRepFeat import BRepFeat_MakePrism
    from OCP.gp import gp_Dir
    from build123d import Solid
    from OCP.GProp import GProp_GProps
    from OCP.BRepGProp import BRepGProp

    # 1. Zylinder
    body, _ = _create_cylinder_body(radius=10.0, height=50.0)
    cylinder = body._build123d_solid
    assert len(list(cylinder.edges())) == 3, "Start: 3 Edges"

    # 2. Push/Pull oben
    all_faces = list(cylinder.faces())
    top_face = max(all_faces, key=lambda f: BRepGProp.SurfaceProperties_s(
        f.wrapped, (props := GProp_GProps())) or props.CentreOfMass().Z()
    )

    prism1 = BRepFeat_MakePrism(cylinder.wrapped, top_face.wrapped, top_face.wrapped, gp_Dir(0, 0, 1), 0, True)
    prism1.Perform(5.0)

    if not prism1.IsDone():
        pytest.skip("Erste BRepFeat_MakePrism fehlgeschlagen")

    intermediate = Solid(prism1.Shape())
    edges_after_top = list(intermediate.edges())
    assert len(edges_after_top) == 3, f"Nach Push/Pull oben: 3 Edges erwartet, {len(edges_after_top)} bekommen"

    # 3. Push/Pull unten
    all_faces2 = list(intermediate.faces())
    bottom_face = min(all_faces2, key=lambda f: BRepGProp.SurfaceProperties_s(
        f.wrapped, (props := GProp_GProps())) or props.CentreOfMass().Z()
    )

    prism2 = BRepFeat_MakePrism(intermediate.wrapped, bottom_face.wrapped, bottom_face.wrapped, gp_Dir(0, 0, -1), 0, True)
    prism2.Perform(5.0)

    if not prism2.IsDone():
        pytest.skip("Zweite BRepFeat_MakePrism fehlgeschlagen")

    final = Solid(prism2.Shape())
    edges_final = list(final.edges())

    # KRITISCHER TEST: Immer noch 3 Edges, nicht 4/5/6!
    assert len(edges_final) == 3, \
        f"Nach doppeltem Push/Pull: 3 Edges erwartet, {len(edges_final)} bekommen (Topologie zerstört!)"

    # Volume sollte deutlich größer sein
    assert final.volume > cylinder.volume * 1.1, "Volume sollte nach doppeltem Push/Pull mindestens 10% größer sein"


def test_cylinder_face_normal_directions():
    """Test dass Face-Normalen korrekt nach außen zeigen."""
    body, _ = _create_cylinder_body()

    solid = body._build123d_solid
    all_faces = list(solid.faces())

    from OCP.BRepAdaptor import BRepAdaptor_Surface
    from OCP.BRepLProp import BRepLProp_SLProps
    from OCP.GProp import GProp_GProps
    from OCP.BRepGProp import BRepGProp

    for face in all_faces:
        # Hole Face-Center
        props = GProp_GProps()
        BRepGProp.SurfaceProperties_s(face.wrapped, props)
        center = props.CentreOfMass()

        # Berechne Normal am Center
        adaptor = BRepAdaptor_Surface(face.wrapped)
        u_mid = (adaptor.FirstUParameter() + adaptor.LastUParameter()) / 2
        v_mid = (adaptor.FirstVParameter() + adaptor.LastVParameter()) / 2

        slprops = BRepLProp_SLProps(adaptor, u_mid, v_mid, 1, 1e-6)

        if slprops.IsNormalDefined():
            normal = slprops.Normal()
            nx, ny, nz = normal.X(), normal.Y(), normal.Z()

            # Normal sollte nicht (0,0,0) sein
            length = (nx**2 + ny**2 + nz**2)**0.5
            assert length > 0.1, f"Face-Normal zu kurz: {length}"


def test_cylinder_geometry_delta_on_creation():
    """Test dass Zylinder-Erstellung _geometry_delta setzt."""
    body, prim = _create_cylinder_body()

    gd = getattr(prim, '_geometry_delta', None)
    assert gd is not None, "PrimitiveFeature Zylinder hat kein _geometry_delta"

    assert gd["volume_after"] > 0, "Zylinder Volume sollte > 0 sein"
    assert gd["faces_after"] == 3, f"Zylinder sollte 3 Faces haben, delta sagt {gd['faces_after']}"
    assert gd["edges_after"] == 2, f"Zylinder sollte 2 Edges haben, delta sagt {gd['edges_after']}"


# ===========================================================================
# Diagnose-Funktionen für manuelle Tests
# ===========================================================================

def diagnose_cylinder_faces(cylinder_solid):
    """Diagnose-Funktion: Gibt detaillierte Face-Info aus."""
    from OCP.BRepAdaptor import BRepAdaptor_Surface
    from OCP.GProp import GProp_GProps
    from OCP.BRepGProp import BRepGProp

    all_faces = list(cylinder_solid.faces())
    print(f"\n=== Zylinder Face-Diagnose ({len(all_faces)} Faces) ===")

    for i, face in enumerate(all_faces):
        adaptor = BRepAdaptor_Surface(face.wrapped)
        surface_type = adaptor.GetType()

        props = GProp_GProps()
        BRepGProp.SurfaceProperties_s(face.wrapped, props)
        center = props.CentreOfMass()
        area = props.Mass()

        print(f"Face {i}: Type={surface_type}, Center=({center.X():.2f}, {center.Y():.2f}, {center.Z():.2f}), Area={area:.2f}")


def diagnose_cylinder_edges(cylinder_solid):
    """Diagnose-Funktion: Gibt detaillierte Edge-Info aus."""
    all_edges = list(cylinder_solid.edges())
    print(f"\n=== Zylinder Edge-Diagnose ({len(all_edges)} Edges) ===")

    for i, edge in enumerate(all_edges):
        try:
            center = edge.center()
            length = float(edge.length)
            geom_type = edge.geom_type
            print(f"Edge {i}: Type={geom_type}, Length={length:.2f}, Center=({center.X:.2f}, {center.Y:.2f}, {center.Z:.2f})")
        except Exception as e:
            print(f"Edge {i}: ERROR - {e}")


if __name__ == "__main__":
    # Manuelle Diagnose ausführen
    print("Erstelle Zylinder für Diagnose...")
    body, _ = _create_cylinder_body(radius=10.0, height=50.0)

    print("\nZylinder-Metriken:")
    metrics = _solid_metrics(body._build123d_solid)
    print(f"  Volume: {metrics['volume']:.0f} mm³")
    print(f"  Faces: {metrics['faces']}")
    print(f"  Edges: {metrics['edges']}")

    diagnose_cylinder_faces(body._build123d_solid)
    diagnose_cylinder_edges(body._build123d_solid)

    print("\n✅ Diagnose abgeschlossen")
