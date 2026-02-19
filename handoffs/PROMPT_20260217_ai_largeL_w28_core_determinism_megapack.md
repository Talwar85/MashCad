Du bist `AI-LARGE-L-CORE` auf Branch `feature/v1-ux-aiB`.

## Mission
Liefer ein grosses W28 Core Determinism Megapack fuer produktionsnahe Stabilitaet.
Fokus: deterministic rebuilds, TNP-Fehlerschaerfung, idempotente Fehlerpfade.

## Harte Regeln
1. Keine kosmetischen-only Aenderungen.
2. Kein `skip`/`xfail` als Abkuerzung.
3. Keine API-Breaks ohne klar dokumentierten Contract.
4. Keine Edits ausserhalb Scope.
5. Keine Git-History-Eingriffe.

## Erlaubter Scope
- `modeling/**`
- `config/feature_flags.py`
- `test/test_tnp_v4_feature_refs.py`
- `test/test_feature_error_status.py`
- `test/test_project_roundtrip_persistence.py`
- `test/test_feature_edit_robustness.py`
- weitere core-nahe Tests unter `test/`

## NO-GO
- `gui/**`
- `scripts/**`
- `handoffs/**`

## Arbeitspaket
### Task 1: Deterministic Reference Canonicalization Deepening
Erweitere kanonische Sortierung/Normalisierung fuer alle relevanten Referenztypen:
1. edges
2. faces
3. sweep profile/path refs
4. loft section refs
5. persistierte shape-id bundles

### Task 2: Idempotence Across Multi-Rebuild Cycles
Fuege robuste Garantien hinzu:
1. missing_ref/mismatch/drift Fehler bleiben ueber 20 Rebuilds konsistent.
2. Keine unsteten status_details Felder.
3. Kein "healed by accident" wenn strict policy aktiv ist.

### Task 3: Strict Topology Fallback Policy Completion
Audit und vereinheitliche fallback behavior:
1. Keine selector-recovery bei invaliden topo refs wenn strict policy aktiv.
2. Legacy-Recovery nur wenn explizit erlaubt.
3. Fehlercodes muessen taxonomisch korrekt sein.

### Task 4: Error Envelope Completeness
Stelle sicher:
1. `status_details.code` ist praezise.
2. `tnp_failure` Objekt ist konsistent.
3. `runtime_dependency` Objekt ist konsistent bei optionalen APIs.

### Task 5: Tests ausbauen
Mindestens 30 neue Assertions, inkl.:
1. idempotence loops
2. canonical ordering stability
3. strict-vs-legacy fallback behavior
4. envelope field completeness

## Pflicht-Validierung
```powershell
conda run -n cad_env python -m py_compile modeling/__init__.py config/feature_flags.py
conda run -n cad_env python -m pytest -q test/test_tnp_v4_feature_refs.py -v
conda run -n cad_env python -m pytest -q test/test_feature_error_status.py -v
conda run -n cad_env python -m pytest -q test/test_project_roundtrip_persistence.py test/test_feature_edit_robustness.py -v
```

## Nachweispflicht
1. Geaenderte core contracts.
2. Liste der neuen Error-Code-Pfade.
3. Determinism-Nachweis ueber mehrere Rebuildzyklen.
4. Testresultate.

## Abgabeformat
Datei:
- `handoffs/HANDOFF_20260217_ai_largeL_w28_core_determinism_megapack.md`

Struktur:
1. Problem
2. API/Behavior Contract
3. Impact
4. Validation
5. Breaking Changes / Rest-Risiken
6. Naechste 5 Folgeaufgaben

