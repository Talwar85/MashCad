# Split Body Multi-Body Architecture Plan

> **Status:** Design Phase
> **Aufwand:** 6-8 Stunden
> **Risiko:** MEDIUM (größeres Refactoring)
> **Ziel:** Korrektes Split mit Historie-Sharing und Undo/Redo

---

## Problem Statement

**Aktuell:**
- Split gibt nur EIN Solid zurück (above/below)
- `keep_side == "both"` nicht implementiert
- Beim Split entsteht ein zweiter Body, aber:
  - ❌ Hat keine shared Historie
  - ❌ Bleibt beim Undo bestehen (Bug)
  - ❌ Wird nicht korrekt im Document registriert

**Soll:**
- Split erzeugt 2 Bodies mit shared Historie
- Beide Bodies haben Features[0..n-1] identisch
- Split-Feature ist das n-te Feature in beiden Bodies
- Undo löscht beide Bodies und restored Original

---

## Architektur Design

### 1. SplitFeature Result Type

**Problem:** Features geben EIN Solid zurück.

**Lösung:** Spezieller Result-Type für Multi-Body Operations:

```python
@dataclass
class SplitResult:
    """Result of a split operation that creates 2 bodies."""
    body_above: Solid      # Body auf der +normal Seite
    body_below: Solid      # Body auf der -normal Seite
    split_plane: dict      # Plane-Info für Visualisierung

    # TNP v4.0: Optional Face-ShapeIDs für Split-Faces
    above_split_face_ids: List = None
    below_split_face_ids: List = None
```

### 2. Body Historie-Sharing

**Problem:** Beide Bodies müssen Historie teilen.

**Lösung:** `source_body_id` und `split_index` in Body:

```python
class Body:
    def __init__(self):
        # ... existing fields ...

        # Split-Tracking
        self.source_body_id: Optional[str] = None  # ID des Original-Bodies
        self.split_index: Optional[int] = None      # Index des Split-Features
        self.split_side: Optional[str] = None       # "above" oder "below"
```

**Feature-Sharing:**
```python
# Original Body
original_body.features = [Extrude, Fillet, SplitFeature]

# Body 1 (above) - geteilt bei Index 2
body_above = Body()
body_above.features = original_body.features.copy()  # [Extrude, Fillet, SplitFeature]
body_above.source_body_id = original_body.id
body_above.split_index = 2
body_above.split_side = "above"

# Body 2 (below)
body_below = Body()
body_below.features = original_body.features.copy()  # [Extrude, Fillet, SplitFeature]
body_below.source_body_id = original_body.id
body_below.split_index = 2
body_below.split_side = "below"
```

### 3. _compute_split() Refactoring

**Aktuell:** Gibt 1 Solid zurück
**Neu:** Gibt SplitResult zurück

```python
def _compute_split(self, feature: 'SplitFeature', current_solid) -> SplitResult:
    """
    Teilt einen Körper in 2 Hälften.

    Returns:
        SplitResult mit beiden Bodies
    """
    # ... OCP Split-Logik ...

    # Beide HalfSpaces erstellen
    ref_pt_above = np.array(feature.plane_origin) + n * 100.0
    half_space_above = BRepPrimAPI_MakeHalfSpace(split_face, gp_Pnt(*ref_pt_above))

    ref_pt_below = np.array(feature.plane_origin) - n * 100.0
    half_space_below = BRepPrimAPI_MakeHalfSpace(split_face, gp_Pnt(*ref_pt_below))

    # Cut für beide Seiten
    cut_above = BRepAlgoAPI_Cut(shape, half_space_above.Solid())
    cut_below = BRepAlgoAPI_Cut(shape, half_space_below.Solid())

    cut_above.Build()
    cut_below.Build()

    if not (cut_above.IsDone() and cut_below.IsDone()):
        raise ValueError("Split fehlgeschlagen")

    # Beide Solids erstellen
    from build123d import Solid
    body_above = Solid(self._fix_shape_ocp(cut_above.Shape()))
    body_below = Solid(self._fix_shape_ocp(cut_below.Shape()))

    return SplitResult(
        body_above=body_above,
        body_below=body_below,
        split_plane={
            "origin": feature.plane_origin,
            "normal": feature.plane_normal
        }
    )
```

### 4. Document.split_body()

**Neue Methode** im Document für Multi-Body-Handling:

