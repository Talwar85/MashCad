# MashCAD Projekt-Planung

Dieses Dokument enthält die aktuellen und geplanten Architektur-Änderungen für MashCAD.

---

# OCP-First Migration Plan

> **Status:** Phase 1-5 Completed ✅ | Tests: 49/49 Passing ✅
> **Startdatum:** 10.02.2026
> **Ziel:** Vollständige Migration von Build123d zu direktem OCP (OpenCASCADE)
> **Aktualisiert:** 10.02.2026 (Phase 5 abgeschlossen - Shell/Hollow)
> **Aktiver Git Branch:** `feature/ocp-first-migration`

---

## Übersicht & Motivation

**Warum OCP-First?**
- ✅ Bessere Performance durch direkten OCP-Zugriff
- ✅ Mehr Kontrolle über BREP-Operationen
- ✅ TNP (Topology Naming Protocol) Integration auf Low-Level
- ✅ Build123d-Wrapper entfernt → weniger Overhead
- ✅ Zukunftssicher für fortgeschrittene Features (Boolean V4, BREP Caching)

**Migration-Strategie:**
- Phase-basierte Migration mit Feature Flags
- Keine Breaking Changes während Migration
- TNP Integration ist OBLIGATORISCH in allen Phasen
- Feature Flags nur für Test/Validierung → nach Validierung entfernen

---

## Phasen-Übersicht

| Phase | Name | Status | Tests | Git Branch/Commit |
|-------|------|--------|-------|-------------------|
| 1 | Foundation | ✅ 100% | 21/21 ✅ | `feature/ocp-first-migration` (cd340e3) |
| 2 | ExtrudeFeature Integration | ✅ 100% | 10/10 ✅ | `feature/ocp-first-migration` |
| 3 | Fillet/Chamfer Integration | ✅ 100% | 7/7 ✅ | `feature/ocp-first-migration` |
| 4 | Revolve/Loft/Sweep Integration | ✅ 100% | 17/17 ✅ | `feature/ocp-first-migration` |
| 5 | Shell/Hollow Integration | ✅ 100% | 15/15 ✅ | `feature/ocp-first-migration` |
| 6 | Boolean V4 (Done) | ✅ 100% | - | Separate Implementation |
| 7 | BREP Caching | ❌ 0% | TBD | TBD |
| 8 | Incremental Rebuild + Dependency Graph | ⚠️ Partial | TBD | Existing code |
| 9 | Native BREP Persistenz | ❌ 0% | TBD | TBD |

**Gesamtaufwand:** ~27 Stunden (Phase 5-9 verbleibend)

---

## Phase 1: Foundation ✅ COMPLETED

### Implementiert (Commit: cd340e3)

**Erstellte Dateien:**
1. ✅ `config/feature_flags.py` (erweitert)
   - 11 neue OCP-First Feature Flags
   - Alle Flags default=False (alter Build123d Code aktiv)
   - Flags: `ocp_first_extrude`, `ocp_first_fillet`, `ocp_first_chamfer`, `ocp_first_draft`, `ocp_first_revolve`, `ocp_first_loft`, `ocp_first_sweep`, `ocp_first_shell`, `ocp_first_hollow`, `ocp_first_performance`, `ocp_first_debug`

2. ✅ `modeling/ocp_helpers.py` (neu)
   - `OCPExtrudeHelper`: Direktes OCP Prism mit TNP Integration
   - `OCPFilletHelper`: Direktes OCP Fillet mit TNP Integration
   - `OCPChamferHelper`: Direktes OCP Chamfer mit TNP Integration
   - `OCPRevolveHelper`: Direktes OCP Revolve mit TNP Integration
   - **VERBINDLICHE TNP Integration** - naming_service und feature_id sind Pflicht-Parameter!
   - Kein Fallback zu Build123d - entweder OCP oder ValueError

3. ✅ `test/ocp_test_utils.py` (neu)
   - `OCPTestContext`: Vollständiger Test-Kontext mit TNP Service
   - Hilfsfunktionen: `create_test_box`, `create_test_cylinder`, `create_test_sketch_face`
   - Assertion-Funktionen: `assert_solid_valid`, `assert_tnp_registered`
   - Pytest Fixtures: `ocp_test_context`, `tnp_mock_service`

4. ✅ `test/test_ocp_helpers_tnp.py` (neu)
   - Umfassende Unit Tests für alle OCP Helpers
   - Tests für TNP Registration (verbindlich!)
   - Error-Case Tests (ohne naming_service/feature_id)
   - Integration Tests (Extrude → Fillet → Chamfer Workflows)
   - Conditional Skip wenn OCP nicht verfügbar

5. ✅ `test/test_feature_flags.py` (neu)
   - Tests für alle 11 OCP-First Flags
   - Tests für Performance, Boolean Robustness, Debug Flags
   - Laufzeit-Modifikations-Tests

---

## Phase 2: ExtrudeFeature Integration ⏳ PENDING

### Ziel
Das `ocp_first_extrude` Flag in `modeling/__init__.py` aktivieren und `OCPExtrudeHelper` integrieren.

### Detaillierter Implementierungsplan

#### Schritt 1: Import hinzufügen
**Datei:** `modeling/__init__.py`
**Position:** Top-level Imports (nach Build123d Imports)

```python
# Neue OCP-First Imports
from modeling.ocp_helpers import (
    OCPExtrudeHelper,
    OCPFilletHelper,
    OCPChamferHelper,
    OCPRevolveHelper
)
from config.feature_flags import is_enabled
```

#### Schritt 2: _compute_extrude_part() refactoren
**Datei:** `modeling/__init__.py`
**Methode:** `_compute_extrude_part()` (ungefähr Zeile 2500-2600)

**Vorher (Legacy Code):**
```python
def _compute_extrude_part(self, feature: 'ExtrudeFeature', current_solid) -> Solid:
    # Legacy Build123d Extrude
    extruded = extrude(feature.profile_face, amount=feature.extrude_depth)
    return extruded
```

**Nachher (mit Feature Flag):**
```python
def _compute_extrude_part(self, feature: 'ExtrudeFeature', current_solid) -> Solid:
    """
    ExtrudeFeature Berechnung mit OCP-First oder Legacy Pfad.
    
    Args:
        feature: ExtrudeFeature mit profile_face und extrude_depth
        current_solid: Aktueller Solid (für konsistente API)
    
    Returns:
        Solid: Extrudierter Körper
    
    Raises:
        ValueError: Wenn OCP-First aktiv aber TNP Service nicht verfügbar
        RuntimeError: Wenn Extrude fehlschlägt
    """
    if is_enabled("ocp_first_extrude"):
        # OCP-First Pfad mit TNP Integration
        try:
            if self._tnp_service is None:
                raise ValueError(
                    "TNP Service nicht verfügbar für OCP-First Extrude. "
                    "Bitte TNP initialisieren oder Feature Flag deaktivieren."
                )
            
            helper = OCPExtrudeHelper(
                naming_service=self._tnp_service,
                feature_id=feature.id
            )
            
            result = helper.extrude(
                face_or_wire=feature.profile_face,
                distance=feature.extrude_depth
            )
            
            # TNP Registration prüfen (wenn debug aktiv)
            if is_enabled("ocp_first_debug"):
                logger.debug(
                    f"OCP-First Extrude: Feature {feature.id} → "
                    f"{len(result.faces)} Faces erstellt"
                )
            
            return result
            
        except Exception as e:
            # OCP-Fehler: Loggen und Fallback prüfen
            logger.error(f"OCP-First Extrude fehlgeschlagen: {e}")
            
            if is_enabled("ocp_first_debug"):
                # Im Debug-Modus Exception propagieren
                raise RuntimeError(f"OCP-First Extrude Fehler: {e}") from e
            
            # Im Produktionsmodus: Fallback zu Legacy mit Warnung
            logger.warning("Falle zurück auf Legacy Build123d Extrude")
            return self._compute_extrude_part_legacy(feature, current_solid)
    else:
        # Legacy Build123d Pfad
        return self._compute_extrude_part_legacy(feature, current_solid)

def _compute_extrude_part_legacy(self, feature: 'ExtrudeFeature', current_solid) -> Solid:
    """Legacy Build123d Extrude (bestehender Code)."""
    from build123d import extrude
    
    try:
        result = extrude(feature.profile_face, amount=feature.extrude_depth)
        return result
    except Exception as e:
        raise RuntimeError(f"Legacy Extrude fehlgeschlagen: {e}") from e
```

#### Schritt 3: Feature-ID Validierung
**Problem:** ExtrudeFeature könnte keine ID haben.

**Lösung:** In ExtrudeFeature.__init__() sicherstellen:
```python
# Falls ExtrudeFeature keine ID hat, generieren
if not hasattr(feature, 'id') or feature.id is None:
    import uuid
    feature.id = str(uuid.uuid4())
    logger.debug(f"Generated ID for ExtrudeFeature: {feature.id}")
```

#### Schritt 4: TNP Service Verfügbarkeit prüfen
**Problem:** `_tnp_service` könnte None sein.

**Lösung:** In Body.__init__() oder Document.__init__():
```python
if self._tnp_service is None:
    logger.warning("TNP Service nicht initialisiert - OCP-First Features deaktiviert")
```

### Testplan Phase 2

#### Test 1: OCP-First Extrude Unit Test
**Datei:** `test/test_phase2_extrude_integration.py` (neu)

```python
import pytest
from modeling.ocp_helpers import OCPExtrudeHelper
from test.ocp_test_utils import OCPTestContext, create_test_box

def test_ocp_first_extrude_with_tnp(ocp_test_context):
    """Test OCP-First Extrude mit aktiven TNP."""
    # Setup
    body = create_test_box(ocp_test_context.document)
    face = body.faces().front()
    
    feature = ExtrudeFeature(
        profile_face=face,
        extrude_depth=10.0
    )
    
    # Execute
    helper = OCPExtrudeHelper(
        naming_service=ocp_test_context.tnp_service,
        feature_id=feature.id
    )
    result = helper.extrude(face_or_wire=face, distance=10.0)
    
    # Assertions
    assert result is not None
    assert len(result.faces()) >= 6  # Box hat mindestens 6 Faces
    
    # TNP Registration prüfen
    from test.ocp_test_utils import assert_tnp_registered
    assert_tnp_registered(ocp_test_context.tnp_service, feature.id)
```

