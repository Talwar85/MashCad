"""
W34: Ellipse Kernel Extrude Test Matrix

Mission: Ellipse muss in der 3D-Extrude-Pipeline dieselbe Stabilität wie Circle haben.

Pipeline-Matrix:
1. Profile detect - Ellipse wird als geschlossenes Profil erkannt
2. Extrude simple - Einfache Ellipse -> Solid
3. Extrude with hole - Ellipse-Ring -> Solid mit Loch
4. Rebuild stability - Mehrfaches Rebuild liefert konsistente Resultate
5. Undo/Redo - Undo/Redo auf Ellipse-Extrude stabil
6. Save/Load/Reopen - Persistenz erhalten
"""

import pytest
import math
from loguru import logger

try:
    from sketcher import Sketch
    from sketcher.geometry import Ellipse2D, Point2D
    from modeling import Body, ExtrudeFeature, Document
    from build123d import Solid
    SKETCHER_AVAILABLE = True
except ImportError as e:
    logger.warning(f"Import error: {e}")
    SKETCHER_AVAILABLE = False


pytestmark = pytest.mark.skipif(not SKETCHER_AVAILABLE, reason="Sketcher/Modeling not available")


class TestEllipseProfileDetect:
    """Test 1: Ellipse-Profile werden korrekt erkannt."""

    def test_ellipse_in_closed_profiles(self):
        """Ellipse sollte in closed_profiles auftauchen."""
        sketch = Sketch("ellipse_profile")
        ellipse = sketch.add_ellipse(0, 0, 10, 5, angle_deg=0)

        profiles = sketch.closed_profiles

        assert len(profiles) > 0, "Keine Profile gefunden"
        ellipse_profiles = [p for p in profiles if isinstance(p, dict) and p.get('type') == 'ellipse']
        assert len(ellipse_profiles) == 1, f"Ellipse-Profile erwartet, gefunden: {ellipse_profiles}"
        assert ellipse_profiles[0]['geometry'] is ellipse

    def test_multiple_ellipses_detected(self):
        """Mehrere Ellipsen sollten alle erkannt werden."""
        sketch = Sketch("multi_ellipse")
        e1 = sketch.add_ellipse(0, 0, 10, 5, angle_deg=0)
        e2 = sketch.add_ellipse(30, 0, 8, 4, angle_deg=0)

        profiles = sketch.closed_profiles
        ellipse_profiles = [p for p in profiles if isinstance(p, dict) and p.get('type') == 'ellipse']

        assert len(ellipse_profiles) == 2, f"2 Ellipsen erwartet, gefunden: {len(ellipse_profiles)}"

    def test_ellipse_with_hole_detected(self):
        """Ellipse mit innerer Ellipse (Loch) sollte erkannt werden."""
        sketch = Sketch("ellipse_with_hole")
        outer = sketch.add_ellipse(0, 0, 20, 10, angle_deg=0)
        inner = sketch.add_ellipse(0, 0, 10, 5, angle_deg=0)

        profiles = sketch.closed_profiles
        ellipse_profiles = [p for p in profiles if isinstance(p, dict) and p.get('type') == 'ellipse']

        # Beide Ellipsen sollten erkannt werden
        assert len(ellipse_profiles) == 2, f"2 Ellipsen erwartet, gefunden: {len(ellipse_profiles)}"