```python
class Document:
    def split_body(self, body: Body, plane_origin: tuple, plane_normal: tuple) -> Tuple[Body, Body]:
        """
        Teilt einen Body in 2 Hälften und fügt beide zum Document hinzu.

        Returns:
            (body_above, body_below) - beide im Document registriert
        """
        # 1. Split-Feature erstellen
        split_feat = SplitFeature(
            plane_origin=plane_origin,
            plane_normal=plane_normal,
            keep_side="both"  # Explizit beide behalten
        )

        # 2. Feature zu Original-Body hinzufügen
        body.add_feature(split_feat, rebuild=False)

        # 3. _compute_split aufrufen → SplitResult
        split_result = body._compute_split(split_feat, body._build123d_solid)

        # 4. Beide Bodies erstellen mit shared history
        split_index = len(body.features) - 1

        body_above = Body(name=f"{body.name}_above")
        body_above.features = body.features.copy()
        body_above._build123d_solid = split_result.body_above
        body_above.source_body_id = body.id
        body_above.split_index = split_index
        body_above.split_side = "above"

        body_below = Body(name=f"{body.name}_below")
        body_below.features = body.features.copy()
        body_below._build123d_solid = split_result.body_below
        body_below.source_body_id = body.id
        body_below.split_index = split_index
        body_below.split_side = "below"

        # 5. Original-Body aus Document entfernen
        self.remove_body(body.id)

        # 6. Beide neue Bodies hinzufügen
        self.add_body(body_above)
        self.add_body(body_below)

        return body_above, body_below
```

### 5. SplitBodyCommand für Undo/Redo

**Spezielles Command** das beide Bodies trackt:

```python
class SplitBodyCommand(QUndoCommand):
    """
    Undo/Redo Command für Body-Split-Operationen.

    Tracked:
    - Original Body (vor Split)
    - Body Above (nach Split)
    - Body Below (nach Split)
    """

    def __init__(self, document, original_body, body_above, body_below, split_feature):
        super().__init__("Split Body")
        self.document = document

        # Snapshots
        self.original_body_snapshot = original_body.to_dict()
        self.original_body_id = original_body.id

        self.body_above_id = body_above.id
        self.body_below_id = body_below.id

        self.split_feature = split_feature

    def redo(self):
        """
        Split durchführen: Original löschen, 2 neue Bodies hinzufügen.
        """
        if self.document.get_body(self.original_body_id):
            # Original Body existiert → Split ausführen
            original = self.document.get_body(self.original_body_id)

            body_above, body_below = self.document.split_body(
                original,
                self.split_feature.plane_origin,
                self.split_feature.plane_normal
            )

            # IDs aktualisieren (falls neu erstellt)
            self.body_above_id = body_above.id
            self.body_below_id = body_below.id
        else:
            # Wiederhole Split (z.B. nach Undo → Redo)
            # Bodies könnten bereits existieren
            pass

    def undo(self):
        """
        Split rückgängig: Beide Bodies löschen, Original wiederherstellen.
        """
        # 1. Beide Split-Bodies aus Document entfernen
        if self.document.get_body(self.body_above_id):
            self.document.remove_body(self.body_above_id)

        if self.document.get_body(self.body_below_id):
            self.document.remove_body(self.body_below_id)

        # 2. Original Body wiederherstellen
        original_body = Body.from_dict(self.original_body_snapshot)

        # WICHTIG: Split-Feature entfernen
        if original_body.features and isinstance(original_body.features[-1], SplitFeature):
            original_body.features.pop()

        # Rebuild ohne Split-Feature
        original_body._rebuild()

        # 3. Original Body zum Document hinzufügen
        self.document.add_body(original_body)

        logger.info(f"Split Undo: Restored original body {original_body.id}")
```

### 6. GUI Integration

**Split Dialog** muss beide Bodies anzeigen:

```python
# In gui/tool_panel_3d.py oder gui/dialogs/split_dialog.py

def apply_split(self):
    """User klickt Apply im Split-Dialog."""
    body = self.selected_body
    plane_origin = self.get_plane_origin()
    plane_normal = self.get_plane_normal()

    # SplitBodyCommand erstellen
    original_body_snapshot = body.to_dict()

    # Split durchführen (ohne Command zunächst, für Vorschau)
    body_above, body_below = self.document.split_body(body, plane_origin, plane_normal)

    # Command für Undo/Redo erstellen
    split_cmd = SplitBodyCommand(
        self.document,
        body,  # Original (bereits gelöscht)
        body_above,
        body_below,
        split_feature=SplitFeature(
            plane_origin=plane_origin,
            plane_normal=plane_normal,
            keep_side="both"
        )
    )

    # Command zu Undo-Stack hinzufügen
    self.undo_stack.push(split_cmd)

    # UI Update
    self.refresh_browser()
    self.viewport.update_all_bodies()

    logger.success(f"Split: Created {body_above.name} and {body_below.name}")
```

---

## Implementation Plan

### Phase 1: SplitResult & _compute_split Refactoring

**Dateien:**
- `modeling/__init__.py` (Lines 3664-3725)

**Änderungen:**
1. SplitResult dataclass hinzufügen
2. _compute_split() refactoren um beide Bodies zu berechnen
3. Beide HalfSpace-Cuts durchführen

**Aufwand:** 1 Stunde

