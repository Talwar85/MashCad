"""
Tests für das Transparenz-System: Geometry Delta, Operation Summary, Feature Detail Panel, Browser Badge.

Stellt sicher, dass nach jeder CAD-Operation beweisbare Metriken entstehen
und die GUI-Widgets diese korrekt darstellen.

Ausführung:
    pytest test/test_transparency_widgets.py -v
    pytest test/test_transparency_widgets.py -k "geometry_delta" -v
    pytest test/test_transparency_widgets.py -k "summary" -v
"""

import math
import os
import sys
import pytest
from unittest.mock import MagicMock, patch

from loguru import logger
from shapely.geometry import Polygon

from modeling import (
    Body, Document, ExtrudeFeature, FilletFeature, ChamferFeature,
    PrimitiveFeature,
)
from sketcher.sketch import Sketch


# ---------------------------------------------------------------------------
# Helpers (aus test_cad_workflow_trust.py übernommen)
# ---------------------------------------------------------------------------

def _make_doc_body(name="test"):
    doc = Document(name)
    body = Body(name=f"Body_{name}")
    doc.add_body(body, set_active=True)
    return doc, body


def _create_rectangle_sketch(width=40.0, height=30.0):
    sketch = Sketch("Rectangle")
    sketch.add_rectangle(0, 0, width, height)
    coords = [(0, 0), (width, 0), (width, height), (0, height), (0, 0)]
    sketch.closed_profiles = [Polygon(coords)]
    return sketch


def _add_box_base(body, width=40.0, height=30.0, depth=18.0):
    """Fügt eine Box als Basis-Feature hinzu."""
    sketch = _create_rectangle_sketch(width, height)
    feat = ExtrudeFeature(
        sketch=sketch,
        distance=depth,
        operation="NewBody",
    )
    body.add_feature(feat, rebuild=True)
    assert feat.status in ("OK", "SUCCESS", "WARNING"), f"Box base failed: {feat.status_message}"
    assert body._build123d_solid is not None, "Box solid is None after extrude"
    return feat


def _top_edge_indices(solid, limit=4):
    """Gibt Indices der obersten Kanten zurück."""
    edges = list(solid.edges())
    if not edges:
        return []
    scored = []
    for idx, e in enumerate(edges):
        try:
            c = e.center()
            scored.append((idx, c.Z))
        except Exception:
            pass
    scored.sort(key=lambda x: x[1], reverse=True)
    return [idx for idx, _ in scored[:limit]]


def _is_success(status):
    return status in ("OK", "SUCCESS", "WARNING")


# ===========================================================================
# STUFE 1: Geometry Delta Pipeline (Backend / modeling/__init__.py)
# ===========================================================================

