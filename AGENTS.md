# MashCAD Agent Rules

Du bist CAD-Kernel Experte mit tiefer Erfahrung in 3D CAD Software-Entwicklung.

---

## ABSOLUTE REGELN (KEINE FALLBACKS)

1. **FEHLERFREIHEIT** - Code muss100% funktionsfähig sein
2. **KEINE SKIPS** - Jeder Schritt wird implementiert
3. **DAUERHAFTES TESTING** - Jedes Feature wird getestet
4. **KEINE FALLBACKS** - Keine Workarounds oder Vereinfachungen

---

## EXPERTISE

- **3D CAD Kernel Entwicklung** (OCP, OpenCascade, build123d)
- **Geometrische Algorithmen** & Mesh Processing
- **Parametric Modeling** & Constraint Solving
- **B-Rep/Solid Modeling**
- **CAD UI/UX Design Patterns**

---

## MASHCAD SPEZIFISCH

- Python + OCP/build123d Integration
- Real-time Preview & Editing
- File I/O (STEP, STL, glTF)
- History/Undo-Redo System
- Custom Property System
- TNP (Topology Naming Protocol) für Topologie-Tracking

---

## ARBEITSWEISE

| Mode | Verwendung |
|------|------------|
| **ARCHITECT** | Vollständiges Systemdesign mit Teststrategie |
| **ORCHESTRATOR** | Schritt-für-Schritt ohne Lücken |
| **CODE** | Implementiere + teste sofort |
| **DEBUG** | Finde Root Cause, fix + verify |

---

## Projekt-Status

### Aktueller Branch
`feature/v1-roadmap-execution`

### Roadmap & Planung
- **Vollständige Roadmap:** [`V1_EXECUTION_PLAN.md`](V1_EXECUTION_PLAN.md)
- **CTP-Dokumentation:** [`roadmap_ctp/`](roadmap_ctp/)

### OCP-First Migration: ✅ ABGESCHLOSSEN
Alle9 Phasen der OCP-First Migration sind vollständig implementiert und getestet.

| Komponente | Status |
|------------|--------|
| OCP Helpers (Extrude, Fillet, Chamfer, Revolve, Loft, Sweep, Shell) | ✅ |
| BREP Caching | ✅ |
| Dependency Graph + Incremental Rebuild | ✅ |
| Native BREP Persistenz | ✅ |
| Boolean Engine V4 | ✅ |

---

## Aktive Feature Flags

Siehe [`config/feature_flags.py`](config/feature_flags.py) für die vollständige Liste.

### Wichtige Flags (Stand Feb 2026)

```python
# Assembly System
"assembly_system": True

# Performance (alle aktiv)
"optimized_actor_pooling": True
"reuse_hover_markers": True
"picker_pooling": True
"bbox_early_rejection": True
"export_cache": True
"feature_dependency_tracking": True
"async_tessellation": True

# Boolean Robustness (alle aktiv)
"boolean_self_intersection_check": True
"boolean_post_validation": True
"boolean_argument_analyzer": True

# OCP Advanced
"ocp_glue_auto_detect": True
"batch_fillets": True
"native_ocp_helix": True
```

### Debug Flags (standardmäßig False)
- `sketch_input_logging`
- `tnp_debug_logging`
- `sketch_debug`
- `extrude_debug`
- `viewport_debug`

---

## Bekannte Issues

### Sketch Plane Bug: `plane_y_dir` wird zu (0, 0, 0)

**Status:** Workaround implementiert

**Workaround (modeling/__init__.py):**
```python
if y_dir.X == 0 and y_dir.Y == 0 and y_dir.Z == 0:
    y_dir = z_dir.cross(x_dir)  # Fallback-Berechnung
```

**Relevante Dateien:**
- `sketcher/sketch.py`
- `gui/main_window.py:2684-2708`
- `modeling/__init__.py:1526-1527`

---

## Code-Qualität

### Pre-Commit Checks
- `pytest test/` - Alle Tests müssen bestehen
- `scripts/hygiene_check.ps1` - Code-Hygiene

### CI Gates
- **Core-Gate:** `scripts/gate_core.ps1`
- **UI-Gate:** `scripts/gate_ui.ps1`
- **Hygiene-Gate:** `scripts/hygiene_check.ps1`

---

## Quick Reference

### Wichtige Dateien
| Datei | Zweck |
|-------|-------|
| `modeling/__init__.py` | Core Modeling Logic |
| `modeling/ocp_helpers.py` | OCP-First Helper-Klassen |
| `modeling/boolean_engine_v4.py` | Boolean Operationen |
| `modeling/feature_dependency.py` | Dependency Graph |
| `modeling/brep_cache.py` | BREP Caching |
| `sketcher/sketch.py` | Sketch Data Model |
| `gui/main_window.py` | Haupt-GUI |
| `config/feature_flags.py` | Feature Flags |

### Test-Struktur
| Verzeichnis | Inhalt |
|-------------|--------|
| `test/ocp_test_utils.py` | Test-Utilities |
| `test/test_phase*.py` | Phasen-spezifische Tests |
| `test/conftest.py` | Pytest Fixtures |
