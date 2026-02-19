# HANDOFF: W24 WP-H Addendum — Gate/Evidence Nachweis

**Datum:** 2026-02-17  
**Author:** KI-SMALL-2  
**Branch:** `feature/v1-ux-aiB`  
**Bezug:** W23-Audit (YELLOW-Ampel), GLM TOTALPACK WP-H

---

## 1. Problem

Das W23-Audit hat WP-H (Gate/Evidence, 10 Punkte) als schwach belegt eingestuft. GLM-Claim: "Skripte W22" — ohne konkreten Lauf-Nachweis. Zusätzlich enthält das generierte Evidence-Dokument **veraltete W18-Labels**, obwohl es als W22 TOTALPACK deklariert wurde.

---

## 2. Claim-vs-Proof (WP-H fokussiert)

### 2.1 Skripte aktualisiert auf W22?

| Artefakt | Claim | Tatsächlicher Befund |
|----------|-------|---------------------|
| `scripts/gate_ui.ps1` Zeile 2 | "W22 TOTALPACK Edition" | ✅ Header korrekt auf W22 |
| `scripts/gate_ui.ps1` Zeile 13 | "W22 TOTALPACK: All Workpackages A-H" | ✅ W22-Zeile vorhanden |
| `scripts/gate_ui.ps1` Zeile 12 | `W18: RECOVERY/CLOSEOUT Edition` | ⚠ **Alte W18-Zeile noch drin** — nicht entfernt, nur ergänzt |
| `scripts/generate_gate_evidence.ps1` Zeile 2 | "W22 TOTALPACK Edition" | ✅ Header korrekt auf W22 |
| `scripts/generate_gate_evidence.ps1` Zeile 12 | `W18: RECOVERY/CLOSEOUT Edition` | ⚠ **Alte W18-Zeile noch drin** |

**Urteil:** Skripte sind erweitert, aber nicht bereinigt. Alte W18-Labels bleiben als Kommentar-Altlast stehen.

### 2.2 Evidence-Dokument korrekt?

| Artefakt | Claim | Tatsächlicher Befund |
|----------|-------|---------------------|
| `QA_EVIDENCE_W22_TOTALPACK_...md` Zeile 1 | — | ⚠ **Titel lautet "QA Evidence W18 RECOVERY"** statt W22 |
| Zeile 6 | — | ⚠ **"Evidence Level: Recovery-Closeout W18"** statt W22 |
| Zeile 7 | — | ⚠ **"Evidence Version: 5.1 (W18: RECOVERY...)"** statt W22 |
| Zeile 127 | — | ⚠ **"Automated W18 RECOVERY"** statt W22 |

**Root Cause:** `generate_gate_evidence.ps1` Zeile 455 hat den MD-Template-String hardcoded auf `"W18 RECOVERY"`. Die W22-Anpassung betraf nur den Kommentar-Header und den `$OutPrefix`, nicht das generierte MD-Template.

### 2.3 Gate-Ergebnisse belastbar?

| Gate | Evidence-Claim | Verifiziert? |
|------|---------------|--------------|
| Core-Gate | 284 passed, 2 skipped | ✅ Aus `QA_EVIDENCE_W22_TOTALPACK_...json` ableitbar |
| PI-010-Gate | 20 passed | ✅ |
| UI-Gate | 169 passed | ✅ |
| Hygiene-Gate | 7 violations (FAIL) | ⚠ **Jetzt 0 violations (CLEAN)** — Evidence veraltet |

**Urteil:** Die Gate-Zahlen im Evidence-Dokument sind Snapshots vom Zeitpunkt der Generierung und nicht mehr aktuell. Hygiene ist inzwischen CLEAN (0 violations).

### 2.4 Hygiene-Gate aktuell

```
=== Hygiene Check Result ===
Violations: 0 found
Status: ✅ CLEAN
Exit Code: 0
```

Aktueller Stand ist sauber — der W22-Evidence-Snapshot mit 7 violations ist überholt.

---

## 3. Impact