---

### Phase 2: Body Split-Tracking

**Dateien:**
- `modeling/__init__.py` (Body Klasse, Lines ~100-200)

**Änderungen:**
1. Neue Felder: `source_body_id`, `split_index`, `split_side`
2. to_dict/from_dict für diese Felder
3. _rebuild() respektiert split_side beim SplitFeature

**Aufwand:** 1 Stunde

---

### Phase 3: Document.split_body()

**Dateien:**
- `modeling/__init__.py` (Document Klasse)

**Änderungen:**
1. Neue Methode split_body()
2. Shared history setup für beide Bodies
3. Original Body entfernen, neue Bodies hinzufügen

**Aufwand:** 2 Stunden

---

### Phase 4: SplitBodyCommand

**Dateien:**
- `gui/commands/feature_commands.py` (neue Klasse)

**Änderungen:**
1. SplitBodyCommand implementieren
2. redo(): Split durchführen
3. undo(): Beide Bodies löschen, Original restore

**Aufwand:** 2 Stunden

---

### Phase 5: GUI Integration

**Dateien:**
- `gui/tool_panel_3d.py` oder `gui/dialogs/split_dialog.py`

**Änderungen:**
1. Split Dialog nutzt SplitBodyCommand
2. Zeigt beide resultierenden Bodies an
3. Browser-Update nach Split

**Aufwand:** 1 Stunde

---

## Test Plan

### Test 1: Einfacher Split
1. Box erstellen
2. Split horizontal (beide behalten)
3. **Erwartung:** 2 Bodies im Browser, Original weg

### Test 2: Split mit Historie
1. Sketch → Extrude → Fillet
2. Split
3. **Erwartung:** Beide Bodies haben [Extrude, Fillet, Split] in Features

### Test 3: Undo/Redo
1. Box → Split
2. Undo
3. **Erwartung:** Beide Bodies weg, Original wieder da
4. Redo
5. **Erwartung:** Split wieder, 2 Bodies

### Test 4: Split → Weitere Features
1. Box → Split
2. Body_above → Fillet hinzufügen
3. **Erwartung:** Nur Body_above hat Fillet, Body_below nicht

### Test 5: Speichern/Laden
1. Box → Split
2. Speichern
3. Laden
4. **Erwartung:** 2 Bodies geladen mit korrekter Historie

---

## Risiken & Mitigation

### Risiko 1: _rebuild() Endlosschleife

**Problem:** Wenn Body_above rebuilt, führt es Split aus → erzeugt wieder 2 Bodies?

**Mitigation:**
- SplitFeature prüft `body.split_side`
- Wenn gesetzt: Gibt nur die entsprechende Hälfte zurück
- Kein neuer Body wird erstellt

```python
def _compute_feature(self, feature, current_solid):
    if isinstance(feature, SplitFeature):
        if self.split_side:
            # Rebuild-Modus: Nur unsere Seite berechnen
            split_result = self._compute_split(feature, current_solid)
            return split_result.body_above if self.split_side == "above" else split_result.body_below
        else:
            # Erster Split: Beide Bodies werden von Document.split_body() gehandhabt
            raise ValueError("Split during rebuild should have split_side set")
```

### Risiko 2: TNP Resolution nach Split

**Problem:** Split-Faces haben neue ShapeIDs, Referenzen könnten brechen.

**Mitigation:**
- SplitResult enthält `above_split_face_ids` und `below_split_face_ids`
- Diese werden in Body registriert
- Features nach Split können Split-Faces via TNP referenzieren

### Risiko 3: Performance bei vielen Splits

**Problem:** Jeder Split dupliziert Feature-Liste.

**Mitigation:**
- Feature-Listen sind Python-Listen (cheap copy)
- Bei Bedarf: Shared Feature-History via Pointer (Phase 2 Optimierung)

---

## Backwards Compatibility

**Legacy Split (keep_side="above"/"below"):**
- Funktioniert weiterhin über _compute_split()
- Gibt nur eine Hälfte zurück
- Kein Multi-Body-Handling nötig

**Migration:**
- Alte .mcad Files mit Split: Laden funktioniert
- Split-Feature bleibt parametrisch
- Keine Breaking Changes

---

## Zusammenfassung

**Vorher:**
- ❌ Split gibt nur 1 Body zurück
- ❌ Undo/Redo fehlerhaft (Body 2 bleibt)
- ❌ Keine Historie-Sharing

**Nachher:**
- ✅ Split erstellt 2 Bodies mit shared Historie
- ✅ Undo löscht beide Bodies, restored Original
- ✅ Rebuild funktioniert korrekt für beide Bodies
- ✅ TNP v4.0 kompatibel

**Aufwand:** 6-8 Stunden
**Risiko:** MEDIUM (aber machbar mit diesem Plan)

---

**Ready to implement?**
