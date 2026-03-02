# MashCad - Architektur-Referenz

> **Version:** 14 | **Stand:** Februar 2026 | **Autor:** Claude (Lead Developer)

---

## Philosophie: CAD-Kernel ist Master

**Kernprinzip:** Das gesamte System baut auf dem CAD-Kernel (Build123d/OpenCASCADE) auf. Es gibt **keine Fallback-Lösungen**. Wenn der Kernel fehlschlägt, schlägt die Operation fehl - klar und deutlich.

Neue Features nur mit Feature Toggle in config/feature_flag.py
Neue Features mit Logging was shcnelles Debuggen erlaubt.
Keine Fallbacks oder stille umwege.
Wenn  etwas unklar ist, keine Annahmen treffne, sondern nachfragen.
to.dict from.dict und FeatureCOmmandas beachten. bei jeder neuen Implementation.
Ein sauberes Speichern und laden und undo/redo System muss immer gewährleistet sein.
Abhnahmetests erfolgen durch den User.

```
┌─────────────────────────────────────────────────────┐
│              SINGLE SOURCE OF TRUTH                 │
│                                                     │
│    _build123d_solid (OCP/OpenCASCADE)              │
│              ↓ (lazy)                               │
│    vtk_mesh / vtk_edges (PyVista)                  │
│              ↓                                      │
│    Viewport Rendering                               │
└─────────────────────────────────────────────────────┘
```

conda run -n cad_env python -c "

**Anti-Patterns (VERBOTEN):**
- Mesh-basierte Fallbacks für Boolean-Operationen
- Manuelle Mesh-Manipulation ohne Kernel-Update
- Cache-Invalidierung vergessen nach Kernel-Änderungen
- Multi-Strategy-Fallbacks ("wenn A nicht klappt, probiere B")

---

## UX-Philosophie: Fusion-Plus

### Benchmark: CAD
- Mindeststandard = CAD Feature-Implementierung
- Ziel: **Besser** → flüssiger UX, weniger Klicks
- Abbruchkriterium: Nicht "fertig" wenn es funktioniert, sondern wenn es sich **gut anfühlt**

### Konsistenz (Anti-Insel-Policy)
- Neue Features analysieren zuerst die UX von **Transform V3** (Referenz)
- Workflow-Konsistenz: Feature A erlaubt Viewport-Selektion → Feature B auch
- UI-Integration: Neue Features passen in bestehende Panel-Strukturen

### Fehlerkultur (Anti-Schwammig-Policy)
- Fehler müssen **glasklar** unterscheidbar sein
- Strukturierte Result-Types: `SUCCESS`, `WARNING`, `EMPTY`, `ERROR`
- "Sollte gehen" ist nicht akzeptabel

---

## Tech-Stack

| Komponente | Technologie | Rolle |
|------------|-------------|-------|
| **CAD-Kernel** | Build123d + OCP (OpenCASCADE) | Master - alle Geometrie |
| **Visualization** | PyVista (VTK) | Slave - nur Darstellung |
| **GUI** | PySide6 (Qt6) | User Interface |
| **2D-Sketcher** | Custom + Shapely | Constraint-basierte Skizzen |
| **Logging** | Loguru | Strukturiertes Logging |

---

## Architektur-Säulen

### 1. Single Source of Truth (Phase 2)

Der CAD-Kernel (`_build123d_solid`) ist die einzige Wahrheit. Meshes werden **lazy** generiert.

```python
class Body:
    def __init__(self):
        self._build123d_solid = None      # ← MASTER
        self._mesh_cache = None           # ← Privat, lazy
        self._mesh_cache_valid = False

    @property
    def vtk_mesh(self):
        """Lazy-loaded - regeneriert automatisch bei Zugriff"""
        if not self._mesh_cache_valid:
            self._regenerate_mesh()
        return self._mesh_cache

    def invalidate_mesh(self):
        """Nach JEDER Kernel-Änderung aufrufen!"""
        self._mesh_cache_valid = False
```

**Regel:** Nach jeder Änderung an `_build123d_solid` → `invalidate_mesh()` aufrufen.

### 2. Fail-Fast Boolean Engine (Phase 3)

Keine Multi-Strategy-Fallbacks. Eine Operation funktioniert oder sie schlägt fehl.

