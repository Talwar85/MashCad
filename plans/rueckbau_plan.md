# MashCAD Rückbau-Plan: Feature-Flags bereinigen

**Datum:** 2026-02-21  
**Status:** Analyse abgeschlossen, zur Implementierung bereit  
**Ziel:** Entferne alten Legacy-Code für Feature-Flags die dauerhaft auf `True` stehen

---

## Übersicht

### Rückbau-Strategie

Feature-Flags die auf `True` stehen bedeuten, dass der **neue Code-Pfad aktiv** ist. Der **alte Code im `else`-Zweig** wird nicht mehr ausgeführt und kann entfernt werden.

**Vorgehensweise pro Flag:**
1. Identifiziere alle `if is_enabled("flag_name")` Stellen
2. Behalte den `if`-Block (neuer Code)
3. Entferne den `else`-Block (alter Legacy-Code)
4. Entferne das Feature-Flag aus [`config/feature_flags.py`](config/feature_flags.py)
5. Teste dass nichts kaputt geht

---

## Kategorisierung der Feature-Flags

### Kategorie A: Performance-Optimierungen (Rückbau empfohlen)

Diese Flags aktivieren performantere Code-Pfade. Der Legacy-Code ist langsamer und kann bedenkenlos entfernt werden.

| Flag | Status | Betroffene Dateien | Legacy-Code Zeilen |
|------|--------|-------------------|-------------------|
| `picker_pooling` | True | [`gui/viewport_pyvista.py`](gui/viewport_pyvista.py:540) | 540-550 |
| `reuse_hover_markers` | True | [`gui/viewport_pyvista.py`](gui/viewport_pyvista.py:1205) | 1232-1237, 3142-3156, 3168-3197 |
| `optimized_actor_pooling` | True | [`gui/viewport/body_mixin.py`](gui/viewport/body_mixin.py:103) | 107-114, 234-242 |
| `export_cache` | True | [`modeling/cad_tessellator.py`](modeling/cad_tessellator.py:756) | 756-768 |
| `async_tessellation` | True | [`modeling/body.py`](modeling/body.py:475) | 475-478 |
| `feature_dependency_tracking` | True | [`modeling/body.py`](modeling/body.py:516), [`modeling/body_rebuild.py`](modeling/body_rebuild.py:217) | Kein else-Block |

### Kategorie B: Boolean-Robustheit (Rückbau empfohlen)

Diese Flags aktivieren sicherere Boolean-Operationen. Der Legacy-Code kann kaputte Geometrie erzeugen.

| Flag | Status | Betroffene Dateien | Legacy-Code Zeilen |
|------|--------|-------------------|-------------------|
| `boolean_self_intersection_check` | True | [`modeling/boolean_engine_v4.py`](modeling/boolean_engine_v4.py:945) | 945-946 (return None) |
| `boolean_post_validation` | True | [`modeling/boolean_engine_v4.py`](modeling/boolean_engine_v4.py:1042) | 1042-1043 |
| `boolean_argument_analyzer` | True | [`modeling/boolean_engine_v4.py`](modeling/boolean_engine_v4.py:994) | 994-995 (return None) |
| `boolean_tolerance_monitoring` | True | [`modeling/boolean_engine_v4.py`](modeling/boolean_engine_v4.py:1090) | 1090-1091 (return) |
| `ocp_glue_auto_detect` | True | [`modeling/boolean_engine_v4.py`](modeling/boolean_engine_v4.py:661) | 661-662 (return None) |
| `bbox_early_rejection` | True | Boolean Engine | Kein direkter else-Block |

### Kategorie C: OCP-First Migration (Rückbau empfohlen)

Diese Flags aktivieren den neuen OCP-First Code-Pfad. Der Legacy build123d-Code wird nicht mehr benötigt.

| Flag | Status | Betroffene Dateien |
|------|--------|-------------------|
| `ocp_first_extrude` | True | [`modeling/body_extrude.py`](modeling/body_extrude.py:122), [`modeling/shape_builders.py`](modeling/shape_builders.py:212) |
| `ocp_brep_cache` | True | [`modeling/brep_cache.py`](modeling/brep_cache.py:108) |
| `ocp_incremental_rebuild` | True | [`modeling/body_rebuild.py`](modeling/body_rebuild.py) |
| `ocp_brep_persistence` | True | [`modeling/brep_persistence.py`](modeling/brep_persistence.py:100) |

### Kategorie D: Export-Features (Rückbau empfohlen)