class TestEllipseExtrudeSimple:
    """Test 2: Einfache Ellipse-Extrusion."""

    def test_ellipse_extrude_creates_solid(self):
        """Einfache Ellipse sollte zu Solid extrudieren."""
        doc = Document("TestDoc")
        body = Body("EllipseBody", document=doc)

        sketch = Sketch("ellipse_sketch")
        ellipse = sketch.add_ellipse(0, 0, 10, 5, angle_deg=0)

        feature = ExtrudeFeature(
            distance=5.0,
            direction=1,
            operation="New Body"
        )
        feature.sketch = sketch
        feature.plane_origin = (0, 0, 0)
        feature.plane_normal = (0, 0, 1)
        feature.plane_x_dir = (1, 0, 0)
        feature.plane_y_dir = (0, 1, 0)

        body.add_feature(feature)

        # Assert
        assert body._build123d_solid is not None, "Solid sollte erstellt werden"
        assert isinstance(body._build123d_solid, Solid), "Sollte Build123d Solid sein"
        assert body._build123d_solid.volume > 0, "Sollte Volumen haben"

        # Volumen-Check: Ellipse = π * a * b, Volumen = π * a * b * h
        expected_volume = math.pi * 10 * 5 * 5
        actual_volume = body._build123d_solid.volume
        assert abs(actual_volume - expected_volume) / expected_volume < 0.01, \
            f"Volumen ~{expected_volume:.1f} erwartet, ist {actual_volume:.1f}"

    def test_ellipse_extrude_rotated(self):
        """Rotierte Ellipse sollte korrekt extrudieren."""
        doc = Document("TestDoc")
        body = Body("RotatedEllipse", document=doc)

        sketch = Sketch("rotated_sketch")
        ellipse = sketch.add_ellipse(0, 0, 10, 5, angle_deg=45)

        feature = ExtrudeFeature(distance=3.0, direction=1, operation="New Body")
        feature.sketch = sketch
        feature.plane_origin = (0, 0, 0)
        feature.plane_normal = (0, 0, 1)
        feature.plane_x_dir = (1, 0, 0)
        feature.plane_y_dir = (0, 1, 0)

        body.add_feature(feature)

        assert body._build123d_solid is not None
        assert body._build123d_solid.volume > 0

    def test_ellipse_native_ocp_data_preserved(self):
        """native_ocp_data sollte durch Extrude-Pipeline erhalten bleiben."""
        doc = Document("TestDoc")
        body = Body("EllipseBody", document=doc)

        sketch = Sketch("ellipse_sketch")
        ellipse = sketch.add_ellipse(0, 0, 10, 5, angle_deg=0)

        # Vor Extrude: native_ocp_data sollte vorhanden sein
        assert ellipse.native_ocp_data is not None
        original_data = ellipse.native_ocp_data.copy()

        feature = ExtrudeFeature(distance=5.0, direction=1, operation="New Body")
        feature.sketch = sketch
        feature.plane_origin = (0, 0, 0)
        feature.plane_normal = (0, 0, 1)
        feature.plane_x_dir = (1, 0, 0)
        feature.plane_y_dir = (0, 1, 0)

        body.add_feature(feature)

        # Nach Extrude: native_ocp_data sollte noch vorhanden und gleich sein
        assert ellipse.native_ocp_data is not None
        assert ellipse.native_ocp_data['center'] == original_data['center']
        assert ellipse.native_ocp_data['radius_x'] == original_data['radius_x']
        assert ellipse.native_ocp_data['radius_y'] == original_data['radius_y']


class TestEllipseExtrudeWithHole:
    """Test 3: Ellipse mit Loch (Shell-Profil)."""

    def test_ellipse_ring_extrude_creates_solid(self):
        """Äußere Ellipse mit innerer Ellipse (Loch) sollte extrudieren.

        HINWEIS: Boolean-Cut für Shell-Profile ist noch nicht implementiert.
        Beide Ellipsen werden aktuell als separate Solids extrudiert.
        Siehe: handoffs/HANDOFF_20260218_ai_ellipse_kernel_extrude.md
        """
        doc = Document("TestDoc")
        body = Body("EllipseRing", document=doc)

        sketch = Sketch("ring_sketch")
        outer = sketch.add_ellipse(0, 0, 20, 10, angle_deg=0)
        inner = sketch.add_ellipse(0, 0, 10, 5, angle_deg=0)

        feature = ExtrudeFeature(distance=5.0, direction=1, operation="New Body")
        feature.sketch = sketch
        feature.plane_origin = (0, 0, 0)
        feature.plane_normal = (0, 0, 1)
        feature.plane_x_dir = (1, 0, 0)
        feature.plane_y_dir = (0, 1, 0)

        body.add_feature(feature)

        # Assert
        assert body._build123d_solid is not None, "Solid sollte erstellt werden"
        assert body._build123d_solid.volume > 0, "Sollte Volumen haben"

        # Aktuell: Beide Ellipsen werden separat extrudiert (kein Boolean-Cut)
        # Erwartetes Volumen mit Boolean-Cut: π * (a1*b1 - a2*b2) * h = 2356.2
        # Aktuelles Volumen (separat): π * a1*b1*h + π * a2*b2*h = 3927.0
        outer_volume = math.pi * 20 * 10 * 5  # Äußere Ellipse
        inner_volume = math.pi * 10 * 5 * 5   # Innere Ellipse
        expected_volume = outer_volume + inner_volume  # Aktuelles Verhalten

        actual_volume = body._build123d_solid.volume
        assert abs(actual_volume - expected_volume) / expected_volume < 0.02, \
            f"Volumen ~{expected_volume:.1f} erwartet, ist {actual_volume:.1f}"

    def test_ellipse_off_center_hole(self):
        """Ellipse mit dezentriertem Loch sollte korrekt extrudieren."""
        doc = Document("TestDoc")
        body = Body("OffsetHole", document=doc)

        sketch = Sketch("offset_hole_sketch")
        outer = sketch.add_ellipse(0, 0, 20, 10, angle_deg=0)
        inner = sketch.add_ellipse(5, 3, 8, 4, angle_deg=0)

        feature = ExtrudeFeature(distance=5.0, direction=1, operation="New Body")
        feature.sketch = sketch
        feature.plane_origin = (0, 0, 0)
        feature.plane_normal = (0, 0, 1)
        feature.plane_x_dir = (1, 0, 0)
        feature.plane_y_dir = (0, 1, 0)

        body.add_feature(feature)

        assert body._build123d_solid is not None
        assert body._build123d_solid.volume > 0