```python
# modeling/boolean_engine_v4.py

class BooleanEngineV4:
    PRODUCTION_FUZZY_TOLERANCE = 1e-4  # 0.1mm (CAD-Level)

    def execute_boolean(body, tool_solid, operation):
        # Eine Strategie, klares Ergebnis
        with BodyTransaction(body) as txn:
            result = _execute_ocp_boolean(...)

            if result is None:
                raise BooleanOperationError("Boolean fehlgeschlagen")

            body._build123d_solid = result
            body.invalidate_mesh()
            txn.commit()
```

**OCP Boolean Settings (Phase 3):**
```python
op.SetFuzzyValue(1e-4)      # Toleranz für numerische Ungenauigkeiten
op.SetRunParallel(True)     # Multi-Threading
# SetGlue NICHT verwenden - verursacht kaputte Bodies
```

### 3. Transaction-basierte Sicherheit (Phase 1)

Jede destruktive Operation ist transaktionsgesichert. Fehler → automatischer Rollback.

```python
# modeling/body_transaction.py

with BodyTransaction(body, "Boolean Cut") as txn:
    # Snapshot wird automatisch erstellt

    result = execute_boolean(...)

    if result.is_error:
        raise BooleanOperationError(result.message)
        # → Automatischer Rollback, Body bleibt intakt

    txn.commit()  # Erst hier wird Änderung permanent
```

### 4. Strukturierte Result-Types (Phase 4)

Klare Unterscheidung zwischen Erfolg, Warnung, Leer und Fehler.

```python
# modeling/result_types.py

class ResultStatus(Enum):
    SUCCESS = auto()   # Alles OK
    WARNING = auto()   # OK aber mit Einschränkungen
    EMPTY = auto()     # Kein Ergebnis (kein Fehler!)
    ERROR = auto()     # Fehlgeschlagen

# Verwendung:
result = BooleanEngineV4.execute_boolean(body, cutter, "Cut")

if result.status == ResultStatus.SUCCESS:
    logger.success(result.message)
elif result.status == ResultStatus.ERROR:
    show_error_dialog(result.message)
```

### 5. TNP v3.0 - Topological Naming Problem (Phase 5)

Professionelles System zur persistenten Shape-Identifikation über Boolean-Operationen hinweg.

**Das Problem:** OpenCASCADE zerstört und erstellt Edges/Faces bei Boolean-Operationen neu. Frühere Referenzen werden ungültig.

**Die Lösung:** Mehrstufiges Resolution-System:

```python
# modeling/tnp_shape_reference.py

@dataclass(frozen=True)
class ShapeID:
    """Immutable identifier for shape tracking"""
    feature_id: str      # Feature that created this reference
    local_id: int        # Index within feature
    shape_type: ShapeType

@dataclass
class ShapeReference:
    """Persistent reference with multi-strategy resolution"""
    ref_id: ShapeID
    original_shape: TopoDS_Shape      # OCP shape for history lookup
    geometric_selector: Any            # Fallback: geometric matching
    
    def resolve(self, solid, history=None):
        # Strategy 1: BRepTools_History (if available)
        if history:
            return self._resolve_via_history(history)
        
        # Strategy 2: Geometric matching (center, direction, length)
        return self._resolve_via_geometry(solid)

class ShapeReferenceRegistry:
    """Central registry for all shape references in a body"""
    def resolve_all(self, solid) -> Dict[ShapeID, TopoDS_Shape]:
        # Resolves all registered references against new solid
```

**Feature-Integration (Fillet/Chamfer):**
```python
@dataclass
class FilletFeature(Feature):
    edge_shape_ids: List[ShapeID] = None        # TNP v3.0 Primary
    geometric_selectors: List = None             # Geometric Fallback
    edge_selectors: List = None                  # Legacy Fallback
```

**Resolution-Strategien (in Reihenfolge):**
1. **History-based** (BRepTools_History) - Primär wenn verfügbar
2. **Geometric matching** - Fallback mit 40/30/20/10 Gewichtung
3. **Legacy point selectors** - Letzter Fallback

---

## Directory-Struktur

