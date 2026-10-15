"""User-facing text in several languages.

Every string the window or the log shows lives in locales/<code>.json under a
stable key; code asks for it with tr("key", name=value). English is the
reference: a key missing from another language falls back to it, and the tests
make sure no language misses one. Adding a language is adding a file and a line
in LANGUAGES.
"""

from __future__ import annotations

import json
from pathlib import Path

from PySide6.QtCore import QLocale

# Native names, in the order the language menu shows them.
LANGUAGES = {
    "en": "English",
    "ru": "Русский",
    "pl": "Polski",
    "fr": "Français",
    "es": "Español",
    "it": "Italiano",
}
DEFAULT = "en"

LOCALE_DIR = Path(__file__).resolve().parent / "locales"

_current = DEFAULT
_table: dict[str, str] = {}
_fallback: dict[str, str] = {}


def load_table(code: str) -> dict[str, str]:
    with open(LOCALE_DIR / f"{code}.json", encoding="utf-8") as f:
        return json.load(f)


def set_language(code: str | None) -> str:
    """Switch every later tr() call to `code`; unknown codes mean English."""
    global _current, _table, _fallback
    if code not in LANGUAGES:
        code = DEFAULT
    _fallback = load_table(DEFAULT)
    _table = _fallback if code == DEFAULT else load_table(code)
    _current = code
    return code


def current() -> str:
    return _current


def system_language() -> str:
    """The Windows display language, when it is one we have; else English."""
    for tag in QLocale.system().uiLanguages():
        code = tag.replace("_", "-").split("-")[0].lower()
        if code in LANGUAGES:
            return code
    return DEFAULT


def tr(key: str, **values) -> str:
    if not _fallback:
        set_language(_current)
    text = _table.get(key) or _fallback.get(key) or key
    return text.format(**values) if values else text