#### Test 2: Legacy Extrude Unit Test
**Datei:** `test/test_phase2_extrude_integration.py`

```python
def test_legacy_extrude_without_flag(ocp_test_context):
    """Test Legacy Extrude ohne OCP-First Flag."""
    from config.feature_flags import set_flag
    
    # Flag deaktivieren
    set_flag("ocp_first_extrude", False)
    
    body = create_test_box(ocp_test_context.document)
    face = body.faces().front()
    
    feature = ExtrudeFeature(
        profile_face=face,
        extrude_depth=10.0
    )
    
    # Execute über Body._compute_extrude_part
    result = body._compute_extrude_part(feature, body._build123d_solid)
    
    # Assertions
    assert result is not None
    assert len(result.faces()) >= 6
```

#### Test 3: OCP-First ohne TNP Service
**Datei:** `test/test_phase2_extrude_integration.py`

```python
def test_ocp_first_extrude_without_tnp_fails():
    """Test dass OCP-First ohne TNP Service fehlschlägt."""
    from config.feature_flags import set_flag
    
    set_flag("ocp_first_extrude", True)
    
    # Body ohne TNP Service
    body = Body()
    body._tnp_service = None  # Explizit None
    
    face = create_test_box(document).faces().front()
    feature = ExtrudeFeature(profile_face=face, extrude_depth=10.0)
    
    # Sollte ValueError werfen
    with pytest.raises(ValueError, match="TNP Service nicht verfügbar"):
        body._compute_extrude_part(feature, body._build123d_solid)
```

#### Test 4: Integration Test - Full Workflow
**Datei:** `test/test_phase2_extrude_integration.py`

```python
def test_full_extrude_workflow_with_ocp_first():
    """Vollständiger Workflow: Sketch → Extrude mit OCP-First."""
    from config.feature_flags import set_flag
    from document import Document
    
    # Flag aktivieren
    set_flag("ocp_first_extrude", True)
    
    # 1. Dokument erstellen
    doc = Document()
    
    # 2. Sketch erstellen
    sketch = Sketch("TestSketch")
    sketch.add_rectangle((0, 0), (10, 10))
    doc.add_sketch(sketch)
    
    # 3. Extrude Feature
    extrude_feat = ExtrudeFeature(
        sketch_id=sketch.id,
        extrude_depth=5.0
    )
    
    # 4. Body erstellen und Feature hinzufügen
    body = Body("TestBody")
    body.add_feature(extrude_feat)
    
    # 5. Execute
    body._rebuild()
    
    # Assertions
    assert body._build123d_solid is not None
    assert body.volume > 0  # Sollte Volumen haben
```

### Fehlerbehandlung Phase 2

#### Fehler 1: OCP-First Extrude fehlschlägt
**Symptom:** `RuntimeError: OCP-First Extrude fehlgeschlagen`

**Diagnose:**
```python
# Log Datei prüfen
logger.info("Checking OCP Extrude logs...")
# Suche nach: "OCP-First Extrude fehlgeschlagen"
```

**Lösung:**
1. OCP Installation prüfen: `python -c "import OCP; print(OCP.__version__)"`
2. TNP Service initialisiert? `body._tnp_service is not None`
3. Feature-ID vorhanden? `feature.id is not None`
4. Profile Face gültig? `feature.profile_face is not None`

#### Fehler 2: TNP Registration fehlt
**Symptom:** TNP Assertions schlagen fehl

**Diagnose:**
```python
# TNP Service prüfen
tnp_service.get_registered_shapes(feature_id)
# Sollte nicht leer sein
```

**Lösung:**
1. TNP Service korrekt initialisieren
2. Feature-ID vor Extrude generieren
3. Naming Service an OCPExtrudeHelper übergeben

#### Fehler 3: Fallback zu Legacy unerwartet
**Symptom:** Legacy Code wird ausgeführt obwohl Flag=True

**Diagnose:**
```python
# Flag Status prüfen
from config.feature_flags import is_enabled
print(f"ocp_first_extrude: {is_enabled('ocp_first_extrude')}")
```

**Lösung:**
1. Flag korrekt setzen: `set_flag("ocp_first_extrude", True)`
2. Flag in config/feature_flags.py vorhanden
3. Keine Exception im OCP Pfad (sonst Fallback)

### Validierung Phase 2

#### Validierungs-Checklist vor Merge:
- [ ] Unit Tests laufen: `pytest test/test_phase2_extrude_integration.py -v`
- [ ] Legacy Tests nicht gebrochen: `pytest test/test_*extrude* -v`
- [ ] OCP-First Pfad mit Flag=True funktioniert
- [ ] Legacy Pfad mit Flag=False funktioniert
- [ ] TNP Registration erfolgreich
- [ ] Fallback bei Fehlern funktioniert
- [ ] Performance nicht schlechter als Legacy
- [ ] Code Review durch peer

---

## Phase 2: ExtrudeFeature Integration ✅ COMPLETED

### Implementiert

**Datei:** `modeling/__init__.py` (Zeile 7401-7584)
- `_compute_extrude_part()` mit Feature-Flag-Steuerung
- `_compute_extrude_part_ocp_first()` - OCPExtrudeHelper Integration
- `_compute_extrude_part_legacy()` - Build123d Fallback

**Feature Flag:** `ocp_first_extrude = True`

**Tests:** `test/test_phase2_extrude_integration.py` - 10/10 bestanden ✅

---

## Phase 3: Fillet/Chamfer Integration ✅ COMPLETED

### Implementiert

**Datei:** `modeling/__init__.py` (Zeile 6023-6120)
- OCPFilletHelper Integration mit Feature-Flag-Steuerung
- OCPChamferHelper Integration mit Feature-Flag-Steuerung
- TNP Edge-Resolution vor Fillet/Chamfer

**Feature Flags:** `ocp_first_fillet = True`, `ocp_first_chamfer = True`

**Tests:** `test/test_phase3_fillet_chamfer_integration.py` - 7/7 bestanden ✅

---

## Phase 4: Revolve/Loft/Sweep Integration ✅ COMPLETED

### Implementiert

**Datei:** `modeling/ocp_helpers.py`

**Neue Helper-Klassen:**
1. `OCPLoftHelper` - Loft zwischen 2+ Profilen mit TNP
   - `BRepOffsetAPI_ThruSections(isSolid=True, ruled=ruled)`
   - Face→Wire Konvertierung via TopExp_Explorer
   - TNP Registration aller Faces/Edges

2. `OCPSweepHelper` - Sweep Profil entlang Pfad mit TNP
   - `BRepOffsetAPI_MakePipe(path_wire, profile_shape)`
   - Face→Wire Konvertierung
   - TNP Registration aller Faces/Edges

**Feature Flags:** `ocp_first_revolve = True`, `ocp_first_loft = True`, `ocp_first_sweep = True`

**Tests:** `test/test_phase4_revolve_loft_sweep.py` - 17/17 bestanden ✅

**Test-Abdeckung:**
- OCPRevolveHelper: 180°, 360° Revolve
- OCPLoftHelper: 2-Faces Loft, Ruled Surface
- OCPSweepHelper: Linear Path Sweep
- TNP Registration Tests für alle Helper
- Feature Flag Validation Tests

---

## Phase 5: Shell/Hollow Integration ✅ COMPLETED

### Implementiert (10.02.2026)

**Erstellte/Geänderte Dateien:**

1. ✅ `modeling/ocp_helpers.py` (erweitert)
   - `OCPShellHelper`: Direktes OCP Shell mit `BRepOffsetAPI_MakeThickSolid`
     - Entfernt bestimmte Faces und erstellt Wandstärke
     - TNP Integration für alle resultierenden Faces und Edges
     - Verwendet `TopTools_ListOfShape` für ClosingFaces
     - `GeomAbs_JoinType.GeomAbs_Arc` für glatte Kantenverbindungen

   - `OCPHollowHelper`: Direktes OCP Hollow
     - Erstellt innere Cavität mit uniformer Wandstärke
     - Verwendet **leere** ClosingFaces-Liste (keine Faces entfernen)
     - Negative thickness = Material nach innen entfernen
     - TNP Integration für alle resultierenden Shapes

2. ✅ `config/feature_flags.py` (bereits aktiviert)
   ```python
   "ocp_first_shell": True,   # ShellFeature nutzt direktes OCP
   "ocp_first_hollow": True,  # HollowFeature nutzt direktes OCP
   ```

3. ✅ `test/test_phase5_shell_hollow.py` (neu)
   - 15 comprehensive Tests für Shell und Hollow
   - Tests für: ein Face, mehrere Faces, ohne TNP, ohne feature_id, leere Face-Liste
   - TNP Registration Tests
   - Feature Flag Validation Tests
   - Volumen-Validierung Tests (vernünftige Reduktion)

**API-Signatur (OCP MakeThickSolidByJoin):**
```python
MakeThickSolidByJoin(
    S: TopoDS_Shape,           # Source Solid
    ClosingFaces: TopTools_ListOfShape,  # Zu entfernende Faces (leer für Hollow)
    Offset: float,             # Wandstärke (negativ = nach innen)
    Tol: float,                # Tolerance
    Mode: BRepOffset_Mode,     # BRepOffset_Skin
    Intersection: bool,        # False
    SelfInter: bool,           # False
    Join: GeomAbs_JoinType,    # GeomAbs_Arc
    RemoveIntEdges: bool       # False
)
```

**Testergebnis:** 15/15 bestanden ✅