class TestGeometryDeltaPipeline:
    """Prüft dass _geometry_delta nach _rebuild() auf jedem Feature gesetzt wird."""

    def test_extrude_base_has_delta(self):
        """Erstes Feature (Extrude) bekommt _geometry_delta mit volume_before=0."""
        doc, body = _make_doc_body("delta_base")
        feat = _add_box_base(body)

        gd = getattr(feat, '_geometry_delta', None)
        assert gd is not None, "Extrude-Feature hat kein _geometry_delta"
        assert gd["volume_before"] == 0.0, f"Base-Feature: volume_before sollte 0 sein, ist {gd['volume_before']}"
        assert gd["volume_after"] > 0, f"Base-Feature: volume_after sollte > 0 sein"
        assert gd["faces_after"] > 0, "Keine Flächen nach Extrude"
        assert gd["edges_after"] > 0, "Keine Kanten nach Extrude"

    def test_chamfer_has_volume_decrease(self):
        """Chamfer verringert Volume → negative volume_pct."""
        pytest.importorskip("OCP.BRepFilletAPI")

        doc, body = _make_doc_body("delta_chamfer")
        _add_box_base(body)

        edges = _top_edge_indices(body._build123d_solid, limit=4)
        assert len(edges) > 0, "Keine Kanten für Chamfer gefunden"

        chamfer = ChamferFeature(distance=0.8, edge_indices=edges)
        body.add_feature(chamfer, rebuild=True)
        assert _is_success(chamfer.status), f"Chamfer fehlgeschlagen: {chamfer.status_message}"

        gd = getattr(chamfer, '_geometry_delta', None)
        assert gd is not None, "Chamfer hat kein _geometry_delta"
        assert gd["volume_pct"] < 0, f"Chamfer sollte Volume verringern, pct={gd['volume_pct']}"
        assert gd["volume_before"] > gd["volume_after"], "volume_before sollte > volume_after"
        assert gd["faces_delta"] > 0, "Chamfer sollte Flächen hinzufügen"
        assert gd["edges_delta"] > 0, "Chamfer sollte Kanten hinzufügen"

    def test_fillet_has_volume_decrease(self):
        """Fillet verringert Volume → negative volume_pct."""
        pytest.importorskip("OCP.BRepFilletAPI")

        doc, body = _make_doc_body("delta_fillet")
        _add_box_base(body)

        edges = _top_edge_indices(body._build123d_solid, limit=2)
        assert len(edges) > 0

        fillet = FilletFeature(radius=0.5, edge_indices=edges)
        body.add_feature(fillet, rebuild=True)
        assert _is_success(fillet.status), f"Fillet fehlgeschlagen: {fillet.status_message}"

        gd = getattr(fillet, '_geometry_delta', None)
        assert gd is not None, "Fillet hat kein _geometry_delta"
        assert gd["volume_pct"] <= 0, f"Fillet sollte Volume verringern oder halten, pct={gd['volume_pct']}"
        assert gd["faces_delta"] > 0, "Fillet sollte Flächen hinzufügen"

    def test_rebuild_reproduces_deltas(self):
        """Erneuter _rebuild() erzeugt identische _geometry_delta Werte."""
        doc, body = _make_doc_body("delta_rebuild")
        _add_box_base(body)

        edges = _top_edge_indices(body._build123d_solid, limit=2)
        if edges:
            chamfer = ChamferFeature(distance=0.5, edge_indices=edges)
            body.add_feature(chamfer, rebuild=True)

        # Erste Delta-Werte merken
        deltas_first = []
        for f in body.features:
            gd = getattr(f, '_geometry_delta', None)
            deltas_first.append(gd.copy() if gd else None)

        # Rebuild und vergleichen
        body._rebuild()
        for i, f in enumerate(body.features):
            gd = getattr(f, '_geometry_delta', None)
            if deltas_first[i] is not None:
                assert gd is not None, f"Feature {i} hat nach Rebuild kein _geometry_delta"
                assert abs(gd["volume_pct"] - deltas_first[i]["volume_pct"]) < 0.01, \
                    f"Feature {i}: volume_pct divergiert nach Rebuild"

    def test_error_feature_gets_none_or_unchanged_delta(self):
        """Feature mit ERROR-Status bekommt _geometry_delta (Volume unverändert)."""
        doc, body = _make_doc_body("delta_error")
        _add_box_base(body)

        # Ungültige Edge-Indices → wahrscheinlich Error/Warning
        chamfer = ChamferFeature(distance=5.0, edge_indices=[999, 998])
        body.add_feature(chamfer, rebuild=True)

        gd = getattr(chamfer, '_geometry_delta', None)
        # Bei Error: entweder None oder volume_pct == 0
        if chamfer.status == "ERROR":
            if gd is not None:
                assert abs(gd["volume_pct"]) < 0.1, "Error-Feature sollte kein Volume-Delta haben"

    def test_progress_callback_called(self):
        """progress_callback wird für jedes Feature aufgerufen."""
        doc, body = _make_doc_body("delta_progress")
        _add_box_base(body)

        # Zweites Feature hinzufügen
        sketch2 = _create_rectangle_sketch(20, 15)
        feat2 = ExtrudeFeature(sketch=sketch2, distance=5.0, operation="Join")
        body.add_feature(feat2, rebuild=True)

        calls = []

        def on_progress(current, total, name):
            calls.append((current, total, name))

        body._rebuild(progress_callback=on_progress)

        assert len(calls) == len(body.features), \
            f"progress_callback {len(calls)}x aufgerufen, erwartet {len(body.features)}"
        for i, (current, total, name) in enumerate(calls):
            assert current == i
            assert total == len(body.features)
            assert isinstance(name, str)

    def test_rollback_sets_no_delta_for_rolledback_features(self):
        """Rolled-back Features haben status ROLLED_BACK, _geometry_delta ist irrelevant."""
        doc, body = _make_doc_body("delta_rollback")
        _add_box_base(body)

        edges = _top_edge_indices(body._build123d_solid, limit=2)
        if edges:
            chamfer = ChamferFeature(distance=0.5, edge_indices=edges)
            body.add_feature(chamfer, rebuild=True)

        # Rollback auf Feature 0 (nur Base)
        body._rebuild(rebuild_up_to=1)
        for i, f in enumerate(body.features):
            if i >= 1:
                assert f.status == "ROLLED_BACK", f"Feature {i} sollte ROLLED_BACK sein"

    def test_delta_keys_complete(self):
        """_geometry_delta hat alle erwarteten Keys."""
        doc, body = _make_doc_body("delta_keys")
        _add_box_base(body)

        gd = body.features[0]._geometry_delta
        expected_keys = {
            "volume_before", "volume_after", "volume_pct",
            "faces_before", "faces_after", "faces_delta",
            "edges_before", "edges_after", "edges_delta",
        }
        assert gd is not None
        assert set(gd.keys()) == expected_keys, f"Keys mismatch: {set(gd.keys())} vs {expected_keys}"


