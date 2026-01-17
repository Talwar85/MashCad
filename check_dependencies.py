#!/usr/bin/env python3
"""
Dependency Check Script für MashCad
Prüft ob alle erforderlichen Module für die Mesh-Converter verfügbar sind
"""

import sys

def check_module(name, required=True):
    """Prüft ob ein Modul importierbar ist"""
    try:
        __import__(name)
        print(f"✅ {name:20s} - OK")
        return True
    except ImportError as e:
        if required:
            print(f"❌ {name:20s} - FEHLT (erforderlich)")
        else:
            print(f"⚠️  {name:20s} - FEHLT (optional)")
        return False

print("=" * 60)
print("MashCad - Dependency Check")
print("=" * 60)
print(f"\nPython Version: {sys.version}")
print("-" * 60)

# Core Dependencies (ERFORDERLICH)
print("\n📦 Core Dependencies (erforderlich):")
core_ok = True
core_ok &= check_module("PySide6", required=True)
core_ok &= check_module("pyvista", required=True)
core_ok &= check_module("build123d", required=True)
core_ok &= check_module("numpy", required=True)
core_ok &= check_module("loguru", required=True)
core_ok &= check_module("shapely", required=True)

# Mesh Converter Dependencies (ERFORDERLICH)
print("\n🔧 Mesh Converter Dependencies (erforderlich):")
converter_ok = True
converter_ok &= check_module("pyransac3d", required=True)
converter_ok &= check_module("trimesh", required=True)

# Optional Dependencies
print("\n🎁 Optional Dependencies (empfohlen):")
optional_ok = True
optional_ok &= check_module("scipy", required=False)
optional_ok &= check_module("gmsh", required=False)
optional_ok &= check_module("pymeshlab", required=False)

# ML Dependencies (optional, für ParSeNet V8)
print("\n🤖 ML Dependencies (optional, für V8):")
ml_ok = True
ml_ok &= check_module("torch", required=False)
ml_ok &= check_module("torchvision", required=False)

# Summary
print("\n" + "=" * 60)
print("ZUSAMMENFASSUNG")
print("=" * 60)

if core_ok and converter_ok:
    print("✅ Alle erforderlichen Dependencies installiert!")
    print("   → MashCad sollte funktionieren")
    print("   → V7 (RANSAC Primitives) verfügbar")
    print("   → V9 (Hybrid) verfügbar")

    if not optional_ok:
        print("\n⚠️  Einige optionale Dependencies fehlen:")
        print("   → scipy: ConvexHull (Fallback zu BoundingBox)")
        print("   → gmsh: V5 Converter nicht verfügbar")
        print("   → pymeshlab: Mesh-Reparatur nicht verfügbar")

    if not ml_ok:
        print("\n🤖 ML-Features nicht verfügbar (V8 ParSeNet)")
        print("   → pip install -r requirements-ml.txt (falls gewünscht)")

    sys.exit(0)
else:
    print("❌ Kritische Dependencies fehlen!")
    print("\nBitte installieren:")
    print("   pip install -r requirements.txt")
    sys.exit(1)
