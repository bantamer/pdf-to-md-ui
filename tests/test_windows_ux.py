"""Windows conventions: one instance, remembered geometry, per-file marks, icon."""

import json
import subprocess
import sys
import time
import uuid

import pytest
from PySide6.QtCore import QUrl
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

import gui
from single_instance import SingleInstance
from tests.conftest import ROOT


def pump(until, seconds=5.0):
    deadline = time.monotonic() + seconds
    while not until() and time.monotonic() < deadline:
        QApplication.processEvents()
        time.sleep(0.01)
    return until()


def pdf(tmp_path, name="a.pdf"):
    path = tmp_path / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"%PDF")
    return path


# -- one instance ------------------------------------------------------------- #

# A real second launch: a separate process, as when Explorer starts the exe.
SECOND = """
import json, sys
sys.path.insert(0, sys.argv[1])
from PySide6.QtCore import QCoreApplication
app = QCoreApplication([])
from single_instance import SingleInstance
print(SingleInstance(sys.argv[2], sys.argv[3]).start(json.loads(sys.argv[4])))
"""


def second_launch(key, lock_dir, paths, pump_first):
    proc = subprocess.Popen(
        [sys.executable, "-c", SECOND, str(ROOT), key, lock_dir, json.dumps(paths)],
        stdout=subprocess.PIPE, text=True,
    )
    # The first instance answers from its event loop, so keep it turning.
    pump(lambda: proc.poll() is not None, seconds=30)
    out, _ = proc.communicate(timeout=30)
    pump_first()
    return out.strip()


@pytest.fixture
def instances(qapp, tmp_path):
    """SingleInstance objects that are closed properly after the test."""
    made = []

    def make():
        key = "pdf-to-md-ui-test-" + uuid.uuid4().hex[:8]
        inst = SingleInstance(key, str(tmp_path))
        made.append(inst)
        return inst

    yield make
    for inst in made:
        inst.close()
    pump(lambda: False, seconds=0.3)  # let the aborted pipes settle


def test_second_launch_hands_its_files_to_the_first(instances, tmp_path):
    first = instances()
    key = first.key
    got = []
    first.received.connect(got.append)
    assert first.start([]) is True  # nobody there yet: carry on as the program

    doc = str(pdf(tmp_path))
    answer = second_launch(key, str(tmp_path), [doc], lambda: pump(lambda: got))

    assert answer == "False", "the second launch should hand over and exit"
    assert got == [[doc]], "the running program never got the file"


def test_launch_without_files_just_wakes_the_window(instances, tmp_path):
    first = instances()
    key = first.key
    got = []
    first.received.connect(got.append)
    first.start([])

    answer = second_launch(key, str(tmp_path), [], lambda: pump(lambda: got))

    assert answer == "False" and got == [[]]


def test_first_launch_with_nobody_running_carries_on(instances):
    assert instances().start(["x.pdf"], attempts=2) is True


def test_handed_over_files_land_in_the_window(window, tmp_path):
    gui._windows.append(window)
    doc = str(pdf(tmp_path))

    gui.bring_forward([doc])

    assert window.inputs == [doc]


# -- remembered geometry -------------------------------------------------------- #


def test_window_reopens_with_the_same_size(qapp, settings_file):
    # Within the offscreen test screen (about 800 px wide): a bigger size would
    # be pulled back onto it, which is the point of restoreGeometry.
    w = gui.MainWindow()
    w.resize(760, 610)
    w._save_settings()
    w.close()

    again = gui.MainWindow()
    assert (again.width(), again.height()) == (760, 610)


def test_reset_forgets_the_geometry(qapp, settings_file):
    w = gui.open_window()
    w.resize(905, 640)
    w._save_settings()

    gui.reset_settings(w)

    assert gui.app_settings().value("geometry") is None


# -- per-file marks ---------------------------------------------------------------- #


def result(path, out, status):
    return {"pdf": str(path), "output_dir": str(out), "status": status}


