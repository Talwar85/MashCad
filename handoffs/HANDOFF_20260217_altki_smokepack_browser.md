# HANDOFF: Browser Smoke-Pack — Type-Safety & Robustheit

**Datum:** 2026-02-17  
**Branch:** `feature/v1-ux-aiB`  
**Prompt:** `handoffs/PROMPT_20260217_altki_smokepack_browser.md`

---

## 1. Problem

Browser-Metrik-Auswertung (`get_problem_count`, `_update_problem_badge`, `get_filtered_features`, Geometry-Badge) crashte bei:
- `status_details = None` (Mock-Objekte, uninitialisierte Features)
- `status_details = "error string"` (String statt dict)
- `_geometry_delta`-Felder mit `None` oder String-Werten statt numerisch
- `get_problem_count()` zählte inkonsistent zu `_update_problem_badge()` (fehlende `status_class`/`severity`-Prüfung)

## 2. API/Behavior Contract

| Funktion | Garantie |
|---|---|
| `_safe_int(v, default)` | Gibt `int` zurück, nie TypeError/ValueError |
| `_safe_float(v, default)` | Gibt `float` zurück, nie TypeError/ValueError |
| `_safe_details(raw)` | Gibt `dict` zurück — auch bei None/str/Mock |
| `get_problem_count()` | Zählt identisch zu `_update_problem_badge()` (status + status_class + severity) |
| `get_filtered_features()` | Crasht nie bei None/str `status_details` |
| `_update_problem_badge()` | Crasht nie bei None/str `status_details` |
| `_is_problem_item()` | Crasht nie bei fehlerhaftem `item.data()` |
| `_should_show_item()` | Crasht nie bei None/str `status_details` |
| Geometry Badge | `volume_pct`, `faces_delta`, `edges_ok`, `edges_total` werden defensiv konvertiert |

## 3. Impact

### Geänderte Dateien

| Datei | Änderung |
|---|---|
| `gui/browser.py` | +3 Helfer (`_safe_int`, `_safe_float`, `_safe_details`), 8 Stellen gehärtet |
| `test/test_browser_product_leap_w21.py` | +2 Testklassen, +17 Tests (22 → 39 total) |

### Kern-Änderungen in `gui/browser.py`

1. **Neue Helfer** (Zeile ~23-44): `_safe_int`, `_safe_float`, `_safe_details`
2. **`_should_show_item`**: `_safe_details()` + `str()` wrapping
3. **`_is_problem_item`**: try/except für `item.data()`, `_safe_details()` + `str()`
4. **`_add_bodies_to_tree` (status color)**: `_safe_details()`
5. **`_add_bodies_to_tree` (geometry badge)**: `_safe_float`/`_safe_int`, `isinstance(gd, dict)` guard
6. **`_add_bodies_to_tree` (tooltip)**: `_safe_details()`
7. **`_update_problem_badge`**: `_safe_details()` + `str()`, try/except für `get_all_bodies()`
8. **`get_problem_count`**: Konsistent mit Badge (+ status_class/severity), `_safe_details()`
9. **`get_filtered_features`**: `_safe_details()` + `str()`, fallback `mode or 'all'`

## 4. Validation

```
conda run -n cad_env python -m pytest -q test/test_browser_product_leap_w21.py -v
```

**Ergebnis: 39 passed in 9.91s ✅**

Keine neuen skips/xfails. Keine Edits in `modeling/**` oder `config/feature_flags.py`.

## 5. Rest-Risiken

- **`_format_feature_status_tooltip`**: Nutzt noch kein `_safe_details()` intern — aktuell aber unkritisch, da `details` am Eingang mit `isinstance(status_details, dict)` geprüft wird.
- **`_filter_item_recursive`**: `item.child(i)` wird verwendet, aber `item.itemAt()` Fallback (Zeile 209) ist nie erreichbar (QTreeWidgetItem hat kein `itemAt`) — toter Code, kein Crash-Risiko.
- **Thread-Safety**: `_safe_details` etc. sind reine Funktionen ohne State — kein Risiko bei Qt-Signal-Threads.
