# PROMPT_20260218_ai_largeAD_w33_core_persistence_compat_megapack

Du bist AI-LARGE-AD (Core Persistence + Compatibility Cell) auf Branch `feature/v1-ux-aiB`.

## Mission
Liefere ein grosses Core-Paket fuer V1-Produktionsreife:
1. robuste Persistenz von Error/Recovery-Metadaten,
2. deterministisches Rebuild-Verhalten nach Reload,
3. klare Kompatibilitaet fuer aeltere Projektdaten.

## Scope
Erlaubte Dateien:
- `modeling/__init__.py`
- persistenznahe Module unter `modeling/**` (nur wenn direkt relevant)
- `config/feature_flags.py` (nur falls zwingend)
- `test/test_project_roundtrip_persistence.py`
- `test/test_feature_error_status.py`
- `test/test_tnp_v4_feature_refs.py`
- `test/test_feature_edit_robustness.py`
- neue Core-Tests nach Bedarf

No-Go:
- `gui/**`
- `scripts/**`

## Harte Regeln
1. Keine neuen `skip` oder `xfail`.
2. Keine API-Verschleierung: Breaking risks transparent dokumentieren.
3. Keine impliziten Migrationen ohne Testabdeckung.
4. Keine `.bak` oder `temp_*` Dateien erzeugen.

## EPIC AD1 - Error Envelope Persistence (P0)
Ziel: Error-Metadaten gehen beim Save/Load nicht verloren.

Aufgaben:
1. Persistiere und restaure robust:
- `status_details.code`
- `status_details.rollback`
- `tnp_failure.*`
- `runtime_dependency.*`
2. Roundtrip-Tests fuer alle Pflichtcodes.
3. Keine stillen default-Overwrites.

## EPIC AD2 - Reload Determinism (P0)
Ziel: Nach Reload bleibt Referenzauflosung stabil.

Aufgaben:
1. Mehrfach-Save/Load + Rebuild Zyklen stabil halten.
2. Keine driftenden `face_indices`/`edge_indices` durch Reload.
3. Regressionstests mit >=2 zyklischen Roundtrips.

## EPIC AD3 - Legacy Compatibility (P1)
Ziel: Alte Projekte ohne neue Felder bleiben ladbar.

Aufgaben:
1. Defensive default-Strategie fuer fehlende Felder.
2. Falls Migration noetig, deterministisch und testbar.
3. Keine Datenzerstoerung bei teilweiser Legacy-Struktur.

## EPIC AD4 - Feature Edit Robustness unter Fehlerstatus (P1)
Ziel: Editierfluss bleibt robust, auch wenn vorherige Features Fehler tragen.

Aufgaben:
1. Edit-Operationen mit vorhandenen Error-Features testen.
2. Sicherstellen, dass Fehlerstatus nicht inkonsistent "verschwindet".
3. Status-Transitions klar und deterministic.

## Pflicht-Validierung
```powershell
conda run -n cad_env python -m py_compile modeling/__init__.py
conda run -n cad_env python -m pytest -q test/test_project_roundtrip_persistence.py
conda run -n cad_env python -m pytest -q test/test_feature_error_status.py test/test_tnp_v4_feature_refs.py
conda run -n cad_env python -m pytest -q test/test_feature_edit_robustness.py
conda run -n cad_env python -m pytest -q test/test_trust_gate_core_workflow.py test/test_cad_workflow_trust.py
```

## Akzeptanzkriterien
1. Mindestens eine echte Persistenzluecke geschlossen.
2. Roundtrip + Rebuild Determinismus testbar belegt.
3. Keine neuen skips/xfails.
4. Pflichtvalidierung komplett gruen.

## Rueckgabeformat
Datei: `handoffs/HANDOFF_20260218_ai_largeAD_w33_core_persistence_compat_megapack.md`

Struktur:
1. Problem
2. API/Behavior Contract
3. Impact
4. Validation
5. Breaking Changes / Rest-Risiken
6. Naechste 3 priorisierte Folgeaufgaben
