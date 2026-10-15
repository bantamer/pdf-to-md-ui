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


@pytest.fixture(autouse=True)
def english():
    """Every test starts in English, whatever the machine's language is."""
    import i18n

    i18n.set_language("en")
    yield
    i18n.set_language("en")


@pytest.fixture(autouse=True)
def delete_windows():
    """Destroy every window a test leaves behind.

    A closed window is only hidden; it stays in the application, and each new
    window's stylesheet re-polishes all of them. Left to pile up, they made
    building a window take seconds by the end of the run.
    """
    yield
    from PySide6.QtCore import QCoreApplication, QEvent
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance()
    if app is None:
        return
    import gui

    for widget in app.topLevelWidgets():
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
