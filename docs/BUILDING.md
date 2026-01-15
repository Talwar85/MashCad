# Building MashCAD Executables

Diese Anleitung beschreibt, wie du Standalone-Executables von MashCAD für Windows, macOS und Linux erstellen kannst.

## Übersicht

MashCAD verwendet [PyInstaller](https://pyinstaller.org/) um Python-Anwendungen in eigenständige Executables zu packen. Dies ermöglicht die Verteilung der Anwendung ohne dass Benutzer Python oder die Abhängigkeiten installieren müssen.

## Voraussetzungen

- Python 3.10 oder höher
- Alle Abhängigkeiten aus `requirements.txt` installiert
- PyInstaller: `pip install pyinstaller`

## Lokales Building

### Option 1: Build-Skripte verwenden (Empfohlen)

#### Windows
```cmd
build_local.bat
```

#### macOS / Linux
```bash
chmod +x build_local.sh
./build_local.sh
```

### Option 2: Manuelles Building

```bash
# Abhängigkeiten installieren
pip install pyinstaller
pip install -r requirements.txt

# Build ausführen
pyinstaller MashCAD.spec

# Executable finden
# Windows: dist/MashCAD/MashCAD.exe
# macOS: dist/MashCAD.app
# Linux: dist/MashCAD/MashCAD
```

## Automatisches Building mit GitHub Actions

Das Repository enthält einen GitHub Actions Workflow, der automatisch Executables für alle Plattformen erstellt.

### Workflow triggern

#### 1. Bei Tag-Push (Empfohlen für Releases)
```bash
git tag v2.5.0
git push origin v2.5.0
```

Dies erstellt automatisch einen GitHub Release mit den Executables für:
- Windows (x64)
- macOS (Universal)
- Linux (x86_64)

#### 2. Manuell über GitHub UI
1. Gehe zu "Actions" tab im Repository
2. Wähle "Build Cross-Platform Executables"
3. Klicke "Run workflow"
4. Die Build-Artifacts werden als Downloads verfügbar sein

## Ausgabe-Dateien

Nach erfolgreichem Build findest du:

### Windows
- **Ordner:** `dist/MashCAD/`
- **Executable:** `MashCAD.exe`
- **Ausführen:** Doppelklick auf `MashCAD.exe`

### macOS
- **App Bundle:** `dist/MashCAD.app`
- **Ausführen:** `open dist/MashCAD.app` oder Doppelklick im Finder

### Linux
- **Ordner:** `dist/MashCAD/`
- **Executable:** `MashCAD`
- **Ausführen:**
  ```bash
  cd dist/MashCAD
  ./MashCAD
  ```

## Distribution

### Archive erstellen

#### Windows
```cmd
cd dist
tar -czf MashCAD-Windows-x64.zip MashCAD
```

#### macOS
```bash
cd dist
tar -czf MashCAD-macOS-universal.tar.gz MashCAD.app
```

#### Linux
```bash
cd dist
tar -czf MashCAD-Linux-x86_64.tar.gz MashCAD
```

## Konfiguration

Die Build-Konfiguration befindet sich in `MashCAD.spec`. Wichtige Einstellungen:

### Icon setzen
```python
# In MashCAD.spec
exe = EXE(
    ...
    icon='path/to/icon.ico',  # Windows
    ...
)

# Für macOS
app = BUNDLE(
    ...
    icon='path/to/icon.icns',  # macOS
    ...
)
```

### Console-Modus (für Debugging)
```python
exe = EXE(
    ...
    console=True,  # Zeigt ein Konsolen-Fenster für Debug-Output
    ...
)
```

### Hidden Imports hinzufügen
Wenn Module nicht automatisch erkannt werden:
```python
hiddenimports = [
    'dein.modul.hier',
]
```

## Troubleshooting

### Problem: "ModuleNotFoundError" beim Ausführen
**Lösung:** Füge das fehlende Modul zu `hiddenimports` in `MashCAD.spec` hinzu

### Problem: Große Executable-Größe
**Lösungen:**
- UPX Compression ist bereits aktiviert
- Unnötige Module zu `excludes` hinzufügen
- Große Datenfiles extern lagern

### Problem: Executable startet nicht
**Debugging:**
1. Setze `console=True` in `MashCAD.spec`
2. Rebuild mit `pyinstaller MashCAD.spec`
3. Führe aus und überprüfe die Konsolen-Output

### Problem: OpenGL/VTK Fehler
**Lösung:** Stelle sicher, dass die Grafiktreiber aktuell sind. Für Linux:
```bash
sudo apt-get install libgl1-mesa-glx libegl1-mesa
```

## Plattform-spezifische Hinweise

### Windows
- Antivirus-Software kann falsch-positive Warnungen zeigen
- Signieren der Executable wird empfohlen für Distribution
- Getestet auf Windows 10/11 x64

### macOS
- App muss eventuell in den Sicherheitseinstellungen erlaubt werden
- Für Distribution: Code Signing und Notarisierung erforderlich
- Getestet auf macOS 12 (Monterey) und höher

### Linux
- Benötigt Qt6-Bibliotheken auf dem Zielsystem
- Getestet auf Ubuntu 20.04+ und Debian-basierten Distributionen
- Für andere Distributionen eventuell zusätzliche Libraries nötig

## Weitere Ressourcen

- [PyInstaller Dokumentation](https://pyinstaller.org/en/stable/)
- [PyInstaller Spec Files](https://pyinstaller.org/en/stable/spec-files.html)
- [GitHub Actions Dokumentation](https://docs.github.com/en/actions)

## Lizenz

Die Build-Skripte und Konfigurationen sind Teil von MashCAD und unter der MIT-Lizenz verfügbar.
