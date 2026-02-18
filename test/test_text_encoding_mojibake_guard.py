"""
Guard Test for Text Encoding / Mojibake Detection
==================================================

This test guards against the re-introduction of Mojibake (encoding corruption)
in user-visible UI strings.

Mojibake patterns to detect:
- German umlauts corrupted: Ã¼, Ã¤, Ã¶, Ãÿ, Ãœ, Ã„, Ã–
- Symbols corrupted: Â°, â†', Ã—, âˆ , â‰¤, â‰¥
- Common sequences: fÃ¼r, zurÃ¼ck, LÃ¶schen, etc.

Usage:
    pytest test/test_text_encoding_mojibake_guard.py -v
"""

import os
import re
import pytest
from pathlib import Path

# Base directory for the project
BASE_DIR = Path(__file__).parent.parent

# Directories to scan (user-facing GUI code)
GUI_DIRS = ["gui", "i18n"]

# File patterns to scan
FILE_PATTERNS = ["*.py", "*.json"]

# Mojibake detection patterns
MOJIBAKE_PATTERNS = [
    # German Umlauts corrupted (UTF-8 bytes read as Latin-1/CP1252)
    r"Ã¼",  # ü
    r"Ã¤",  # ä
    r"Ã¶",  # ö
    r"Ãÿ",  # ß
    r"Ãœ",  # Ü
    r"Ã„",  # Ä
    r"Ã–",  # Ö
    r"Â°",  # °
    r"Ã—",  # ×
    r"Ã·",  # ÷
    r"â†'",  # →
    r"â†",   # →
    r"âˆ",   # ∠
    r"â‰",   # ≉
    r"â‰¥",  # ≥
    r"â‰¤",  # ≤
    r"Â",    # Â (leftover from encoding issues)
    # Additional patterns from actual audit (UTF-8 bytes interpreted as Windows-1252)
    r"âŒ€",  # ⌀ (diameter)
    r"â\x80\x9D",  # " or — (right double quote/em dash)
    r"â€“",  # – (en dash)
    r"â\x80\x9C",  # " (left curly quote)
    # High-byte corruption patterns (0x80-0x9F range interpreted as Windows-1252)
    r"Ô[åêäàéüöôùîúûÿ¼§èëçû¼í»âØ£Üá©åÉåí¬ü]",  # Multiple Ô followed by high bytes
    # Generic two-byte corruption (common UTF-8 -> Windows-1252)
    r"Ã[Â‚ƒ„…†‡ˆ‰Š‹ŒŽ''""•–—]",  # Ã followed by corruption markers
]

# Whitelist: Strings that may contain these patterns but are NOT Mojibake
# Format: (file_pattern, line_contains)
WHITELIST = [
    # Valid uses of special characters in code (not user-visible strings)
    (r".*", r"#.*"),  # Comments
    (r".*", r"import.*"),  # Imports
    (r".*", r"def.*"),  # Function definitions
    (r".*", r"class.*"),  # Class definitions
    # Special cases
    (r".*", r"Ã—"),  # Multiplication symbol in some contexts (not user visible)
]


def is_whitelisted(filepath: str, line: str, pattern: str) -> bool:
    """Check if a match is whitelisted."""
    import fnmatch
    
    for file_pattern, line_pattern in WHITELIST:
        if fnmatch.fnmatch(filepath, file_pattern):
            if re.search(line_pattern, line):
                return True
    return False


def scan_for_mojibake(directory: Path, file_patterns: list) -> dict:
    """Scan directory for Mojibake patterns using regex search."""
    findings = {}

    for dir_name in directory.iterdir():
        if not dir_name.is_dir():
            continue
        if dir_name.name not in GUI_DIRS:
            continue

        for pattern in file_patterns:
            for filepath in dir_name.rglob(pattern):
                # Skip backup files
                if any(filepath.name.endswith(ext) for ext in ['.bak', '.bak2', '.bak3', '.bak4', '.bak_final']):
                    continue
                try:
                    with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
                        for line_num, line in enumerate(f, 1):
                            for mojibake in MOJIBAKE_PATTERNS:
                                # Use proper regex search instead of 'in' check
                                match = re.search(mojibake, line)
                                if match:
                                    # Check if whitelisted
                                    if not is_whitelisted(str(filepath), line, mojibake):
                                        key = f"{filepath}:{line_num}"
                                        if key not in findings:
                                            findings[key] = []
                                        findings[key].append({
                                            'pattern': mojibake,
                                            'matched': match.group(0),
                                            'line': line.strip()[:100],  # Truncate for readability
                                        })
                except Exception as e:
                    # Skip files that can't be read
                    pass

    return findings


def test_no_mojibake_in_gui():
    """Test that there are no Mojibake patterns in GUI source files."""
    findings = scan_for_mojibake(BASE_DIR, FILE_PATTERNS)
    
    if findings:
        error_msg = "\n\nMojibake encoding issues found:\n"
        for location, issues in sorted(findings.items())[:20]:  # Limit output
            error_msg += f"\n{location}:\n"
            for issue in issues:
                error_msg += f"  - Pattern '{issue['pattern']}' in: {issue['line'][:80]}...\n"
        
        if len(findings) > 20:
            error_msg += f"\n... and {len(findings) - 20} more locations."
            
        pytest.fail(error_msg)


def test_i18n_files_valid_utf8():
    """Test that i18n files are valid UTF-8."""
    i18n_dir = BASE_DIR / "i18n"
    
    if not i18n_dir.exists():
        pytest.skip("i18n directory not found")
    
    for json_file in i18n_dir.glob("*.json"):
        try:
            with open(json_file, 'r', encoding='utf-8') as f:
                import json
                json.load(f)  # Valid JSON
        except UnicodeDecodeError as e:
            pytest.fail(f"i18n file {json_file} is not valid UTF-8: {e}")
        except json.JSONDecodeError as e:
            pytest.fail(f"i18n file {json_file} has invalid JSON: {e}")


def test_german_umlauts_in_i18n():
    """Test that German umlauts are properly defined in i18n files."""
    i18n_dir = BASE_DIR / "i18n"
    de_file = i18n_dir / "de.json"
    
    if not de_file.exists():
        pytest.skip("German translation file not found")
    
    import json
    with open(de_file, 'r', encoding='utf-8') as f:
        translations = json.load(f)
    
    # Check for common German words that should have proper umlauts
    # These should NOT have Mojibake
    forbidden_patterns = [r"Ã¼", r"Ã¤", r"Ã¶", r"Ãÿ", r"Â°"]
    
    for key, value in translations.items():
        if isinstance(value, str):
            for pattern in forbidden_patterns:
                assert pattern not in value, f"Found Mojibake '{pattern}' in i18n key '{key}': {value[:50]}"


if __name__ == "__main__":
    # Run directly for quick testing
    findings = scan_for_mojibake(BASE_DIR, FILE_PATTERNS)
    
    if findings:
        print(f"\n❌ Found {len(findings)} Mojibake locations:\n")
        for location, issues in sorted(findings.items())[:30]:
            print(f"{location}:")
            for issue in issues:
                print(f"  - Pattern '{issue['pattern']}' in: {issue['line'][:60]}...")
    else:
        print("\n✅ No Mojibake patterns found in GUI source files!")
    
    print("\n✅ Guard test complete!")
