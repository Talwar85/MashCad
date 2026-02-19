Du bist `AI-LARGE-L-CORE` auf Branch `feature/v1-ux-aiB`.

Lies zuerst:
- `handoffs/HANDOFF_20260217_ai_largeL_w28_core_determinism_megapack.md`

## Kritischer Kontext
Aktueller Stand hat eine Regression: neue Core-Tests leaken globale Feature-Flags.
Dadurch bricht z.B. `test/test_tnp_v4_feature_refs.py::test_resolve_edges_tnp_blocks_selector_fallback_when_topology_refs_break` nach bestimmten W28-Tests.

## Ziel
W29 Core Regression Fix: determinism package stabilisieren, ohne Fremd-Suites zu kontaminieren.

## Harte Regeln
1. Kein `skip`/`xfail`.
2. Keine API-Breaks.
3. Keine Edits ausserhalb Scope.
4. Test-Isolation ist Pflicht.

## Scope
- `modeling/__init__.py`
- `config/feature_flags.py` (nur falls zwingend)
- `test/test_core_determinism_megapack.py`
- `test/test_tnp_v4_feature_refs.py`
- `test/test_feature_error_status.py`

## NO-GO
- `gui/**`
- `scripts/**`
- `handoffs/**`

## Aufgaben
### 1) Flag-Leakage beseitigen
- Alle Tests muessen globale Flags sauber wiederherstellen.
- Nutze fixtures/context manager fuer deterministische cleanup.

### 2) Cross-Suite Idempotenz absichern
- Neue Tests duerfen bestehende TNP-Suites nicht beeinflussen.
- Reihenfolge-unabhaengigkeit herstellen.

### 3) Contract-Konsistenz
- strict vs legacy fallback policy weiter taxonomisch korrekt halten.
- error envelope v1 Felder konsistent.

### 4) Tests haerten
- Negative Sequenztests, die explizit auf state leakage pruefen.

## Pflicht-Validierung
```powershell
conda run -n cad_env python -m py_compile modeling/__init__.py config/feature_flags.py test/test_core_determinism_megapack.py
conda run -n cad_env python -m pytest -q test/test_core_determinism_megapack.py -v
conda run -n cad_env python -m pytest -q test/test_tnp_v4_feature_refs.py::test_resolve_edges_tnp_blocks_selector_fallback_when_topology_refs_break -v
conda run -n cad_env python -m pytest -q test/test_core_determinism_megapack.py::TestStrictTopologyFallbackPolicy::test_legacy_policy_allows_selector_recovery test/test_tnp_v4_feature_refs.py::test_resolve_edges_tnp_blocks_selector_fallback_when_topology_refs_break -v
conda run -n cad_env python -m pytest -q test/test_tnp_v4_feature_refs.py test/test_feature_error_status.py -v
```

## Abgabe
Datei:
- `handoffs/HANDOFF_20260217_ai_largeL_w29_core_determinism_regression_fix.md`

Pflichtinhalte:
1. Root-Cause Analyse der Regression
2. Geaenderte Dateien + Begruendung
3. Nachweis ohne Cross-Suite-Leak
4. Testergebnisse
5. Restrisiken