| Flag | Status | Betroffene Dateien | Legacy-Code |
|------|--------|-------------------|-------------|
| `export_3mf` | True | [`gui/export_controller.py`](gui/export_controller.py:462) | Warning-Dialog |
| `export_free_bounds_check` | True | [`modeling/body.py`](modeling/body.py:1361) | 1361-1362 (return) |
| `export_auto_repair` | True | Export Pipeline | - |

### Kategorie E: Solver-Features (Rückbau empfohlen)

| Flag | Status | Betroffene Dateien |
|------|--------|-------------------|
| `sketch_drag_optimization` | True | [`gui/sketch_editor.py`](gui/sketch_editor.py:5257) |
| `solver_pre_validation` | True | [`sketcher/solver.py`](sketcher/solver.py:168), [`sketcher/solver_interface.py`](sketcher/solver_interface.py:227) |
| `solver_smooth_penalties` | True | [`sketcher/solver.py`](sketcher/solver.py:169), [`sketcher/constraints.py`](sketcher/constraints.py:462) |

### Kategorie F: Andere Features (Rückbau empfohlen)

| Flag | Status | Betroffene Dateien |
|------|--------|-------------------|
| `assembly_system` | True | [`modeling/document.py`](modeling/document.py:85), [`gui/browser.py`](gui/browser.py:795) |
| `mate_system_v1` | True | Assembly System |
| `mate_solver` | True | Assembly System |
| `self_heal_strict` | True | [`modeling/body_rebuild.py`](modeling/body_rebuild.py:46), [`modeling/feature_operations.py`](modeling/feature_operations.py:444) |
| `strict_topology_fallback_policy` | True | [`modeling/feature_operations.py`](modeling/feature_operations.py:445), [`gui/main_window_setup.py`](gui/main_window_setup.py:383) |
| `geometry_drift_detection` | True | [`modeling/body_rebuild.py`](modeling/body_rebuild.py:1128) |
| `adaptive_tessellation` | True | [`modeling/cad_tessellator.py`](modeling/cad_tessellator.py:456) |
| `detailed_boolean_history` | True | [`modeling/boolean_engine_v4.py`](modeling/boolean_engine_v4.py:206) |
| `native_ocp_helix` | True | Modeling Pipeline |
| `helix_fitting_enabled` | True | [`modeling/brep_face_analyzer.py`](modeling/brep_face_analyzer.py:759) |
| `wall_thickness_analysis` | True | Modeling Pipeline |
| `batch_fillets` | True | Modeling Pipeline |
| `loft_sweep_hardening` | True | Modeling Pipeline |
| `mesh_converter_adaptive_tolerance` | True | [`modeling/mesh_converter.py`](modeling/mesh_converter.py:64) |
| `printability_trust_gate` | True | [`gui/export_controller.py`](gui/export_controller.py:237), [`modeling/printability_gate.py`](modeling/printability_gate.py:257) |
| `rollback_validation` | True | [`modeling/body_transaction.py`](modeling/body_transaction.py:352) |
| `first_run_tutorial` | True | [`gui/first_run_wizard.py`](gui/first_run_wizard.py:579) |
| `live_preview_textures` | True | [`gui/main_window.py`](gui/main_window.py) |
| `live_preview_patterns` | True | [`gui/main_window.py`](gui/main_window.py) |

---

## Kategorie G: Debug-Flags (NICHT entfernen)

Diese Flags sind **immer `False`** und für Debugging gedacht. Sie sollen bleiben.

| Flag | Status | Zweck |
|------|--------|-------|
| `sketch_input_logging` | False | Detailliertes Sketch-Input Logging |
| `tnp_debug_logging` | False | TNP v4.0 Shape-Tracking Debug |
| `sketch_debug` | False | Sketch-Editor Debug |
| `extrude_debug` | False | Extrude Operation Debug |
| `viewport_debug` | False | Viewport/Mesh Debug |

---

## Kategorie H: Experimentelle Features (NICHT entfernen)

Diese Flags sind **`False`** für experimentelle Features. Sie sollen bleiben.

| Flag | Status | Zweck |
|------|--------|-------|
| `sketch_orientation_indicator` | False | 3D-Orientierung im Sketch-Editor |
| `cylindrical_face_edit` | False | Zylindrische Faces radius-modifizieren |
| `export_normals_check` | False | Normalen-Konsistenz-Check |
| `sketch_performance_monitoring` | False | Performance Stats Collection |
| `live_preview_shell` | False | Live Shell Thickness Preview |
| `live_preview_fillet` | False | Live Fillet Radius Preview |
| `live_preview_chamfer` | False | Live Chamfer Size Preview |
| `normal_map_preview` | False | Normal Map Visualization |
| `normal_map_shader` | False | Shader-based Normal Mapping |
| `rc_burn_in_mode` | False | RC Burn-in Testing Mode |

