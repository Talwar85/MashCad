Du bist KI-SMALL auf Branch `feature/v1-ux-aiB`.

MISSION (kleines Paket, 45-75 Minuten):
Schneller Integrations-Check ohne Produktcode-Umbau. Ziel ist verwertbare Freigabe-Ampel.

ERLAUBTE DATEIEN:
- `handoffs/**`
- `docs/**`

NO-GO:
- Kein Edit in `gui/**`
- Kein Edit in `modeling/**`
- Kein Edit in `scripts/**`
- Keine neuen Tests

AUFGABEN:
1) Lies und bewerte:
- `handoffs/HANDOFF_20260217_glm47_totalpack_all_tasks.md`
- `handoffs/HANDOFF_20260217_altki_smokepack_browser.md`
- `handoffs/HANDOFF_20260217_altki_smokepack_feature_detail.md`
2) Erstelle ein kurzes Audit mit Claim-vs-Proof:
- Welche Claims sind sauber nachweisbar?
- Welche Claims sind Zahlendreher/Inkonsistenzen?
3) Liefere eine Release-Ampel:
- `GREEN`: sofort integrierbar
- `YELLOW`: integrierbar mit Auflagen
- `RED`: nicht integrierbar

PFLICHT-COMMANDS (nur Lesen/Checks):
- `git status --short`
- `rg -n "passed|skipped|Completion" handoffs/HANDOFF_20260217_glm47_totalpack_all_tasks.md`

RUECKGABE:
- Datei: `handoffs/HANDOFF_20260217_ai_small_w23_audit.md`
- Struktur:
  1. Problem
  2. Claim-vs-Proof
  3. Impact
  4. Validation
  5. Ampel + 5 konkrete Follow-ups
