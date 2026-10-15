"""The menu bar: File, Settings, Help, and the About dialog."""

import pytest
from PySide6.QtCore import QUrl

import gui
import i18n
from version import __version__


def menu_titles(window):
    return [a.text() for a in window.findChild(gui.QMenuBar).actions()]


def test_three_menus_in_windows_order(window):
    assert menu_titles(window) == ["&File", "&Settings", "&Help"]


def test_menus_follow_the_language(qapp, settings_file):
    i18n.set_language("ru")
    w = gui.open_window()
    try:
        assert menu_titles(w) == ["&Файл", "&Настройки", "&Справка"]
    finally:
        w.close()
        gui._windows.remove(w)


def test_standard_shortcuts(window):
    assert window.act_add_files.shortcut().toString() == "Ctrl+O"
    assert window.act_convert.text().endswith("	Ctrl+Enter")
    assert window.act_stop.shortcut().toString() == "Esc"
    assert window.act_guide.shortcut().toString() == "F1"


def test_commands_follow_the_state(window, tmp_path):
    pdf = tmp_path / "a.pdf"
    pdf.write_bytes(b"%PDF")

    assert not window.act_convert.isEnabled()
    assert not window.act_clear.isEnabled()
    assert not window.act_stop.isEnabled()
    assert not window.act_open_output.isEnabled()

    window.add_paths([str(pdf)])
    assert window.act_convert.isEnabled() and window.act_clear.isEnabled()

    window.thread = object()  # a run in progress
    window._set_busy(True, 1)
    assert not window.act_convert.isEnabled()
    assert window.act_stop.isEnabled()
    assert not window.language_menu.isEnabled()
    assert not window.act_reset.isEnabled()

    window.thread = None
    window._set_busy(False)
    window.output_dir = str(tmp_path)
    window._sync_actions()
    assert window.act_convert.isEnabled() and not window.act_stop.isEnabled()
    assert window.act_open_output.isEnabled()


def test_clear_from_the_menu(window, tmp_path):
    pdf = tmp_path / "a.pdf"
    pdf.write_bytes(b"%PDF")
    window.add_paths([str(pdf)])

    window.act_clear.trigger()

    assert window.inputs == [] and not window.act_clear.isEnabled()


def test_language_from_the_menu(qapp, settings_file):
    w = gui.open_window()
    w.language_actions["it"].trigger()

    new = gui._windows[-1]
    try:
        assert new is not w and i18n.current() == "it"
        assert new.language_actions["it"].isChecked()
        assert menu_titles(new)[0] == "&File"  # Italian keeps "File"
        assert new.run_btn.text() == "Converti"
    finally:
        new.close()
        gui._windows.remove(new)


def test_theme_modes(window, settings_file):
    window._set_theme("dark")
    assert window.dark and gui.app_settings().value("dark") in (True, "true")
    assert window.theme_actions["dark"].isChecked()

    window._set_theme("light")
    assert not window.dark and window.theme_actions["light"].isChecked()

    window._set_theme("system")
    assert gui.app_settings().value("dark") is None
    assert window.dark == gui._system_prefers_dark()


def test_log_menu_and_button_stay_in_step(window):
    window.act_show_log.trigger()
    assert window.log_btn.isChecked() and not window.log_card.isHidden()

    height = window.height()
    window._toggle_log(True)  # already shown: nothing to do
    assert window.height() == height

    window.log_btn.click()
    assert not window.act_show_log.isChecked() and window.log_card.isHidden()


def test_reset_forgets_settings_but_keeps_files(qapp, settings_file, tmp_path):
    pdf = tmp_path / "a.pdf"
    pdf.write_bytes(b"%PDF")
    gui.app_settings().setValue("language", "fr")
    i18n.set_language("fr")
    w = gui.open_window()
    w.add_paths([str(pdf)])
    w.timeout_spin.setValue(99)
    w.output_edit.setText(str(tmp_path))
    w._remember_output_dir()
    w._set_theme("dark")
    w._save_settings()

    new = gui.reset_settings(w)
    try:
        settings = gui.app_settings()
        assert settings.value("options/timeout") is None
        assert settings.value("output_dir") is None
        assert settings.value("dark") is None
        assert settings.value("language") is None
        assert new.timeout_spin.value() == 30
        assert new.output_edit.text() == ""
        assert new.inputs == [str(pdf)]
        assert i18n.current() == i18n.system_language()
    finally:
        new.close()
        gui._windows.remove(new)


@pytest.mark.parametrize(
    "lang, readme", [("ru", "README.ru.md"), ("en", "README.md"), ("pl", "README.md")]
)
def test_user_guide_opens_the_readme_in_the_right_language(
    window, monkeypatch, lang, readme
):
    opened = []
    monkeypatch.setattr(gui.QDesktopServices, "openUrl", lambda url: opened.append(url))
    monkeypatch.setattr(i18n, "_current", lang)

    window.act_guide.trigger()

    assert opened == [QUrl(f"{gui.REPO_URL}/blob/main/{readme}")]


def test_about_names_version_licence_and_authors(window):
    dialog = gui.AboutDialog(window)
    text = dialog.text.text()

    assert __version__ in text
    assert gui.odl_version() in text
    assert "LICENSE" in text and "THIRD_PARTY_NOTICES.md" in text
    assert "bantamer" in text and "k1llrouz" in text
    assert dialog.text.openExternalLinks()


def test_version_is_in_the_log(window):
    window._check_java()
    assert f"{gui.APP_NAME} {__version__}" in window.log_view.toPlainText()


def test_ctrl_enter_converts_only_when_convert_is_available(window, tmp_path, monkeypatch):
    from PySide6.QtGui import QShortcut

    started = []
    monkeypatch.setattr(window, "start", lambda: started.append(1))
    keys = {s.key().toString(): s for s in window.findChildren(QShortcut)}
    assert {"Ctrl+Return", "Ctrl+Enter"} <= set(keys)

    keys["Ctrl+Return"].activated.emit()
    assert started == []  # nothing to convert yet

    pdf = tmp_path / "a.pdf"
    pdf.write_bytes(b"%PDF")
    window.add_paths([str(pdf)])
    keys["Ctrl+Enter"].activated.emit()
    assert started == [1]