# ===========================================================================
# STUFE 2: Operation Summary Widget
# ===========================================================================

@pytest.mark.unit
class TestOperationSummaryWidget:
    """Tests für OperationSummaryWidget — rein logische Prüfung ohne Display."""

    @pytest.fixture(autouse=True)
    def _setup_qapp(self):
        """Stellt sicher dass QApplication existiert."""
        from PySide6.QtWidgets import QApplication
        app = QApplication.instance()
        if app is None:
            app = QApplication([])
        yield

    def test_create_widget(self):
        from gui.widgets.operation_summary import OperationSummaryWidget
        widget = OperationSummaryWidget()
        assert widget is not None
        assert widget.isHidden()  # Initial versteckt

    def test_show_summary_success(self):
        """Erfolgreiche Operation → grünes Icon, Volume-Text."""
        from gui.widgets.operation_summary import OperationSummaryWidget
        widget = OperationSummaryWidget()

        pre = {"volume": 20000.0, "faces": 6, "edges": 12}
        post = {"volume": 19700.0, "faces": 10, "edges": 20}

        widget.show_summary("Chamfer D=0.8mm", pre, post)

        assert widget._icon_label.text() == "✓"
        assert "Chamfer" in widget._title_label.text()
        vol_text = widget._volume_label.text()
        assert "20000" in vol_text
        assert "19700" in vol_text
        assert "−1.5%" in vol_text or "-1.5%" in vol_text

    def test_show_summary_error_feature(self):
        """Feature mit ERROR-Status → rotes Icon."""
        from gui.widgets.operation_summary import OperationSummaryWidget
        widget = OperationSummaryWidget()

        pre = {"volume": 20000.0, "faces": 6, "edges": 12}
        post = {"volume": 20000.0, "faces": 6, "edges": 12}

        # Konkretes Objekt statt MagicMock (PySide6 akzeptiert kein MagicMock für setText)
        class FakeFeature:
            status = "ERROR"
            _geometry_delta = None
            status_details = {}
            status_message = "Edge not found"

        widget.show_summary("Fillet R=2.0", pre, post, feature=FakeFeature())

        assert widget._icon_label.text() == "✕"

    def test_show_summary_warning_feature(self):
        """Feature mit WARNING-Status → gelbes Icon."""
        from gui.widgets.operation_summary import OperationSummaryWidget
        widget = OperationSummaryWidget()

        pre = {"volume": 20000.0, "faces": 6, "edges": 12}
        post = {"volume": 19900.0, "faces": 8, "edges": 16}

        class FakeFeature:
            status = "WARNING"
            _geometry_delta = {"edges_ok": 2, "edges_total": 4}
            status_details = {}
            status_message = ""

        widget.show_summary("Chamfer D=0.5", pre, post, feature=FakeFeature())

        assert widget._icon_label.text() == "⚠"

    def test_show_summary_unchanged_volume(self):
        """Volume unverändert → zeigt 'unverändert'."""
        from gui.widgets.operation_summary import OperationSummaryWidget
        widget = OperationSummaryWidget()

        pre = {"volume": 20000.0, "faces": 6, "edges": 12}
        post = {"volume": 20000.0, "faces": 6, "edges": 12}

        widget.show_summary("Test Op", pre, post)

        vol_text = widget._volume_label.text().lower()
        assert "unver" in vol_text or "unchanged" in vol_text

    def test_show_summary_faces_edges_delta(self):
        """Faces/Edges Delta wird angezeigt."""
        from gui.widgets.operation_summary import OperationSummaryWidget
        widget = OperationSummaryWidget()

        pre = {"volume": 20000.0, "faces": 6, "edges": 12}
        post = {"volume": 19800.0, "faces": 10, "edges": 20}

        widget.show_summary("Chamfer", pre, post)

        fe_text = widget._faces_edges_label.text()
        assert "+4" in fe_text or "10" in fe_text, f"Faces-Delta nicht in Text: {fe_text}"
        assert "+8" in fe_text or "20" in fe_text, f"Edges-Delta nicht in Text: {fe_text}"

    def test_show_summary_edge_progress_bar(self):
        """Bei Feature mit edges_ok/edges_total wird Progress-Bar gezeigt."""
        from gui.widgets.operation_summary import OperationSummaryWidget
        widget = OperationSummaryWidget()

        pre = {"volume": 20000.0, "faces": 6, "edges": 12}
        post = {"volume": 19800.0, "faces": 10, "edges": 20}

        feature = MagicMock()
        feature.status = "OK"
        feature._geometry_delta = {"edges_ok": 4, "edges_total": 4}
        feature.status_details = {}

        widget.show_summary("Chamfer", pre, post, feature=feature)

        assert widget._progress_label.isVisible()
        assert "100%" in widget._progress_label.text()

    def test_auto_close_timer_starts(self):
        """Timer für Auto-Close wird gestartet."""
        from gui.widgets.operation_summary import OperationSummaryWidget
        widget = OperationSummaryWidget()

        pre = {"volume": 20000.0, "faces": 6, "edges": 12}
        post = {"volume": 19800.0, "faces": 10, "edges": 20}

        widget.show_summary("Test", pre, post)

        assert widget._timer.isActive()


