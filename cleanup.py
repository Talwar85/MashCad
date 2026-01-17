#!/usr/bin/env python3
"""
Cleanup-Skript für MashCad
Entfernt temporäre Dateien, Cache, und alte Build-Artefakte
"""

import os
import shutil
from pathlib import Path

def cleanup():
    """Entfernt temporäre Dateien und Cache"""
    project_root = Path(__file__).parent

    # Zu löschende Patterns
    patterns_to_delete = [
        "**/__pycache__",
        "**/*.pyc",
        "**/*.pyo",
        "**/*.pyd",
        "**/.pytest_cache",
        "**/.mypy_cache",
        "**/*.egg-info",
        "**/build",
        "**/dist",
        "**/*.spec",
    ]

    deleted_count = 0

    print("🧹 MashCad Cleanup")
    print("=" * 60)

    for pattern in patterns_to_delete:
        for path in project_root.glob(pattern):
            try:
                if path.is_file():
                    path.unlink()
                    print(f"  🗑️  Gelöscht: {path.relative_to(project_root)}")
                    deleted_count += 1
                elif path.is_dir():
                    shutil.rmtree(path)
                    print(f"  📁 Gelöscht: {path.relative_to(project_root)}/")
                    deleted_count += 1
            except Exception as e:
                print(f"  ⚠️  Fehler bei {path}: {e}")

    # Log-Dateien (optional)
    log_files = list(project_root.glob("*.log"))
    if log_files:
        print("\n📝 Log-Dateien gefunden:")
        for log in log_files:
            print(f"  - {log.name}")

        response = input("\nLog-Dateien auch löschen? (y/N): ")
        if response.lower() == 'y':
            for log in log_files:
                try:
                    log.unlink()
                    print(f"  🗑️  Gelöscht: {log.name}")
                    deleted_count += 1
                except Exception as e:
                    print(f"  ⚠️  Fehler: {e}")

    print("\n" + "=" * 60)
    print(f"✅ Cleanup abgeschlossen: {deleted_count} Einträge entfernt")

if __name__ == "__main__":
    cleanup()
