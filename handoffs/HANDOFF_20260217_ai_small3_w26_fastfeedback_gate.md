# HANDOFF: W26 Fast Feedback Gate

**Datum:** 2026-02-17  
**Author:** AI-SMALL-3  
**Branch:** `feature/v1-ux-aiB`

---

## 1. Problem

Jeder Gate-Lauf (gate_core, gate_ui, gate_all) dauert 2-10+ Minuten. Für schnelle Inner-Dev-Loops fehlt ein leichtgewichtiger Runner, der in <15s ein Go/No-Go liefert.

---

## 2. API/Behavior Contract

### Script: `scripts/gate_fast_feedback.ps1`

| Parameter | Werte | Default |
|-----------|-------|---------|
| `-Profile` | `smoke`, `ui_quick`, `core_quick` | `smoke` |
| `-JsonOut` | Pfad für JSON-Export | (leer = kein Export) |

### Exit-Code-Vertrag

| Status | Exit Code |
|--------|-----------|
| PASS | 0 |
| FAIL (Test-Fehler, fehlende Dateien, Errors) | 1 |

### Output-Schema (analog bestehende Gates)

```
=== Fast Feedback Gate (<profile>) ===
Timestamp: ...
Profile: ...
Suites: ...

=== Fast Feedback Gate Result ===
Profile: <profile>
Duration: <n>s
Tests: <passed> passed, <failed> failed, <skipped> skipped, <errors> errors
Pass-Rate: <n>%
Status: PASS|FAIL
Exit Code: 0|1
```

### JSON-Schema (`-JsonOut`)

```json
{
  "schema": "fast_feedback_gate_v1",
  "profile": "smoke",
  "timestamp": "...",
  "duration_seconds": 12.17,
  "passed": 8, "failed": 0, "skipped": 0, "errors": 0,
  "total": 8, "status": "PASS", "exit_code": 0,
  "suites": ["test/...", "test/..."]
}
```

### Profil-Testauswahl

| Profil | Suites | Typische Dauer |
|--------|--------|---------------|
| `smoke` | `test_workflow_product_leaps_w25.py` + `test_gate_runner_contract.py::test_gate_all_script_exists` | ~12s |
| `ui_quick` | `test_ui_abort_logic.py` + `test_discoverability_hints_w17.py` | ~5min (Harness-Subprozess) |
| `core_quick` | `test_feature_error_status.py` + `test_tnp_v4_feature_refs.py` | ~11s |

### Pre-flight

Fehlende Testdateien werden vor dem pytest-Lauf erkannt und führen zu `Status: FAIL` mit klarer Fehlermeldung.

---

## 3. Impact

| Datei | Änderung |
|-------|----------|
| `scripts/gate_fast_feedback.ps1` | **Neu** — 170 Zeilen, 3 Profile, JSON-Export |
| `test/test_gate_runner_contract.py` | +7 Contract-Tests (`TestFastFeedbackGateContract`) |
| `roadmap_ctp/05_release_gates_and_quality_model.md` | +19 Zeilen Doku (Sektion 7) |

---

## 4. Validation

### py_compile
```powershell
conda run -n cad_env python -m py_compile test/test_gate_runner_contract.py
# Exit Code: 0 ✅
```

### Contract-Tests
```powershell
conda run -n cad_env python -m pytest -q test/test_gate_runner_contract.py -k "fast_feedback or gate_all_script_exists" -v
# 8 passed, 41 deselected in 83.57s ✅
```

### Smoke-Profil
```powershell
powershell -ExecutionPolicy Bypass -File scripts/gate_fast_feedback.ps1 -Profile smoke
# 8 passed, 0 failed — Status: PASS — Duration: 12.17s ✅
```

### Core-Quick-Profil
```powershell
powershell -ExecutionPolicy Bypass -File scripts/gate_fast_feedback.ps1 -Profile core_quick
# 102 passed, 1 skipped — Status: PASS — Duration: 11.44s ✅
```

### UI-Quick-Profil
```powershell
powershell -ExecutionPolicy Bypass -File scripts/gate_fast_feedback.ps1 -Profile ui_quick
# Läuft durch, aber >5min wegen Subprozess-Harness in discoverability_hints_w17
```

---

## 5. Breaking Changes / Rest-Risiken

**Breaking Changes:** Keine — rein additiv.

| Risiko | Impact | Mitigation |
|--------|--------|------------|
| `ui_quick` ist langsamer als erwartet (~5min statt <60s) | Niedrig | Harness-Tests nutzen Subprozess-Isolation; Alternative: `test_ui_abort_logic.py` allein als ultra-fast UI-Check |
| PowerShell `Out-File` schreibt UTF-8 BOM | Behoben | `[System.IO.File]::WriteAllText()` mit BOM-freiem Encoding |

---

## 6. Nächste 3 Folgeaufgaben

1. **ui_quick Profil optimieren:** `test_discoverability_hints_w17.py` durch schnellere Alternative ersetzen (z.B. `test_browser_tooltip_formatting.py`) — Subprozess-Harness zu langsam für Fast-Feedback
2. **CI-Integration:** `gate_fast_feedback.ps1 -Profile smoke -JsonOut` als pre-push Hook einbinden
3. **Dashboard-Feed:** JSON-Output in Stability-Dashboard integrieren (Trend über Fast-Feedback-Läufe)

---

## Wie das Wartezeiten reduziert

- **smoke (12s)** ersetzt den 2-10min `gate_core.ps1`-Lauf für schnelle Sanity-Checks nach jedem Edit.
- **core_quick (11s)** gibt Modeling-Entwicklern sofortiges Feedback über Feature-Error-Status und TNP-Refs.
- Empfohlener Loop: smoke→code→smoke→commit→gate_core — spart ~80% der Gate-Wartezeit im Inner Loop.

---

**Ende des Handoffs**