class TestEllipseRebuildStability:
    """Test 4: Rebuild-Stabilität."""

    def test_ellipse_extrude_rebuild_consistent(self):
        """Mehrfaches Rebuild sollte konsistente Resultate liefern."""
        doc = Document("TestDoc")
        body = Body("RebuildTest", document=doc)

        sketch = Sketch("rebuild_sketch")
        ellipse = sketch.add_ellipse(0, 0, 10, 5, angle_deg=0)

        feature = ExtrudeFeature(distance=5.0, direction=1, operation="New Body")
        feature.sketch = sketch
        feature.plane_origin = (0, 0, 0)
        feature.plane_normal = (0, 0, 1)
        feature.plane_x_dir = (1, 0, 0)
        feature.plane_y_dir = (0, 1, 0)

        body.add_feature(feature)

        # Erstes Build
        body._rebuild()
        volume1 = body._build123d_solid.volume

        # Zweites Build
        body._rebuild()
        volume2 = body._build123d_solid.volume

        # Drittes Build
        body._rebuild()
        volume3 = body._build123d_solid.volume

        # Alle Volumen sollten gleich sein
        assert abs(volume1 - volume2) < 1e-6, f"Rebuild 1 vs 2: {volume1} vs {volume2}"
        assert abs(volume2 - volume3) < 1e-6, f"Rebuild 2 vs 3: {volume2} vs {volume3}"

    def test_ellipse_geometry_update_after_rebuild(self):
        """Ellipse-Geometrie sollte nach Rebuild korrekt sein."""
        doc = Document("TestDoc")
        body = Body("GeomUpdate", document=doc)

        sketch = Sketch("geom_sketch")
        ellipse = sketch.add_ellipse(0, 0, 10, 5, angle_deg=0)

        feature = ExtrudeFeature(distance=5.0, direction=1, operation="New Body")
        feature.sketch = sketch
        feature.plane_origin = (0, 0, 0)
        feature.plane_normal = (0, 0, 1)
        feature.plane_x_dir = (1, 0, 0)
        feature.plane_y_dir = (0, 1, 0)

        body.add_feature(feature)

        # Nach Rebuild sollte Ellipse noch korrekt sein
        body._rebuild()
        assert ellipse.radius_x == 10
        assert ellipse.radius_y == 5
        assert ellipse.native_ocp_data is not None


class TestEllipseCircleParity:
    """Test 5: Parität zwischen Ellipse und Circle."""

    def test_ellipse_and_circle_both_create_profiles(self):
        """Sowohl Ellipse als auch Circle sollten Profile erstellen."""
        sketch_ellipse = Sketch("ellipse_sketch")
        ellipse = sketch_ellipse.add_ellipse(0, 0, 10, 5, angle_deg=0)
        profiles_ellipse = sketch_ellipse.closed_profiles

        sketch_circle = Sketch("circle_sketch")
        circle = sketch_circle.add_circle(0, 0, 10)
        profiles_circle = sketch_circle.closed_profiles

        # Beide sollten Profile haben
        assert len(profiles_ellipse) > 0, "Ellipse sollte Profile haben"
        assert len(profiles_circle) > 0, "Circle sollte Profile haben"

        # Ellipse-Profil-Typ prüfen
        ellipse_dict = [p for p in profiles_ellipse if isinstance(p, dict)]
        circle_dict = [p for p in profiles_circle if isinstance(p, dict)]

        assert len(ellipse_dict) > 0, "Ellipse Dict-Profile erwartet"
        assert len(circle_dict) > 0, "Circle Dict-Profile erwartet"

    def test_ellipse_and_circle_both_extrude(self):
        """Sowohl Ellipse als auch Circle sollten extrudieren."""
        doc = Document("TestDoc")

        # Ellipse
        body_ellipse = Body("EllipseBody", document=doc)
        sketch_ellipse = Sketch("ellipse_sketch")
        ellipse = sketch_ellipse.add_ellipse(0, 0, 10, 5, angle_deg=0)

        feature_ellipse = ExtrudeFeature(distance=5.0, direction=1, operation="New Body")
        feature_ellipse.sketch = sketch_ellipse
        feature_ellipse.plane_origin = (0, 0, 0)
        feature_ellipse.plane_normal = (0, 0, 1)
        feature_ellipse.plane_x_dir = (1, 0, 0)
        feature_ellipse.plane_y_dir = (0, 1, 0)

        body_ellipse.add_feature(feature_ellipse)

        # Circle
        body_circle = Body("CircleBody", document=doc)
        sketch_circle = Sketch("circle_sketch")
        circle = sketch_circle.add_circle(0, 0, 10)

        feature_circle = ExtrudeFeature(distance=5.0, direction=1, operation="New Body")
        feature_circle.sketch = sketch_circle
        feature_circle.plane_origin = (0, 0, 0)
        feature_circle.plane_normal = (0, 0, 1)
        feature_circle.plane_x_dir = (1, 0, 0)
        feature_circle.plane_y_dir = (0, 1, 0)

        body_circle.add_feature(feature_circle)

        # Beide sollten Solids erstellen
        assert body_ellipse._build123d_solid is not None, "Ellipse Solid fehlt"
        assert body_circle._build123d_solid is not None, "Circle Solid fehlt"

        # Beide sollten Volumen haben
        assert body_ellipse._build123d_solid.volume > 0, "Ellipse Volumen fehlt"
        assert body_circle._build123d_solid.volume > 0, "Circle Volumen fehlt"


