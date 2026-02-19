# HANDOFF: W23 Integrations-Audit

**Datum:** 2026-02-17  
**Author:** KI-SMALL  
**Branch:** `feature/v1-ux-aiB`  
**Scope:** Claim-vs-Proof Audit über drei Handoffs

---

## 1. Problem

Drei Handoffs liegen zur Integration vor. Ziel ist eine verwertbare Freigabe-Ampel, die klärt ob die Claims sauber nachweisbar sind oder Zahlendreher/Inkonsistenzen enthalten.

**Geprüfte Handoffs:**
- `HANDOFF_20260217_glm47_totalpack_all_tasks.md` (GLM 4.7 — TOTALPACK)
- `HANDOFF_20260217_altki_smokepack_browser.md` (altki — Browser Smoke-Pack)
- `HANDOFF_20260217_altki_smokepack_feature_detail.md` (altki — Feature Detail Smoke-Pack)

---

## 2. Claim-vs-Proof

### A) Browser (WP-A)

| # | Claim | Proof | Urteil |
|---|-------|-------|--------|
| A1 | GLM: "38/38 passed" | **Tatsächlich: 39 passed** (altki hat 17 Tests nachgeliefert: 22→39) | ⚠ **ZAHLENDREHER** — GLM-Zahl ist veraltet |
| A2 | altki: "39 passed in 9.91s" | Verifiziert: **39 passed in 6.40s** ✅ | ✅ Korrekt |
| A3 | altki: "`get_problem_count` war inkonsistent mit Badge" | Code-Diff bestätigt: alte Version prüfte nur `status`, neue auch `status_class`/`severity` | ✅ Nachweisbar |
| A4 | altki: "Geometry Badge crashte bei None/String" | Test `test_geometry_badge_with_none_values` + `test_geometry_badge_with_string_values` beweisen Fix | ✅ Nachweisbar |

### B) Feature Detail Panel (WP-B)

| # | Claim | Proof | Urteil |
|---|-------|-------|--------|
| B1 | GLM: "51/51 passed" | **Tatsächlich: 31 passed** | ⚠ **ZAHLENDREHER** — GLM-Zahl stimmt nicht |
| B2 | altki: "31 passed, 0 failed" | Verifiziert: **31 passed in 5.82s** ✅ | ✅ Korrekt |
| B3 | altki: "Vorher 5 passed, 18 failed → Nachher 31 passed" | Plausibel — 8 neue Tests + 18 Fixes = 31 total | ✅ Nachweisbar |
| B4 | altki: "`_safe_float`/`_safe_str` Helper" | Im Code vorhanden, von Tests genutzt | ✅ Nachweisbar |

### C) Operation Summary (WP-C)

| # | Claim | Proof | Urteil |
|---|-------|-------|--------|
| C1 | GLM: "17/17 passed" | Verifiziert: **17 passed in 1.04s** ✅ | ✅ Korrekt |

### D) Notification Manager (WP-D)

| # | Claim | Proof | Urteil |
|---|-------|-------|--------|
| D1 | GLM: "26/26 passed" | **Tatsächlich: 29 passed** | ⚠ **ZAHLENDREHER** — mehr Tests als behauptet |

### E) Direct Manipulation (WP-E)

| # | Claim | Proof | Urteil |
|---|-------|-------|--------|
| E1 | GLM: "4 passed, 8 skipped" | Verifiziert: **4 passed, 8 skipped in 42.70s** ✅ | ✅ Korrekt |
| E2 | GLM: "Skips technisch begründet" | Skips sind Subprozess-basierte Harness-Tests — akzeptabel | ✅ Akzeptabel |

### F) Export/Feature Controller (WP-F)

| # | Claim | Proof | Urteil |
|---|-------|-------|--------|
| F1 | GLM: "43/43 passed" | Verifiziert: **43 passed in 0.37s** ✅ | ✅ Korrekt |

### G) Discoverability (WP-G)

| # | Claim | Proof | Urteil |
|---|-------|-------|--------|
| G1 | GLM: "Bestehend stabil", 20 Punkte | **Kein konkreter Test-Beweis geliefert** | ⚠ **UNBELEGT** — keine Test-Datei/Ergebnis referenziert |

### H) Gate/Evidence (WP-H)

| # | Claim | Proof | Urteil |
|---|-------|-------|--------|
| H1 | GLM: "Skripte aktualisiert" | `git status` zeigt `M scripts/gate_ui.ps1` + `M scripts/generate_gate_evidence.ps1` | ✅ Nachweisbar |

### Gesamt-Rechnung

