# HANDOFF: W26 Browser-/Diagnostik-/Recovery-Surface

**Datum:** 2026-02-17  
**Branch:** `feature/v1-ux-aiB`  
**Prompt:** `handoffs/PROMPT_20260217_ai_largeF_w26_browser_diagnostics_recovery_surface.md`  
**Implementiert von:** AI-LARGE-F

---

## 1. Problem

Der Browser-/Diagnostik-/Recovery-Bereich benötigte einen großen sichtbaren Produkt-Sprung:

1. **Browser Navigation:** Keine problemorientierte Navigation, keine Priorisierung (CRITICAL > BLOCKED > ERROR > WARNING)
2. **Feature Detail Panel:** Fehlende Recovery-Aktionen für Error-Codes, schwache Copy-Diagnostics
3. **Severity Alignment:** Inkonsistente Darstellung zwischen Operation Summary, Notifications und Browser
4. **Testabdeckung:** Fehlende Assertions für neue W26-Features

---

## 2. API/Behavior Contract

### Paket F1: Browser Problem Workflow v2

| Feature | Behavior |
|---------|----------|
| `_get_problem_priority(item)` | Gibt Priorität 0-3 zurück (CRITICAL=0, BLOCKED=1, ERROR=2, WARNING=3) |
| `navigate_to_next_critical_problem()` | Springt zum nächsten Problem nach Priorität |
| `navigate_to_prev_critical_problem()` | Springt zum vorherigen Problem nach Priorität |
| `select_all_problem_items()` | Selektiert alle Problem-Features (Ctrl+A) |
| `get_selected_problem_features()` | Gibt List[(feature, body)] von Problem-Features zurück |
| `batch_retry_selected()` | Emittiert `batch_retry_rebuild` Signal |
| `batch_open_diagnostics()` | Emittiert `batch_open_diagnostics` Signal |
| `batch_isolate_selected_bodies()` | Emittiert `batch_isolate_bodies` Signal |

**Neue Keyboard Shortcuts:**
- `Ctrl+Shift+Down`: Nächstes kritisches Problem
- `Ctrl+Shift+Up`: Vorheriges kritisches Problem
- `Ctrl+A`: Alle Problem-Features selektieren

**Neue Batch-Signale:**
```python
batch_retry_rebuild = Signal(list)     # List[(feature, body)]
batch_open_diagnostics = Signal(list)  # List[(feature, body)]
batch_isolate_bodies = Signal(list)    # List[body]
```

### Paket F2: Feature Detail Recovery Actions

| Error-Code | Recovery-Aktionen |
|------------|-------------------|
| `tnp_ref_missing` | "Referenz neu wählen", "Feature editieren", "Dependencies prüfen" |
| `tnp_ref_mismatch` | "Feature editieren", "Konflikt isolieren", "Rebuild wiederholen" |
| `tnp_ref_drift` | "Drift akzeptieren", "Feature editieren" |
| `rebuild_finalize_failed` | "Rebuild wiederholen", "Feature editieren", "Feature löschen" |
| `ocp_api_unavailable` | "OCP prüfen", "Dependencies prüfen", "Fallback verwenden" |

**Neue Signale:**
```python
recovery_action_requested = Signal(str, object)  # (action, feature)
edit_feature_requested = Signal(object)
rebuild_feature_requested = Signal(object)
delete_feature_requested = Signal(object)
```

**Neue Recovery-Buttons:**
- `_btn_reselect_ref`: "🔄 Referenz neu wählen"
- `_btn_edit_feature`: "✏️ Feature editieren"
- `_btn_rebuild`: "🔄 Rebuild"
- `_btn_accept_drift`: "✓ Drift akzeptieren"
- `_btn_check_deps`: "🔍 Dependencies prüfen"

**Verbesserte Copy-Diagnostics:**
- Strukturierte Felder: `[FEATURE]`, `[STATUS]`, `[TNP FAILURE]`, `[RECOVERY OPTIONS]`
- Recovery-Vorschläge pro Error-Code
- Zeitstempel und vollständige Metadaten

### Paket F3: Operation Summary + Notification Alignment

**SeverityLevel Enum:**
```python
CRITICAL = "critical"      # System-kritisch
BLOCKED = "blocked"        # Blockiert weitere Arbeit
ERROR = "error"            # Fehler, nicht blockierend
WARNING = "warning"        # Warnung, Arbeit möglich
SUCCESS = "success"        # Erfolgreich
INFO = "info"              # Information
```

**Severity-Mapping:**
| Input | Output |
|-------|--------|
| `status_class="CRITICAL"` oder `severity="critical"` | `SeverityLevel.CRITICAL` |
| `status_class="BLOCKED"` oder `severity="blocked"` | `SeverityLevel.BLOCKED` |
| `status_class="ERROR"` oder `severity="error"` | `SeverityLevel.ERROR` |
| `status_class="WARNING_RECOVERABLE"` oder `severity="warning"` | `SeverityLevel.WARNING` |

**Konsistente Darstellung:**
- Alle Komponenten verwenden `map_to_severity()` für einheitliches Mapping
- Recoverable-Warnings zeigen "💡 Weiterarbeiten möglich"
- Severity-basierte Anzeigedauer (CRITICAL: 15s, WARNING: 8s, SUCCESS: 5s)

---

## 3. Impact

### Geänderte Dateien

