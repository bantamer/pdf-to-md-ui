"""Languages: every translation complete, every one usable, nothing hard-coded."""

import json
import re
import string

import pytest

import gui
import i18n
from tests.conftest import ROOT, must_be_complete

LANGS = list(i18n.LANGUAGES)
EN = i18n.load_table("en")


def placeholders(text: str) -> set[str]:
    return {name for _, name, _, _ in string.Formatter().parse(text) if name}


def test_every_language_has_a_file_and_every_file_a_language():
    files = {p.stem for p in i18n.LOCALE_DIR.glob("*.json")}
    assert files == set(LANGS)


@pytest.mark.parametrize("code", LANGS)
def test_translation_is_complete(code):
    """Every key, for English and Russian always and for the rest at
    release time (see ALWAYS_COMPLETE in conftest). Keys English does not
    have, empty strings and wrong placeholders are errors in every language
    at any time."""
    table = i18n.load_table(code)

    unknown = sorted(set(table) - set(EN))
    assert not unknown, f"{code}: unknown {unknown}"
    missing = sorted(set(EN) - set(table))
    if must_be_complete(code):
        assert not missing, f"{code}: missing {missing}"
    for key, text in table.items():
        assert text.strip(), f"{code}: {key} is empty"
        assert placeholders(text) == placeholders(EN[key]), (
            f"{code}: {key} has placeholders {placeholders(text)}, "
            f"English has {placeholders(EN[key])}"
        )


@pytest.mark.parametrize("code", LANGS)
def test_files_are_valid_utf8_json(code):
    raw = (i18n.LOCALE_DIR / f"{code}.json").read_bytes()
    json.loads(raw.decode("utf-8"))


def test_no_text_hard_coded_in_the_code():
    """User-facing text belongs in locales/; Cyrillic in the code means a
    string slipped past them."""
    for name in ("gui.py", "converter.py"):
        source = (ROOT / name).read_text(encoding="utf-8")
        hits = [
            line.strip()
            for line in source.splitlines()
            if re.search("[А-Яа-яЁё]", line)
        ]
        assert not hits, f"{name}: {hits[:3]}"


def test_unknown_language_falls_back_to_english():
    assert i18n.set_language("xx") == "en"
    assert i18n.tr("action.convert") == EN["action.convert"]


def test_missing_key_falls_back_to_english(monkeypatch):
    i18n.set_language("pl")
    monkeypatch.delitem(i18n._table, "action.convert")

    assert i18n.tr("action.convert") == EN["action.convert"]


def test_placeholders_are_filled():
    i18n.set_language("ru")
    assert i18n.tr("summary.partial", ok=2, total=5, seconds="3.1") == (
        "Сконвертировано 2 из 5 за 3.1 с"
    )


@pytest.mark.parametrize("code", LANGS)
def test_window_builds_in_every_language(qapp, settings_file, code):
    i18n.set_language(code)
    table = i18n.load_table(code)

    w = gui.open_window()
    try:
        assert w.run_btn.text() == table["action.convert"]
        assert w.format_boxes["pdf"].text() == table["format.pdf"]
        assert w.image_mode.itemText(0) == i18n.tr("images.files")
        assert w.language_actions[code].isChecked()
        assert w._collect_options()["format"] == "markdown"
    finally:
        w.close()
        gui._windows.remove(w)


def test_switching_language_keeps_files_and_options(qapp, settings_file, tmp_path):
    pdf = tmp_path / "doc.pdf"
    pdf.write_bytes(b"%PDF")
    old = gui.open_window()
    old.add_paths([str(pdf)])
    old.timeout_spin.setValue(77)
    old.format_boxes["json"].setChecked(True)

    new = gui.switch_language(old, "fr")
    try:
        assert i18n.current() == "fr"
        assert new.run_btn.text() == i18n.load_table("fr")["action.convert"]
        assert new.inputs == [str(pdf)]
        assert new.timeout_spin.value() == 77
        assert new.format_boxes["json"].isChecked()
        assert gui.app_settings().value("language") == "fr"
        assert old not in gui._windows and new in gui._windows
    finally:
        new.close()
        gui._windows.remove(new)


def test_language_menu_lists_every_language_in_its_own_name(window):
    names = [a.text() for a in window.language_actions.values()]
    assert names == list(i18n.LANGUAGES.values())


@pytest.mark.parametrize(
    "code, close", [("ru", "Закрыть"), ("pl", "Zamknij"), ("fr", "Fermer"),
                    ("es", "Cerrar"), ("it", "Chiudi"), ("en", "Close")]
)
def test_qt_standard_buttons_follow_the_language(qapp, code, close):
    """Yes/No/Cancel/Close come from Qt's own translations, not locales/."""
    from PySide6.QtWidgets import QDialogButtonBox

    i18n.set_language(code)
    box = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)

    assert box.button(QDialogButtonBox.StandardButton.Close).text().replace("&", "") == close
