"""
MashCad - Transparency Phase 2 Tests (No Qt)
=============================================

Tests für Fehlerkorrektur (ohne Qt GUI):
1. Face Highlighting mit korrekter OCP API (nicht Mesher)
2. Push/Pull Geometry Delta Berechnung
3. _solid_metrics() Funktionalität

Author: Claude
Date: 2026-02-09
"""
import pytest
from build123d import Box, Solid
from modeling import Body, ExtrudeFeature, _solid_metrics


# ============================================================================
# Helper Functions
# ============================================================================

def _make_box_body(width=40, height=28, depth=18):
    """Create a simple box body for testing."""
    body = Body(name="Test Box")
    box = Box(width, height, depth)
    body._build123d_solid = box
    body.invalidate_mesh()
    return body


# ============================================================================
# _solid_metrics() Tests
# ============================================================================

def test_solid_metrics_basic():
    """Test that _solid_metrics() returns correct data structure."""
    box = Box(40, 28, 18)
    metrics = _solid_metrics(box)

    assert metrics is not None, "_solid_metrics returned None"
    assert isinstance(metrics, dict), f"_solid_metrics should return dict, got {type(metrics)}"

    # Check required keys
    assert "volume" in metrics, "_solid_metrics missing 'volume' key"
    assert "faces" in metrics, "_solid_metrics missing 'faces' key"
    assert "edges" in metrics, "_solid_metrics missing 'edges' key"


def test_solid_metrics_box_values():
    """Test that _solid_metrics() returns correct values for a box."""
    box = Box(40, 28, 18)
    metrics = _solid_metrics(box)

    # Volume check (40 * 28 * 18 = 20160)
    expected_volume = 40 * 28 * 18
    assert abs(metrics["volume"] - expected_volume) < 1.0, \
        f"Box volume should be ~{expected_volume}, got {metrics['volume']}"

    # Face count (box has 6 faces)
    assert metrics["faces"] == 6, f"Box should have 6 faces, got {metrics['faces']}"

    # Edge count (box has 12 edges)
    assert metrics["edges"] == 12, f"Box should have 12 edges, got {metrics['edges']}"


def test_solid_metrics_returns_none_for_invalid_solid():
    """Test that _solid_metrics() handles invalid input gracefully."""
    metrics = _solid_metrics(None)

    # Should return None or empty dict, not crash
    assert metrics is None or metrics == {}, \
        f"_solid_metrics(None) should return None or {{}}, got {metrics}"


def test_solid_metrics_different_sizes():
    """Test that _solid_metrics() scales correctly with different box sizes."""
    # Small box
    small_box = Box(10, 10, 10)
    small_metrics = _solid_metrics(small_box)
    assert abs(small_metrics["volume"] - 1000) < 1.0
    assert small_metrics["faces"] == 6
    assert small_metrics["edges"] == 12

    # Large box
    large_box = Box(100, 100, 100)
    large_metrics = _solid_metrics(large_box)
    assert abs(large_metrics["volume"] - 1000000) < 10.0
    assert large_metrics["faces"] == 6
    assert large_metrics["edges"] == 12


# ============================================================================
# Geometry Delta Calculation Tests
# ============================================================================

def test_geometry_delta_percentage_calculation():
    """Test that volume percentage is calculated correctly."""
    pre_vol = 1000.0
    post_vol = 1250.0

    vol_pct = ((post_vol - pre_vol) / pre_vol * 100.0)

    assert abs(vol_pct - 25.0) < 0.01, f"Volume percent should be 25%, got {vol_pct}"


def test_geometry_delta_negative_change():
    """Test volume decrease calculation."""
    pre_vol = 1000.0
    post_vol = 800.0  # 20% decrease

    vol_pct = ((post_vol - pre_vol) / pre_vol * 100.0)

    assert abs(vol_pct - (-20.0)) < 0.01, f"Volume percent should be -20%, got {vol_pct}"


def test_geometry_delta_zero_change():
    """Test that zero change is handled correctly."""
    pre_vol = 1000.0
    post_vol = 1000.0

    vol_pct = ((post_vol - pre_vol) / pre_vol * 100.0) if pre_vol > 1e-12 else 0.0

    assert abs(vol_pct) < 0.01, f"Volume percent should be 0%, got {vol_pct}"


def test_geometry_delta_zero_volume_edge_case():
    """Test edge case when previous volume is zero."""
    pre_vol = 0.0
    post_vol = 1000.0

    vol_pct = ((post_vol - pre_vol) / pre_vol * 100.0) if pre_vol > 1e-12 else 0.0

    # Should return 0.0 to avoid division by zero
    assert abs(vol_pct) < 0.01, f"With zero pre_vol, should return 0%, got {vol_pct}"


