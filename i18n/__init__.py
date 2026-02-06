"""
LiteCAD - Internationalization (i18n) System
Zukunftsfähiges Übersetzungssystem mit JSON-Dateien

Verwendung:
    from i18n import tr, set_language, get_language
    
    # Sprache setzen
    set_language('de')  # oder 'en'
    
    # Text übersetzen
    label = tr("File")  # -> "Datei" (in Deutsch)
    
    # Mit Formatierung
    msg = tr("Saved: {path}").format(path="/home/file.txt")
"""

import json
import os
from typing import Dict, Optional
from loguru import logger
from loguru import logger

# Globale Variablen
_current_language = 'de'  # Default: Deutsch
_translations: Dict[str, Dict[str, str]] = {}
_fallback_language = 'en'

# Pfad zu den Übersetzungsdateien
_i18n_dir = os.path.dirname(os.path.abspath(__file__))
_config_file = os.path.join(os.path.dirname(_i18n_dir), 'config.json')


def _load_config():
    """Lädt die gespeicherte Spracheinstellung"""
    global _current_language
    try:
        if os.path.exists(_config_file):
            with open(_config_file, 'r', encoding='utf-8') as f:
                config = json.load(f)
                _current_language = config.get('language', 'de')
    except Exception as e:
        logger.debug(f"[i18n] Fehler: {e}")


def _save_config():
    """Speichert die Spracheinstellung"""
    try:
        config = {'language': _current_language}
        with open(_config_file, 'w', encoding='utf-8') as f:
            json.dump(config, f)
    except Exception as e:
        logger.debug(f"[i18n] Fehler: {e}")


def load_language(lang: str) -> bool:
    """Lädt eine Sprachdatei"""
    global _translations
    
    filepath = os.path.join(_i18n_dir, f'{lang}.json')
    
    if os.path.exists(filepath):
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                _translations[lang] = json.load(f)
            return True
        except (json.JSONDecodeError, IOError) as e:
            logger.warning(f"Error loading language file {filepath}: {e}")
            return False
    return False


def set_language(lang: str) -> bool:
    """Setzt die aktuelle Sprache und speichert sie"""
    global _current_language
    
    # Lade Sprache wenn nicht bereits geladen
    if lang not in _translations:
        if not load_language(lang):
            logger.info(f"Language '{lang}' not found, using fallback '{_fallback_language}'")
            return False
    
    _current_language = lang
    _save_config()  # Speichern!
    return True


def get_language() -> str:
    """Gibt die aktuelle Sprache zurück"""
    return _current_language


def get_available_languages() -> list:
    """Gibt alle verfügbaren Sprachen zurück"""
    languages = []
    for filename in os.listdir(_i18n_dir):
        if filename.endswith('.json'):
            lang = filename[:-5]  # Remove .json
            languages.append(lang)
    return sorted(languages)


def tr(text: str, context: str = None) -> str:
    """
    Übersetzt einen Text.
    
    Args:
        text: Der zu übersetzende Text (in Englisch als Schlüssel)
        context: Optionaler Kontext für mehrdeutige Texte
        
    Returns:
        Übersetzter Text oder Original wenn keine Übersetzung gefunden
    """
    # Wenn Englisch, gib Original zurück
    if _current_language == 'en':
        return text
    
    # Versuche Übersetzung zu finden
    if _current_language in _translations:
        trans = _translations[_current_language]
        
        # Mit Kontext versuchen
        if context:
            key = f"{context}::{text}"
            if key in trans:
                return trans[key]
        
        # Ohne Kontext
        if text in trans:
            return trans[text]
    
    # Fallback: Original zurückgeben
    return text


# Alias für kürzere Schreibweise
_ = tr


# Beim Import: Config laden und Sprachen laden
_load_config()
load_language('en')
load_language('de')
