# Sketch-Agent - Architektur Plan

## Idee

Ein Agent der wie ein Mensch CAD-Sketches zeichnet und OCP-Operationen durchführt.

**Use Cases:**
- 🧪 Automatisches Testing des CAD-Systems
- 🐛 Bug-Discovery (zufällige Operationen finden Edge-Cases)
- 📊 Training-Data-Generation für ML-Modelle
- 🎨 Design-Exploration (zufällige Designs generieren)
- 📈 Performance-Testing (Stress-Test mit komplexen Modellen)

## Architektur

```
┌─────────────────────────────────────────────────────────────┐
│                    SketchAgent                              │
│  - Zufällige Sketch-Generierung (mensch-like)              │
│  - OCP-Operationen (Extrude, Fillet, Chamfer, Boolean)     │
│  - Feedback-Learning (was funktioniert, was nicht)         │
└─────────────────────────────────────────────────────────────┘
         │                    │                    │
         ▼                    ▼                    ▼
┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐
│  SketchGenerator│  │  OperationAgent │  │  FeedbackLoop   │
│                 │  │                 │  │                 │
│ - Linien        │  │ - Extrude       │  │ - Erfolge       │
│ - Kreise        │  │ - Fillet        │  │ - Fehler        │
│ - Bögen         │  │ - Chamfer       │  │ - Optimierung   │
│ - Constraints   │  │ - Boolean       │  │                 │
└─────────────────┘  └─────────────────┘  └─────────────────┘
```

## Komponenten

### 1. SketchGenerator

Erstellt "menschliche" Sketches mit zufälligen aber sinnvollen Formen.

```python
class SketchGenerator:
    """Generiert zufällige aber plausible Sketches."""

    def generate_random_profile(self) -> Sketch:
        """
        Generiert ein zufälliges Profil für Extrusion.

        Strategien:
        - Rechteck mit Variationen
        - Polygon (3-8 Seiten)
        - Kreis + Abgeschnitte
        - Mehrere geschlossene Konturen
        """

    def generate_mechanical_part(self) -> Sketch:
        """
        Generiert mechanische Bauteile.

        Beispiele:
        - Welle mit Bohrung
        - Flansch mit Schraubenlöchern
        - Bracket mit Mounting-Holes
        """
```

### 2. OperationAgent

Führt OCP-Operationen auf Sketches aus.

```python
class OperationAgent:
    """Führt CAD-Operationen aus."""

    def extrude(self, sketch, distance) -> Solid:
        """Extrudiert Sketch zu Solid."""

    def fillet(self, solid, edges, radius) -> Solid:
        """Rundet Kanten ab."""

    def chamfer(self, solid, edges, distance) -> Solid:
        """Kante abschrägen."""

    def boolean_cut(self, solid, tool) -> Solid:
        """Subtrahiert Tool von Solid."""

    def shell(self, solid, faces, thickness) -> Solid:
        """Erstellt Hohlkörper."""
```

### 3. DesignPatterns

Vordefinierte Design-Patterns für realistische Bauteile.

```python
DESIGN_PATTERNS = {
    "shaft": {
        "base": "circle",
        "operations": ["extrude", "fillet_edges"],
        "parameters": {"diameter": (10, 50), "length": (50, 200)}
    },
    "flange": {
        "base": "circle",
        "operations": ["extrude", "add_holes", "fillet"],
        "parameters": {"diameter": (50, 150), "holes": (4, 8)}
    },
    "bracket": {
        "base": "rectangle",
        "operations": ["extrude", "cut_slot", "add_holes"],
        "parameters": {"width": (30, 100), "height": (50, 150)}
    },
    "housing": {
        "base": "rectangle",
        "operations": ["extrude", "shell", "cut_opening"],
        "parameters": {"width": (50, 200), "wall_thickness": (2, 10)}
    }
}
```

### 4. FeedbackLoop

Lernt aus Ergebnissen und optimiert Strategien.

```python
class FeedbackLoop:
    """Sammelt Feedback und lernt daraus."""

    def record_success(self, operation, params, time, result):
        """Zeichnet erfolgreiche Operation auf."""

    def record_failure(self, operation, params, error):
        """Zeichnet fehlgeschlagene Operation auf."""

    def get_success_rate(self, operation) -> float:
        """Gibt Erfolgsrate zurück."""

    def suggest_parameters(self, operation) -> dict:
        """Schlägt erfolgreiche Parameter vor."""
```

## Implementation Plan

### Phase 1: Grundlagen (1-2 Tage)
- [ ] `sketch_agent.py` - Basis-Klasse
- [ ] `sketch_generator.py` - Zufällige Sketches
- [ ] `operation_agent.py` - OCP-Operation Wrapper

### Phase 2: Design Patterns (1 Tag)
- [ ] `design_patterns.py` - Vordefinierte Bauteile
- [ ] Parameter-Ranges für verschiedene Typen

### Phase 3: Feedback & Learning (1-2 Tage)
- [ ] `feedback_loop.py` - Ergebnis-Sammlung
- [ ] Statistiken und Reporting
- [ ] Parameter-Optimierung

### Phase 4: Automated Testing (1 Tag)
- [ ] `test_runner.py` - Führt Agenten aus
- [ ] Error-Reporting
- [ ] Performance-Metriken

## Test-Scenario

```python
# Einfacher Test
agent = SketchAgent()

# 100 zufällige Teile generieren
for i in range(100):
    # Sketch generieren
    sketch = agent.generate_random_profile()

    # Extrudieren
    solid = agent.extrude(sketch, distance=random(10, 50))

    # Zufällige Fillets
    edges = agent.select_random_edges(solid, count=random(1, 5))
    solid = agent.fillet(solid, edges, radius=random(1, 5))

    # Bohrungen hinzufügen
    if random() > 0.5:
        solid = agent.add_random_holes(solid, count=random(1, 4))

    # Speichern
    solid.export_step(f"test_output/part_{i}.step")

    # Feedback aufzeichnen
    agent.record_success(...)
```

## Benefits

1. **Testing:** Findet Bugs die manuelle Tests übersehen
2. **Coverage:** Testet Kombinationen die ein Mensch nicht probieren würde
3. **Regression:** Neue Releases werden gegen getestet
4. **Performance:** Stresstest für grosse Modelle
5. **ML Training:** Generiert Trainingsdaten für CAD-ML-Modelle

## nächste Schritte

1. Erstelle `sketching/sketch_agent.py`
2. Implementiere `SketchGenerator` mit zufälligen Profilen
3. Implementiere `OperationAgent` für Extrude/Fillet/Chamfer
4. Erste Tests mit 100 zufälligen Teilen
