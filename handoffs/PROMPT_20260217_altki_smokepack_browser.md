Du bist KI-X auf Branch `feature/v1-ux-aiB`.

Ziel:
Kleines Recovery-Paket nur fuer Browser-Robustheit, damit wir schnell Qualitaet vergleichen koennen.

Erlaubte Dateien:
- `gui/browser.py`
- `test/test_browser_product_leap_w21.py`

No-Go:
- Kein Edit in `modeling/**`
- Kein Edit in `config/feature_flags.py`
- Keine neuen skips/xfails

Aufgaben:
1. Mache Browser-Metrik/Status-Auswertung typsicher.
   - Keine TypeErrors bei Mock/None/String in numerischen Feldern.
   - Defensive Konvertierung (z. B. safe-int/safe-float Helfer).
2. Stabilisiere Problem-Badge/Filterlogik.
   - `all/errors/warnings/blocked` darf bei unvollstaendigen Daten nicht crashen.
3. Ergaenze gezielte Tests nur dort, wo Verhalten bisher nicht abgesichert ist.
   - Fokus auf Behavior-Proof, nicht nur "Methode existiert".

Pflicht-Validierung:
- `conda run -n cad_env python -m pytest -q test/test_browser_product_leap_w21.py -v`

Abgabe:
- Datei `handoffs/HANDOFF_20260217_altki_smokepack_browser.md`
- Struktur:
  1. Problem
  2. API/Behavior Contract
  3. Impact (Dateien + Kernaenderungen)
  4. Validation (exakte Commands + Ergebniszahlen)
  5. Rest-Risiken