---

## Detaillierte Rückbau-Anweisungen

### 1. `picker_pooling` - Picker-Pooling

**Datei:** [`gui/viewport_pyvista.py`](gui/viewport_pyvista.py:540)

**Aktueller Code (Zeile 540-570):**
```python
if not is_enabled("picker_pooling"):
    # LEGACY: Immer neuen Picker erstellen
    import vtk
    picker = vtk.vtkCellPicker()
    if tolerance_type == "coarse":
        picker.SetTolerance(Tolerances.PICKER_TOLERANCE_COARSE)
    elif tolerance_type == "measure":
        picker.SetTolerance(0.005)
    else:
        picker.SetTolerance(Tolerances.PICKER_TOLERANCE)
    return picker

# OPTIMIZED: Picker wiederverwenden
import vtk
if tolerance_type == "coarse":
    ...
```

**Rückbau:**
- Entferne Zeile 540-550 (if-Block mit Legacy-Code)
- Behalte nur den "OPTIMIZED" Block
- Entferne `from config.feature_flags import is_enabled` wenn nicht mehr benötigt

---

### 2. `reuse_hover_markers` - Hover-Marker wiederverwenden

**Datei:** [`gui/viewport_pyvista.py`](gui/viewport_pyvista.py:1205)

**Betroffene Stellen:**
- Zeile 1205-1210: Marker-Erstellung
- Zeile 1226-1237: Cleanup-Logik
- Zeile 3124-3197: Point-to-Point Mode

**Rückbau:**
- Entferne alle `if is_enabled("reuse_hover_markers")` Checks
- Behalte nur den "OPTIMIZED" Code-Pfad
- Entferne alle "# LEGACY" kommentierten Blöcke

---

### 3. `optimized_actor_pooling` - VTK Actor Pooling

**Datei:** [`gui/viewport/body_mixin.py`](gui/viewport/body_mixin.py:103)

**Aktueller Code (Zeile 103-114):**
```python
if is_enabled("optimized_actor_pooling"):
    # OPTIMIZED: Nur existing_actors prüfen (renderer check redundant)
    can_reuse_mesh = (n_mesh in existing_actors and mesh_obj is not None)
    can_reuse_edge = (n_edge in existing_actors and edge_mesh_obj is not None)
else:
    # LEGACY: Mit redundantem Renderer-Check
    can_reuse_mesh = (n_mesh in existing_actors and
                     n_mesh in self.plotter.renderer.actors and
                     mesh_obj is not None)
    can_reuse_edge = (n_edge in existing_actors and
                     n_edge in self.plotter.renderer.actors and
                     edge_mesh_obj is not None)
```

**Rückbau:**
- Ersetze gesamten Block durch den OPTIMIZED Code
- Entferne den LEGACY else-Block

---

### 4. `export_cache` - Tessellation-Cache für Export

**Datei:** [`modeling/cad_tessellator.py`](modeling/cad_tessellator.py:756)

**Aktueller Code (Zeile 756-800):**
```python
if not is_enabled("export_cache"):
    # LEGACY: Keine Caching, direkt tessellieren
    try:
        b3d_mesh = solid.tessellate(...)
        ...
    except Exception as e:
        ...
    return verts, faces

# OPTIMIZED: Mit Caching
try:
    ...
```

**Rückbau:**
- Entferne den gesamten "LEGACY" if-Block (Zeile 756-768)
- Behalte nur den "OPTIMIZED" Code

---

### 5. `async_tessellation` - Background Mesh Generation

**Datei:** [`modeling/body.py`](modeling/body.py:475)

**Aktueller Code:**
```python
if not is_enabled("async_tessellation"):
    # Synchroner Fallback
    self._regenerate_mesh()
    return

if self._build123d_solid is None:
    return
# ... async code
```

**Rückbau:**
- Entferne den synchronen Fallback-Block
- Behalte nur den async Code

---

### 6. `sketch_drag_optimization` - Sketch Drag Performance

**Datei:** [`gui/sketch_editor.py`](gui/sketch_editor.py:5257)

