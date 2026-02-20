# MashCad - Technische Schulden & TODOs

> **Letzte Aktualisierung:** 2026-02-20
> **Gesamt:** 10 offene Punkte

---

## 🔴 Kritisch (Müssen vor Release behoben werden)

### BUGs

*Keine kritischen Bugs aktuell.*

---

## 🟡 Hoch (Wichtige Features/Refactoring)

### Features

| Datei | Zeile | Beschreibung | Status |
|-------|-------|--------------|--------|
| `gui/main_window.py` | 8489 | Live-Preview für Texturen wenn Performance es erlaubt | 🟡 Offen |
| `gui/main_window.py` | 8746 | Live-Preview für Patterns wenn Performance es erlaubt | 🟡 Offen |
| `gui/main_window.py` | 8940 | Normal-Map Preview im Viewport | 🟡 Offen |

### Core Improvements

| Datei | Zeile | Beschreibung | Status |
|-------|-------|--------------|--------|
| `modeling/__init__.py` | 4611 | OCP History von Boolean-Operationen extrahieren für besseres TNP | 🟡 Offen |
| `modeling/brep_face_analyzer.py` | 685 | Helix-Fitting implementieren | 🟡 Offen |

---

## 🟢 Mittel (Verbesserungen/Nice-to-have)

### Mesh Converter

| Datei | Zeile | Beschreibung | Status |
|-------|-------|--------------|--------|
| `meshconverter/brep_optimizer.py` | 664 | NURBS-Replacement in zukünftiger Version | 🟢 Offen |
| `meshconverter/brep_optimizer.py` | 970 | Besserer Ansatz für Planar-Gruppen in Zukunft | 🟢 Offen |
| `meshconverter/mesh_converter_v10.py` | 225 | Consistent normal orientation implementieren | 🟢 Offen |

---

## 🔵 Niedrig (Archiv/Referenz)

### Dokumentation/Hinweise

| Datei | Zeile | Beschreibung | Status |
|-------|-------|--------------|--------|
| `gui/main_window.py` | 5691 | Height-Inversion basierend auf Mesh vs B-Rep Normale entfernt | 🔵 Dokumentiert |
| `modeling/__init__.py` | 33 | Altes TNP-System (Phase 8.2) deaktiviert - v3.0 aktiv | 🔵 Archiviert |
| `modeling/__init__.py` | 1197 | Altes TNP-System (Phase 8.2/3) deaktiviert - v4.0 aktiv | 🔵 Archiviert |
| `modeling/shape_reference.py` | 198 | session_id is NOT persisted - nur in current session gültig | 🔵 Dokumentiert |
| `gui/sketch_handlers.py` | 2982 | Dimension input handled by _show_dimension_input() | 🔵 Dokumentiert |
| `meshconverter/__init__.py` | 45 | Fillet conversion disabled, only chamfers work | 🔵 Dokumentiert |
| `meshconverter/fillet_aware_converter.py` | 249 | Fillet (cylindrical) face creation is disabled for now | 🔵 Dokumentiert |

---

## 📊 Statistik

```
🔴 Kritisch:  0
🟡 Hoch:      5
🟢 Mittel:    3
🔵 Niedrig:   7
─────────────
Gesamt:      15
```

---

## 🏷️ Labels

- **BUG** - Bekannter Fehler der behoben werden muss
- **FEATURE** - Neues Feature das implementiert werden soll
- **REFACTOR** - Code-Verbesserung ohne Funktionsänderung
- **PERFORMANCE** - Performance-Optimierung
- **DOCUMENTATION** - Nur zur Dokumentation/Information

---

## 📝 Workflow

1. **TODO erledigt?** → Kommentar aus Code entfernen + TODO.md aktualisieren
2. **Neues TODO?** → Hier dokumentieren + Code-Kommentar mit `# TODO: ...`
3. **Priorität ändern?** → In entsprechende Sektion verschieben

---

*Diese Datei wird automatisch aus Code-Kommentaren generiert.  
Pattern: `# TODO: ...`, `# FIXME: ...`, `# HACK: ...`, `# XXX: ...`, `# BUG: ...`, `# NOTE: ...`*
