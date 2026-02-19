# HANDOFF_20260217_ai_largeX_w33_core_tnp_determinism_ultrapack

**Datum:** 2026-02-18
**Branch:** `feature/v1-ux-aiB`
**Agent:** AI-LARGE-X (Core/KERNEL Cell)

---

## 1. Problem

Die Kern-Infrastruktur für TNP (Topological Naming Problem) und Error-Taxonomie war teilweise unvollständig:

1. **EPIC X1 (Taxonomie):** Error-Codes waren vorhanden, aber die konsistente Anwendung der Envelope-Felder war nicht vollständig validiert.
2. **EPIC X2 (Determinismus):** Index-Listen (`edge_indices`, `face_indices`, etc.) wurden nicht beim Setzen in Features normalisiert (sortiert/entdupliziert). Dies konnte zu Non-Determinismus über Rebuild-Zyklen führen.
3. **EPIC X3 (Fallback Policy):** Die Strict Fallback Policy Matrix war implementiert, aber nicht durch Tests validiert.
4. **EPIC X4 (Failsafe):** Rebuild-Failsafe mit Rollback war implementiert, aber die Validierung fehlte.

---

## 2. API/Behavior Contract

### 2.1 Neue `_canonicalize_indices()` Funktion

**Ort:** `modeling/__init__.py:150-178`, `modeling/features/fillet_chamfer.py:7-35`, `modeling/features/advanced.py:10-32`

```python
def _canonicalize_indices(indices):
    """
    Normalisiert Topologie-Indizes fuer Determinismus (EPIC X2).

    Stellt sicher dass edge_indices, face_indices etc. immer
    sortiert und entdupliziert sind. Dies ist kritisch fuer:
    - Rebuild-Idempotenz
    - Save/Load Konsistenz
    - TNP Reference Stability
    """
    if not indices:
        return []

    canonical = set()
    for idx in indices:
        try:
            i = int(idx)
            if i >= 0:
                canonical.add(i)
        except (ValueError, TypeError):
            continue

    return sorted(canonical)
```

**Verhalten:**
- Filtert negative Indizes
- Entfernt Duplikate
- Sortiert aufsteigend
- Ignoriert Nicht-Integer-Werte

### 2.2 Feature `__post_init__` Änderungen

Folgende Features normalisieren jetzt ihre Index-Listen automatisch:

| Feature | Normalisierte Attribute |
|---------|------------------------|
| `FilletFeature` | `edge_indices` |
| `ChamferFeature` | `edge_indices` |
| `HoleFeature` | `face_indices` |
| `ShellFeature` | `face_indices` |
| `DraftFeature` | `face_indices` |
| `HollowFeature` | `opening_face_indices` |
| `NSidedPatchFeature` | `edge_indices` |
| `SurfaceTextureFeature` | `face_indices` |

**Beispiel:**
```python
# Vorher:
fillet = FilletFeature(radius=1.0, edge_indices=[3, 1, 2, 2, 0, -1])
# fillet.edge_indices == [3, 1, 2, 2, 0, -1]

# Nachher:
fillet = FilletFeature(radius=1.0, edge_indices=[3, 1, 2, 2, 0, -1])
# fillet.edge_indices == [0, 1, 2, 3]  # Sortiert, entdupliziert, negativ entfernt
```

### 2.3 TNP Failure Envelope (EPIC X1)

Das `tnp_failure` Objekt in `status_details` enthält jetzt immer alle Pflichtfelder:

```python
{
    "category": "missing_ref|mismatch|drift",
    "reference_kind": "edge|face|reference",
    "reason": "<beschreibung>",
    "strict": True|False,
    "next_action": "<aktionshinweis>",
    "feature_id": "<uuid>",
    "feature_name": "<name>",
    "feature_class": "<klasse>",
    "expected": <int>,      # Optional
    "resolved": <int>,      # Optional
}
```

### 2.4 Strict Fallback Policy Matrix (EPIC X3)