**Schlüsselerkenntnisse:**
- Shell mit ClosingFaces erstellt offene Wände
- Hollow mit leerer ClosingFaces-Liste erstellt geschlossenen Hohlkörper
- `TopTools_ListOfShape` ist Pflicht (Python-Liste funktioniert nicht)
- `GeomAbs_JoinType` statt bool für Join-Parameter
            )
            
            from build123d import Solid
            return Solid(self._fix_shape_ocp(result))
            
        except Exception as e:
            logger.error(f"OCP-First Chamfer fehlgeschlagen: {e}")
            
            if is_enabled("ocp_first_debug"):
                raise RuntimeError(f"OCP-First Chamfer Fehler: {e}") from e
            
            logger.warning("Falle zurück auf Legacy Build123d Chamfer")
            return self._compute_chamfer_part_legacy(feature, current_solid)
    else:
        return self._compute_chamfer_part_legacy(feature, current_solid)

def _compute_chamfer_part_legacy(self, feature: 'ChamferFeature', current_solid) -> Solid:
    """Legacy Build123d Chamfer."""
    from build123d import chamfer
    
    try:
        result = chamfer(feature.edges, feature.distance)
        return result
    except Exception as e:
        raise RuntimeError(f"Legacy Chamfer fehlgeschlagen: {e}") from e
```

### Testplan Phase 3

#### Test 1: OCP-First Fillet Unit Test
**Datei:** `test/test_phase3_fillet_chamfer_integration.py` (neu)

```python
def test_ocp_first_fillet_with_tnp(ocp_test_context):
    """Test OCP-First Fillet mit aktiven TNP."""
    body = create_test_box(ocp_test_context.document)
    edges = [body.edges().front_edge()]
    
    feature = FilletFeature(
        edges=edges,
        radius=2.0
    )
    
    helper = OCPFilletHelper(
        naming_service=ocp_test_context.tnp_service,
        feature_id=feature.id
    )
    result = helper.fillet(
        shape=body.wrapped,
        edges=[e.wrapped for e in edges],
        radius=2.0
    )
    
    assert result is not None
    assert_tnp_registered(ocp_test_context.tnp_service, feature.id)
```

#### Test 2: Chamfer Integration Test
**Datei:** `test/test_phase3_fillet_chamfer_integration.py`

```python
def test_full_fillet_chamfer_workflow():
    """Workflow: Extrude → Fillet → Chamfer."""
    from config.feature_flags import set_flag
    
    set_flag("ocp_first_extrude", True)
    set_flag("ocp_first_fillet", True)
    set_flag("ocp_first_chamfer", True)
    
    doc = Document()
    
    # Extrude
    sketch = Sketch("Box")
    sketch.add_rectangle((0, 0), (10, 10))
    doc.add_sketch(sketch)
    
    body = Body("Box")
    extrude = ExtrudeFeature(sketch_id=sketch.id, extrude_depth=10.0)
    body.add_feature(extrude)
    
    # Fillet
    edges = [body.edges().front_edge()]
    fillet = FilletFeature(edges=edges, radius=1.0)
    body.add_feature(fillet)
    
    # Chamfer
    chamfer_edges = [body.edges().top_edge()]
    chamfer = ChamferFeature(edges=chamfer_edges, distance=0.5)
    body.add_feature(chamfer)
    
    body._rebuild()
    
    assert body._build123d_solid is not None
    assert body.volume > 0
```

### Fehlerbehandlung Phase 3

#### Fehler 1: Fillet Radius zu groß
**Symptom:** Fillet erzeugt invalid geometry

**Diagnose:**
```python
# Radius prüfen
if feature.radius > min_edge_length / 2:
    logger.warning(f"Fillet radius {feature.radius} zu groß für Edge {edge}")
```

**Lösung:**
1. Radius validieren vor Fillet
2. Max Radius = min(edge_length / 2)
3. Auto-Reduzierung oder Fehler werfen

#### Fehler 2: Edges nicht adjazent
**Symptom:** Fillet auf nicht-verbundenen Edges

**Diagnose:**
```python
# Adjazenz prüfen
from modeling.brep_utils import edges_are_connected
if not edges_are_connected(feature.edges):
    raise ValueError("Fillet Edges müssen verbunden sein")
```

**Lösung:**
1. Adjazenz-Check vor Fillet
2. Nur verbundene Edges zulassen
3. Separate Fillet Features für nicht-verbundene Edges

### Validierung Phase 3

- [ ] Unit Tests für Fillet
- [ ] Unit Tests für Chamfer
- [ ] Integration Tests (Extrude → Fillet → Chamfer)
- [ ] Legacy Tests nicht gebrochen
- [ ] Performance Test (viele Fillets)
- [ ] Edge Cases: Radius 0, sehr groß, negativ

---

## Phase 4: Revolve/Loft/Sweep Integration ⏳ PENDING

### Ziel
Integration von `OCPRevolveHelper` und neue Helpers für Loft/Sweep.

### Detaillierter Implementierungsplan

#### Schritt 1: OCPRevolveHelper integrieren
**Datei:** `modeling/__init__.py`
**Methode:** `_compute_revolve_part()`

```python
def _compute_revolve_part(self, feature: 'RevolveFeature', current_solid) -> Solid:
    """
    RevolveFeature Berechnung mit OCP-First oder Legacy Pfad.
    """
    if is_enabled("ocp_first_revolve"):
        try:
            if self._tnp_service is None:
                raise ValueError("TNP Service nicht verfügbar für OCP-First Revolve")
            
            # Axis und Angle extrahieren
            axis = feature.axis  # gp_Ax1 oder tuple
            angle = feature.angle
            
            helper = OCPRevolveHelper(
                naming_service=self._tnp_service,
                feature_id=feature.id
            )
            
            result = helper.revolve(
                face_or_wire=feature.profile_face,
                axis=axis,
                angle=angle
            )
            
            return result
            
        except Exception as e:
            logger.error(f"OCP-First Revolve fehlgeschlagen: {e}")
            
            if is_enabled("ocp_first_debug"):
                raise RuntimeError(f"OCP-First Revolve Fehler: {e}") from e
            
            logger.warning("Falle zurück auf Legacy Build123d Revolve")
            return self._compute_revolve_part_legacy(feature, current_solid)
    else:
        return self._compute_revolve_part_legacy(feature, current_solid)
```

#### Schritt 2: Neue OCP Helpers für Loft/Sweep erstellen
**Datei:** `modeling/ocp_helpers.py` (erweitern)

```python
class OCPRevolveHelper:
    """Helper für Revolve-Operationen mit TNP Integration."""
    
    def __init__(self, naming_service: TNPService, feature_id: str):
        self.naming_service = naming_service
        self.feature_id = feature_id
    
    def revolve(self, face_or_wire, axis, angle: float = 360.0) -> Solid:
        """
        Face/Wire um Achse rotieren.
        
        Args:
            face_or_wire: Zu rotierendes Face oder Wire
            axis: Rotationsachse (gp_Ax1 oder tuple (origin, direction))
            angle: Rotationswinkel in Grad
        
        Returns:
            Solid: Rotierter Körper
        """
        from build123d import Solid
        from OCP.gp import gp_Ax1, gp_Dir, gp_Pnt
        
        # Axis konvertieren
        if isinstance(axis, tuple):
            origin, direction = axis
            ocp_axis = gp_Ax1(gp_Pnt(*origin), gp_Dir(*direction))
        else:
            ocp_axis = axis
        
        # Revolve ausführen
        from OCP.BRepPrimAPI import BRepPrimAPI_MakeRevol
        revolve_builder = BRepPrimAPI_MakeRevol(
            self._to_ocp_shape(face_or_wire),
            ocp_axis,
            math.radians(angle)
        )
        
        if not revolve_builder.IsDone():
            raise ValueError(f"Revolve fehlgeschlagen für Feature {self.feature_id}")
        
        result = Solid(self._fix_shape_ocp(revolve_builder.Shape()))
        
        # TNP Registration
        self.naming_service.register_feature_result(
            self.feature_id,
            result,
            operation_type="revolve"
        )
        
        return result


class OCPLoftHelper:
    """Helper für Loft-Operationen mit TNP Integration."""
    
    def __init__(self, naming_service: TNPService, feature_id: str):
        self.naming_service = naming_service
        self.feature_id = feature_id
    
    def loft(self, sections: List, ruled: bool = False) -> Solid:
        """
        Loft zwischen mehreren Profilen.
        
        Args:
            sections: Liste von Faces oder Wires
            ruled: ruled surface (True) oder smooth (False)
        
        Returns:
            Solid: Loft-Körper
        """
        from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeThickSolid, BRepBuilderAPI_MakeSolid
        from OCP.GeomAbs import GeomAbs_C0, GeomAbs_C1
        
        # Sections in OCP Shapes konvertieren
        ocp_sections = [self._to_ocp_shape(sec) for sec in sections]
        
        # Loft ausführen
        from OCP.BRepOffsetAPI import BRepOffsetAPI_ThruSections
        loft_builder = BRepOffsetAPI_ThruSections(Bool=ruled)
        
        for section in ocp_sections:
            loft_builder.AddWire(section)
        
        loft_builder.Build()
        
        if not loft_builder.IsDone():
            raise ValueError(f"Loft fehlgeschlagen für Feature {self.feature_id}")
        
        result = Solid(self._fix_shape_ocp(loft_builder.Shape()))
        
        # TNP Registration
        self.naming_service.register_feature_result(
            self.feature_id,
            result,
            operation_type="loft"
        )
        
        return result


class OCPSweepHelper:
    """Helper für Sweep-Operationen mit TNP Integration."""
    
    def __init__(self, naming_service: TNPService, feature_id: str):
        self.naming_service = naming_service
        self.feature_id = feature_id
    
    def sweep(self, profile, path) -> Solid:
        """
        Profile entlang Path sweepen.
        
        Args:
            profile: Zu sweependes Face oder Wire
            path: Pfad als Wire oder Edge
        
        Returns:
            Solid: Sweep-Körper
        """
        from OCP.BRepOffsetAPI import BRepOffsetAPI_MakePipe
        
        ocp_profile = self._to_ocp_shape(profile)
        ocp_path = self._to_ocp_shape(path)
        
        sweep_builder = BRepOffsetAPI_MakePipe(ocp_path, ocp_profile)
        sweep_builder.Build()
        
        if not sweep_builder.IsDone():
            raise ValueError(f"Sweep fehlgeschlagen für Feature {self.feature_id}")
        
        result = Solid(self._fix_shape_ocp(sweep_builder.Shape()))
        
        # TNP Registration
        self.naming_service.register_feature_result(
            self.feature_id,
            result,
            operation_type="sweep"
        )
        
        return result
