Du bist `AI-LARGE-I-SKETCH` auf Branch `feature/v1-ux-aiB`.

Lies zuerst:
- `handoffs/HANDOFF_20260217_ai_largeI_w28_sketch_interaction_megapack.md`
- `handoffs/HANDOFF_20260217_ai_largeE_w26_recovery_hardgate.md`

## Ziel
W29 Sketch Stabilization Hardgate: bestehende W28-Sketch-Verbesserungen robust machen, inkl. stabiler Headless-Testbarkeit.

## Harte Regeln
1. Kein `skip` oder `xfail` als Problemlosung.
2. Keine Analyse-only Lieferung.
3. Keine Placeholder/TODO ohne Umsetzung.
4. Keine Edits ausserhalb Scope.

## Scope
- `gui/sketch_editor.py`
- `gui/sketch_snapper.py`
- `test/test_sketch_editor_w26_signals.py`
- `test/test_projection_trace_workflow_w26.py`
- `test/harness/test_interaction_direct_manipulation_w17.py`

## NO-GO
- `gui/main_window.py`
- `gui/viewport_pyvista.py`
- `gui/browser.py`
- `modeling/**`
- `scripts/**`

## Aufgaben
### 1) Direct-Edit Stabilisierung
- Arc/Ellipse/Polygon-Drag darf keinen Ghost-State hinterlassen.
- Cursor-Parity muss konsistent bleiben (hover und drag).
- SHIFT-Lock Verhalten fuer alle betroffenen Handles verifizieren und haerten.

### 2) Projection-Cleanup Robustheit
- Garantierte Clear-Pfade fuer Confirm/Cancel/Toolwechsel/Sketch-Exit.
- Keine Duplicate-Emission fuer identische Hover-Edge.

### 3) Headless-Test-Hardening
- W17 Harness darf unter Headless nicht crashen.
- Falls notwendig: test-seitige OpenGL-Software-Guards korrekt und lokal setzen.
- Keine globale Nebenwirkungen auf andere Test-Suites.

### 4) Testausbau
- Mindestens 20 neue oder geschaerfte Assertions.
- Fokus auf echte Verhaltensassertions, nicht nur `hasattr`.

## Pflicht-Validierung
```powershell
$env:QT_OPENGL='software'
conda run -n cad_env python -m py_compile gui/sketch_editor.py gui/sketch_snapper.py test/test_sketch_editor_w26_signals.py test/test_projection_trace_workflow_w26.py test/harness/test_interaction_direct_manipulation_w17.py
conda run -n cad_env python -m pytest -q test/test_sketch_editor_w26_signals.py -v
conda run -n cad_env python -m pytest -q test/test_projection_trace_workflow_w26.py -v
conda run -n cad_env python -m pytest -q test/harness/test_interaction_direct_manipulation_w17.py::TestArcDirectManipulation -v
```

## Abgabe
Datei:
- `handoffs/HANDOFF_20260217_ai_largeI_w29_sketch_stabilization_hardgate.md`

Pflichtinhalte:
1. Geaenderte Dateien mit Begruendung
2. Vorher/Nachher Verhalten
3. Exakte Testkommandos + Ergebnisse
4. Restrisiken