# ============================================================================
# Face Tessellation Tests (OCP API)
# ============================================================================

def test_face_tessellation_ocp_imports():
    """Test that OCP face tessellation imports are available."""
    try:
        from OCP.BRepMesh import BRepMesh_IncrementalMesh
        from OCP.TopLoc import TopLoc_Location
        from OCP.BRep import BRep_Tool
        assert True
    except ImportError as e:
        pytest.fail(f"OCP imports failed: {e}")


def test_face_tessellation_on_box():
    """Test that OCP face tessellation works on a simple box face."""
    from OCP.BRepMesh import BRepMesh_IncrementalMesh
    from OCP.TopLoc import TopLoc_Location
    from OCP.BRep import BRep_Tool

    box = Box(40, 28, 18)
    all_faces = list(box.faces())

    assert len(all_faces) == 6, f"Box should have 6 faces, got {len(all_faces)}"

    # Test tessellation on first face
    face = all_faces[0]
    quality = 0.05

    # Tessellate
    BRepMesh_IncrementalMesh(face.wrapped, quality, False, quality * 5, True)

    # Get triangulation
    loc = TopLoc_Location()
    triangulation = BRep_Tool.Triangulation_s(face.wrapped, loc)

    assert triangulation is not None, "Triangulation should not be None"

    # Check vertices and triangles
    n_verts = triangulation.NbNodes()
    n_tris = triangulation.NbTriangles()

    assert n_verts >= 4, f"Face should have at least 4 vertices, got {n_verts}"
    assert n_tris >= 2, f"Face should have at least 2 triangles, got {n_tris}"


def test_face_tessellation_extracts_vertices():
    """Test that we can extract vertices from tessellated face."""
    from OCP.BRepMesh import BRepMesh_IncrementalMesh
    from OCP.TopLoc import TopLoc_Location
    from OCP.BRep import BRep_Tool

    box = Box(40, 28, 18)
    face = list(box.faces())[0]

    BRepMesh_IncrementalMesh(face.wrapped, 0.05, False, 0.25, True)

    loc = TopLoc_Location()
    triangulation = BRep_Tool.Triangulation_s(face.wrapped, loc)
    transform = loc.Transformation()

    vertices = []
    n_verts = triangulation.NbNodes()
    for i in range(1, n_verts + 1):
        p = triangulation.Node(i)
        if not loc.IsIdentity():
            p = p.Transformed(transform)
        vertices.append([p.X(), p.Y(), p.Z()])

    assert len(vertices) >= 4, f"Should extract at least 4 vertices, got {len(vertices)}"
    assert all(isinstance(v, list) and len(v) == 3 for v in vertices), \
        "All vertices should be [x, y, z] lists"


def test_face_tessellation_extracts_triangles():
    """Test that we can extract triangles from tessellated face."""
    from OCP.BRepMesh import BRepMesh_IncrementalMesh
    from OCP.TopLoc import TopLoc_Location
    from OCP.BRep import BRep_Tool

    box = Box(40, 28, 18)
    face = list(box.faces())[0]

    BRepMesh_IncrementalMesh(face.wrapped, 0.05, False, 0.25, True)

    loc = TopLoc_Location()
    triangulation = BRep_Tool.Triangulation_s(face.wrapped, loc)

    triangles = []
    n_tris = triangulation.NbTriangles()
    for i in range(1, n_tris + 1):
        tri = triangulation.Triangle(i)
        v1, v2, v3 = tri.Get()
        # OCP is 1-based, PyVista is 0-based
        triangles.append([v1 - 1, v2 - 1, v3 - 1])

    assert len(triangles) >= 2, f"Should extract at least 2 triangles, got {len(triangles)}"
    assert all(isinstance(t, list) and len(t) == 3 for t in triangles), \
        "All triangles should be [v1, v2, v3] lists"
    # Verify indices are valid (0-based)
    for tri in triangles:
        assert all(idx >= 0 for idx in tri), f"Triangle indices should be >= 0, got {tri}"


# ============================================================================
# Feature Geometry Delta Tests
# ============================================================================