```

### Testplan Phase 4

#### Test 1: Revolve Unit Test
**Datei:** `test/test_phase4_revolve_loft_sweep.py` (neu)

```python
def test_ocp_revolve_full_circle(ocp_test_context):
    """Test Revolve um 360 Grad."""
    from modeling.ocp_helpers import OCPRevolveHelper
    
    # Rectangle als Profil
    face = create_test_sketch_face([(0, 0), (10, 0), (10, 5), (0, 5)])
    
    # Axis: Y-Achse
    axis = ((0, 0, 0), (0, 1, 0))
    
    helper = OCPRevolveHelper(
        naming_service=ocp_test_context.tnp_service,
        feature_id="revolve_1"
    )
    
    result = helper.revolve(face_or_wire=face, axis=axis, angle=360.0)
    
    assert result is not None
    assert result.volume > 0
    assert_tnp_registered(ocp_test_context.tnp_service, "revolve_1")
```

#### Test 2: Loft Unit Test
**Datei:** `test/test_phase4_revolve_loft_sweep.py`

```python
def test_ocp_loft_between_circles(ocp_test_context):
    """Test Loft zwischen zwei Kreisen."""
    from modeling.ocp_helpers import OCPLoftHelper
    
    # Zwei Kreise als Sections
    circle1 = create_test_circle(center=(0, 0, 0), radius=5)
    circle2 = create_test_circle(center=(0, 0, 10), radius=3)
    
    helper = OCPLoftHelper(
        naming_service=ocp_test_context.tnp_service,
        feature_id="loft_1"
    )
    
    result = helper.loft(sections=[circle1, circle2], ruled=False)
    
    assert result is not None
    assert result.volume > 0
    assert_tnp_registered(ocp_test_context.tnp_service, "loft_1")
```

### Fehlerbehandlung Phase 4

#### Fehler 1: Revolve Axis durch Profil
**Symptom:** Self-intersection

**Diagnose:**
```python
# Axis-Abstand zum Profil prüfen
if axis_intersects_profile(profile, axis):
    raise ValueError("Revolve Axis darf Profil nicht schneiden")
```

**Lösung:**
1. Axis-Abstand validieren
2. Mindestabstand = 0.1 * Profilgröße
3. Fehler werfen oder Warnung mit Auto-Korrektur

#### Fehler 2: Loft Sections nicht parallel
**Symptom:** Loft erzeugt twisted geometry

**Diagnose:**
```python
# Section-Normalen prüfen
if not sections_are_parallel(loft_sections):
    logger.warning("Loft Sections nicht parallel - twisted Geometry möglich")
```

**Lösung:**
1. Parallelität-Check warnen
2. Guide Curves für komplexe Loft nutzen
3. Loft Parameter (tension, continuity) anpassen

### Validierung Phase 4

- [ ] Unit Tests für Revolve
- [ ] Unit Tests für Loft
- [ ] Unit Tests für Sweep
- [ ] Integration Tests (Extrude → Revolve → Loft)
- [ ] Edge Cases: Angle 0, 360+, negative
- [ ] Performance Test (viele Loft sections)

---

## Phase 5: Shell/Hollow Integration ⏳ PENDING

### Ziel
Neue Helpers für Shell und Hollow Operationen erstellen.

### Detaillierter Implementierungsplan

#### Schritt 1: OCPShellHelper erstellen
**Datei:** `modeling/ocp_helpers.py` (erweitern)

```python
class OCPShellHelper:
    """Helper für Shell-Operationen mit TNP Integration."""
    
    def __init__(self, naming_service: TNPService, feature_id: str):
        self.naming_service = naming_service
        self.feature_id = feature_id
    
    def shell(self, shape, faces_to_remove: List, thickness: float) -> Solid:
        """
        Hollow aus Shape mit Face-Removal.
        
        Args:
            shape: OCP Shape
            faces_to_remove: Liste von Faces die entfernt werden
            thickness: Wandstärke (positiv für Shell nach außen)
        
        Returns:
            Solid: Gehühlter Körper
        """
        from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeSolid
        from OCP.BRepOffsetAPI import BRepOffsetAPI_MakeThickSolid
        
        # Faces in OCP Format
        ocp_faces = [face.wrapped for face in faces_to_remove]
        
        # Shell ausführen
        shell_builder = BRepOffsetAPI_MakeThickSolid()
        
        try:
            shell_builder.MakeThickSolidByJoin(
                shape,
                ocp_faces,
                -thickness,  # Negativ = innen, Positiv = außen
                0.001,  # Tolerance
                BRepOffset_Skin,  # OffsetMode
                False,  # Intersection
                False,  # Self-Intersection
                True,  # Join
                1e-3   # Tolerance
            )
        except Exception as e:
            raise ValueError(f"Shell fehlgeschlagen: {e}")
        
        if not shell_builder.IsDone():
            raise ValueError(f"Shell Builder nicht fertig für Feature {self.feature_id}")
        
        result = Solid(self._fix_shape_ocp(shell_builder.Shape()))
        
        # TNP Registration
        self.naming_service.register_feature_result(
            self.feature_id,
            result,
            operation_type="shell"
        )
        
        return result


class OCPHollowHelper:
    """Helper für Hollow-Operationen mit TNP Integration."""
    
    def __init__(self, naming_service: TNPService, feature_id: str):
        self.naming_service = naming_service
        self.feature_id = feature_id
    
    def hollow(self, shape, thickness: float) -> Solid:
        """
        Hollow ohne Face-Removal (uniforme Wandstärke).
        
        Args:
            shape: OCP Shape
            thickness: Wandstärke
        
        Returns:
            Solid: Gehühlter Körper
        """
        from OCP.BRepOffsetAPI import BRepOffsetAPI_MakeThickSolid
        
        # Alle Faces entfernen = Hollow
        all_faces = list(Face Explorer auf shape)
        
        shell_builder = BRepOffsetAPI_MakeThickSolid()
        
        try:
            shell_builder.MakeThickSolidByJoin(
                shape,
                all_faces,
                -thickness,
                0.001,
                BRepOffset_Skin,
                False,
                False,
                True,
                1e-3
            )
        except Exception as e:
            raise ValueError(f"Hollow fehlgeschlagen: {e}")
        
        if not shell_builder.IsDone():
            raise ValueError(f"Hollow Builder nicht fertig für Feature {self.feature_id}")
        
        result = Solid(self._fix_shape_ocp(shell_builder.Shape()))
        
        # TNP Registration
        self.naming_service.register_feature_result(
            self.feature_id,
            result,
            operation_type="hollow"
        )
        
        return result
```

#### Schritt 2: _compute_shell_part() und _compute_hollow_part() refactoren
**Datei:** `modeling/__init__.py`

```python
def _compute_shell_part(self, feature: 'ShellFeature', current_solid) -> Solid:
    """ShellFeature Berechnung mit OCP-First oder Legacy."""
    if is_enabled("ocp_first_shell"):
        try:
            if self._tnp_service is None:
                raise ValueError("TNP Service nicht verfügbar für OCP-First Shell")
            
            helper = OCPShellHelper(
                naming_service=self._tnp_service,
                feature_id=feature.id
            )
            
            result = helper.shell(
                shape=current_solid.wrapped,
                faces_to_remove=feature.faces_to_remove,
                thickness=feature.wall_thickness
            )
            
            return result
            
        except Exception as e:
            logger.error(f"OCP-First Shell fehlgeschlagen: {e}")
            
            if is_enabled("ocp_first_debug"):
                raise RuntimeError(f"OCP-First Shell Fehler: {e}") from e
            
            return self._compute_shell_part_legacy(feature, current_solid)
    else:
        return self._compute_shell_part_legacy(feature, current_solid)


def _compute_hollow_part(self, feature: 'HollowFeature', current_solid) -> Solid:
    """HollowFeature Berechnung mit OCP-First oder Legacy."""
    if is_enabled("ocp_first_hollow"):
        try:
            if self._tnp_service is None:
                raise ValueError("TNP Service nicht verfügbar für OCP-First Hollow")
            
            helper = OCPHollowHelper(
                naming_service=self._tnp_service,
                feature_id=feature.id
            )
            
            result = helper.hollow(
                shape=current_solid.wrapped,
                thickness=feature.wall_thickness
            )
            
            return result
            
        except Exception as e:
            logger.error(f"OCP-First Hollow fehlgeschlagen: {e}")
            
            if is_enabled("ocp_first_debug"):
                raise RuntimeError(f"OCP-First Hollow Fehler: {e}") from e
            
            return self._compute_hollow_part_legacy(feature, current_solid)
    else:
        return self._compute_hollow_part_legacy(feature, current_solid)
```

### Testplan Phase 5

#### Test 1: Shell Unit Test
**Datei:** `test/test_phase5_shell_hollow.py` (neu)

```python
def test_ocp_shell_with_face_removal(ocp_test_context):
    """Test Shell mit Face-Removal."""
    from modeling.ocp_helpers import OCPShellHelper
    
    body = create_test_box(ocp_test_context.document)
    faces_to_remove = [body.faces().front()]
    
    helper = OCPShellHelper(
        naming_service=ocp_test_context.tnp_service,
        feature_id="shell_1"
    )
    
    result = helper.shell(
        shape=body.wrapped,
        faces_to_remove=faces_to_remove,
        thickness=1.0
    )
    
    assert result is not None
    assert result.volume < body.volume  # Shell hat weniger Volumen
    assert_tnp_registered(ocp_test_context.tnp_service, "shell_1")
