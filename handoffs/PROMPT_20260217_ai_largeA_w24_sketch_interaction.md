Du bist KI-LARGE-A (Sketch/Interaction Delivery Cell) auf Branch `feature/v1-ux-aiB`.

MISSION (sehr großes Paket):
Direct-Manipulation und Discoverability auf Produktniveau bringen.

WICHTIG: Dieses Paket DARF sich NICHT mit KI-LARGE-B überschneiden.

ERLAUBTE DATEIEN (nur diese Bereiche):
- `gui/sketch_editor.py`
- `test/harness/test_interaction_direct_manipulation_w17.py`
- `test/harness/test_interaction_consistency.py`
- `test/test_ui_abort_logic.py`
- `test/test_discoverability_hints.py`
- `test/test_discoverability_hints_w17.py`

NO-GO:
- Kein Edit in `gui/browser.py`
- Kein Edit in `gui/widgets/feature_detail_panel.py`
- Kein Edit in `gui/widgets/operation_summary.py`
- Kein Edit in `gui/managers/notification_manager.py`
- Kein Edit in `scripts/**`
- Kein Edit in `modeling/**`

ZIELE:
1) Arc/Ellipse/Line/Rectangle Direct-Edit konsistent: Cursor, Drag-Start, Drag-Abbruch, Live-Feedback.
2) Harness-Qualität: Keine 0-item Illusion, keine pseudo-grünen Exists-only Tests.
3) Abort-Contract hart: ESC und Rechtsklick in allen Direct-Edit-Modi gleiches Endstate.
4) Discoverability sichtbar: Rotate/Peek-Hinweise klar, anti-spam bleibt stabil.

MINDEST-ABNAHME:
- Mindestens 2 sichtbare UX-Verbesserungen + 2 robuste Behavior-Proof Tests pro Bereich.
- Keine neuen skips/xfails.

PFLICHT-VALIDIERUNG:
```powershell
conda run -n cad_env python -m pytest -q test/harness/test_interaction_direct_manipulation_w17.py test/harness/test_interaction_consistency.py test/test_ui_abort_logic.py -v
conda run -n cad_env python -m pytest -q test/test_discoverability_hints.py test/test_discoverability_hints_w17.py -v
```

RUECKGABE:
- Datei: `handoffs/HANDOFF_20260217_ai_largeA_w24_sketch_interaction.md`
- Struktur:
  1. Problem
  2. API/Behavior Contract
  3. Impact
  4. Validation (exakte Commands + Zahlen)
  5. Breaking Changes / Rest-Risiken
  6. Product Change Log (user-facing)
  7. Nächste 8 Aufgaben