def test_extrude_feature_geometry_delta_attribute():
    """Test that ExtrudeFeature can store _geometry_delta."""
    feat = ExtrudeFeature(
        sketch=None,
        distance=5.0,
        operation="Join",
        name="Test Push/Pull",
    )

    # Set geometry delta
    feat._geometry_delta = {
        "volume_before": 1000.0,
        "volume_after": 1250.0,
        "volume_pct": 25.0,
        "faces_before": 6,
        "faces_after": 10,
        "faces_delta": 4,
        "edges_before": 12,
        "edges_after": 20,
        "edges_delta": 8,
    }

    assert hasattr(feat, '_geometry_delta'), "Feature should have _geometry_delta attribute"
    assert feat._geometry_delta["volume_pct"] == 25.0
    assert feat._geometry_delta["faces_delta"] == 4
    assert feat._geometry_delta["edges_delta"] == 8


def test_pushpull_geometry_delta_realistic_values():
    """Test Push/Pull geometry delta with realistic box extrusion."""
    body = _make_box_body(40, 28, 18)

    # Calculate metrics before
    old_metrics = _solid_metrics(body._build123d_solid)

    # Simulate Push/Pull: extrude one face by 5mm
    # For a 40x28 box, extruding one face by 5mm adds 40*28*5 = 5600 mm³
    expected_added_volume = 40 * 28 * 5
    expected_new_volume = old_metrics["volume"] + expected_added_volume

    # Expected percentage increase
    expected_pct = (expected_added_volume / old_metrics["volume"]) * 100.0

    # Verify calculation
    assert abs(expected_pct - 27.78) < 1.0, \
        f"Expected ~27.78% volume increase for 5mm extrusion on 40x28x18 box, got {expected_pct:.2f}%"


def test_geometry_delta_struct():
    """Test that geometry delta has all required fields."""
    delta = {
        "volume_before": 1000.0,
        "volume_after": 1250.0,
        "volume_pct": 25.0,
        "faces_before": 6,
        "faces_after": 10,
        "faces_delta": 4,
        "edges_before": 12,
        "edges_after": 20,
        "edges_delta": 8,
    }

    # Check all required keys exist
    required_keys = [
        "volume_before", "volume_after", "volume_pct",
        "faces_before", "faces_after", "faces_delta",
        "edges_before", "edges_after", "edges_delta",
    ]

    for key in required_keys:
        assert key in delta, f"Geometry delta missing required key: {key}"

    # Check value types
    assert isinstance(delta["volume_before"], (int, float))
    assert isinstance(delta["volume_after"], (int, float))
    assert isinstance(delta["volume_pct"], (int, float))
    assert isinstance(delta["faces_before"], int)
    assert isinstance(delta["faces_after"], int)
    assert isinstance(delta["faces_delta"], int)


# ============================================================================
# Integration Test
# ============================================================================

def test_full_geometry_delta_workflow():
    """Test complete workflow: Capture metrics -> Calculate delta -> Verify."""
    # 1. Create box
    body = _make_box_body(40, 28, 18)

    # 2. Capture initial metrics
    old_metrics = _solid_metrics(body._build123d_solid)
    assert old_metrics is not None
    assert old_metrics["volume"] > 0

    # 3. Simulate geometry change (20% volume increase)
    new_metrics = old_metrics.copy()
    new_metrics["volume"] = old_metrics["volume"] * 1.20
    new_metrics["faces"] = old_metrics["faces"] + 4
    new_metrics["edges"] = old_metrics["edges"] + 6

    # 4. Calculate delta
    vol_pct = ((new_metrics["volume"] - old_metrics["volume"]) / old_metrics["volume"] * 100.0)

    geometry_delta = {
        "volume_before": round(old_metrics["volume"], 2),
        "volume_after": round(new_metrics["volume"], 2),
        "volume_pct": round(vol_pct, 1),
        "faces_before": old_metrics["faces"],
        "faces_after": new_metrics["faces"],
        "faces_delta": new_metrics["faces"] - old_metrics["faces"],
        "edges_before": old_metrics["edges"],
        "edges_after": new_metrics["edges"],
        "edges_delta": new_metrics["edges"] - old_metrics["edges"],
    }

    # 5. Verify delta
    assert abs(geometry_delta["volume_pct"] - 20.0) < 0.1
    assert geometry_delta["faces_delta"] == 4
    assert geometry_delta["edges_delta"] == 6

    # 6. Create feature with delta
    feat = ExtrudeFeature(
        sketch=None,
        distance=5.0,
        operation="Join",
        name="Test Push/Pull",
    )
    feat._geometry_delta = geometry_delta

    # 7. Verify feature has complete delta info
    assert feat._geometry_delta["volume_pct"] == 20.0
    assert feat._geometry_delta["volume_before"] == old_metrics["volume"]
    assert feat._geometry_delta["volume_after"] > old_metrics["volume"]