```

#### Test 2: Hollow Integration Test
**Datei:** `test/test_phase5_shell_hollow.py`

```python
def test_full_hollow_workflow():
    """Workflow: Extrude → Hollow."""
    from config.feature_flags import set_flag
    
    set_flag("ocp_first_extrude", True)
    set_flag("ocp_first_hollow", True)
    
    doc = Document()
    
    # Extrude
    sketch = Sketch("Box")
    sketch.add_rectangle((0, 0), (10, 10))
    doc.add_sketch(sketch)
    
    body = Body("Box")
    extrude = ExtrudeFeature(sketch_id=sketch.id, extrude_depth=10.0)
    body.add_feature(extrude)
    
    # Hollow
    hollow = HollowFeature(wall_thickness=1.0)
    body.add_feature(hollow)
    
    body._rebuild()
    
    assert body._build123d_solid is not None
    assert body.volume > 0
    assert body.volume < 1000  # Sollte gehühlt sein
```

### Fehlerbehandlung Phase 5

#### Fehler 1: Shell thickness zu groß
**Symptom:** Shell erzeugt invalid geometry oder self-intersection

**Diagnose:**
```python
# Max thickness prüfen
max_thickness = min_edge_length / 2
if feature.wall_thickness > max_thickness:
    raise ValueError(f"Wall thickness {feature.wall_thickness} zu groß (max: {max_thickness})")
```

**Lösung:**
1. Thickness validieren vor Shell
2. Max Thickness berechnen basierend auf Geometrie
3. Auto-Reduzierung oder Fehler werfen

#### Fehler 2: Face removal führt zu offener Geometrie
**Symptom:** Shell result ist nicht closed

**Diagnose:**
```python
# Closure prüfen
from OCP.ShapeAnalysis import ShapeAnalysis_CheckSmall
checker = ShapeAnalysis_CheckSmall()
if not checker.IsClosed(result.wrapped):
    logger.warning("Shell result ist nicht geschlossen")
```

**Lösung:**
1. Closure-Check nach Shell
2. Faces neu prüfen und korrigieren
3. BRepTools::Clean() ausführen

### Validierung Phase 5

- [ ] Unit Tests für Shell
- [ ] Unit Tests für Hollow
- [ ] Integration Tests (Extrude → Shell → Hollow)
- [ ] Edge Cases: Thickness 0, sehr groß, negativ
- [ ] Face Removal Tests (1 Face, mehrere Faces, alle Faces)

---

## Phase 7: BREP Caching ⏳ PENDING

### Ziel
Caching-Schicht für häufig verwendete BREP-Operationen mit TNP-Awareness.

### Detaillierter Implementierungsplan

#### Schritt 1: BREP Cache Klasse erstellen
**Datei:** `modeling/brep_cache.py` (neu)

```python
import hashlib
import pickle
from typing import Optional, Dict, Any
from dataclasses import dataclass
from datetime import datetime, timedelta

@dataclass
class CacheEntry:
    """Cache Entry mit Metadaten."""
    result: Any  # BREP Result (Solid, Face, etc.)
    shape_id: str  # TNP ShapeID
    feature_id: str
    timestamp: datetime
    hit_count: int = 0

class BREPCache:
    """
    Caching-Schicht für BREP-Operationen.
    
    Strategie:
    - Key basierend auf Operation und Input ShapeIDs
    - TNP ShapeIDs für Consistency
    - LRU Eviction Policy
    - TTL (Time To Live) optional
    """
    
    def __init__(self, max_size: int = 100, ttl_seconds: Optional[int] = None):
        self.max_size = max_size
        self.ttl = timedelta(seconds=ttl_seconds) if ttl_seconds else None
        self._cache: Dict[str, CacheEntry] = {}
        self._access_order: List[str] = []  # Für LRU
    
    def _generate_cache_key(self, operation: str, input_shape_ids: List[str], **kwargs) -> str:
        """Generiert eindeutigen Cache Key."""
        # Key-Komponenten
        components = [operation] + input_shape_ids
        
        # Sortierte kwargs
        sorted_kwargs = sorted(kwargs.items())
        for key, value in sorted_kwargs:
            components.append(f"{key}={value}")
        
        # SHA256 Hash
        key_string = "|".join(str(c) for c in components)
        return hashlib.sha256(key_string.encode()).hexdigest()
    
    def get(self, operation: str, input_shape_ids: List[str], **kwargs) -> Optional[Any]:
        """
        Cached Result abrufen.
        
        Returns:
            Cached result oder None wenn nicht gefunden oder expired
        """
        key = self._generate_cache_key(operation, input_shape_ids, **kwargs)
        
        if key not in self._cache:
            return None
        
        entry = self._cache[key]
        
        # TTL Check
        if self.ttl and (datetime.now() - entry.timestamp) > self.ttl:
            del self._cache[key]
            return None
        
        # Hit Count erhöhen
        entry.hit_count += 1
        
        # LRU Update
        if key in self._access_order:
            self._access_order.remove(key)
        self._access_order.append(key)
        
        logger.debug(f"Cache HIT: {operation} (hits: {entry.hit_count})")
        return entry.result
    
    def put(self, operation: str, input_shape_ids: List[str], result: Any, 
            feature_id: str, **kwargs) -> None:
        """Result in Cache speichern."""
        key = self._generate_cache_key(operation, input_shape_ids, **kwargs)
        
        # ShapeID von Result extrahieren (TNP)
        shape_id = self._extract_shape_id(result)
        
        # Cache Entry erstellen
        entry = CacheEntry(
            result=result,
            shape_id=shape_id,
            feature_id=feature_id,
            timestamp=datetime.now()
        )
        
        # Eviction wenn voll
        if len(self._cache) >= self.max_size:
            self._evict_lru()
        
        # Speichern
        self._cache[key] = entry
        self._access_order.append(key)
        
        logger.debug(f"Cache PUT: {operation} (cache size: {len(self._cache)})")
    
    def _evict_lru(self) -> None:
        """Least Recently Used Entry entfernen."""
        if self._access_order:
            lru_key = self._access_order.pop(0)
            del self._cache[lru_key]
            logger.debug(f"Cache EVICT: {lru_key}")
    
    def _extract_shape_id(self, result: Any) -> str:
        """Extrahiert ShapeID aus Result (TNP v4.1)."""
        # TNP Integration: ShapeID aus Result holen
        if hasattr(result, 'shape_id'):
            return result.shape_id
        elif hasattr(result, 'wrapped'):
            # OCP Shape Hash
            from OCP.TopAbs import TopAbs_SHAPE
            return hashlib.sha256(str(result.wrapped).encode()).hexdigest()
        else:
            return "unknown"
    
    def clear(self) -> None:
        """Cache leeren."""
        self._cache.clear()
        self._access_order.clear()
        logger.info("Cache cleared")
    
    def get_stats(self) -> Dict[str, Any]:
        """Cache Statistiken."""
        total_hits = sum(entry.hit_count for entry in self._cache.values())
        avg_hits = total_hits / len(self._cache) if self._cache else 0
        
        return {
            "size": len(self._cache),
            "max_size": self.max_size,
            "total_hits": total_hits,
            "avg_hits": avg_hits,
            "entries": [
                {
                    "feature_id": entry.feature_id,
                    "shape_id": entry.shape_id,
                    "hits": entry.hit_count,
                    "age_seconds": (datetime.now() - entry.timestamp).total_seconds()
                }
                for entry in sorted(self._cache.values(), key=lambda e: e.hit_count, reverse=True)[:10]
            ]
        }


# Global Cache Instance
_global_cache: Optional[BREPCache] = None

def get_global_cache() -> BREPCache:
    """Gibt globale Cache Instance zurück."""
    global _global_cache
    if _global_cache is None:
        _global_cache = BREPCache(max_size=100, ttl_seconds=3600)
    return _global_cache
```

#### Schritt 2: Cache in OCP Helpers integrieren
**Datei:** `modeling/ocp_helpers.py` (erweitern)

```python
class OCPExtrudeHelper:
    def __init__(self, naming_service: TNPService, feature_id: str, 
                 use_cache: bool = True):
        self.naming_service = naming_service
        self.feature_id = feature_id
        self.use_cache = use_cache and is_enabled("ocp_first_performance")
        
        if self.use_cache:
            from modeling.brep_cache import get_global_cache
            self.cache = get_global_cache()
    
    def extrude(self, face_or_wire, distance: float) -> Solid:
        """
        Extrude mit optionaler Caching.
        """
        # Input ShapeIDs für Cache Key
        input_shape_ids = []
        if hasattr(face_or_wire, 'shape_id'):
            input_shape_ids.append(face_or_wire.shape_id)
        
        # Cache Lookup
        if self.use_cache:
            cached_result = self.cache.get(
                operation="extrude",
                input_shape_ids=input_shape_ids,
                distance=distance
            )
            if cached_result is not None:
                logger.debug(f"Cache HIT for Extrude {self.feature_id}")
                return cached_result
        
        # Extrude ausführen
        # ... bestehender Code ...
        result = self._do_extrude(face_or_wire, distance)
        
        # Cache Store
        if self.use_cache:
            self.cache.put(
                operation="extrude",
                input_shape_ids=input_shape_ids,
                result=result,
                feature_id=self.feature_id,
                distance=distance
            )
        
        return result
```

### Testplan Phase 7

#### Test 1: Cache Basic Operations
**Datei:** `test/test_phase7_brep_cache.py` (neu)

```python
def test_cache_put_get():
    """Test grundlegende Cache Operationen."""
    from modeling.brep_cache import BREPCache
    
    cache = BREPCache(max_size=10)
    
    # Put
    cache.put("test_op", ["shape1"], "result1", "feature1", param1=10)
    
    # Get
    result = cache.get("test_op", ["shape1"], param1=10)
    assert result == "result1"
    
    # Get miss
    result = cache.get("test_op", ["shape2"], param1=10)
    assert result is None
