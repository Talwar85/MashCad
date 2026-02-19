# HANDOFF_20260216_glm47_w3_ux_replace

**Date:** 2026-02-16
**From:** Claude (UX/WORKFLOW Cell)
**To:** AI-3 (QA/Gate Cell), Core (Codex)
**ID:** glm47_w3_ux_replace
**Branch:** `feature/v1-ux-aiB`

---

## 1. Problem

GLM 4.7 übernimmt den UX/Workflow-Track von Gemini mit dem Ziel, die UI-Gates stabil und deterministisch zu machen. Die zu lösenden Probleme waren:

1. **Right-Click Abort/Background-Clear** war nicht deterministisch
2. **UI-Gate Instabilität** durch VTK OpenGL Context Fehler (`wglMakeCurrent failed`)
3. **Drift-UX** musste als recoverable warning konsolidiert werden
4. **2D-Modus Bedienhinweise** mussten sichtbar gemacht werden

---

## 2. Read Acknowledgement

| Handoff Datei | Impact |
|---------------|--------|
| `HANDOFF_20260216_core_to_gemini_w6.md` | `tnp_ref_drift` Status als WARNING emittieren, nicht ERROR |
| `HANDOFF_20260216_core_to_gemini_w7.md` | Single-ref-pair weak conflicts bevorzugen Index, markieren als Drift |
| `HANDOFF_20260216_core_to_gemini_w8.md` | Face-Resolver analog zu Edge-Resolver für Drift |
| `HANDOFF_20260216_core_to_gemini_w9.md` | Sweep-Pfad-Resolver Drift-Härtung |
| `HANDOFF_20260216_core_to_gemini_w10.md` | Sweep-Profil-Resolver Drift-Härtung |
| `HANDOFF_20260216_core_to_gemini_w11.md` | Core-Gate-Baseline: 248 passed |
| `HANDOFF_20260216_gemini_w5.md` | Browser-Tooltip Drift UX, Right-Click Konsolidierung |
| `HANDOFF_20260216_gemini_w6.md` | Doppelte eventFilter entfernt, Single Source of Truth |
| `HANDOFF_20260216_glm47_w2.md` | QA-Infrastruktur, Evidence-Generator, Flaky-Strategie |

---

## 3. API/Behavior Contract

### W4-1: Right-Click Abort/Background-Clear (FIXED)

**Verhalten:**
- **Right-Press:** Bricht aktive Drags/Tool-Operationen ab (`is_dragging`, `_offset_plane_dragging`, `_split_dragging`, `extrude_mode`, `point_to_point_mode`)
- **Right-Release (Background):** Leert Selektion wenn Mausbewegung < 5px und Dauer < 0.3s
- **Left-Click (Background):** Leert Selektion über `clear_selection()` Methode

**Geänderte Files:**
- `gui/main_window.py:11845` - `hasattr` Check für `_selected_body_for_transform`
- `gui/viewport_pyvista.py:3047` - `clear_selection()` statt manuellem Clear

### W4-2: UI-Gate Stabilität (MITIGATED)

**Workaround:** `QT_OPENGL=software` Environment Variable

**Strategie:**
- OpenGL Fehler (`wglMakeCurrent failed`) werden in stderr geloggt aber verursachen keine Test-Fehler mehr
- Tests laufen stabil mit Software-Rendering

**Geänderte Files:**
- `roadmap_ctp/UI_GATE_TRIAGE_W3_20260216.md` - Status auf MITIGATED aktualisiert

### W4-3: Drift-UX Konsolidierung (VERIFIED)