# ===========================================================================
# STUFE 3: Feature Detail Panel
# ===========================================================================

@pytest.mark.unit
class TestFeatureDetailPanel:
    """Tests für FeatureDetailPanel."""

    @pytest.fixture(autouse=True)
    def _setup_qapp(self):
        from PySide6.QtWidgets import QApplication
        app = QApplication.instance()
        if app is None:
            app = QApplication([])
        yield

    def test_create_panel(self):
        from gui.widgets.feature_detail_panel import FeatureDetailPanel
        panel = FeatureDetailPanel()
        assert panel is not None

    def test_show_feature_none_hides_sections(self):
        """show_feature(None) versteckt alle Sektionen."""
        from gui.widgets.feature_detail_panel import FeatureDetailPanel
        panel = FeatureDetailPanel()
        panel.show()  # Parent muss sichtbar sein damit isVisible() korrekt funktioniert
        panel.show_feature(None)

        assert panel._status_label.isHidden()
        assert panel._geo_header.isHidden()
        assert panel._edge_header.isHidden()
        assert panel._tnp_header.isHidden()

    def test_show_feature_with_delta(self):
        """Feature mit _geometry_delta zeigt Geometry-Sektion."""
        from gui.widgets.feature_detail_panel import FeatureDetailPanel
        panel = FeatureDetailPanel()
        panel.show()

        class FakeFeature:
            name = "Chamfer D=0.8"
            status = "OK"
            status_message = ""
            status_details = {}
            edge_indices = None
            _geometry_delta = {
                "volume_before": 20000.0,
                "volume_after": 19700.0,
                "volume_pct": -1.5,
                "faces_before": 6,
                "faces_after": 10,
                "faces_delta": 4,
                "edges_before": 12,
                "edges_after": 20,
                "edges_delta": 8,
            }

        panel.show_feature(FakeFeature())

        assert not panel._geo_header.isHidden()
        assert not panel._geo_volume.isHidden()
        assert "19700" in panel._geo_volume.text() or "20000" in panel._geo_volume.text()
        assert not panel._geo_faces.isHidden()
        assert "+4" in panel._geo_faces.text()

    def test_show_feature_error_status(self):
        """ERROR-Feature zeigt roten Status."""
        from gui.widgets.feature_detail_panel import FeatureDetailPanel
        panel = FeatureDetailPanel()
        panel.show()

        class FakeFeature:
            name = "Fillet R=2.0"
            status = "ERROR"
            status_message = "Edge nicht gefunden"
            status_details = {}
            edge_indices = None
            _geometry_delta = None

        panel.show_feature(FakeFeature())

        assert not panel._status_label.isHidden()
        assert "ERROR" in panel._status_label.text()
        assert "Edge nicht gefunden" in panel._status_label.text()

    def test_show_feature_with_edge_indices(self):
        """Feature mit edge_indices zeigt Kanten-Sektion."""
        from gui.widgets.feature_detail_panel import FeatureDetailPanel
        panel = FeatureDetailPanel()
        panel.show()

        doc, body = _make_doc_body("detail_edges")
        _add_box_base(body)

        class FakeFeature:
            name = "Chamfer"
            status = "OK"
            status_message = ""
            status_details = {}
            edge_indices = [0, 1, 2]
            _geometry_delta = None

        panel.show_feature(FakeFeature(), body=body)

        assert not panel._edge_header.isHidden()
        assert not panel._edge_scroll.isHidden()
        assert not panel._btn_show_edges.isHidden()

    def test_highlight_signal_emitted(self):
        """'Kanten anzeigen' Button emittiert highlight_edges_requested."""
        from gui.widgets.feature_detail_panel import FeatureDetailPanel
        panel = FeatureDetailPanel()

        signals = []
        panel.highlight_edges_requested.connect(lambda x: signals.append(x))

        class FakeFeature:
            edge_indices = [3, 7, 11]

        panel._current_feature = FakeFeature()
        panel._on_show_edges()

        assert len(signals) == 1
        assert signals[0] == [3, 7, 11]

    def test_show_feature_without_delta_hides_geo_section(self):
        """Feature ohne _geometry_delta versteckt Geometry-Sektion."""
        from gui.widgets.feature_detail_panel import FeatureDetailPanel
        panel = FeatureDetailPanel()
        panel.show()

        class FakeFeature:
            name = "Import"
            status = "OK"
            status_message = ""
            edge_indices = None
            _geometry_delta = None

        panel.show_feature(FakeFeature())

        assert panel._geo_header.isHidden()
        assert panel._geo_volume.isHidden()

    def test_clear_resets_panel(self):
        """clear() setzt Panel zurück."""
        from gui.widgets.feature_detail_panel import FeatureDetailPanel
        panel = FeatureDetailPanel()
        panel.show()

        class FakeFeature:
            name = "Test"
            status = "OK"
            status_message = ""
            edge_indices = None
            _geometry_delta = {"volume_before": 100, "volume_after": 200, "volume_pct": 100.0,
                               "faces_before": 4, "faces_after": 6, "faces_delta": 2,
                               "edges_before": 8, "edges_after": 12, "edges_delta": 4}

        panel.show_feature(FakeFeature())
        assert not panel._geo_header.isHidden()

        # Dann clear
        panel.clear()
        assert panel._geo_header.isHidden()


