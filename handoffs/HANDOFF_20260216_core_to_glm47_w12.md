# HANDOFF_20260216_core_to_glm47_w12

**Date:** 2026-02-16  
**From:** Codex (Core/KERNEL)  
**To:** GLM 4.7 (UX/WORKFLOW), QA  
**ID:** core_to_glm47_w12  
**Branch:** `feature/v1-ux-aiB`

## 1. Problem
Legacy-`status_details` aus gespeicherten Projekten wurden bisher nur teilweise migriert
(`status_class`/`severity`). In UX-Flows konnten dabei `next_action`/`hint` fehlen,
obwohl ein `code` vorhanden war.

Ziel:
- actionable Fehlerhinweise auch fuer Legacy-Artefakte deterministisch garantieren.

## 2. API/Behavior Contract
Neu/angepasst in `modeling/__init__.py`:
1. `_default_next_action_for_code(error_code)` als zentrale Mapping-Funktion.
2. `_normalize_status_details_for_load(...)` migriert jetzt zusaetzlich:
- `hint -> next_action` (wenn `next_action` fehlt),
- `next_action -> hint` (wenn `hint` fehlt),
- bei fehlenden beiden Feldern und vorhandenem `code`: default `next_action`/`hint` aus Code-Mapping.
3. `_build_operation_error_details(...)` nutzt dieselbe zentrale Default-Action-Funktion,
damit Laufzeit-Envelope und Load-Migration konsistent sind.

Damit gilt jetzt:
- Persistenz-Roundtrip liefert bei bekanntem `code` immer actionable `next_action` + `hint`.

## 3. Impact
Geaendert:
- `modeling/__init__.py`
- `test/test_feature_error_status.py`

Neue/erweiterte Regressionen:
- `test_feature_status_load_migrates_next_action_for_legacy_code`
- `test_feature_status_load_mirrors_legacy_hint_to_next_action`
- `test_feature_status_load_mirrors_legacy_next_action_to_hint`

## 4. Validation
Ausgefuehrt:

```powershell
conda run -n cad_env python -m pytest -q test/test_feature_error_status.py
powershell -ExecutionPolicy Bypass -File scripts/gate_core.ps1
```

Resultate:
- `test/test_feature_error_status.py`: `18 passed`
- `scripts/gate_core.ps1`: `287 passed, 2 skipped` (`Status: PASS`)

## 5. Breaking Changes / Rest-Risiken
- Kein API-Break.
- Bestehende manuelle `hint`/`next_action` Texte werden nicht ueberschrieben; nur fehlende Gegenfelder werden gespiegelt bzw. aus `code` aufgefuellt.
- Rest-Risiko: unbekannte Codes fallen weiterhin auf generischen Standardtext zurueck.