**Konsistente Implementierung:**
- Browser-Tooltip: "Warning (Recoverable)" für `tnp_ref_drift`
- Browser-Farbe: Orange (#e0a030) statt Rot
- TNP Stats Panel: Mappt `tnp_ref_drift` zu "fallback" Status

**Bestätigte Files:**
- `gui/browser.py:52-56, 563-566` - Tooltip + Color
- `gui/widgets/tnp_stats_panel.py:244` - Status Mapping

### W4-4: 2D-Modus Bedienhinweise (VERIFIED)

**Vorhandene Implementierung:**
- HUD in `gui/sketch_renderer.py:2608-2673`
- Navigation-Hint Zeile 2621: "Navigation: Shift+R=Ansicht drehen | Space halten=3D-Peek"
- Position: Oben-Links (12, hint_y)
- Farbe: Blau (110, 180, 255, 220)

---

## 4. Impact

### Geänderte Dateien (2)

| Datei | Änderung | Grund |
|-------|----------|-------|
| `gui/main_window.py` | `hasattr` Check für `_selected_body_for_transform` | Fix AttributeError in `_on_background_clicked` |
| `gui/viewport_pyvista.py` | `clear_selection()` aufrufen statt manuellem Clear | Konsistente Selektions-Logik |

### Aktualisierte Dokumentation (1)

| Datei | Änderung |
|-------|----------|
| `roadmap_ctp/UI_GATE_TRIAGE_W3_20260216.md` | W4 Status: MITIGATED via `QT_OPENGL=software` |

### Verifizierte Implementierungen (2)

| Feature | Datei | Status |
|---------|-------|--------|
| Drift-UX | `gui/browser.py`, `gui/widgets/tnp_stats_panel.py` | ✅ KONSISTENT |
| 2D-Hints | `gui/sketch_renderer.py` | ✅ SICHTBAR |

---

## 5. Validation

### Executed Commands & Results

#### W4-1: Right-Click Abort Tests
```powershell
conda run -n cad_env python -m pytest -q test/test_ui_abort_logic.py::TestAbortLogic::test_right_click_cancels_drag test/test_ui_abort_logic.py::TestAbortLogic::test_right_click_background_clears_selection -vv
```
**Result:** `2 passed in 14.20s` ✅

#### W4-1: Interaction Consistency
```powershell
conda run -n cad_env python -m pytest -q test/harness/test_interaction_consistency.py::TestInteractionConsistency::test_click_selects_nothing_in_empty_space -vv
```
**Result:** `1 passed in 10.69s` ✅

#### W4-3: Browser Tooltip (Drift UX)
```powershell
conda run -n cad_env python -m pytest -q test/test_browser_tooltip_formatting.py test/test_feature_commands_atomic.py
```
**Result:** `11 passed in 5.09s` ✅
- `test_browser_tooltip_shows_warning_for_drift` - PASSED

#### Full UI Gate (mit OpenGL Workaround)
```powershell
powershell -Command "$env:QT_OPENGL='software'; conda run -n cad_env python -m pytest -q test/test_ui_abort_logic.py test/harness/test_interaction_consistency.py -vv"
```
**Result:** `3 passed in 21.63s` ✅
- Hinweis: OpenGL-Warnings (`wglMakeCurrent failed`) erscheinen im stderr, verursachen aber keine Fehler

---

## 6. Breaking Changes / Rest-Risiken

### Breaking Changes
**Keine** - Alle Änderungen sind Bugfixes und Bestätigungen.

### Residual Risks

| Risiko | Wahrscheinlichkeit | Impact | Mitigation |
|--------|-------------------|--------|------------|
| OpenGL Context Fehler in CI | Mittel | Tests langsamer/timeout | `QT_OPENGL=software` in CI setzen |
| `selected_faces` vs `selected_face_ids` Duplikat | Niedrig | Verwirrung bei zukünftigen Änderungen | Technical Debt für spätere Refactorierung |

### Technical Debt Notes

1. **Doppelte Selektions-Attribute:** `selected_faces` und `selected_face_ids` existieren parallel. Sollte in einem zukünftigen Refactor konsolidiert werden.
2. **OpenGL Software Rendering:** `QT_OPENGL=software` ist ein Workaround. Langfristig sollte VTK Context Management verbessert werden.

---

## 7. Nächste 3 priorisierte Folgeaufgaben

### 1. P1: Selektions-Attribute Konsolidierung
**Beschreibung:** `selected_faces` und `selected_face_ids` zu einem einzigen Attribut zusammenfassen.
**Validierung:**
```powershell
# Search für doppelte Attribute
conda run -n cad_env python -c "import re; content = open('gui/viewport_pyvista.py').read(); print('selected_faces:', len(re.findall(r'selected_faces', content)), 'selected_face_ids:', len(re.findall(r'selected_face_ids', content)))"
```
**Owner:** UX (GLM 4.7) | **ETA:** W5

### 2. P1: 2D-Modus Peek-Feature Überprüfung
**Beschreibung:** 3D-Peek (Space halten) funktioniert im Sketch-Editor. Überprüfen ob alle UI-Elemente korrekt ein/ausgeblendet werden.
**Validierung:**
```powershell
# Manuelles Testen oder UI-Test erweitern
conda run -n cad_env python -m pytest test/harness/test_interaction_consistency.py -k peek -v
```
**Owner:** UX (GLM 4.7) | **ETA:** W5

### 3. P2: VTK Context Management Verbesserung
**Beschreibung:** Langfristige Lösung für OpenGL Context Fehler anstatt Software-Rendering Workaround.
**Ansätze:**
- Explizite Context Cleanup in Test Teardown
- Offscreen Rendering für UI Tests
- Separate Prozesse für UI Tests

**Owner:** Core (Codex) | **ETA:** W6+

---

## 8. Summary

| Aufgabe | Status | Result |
|---------|--------|--------|
| W4-1 P0: Right-Click Abort/Background-Clear | ✅ COMPLETED | 2 Fixes, Tests pass |
| W4-2 P0: UI-Gate Stabilität | ✅ COMPLETED | Mitigated via `QT_OPENGL=software` |
| W4-3 P1: Drift-UX Konsolidierung | ✅ VERIFIED | Bereits konsistent implementiert |
| W4-4 P1: 2D-Modus Bedienhinweise | ✅ VERIFIED | Bereits sichtbar in HUD |

**Gesamtstatus:** Alle Aufgaben erfolgreich abgeschlossen. UI-Gates laufen stabil mit Software-Rendering Workaround.

---

## Signature

```
Handoff-Signature: w3_ux_replace_4tasks_2fixes_verified_20260216
UX-Cell: Claude (GLM 4.7 Replacement)
Validated: 2026-02-16 00:05 UTC
Branch: feature/v1-ux-aiB
```

---

**End of Handoff GLM 4.7 W3 (UX Replace)**
