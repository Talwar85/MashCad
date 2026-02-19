Du bist `AI-LARGE-H-RELEASE-OPS` auf Branch `feature/v1-ux-aiB`.

Lies zuerst vollstaendig:
- `handoffs/PROMPT_20260217_ai_largeG_w26_stabilization_hardline.md`
- `roadmap_ctp/05_release_gates_and_quality_model.md`
- `roadmap_ctp/DELIVERY_VELOCITY_POLICY_W16_20260216.md`
- `test/test_gate_runner_contract.py`

## Ziel dieses Pakets (strikt getrennt von Stabilisierung)
Dieses Paket darf NICHT an Sketch/UI-Kerncode arbeiten.
Es soll die Delivery-Engine deutlich schneller und belastbarer machen:
- weniger Leerlauf,
- klarere BLOCKED/FAIL-Diagnose,
- bessere Evidence-Qualitaet,
- schnellere Entwickler-Loops.

## Harte Trennung / NO-GO
Du darfst NICHT aendern:
- `gui/**`
- `modeling/**`
- `sketcher/**`

Erlaubt:
- `scripts/**`
- `test/**` (nur Gate/Runner/Evidence/Contract/Infrastructure)
- `roadmap_ctp/**`
- optional `handoffs/**`

## Mission (W27-H RELEASE OPS MEGAPACK)
Liefere ein zusammenhaengendes Megapack mit 5 Teilleistungen.

### H1 (P0): Fast-Feedback v2 (echter Geschwindigkeitsgewinn)
Erweitere `scripts/gate_fast_feedback.ps1` um robuste Schnellprofile.

Pflicht:
1. Profile:
- `smoke` (bestehend)
- `core_quick` (bestehend)
- `ui_ultraquick` (neu, <30s Ziel)
- `ops_quick` (neu, script/contract-lastig, <20s Ziel)
2. Jeder Profil-Run muss klares Resultat liefern: PASS/FAIL + Exit-Code.
3. Optionaler JSON-Output bleibt stabil (`schema = fast_feedback_gate_v1` oder sauber versioniert auf v2 + Migration dokumentieren).
4. Keine stillen Fehler bei fehlenden Testdateien.

### H2 (P0): Preflight-Blocker-Scanner fuer UI-Gates
Baue einen sehr schnellen Vorabcheck, der harte Bootstrap-Blocker vor langen Läufen erkennt.

Neue Datei:
- `scripts/preflight_ui_bootstrap.ps1`

Pflicht:
1. Erkennt kritische UI-Bootstrap-Fehler (Import-/Init-Blocker) in <20s.
2. Liefert strukturierte Ausgabe:
- Status: `PASS` | `BLOCKED_INFRA` | `FAIL`
- Blocker-Type (wenn vorhanden)
- Root-Cause (Datei/Exception-Kern)
3. Integration in `scripts/gate_ui.ps1` als frueher Schritt:
- Bei hartem Bootstrap-Blocker frueher Abbruch mit klarem Status statt minutenlangem Fehlerspam.

### H3 (P0): Gate-Runner-Robustheit gegen race/lock Probleme
Baue Schutzmechanismen, damit Gate-Calls nicht durch parallele Temp-/Lock-Konflikte entgleisen.

Pflicht:
1. Serielle Ausfuehrung innerhalb der Gate-Skripte klar erzwingen (keine unkontrollierten parallelen `conda run` innerhalb eines Scripts).
2. Erkenne und klassifiziere bekannte Lock-/Infra-Ausfaelle sauber als BLOCKED_INFRA.
3. Error-Ausgaben in Gate-Result zusammenfassen (Top-Root-Causes, nicht nur Rohspam).

### H4 (P1): Evidence/Scorecard-Aufwertung
Erweitere Evidence-Generierung fuer bessere Steuerbarkeit.

Pflicht:
1. In Evidence (JSON/MD) zusaetzliche Felder, mind.:
- `delivery_completion_ratio`
- `validation_runtime_seconds`
- `blocker_type`
- `failed_suite_count`
- `error_suite_count`
2. Kompatibilitaet zu bestehenden Evidence-Dateien erhalten.
3. Falls Schema erweitert wird: Validator und Contract-Tests aktualisieren.

### H5 (P0): Contract-Test-Ausbau
Erweitere `test/test_gate_runner_contract.py` und ggf. verwandte Gate-Contract-Tests.

Pflicht:
1. Neue Tests fuer `ui_ultraquick` und `ops_quick` Profile.
2. Neue Tests fuer Preflight-Scanner (Output, Status, Exit-Vertrag).
3. Neue Tests fuer Gate-UI-Preflight-Integration.
4. Mindestens 15 neue belastbare Assertions (kein `hasattr`-Spam).

## Qualitätsregeln
1. Keine API-Fassade ohne echte Nutzung im Script.
2. Keine Dokudeltas ohne Test/Runner-Nachweis.
3. Keine Regression in bestehenden Gate-Contracts.

## Pflicht-Validierung (exakt ausführen)
```powershell
conda run -n cad_env python -m py_compile scripts/gate_fast_feedback.ps1 scripts/gate_ui.ps1 scripts/preflight_ui_bootstrap.ps1 scripts/generate_gate_evidence.ps1 scripts/validate_gate_evidence.ps1

conda run -n cad_env python -m pytest -q test/test_gate_runner_contract.py -k "fast_feedback or preflight or gate_ui or gate_all_script_exists" -v
conda run -n cad_env python -m pytest -q test/test_gate_evidence_contract.py test/test_stability_dashboard_seed.py test/test_gate_summary_archive_seed.py -v

powershell -ExecutionPolicy Bypass -File scripts/gate_fast_feedback.ps1 -Profile smoke
powershell -ExecutionPolicy Bypass -File scripts/gate_fast_feedback.ps1 -Profile core_quick
powershell -ExecutionPolicy Bypass -File scripts/gate_fast_feedback.ps1 -Profile ui_ultraquick
powershell -ExecutionPolicy Bypass -File scripts/gate_fast_feedback.ps1 -Profile ops_quick
powershell -ExecutionPolicy Bypass -File scripts/preflight_ui_bootstrap.ps1
```

## Nachweispflicht im Handoff
Du MUSST liefern:
1. Geaenderte Dateien + Grund.
2. Commit-Hash + Commit-Message.
3. Exakte Kommandos + reale Ergebnisse (passed/failed/skipped/errors).
4. Vorher/Nachher-Laufzeiten fuer Fast-Feedback-Profile.
5. Grep-Nachweise:
- neue Profile in `gate_fast_feedback.ps1`
- Preflight-Aufruf in `gate_ui.ps1`
- neue Contract-Tests in `test/test_gate_runner_contract.py`

## Abgabeformat
Datei:
- `handoffs/HANDOFF_20260217_ai_largeH_w27_release_ops_megapack.md`

Struktur:
1. Problem
2. API/Behavior Contract
3. Impact
4. Validation
5. Breaking Changes / Rest-Risiken
6. Naechste 5 Folgeaufgaben

Wenn ein Pflichtpunkt nicht geliefert werden kann:
- exakt sagen warum,
- mit Datei/Zeile/Exception,
- plus konkretem Recovery-Plan.
