# PROMPT_20260217_ai_largeX_w33_core_tnp_determinism_ultrapack

Du bist AI-LARGE-X (Core/KERNEL Cell) auf Branch `feature/v1-ux-aiB`.

## Mission
Massiver Kern-Fortschritt fuer V1: TNP-Fehlerpfade, Determinismus und Rebuild-Robustheit auf Produktionsniveau bringen.

## Harte Grenzen
### No-Go
- `gui/**`
- `scripts/**`
- `handoffs/**`

### Fokus
- `modeling/__init__.py`
- `config/feature_flags.py`
- `test/test_tnp_v4_feature_refs.py`
- `test/test_feature_error_status.py`
- `test/test_trust_gate_core_workflow.py`
- `test/test_cad_workflow_trust.py`
- neue Core-Tests nach Bedarf

## Harte Regeln
1. Keine Skips/Xfails neu einfuehren.
2. Keine bestehenden Tests abschwaechen.
3. Kein "nur Test"-Paket: echte Core-Verbesserung ist Pflicht.
4. Jede neue Error-Policy braucht Tests fuer positive + negative Pfade.

---

## EPIC X1 - Error-Taxonomie Vollstaendig und Konsistent (P0)
Ziel: `status_details.code` und `tnp_failure` in allen topology-sensitiven Pfaden konsistent.

### Aufgaben
1. Pruefe und schliesse Luecken fuer:
- `tnp_ref_missing`
- `tnp_ref_mismatch`
- `tnp_ref_drift`
- `rebuild_finalize_failed`
- `ocp_api_unavailable`

2. Erzwinge konsistente Envelope-Felder:
- `code`
- `tnp_failure.category`
- `tnp_failure.reference_kind`
- `tnp_failure.next_action`
- `runtime_dependency` (falls zutreffend)

3. Bei operation_failed-Fallback nur dort zulassen, wo keine praezisere Taxonomie moeglich ist, und in Tests dokumentieren.

---

## EPIC X2 - Determinismus ueber Mehrfach-Rebuilds (P0)
Ziel: Rebuild-Idempotenz ueber wiederholte Zyklen mit stabilen Referenzindizes.

### Aufgaben
1. Verifiziere/stabilisiere Sortierung + Entduplizierung fuer:
- `feature.edge_indices`
- `feature.face_indices`
- persistierte ShapeIDs

2. Fuehre mehrzyklische Determinismus-Tests ein:
- gleiche Eingabe, >=25 Rebuilds, identische Referenzstruktur.
- veraenderte Rebuild-Reihenfolge darf keine driftenden Index-Arrays erzeugen.

3. Seed-basierte Reproduzierbarkeit fuer deterministische Tests (kein flaky behavior).

---

## EPIC X3 - Strict Fallback Policy Matrix (P0)
Ziel: `strict_topology_fallback_policy` Verhalten glasklar und regressionssicher.

### Aufgaben
1. Matrix absichern:
- `strict_topology_fallback_policy=True/False`
- `self_heal_strict=True/False`
- vorhandene kaputte Topologie-Referenzen

2. Sicherstellen:
- bei strict policy kein stilles selector-recovery.
- bei legacy policy kontrolliertes recovery bleibt moeglich.

3. Tests muessen das Verhalten explizit pro Matrix-Kombination nachweisen.

---

## EPIC X4 - Rebuild-Failsafe Invariants (P1)
Ziel: Finalize-Crash darf Zustand nicht korrumpieren.

### Aufgaben
1. Rollback-Invariant haerten:
- pre-rebuild snapshot wiederhergestellt.
- `status_details.rollback.from/to` konsistent befuellt.

2. Zusatztsts fuer Kettenfehler:
- erster Fehler + nachfolgender Rebuild darf nicht in undefiniertem Zustand landen.

---

## Pflicht-Validierung
```powershell
conda run -n cad_env python -m py_compile modeling/__init__.py config/feature_flags.py
conda run -n cad_env python -m pytest -q test/test_feature_error_status.py test/test_tnp_v4_feature_refs.py
conda run -n cad_env python -m pytest -q test/test_trust_gate_core_workflow.py test/test_cad_workflow_trust.py
conda run -n cad_env python -m pytest -q test/test_brepopengun_offset_api.py
```

## Akzeptanzkriterien
- Mindestens 1 reale Core-Luecke geschlossen (nicht nur Refactor).
- Taxonomie + Determinismus + Policy-Matrix durch Tests belastbar.
- Kein regressiver Bruch in Pflicht-Suiten.

## Rueckgabeformat
Datei: `handoffs/HANDOFF_20260217_ai_largeX_w33_core_tnp_determinism_ultrapack.md`

Struktur:
1. Problem
2. API/Behavior Contract
3. Impact
4. Validation
5. Breaking Changes / Rest-Risiken
6. Naechste 3 priorisierte Folgeaufgaben
