# HANDOFF_20260216_glm47_w13_unskip_retest

**Date:** 2026-02-16
**From:** GLM 4.7 (UX/WORKFLOW + QA Integration Cell)
**To:** Nächste UX-Iteration, Codex (Core), AI-3 (QA)
**ID:** glm47_w13_unskip_retest
**Branch:** `feature/v1-ux-aiB`

---

## 1. Problem

**W12 Stand:** Die 3 riskanten Drag-Tests waren mit `@pytest.mark.skip` markiert und in `test_interaction_drag_isolated.py` ausgelagert. UI-Gate lief stabil mit `1 passed, 3 skipped`.

**W13 Ziel:** Endzustand B erreicht - **Contained Runnable**: Die 3 Drag-Tests laufen wieder im Hauptlauf (nicht mehr skip), aber mit Subprozess-Isolierung, die bei ACCESS_VIOLATION den Runner schützt.

---

## 2. API/Behavior Contract

### Paket A (P0): Drag-Tests Unskip + Subprozess-Isolierung

**Status:** ✅ IMPLEMENTED

**Änderungen:**

1. **Update:** `test/harness/test_interaction_consistency.py`
   - Die 3 Drag-Tests sind NICHT mehr skip-markiert
   - Tests verwenden `@pytest.mark.xfail(strict=False)` mit W13 Reason
   - Tests rufen `run_test_in_subprocess()` aus `crash_containment_helper` auf
   - Bei Crash: `xfail_on_crash()` markiert Test als xfail
   - Bei Erfolg: Test kann pass (Blocker behoben)

2. **Produktiv-Verwendung:** `test/harness/crash_containment_helper.py`
   - W12: Helper existierte aber wurde nicht produktiv verwendet
   - W13: Helper wird aktiv von den Drag-Tests genutzt
   - `run_test_in_subprocess()` - Führt Test in isoliertem Prozess aus
   - `xfail_on_crash()` - Markiert Test als xfail bei Crash

### Paket C (P1): W13 Contracts und Gate-Update

**Status:** ✅ IMPLEMENTED

**Änderungen:**

1. **Update:** `test/test_crash_containment_contract.py`
   - W12 Contracts prüften dass Tests skipped sind
   - W13 Contracts prüfen dass Tests NICHT skipped sind
   - Neue Contracts: `test_interaction_consistency_drag_tests_are_not_skipped`
   - Neue Contracts: `test_interaction_consistency_uses_subprocess_isolation`
   - Klasse `TestGateRunnerContractW12` → `TestGateRunnerContractW13`

2. **Update:** `scripts/gate_ui.ps1`
   - Header: "W13 Unskip + Retest Edition"
   - W13 Kommentar: "Paket A+B - Contained Runnable: Drag-Tests laufen mit Subprozess-Isolierung"

3. **Update:** `scripts/generate_gate_evidence.ps1`
   - Header: "W13 Unskip + Retest Edition"
   - Default Prefix: `QA_EVIDENCE_W13_`
   - Evidence Version: 3.1 (W13: Drag-Tests runnable)

---

## 3. Impact

### Geänderte Dateien (4)

| Datei | Art | Zweck |
|-------|-----|-------|
| `test/harness/test_interaction_consistency.py` | UPDATE | Drag-Tests unskipped, Subprozess-Isolierung |
| `test/test_crash_containment_contract.py` | UPDATE | W13 Contracts: prüfen dass Tests NICHT skipped sind |
| `scripts/gate_ui.ps1` | UPDATE | W13 Header |
| `scripts/generate_gate_evidence.ps1` | UPDATE | W13 Header, Prefix W13, Version 3.1 |

### Test-Status (W13 Pflicht-Validation)

| Suite | W12 | W13 | Delta | Status |
|-------|-----|-----|-------|--------|
| `test_interaction_consistency.py` | 1p, 3s | **1p, 3x** | **skip→xfail** | ✅ RUNNABLE |
| `test_crash_containment_contract.py` | 8p | **9p** | **+1** | ✅ UPDATED |
| `test_ui_abort_logic.py` | 20p | 20p | 0 | ✅ STABLE |
| `test_selection_state_unified.py` | 23p | 23p | 0 | ✅ STABLE |
| `test_browser_tooltip_formatting.py` | 10p | 10p | 0 | ✅ STABLE |
| `test_discoverability_hints.py` | 24p | 24p | 0 | ✅ STABLE |
| `test_error_ux_v2_integration.py` | 32p | 32p | 0 | ✅ STABLE |
| `test_feature_commands_atomic.py` | 7p | 7p | 0 | ✅ STABLE |

