"""Recent files manager for MashCAD."""
import json
import os
from pathlib import Path
from typing import List

_MAX_RECENT = 8
_CONFIG_DIR = Path(os.path.expanduser("~")) / ".mashcad"
_RECENT_FILE = _CONFIG_DIR / "recent_files.json"


def get_recent_files() -> List[str]:
    """Returns list of recent file paths (most recent first). Filters out non-existent files."""
    try:
        if _RECENT_FILE.exists():
            data = json.loads(_RECENT_FILE.read_text(encoding="utf-8"))
            files = [f for f in data if os.path.exists(f)]
            return files[:_MAX_RECENT]
    except Exception:
        pass
    return []


def add_recent_file(path: str) -> None:
    """Adds a file path to the recent files list."""
    path = os.path.abspath(path)
    files = get_recent_files()
    if path in files:
        files.remove(path)
    files.insert(0, path)
    files = files[:_MAX_RECENT]
    try:
        _CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        _RECENT_FILE.write_text(json.dumps(files, indent=2), encoding="utf-8")
    except Exception:
        pass
