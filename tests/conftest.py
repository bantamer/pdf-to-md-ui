import os
import sys
from pathlib import Path

import pytest

# Windows must never pop up during a test run; the offscreen platform ships
# with PySide6. Set before anything imports Qt.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

FIXTURES = Path(__file__).resolve().parent / "fixtures"

# English and Russian are kept complete all the time. The other languages
# catch up in one go before a release, so strings can still change while a
# feature is being finished; until then they show English for what is
# missing. The release build sets RELEASE_CHECK=1 and insists on all of them.
ALWAYS_COMPLETE = {"en", "ru"}
RELEASE_CHECK = os.environ.get("RELEASE_CHECK") == "1"


def must_be_complete(code: str) -> bool:
    return RELEASE_CHECK or code in ALWAYS_COMPLETE


@pytest.fixture(autouse=True)
def english():
    """Every test starts in English, whatever the machine's language is."""
    import i18n

    i18n.set_language("en")
    yield
    i18n.set_language("en")


@pytest.fixture(autouse=True)
def dialogs(monkeypatch):
    """Message boxes are recorded, not shown.

    A modal box off screen waits for a click that never comes: the run hangs,
    or crashes when the next test tears its window down underneath it.
    Questions are answered Yes.
    """
    from PySide6.QtWidgets import QMessageBox

    shown = []

    def record(answer):
        return staticmethod(lambda *args, **kwargs: shown.append(args) or answer)

    for name in ("critical", "information", "warning"):
        monkeypatch.setattr(QMessageBox, name, record(QMessageBox.StandardButton.Ok))
    monkeypatch.setattr(QMessageBox, "question", record(QMessageBox.StandardButton.Yes))
    return shown


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    """No test talks to GitHub; a check that does ask hears nothing back."""
    import gui
    import updates

    monkeypatch.setattr(updates, "fetch_latest", lambda: None)
    monkeypatch.setattr(gui, "_latest_release", None)


@pytest.fixture(autouse=True)
def delete_windows():
    """Destroy every window a test leaves behind.

    A closed window is only hidden; it stays in the application, and each new
    window's stylesheet re-polishes all of them. Left to pile up, they made
    building a window take seconds by the end of the run.

    Closing does not save: this runs after settings_file has been undone, and
    a window saving now would write to the real registry.
    """
    yield
    from PySide6.QtCore import QCoreApplication, QEvent
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance()
    if app is None:
        return
    import gui

    for widget in app.topLevelWidgets():
        if isinstance(widget, gui.MainWindow):
            widget.skip_save = True
        widget.close()
        widget.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    gui._windows.clear()


@pytest.fixture(scope="session")
def qapp():
    from PySide6.QtWidgets import QApplication

    return QApplication.instance() or QApplication([])


@pytest.fixture
def settings_file(tmp_path, monkeypatch):
    """Point the app's settings at a throwaway ini file instead of the registry."""
    from PySide6.QtCore import QSettings

    import gui

    path = tmp_path / "settings.ini"
    monkeypatch.setattr(
        gui, "app_settings", lambda: QSettings(str(path), QSettings.Format.IniFormat)
    )
    return path


@pytest.fixture
def window(qapp, settings_file):
    import gui

    w = gui.MainWindow()
    yield w
    w.close()