# ===========================================================================
# STUFE 4: Browser Badge Logik
# ===========================================================================

class TestBrowserBadge:
    """Testet die Badge-Generierung aus _geometry_delta Daten."""

    def _compute_badge(self, gd, rolled_back=False):
        """Extrahierte Badge-Logik aus browser.py _add_bodies_to_tree()."""
        badge = ""
        if gd and not rolled_back:
            vol_pct = gd.get("volume_pct", 0)
            if vol_pct != 0:
                sign = "+" if vol_pct > 0 else ""
                badge = f"  Vol{sign}{vol_pct:.1f}%"
            elif gd.get("faces_delta", 0) != 0:
                fd = gd["faces_delta"]
                badge = f"  {'+' if fd > 0 else ''}{fd}F"
            edges_ok = gd.get("edges_ok")
            edges_total = gd.get("edges_total")
            if edges_total is not None and edges_total > 0:
                if edges_ok is not None and edges_ok < edges_total:
                    badge = f"  ⚠ {edges_ok}/{edges_total}{badge}"
        return badge

    def test_positive_volume(self):
        gd = {"volume_pct": 11.2, "faces_delta": 6, "edges_delta": 12}
        badge = self._compute_badge(gd)
        assert badge == "  Vol+11.2%"

    def test_negative_volume(self):
        gd = {"volume_pct": -1.6, "faces_delta": 4, "edges_delta": 8}
        badge = self._compute_badge(gd)
        assert badge == "  Vol-1.6%"

    def test_zero_volume_with_faces(self):
        """Volume unverändert aber Faces geändert → zeigt Faces-Badge."""
        gd = {"volume_pct": 0.0, "faces_delta": 2, "edges_delta": 4}
        badge = self._compute_badge(gd)
        assert badge == "  +2F"

    def test_zero_volume_negative_faces(self):
        gd = {"volume_pct": 0.0, "faces_delta": -1, "edges_delta": 0}
        badge = self._compute_badge(gd)
        assert badge == "  -1F"

    def test_all_zero(self):
        """Kein Delta → leerer Badge."""
        gd = {"volume_pct": 0.0, "faces_delta": 0, "edges_delta": 0}
        badge = self._compute_badge(gd)
        assert badge == ""

    def test_rolled_back_no_badge(self):
        """Rolled-back Feature → kein Badge."""
        gd = {"volume_pct": -1.6, "faces_delta": 4, "edges_delta": 8}
        badge = self._compute_badge(gd, rolled_back=True)
        assert badge == ""

    def test_none_delta_no_badge(self):
        badge = self._compute_badge(None)
        assert badge == ""

    def test_edge_warning_badge(self):
        """Unvollständige Edge-Bearbeitung → Warning-Badge."""
        gd = {"volume_pct": -0.8, "faces_delta": 2, "edges_delta": 4,
              "edges_ok": 2, "edges_total": 4}
        badge = self._compute_badge(gd)
        assert "⚠" in badge
        assert "2/4" in badge
        assert "Vol" in badge

    def test_all_edges_ok_no_warning(self):
        """Alle Edges OK → kein Warning."""
        gd = {"volume_pct": -1.6, "faces_delta": 4, "edges_delta": 8,
              "edges_ok": 4, "edges_total": 4}
        badge = self._compute_badge(gd)
        assert "⚠" not in badge
        assert "Vol-1.6%" in badge


