"""The batch loop: errors, timeouts, the retry without images, Cancel.

The JVM is replaced by a small Python script that behaves according to the
name of the file it is given, so every path runs in seconds and the same way
every time.
"""

import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest

import converter
from converter import ConvertWorker, Job
from i18n import tr

FAKE_JAVA = r"""
import sys, time
args = sys.argv[1:]
name = args[0].replace("\\", "/").rsplit("/", 1)[-1]
images_off = "--image-output" in args and args[args.index("--image-output") + 1] == "off"
print("fake converter:", name, flush=True)
if name == "bad.pdf":
    sys.exit(1)
if name == "slow.pdf" and not images_off:
    time.sleep(60)
if name == "hang.pdf":
    time.sleep(60)
sys.exit(0)
"""


@pytest.fixture
def fake_java(monkeypatch):
    """Route every conversion through FAKE_JAVA; record the processes started."""
    started: list[subprocess.Popen] = []
    real_popen = subprocess.Popen

    class Recorder(real_popen):
        def __init__(self, cmd, *a, **kw):
            super().__init__(cmd, *a, **kw)
            if isinstance(cmd, list) and FAKE_JAVA in cmd:
                started.append(self)

    monkeypatch.setattr(subprocess, "Popen", Recorder)
    monkeypatch.setattr(converter, "jar_path", lambda: "fake.jar")
    monkeypatch.setattr(converter, "java_executable", lambda: sys.executable)
    monkeypatch.setattr(
        converter,
        "java_command",
        lambda java, jar, args: [sys.executable, "-c", FAKE_JAVA, *args],
    )
    return started


def run_worker(qapp, jobs, timeout=30, options=None, cancel_after=None):
    worker = ConvertWorker(
        jobs, "out", options or {"image_output": "external"}, timeout, None
    )
    result, log = {}, []
    worker.finished.connect(result.update)
    worker.log.connect(log.append)
    if cancel_after is not None:
        threading.Timer(cancel_after, worker.cancel).start()
    worker.run()
    return result, "\n".join(log)


def jobs_for(tmp_path, *names):
    return [Job(str(tmp_path / n), str(tmp_path / "out"), n) for n in names]


def test_one_bad_file_does_not_stop_the_batch(qapp, fake_java, tmp_path):
    result, _ = run_worker(qapp, jobs_for(tmp_path, "bad.pdf", "ok.pdf"))

    assert result["ok"] == 1
    assert result["failed"] == ["bad.pdf"]
    assert result["total"] == 2


def test_timeout_retries_without_images(qapp, fake_java, tmp_path):
    start = time.monotonic()
    result, log = run_worker(qapp, jobs_for(tmp_path, "slow.pdf"), timeout=2)

    assert result["ok"] == 1
    assert result["degraded"] == ["slow.pdf"]
    assert tr("run.retry_no_images").strip() in log
    assert time.monotonic() - start < 20
    assert all(p.poll() is not None for p in fake_java), "a timed-out process lives on"


def test_no_retry_when_images_are_already_off(qapp, fake_java, tmp_path):
    result, _ = run_worker(
        qapp, jobs_for(tmp_path, "hang.pdf"), timeout=2, options={"image_output": "off"}
    )

    assert result["timed_out"] == ["hang.pdf"]
    assert len(fake_java) == 1


def test_cancel_stops_the_running_process(qapp, fake_java, tmp_path):
    start = time.monotonic()
    result, _ = run_worker(
        qapp, jobs_for(tmp_path, "hang.pdf", "ok.pdf"), timeout=0, cancel_after=1.0
    )

    assert result["cancelled"] is True
    assert result["ok"] == 0
    assert time.monotonic() - start < 20
    assert len(fake_java) == 1, "the next file must not start after Cancel"
    assert fake_java[0].poll() is not None, "the process survived Cancel"


def test_output_folders_are_created_per_job(qapp, fake_java, tmp_path):
    nested = tmp_path / "out" / "TI" / "doc (2)"
    jobs = [Job(str(tmp_path / "ok.pdf"), str(nested), "TI/ok.pdf")]

    result, _ = run_worker(qapp, jobs)

    assert result["ok"] == 1
    assert nested.is_dir()


def test_log_names_the_converter_version(qapp, fake_java, tmp_path):
    _, log = run_worker(qapp, jobs_for(tmp_path, "ok.pdf"))

    assert f"opendataloader-pdf {converter.odl_version()}" in log
    assert converter.odl_version() != "?"


def test_missing_java_is_reported_not_crashed(qapp, monkeypatch, tmp_path):
    monkeypatch.setattr(converter, "jar_path", lambda: "fake.jar")
    monkeypatch.setattr(converter, "java_executable", lambda: None)

    result, _ = run_worker(qapp, jobs_for(tmp_path, "ok.pdf"))

    assert result["error"] == tr("run.no_java")


def test_summary_records_every_file(qapp, fake_java, tmp_path):
    result, _ = run_worker(qapp, jobs_for(tmp_path, "ok.pdf", "bad.pdf", "slow.pdf"), timeout=2)

    statuses = {Path(r["pdf"]).name: r["status"] for r in result["results"]}
    assert statuses == {"ok.pdf": "ok", "bad.pdf": "failed", "slow.pdf": "degraded"}
