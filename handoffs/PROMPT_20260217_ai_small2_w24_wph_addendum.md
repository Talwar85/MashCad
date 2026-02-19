Du bist KI-SMALL-2 auf Branch `feature/v1-ux-aiB`.

MISSION (klein, 20-40 Minuten, no long tests):
WP-H (Gate/Evidence) Nachweis sauberziehen und Handoff-Zahlen konsistent dokumentieren.

ERLAUBTE DATEIEN:
- `handoffs/**`
- `roadmap_ctp/**`
- optional: `docs/**`

NO-GO:
- Kein Edit in `gui/**`
- Kein Edit in `modeling/**`
- Kein Edit in `test/**`
- Kein Edit in `scripts/**`

AUFGABEN:
1) Erzeuge ein Addendum mit harten Nachweisen fuer WP-H:
   - Belege aus vorhandenem Evidence-Output sammeln
   - klar markieren, wo alte Labels (W18) noch auftauchen
2) Erzeuge eine korrigierte Scorecard-Notiz fuer W22:
   - Einzelzahlen A/B/D richtigstellen
   - Gesamtbewertung als "YELLOW mit Auflagen" begruenden
3) Definiere einen Micro-Runbook-Block (max. 8 Schritte), wie man WP-H in <10 min erneut validiert (ohne Full-Suite).

PFLICHT-COMMANDS (schnell):
```powershell
rg -n "W18|W22|Hygiene|passed|skipped|Completion" handoffs/HANDOFF_20260217_glm47_totalpack_all_tasks.md roadmap_ctp/QA_EVIDENCE_W22_TOTALPACK_20260217_codex_validate.md
powershell -ExecutionPolicy Bypass -File scripts/hygiene_check.ps1
```

RUECKGABE:
1) `handoffs/HANDOFF_20260217_ai_small2_w24_wph_addendum.md`
   Struktur:
   - Problem
   - Claim-vs-Proof (WP-H fokussiert)
   - Impact
   - Validation
   - Rest-Risiken
2) `roadmap_ctp/W22_WPH_MICRO_RUNBOOK.md`
   - Max 8 nummerierte Schritte
   - Jeder Schritt mit Command und erwarteter Kurz-Ausgabe

WICHTIG:
- Kein Marketing-Text, nur belastbare Fakten.
- Keine langen Testlaeufe starten.