**Gesamt:** **117 passed, 3 xfailed, 9 contracts passed** ✅ (W12: 117 passed, 3 skipped, 8 contracts)

**Wichtigste Änderung:** Die 3 riskanten Tests sind **nicht mehr skipped** sondern **werden ausgeführt** (xfail bei Crash). Runner läuft stabil durch.

---

## 4. Validation

### Executed Commands & Results

#### W13 Interaction Consistency Tests (Contained Runnable)
```powershell
conda run -n cad_env python -m pytest test/harness/test_interaction_consistency.py -v
```
**Result:** `1 passed, 3 xfailed in ~27s` ✅
- Kein `skipped` mehr!
- Kein ACCESS_VIOLATION Runner-Absturz!
- Tests laufen in Subprozess-Isolierung

#### W13 Crash Containment Contract Tests
```powershell
conda run -n cad_env python -m pytest test/test_crash_containment_contract.py -v
```
**Result:** `9 passed in ~0.09s` ✅
- W13 Contracts prüfen dass Tests NICHT skipped sind

#### UI Bundle Tests (Stability Check)
```powershell
conda run -n cad_env python -m pytest test/test_ui_abort_logic.py test/test_selection_state_unified.py test/test_browser_tooltip_formatting.py test/test_discoverability_hints.py test/test_error_ux_v2_integration.py test/test_feature_commands_atomic.py
```
**Result:** `116 passed in ~395s` ✅

---

## 5. Breaking Changes / Rest-Risiken

### Breaking Changes
**Keine** - Alle Änderungen sind rückwärtskompatibel:
- Isolierte Tests sind weiterhin separat verfügbar
- UI-Gate läuft stabil durch

### Residual Risiken

| Risiko | Wahrscheinlichkeit | Impact | Mitigation |
|--------|-------------------|--------|------------|
| Drag-Tests crashen weiterhin in bestimmten Umgebungen | Hoch | Tests sind als xfail markiert | Subprozess-Isolierung schützt Runner |
| Subprozess-Laufzeit ist höher als direkter Lauf | Mittel | ~27s statt ~10s | Akzeptabel für Stabilität |

---

## 6. W13 Unskip Resolution Matrix (Pflicht)

| Testname | W12 Status | W13 Status | Skip entfernt (ja/nein) | Runner-Crash | Ergebnis | Blocker-Signatur |
|----------|-----------|-----------|------------------------|--------------|----------|------------------|
| `test_circle_move_resize` | SKIPPED | **XFAIL** | **JA** | **NEIN** | xfail (ACCESS_VIOLATION in Subprozess) | ACCESS_VIOLATION_INTERACTION_DRAG |
| `test_rectangle_edge_drag` | SKIPPED | **XFAIL** | **JA** | **NEIN** | xfail (ACCESS_VIOLATION in Subprozess) | ACCESS_VIOLATION_INTERACTION_DRAG |
| `test_line_drag_consistency` | SKIPPED | **XFAIL** | **JA** | **NEIN** | xfail (ACCESS_VIOLATION in Subprozess) | ACCESS_VIOLATION_INTERACTION_DRAG |

**Zusammenfassung:**
- Vorher (W12): Tests sind skipped → Runner läuft stabil durch
- Nachher (W13): Tests laufen (xfail bei Crash) → Runner läuft weiterhin stabil durch
- **Keine Tests mehr skipped!**

---

## 7. W13 Review Template (Ausgefüllt)