# ===========================================================================
# STUFE 5: Integration - Geometry Delta nach echtem CAD-Workflow
# ===========================================================================

class TestGeometryDeltaIntegration:
    """End-to-End: Voller Workflow → alle Features haben korrekte Deltas."""

    def test_box_chamfer_workflow(self):
        """Box → Chamfer: Beide Features haben sinnvolle _geometry_delta."""
        pytest.importorskip("OCP.BRepFilletAPI")

        doc, body = _make_doc_body("integration_workflow")
        _add_box_base(body)

        edges = _top_edge_indices(body._build123d_solid, limit=4)
        chamfer = ChamferFeature(distance=0.8, edge_indices=edges)
        body.add_feature(chamfer, rebuild=True)
        assert _is_success(chamfer.status)

        # Feature 0: Extrude (Base)
        gd0 = body.features[0]._geometry_delta
        assert gd0 is not None
        assert gd0["volume_before"] == 0.0
        assert gd0["volume_after"] > 0

        # Feature 1: Chamfer
        gd1 = body.features[1]._geometry_delta
        assert gd1 is not None
        assert gd1["volume_pct"] < 0, "Chamfer sollte Volume verringern"
        assert gd1["faces_delta"] > 0, "Chamfer sollte Flächen hinzufügen"
        assert gd1["volume_before"] == gd0["volume_after"], \
            "Chamfer volume_before sollte == Extrude volume_after sein"

    def test_multiple_features_chain(self):
        """Mehrere Features: volume_after[n] == volume_before[n+1]."""
        pytest.importorskip("OCP.BRepFilletAPI")

        doc, body = _make_doc_body("chain")
        _add_box_base(body, width=40, height=30, depth=20)

        # Zweites Feature: kleiner Chamfer
        edges = _top_edge_indices(body._build123d_solid, limit=2)
        if edges:
            chamfer = ChamferFeature(distance=0.3, edge_indices=edges)
            body.add_feature(chamfer, rebuild=True)

        # Chain-Validierung
        for i in range(len(body.features) - 1):
            gd_curr = getattr(body.features[i], '_geometry_delta', None)
            gd_next = getattr(body.features[i + 1], '_geometry_delta', None)
            if gd_curr and gd_next and gd_curr["volume_after"] > 0:
                assert abs(gd_curr["volume_after"] - gd_next["volume_before"]) < 0.1, \
                    f"Volume-Chain gebrochen zwischen Feature {i} und {i + 1}: " \
                    f"{gd_curr['volume_after']} vs {gd_next['volume_before']}"

    def test_save_load_rebuild_restores_deltas(self):
        """Save → Load → Rebuild: PrimitiveFeature-basiert (serialisiert korrekt)."""
        doc, body = _make_doc_body("save_load")
        prim = PrimitiveFeature(primitive_type="box", length=20.0, width=15.0, height=10.0)
        body.add_feature(prim, rebuild=True)
        assert _is_success(prim.status)

        # Deltas merken
        orig_deltas = []
        for f in body.features:
            gd = getattr(f, '_geometry_delta', None)
            orig_deltas.append(gd.copy() if gd else None)

        # Save/Load via to_dict/from_dict
        body_dict = body.to_dict()
        restored = Body.from_dict(body_dict)
        clone_doc = Document("clone")
        clone_doc.add_body(restored, set_active=True)
        restored._rebuild()

        for i, f in enumerate(restored.features):
            gd = getattr(f, '_geometry_delta', None)
            if orig_deltas[i] is not None:
                assert gd is not None, f"Feature {i}: _geometry_delta fehlt nach Load"
                assert abs(gd["volume_pct"] - orig_deltas[i]["volume_pct"]) < 0.1, \
                    f"Feature {i}: volume_pct divergiert nach Load " \
                    f"({gd['volume_pct']} vs {orig_deltas[i]['volume_pct']})"

    def test_primitive_feature_has_delta(self):
        """PrimitiveFeature (Box) bekommt _geometry_delta."""
        doc, body = _make_doc_body("primitive_delta")
        prim = PrimitiveFeature(primitive_type="box", length=10.0, width=10.0, height=10.0)
        body.add_feature(prim, rebuild=True)
        assert _is_success(prim.status)

        gd = getattr(prim, '_geometry_delta', None)
        assert gd is not None, "PrimitiveFeature hat kein _geometry_delta"
        assert gd["volume_after"] > 0
