Du bist KI-X auf Branch `feature/v1-ux-aiB`.

Ziel:
Kleines Recovery-Paket fuer Feature-Detail-Robustheit, damit wir schnell Qualität und Abdeckung vergleichen koennen.

Erlaubte Dateien:
- `gui/widgets/feature_detail_panel.py`
- `test/test_feature_detail_panel_w21.py`

No-Go:
- Kein Edit in `modeling/**`
- Kein Edit in `config/feature_flags.py`
- Keine neuen skips/xfails

Aufgaben:
1. Mache Diagnose-/Statusanzeige typsicher.
   - Keine TypeErrors bei Mock/None/String in status_message, code, category, hint, geometry-Feldern.
   - Defensive Konvertierung und robuste Defaults.
2. Stabilisiere Copy-Diagnostics und Edge/TNP-Darstellung.
   - Kein Crash bei partiellen/ungueltigen Referenzdaten.
   - Kritische Fehler muessen visuell priorisiert bleiben.
3. Ergaenze gezielte Behavior-Proof-Tests nur dort, wo reale Luecken bestehen.
   - Keine reinen API-Existenztests.

Pflicht-Validierung:
- `conda run -n cad_env python -m pytest -q test/test_feature_detail_panel_w21.py -v`

Abgabe:
- Datei `handoffs/HANDOFF_20260217_altki_smokepack_feature_detail.md`
- Struktur:
  1. Problem
  2. API/Behavior Contract
  3. Impact (Dateien + Kernaenderungen)
  4. Validation (exakte Commands + Ergebniszahlen)
  5. Rest-Risiken
