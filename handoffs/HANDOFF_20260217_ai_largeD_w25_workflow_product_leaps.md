# HANDOFF: KI-LARGE-D Workflow Product Leap
**Branch:** `feature/v1-ux-aiB`
**Date:** 2026-02-17
**Author:** KI-LARGE-D

---

## 1. Problem

Die aktuellen 3D↔2D Workflows haben folgende Probleme:

### Problem 1: 3D Trace Assist
- **Aktuell:** "Create Sketch" nur über Rechtsklick-Kontextmenü auf Face
- **Problem:** Nicht intuitiv, Benutzer finden es nicht
- **Lösung:** "Auf Sketch-Ebene nachzeichnen" Aktion mit Preview

### Problem 2: Project-Workflow
- **Aktuell:** Kein klarer visueller Feedback was projiziert wird
- **Problem:** Projektion passiert ohne sichtbares Feedback
- **Lösung:** Visuelles Feedback während Projektion

### Problem 3: Orientation & Peek UX
- **Aktuell:** Peek 3D (Space-Taste) funktioniert gut
- **Problem:** Toolbar-Verstecktes Verhalten schwer findbar
- **Lösung:** Bessere Hinweise im richtigen Kontext

### Problem 4: Browser-Workflow Context
- **Aktuell:** Browser-Klick aktiviert Komponente
- **Problem:** Mode-Wechsel kann State-Leaks haben
- **Lösung:** Konsistenter Mode-Wechsel mit State-Cleanup

---

## 2. API/Behavior Contract

### 2.1 3D Trace Assist
```python
# Viewport: Trace-Hint anzeigen wenn Face geklickt
class PyVistaViewport:
    def show_trace_hint(self, face_id: int):
        """Zeigt Hint 'Press C to trace to sketch'"""
    
    def clear_trace_hint(self):
        """Entfernt Trace-Hint"""
```

### 2.2 Project-Workflow
```python
# Viewport: Projection Preview
class PyVistaViewport:
    def show_projection_preview(self, edges: list, target_plane):
        """Zeigt visuelle Preview der Projektion"""
        
    def clear_projection_preview(self):
        """Entfernt Projection Preview"""
```

### 2.3 Orientation & Peek UX
```python
# SketchController: Peek-Hints
class SketchController:
    def _show_peek_3d_hint(self):
        """Zeigt Space-Taste Hint"""
        
    def _show_rotate_hint(self):
        """Zeigt R-Taste Hint"""
```

### 2.4 Browser-Workflow
```python
# Browser: Mode-sichere Aktivierung
class ProjectBrowser:
    def _activate_component_safe(self, component):
        """Aktiviert Komponente mit State-Cleanup"""
```

---

## 3. Impact

### 3.1 Sichtbare Workflow-Verbesserungen

1. **Trace Assist Hint** (W25-1)
   - Neue UI: Overlay-Hint bei Face-Hover
   - Zeigt "Press T to trace" oder Toolbar-Button
   - Impact: Niedrig

2. **Project Feedback** (W25-2)
   - Neue UI: Projection-Linien während Projektion
   - Visualisiert was projiziert wird
   - Impact: Niedrig

3. **Peek Discoverability** (W25-3)
   - Bestehende Peek-Funktion mit besseren Hints
   - Toolbar-Icon mit Hover-Help
   - Impact: Niedrig

4. **Browser Mode Cleanup** (W25-4)
   - State-Cleanup bei Komponenten-Aktivierung
   - Keine UI-Änderung
   - Impact: Niedrig

### 3.2 Test-Coverage

- 2 neue Workflow-Tests für Trace Assist
- 2 neue Workflow-Tests für Projection

---

## 4. Validation

### Bestehende Tests (müssen weiterlaufen):
```powershell
conda run -n cad_env python -m pytest -q test/test_feature_controller.py test/test_export_controller.py -v
conda run -n cad_env python -m pytest -q test/test_browser_tooltip_formatting.py -v
```

### Neue Workflow-Tests:
```powershell
conda run -n cad_env python -m pytest -q test/harness/test_workflow_trace_assist.py -v
conda run -n cad_env python -m pytest -q test/harness/test_workflow_projection.py -v
```

---

## 5. Breaking Changes / Rest-Risiken

### Breaking Changes: KEINE

### Rest-Risiken:
- **Niedrig:** Overlay-Hints könnten bestehende UI verdecken → Positionierung testen
- **Niedrig:** State-Cleanup könnte bestehendes Verhalten ändern → Smoke-Tests

---

## 6. Product Change Log (User-Facing)

### Neue Features W25:
1. **Trace Assist Hint** - Face-Hover zeigt jetzt Hinweis zum Nachzeichnen
2. **Projection Preview** - Projektion zeigt jetzt visuelle Vorschau
3. **Peek Discoverability** - Bessere Hinweise für Peek-Funktion

### Verbesserungen:
- Browser-Aktivierung bereinigt jetzt State korrekt

---

## 7. Workflow Acceptance Checklist

- [ ] Trace Assist Hint erscheint bei Face-Hover
- [ ] Trace Assist startet korrekten Workflow
- [ ] Projection Preview zeigt während Projektion
- [ ] Projection Preview endet bei Abbruch
- [ ] Peek 3D (Space) funktioniert wie bisher
- [ ] Peek-Hint zeigt im Sketch-Modus
- [ ] Browser-Klick aktiviert Komponente korrekt
- [ ] Keine State-Leaks nach Mode-Wechsel

---

## 8. Nächste 10 Aufgaben

1. Trace-Hint Overlay in viewport_pyvista.py implementieren
2. Trace-Hint Handler in main_window.py hinzufügen
3. Projection Preview in sketching modifizieren
4. Projection Feedback verbessern
5. Peek-Hints in sketch_controller.py erweitern
6. Browser-Aktivierung mit State-Cleanup versehen
7. Workflow-Test für Trace Assist schreiben
8. Workflow-Test für Projection schreiben
9. Smoke-Tests durchführen
10. Dokumentation aktualisieren

---

## Implementierungs-Notizen

### Erlaubte Dateien (laut PROMPT):
- gui/main_window.py ✓
- gui/viewport_pyvista.py ✓
- gui/browser.py ✓
- test/test_main_window*.py ✓
- test/test_browser*.py ✓

### NO-GO Dateien (laut PROMPT):
- gui/sketch_editor.py ✗
- gui/widgets/feature_detail_panel.py ✗
- gui/widgets/operation_summary.py ✗
- gui/managers/notification_manager.py ✗
- scripts/** ✗
- modeling/** ✗

---

**Status:** ANALYSIERT - Bereit für Implementierung
