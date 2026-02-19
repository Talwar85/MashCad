Du bist KI-LARGE-D (Workflow Product Leap Cell) auf Branch `feature/v1-ux-aiB`.

MISSION (sehr großes Paket):
3D?2D Workflow-Leaps liefern: schneller nachzeichnen, projektieren, orientieren. Fokus auf echte Nutzerwirkung.

WICHTIG:
- Dieses Paket ist exklusiv fuer Workflow/Orchestrierung.
- DARF sich NICHT mit KI-LARGE-C ueberschneiden.

ERLAUBTE DATEIEN:
- `gui/main_window.py`
- `gui/viewport_pyvista.py`
- `gui/viewport/selection_mixin.py`
- `gui/browser.py`
- `test/test_main_window*.py`
- `test/test_browser*.py`
- `test/harness/test_interaction_consistency.py` (nur falls fuer Workflow-Repro zwingend)

NO-GO:
- Kein Edit in `gui/sketch_editor.py`
- Kein Edit in `gui/widgets/feature_detail_panel.py`
- Kein Edit in `gui/widgets/operation_summary.py`
- Kein Edit in `gui/managers/notification_manager.py`
- Kein Edit in `scripts/**`
- Kein Edit in `modeling/**`

ZIELBILD (Product Leaps):
1) 3D Trace Assist v1:
- klare Aktion „auf Sketch-Ebene nachzeichnen“
- sofort sichtbare Preview/Hinweise
- robuste Rückkehr von 3D zu Sketch

2) Project-Workflow Beschleunigung:
- Auswahl+Projektionspfad mit weniger Klicks
- nachvollziehbares visuelles Feedback (was wird projiziert)
- Fehlerfälle klar, nicht stumm

3) Orientation & Peek UX:
- Rotate/Peek Hinweise im richtigen Kontext
- Toolbar-Verstecktes Verhalten besser auffindbar
- Right-click empty = konsistenter Abbruch im Workflow

4) Browser-Workflow Kontext:
- bei Feature-/Sketch-Auswahl schneller Sprung in relevanten Modus
- kein state-leak bei Moduswechseln

DELIVERY-ANFORDERUNGEN:
- Mindestens 3 sichtbare Workflow-Leaps
- Mindestens 2 neue reproduzierbare Workflow-Regressionstests
- Keine neue Blocker-Regressionsspur im bestehenden UI-Flow

PFLICHT-VALIDIERUNG:
```powershell
conda run -n cad_env python -m pytest -q test/test_feature_controller.py test/test_export_controller.py -v
conda run -n cad_env python -m pytest -q test/test_browser_tooltip_formatting.py -v
# Neue/angepasste Workflow-Tests aus deiner Lieferung:
conda run -n cad_env python -m pytest -q <deine_workflow_tests> -v
```

RUECKGABE:
- Datei: `handoffs/HANDOFF_20260217_ai_largeD_w25_workflow_product_leaps.md`
- Struktur:
  1. Problem
  2. API/Behavior Contract
  3. Impact
  4. Validation (exakte Commands + Zahlen)
  5. Breaking Changes / Rest-Risiken
  6. Product Change Log (user-facing)
  7. Workflow Acceptance Checklist
  8. Nächste 10 Aufgaben

NO-GO fuer Abgabe:
- nur Refactor ohne sichtbaren Workflow-Nutzen
- nur manuelle Verifikation ohne testbaren Repro-Flow
- Änderungen in NO-GO-Dateien
