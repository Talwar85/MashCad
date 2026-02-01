"""
MashCad - Zentrale Versionsverwaltung
=====================================

Alle Versionsinformationen werden hier zentral gepflegt.
Import: from config.version import VERSION, VERSION_STRING, APP_NAME
"""

# Haupt-Versionsnummer (Semantic Versioning: MAJOR.MINOR.PATCH)
VERSION_MAJOR = 0
VERSION_MINOR = 2
VERSION_PATCH = 0

# Release-Typ: "alpha", "beta", "rc1", "" (leer für stable release)
VERSION_SUFFIX = "alpha"

# Build-Datum (optional, kann für CI/CD automatisch gesetzt werden)
BUILD_DATE = "2026-02"

# App-Name
APP_NAME = "MashCad"

# Abgeleitete Strings
VERSION = f"{VERSION_MAJOR}.{VERSION_MINOR}.{VERSION_PATCH}"
VERSION_STRING = f"{VERSION}-{VERSION_SUFFIX}" if VERSION_SUFFIX else VERSION
VERSION_FULL = f"v{VERSION_STRING}"

# Copyright
COPYRIGHT_YEAR = "2024-2026"
COPYRIGHT = f"© {COPYRIGHT_YEAR}"


def get_version_info() -> dict:
    """
    Gibt alle Versionsinformationen als Dictionary zurück.
    Nützlich für Debug-Ausgaben und Crash-Reports.
    """
    return {
        "app_name": APP_NAME,
        "version": VERSION,
        "version_string": VERSION_STRING,
        "version_full": VERSION_FULL,
        "major": VERSION_MAJOR,
        "minor": VERSION_MINOR,
        "patch": VERSION_PATCH,
        "suffix": VERSION_SUFFIX,
        "build_date": BUILD_DATE,
        "copyright": COPYRIGHT,
    }