| Datei | Änderung |
|-------|----------|
| `gui/browser.py` | +180 Zeilen: Problem-First Navigation, Batch-Aktionen, Multi-Select, Refresh-Stabilität |
| `gui/widgets/feature_detail_panel.py` | +150 Zeilen: Recovery-Actions, verbesserte Copy-Diagnostics, Error-Code-Mapping |
| `gui/widgets/operation_summary.py` | +80 Zeilen: SeverityLevel Enum, konsistentes Mapping, recoverable-Hinweise |
| `gui/managers/notification_manager.py` | +20 Zeilen: BLOCKED in Priorität, konsistentes Severity-Mapping |

### Neue Testdateien

| Datei | Tests |
|-------|-------|
| `test/test_browser_product_leap_w26.py` | 12 Tests für Problem-First Navigation, Batch-Aktionen |
| `test/test_feature_detail_recovery_w26.py` | 8 Tests für Recovery-Actions, Error-Code-Mapping |
| `test/test_operation_summary_notification_alignment_w26.py` | 7 Tests für Severity-Alignment |

**Gesamt: 143 Tests (116 W21 + 27 W26), alle ✅ passing**

---

## 4. Validation

### Pflicht-Validierung

```powershell
# Syntax-Check
conda run -n cad_env python -m py_compile gui/browser.py gui/widgets/feature_detail_panel.py gui/widgets/operation_summary.py gui/managers/notification_manager.py

# W21 Tests
conda run -n cad_env python -m pytest -q test/test_browser_product_leap_w21.py -v
# 39 passed ✅

conda run -n cad_env python -m pytest -q test/test_feature_detail_panel_w21.py -v
# 31 passed ✅

conda run -n cad_env python -m pytest -q test/test_operation_summary_w21.py test/test_notification_manager_w21.py -v
# 46 passed ✅

# W26 Tests
conda run -n cad_env python -m pytest -q test/test_browser_product_leap_w26.py test/test_feature_detail_recovery_w26.py test/test_operation_summary_notification_alignment_w26.py -v
# 27 passed ✅
```

**Gesamtergebnis: 143 passed ✅**

---

## 5. Breaking Changes / Rest-Risiken

### Keine Breaking Changes
- Alle Änderungen sind Erweiterungen bestehender APIs
- W21-Tests bestehen ohne Modifikation
- Neue Signale sind optional (keine Pflicht-Handler)

### Bekannte Limitierungen
1. **Recovery-Actions**: UI-seitig implementiert, externe Handler müssen Signale verbinden
2. **Batch-Aktionen**: Methoden emittieren Signale, MainWindow muss Handler implementieren
3. **Scroll-Position**: Wird bei Refresh wiederhergestellt, aber nicht bei Filter-Änderung

### Empfohlene Folgeaufgaben
1. MainWindow: Handler für `batch_retry_rebuild`, `batch_open_diagnostics`, `batch_isolate_bodies`
2. MainWindow: Handler für `recovery_action_requested`, `edit_feature_requested`, `rebuild_feature_requested`
3. Integration: Keyboard-Shortcuts in MainWindow-Shortcut-Tabelle aufnehmen
4. UX: Toast-Notification bei erfolgreicher Recovery-Aktion

---

## 6. Nächste 5 priorisierte Folgeaufgaben

1. **MainWindow Integration** (Prio 1)
   - Signale `batch_*` mit Handler verbinden
   - Recovery-Aktionen mit Backend verbinden

2. **Keyboard Shortcuts Dokumentation** (Prio 2)
   - Alle neuen Shortcuts in Hilfe-Menü aufnehmen
   - Shortcut-Cheatsheet aktualisieren

3. **Recovery Action Backend** (Prio 3)
   - "Referenz neu wählen" mit Sketch-Editor verbinden
   - "Drift akzeptieren" persistiert Status-Reset

4. **Performance-Monitoring** (Prio 4)
   - Refresh-Zeit bei >200 Features messen
   - Memory-Leak-Check bei häufigem Refresh

5. **User Feedback** (Prio 5)
   - Recovery-Erfolg mit Toast bestätigen
   - Batch-Aktionen Fortschrittsanzeige

---

## Commit-Liste

```
(Keine Git commits durchgeführt - nur Dateiänderungen)
```

---

## UX-Delta: "vorher" vs "nachher"

| # | Vorher | Nachher |
|---|--------|---------|
| 1 | Problem-Navigation ohne Priorisierung | CRITICAL > BLOCKED > ERROR > WARNING Priorisierung |
| 2 | Nur einzelne Features auswählbar | Multi-Select mit Ctrl+A für alle Problem-Features |
| 3 | Keine Batch-Aktionen | Retry Rebuild, Open Diagnostics, Isolate Body |
| 4 | Generische Fehlermeldungen | Error-Code-spezifische Recovery-Aktionen |
| 5 | Einfache Copy-Diagnostics | Strukturierter Report mit Recovery-Vorschlägen |
| 6 | Inkonsistente Severity-Darstellung | Einheitliche Severity-Levels über alle Komponenten |
| 7 | Kein "Weiterarbeiten möglich" Hinweis | Recoverable-Warnings zeigen klaren Hinweis |
| 8 | Flackern bei Refresh | Scroll-Position Erhaltung, Updates-Blocker |
| 9 | Keine Keyboard-Shortcuts für kritische Probleme | Ctrl+Shift+Down/Up für kritische Probleme |
| 10 | Keine visuelle Priorisierung im Browser | Problem-First Navigation mit Farb-Codierung |

---

**Ende des Handoffs**