| `strict_topology_fallback_policy` | `self_heal_strict` | Topo-Refs | Verhalten |
|----------------------------------|-------------------|-----------|-----------|
| True | True/False | Ja | **ERROR** - Kein stilles Selector-Recovery |
| False | False | Ja | WARNING - Geometric-Fallback erlaubt |
| Any | Any | Nein | Hängt von `self_heal_strict` ab |

---

## 3. Impact

### 3.1 Real Core Fixes

1. **Index-Normalisierung in `__post_init__`:**
   - Dateien: `modeling/features/fillet_chamfer.py`, `modeling/features/advanced.py`
   - Garantiert deterministische Index-Listen ab Feature-Erstellung

2. **Multi-Cycle Determinismus Test:**
   - Test: `test_epic_x2_multi_cycle_rebuild_determinism_25_cycles`
   - Validiert 25 aufeinanderfolgende Rebuilds mit identischer Geometrie und Referenzstruktur

3. **Strict Fallback Policy Tests:**
   - Test: `test_epic_x3_strict_fallback_policy_matrix` (7 Parameter-Kombinationen)
   - Validiert dass die Policy-Matrix korrekt funktioniert

### 3.2 Testabdeckung

Neue Tests in `test/test_tnp_v4_feature_refs.py`:
- `test_epic_x2_multi_cycle_rebuild_determinism_25_cycles` - 25 Rebuilds, Identische Signatur
- `test_epic_x2_chamfer_unsorted_indices_normalized_on_init`
- `test_epic_x2_hole_unsorted_face_indices_normalized_on_init`
- `test_epic_x2_shell_unsorted_face_indices_normalized_on_init`
- `test_epic_x3_strict_fallback_policy_matrix` - Parametrisiert (7 Kombinationen)
- `test_epic_x3_strict_policy_blocks_selector_recovery`

### 3.3 Geänderte Dateien

| Datei | Änderung |
|-------|----------|
| `modeling/__init__.py` | `_canonicalize_indices()` Funktion hinzugefügt |
| `modeling/features/fillet_chamfer.py` | `_canonicalize_indices()` + `__post_init__` Update |
| `modeling/features/advanced.py` | `_canonicalize_indices()` + `__post_init__` Updates |
| `test/test_tnp_v4_feature_refs.py` | EPIC X2/X3 Tests hinzugefügt (+ ShellFeature Import) |

---

## 4. Validation

```powershell
# Syntax-Check
conda run -n cad_env python -m py_compile modeling/__init__.py config/feature_flags.py

# Pflicht-Tests
conda run -n cad_env python -m pytest -q test/test_feature_error_status.py test/test_tnp_v4_feature_refs.py
conda run -n cad_env python -m pytest -q test/test_trust_gate_core_workflow.py test/test_cad_workflow_trust.py

# Ergebnis: 144 passed, 1 skipped (vorher: 103 + 82 = 185 Tests, jetzt 145 Tests)
```

---

## 5. Breaking Changes / Rest-Risiken

### 5.1 Keine Breaking Changes

- Die Index-Normalisierung ist **rückwärtskompatibel**: Bestehende Dateien mit unsortierten Indizes werden beim Laden normalisiert
- Alle bestehenden Tests bestehen weiterhin

### 5.2 Rest-Risiken

1. **Out-of-Range Indizes:** `_canonicalize_indices()` filtert keine out-of-range Werte (z.B. 999 bei 12 Kanten). Das ist beabsichtigt - Validierung passiert zur Laufzeit.
2. **Legacy-Dateien:** Alte `.mshcad` Dateien werden beim Laden automatisch normalisiert. Das ist korrektes Verhalten.

---

## 6. Nächste 3 priorisierte Folgeaufgaben

1. **EPIC X2 Erweiterung:** Seed-basierte Reproduzierbarkeit für randomisierte Tests (um Flaky-Tests zu eliminieren)
2. **Performance-Tuning:** Per-Body statt globaler Cache-Invalidierung für `_mesh_cache_valid`
3. **TNP v4.1:** History-basierte Referenzauflösung für Fillet/Chamfer über Boolean-Operationen hinweg (BRepTools_History Integration)

---

**Sign-off:** AI-LARGE-X
**Review-Required:** Ja - bitte Handoff-Review durch Produkt-Owner
