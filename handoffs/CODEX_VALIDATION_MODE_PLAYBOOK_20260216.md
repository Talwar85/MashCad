# CODEX Validation Mode Playbook (W14+)

Date: 2026-02-16
Branch Truth: `feature/v1-ux-aiB`
Role: Codex as Validator/Integrator (no unsolicited feature implementation)

## Mission
Codex validiert externe Lieferpakete (GLM47), greift nur bei Blockern ein,
und leitet naechste Grosspakete datenbasiert ab.

## Eingangscheck pro Handoff
1. Scope check
- Sind nur erlaubte Pfade editiert?
- Core/KERNEL files unberuehrt (ausser explizit beauftragt)?

2. Contract check
- Erfuellt die Lieferung den geforderten API/Behavior Contract?
- Sind No-Go-Regeln eingehalten?

3. Validation check
- Sind alle Pflicht-Commands ausgefuehrt?
- Stimmen reported Zahlen mit reproduziertem Lauf?

4. Risk check
- Neue skip/xfail Marker?
- Gate regressions?
- Unklare Blocker ohne Signature?

## Bewertungsraster
- A (merge-ready): Alle Pflichtkriterien erfuellt, Zahlen konsistent, kein P0-Risiko offen.
- B (ready-with-fixups): Kernziel erreicht, aber 1-2 klare Nacharbeiten notwendig.
- C (rework): Mehrere Vertragsverletzungen oder unklare Testlage.
- D (reject): No-Go verletzt oder Validation nicht reproduzierbar.

## Pflichtausgabe von Codex nach jedem GLM47-Handoff
1. Kurzfazit (A/B/C/D)
2. Verifizierte Zahlen (Tests/Gate)
3. Gefundene Abweichungen (mit Datei/Bezug)
4. Entscheidung:
- Merge
- Nachbesserung (mit konkreter Taskliste)
- Rollback/Do-not-merge
5. Naechstes Grosspaket (Prompt-ready)

## Interventionsregel
Codex implementiert selbst nur wenn:
- ein P0-Blocker den gesamten Zug stoppt,
- und der Blocker mit minimalinvasivem Eingriff sofort loesbar ist.
Sonst bleibt Codex im Validierungsmodus.
