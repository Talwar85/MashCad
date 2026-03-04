# MashCad - Architektur-Referenz

> **Version:** 16 | **Stand:** März 2026

## Kernprinzip: CAD-Kernel ist Master

`_build123d_solid` (OCP/OpenCASCADE) → lazy `vtk_mesh/vtk_edges` (PyVista) → Viewport Rendering

**Single Source of Truth.** Kein Mesh-Fallback. Kernel schlägt fehl = Operation schlägt fehl.

## Workflow-Regeln

- Neue Features nur mit Feature Toggle (`config/feature_flag.py`)
- Neue Features mit Logging (Loguru) für schnelles Debuggen
- `to_dict`/`from_dict` und `FeatureCommand` bei jeder neuen Implementation beachten
- Sauberes Speichern/Laden und Undo/Redo muss immer gewährleistet sein
- Bei Unklarheit: **nachfragen**, keine Annahmen treffen
- Abnahmetests erfolgen durch den User

## Tech-Stack

- **CAD-Kernel:** Build123d + OCP (OpenCASCADE) — Master für alle Geometrie
- **Visualization:** PyVista (VTK) — Slave, nur Darstellung
- **GUI:** PySide6 (Qt6)
- **2D-Sketcher:** Custom + Shapely
- **Logging:** Loguru

## Architektur-Regeln

1. **Transaction-Sicherheit:** Jede destruktive Kernel-Op in `BodyTransaction` wrappen
2. **Mesh-Invalidierung:** Nach JEDER Änderung an `_build123d_solid` → `invalidate_mesh()`
3. **Lazy Mesh:** Nie `_regenerate_mesh()` direkt aufrufen — Mesh wird beim Render-Zugriff generiert
4. **Result-Types:** Alle Operationen liefern `OperationResult` mit `SUCCESS/WARNING/EMPTY/ERROR`
5. **Fail-Fast Booleans:** `BooleanEngineV4` — eine Strategie, kein Multi-Strategy-Fallback
6. **OCP Booleans:** `SetFuzzyValue(1e-4)`, `SetRunParallel(True)`, **kein** `SetGlue`
7. **TNP:** Shape-Referenzen via `modeling/tnp_v5/` — History-based → Geometric → Legacy Fallback
8. **Native Geometrie:** Sketch-Elemente (Arcs, Lines, Circles) immer als OCP-native Edges/Wires verarbeiten — nie zu Polygon-Approximationen degradieren. `Build123dProfileDetector` ist der primäre Pfad für Extrusion

## UX-Standards

- Benchmark: Fusion 360, Ziel: besser (flüssiger, weniger Klicks)
- Referenz-UX: Transform V3 (`gui/viewport/transform_mixin_v3.py`)
- Interaktive Features: Live-Preview via VTK (kein Kernel während Drag), Commit on Release
- Fehler sofort und klar an User kommunizieren — keine stillen Failures

## Verbotene Patterns

- **Mesh-Fallbacks** für Boolean/Geometrie-Operationen
- **Direkte Mesh-Zuweisung** (`body.vtk_mesh = ...` ist `@property`!)
- **Silent Failures** (`except: pass`)
- **Quick Fixes** — nie Thresholds senken oder Toleranzen erhöhen um Bugs zu verbergen
- **Multi-Strategy-Fallbacks** ("wenn A nicht klappt, probiere B")
- **`pass`-Platzhalter** in Tests oder Implementierungen
- **Eager Tessellation** in Event-Loops oder Mouse-Move Events
- **Polygon-Approximation** von analytischer Geometrie (Arcs, Circles) — immer OCP-native Wires nutzen

## MANDATORY: Test-Regeln

- Tests IMMER ausführen: `conda run -n cad_env python -m pytest test/<tests>.py -v --tb=short`
- Nur bei GRÜN darf "erfolgreich" gemeldet werden — ROT = Fehler, fixen oder ehrlich melden
- Nie behaupten "Tests bestanden" ohne sie tatsächlich auszuführen
- API-Signaturen VOR Verwendung mit Grep/Read prüfen (nicht raten!)
- Keine Platzhalter-Tests — nur echte Implementierungen mit echten Assertions

## Performance

- Mouse-Move: Kein Tessellieren, kein Logging
- Viewport: Nur bei Änderungen rendern, cached Meshes nutzen
- Tessellator-Cache: Geometry-basierter Hash (nicht Python `id()`)
- Cache-Invalidierung: Per-Shape statt global wenn möglich

## Pre-Commit Checklist

- [ ] Tests ausgeführt und GRÜN
- [ ] API-Signaturen geprüft
- [ ] Keine `pass`-Platzhalter
- [ ] Kernel-Ops in `BodyTransaction`
- [ ] `invalidate_mesh()` nach Kernel-Änderungen
- [ ] Result-Types für alle Operationen
- [ ] Keine Silent Failures / Mesh-Fallbacks

## Entwicklung

```
conda run -n cad_env python -c "..."
```