```
MashCad/
├── main.py                           # Entry Point
│
├── modeling/
│   ├── __init__.py                   # Body, Feature, Document
│   ├── boolean_engine_v4.py          # Fail-Fast Boolean Operations
│   ├── body_transaction.py           # Transaction/Rollback System
│   ├── result_types.py               # OperationResult, BooleanResult
│   ├── cad_tessellator.py            # Kernel → Mesh Konvertierung
│   ├── geometric_selector.py         # Face/Edge Selection (TNP Fallback)
│   └── tnp_shape_reference.py        # TNP v3.0: Persistent Shape IDs
│
├── gui/
│   ├── main_window.py                # Zentrale App-Logik
│   ├── viewport_pyvista.py           # 3D-Viewport (Mixin-basiert)
│   ├── browser.py                    # Feature-Tree
│   ├── sketch_editor.py              # 2D-Sketcher
│   ├── tool_panel_3d.py              # 3D-Tools (Extrude, Fillet, etc.)
│   │
│   └── viewport/
│       ├── body_mixin.py             # Body-Rendering
│       ├── picking_mixin.py          # Raycasting & Selection
│       ├── transform_mixin_v3.py     # Transform-Gizmo (REFERENZ-UX)
│       ├── extrude_mixin.py          # Extrude-Preview
│       └── edge_selection_mixin.py   # Kanten-Selektion
│
├── sketcher/
│   ├── __init__.py                   # Sketch-Klasse
│   ├── geometry.py                   # 2D-Primitive
│   ├── constraints.py                # Constraint-Definitionen
│   └── solver.py                     # Lagrange-Multiplier Solver
│
└── i18n/                             # Internationalisierung (DE/EN)
```

---

## Performance-Architektur

### Tessellator-Caching

```python
# cad_tessellator.py

class CADTessellator:
    _mesh_cache = {}  # Geometry-Hash → (mesh, edges)

    def tessellate(solid):
        # Cache-Key basiert auf GEOMETRIE, nicht Python-ID
        # → Änderungen am Solid = neuer Hash = Cache-Miss
        shape_hash = hash((n_faces, n_edges, n_vertices, volume, center_of_mass))
        cache_key = f"{shape_hash}_{quality}"

        if cache_key in _mesh_cache:
            return _mesh_cache[cache_key]  # HIT

        # MISS: Tesselliere und cache
        mesh = ocp_tessellate(solid.wrapped, ...)
        _mesh_cache[cache_key] = mesh
        return mesh
```

**Wichtig:** Geometry-basierter Hash statt Python `id()` verhindert Cache-Kollisionen.

### Lazy Mesh-Regeneration

Meshes werden **nur** generiert wenn sie gebraucht werden (beim Rendern).

```python
# RICHTIG: Lazy
body._build123d_solid = new_solid
body.invalidate_mesh()
# → Mesh wird erst bei nächstem Viewport-Render generiert

# FALSCH: Eager (verschwendet Performance)
body._build123d_solid = new_solid
body._regenerate_mesh()  # ← Nicht direkt aufrufen!
```

### Performance-Kritische Pfade

| Pfad | Regel |
|------|-------|
| Mouse-Move Events | Kein Tessellieren, kein Logging |
| Viewport Render | Nur bei Änderungen, cached meshes |
| Boolean Operations | Parallel via `SetRunParallel(True)` |
| Cache-Invalidierung | Per-Shape statt global wenn möglich |

---

## UX-Standards

### Referenz: Transform-System V3

Alle interaktiven Features sollten diesem Standard folgen:

1. **Direkte Manipulation** - Gizmo im Viewport
2. **Live-Preview** - VTK UserTransform (kein Kernel-Update während Drag)
3. **Numerische Eingabe** - Panel für präzise Werte
4. **Commit on Release** - Kernel-Update erst bei Maus-Release

```
User Drag Gizmo
    ↓
Live VTK Transform (SCHNELL, kein Kernel)
    ↓
User Release
    ↓
Kernel Update + invalidate_mesh()
    ↓
Viewport Refresh
```

### Error-Feedback

Fehler müssen **sofort** und **klar** kommuniziert werden:

```python
# RICHTIG: Klare Fehlermeldung
if result.is_error:
    show_notification(
        "Boolean Cut fehlgeschlagen",
        detail="Geometrien überschneiden sich nicht",
        type="error"
    )

# FALSCH: Stille Fehler
if result.is_error:
    logger.warning("Something went wrong")  # User sieht das nicht!
```

---

## Code-Patterns

### Pattern 1: Kernel-Operation mit Transaction