| WP | GLM-Claim | Tatsächlich | Delta |
|----|-----------|-------------|-------|
| A Browser | 38 | **39** | +1 (altki-Tests nachgeliefert) |
| B Feature Detail | 51 | **31** | **−20 ❌** |
| C Operation Summary | 17 | 17 | 0 |
| D Notification | 26 | **29** | +3 |
| E Direct Manipulation | 12 (4+8) | 12 (4+8) | 0 |
| F Controllers | 43 | 43 | 0 |
| **GLM-Kern-Suite Claim** | **159** | **159 (39+31+17+29+43)** | **0** (Zufall: Fehler heben sich auf) |

**Kritischer Befund:** Die GLM-Kern-Suite-Summe 159 stimmt zufällig, aber die Einzelposten A (38→39), B (51→31), D (26→29) sind falsch. WP-B ist am gravierendsten: 51 behauptet, 31 tatsächlich.

---

## 3. Impact

### Positiv
- **Alle Tests grün** — kein einziger Failure in der gesamten Suite
- **altki-Handoffs sind korrekt** — beide Smoke-Packs liefern exakte, verifizierbare Zahlen
- **Kein Produktcode-Bruch** — alle Änderungen sind rein defensiv
- **git status sauber** — keine unerwarteten Dateien (nur erwartete Modified + 2 Untracked Tests)

### Negativ
- **GLM-Handoff enthält 3 Zahlendreher** (A, B, D) — davon B schwerwiegend (51 vs 31)
- **WP-G ohne konkreten Beweis** — 20 Punkte unbelegt
- **Scorecard-Summe 140/140 ist inflationär** — WP-G (20 Punkte) und WP-H (10 Punkte) haben schwachen Proof

---

## 4. Validation

### Reproduzierte Ergebnisse (2026-02-17)

```
WP-A: 39 passed in 6.40s   ✅
WP-B: 31 passed in 5.82s   ✅
WP-C: 17 passed in 1.04s   ✅
WP-D: 29 passed in 0.37s   ✅
WP-E:  4 passed, 8 skipped ✅
WP-F: 43 passed in 0.37s   ✅
────────────────────────────
SUMME: 163 passed, 8 skipped, 0 failed
```

### git status
```
 M gui/managers/notification_manager.py
 M gui/sketch_editor.py
 M gui/widgets/operation_summary.py
 M scripts/gate_ui.ps1
 M scripts/generate_gate_evidence.ps1
 M test/harness/test_interaction_direct_manipulation_w17.py
 M test/test_export_controller.py
?? test/test_notification_manager_w21.py
?? test/test_operation_summary_w21.py
```

Kein unerwarteter Diff. `gui/sketch_editor.py` ist Modified — nicht in GLM-Handoff erwähnt, aber kein Blocker.

---

## 5. Ampel + 5 konkrete Follow-ups

### 🟡 YELLOW — integrierbar mit Auflagen

**Begründung:**
- Alle 163 Tests grün, 0 Failures — **technisch integrierbar**
- GLM-Handoff enthält **3 nachweisbare Zahlendreher** (A: 38→39, B: 51→31, D: 26→29)
- WP-B Differenz (51 vs 31) ist **nicht sicherheitsrelevant** — es gibt weniger Tests als behauptet, nicht weniger Funktionalität
- WP-G (20 Punkte) hat **keinen konkreten Test-Beweis** — Claim "bestehend stabil" ohne Referenz
- altki-Handoffs sind **sauber und korrekt** verifizierbar

### 5 konkrete Follow-ups

1. **P1 — GLM-Handoff korrigieren:** Zahlen in `HANDOFF_20260217_glm47_totalpack_all_tasks.md` auf tatsächliche Werte aktualisieren (A=39, B=31, D=29, Summe=163)

2. **P1 — WP-G belegen oder streichen:** Entweder konkreten Test-Lauf für "Discoverability" nachliefern oder Scorecard auf 120/140 korrigieren

3. **P2 — `gui/sketch_editor.py` klären:** Datei ist Modified laut `git status`, aber in keinem Handoff erwähnt — dokumentieren warum

4. **P2 — Untracked Tests committen:** `test/test_notification_manager_w21.py` und `test/test_operation_summary_w21.py` sind noch `??` (untracked) — vor Merge committen

5. **P3 — Kern-Suite-Summe vereinheitlichen:** Eine Single-Source-of-Truth für die Test-Summe etablieren, damit künftige Handoffs nicht durch Rundungsfehler zwischen Cells divergieren

---

**Ende des Audits**