```

#### Test 2: Cache LRU Eviction
**Datei:** `test/test_phase7_brep_cache.py`

```python
def test_cache_lru_eviction():
    """Test LRU Eviction Policy."""
    from modeling.brep_cache import BREPCache
    
    cache = BREPCache(max_size=3)
    
    # 3 Entries
    cache.put("op1", ["s1"], "r1", "f1")
    cache.put("op2", ["s2"], "r2", "f2")
    cache.put("op3", ["s3"], "r3", "f3")
    
    # 4. Entry sollte 1. evicten
    cache.put("op4", ["s4"], "r4", "f4")
    
    # op1 sollte weg sein
    assert cache.get("op1", ["s1"]) is None
    
    # op2-4 sollten noch da sein
    assert cache.get("op2", ["s2"]) == "r2"
    assert cache.get("op3", ["s3"]) == "r3"
    assert cache.get("op4", ["s4"]) == "r4"
```

### Fehlerbehandlung Phase 7

#### Fehler 1: Cache Entry ungültig
**Symptom:** Cached Result führt zu Fehlern

**Diagnose:**
```python
# Result validieren vor Cache
if not is_valid_brep(result):
    logger.warning(f"Invalid BREP Result - nicht cachen")
    return result  # Ohne Cache speichern
```

**Lösung:**
1. BREP Validierung vor Cache
2. Invalid Entries automatisch evicten
3. Cache Corruption Detection

#### Fehler 2: Memory Leak
**Symptom:** Cache wächst unendlich

**Diagnose:**
```python
# Cache Size monitoren
if len(cache._cache) > cache.max_size * 1.5:
    logger.error(f"Cache overflow: {len(cache._cache)} entries")
    cache.clear()
```

**Lösung:**
1. Aggressive Eviction wenn Max Size überschritten
2. Memory Limit prüfen
3. Periodic Cache Cleanup

### Validierung Phase 7

- [ ] Unit Tests für Cache
- [ ] LRU Eviction Tests
- [ ] TTL Tests
- [ ] Integration Tests mit OCP Helpers
- [ ] Performance Benchmarks (mit/ohne Cache)
- [ ] Memory Leak Tests

---

## Phase 8: Incremental Rebuild + Dependency Graph ⏳ PENDING

### Ziel
Dependency Graph für Features und inkrementelles Rebuild nur geänderter Features.

### Detaillierter Implementierungsplan

#### Schritt 1: FeatureDependency Klasse erstellen
**Datei:** `modeling/feature_dependency.py` (neu)

```python
from typing import List, Set, Dict
from dataclasses import dataclass

@dataclass
class FeatureNode:
    """Node im Dependency Graph."""
    feature_id: str
    feature_type: str
    depends_on: Set[str]  # Feature IDs die wir brauchen
    used_by: Set[str]     # Features die uns brauchen
    
    def __hash__(self):
        return hash(self.feature_id)

class FeatureDependencyGraph:
    """
    Dependency Graph für Features.
    
    Ermöglicht:
    - Topologische Sortierung für Build Order
    - Identifikation von zyklischen Abhängigkeiten
    - Incremental Rebuild (nur geänderte Features + Abhängige)
    """
    
    def __init__(self):
        self._nodes: Dict[str, FeatureNode] = {}
        self._dirty: Set[str] = set()  # Features die rebuilded werden müssen
    
    def add_feature(self, feature_id: str, feature_type: str, 
                    depends_on: Set[str]) -> None:
        """Feature zum Graphen hinzufügen."""
        node = FeatureNode(
            feature_id=feature_id,
            feature_type=feature_type,
            depends_on=depends_on,
            used_by=set()
        )
        
        # Bidirektionale Verbindungen
        for dep_id in depends_on:
            if dep_id in self._nodes:
                self._nodes[dep_id].used_by.add(feature_id)
        
        self._nodes[feature_id] = node
    
    def remove_feature(self, feature_id: str) -> None:
        """Feature aus Graphen entfernen."""
        if feature_id not in self._nodes:
            return
        
        node = self._nodes[feature_id]
        
        # Verbindungen auflösen
        for dep_id in node.depends_on:
            if dep_id in self._nodes:
                self._nodes[dep_id].used_by.discard(feature_id)
        
        # Dependent Features markieren als dirty
        for user_id in node.used_by:
            self.mark_dirty(user_id)
        
        del self._nodes[feature_id]
    
    def mark_dirty(self, feature_id: str) -> None:
        """Feature als geändert markieren (inklusive Abhängige)."""
        if feature_id not in self._nodes:
            return
        
        self._dirty.add(feature_id)
        
        # Rekursiv: Alle Features die uns benutzen auch dirty
        node = self._nodes[feature_id]
        for user_id in node.used_by:
            self.mark_dirty(user_id)
    
    def get_build_order(self, feature_ids: Set[str] = None) -> List[str]:
        """
        Topologische Sortierung für Build Order.
        
        Args:
            feature_ids: Optional subset (default: alle)
        
        Returns:
            Liste von Feature IDs in Build Order
        
        Raises:
            ValueError: Wenn zyklische Abhängigkeiten existieren
        """
        if feature_ids is None:
            feature_ids = set(self._nodes.keys())
        
        # Topological Sort (Kahn's Algorithm)
        in_degree = {fid: 0 for fid in feature_ids}
        adjacency: Dict[str, List[str]] = {fid: [] for fid in feature_ids}
        
        for fid in feature_ids:
            node = self._nodes[fid]
            for dep_id in node.depends_on:
                if dep_id in feature_ids:
                    in_degree[fid] += 1
                    adjacency[dep_id].append(fid)
        
        # Queue mit 0 in-degree
        queue = [fid for fid, degree in in_degree.items() if degree == 0]
        build_order = []
        
        while queue:
            fid = queue.pop(0)
            build_order.append(fid)
            
            for neighbor in adjacency[fid]:
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    queue.append(neighbor)
        
        # Zyklus-Check
        if len(build_order) != len(feature_ids):
            raise ValueError(
                f"Zyklische Abhängigkeiten detected: "
                f"{feature_ids - set(build_order)}"
            )
        
        return build_order
    
    def get_incremental_rebuild_order(self, changed_features: Set[str]) -> List[str]:
        """
        Build Order für inkrementelles Rebuild.
        
        Returns:
            Liste von Features die rebuilded werden müssen (inklusive Abhängige)
        """
        # Alle geänderten + ihre Abhängigen als dirty markieren
        for fid in changed_features:
            self.mark_dirty(fid)
        
        # Build Order nur für dirty features
        dirty_in_graph = self._dirty & set(self._nodes.keys())
        build_order = self.get_build_order(dirty_in_graph)
        
        # Dirty Status zurücksetzen
        self._dirty.clear()
        
        return build_order
    
    def detect_cycles(self) -> List[List[str]]:
        """
        Zyklus-Detection (für Debugging).
        
        Returns:
            Liste von Zyklen (jeder Zyklus ist eine Liste von Feature IDs)
        """
        visited = set()
        recursion_stack = set()
        cycles = []
        
        def dfs(fid: str, path: List[str]):
            if fid in recursion_stack:
                # Zyklus gefunden
                cycle_start = path.index(fid)
                cycle = path[cycle_start:] + [fid]
                cycles.append(cycle)
                return
            
            if fid in visited:
                return
            
            visited.add(fid)
            recursion_stack.add(fid)
            
            node = self._nodes.get(fid)
            if node:
                for dep_id in node.depends_on:
                    dfs(dep_id, path + [fid])
            
            recursion_stack.remove(fid)
        
        for fid in self._nodes:
            dfs(fid, [])
        
        return cycles
```

#### Schritt 2: Body mit Dependency Graph erweitern
**Datei:** `modeling/__init__.py` (Body Klasse)

```python
class Body:
    def __init__(self, name: str = "Body"):
        # ... existing fields ...
        
        # Dependency Graph
        self._dependency_graph: Optional[FeatureDependencyGraph] = None
    
    def _ensure_dependency_graph(self):
        """Dependency Graph initialisieren wenn nötig."""
        if self._dependency_graph is None:
            self._dependency_graph = FeatureDependencyGraph()
            self._rebuild_dependency_graph()
    
    def _rebuild_dependency_graph(self):
        """Dependency Graph aus aktuellen Features neu aufbauen."""
        self._dependency_graph = FeatureDependencyGraph()
        
        # Features analysieren
        for i, feature in enumerate(self.features):
            depends_on = set()
            
            # Extrude hängt vom ersten Sketch ab
            if isinstance(feature, ExtrudeFeature):
                if hasattr(feature, 'sketch_id'):
                    depends_on.add(feature.sketch_id)
            
            # Fillet/Chamfer hängen vom vorherigen Feature ab
            elif isinstance(feature, (FilletFeature, ChamferFeature)):
                if i > 0:
                    prev_feature = self.features[i - 1]
                    depends_on.add(prev_feature.id)
            
            # Revolve hängt von Sketch ab
            elif isinstance(feature, RevolveFeature):
                if hasattr(feature, 'sketch_id'):
                    depends_on.add(feature.sketch_id)
            
            # Boolean Features hängen von 2 Bodies ab
            elif isinstance(feature, BooleanFeature):
                if hasattr(feature, 'target_body_id'):
                    depends_on.add(feature.target_body_id)
                if hasattr(feature, 'tool_body_id'):
                    depends_on.add(feature.tool_body_id)
            
            # Feature zum Graphen hinzufügen
            self._dependency_graph.add_feature(
                feature_id=feature.id,
                feature_type=type(feature).__name__,
                depends_on=depends_on
            )
    
    def add_feature(self, feature, rebuild: bool = True) -> None:
        """Feature hinzufügen mit Dependency Graph Update."""
        super().add_feature(feature, rebuild=False)
        
        # Dependency Graph updaten
        self._ensure_dependency_graph()
        self._rebuild_dependency_graph()
        
        if rebuild:
            self._incremental_rebuild(changed_features={feature.id})
    
    def remove_feature(self, feature_id: str) -> None:
        """Feature entfernen mit Dependency Graph Update."""
        super().remove_feature(feature_id)
        
        # Dependency Graph updaten
        if self._dependency_graph:
            self._dependency_graph.remove_feature(feature_id)
            self._rebuild_dependency_graph()
    
    def _incremental_rebuild(self, changed_features: Set[str] = None):
        """
        Inkrementelles Rebuild nur geänderter Features.
        
        Args:
            changed_features: Features die geändert wurden (default: alle)
        """
        self._ensure_dependency_graph()
        
        if changed_features is None:
            changed_features = {f.id for f in self.features}
        
        # Build Order für inkrementelles Rebuild
        build_order = self._dependency_graph.get_incremental_rebuild_order(changed_features)
        
        logger.info(f"Incremental Rebuild: {len(build_order)} Features")
        
        # Features in Build Order rebuilden
        for feature_id in build_order:
            feature = next((f for f in self.features if f.id == feature_id), None)
            if feature:
                try:
                    self._compute_feature(feature)
                except Exception as e:
                    logger.error(f"Feature {feature_id} Rebuild fehlgeschlagen: {e}")
                    raise
        
        # TNP Update für finalen Solid
        if self._tnp_service:
            self._tnp_service.update_body_state(self.id, self._build123d_solid)
    
    def modify_feature(self, feature_id: str, **kwargs) -> None:
        """
        Feature modifizieren mit inkrementellem Rebuild.
        
        Args:
            feature_id: ID des zu modifizierenden Features
            **kwargs: Zu setzende Attribute
        """
        # Feature finden und modifizieren
        feature = next((f for f in self.features if f.id == feature_id), None)
        if not feature:
            raise ValueError(f"Feature {feature_id} nicht gefunden")
        
        # Attribute setzen
        for key, value in kwargs.items():
            setattr(feature, key, value)
        
        # Inkrementelles Rebuild
        self._incremental_rebuild(changed_features={feature_id})