```python
def apply_fillet(body, edge_indices, radius):
    with BodyTransaction(body, "Fillet") as txn:
        # 1. Kernel-Operation
        new_solid = body._build123d_solid.fillet(edges, radius)

        # 2. Validierung
        if new_solid is None or new_solid.is_null():
            raise BooleanOperationError("Fillet fehlgeschlagen")

        # 3. Update
        body._build123d_solid = new_solid
        body.invalidate_mesh()

        # 4. Commit
        txn.commit()

    return OperationResult.success(new_solid)
```

### Pattern 2: Viewport Body-Update

```python
def update_body_in_viewport(viewport, body):
    # Mesh wird lazy generiert beim ersten Zugriff
    mesh = body.vtk_mesh  # ← Lazy, cached
    edges = body.vtk_edges

    if mesh is None:
        return

    viewport.plotter.add_mesh(mesh, name=f"body_{body.id}")
    viewport.plotter.add_mesh(edges, name=f"edges_{body.id}")
```

### Pattern 3: Result-Handling

```python
result = BooleanEngineV4.execute_boolean(body, tool, "Cut")

match result.status:
    case ResultStatus.SUCCESS:
        update_viewport(body)
        show_success("Cut erfolgreich")

    case ResultStatus.EMPTY:
        show_info("Keine Überschneidung gefunden")

    case ResultStatus.ERROR:
        show_error(result.message)
        # Body ist automatisch zurückgerollt!
```

---

## Verbotene Patterns

### 1. Mesh-Fallbacks

```python
# VERBOTEN
def boolean_cut(body, tool):
    try:
        return kernel_boolean(body, tool)
    except:
        return mesh_boolean(body, tool)  # ← NEIN!
```

### 2. Direkte Mesh-Zuweisung

```python
# VERBOTEN
body.vtk_mesh = some_mesh  # ← vtk_mesh ist @property!

# RICHTIG
body._build123d_solid = new_solid
body.invalidate_mesh()
```

### 3. Cache-Invalidierung vergessen

```python
# VERBOTEN
body._build123d_solid = new_solid
# mesh ist jetzt out-of-sync!

# RICHTIG
body._build123d_solid = new_solid
body.invalidate_mesh()
```

### 4. No Quick Fixes - Build Solid Software

**Regel:** Nie Thresholds senken, Toleranzen erhöhen oder Workarounds einbauen um Bugs zu verbergen. Immer die Ursache beheben.

```python
# VERBOTEN (Quick Fix)
if best_score > 0.3:  # Von 0.6 auf 0.3 gesenkt "damit es klappt"
    return best_edge

# RICHTIG (Proper Solution)
# Das Referenz-Tracking fixen damit Edges korrekt gefunden werden
if best_score > 0.6:  # Strikten Threshold beibehalten
    return best_edge
else:
    # Referenzen mittels History oder geometrischem Matching aktualisieren
    self._update_references_after_operation()
```

### 5. Silent Failures

```python
# VERBOTEN
try:
    do_operation()
except:
    pass  # ← User erfährt nichts!

# RICHTIG
try:
    do_operation()
except Exception as e:
    return OperationResult.error(f"Operation fehlgeschlagen: {e}")
```

---

## Keyboard-Shortcuts

| Taste | Funktion |
|-------|----------|
| `G` | Move-Gizmo |
| `R` | Rotate-Gizmo |
| `S` | Scale-Gizmo |
| `M` | Mirror-Dialog |
| `Esc` | Abbrechen / Deselektieren |
| `Delete` | Löschen |
| `H` | Verstecken/Zeigen |

---

## Entwicklung

### Starten

conda run -n cad_env python -c "

### Debug-Logging

```python
from loguru import logger

logger.debug("...")      # Entwickler-Details
logger.info("...")       # Normale Info
logger.success("...")    # Erfolg (grün)
logger.warning("...")    # Warnung
logger.error("...")      # Fehler
```

---

## MANDATORY: Test-Verifikungs-Regeln ⚠️

**KRITISCH:** Diese Regeln MÜSSEN befolgt werden. Keine Ausnahmen.

### Regel 1: Tests IMMER ausführen und verifizieren

```bash
# VOR Code-Änderung oder "Erfolg"-Meldung:
conda run -n cad_env python -m pytest test/<meine_tests>.py -v --tb=short

# Nur wenn GRÜN zurückkommt, darf "erfolgreich" gemeldet werden
# ROT = Problem, nicht ignorieren!
```

