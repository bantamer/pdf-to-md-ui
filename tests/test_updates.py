"""The update check and the title bar colour."""

import io
import json
import time

import pytest
from PySide6.QtCore import QEvent, Qt, QUrl
from PySide6.QtWidgets import QApplication

import gui
import updates
from version import __version__


def pump(until, seconds=5.0):
    deadline = time.monotonic() + seconds
    while not until() and time.monotonic() < deadline:
        QApplication.processEvents()
        time.sleep(0.01)
    return until()


# -- comparing versions ---------------------------------------------------------- #


@pytest.mark.parametrize(
    "latest, current, newer",
    [
        ("v1.2.0", "1.1.0", True),
        ("1.1.1", "1.1.0", True),
        ("v1.10.0", "1.9.0", True),  # numbers, not text
        ("v1.1.0", "1.1.0", False),
        ("v1.1", "1.1.0", False),
        ("v1.0.9", "1.1.0", False),
        ("v2.0.0-beta", "1.1.0", True),
        ("nightly", "1.1.0", False),
    ],
)
def test_is_newer(latest, current, newer):
    assert updates.is_newer(latest, current) is newer


# -- asking GitHub ------------------------------------------------------------------ #


class Response(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


REAL_FETCH = updates.fetch_latest  # before the autouse fixture swaps it out


@pytest.fixture
def github(monkeypatch):
    """The real fetch_latest against a stand-in for GitHub's answer."""
    monkeypatch.setattr(updates, "fetch_latest", REAL_FETCH)
    answer = {}

    def urlopen(request, timeout):
        answer["request"] = request
        if isinstance(answer.get("body"), Exception):
            raise answer["body"]
        return Response(answer["body"])

    monkeypatch.setattr(updates.urllib.request, "urlopen", urlopen)
    return answer


def test_reads_the_latest_release(github):
    github["body"] = json.dumps(
        {"tag_name": "v1.2.0", "html_url": "https://github.com/k1llrouz/pdf-to-md-ui/releases/tag/v1.2.0"}
    ).encode()

    assert updates.fetch_latest() == {
        "version": "1.2.0",
        "url": "https://github.com/k1llrouz/pdf-to-md-ui/releases/tag/v1.2.0",
    }
    assert github["request"].get_header("User-agent").startswith("pdf-to-md-ui/")


@pytest.mark.parametrize("body", [OSError("offline"), b"<html>rate limited</html>", b"{}"])
def test_no_answer_is_not_an_error(github, body):
    github["body"] = body

    assert updates.fetch_latest() is None


def test_check_answers_on_the_window_thread(qapp, monkeypatch):
    monkeypatch.setattr(updates, "fetch_latest", lambda: {"version": "9.9.9", "url": "u"})
    got = []
    check = updates.UpdateCheck()
    check.finished.connect(got.append)

    check.start()

    assert pump(lambda: got)
    assert got == [{"version": "9.9.9", "url": "u"}]


# -- what the window does with it -------------------------------------------------- #

NEWER = {"version": "99.0.0", "url": "https://github.com/k1llrouz/pdf-to-md-ui/releases/tag/v99.0.0"}
SAME = {"version": __version__, "url": "https://example.invalid/same"}


@pytest.fixture
def on_screen(window):
    gui._windows.append(window)
    return window


def check(monkeypatch, answer, manual=False):
    monkeypatch.setattr(updates, "fetch_latest", lambda: answer)
    gui.check_for_updates(manual=manual)
    assert pump(lambda: not gui._update_checks), "the check never came back"


@pytest.fixture
def opened(monkeypatch):
    urls = []
    monkeypatch.setattr(gui.QDesktopServices, "openUrl", lambda url: urls.append(url))
    return urls


def test_startup_check_shows_a_newer_release(on_screen, monkeypatch, dialogs):
    check(monkeypatch, NEWER)

    assert on_screen.update_link.isVisibleTo(on_screen)
    assert "99.0.0" in on_screen.update_link.text()
    assert NEWER["url"] in on_screen.update_link.text()
    assert dialogs == [], "a startup check must not pop anything up"


@pytest.mark.parametrize("answer", [SAME, None])
def test_startup_check_stays_quiet_otherwise(on_screen, monkeypatch, dialogs, answer):
    check(monkeypatch, answer)

    assert not on_screen.update_link.isVisibleTo(on_screen)
    assert dialogs == []


def test_manual_check_offers_the_download(on_screen, monkeypatch, dialogs, opened):
    check(monkeypatch, NEWER, manual=True)

    assert "99.0.0" in dialogs[0][2] and __version__ in dialogs[0][2]
    assert opened == [QUrl(NEWER["url"])]


def test_manual_check_says_when_up_to_date(on_screen, monkeypatch, dialogs, opened):
    check(monkeypatch, SAME, manual=True)

    assert dialogs[0][2] == gui.tr("update.latest", version=__version__)
    assert opened == []


def test_manual_check_says_when_offline(on_screen, monkeypatch, dialogs):
    check(monkeypatch, None, manual=True)

    assert dialogs[0][2] == gui.tr("update.failed")


def test_the_link_survives_a_language_switch(qapp, settings_file, monkeypatch):
    old = gui.open_window()
    check(monkeypatch, NEWER)

    new = gui.switch_language(old, "ru")

    assert new.update_link.isVisibleTo(new)
    assert "Доступна версия 99.0.0" in new.update_link.text()


def test_startup_check_can_be_turned_off(window):
    assert gui.auto_update_check_enabled()  # on unless switched off

    window.act_auto_updates.setChecked(False)

    assert not gui.auto_update_check_enabled()
    assert not gui.MainWindow().act_auto_updates.isChecked()


# -- title bar colour ------------------------------------------------------------------ #


class Hints:
    """Records what the program tells Qt about its colours."""

    def __init__(self):
        self.calls = []

    def setColorScheme(self, scheme):
        self.calls.append(scheme)

    def unsetColorScheme(self):
        self.calls.append("system")

    def colorScheme(self):
        return Qt.ColorScheme.Dark


def test_qt_is_told_the_chosen_theme(window, monkeypatch):
    hints = Hints()
    monkeypatch.setattr(gui.QGuiApplication, "styleHints", staticmethod(lambda: hints))

    window._set_theme("dark")
    window._set_theme("light")
    window._set_theme("system")

    assert hints.calls == [Qt.ColorScheme.Dark, Qt.ColorScheme.Light, "system"]


def test_as_in_windows_follows_a_change_in_windows(window, monkeypatch):
    window._set_theme("system")
    monkeypatch.setattr(gui, "_system_prefers_dark", lambda: not window.dark)
    was = window.dark

    window._follow_system_theme()

    assert window.dark is (not was)


def test_a_chosen_theme_ignores_windows(window, monkeypatch):
    window._set_theme("light")
    monkeypatch.setattr(gui, "_system_prefers_dark", lambda: True)

    window._follow_system_theme()

    assert window.dark is False


def test_closed_windows_stop_listening(qapp, settings_file):
    w = gui.MainWindow()
    w.close()
    w.deleteLater()
    QApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    QApplication.processEvents()

    # Would raise "already deleted" if the window were still connected.
    QApplication.styleHints().colorSchemeChanged.emit(Qt.ColorScheme.Dark)