```

### Testplan Phase 8

#### Test 1: Dependency Graph Basic Operations
**Datei:** `test/test_phase8_dependency_graph.py` (neu)

```python
def test_dependency_graph_build_order():
    """Test topologische Sortierung."""
    from modeling.feature_dependency import FeatureDependencyGraph
    
    graph = FeatureDependencyGraph()
    
    # Features: Extrude (hängt von Sketch ab) → Fillet (hängt von Extrude ab)
    graph.add_feature("sketch1", "Sketch", depends_on=set())
    graph.add_feature("extrude1", "Extrude", depends_on={"sketch1"})
    graph.add_feature("fillet1", "Fillet", depends_on={"extrude1"})
    
    build_order = graph.get_build_order()
    
    assert build_order == ["sketch1", "extrude1", "fillet1"]
```

#### Test 2: Incremental Rebuild
**Datei:** `test/test_phase8_dependency_graph.py`

```python
def test_incremental_rebuild():
    """Test inkrementelles Rebuild nur geänderter Features."""
    doc = Document()
    
    # 3 Features: Extrude → Fillet → Chamfer
    sketch = Sketch("Box")
    sketch.add_rectangle((0, 0), (10, 10))
    doc.add_sketch(sketch)
    
    body = Body("Box")
    extrude = ExtrudeFeature(sketch_id=sketch.id, extrude_depth=10.0)
    body.add_feature(extrude)
    
    fillet = FilletFeature(edges=[body.edges().front_edge()], radius=1.0)
    body.add_feature(fillet)
    
    chamfer = ChamferFeature(edges=[body.edges().top_edge()], distance=0.5)
    body.add_feature(chamfer)
    
    # Nur Extrude ändern
    body.modify_feature(extrude.id, extrude_depth=15.0)
    
    # Assertions: Alle Features rebuildet (Extrude → Fillet → Chamfer)
    assert len(body._dependency_graph.get_dirty_features()) == 3
```

### Fehlerbehandlung Phase 8

#### Fehler 1: Zyklische Abhängigkeiten
**Symptom:** `ValueError: Zyklische Abhängigkeiten detected`

**Diagnose:**
```python
# Zyklus detecten
cycles = graph.detect_cycles()
if cycles:
    logger.error(f"Zyklen gefunden: {cycles}")
```

**Lösung:**
1. Zyklus auflösen (Feature reihenfolge ändern)
2. Boolean Operationen prüfen (selbst-referenz)
3. Sketch-Zyklen vermeiden (zirkuläre Constraints)

#### Fehler 2: Missing Dependency
**Symptom:** Feature rebuildet aber Abhängigkeiten fehlen

**Diagnose:**
```python
# Dependency Check
if missing_deps := node.depends_on - set(self._nodes.keys()):
    logger.warning(f"Missing dependencies: {missing_deps}")
```

**Lösung:**
1. Alle Dependencies vor Rebuild validieren
2. Missing Dependencies automatisch hinzufügen
3. Feature Order korrigieren

### Validierung Phase 8

- [ ] Unit Tests für Dependency Graph
- [ ] Topological Sort Tests
- [ ] Cycle Detection Tests
- [ ] Incremental Rebuild Tests
- [ ] Integration Tests mit Body
- [ ] Performance Benchmarks (Full vs Incremental Rebuild)

---

## Phase 9: Native BREP Persistenz ⏳ PENDING

### Ziel
Speichern/Laden von BREP-Geometrie (.brep Format) mit TNP v4.1 ShapeID Persistenz.

### Detaillierter Implementierungsplan

#### Schritt 1: BREPPersistence Klasse erstellen
**Datei:** `modeling/brep_persistence.py` (neu)

```python
import json
from pathlib import Path
from typing import Dict, Any, Optional
from dataclasses import dataclass, asdict

@dataclass
class BREPMetadata:
    """Metadaten für BREP Dateien."""
    shape_id: str  # TNP v4.1 ShapeID
    feature_id: str
    operation_type: str
    shape_type: str  # "Solid", "Face", "Edge", etc.
    version: str = "1.0"
    timestamp: str = ""
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'BREPMetadata':
        return cls(**data)

class BREPPersistence:
    """
    Native BREP Persistenz mit TNP Support.
    
    Speichert BREP-Geometrie im nativen OpenCascade .brep Format
    zusammen mit Metadaten (JSON) und TNP ShapeIDs.
    """
    
    def __init__(self, base_path: Path = Path("data/breps")):
        self.base_path = base_path
        self.base_path.mkdir(parents=True, exist_ok=True)
    
    def _get_brep_path(self, shape_id: str) -> Path:
        """Pfad zur .brep Datei."""
        return self.base_path / f"{shape_id}.brep"
    
    def _get_meta_path(self, shape_id: str) -> Path:
        """Pfad zur Metadaten JSON Datei."""
        return self.base_path / f"{shape_id}.meta.json"
    
    def save_shape(self, shape, metadata: BREPMetadata) -> None:
        """
        Shape als .brep speichern.
        
        Args:
            shape: Build123d oder OCP Shape
            metadata: Metadaten (inklusive TNP ShapeID)
        """
        from OCP.BRep import BRep_Builder
        from OCP.TopoDS import TopoDS_Shape
        
        # OCP Shape extrahieren
        ocp_shape = shape.wrapped if hasattr(shape, 'wrapped') else shape
        
        # Speichern als .brep
        brep_path = self._get_brep_path(metadata.shape_id)
        
        try:
            from OCP.BRepTools import BRepTools_Write
            BRepTools_Write(ocp_shape, str(brep_path))
        except Exception as e:
            raise RuntimeError(f"BREP Save fehlgeschlagen: {e}")
 from e
        
        # Metadaten speichern
        metadata.timestamp = datetime.now().isoformat()
        meta_path = self._get_meta_path(metadata.shape_id)
        
        with open(meta_path, 'w') as f:
            json.dump(metadata.to_dict(), f, indent=2)
        
        logger.info(f"BREP gespeichert: {brep_path}")
    
    def load_shape(self, shape_id: str) -> Optional[Any]:
        """
        Shape aus .brep laden.
        
        Args:
            shape_id: TNP ShapeID
        
        Returns:
            Build123d Shape oder None wenn nicht gefunden
        """
        brep_path = self._get_brep_path(shape_id)
        
        if not brep_path.exists():
            logger.warning(f"BREP nicht gefunden: {brep_path}")
            return None
        
        # Laden aus .brep
        try:
            from OCP.BRepTools import BRepTools_Read
            from build123d import Shape
            
            ocp_shape = TopoDS_Shape()
            BRepTools_Read(str(brep_path), ocp_shape)
            
            # In Build123d Shape konvertieren
            return Shape(self._fix_shape_ocp(ocp_shape))
            
        except Exception as e:
            raise RuntimeError(f"BREP Load fehlgeschlagen: {e}")
    
    def load_metadata(self, shape_id: str) -> Optional[BREPMetadata]:
        """Metadaten für Shape laden."""
        meta_path = self._get_meta_path(shape_id)
        
        if not meta_path.exists():
            return None
        
        with open(meta_path, 'r') as f:
            data = json.load(f)
        
        return BREPMetadata.from_dict(data)
    
    def delete_shape(self, shape_id: str) -> None:
        """Shape und Metadaten löschen."""
        brep_path = self._get_brep_path(shape_id)
        meta_path = self._get_meta_path(shape_id)
        
        if brep_path.exists():
            brep_path.unlink()
        
        if meta_path.exists():
            meta_path.unlink()
        
        logger.info(f"BREP gelöscht: {shape_id}")
    
    def list_shapes(self) -> Dict[str, BREPMetadata]:
        """Alle gespeicherten Shapes auflisten."""
        shapes = {}
        
        for meta_path in self.base_path.glob("*.meta.json"):
            shape_id = meta_path.stem
            metadata = self.load_metadata(shape_id)
            if metadata:
                shapes[shape_id] = metadata
        
        return shapes
    
    def cleanup_expired(self, ttl_hours: int = 24) -> int:
        """
        Alte BREP Dateien löschen.
        
        Returns:
            Anzahl gelöschter Dateien
        """
        from datetime import datetime, timedelta
        
        expired_count = 0
        cutoff = datetime.now() - timedelta(hours=ttl_hours)
        
        for shape_id, metadata in self.list_shapes().items():
            try:
                timestamp = datetime.fromisoformat(metadata.timestamp)
                if timestamp < cutoff:
                    self.delete_shape(shape_id)
                    expired_count += 1
            except Exception as e:
                logger.warning(f"Cleanup error für {shape_id}: {e}")
        
        logger.info(f"Cleanup: {expired_count} alte BREPs gelöscht")
        return expired_count