def finish(window, results, formats=("markdown",)):
    """What the end of a run does, without running one."""
    window.result_formats = list(formats)
    window.elapsed.start()
    window.on_finished(
        {"ok": sum(r["status"] in ("ok", "degraded") for r in results),
         "total": len(results), "failed": [], "timed_out": [], "degraded": [],
         "cancelled": False, "error": "", "results": results}
    )


def test_marks_after_a_run(window, tmp_path):
    good, bad = pdf(tmp_path, "good.pdf"), pdf(tmp_path, "bad.pdf")
    window.add_paths([str(good), str(bad)])
    out = tmp_path / "out"

    finish(window, [result(good, out, "ok"), result(bad, out, "failed")])

    first, second = window.file_list.item(0), window.file_list.item(1)
    assert not first.icon().isNull() and not second.icon().isNull()
    assert gui.tr("list.ok") in first.toolTip()
    assert gui.tr("list.open_hint") in first.toolTip()
    assert gui.tr("list.failed") in second.toolTip()
    assert gui.tr("list.open_hint") not in second.toolTip()


def test_status_line_keeps_the_run_headline(window, tmp_path):
    doc = pdf(tmp_path)
    window.add_paths([str(doc)])

    finish(window, [result(doc, tmp_path, "ok")])

    assert window.status.text().startswith(gui.tr("summary.done", seconds="")[:4])


def test_folder_mark_sums_up_its_files(window, tmp_path):
    folder = tmp_path / "datasheets"
    a, b = pdf(folder, "a.pdf"), pdf(folder / "TI", "b.pdf")
    window.add_paths([str(folder)])

    finish(window, [result(a, tmp_path, "ok"), result(b, tmp_path, "failed")])

    tip = window.file_list.item(0).toolTip()
    assert gui.tr("list.partial", ok=1, total=2) in tip


def test_marks_clear_when_a_new_run_starts(window, tmp_path, monkeypatch):
    doc = pdf(tmp_path)
    window.add_paths([str(doc)])
    finish(window, [result(doc, tmp_path, "ok")])
    assert not window.file_list.item(0).icon().isNull()

    window.clear_inputs()
    window.add_paths([str(doc)])

    assert window.file_list.item(0).icon().isNull()


@pytest.fixture
def opened(monkeypatch):
    urls = []
    monkeypatch.setattr(gui.QDesktopServices, "openUrl", lambda url: urls.append(url))
    return urls


def test_double_click_opens_the_markdown(window, tmp_path, opened):
    doc = pdf(tmp_path, "tps7a02.pdf")
    out = tmp_path / "out"
    out.mkdir()
    (out / "tps7a02.md").write_text("# x")
    window.add_paths([str(doc)])
    finish(window, [result(doc, out, "ok")], formats=("json", "markdown"))

    window._open_result(window.file_list.item(0))

    assert opened == [QUrl.fromLocalFile(str(out / "tps7a02.md"))]


def test_double_click_on_a_folder_opens_its_results(window, tmp_path, opened):
    folder = tmp_path / "src"
    a, b = pdf(folder, "a.pdf"), pdf(folder / "TI", "b.pdf")
    out = tmp_path / "out"
    window.add_paths([str(folder)])
    finish(window, [result(a, out, "ok"), result(b, out / "TI", "ok")])

    window._open_result(window.file_list.item(0))

    assert opened == [QUrl.fromLocalFile(str(out))]


def test_double_click_on_a_failed_file_does_nothing(window, tmp_path, opened):
    doc = pdf(tmp_path)
    window.add_paths([str(doc)])
    finish(window, [result(doc, tmp_path, "failed")])

    window._open_result(window.file_list.item(0))

    assert opened == []


# -- icon --------------------------------------------------------------------------- #


def test_icon_ships_in_every_size_windows_asks_for(qapp):
    icon = QIcon(str(gui.resource("icon.ico")))
    sizes = {s.width() for s in icon.availableSizes()}

    assert {16, 24, 32, 48, 256} <= sizes