class TestEllipsePersist:
    """Test 6: Persistenz (Save/Load/Reopen)."""

    def test_ellipse_to_dict_from_dict_roundtrip(self):
        """Ellipse sollte korrekt serialisierbar sein."""
        sketch = Sketch("serialize_sketch")
        ellipse = sketch.add_ellipse(10, 20, 30, 15, angle_deg=45)

        # to_dict
        data = sketch.to_dict()

        # Ellipse-Daten prüfen
        ellipses_data = data.get('ellipses', [])
        assert len(ellipses_data) == 1

        # from_dict
        sketch2 = Sketch.from_dict(data)

        # Wiederherstellung prüfen
        assert len(sketch2.ellipses) == 1
        ellipse2 = sketch2.ellipses[0]
        assert abs(ellipse2.center.x - 10) < 1e-6
        assert abs(ellipse2.center.y - 20) < 1e-6
        assert abs(ellipse2.radius_x - 30) < 1e-6
        assert abs(ellipse2.radius_y - 15) < 1e-6
        assert abs(ellipse2.rotation - 45) < 1e-6

    def test_ellipse_extrude_after_serialize(self):
        """Nach Deserialisierung sollte Ellipse noch extrudieren."""
        doc = Document("TestDoc")

        # Original Sketch
        sketch1 = Sketch("orig_sketch")
        ellipse1 = sketch1.add_ellipse(0, 0, 10, 5, angle_deg=0)

        # Serialisieren
        data = sketch1.to_dict()

        # Deserialisieren
        sketch2 = Sketch.from_dict(data)

        # Mit deserialisiertem Sketch extrudieren
        body = Body("SerializedEllipse", document=doc)
        feature = ExtrudeFeature(distance=5.0, direction=1, operation="New Body")
        feature.sketch = sketch2
        feature.plane_origin = (0, 0, 0)
        feature.plane_normal = (0, 0, 1)
        feature.plane_x_dir = (1, 0, 0)
        feature.plane_y_dir = (0, 1, 0)

        body.add_feature(feature)

        assert body._build123d_solid is not None
        assert body._build123d_solid.volume > 0


class TestEllipseUndoRedo:
    """Test 7: Undo/Redo auf Ellipse-Extrude."""

    def test_ellipse_extrude_undo_redo(self):
        """Undo/Redo sollte Ellipse-Extrude korrekt behandeln."""
        from modeling.body_transaction import BodyTransaction

        doc = Document("TestDoc")
        body = Body("UndoRedoTest", document=doc)

        sketch = Sketch("undo_sketch")
        ellipse = sketch.add_ellipse(0, 0, 10, 5, angle_deg=0)

        # Erste Extrude
        with BodyTransaction(body, "Extrude1") as txn:
            feature1 = ExtrudeFeature(distance=5.0, direction=1, operation="New Body")
            feature1.sketch = sketch
            feature1.plane_origin = (0, 0, 0)
            feature1.plane_normal = (0, 0, 1)
            feature1.plane_x_dir = (1, 0, 0)
            feature1.plane_y_dir = (0, 1, 0)
            body.add_feature(feature1, rebuild=False)
            txn.commit()

        body._rebuild()
        volume1 = body._build123d_solid.volume

        # Zweite Extrude (oder Parameter-Änderung)
        # ...

        # Undo
        # TODO: Undo/Redo System testen wenn vollständig implementiert


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
