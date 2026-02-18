# MashCAD Stabilization Protocol (Verbindlich)

**Version:** 1.0  
**Gueltig ab:** 2026-02-18  
**Status:** VERBINDLICH

## 1. Zweck
Dieses Protokoll ist verbindlich fuer alle Entwicklungsarbeiten, bis die Produkt-Stabilitaet wiederhergestellt ist.  
Ziel ist, dass funktionale Bedienbarkeit (insbesondere 2D/3D Interaktion) nicht erneut durch unkontrollierte Parallel-Aenderungen verloren geht.

## 2. Geltungsbereich
Dieses Protokoll gilt fuer:
- alle KI-Agents
- alle menschlichen Mitwirkenden
- alle Branches ausser `main`
- alle Aenderungen in UX-, Interaktions-, Sketch-, Browser-, Viewport- und Core-Workflows

## 3. Verbindliche Regeln (MUSS)
1. `main` ist die einzige produktive Wahrheit und DARF NICHT direkt bearbeitet werden.
2. Es MUSS einen Integrationsbranch geben (z. B. `stabilize/YYYY-MM-DD`).
3. Jede Arbeit MUSS in einem separaten Task-Branch erfolgen (`task/<owner>/<ticket>`).
4. Pro Task-Paket MUSS ein exklusiver Datei-Scope definiert werden.
5. Ueberschneidende Datei-Scope zwischen zwei parallel laufenden Paketen sind VERBOTEN.
6. Ein Merge in den Integrationsbranch ist nur nach manueller fachlicher Abnahme erlaubt.
7. Test-Erfolg allein ist kein Abnahmekriterium.
8. Vor jeder Integrationswelle MUSS ein Recovery-Tag gesetzt werden (`recovery/<date>-<wave>`).
9. Wenn ein kritischer UX-Fehler gefunden wird, gilt sofortiger Merge-Stopp.
10. Keine neuen Features waehrend einer aktiven Stabilisierung fuer denselben Bereich.

## 4. Rollen und Verantwortung
- **Product Owner (User):**
  - finale fachliche Abnahme (`ABNAHME: OK` / `ABNAHME: NICHT OK`)
  - Freigabe fuer Merge
- **Integrator (Codex):**
  - Scope-Definition, Paket-Zuteilung, Konfliktvermeidung
  - harte Validierung gegen Scope und Regression-Risiko
  - Merge nur bei expliziter Abnahme
- **Implementierer (KI/Human):**
  - Aenderungen nur im freigegebenen Datei-Scope
  - Pflicht-Handoff mit reproduzierbaren Pruefschritten

## 5. Pflicht-Ablauf je Arbeitspaket
1. Ticket erstellen:
   - Problem
   - Reproduktion
   - Soll-Verhalten
   - Dateiscope
2. Branch anlegen (`task/...`).
3. Implementierung nur im Scope.
4. Handoff liefern (Pflichtstruktur, siehe Abschnitt 6).
5. Manuelle Fachabnahme durch Product Owner.
6. Nur bei `ABNAHME: OK`: Integrationsmerge.
7. Kurzer technischer Smoke-Run nach Merge.

## 6. Pflicht-Handoff-Format
Jedes Handoff MUSS enthalten:
1. **Problemursache (Root Cause)** mit betroffenen Methoden/Dateien.
2. **Exakte Aenderungen** (Datei + relevante Zeilen/Funktionen).
3. **Warum der Fix fachlich wirkt** (nicht nur technisch).
4. **Manueller Pruefplan (max 5 Schritte)** fuer den Product Owner.
5. **Risikoanalyse**: moegliche Nebenwirkungen.
6. **Rollback-Referenz**: Commit/Tag fuer sofortige Ruecknahme.

## 7. Kritische Bereiche (Sonderregel)
Fuer folgende Dateien gilt Einzelpaket-Regel (keine Parallel-Aenderung):
- `gui/sketch_editor.py`
- `gui/sketch_handlers.py`
- `sketcher/sketch.py`
- `gui/viewport_pyvista.py`
- `gui/main_window.py`

Diese Dateien duerfen nur in einem aktiven Task gleichzeitig veraendert werden.

## 8. Merge-Stop-Kriterien (hart)
Sobald einer der folgenden Punkte eintritt, ist Merge sofort gesperrt:
- Interaktion nicht reproduzierbar (z. B. Move/Copy/Rotate/Mirror/Scale bricht ab)
- Geometrie veraendert sich unerwartet bei Folgeaktionen
- Datenverlust/Verwerfen von Nutzereingaben
- Crash/Traceback im normalen Bedienfluss
- Scope-Verletzung (Aenderungen ausserhalb erlaubter Dateien)

## 9. Abnahmekriterien (fachlich)
Ein Paket gilt nur als fertig, wenn:
1. Der manuelle Pruefplan ohne Abweichung funktioniert.
2. Das Soll-Verhalten sichtbar erreicht ist.
3. Keine neuen kritischen Seiteneffekte im gleichen Bedienfluss auftreten.
4. Product Owner explizit `ABNAHME: OK` dokumentiert.

## 10. Dokumentationspflicht
Nach jeder Integrationswelle MUSS dokumentiert werden:
- was gemerged wurde
- was bewusst nicht gemerged wurde
- offene Risiken
- naechste priorisierte Schritte

Ohne diese Dokumentation gilt die Welle als unvollstaendig.

## 11. Durchsetzung
Verstoesse gegen dieses Protokoll fuehren zu:
1. sofortigem Merge-Stopp,
2. Ruecknahme der betroffenen Aenderung,
3. Neuplanung mit reduziertem Scope.

---

**Kurzform:**  
Ohne manuellen fachlichen Nachweis kein Merge.  
Ohne exklusiven Dateiscope kein Start.  
Bei kritischem UX-Fehler sofortiger Stop.