**Aktueller Code:**
```python
if not is_enabled("sketch_drag_optimization"):
    # Legacy behavior - always solve
    try:
        self.sketch.solve()
    except Exception as e:
        logger.debug(f"Direct drag solve failed: {e}")
    return

now = time.perf_counter()
# ... throttled solver code
```

**Rückbau:**
- Entferne den Legacy-Block
- Behalte nur den throttled Solver-Code

---

### 7. Boolean Robustness Flags

**Datei:** [`modeling/boolean_engine_v4.py`](modeling/boolean_engine_v4.py)

Alle diese Flags haben das gleiche Pattern:

```python
if not is_enabled("flag_name"):
    return None  # oder return result_shape
```

**Rückbau für alle:**
- Entferne die `if not is_enabled()` Checks
- Der Code danach wird immer ausgeführt

**Betroffene Flags:**
- `boolean_self_intersection_check` (Zeile 945)
- `boolean_post_validation` (Zeile 1042)
- `boolean_argument_analyzer` (Zeile 994)
- `boolean_tolerance_monitoring` (Zeile 1090)
- `ocp_glue_auto_detect` (Zeile 661)
- `detailed_boolean_history` (Zeile 206)

---

## Priorisierte Rückbau-Reihenfolge

### Phase 1: Niedriges Risiko (Performance-Flags)
1. `picker_pooling`
2. `reuse_hover_markers`
3. `optimized_actor_pooling`
4. `export_cache`

**Test:** Core-Smoke-Tests, Performance-Benchmarks

### Phase 2: Mittleres Risiko (Boolean-Flags)
1. `boolean_self_intersection_check`
2. `boolean_post_validation`
3. `boolean_argument_analyzer`
4. `ocp_glue_auto_detect`
5. `detailed_boolean_history`

**Test:** Boolean-Test-Suite, TNP-Tests

### Phase 3: Mittleres Risiko (OCP-First Flags)
1. `ocp_first_extrude`
2. `ocp_brep_cache`
3. `ocp_incremental_rebuild`
4. `ocp_brep_persistence`

**Test:** Vollständige Modeling-Test-Suite

### Phase 4: Höheres Risiko (Core-Features)
1. `assembly_system`
2. `mate_system_v1`
3. `mate_solver`
4. `self_heal_strict`
5. `strict_topology_fallback_policy`

**Test:** Vollständige Test-Suite

### Phase 5: Übrige Flags
1. Alle Export-Flags
2. Alle Solver-Flags
3. Alle UX-Flags

---

## Risiken und Mitigation

### Risiko 1: Unbekannte Code-Pfade
**Beschreibung:** Es könnte Code geben, der das Flag zur Laufzeit ändert.  
**Mitigation:** Suche nach `set_flag()` und `set_enabled()` Aufrufen in Tests - diese sind erlaubt, aber zur Laufzeit shouldn't happen.

### Risiko 2: Test-Abhängigkeiten
**Beschreibung:** Einige Tests prüfen explizit Flag-Zustände.  
**Mitigation:** Tests müssen nach Rückbau aktualisiert werden. Siehe Test-Dateien in [`test/`](test/).

### Risiko 3: TNP-System Abhängigkeiten
**Beschreibung:** Das TNP-System hat viele Debug-Flags die False sind.  
**Mitigation:** `tnp_debug_logging` bleibt als Debug-Flag erhalten.

### Risiko 4: Thread-Safety
**Beschreibung:** Einige Flags beeinflussen Thread-Verhalten (async_tessellation).  
**Mitigation:** Gründliche Tests mit Background-Workers.

---

## Test-Checkliste nach jedem Rückbau

- [ ] `pytest test/` - Alle Tests bestanden
- [ ] `scripts/gate_core.ps1` - Core-Gate bestanden
- [ ] `scripts/gate_ui.ps1` - UI-Gate bestanden
- [ ] Manueller Smoke-Test: Sketch erstellen → Extrude → Fillet → Export STL
- [ ] Manueller Smoke-Test: Assembly erstellen

---

## Zusammenfassung

### Zu entfernende Flags (True → Standard-Code): 42 Flags

### Zu behaltende Flags:
- **Debug-Flags (False):** 5 Flags
- **Experimentelle Flags (False):** 10 Flags

### Geschätzte Code-Reduktion
- ca. 200-300 Zeilen Legacy-Code
- 42 Feature-Flag-Einträge in [`config/feature_flags.py`](config/feature_flags.py)

---

**Nächste Schritte:**
1. Review dieses Plans durch das Team
2. Priorisierung der Phasen
3. Wechsel zu CODE-Mode für die Implementierung