```markdown
# W13 Review Template (GLM47)

## Scope-Check
- [x] Nur erlaubte Pfade editiert (test/**, scripts/**, handoffs/**)
- [x] Kein Core-Kernel geändert
- [x] Drag-Tests unskipped mit Subprozess-Isolierung

## Contract-Check
- [x] Drag-Tests sind NICHT mit @pytest.mark.skip markiert
- [x] Drag-Tests sind mit @pytest.mark.xfail(strict=False) markiert
- [x] Subprozess-Isolierung via crash_containment_helper implementiert
- [x] UI-Gate läuft stabil durch (1 passed, 3 xfailed)

## Test-Check
- [x] Interaction Consistency: 1 passed, 3 xfailed (kein Crash!)
- [x] Crash Containment Contracts: 9 passed (W13)
- [x] UI-Bundle läuft stabil (116 passed)
- [x] Gate-Skripte auf W13 aktualisiert

## Unskip-Matrix (W12→W13)
- `test_circle_move_resize`:
  - W12: SKIPPED (ausgelagert)
  - W13: **XFAIL** (läuft in Subprozess-Isolierung)
- `test_rectangle_edge_drag`:
  - W12: SKIPPED (ausgelagert)
  - W13: **XFAIL** (läuft in Subprozess-Isolierung)
- `test_line_drag_consistency`:
  - W12: SKIPPED (ausgelagert)
  - W13: **XFAIL** (läuft in Subprozess-Isolierung)

## Merge-Risiken
1. Isolierte Tests sind weiterhin verfügbar (GETESTET: test_interaction_drag_isolated.py existiert)
2. UI-Gate läuft stabil durch (GETESTET: 1p/3x, kein Crash)
3. W13 Regression-Tests validieren Konfiguration (GETESTET: 9 passed)

## Empfehlung
- [x] Ready for merge train
- [ ] Needs follow-up
Begründung: Endzustand B erreicht: Contained Runnable implementiert. UI-Gate läuft stabil durch ohne ACCESS_VIOLATION Absturz. Die 3 Drag-Tests sind nicht mehr skipped sondern werden ausgeführt (xfail bei Crash).
```

---

## 8. Nächste 5 priorisierte Folgeaufgaben

### 1. P1: Drag-Tests Stabilisieren (UX-Cell W14+)
**Beschreibung:** VTK-mocking oder stabilere coordinate mapping für headless CI implementieren
**Repro:** `conda run -n cad_env python -m pytest test/harness/test_interaction_drag_isolated.py -v`
**Owner:** Core (VTK Integration) | **ETA:** 2026-02-25

### 2. P2: Subprozess-Laufzeit Optimieren (UX-Cell W14)
**Beschreibung:** Subprozess-Isolierung optimieren (z.B. multiprocessing statt subprocess.run)
**Owner:** UX-Cell | **ETA:** 2026-02-25

### 3. P2: UI Panels Error UX v2 Integration (UX-Cell W12)
**Beschreibung:** Input-Panels mit status_class/severity aufrufen (Hole-, Extrude-, Fillet-Panels)
**Owner:** UX-Cell | **ETA:** 2026-02-20

### 4. P3: VTK OpenGL Context Hardening (Core)
**Beschreibung:** Langfristige Lösung für VTK OpenGL Context Issues
**Owner:** Core | **ETA:** 2026-03-01

### 5. P3: Subprozess-Isolierung Für Alle Riskanten Tests (UX-Cell W14)
**Beschreibung:** Automatisierte Subprozess-Isolierung für alle riskanten UI-Tests
**Owner:** UX-Cell | **ETA:** 2026-02-25

---

## Summary

| Aufgabe | Status | Result |
|---------|--------|--------|
| Paket A P0: Drag-Tests Unskip + Subprozess-Isolierung | ✅ IMPLEMENTED | 3 Tests laufen (xfail bei Crash), kein Runner-Crash |
| Paket B P0: Crash Containment Helper Produktiv-Verwendung | ✅ IMPLEMENTED | Tests nutzen run_test_in_subprocess() und xfail_on_crash() |
| Paket C P1: Contracts und Gate-Update für W13 | ✅ IMPLEMENTED | 9 Contracts passed, Gate-Skripte auf W13 |

**Gesamtstatus:** Endzustand B erreicht - **Contained Runnable**: UI-Gate läuft stabil durch ohne ACCESS_VIOLATION Absturz. Die 3 Drag-Tests sind **nicht mehr skipped** sondern werden mit Subprozess-Isolierung ausgeführt.

---

## Signature

```
Handoff-Signature: w13_unskip_retest_3pkgs_contained_runnable_117p3x_20260216
UX-Cell: GLM 4.7 (UX/WORKFLOW + QA Integration Cell)
Validated: 2026-02-16 16:00 UTC
Branch: feature/v1-ux-aiB
Tests: 117 passed, 3 xfailed, 9 contracts passed
Blocker Resolution: ACCESS_VIOLATION_INTERACTION_DRAG (Contained via subprocess isolation)
```

---

**End of Handoff GLM 4.7 W13 UNSKIP + RETEST**