```

#### Schritt 2: Document mit BREP Persistenz erweitern
**Datei:** `modeling/__init__.py` (Document Klasse)

```python
class Document:
    def __init__(self, name: str = "Document"):
        # ... existing fields ...
        
        # BREP Persistenz
        self._brep_persistence: Optional[BREPPersistence] = None
    
    def enable_brep_persistence(self, base_path: Path = Path("data/breps")):
        """BREP Persistenz aktivieren."""
        from modeling.brep_persistence import BREPPersistence
        self._brep_persistence = BREPPersistence(base_path)
        logger.info(f"BREP Persistenz aktiviert: {base_path}")
    
    def save_to_brep(self, body_id: str) -> Dict[str, str]:
        """
        Body als BREP speichern.
        
        Args:
            body_id: ID des zu speichernen Bodies
        
        Returns:
            Mapping Feature ID → Shape ID
        """
        if self._brep_persistence is None:
            raise RuntimeError("BREP Persistenz nicht aktiviert")
        
        body = self.get_body(body_id)
        if not body:
            raise ValueError(f"Body {body_id} nicht gefunden")
        
        mapping = {}
        
        # Body Solid speichern
        from modeling.brep_persistence import BREPMetadata
        
        body_metadata = BREPMetadata(
            shape_id=body.id,
            feature_id=body.id,
            operation_type="body",
            shape_type="Solid"
        )
        self._brep_persistence.save_shape(body._build123d_solid, body_metadata)
        mapping[body.id] = body.id
        
        # Feature Results speichern (falls im Cache)
        if hasattr(body, '_feature_results'):
            for feature_id, result in body._feature_results.items():
                feature_metadata = BREPMetadata(
                    shape_id=result.shape_id,
                    feature_id=feature_id,
                    operation_type=type(result).__name__,
                    shape_type="Solid"
                )
                self._brep_persistence.save_shape(result, feature_metadata)
                mapping[feature_id] = result.shape_id
        
        logger.info(f"Body {body_id} als BREP gespeichert: {len(mapping)} Shapes")
        return mapping
    
    def load_from_brep(self, body_id: str) -> Optional[Body]:
        """
        Body aus BREP laden.
        
        Args:
            body_id: ID des zu ladenden Bodies
        
        Returns:
            Geladener Body oder None wenn nicht gefunden
        """
        if self._brep_persistence is None:
            raise RuntimeError("BREP Persistenz nicht aktiviert")
        
        # Body Solid laden
        body_shape = self._brep_persistence.load_shape(body_id)
        if not body_shape:
            return None
        
        # Body erstellen
        body = Body(name=f"Loaded_{body_id}")
        body._build123d_solid = body_shape
        body.id = body_id
        
        # Metadaten laden
        metadata = self._brep_persistence.load_metadata(body_id)
        if metadata:
            logger.info(f"Body {body_id} aus BREP geladen: {metadata}")
        
        # Zum Document hinzufügen
        self.add_body(body)
        
        return body
    
    def cleanup_breps(self, ttl_hours: int = 24) -> int:
        """Alte BREP Dateien aufräumen."""
        if self._brep_persistence is None:
            return 0
        
        return self._brep_persistence.cleanup_expired(ttl_hours)
```

### Testplan Phase 9

#### Test 1: BREP Save/Load
**Datei:** `test/test_phase9_brep_persistence.py` (neu)

```python
def test_brep_save_load():
    """Test BREP Speichern und Laden."""
    from modeling.brep_persistence import BREPPersistence, BREPMetadata
    from test.ocp_test_utils import create_test_box
    
    persistence = BREPPersistence()
    
    # Body erstellen
    body = create_test_box(Document())
    
    # Speichern
    metadata = BREPMetadata(
        shape_id=body.id,
        feature_id=body.id,
        operation_type="body",
        shape_type="Solid"
    )
    persistence.save_shape(body._build123d_solid, metadata)
    
    # Laden
    loaded_shape = persistence.load_shape(body.id)
    
    assert loaded_shape is not None
    assert loaded_shape.volume == body._build123d_solid.volume
    
    # Cleanup
    persistence.delete_shape(body.id)
```

#### Test 2: Document BREP Persistenz
**Datei:** `test/test_phase9_brep_persistence.py`

```python
def test_document_brep_save_load():
    """Test Document BREP Persistenz."""
    doc = Document()
    doc.enable_brep_persistence()
    
    # Body erstellen
    body = create_test_box(doc)
    doc.add_body(body)
    
    # Speichern
    mapping = doc.save_to_brep(body.id)
    assert body.id in mapping
    
    # Neues Document und Laden
    doc2 = Document()
    doc2.enable_brep_persistence()
    
    loaded_body = doc2.load_from_brep(body.id)
    
    assert loaded_body is not None
    assert loaded_body.volume == body.volume
```

### Fehlerbehandlung Phase 9

#### Fehler 1: BREP Datei beschädigt
**Symptom:** `RuntimeError: BREP Load fehlgeschlagen`

**Diagnose:**
```python
# BREP Validierung
try:
    from OCP.BRepCheck import BRepCheck_Analyzer
    analyzer = BRepCheck_Analyzer(shape)
    status = analyzer.IsValid()
    if status != 0:
        logger.error(f"Invalid BREP: status={status}")
except Exception as e:
    logger.error(f"BREP validation error: {e}")
```

**Lösung:**
1. BREP Validierung vor Load
2. Beschädigte Dateien automatisch löschen
3. Fallback zu Rebuild

#### Fehler 2: ShapeID Konflikt
**Symptom:** Zwei verschiedene Bodies haben gleiche ShapeID

**Diagnose:**
```python
# ShapeID Uniqueness prüfen
existing_shape_ids = set(list_shapes().keys())
if new_shape_id in existing_shape_ids:
    logger.warning(f"ShapeID Konflikt: {new_shape_id}")
```

**Lösung:**
1. ShapeID Uniqueness erzwingen
2. Bei Konflikt: neue ShapeID generieren
3. Mapping Tabelle für ShapeID Remapping

### Validierung Phase 9

- [ ] Unit Tests für BREPPersistence
- [ ] Save/Load Tests
- [ ] Document Integration Tests
- [ ] TNP ShapeID Persistenz Tests
- [ ] Cleanup Tests
- [ ] Performance Benchmarks (File I/O)
- [ ] Corruption Recovery Tests

---

## Zusammenfassung & Checklisten

### Pre-Flight Checklist vor Phase-Start

#### Vor jeder Phase:
- [ ] Backup des aktuellen Codes (Git commit)
- [ ] Feature Flags in `config/feature_flags.py` vorhanden
- [ ] OCP Helpers in `modeling/ocp_helpers.py` implementiert
- [ ] Test-Infrastruktur in `test/ocp_test_utils.py` bereit
- [ ] Dokumentation in AGENTS.md aktualisiert

#### Phase-spezifische Checklisten:

**Phase 2:**
- [ ] `_compute_extrude_part()` refactored
- [ ] Legacy Code in `_compute_extrude_part_legacy()` ausgelagert
- [ ] Feature-ID Validierung vorhanden
- [ ] TNP Service Check vorhanden
- [ ] Tests geschrieben und bestanden
- [ ] Performance nicht schlechter als Legacy

**Phase 3:**
- [ ] `_compute_fillet_part()` und `_compute_chamfer_part()` refactored
- [ ] OCPFilletHelper und OCPChamferHelper integriert
- [ ] Edge Validierung (Adjazenz, Radius)
- [ ] Tests für Fillet und Chamfer
- [ ] Integration Test (Extrude → Fillet → Chamfer)

**Phase 4:**
- [ ] `_compute_revolve_part()` refactored
- [ ] OCPRevolveHelper, OCPLoftHelper, OCPSweepHelper erstellt
- [ ] Axis-Validierung vorhanden
- [ ] Loft Section Parallelität Check
- [ ] Tests für Revolve, Loft, Sweep

**Phase 5:**
- [ ] `_compute_shell_part()` und `_compute_hollow_part()` refactored
- [ ] OCPShellHelper und OCPHollowHelper erstellt
- [ ] Thickness Validierung vorhanden
- [ ] Closure Check nach Shell
- [ ] Tests für Shell und Hollow

**Phase 7:**
- [ ] BREPCache implementiert
- [ ] Cache in OCP Helpers integriert
- [ ] LRU Eviction funktioniert
- [ ] TTL Support vorhanden
- [ ] Performance Benchmarks (mit/ohne Cache)

**Phase 8:**
- [ ] FeatureDependencyGraph implementiert
- [ ] Topological Sort funktioniert
- [ ] Cycle Detection vorhanden
- [ ] Incremental Rebuild in Body integriert
- [ ] Tests für Dependency Graph und Incremental Rebuild

**Phase 9:**
- [ ] BREPPersistence implementiert
- [ ] Document BREP Persistenz integriert
- [ ] Save/Load funktioniert
- [ ] TNP ShapeID Persistenz vorhanden
- [ ] Cleanup Mechanismus implementiert
- [ ] Tests für Save, Load, Cleanup

### Post-Phase Checklist

#### Nach jeder Phase:
- [ ] Alle Tests bestanden: `pytest test/test_phase*.py -v`
- [ ] Legacy Tests nicht gebrochen: `pytest test/test_*legacy*.py -v`
- [ ] Integration Tests bestanden
- [ ] Performance Benchmarks durchgeführt
- [ ] Code Review durch peer
- [ ] AGENTS.md aktualisiert
- [ ] Git commit mit descriptive message
- [ ] Feature Flags dokumentiert

---

**Ende der OCP-First Migration Plan Dokumentation**