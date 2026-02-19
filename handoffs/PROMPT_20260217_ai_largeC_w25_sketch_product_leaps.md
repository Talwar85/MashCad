Du bist KI-LARGE-C (Sketch Product Leap Cell) auf Branch `feature/v1-ux-aiB`.

MISSION (sehr groﬂes Paket):
Sketch-Interaktion auf Ñpro CADì-Niveau bringen. Kein Test-Skip als Ersatz fuer UX-Fixes.

WICHTIG:
- Dieses Paket ist exklusiv fuer Sketch/2D-Interaktion.
- DARF sich NICHT mit KI-LARGE-D ueberschneiden.

ERLAUBTE DATEIEN:
- `gui/sketch_editor.py`
- `test/harness/test_interaction_direct_manipulation_w17.py`
- `test/harness/test_interaction_consistency.py`
- `test/test_ui_abort_logic.py`
- `test/test_discoverability_hints.py`
- `test/test_discoverability_hints_w17.py`

NO-GO:
- Kein Edit in `gui/main_window.py`
- Kein Edit in `gui/browser.py`
- Kein Edit in `gui/widgets/**`
- Kein Edit in `gui/managers/**`
- Kein Edit in `scripts/**`
- Kein Edit in `modeling/**`

ZIELBILD (Product Leaps):
1) Arc Direct Edit parity:
- center/radius/start/end robust
- kein versteckter Zustand nach ESC/Finish
- konsistente Cursor-Modi

2) Rectangle/Line pro-level drag:
- Kantenziehen passt Constraint/Dimensionen robust an
- Drag-Hotspots klar und reproduzierbar
- Right-click empty + ESC immer gleiche Endzust‰nde

3) Discoverability v3:
- sichtbare Hinweise fuer Rotate + Space-Peek
- anti-spam + context-hints stabil
- keine API-Existenztests als Hauptnachweis

4) Testqualit‰t:
- Skip/Placeholder in W17-Direct-Manipulation reduzieren
- Behavior-Proof statt nur method existence
- kein neuer skip/xfail in neuem Code

DELIVERY-ANFORDERUNGEN:
- Mindestens 3 sichtbare UX-Leaps
- Mindestens 8 neue oder aufgewertete Behavior-Proof-Assertions
- Keine Regression im Abort-Contract

PFLICHT-VALIDIERUNG (in dieser Reihenfolge):
```powershell
conda run -n cad_env python -m pytest -q test/harness/test_interaction_direct_manipulation_w17.py::TestArcDirectManipulation -v
conda run -n cad_env python -m pytest -q test/harness/test_interaction_consistency.py test/test_ui_abort_logic.py -v
conda run -n cad_env python -m pytest -q test/test_discoverability_hints.py test/test_discoverability_hints_w17.py -v
```

RUECKGABE:
- Datei: `handoffs/HANDOFF_20260217_ai_largeC_w25_sketch_product_leaps.md`
- Struktur:
  1. Problem
  2. API/Behavior Contract
  3. Impact
  4. Validation (exakte Commands + Zahlen)
  5. Breaking Changes / Rest-Risiken
  6. Product Change Log (user-facing)
  7. Scorecard (Leaps + Testqualit‰t)
  8. N‰chste 10 Aufgaben

NO-GO fuer Abgabe:
- "Done" mit Skip statt UX-Fix
- fehlende Command-Outputs
- nur Testumbau ohne sichtbare Produkt‰nderung