### Korrigierte Scorecard-Notiz W22

| WP | GLM-Claim | Audit-Verifiziert | Korrigierter Wert | Punkte |
|----|-----------|-------------------|-------------------|--------|
| WP-A Browser | 38/38 | 39 passed | **39 passed** | 25 ✅ |
| WP-B Feature Detail | 51/51 | 31 passed | **31 passed** | 20 ✅ |
| WP-C Operation Summary | 17/17 | 17 passed | 17 passed | 15 ✅ |
| WP-D Notification | 26/26 | 29 passed | **29 passed** | 15 ✅ |
| WP-E Direct Manipulation | 4+8 | 4+8 | 4 passed, 8 skipped | 25 ✅ |
| WP-F Controllers | 43/43 | 43 passed | 43 passed | 10 ✅ |
| WP-G Discoverability | "bestehend stabil" | **Kein Test-Beweis** | **Unbelegt** | 20 ⚠ |
| WP-H Gate/Evidence | "Skripte W22" | Skripte W22-Header ✅, MD-Template W18 ⚠ | **Teilweise** | 5/10 ⚠ |

### Gesamt-Bewertung

| Metrik | Wert |
|--------|------|
| Verifizierte Punkte | **115/140** (WP-A bis WP-F) |
| Teilweise belegte Punkte | **+5** (WP-H: Skripte ja, Template nein) |
| Unbelegte Punkte | **20** (WP-G: kein konkreter Test) |
| **Bewertung** | **🟡 YELLOW mit Auflagen** |

### Begründung YELLOW

1. **Pro Integration:** 163 Tests grün, 0 Failures, Hygiene CLEAN — technisch solide
2. **Auflagen:**
   - WP-G muss mit konkretem Test-Lauf belegt oder Punkte gestrichen werden
   - WP-H Evidence-Template muss W18→W22 korrigiert werden (5 Strings im PS1-Template)
   - GLM-Handoff Einzelzahlen müssen korrigiert werden

---

## 4. Validation

### Pflicht-Commands ausgeführt

**git status:**
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

**Hygiene-Gate:** 0 violations, CLEAN ✅

**W18-Label-Fundstellen in Evidence-Pipeline:**

| Datei | Zeile | Inhalt |
|-------|-------|--------|
| `scripts/gate_ui.ps1` | 12 | `# W18: RECOVERY/CLOSEOUT Edition` |
| `scripts/generate_gate_evidence.ps1` | 11 | `# W18: RECOVERY/CLOSEOUT Edition` |
| `scripts/generate_gate_evidence.ps1` | 455 | `"# QA Evidence W18 RECOVERY"` |
| `scripts/generate_gate_evidence.ps1` | 461 | `"Evidence Version: 5.1 (W18: RECOVERY..."` |
| `scripts/generate_gate_evidence.ps1` | 627 | `"Automated W18 RECOVERY"` |
| `QA_EVIDENCE_W22_...md` | 1,6,7,127 | Generiert aus obigen Templates |

---

## 5. Rest-Risiken

1. **W18-Labels im Template:** Wenn `generate_gate_evidence.ps1` erneut läuft, wird wieder ein W18-Evidence erzeugt. Fix: 5 Strings in Zeilen 455, 457, 461, 627 ändern. **(NO-GO in diesem Paket — scripts/** darf nicht editiert werden.)**

2. **WP-G Discoverability:** Keine harte Ablehnung — die Tests existieren (`test_discoverability_hints.py`, `test_discoverability_hints_w17.py`), sie sind nur im UI-Gate enthalten und nicht separat im GLM-Handoff als WP-G-Beweis referenziert.

3. **Evidence-Snapshot veraltet:** Das JSON/MD-Evidence-Paar ist ein Snapshot von ~01:30 UTC. Seitdem wurden browser.py und feature_detail_panel.py geändert (altki Smoke-Packs). Ein Re-Run des Evidence-Generators würde aktuellere Zahlen liefern.

---

**Ende des Addendums**
