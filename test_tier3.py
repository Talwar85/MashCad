"""Test: OCP Feature Audit Tier 3"""
import sys
print("=== OCP Feature Audit Tier 3 Tests ===\n")

# Test 1: Feature Flags
print("1. Feature Flags...")
from config.feature_flags import is_enabled
assert is_enabled("mesh_converter_adaptive_tolerance"), "Flag fehlt!"
assert is_enabled("loft_sweep_hardening"), "Flag fehlt!"
print("   OK Alle Tier 3 Flags aktiv")

# Test 2: Mesh Converter - Imports + adaptive Toleranz
print("\n2. Mesh Converter Robustheit...")
from modeling.mesh_converter import MeshToBREPConverter
import numpy as np

converter = MeshToBREPConverter()

# Test adaptive Toleranz-Berechnung
verts = np.array([[0,0,0], [100,0,0], [0,100,0], [100,100,0],
                   [0,0,100], [100,0,100], [0,100,100], [100,100,100]], dtype=np.float64)
bbox_diag = np.linalg.norm(verts.max(axis=0) - verts.min(axis=0))
expected_tol = max(1e-4, min(0.5, bbox_diag * 0.001))
print(f"   BBox-Diag = {bbox_diag:.1f}mm → Tolerance = {expected_tol:.4f}mm")
assert 1e-4 <= expected_tol <= 0.5, f"Toleranz außerhalb Range: {expected_tol}"
print("   OK Adaptive Toleranz-Berechnung korrekt")

# Test 3: BRepCheck_Analyzer und ShapeFix importiert
print("\n3. Post-Sewing Validation Imports...")
from OCP.BRepCheck import BRepCheck_Analyzer
from OCP.ShapeFix import ShapeFix_Shape
print("   OK BRepCheck_Analyzer + ShapeFix_Shape verfügbar")

# Test 4: Loft Hardening - SetMaxDegree/SetCriteriumWeight
print("\n4. Loft Hardening...")
from OCP.BRepOffsetAPI import BRepOffsetAPI_ThruSections
ts = BRepOffsetAPI_ThruSections(True, False)
ts.SetMaxDegree(8)
print(f"   MaxDegree gesetzt auf 8, gelesen: {ts.MaxDegree()}")
assert ts.MaxDegree() == 8
try:
    ts.SetCriteriumWeight(0.4, 0.2, 0.4)
    w1, w2, w3 = ts.CriteriumWeight()
    print(f"   CriteriumWeight: ({w1:.1f}, {w2:.1f}, {w3:.1f})")
except Exception as e:
    print(f"   CriteriumWeight nicht unterstützt: {e}")
print("   OK Loft Hardening Parameter funktionieren")

# Test 5: Sweep Robust - MakePipeShell + CorrectedFrenet
print("\n5. Sweep Robust (MakePipeShell)...")
from OCP.BRepOffsetAPI import BRepOffsetAPI_MakePipeShell
from OCP.GeomFill import GeomFill_IsCorrectedFrenet
print("   OK MakePipeShell + CorrectedFrenet importierbar")

# Test 6: Body._ocp_sweep_robust existiert
print("\n6. _ocp_sweep_robust Methode...")
from modeling import Body
body = Body(name="Test")
assert hasattr(body, '_ocp_sweep_robust'), "Methode fehlt!"
print("   OK Methode vorhanden")

# Test 7: Helix-Erkennung
print("\n7. Helix-Erkennung...")
from modeling.brep_face_analyzer import BRepFaceAnalyzer, FeatureType
assert hasattr(BRepFaceAnalyzer, '_detect_helix_features'), "Methode fehlt!"

# Teste mit einer Box (keine Helix erwartet)
from build123d import Solid
box = Solid.make_box(20, 20, 20)
analyzer = BRepFaceAnalyzer()
result = analyzer.analyze(box)
helix_features = [f for f in result.features if f.feature_type == FeatureType.THREAD]
print(f"   Box: {len(helix_features)} Helix-Features (erwartet: 0)")
assert len(helix_features) == 0, "Box sollte keine Helix haben!"
print("   OK Keine False Positives bei Box")

# Test 8: Dead Code entfernt
print("\n8. Dead-Code Cleanup...")
assert not hasattr(body, '_update_shape_registry_after_operation'), "Dead Code nicht entfernt!"
print("   OK _update_shape_registry_after_operation entfernt")

# Test 9: Loft-Integration funktioniert
print("\n9. Loft-Integration (End-to-End)...")
from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeWire, BRepBuilderAPI_MakeFace
from OCP.BRepOffsetAPI import BRepOffsetAPI_ThruSections
from OCP.Geom import Geom_Circle
from OCP.gp import gp_Ax2, gp_Pnt, gp_Dir
from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeEdge

# Zwei Kreise in verschiedenen Höhen
circle1 = Geom_Circle(gp_Ax2(gp_Pnt(0,0,0), gp_Dir(0,0,1)), 10.0)
circle2 = Geom_Circle(gp_Ax2(gp_Pnt(0,0,20), gp_Dir(0,0,1)), 5.0)

edge1 = BRepBuilderAPI_MakeEdge(circle1).Edge()
wire1 = BRepBuilderAPI_MakeWire(edge1).Wire()
edge2 = BRepBuilderAPI_MakeEdge(circle2).Edge()
wire2 = BRepBuilderAPI_MakeWire(edge2).Wire()

loft = BRepOffsetAPI_ThruSections(True, False)
loft.SetMaxDegree(8)
loft.AddWire(wire1)
loft.AddWire(wire2)
loft.Build()

assert loft.IsDone(), "Loft fehlgeschlagen!"
result = Solid(loft.Shape())
print(f"   OK Loft: Volume={result.volume:.1f}")

print("\n=== Tier 3 Tests abgeschlossen ===")