**VERBOTEN:**
- Behaupten "alle Tests bestanden" ohne sie auszuführen
- Test-Ergebnisse ignorieren oder "überspringen"
- Fehlgeschlagene Tests als "kleiniges Problem" abtun

### Regel 2: API-Verwendung PRÜFEN bevor Code geschrieben wird

```python
# VOR Verwendung einer Klasse/API:
# 1. Source lesen (Grep/Read)
# 2. Aktuelle Signatur verstehen
# 3. Beispiel-Code in existierenden Tests finden

# BEISPIEL - FALSCH:
body = Body(name="test", solid=box)  # ← alte API, funktioniert nicht mehr!

# BEISPIEL - RICHTIG:
# Zuerst prüfen:
grep -n "def __init__" modeling/body.py
# Ergebnis: def __init__(self, name: str = "Body", document=None)

# Dann richtig verwenden:
body = Body(name="test")
# Solid später via Features hinzufügen
```

### Regel 3: Keine Platzhalter - NUR echte Implementierung

```python
# VERBOTEN:
def test_selection_performance():
    for i in range(100):
        pass  # ← NICHT ERLAUBT!

# ERLAUBT:
def test_selection_performance():
    times = []
    for i in range(100):
        start = time.perf_counter()
        result = perform_selection()  # Echte Messung
        times.append((time.perf_counter() - start) * 1000)
    assert max(times) < 10  # Echtes Kriterium
```

### Regel 4: Ehrliche Status-Berichterstattung

```python
# FALSCH:
print("✅ Alle Tests erfolgreich")  # Aber 10 Tests sind rot!

# RICHTIG:
if test_results.failed > 0:
    print(f"⚠️ {test_results.failed} Tests fehlgeschlagen:")
    for test in test_results.failed:
        print(f"  - {test.name}: {test.error}")
```

### Regel 5: Anti-Pattern "Scheinerfolg" erkennen und vermeiden

Das passiert NICHT mehr:

1. Tests schreiben → Tests ausführen → **Tests rot** → Trotzdem "Erfolg" melden ❌
2. `pass` als Platzhalter verwenden und behaupten "ist implementiert" ❌
3. Veraltete API verwenden und ignorieren dass es crasht ❌
4. Von Regression-Schutz schreiben ohne Tests zu validieren ❌

**WICHTIG:** Ein Test der rot ist, ist EIN FEHLER. Kein "eigentlich funktioniert es". Fixen oder ehrlich melden.

---

## Pre-Commit Checklist

- [ ] **Tests AUSFÜHREN** (`conda run -n cad_env python -m pytest ...`) - Nur bei GRÜN weitermachen
- [ ] **API prüfen** (aktuelle Signatur mit Grep/Read ermitteln)
- [ ] **Keine `pass` Platzhalter** (nur echte Implementierungen)
- [ ] Kernel-Operationen in Transaction gewrapped
- [ ] `invalidate_mesh()` nach Kernel-Änderungen
- [ ] Result-Types für alle Operationen
- [ ] Keine Silent Failures
- [ ] Keine Mesh-Fallbacks
- [ ] Performance: Kein Tessellieren in Event-Loops

---

## Versions-Historie

| Version | Datum | Änderungen |
|---------|-------|------------|
| V15 | Feb 2026 | Test-Verifikungs-Regeln hinzugefügt (nach "Scheinerfolg"-Incident) |
| V14 | Feb 2026 | Sketcher-Reliability, TNP v5, Plane-Serialisierung, DOF-Analyse |
| V13 | Jan 2026 | Phase 2+3 implementiert, neue CLAUDE.md |
| V12 | Jan 2026 | Transform V3, Cache-Counter |
| V11 | Dez 2025 | Sketch-Solver verbessert |
| V10 | Nov 2025 | PyVista-Integration |

---

## Performance-Optimierung (TODO)

Bekannte Bottlenecks für zukünftige Optimierung:

1. **Tessellation bei jedem Render** - LOD-System einführen
2. **Globale Cache-Invalidierung** - Per-Body Invalidierung
3. **Sketch-Renderer** - Batch-Rendering statt einzelne Elemente
4. **Event-Handling** - Debouncing für Mouse-Move
5. **VTK Actor-Management** - Pooling statt neu erstellen
