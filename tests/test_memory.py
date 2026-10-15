"""The veraPDF line-art patch: does it apply, does it help, is it still needed.

See patches/README.md. The fixture is a page of 3000 separate strokes, built
on the fly by tests/pdfgen.py - the shape of a datasheet's plot pages. Without
the patch, opendataloader-pdf 2.5.13 needs well over 256 MB for it; with the
patch, 64 MB is enough. The tests run it in 128 MB.
"""

import subprocess
import zipfile

import pytest

import converter
from converter import ConvertWorker, Job
from tests.pdfgen import dense_line_pdf

HEAP_MB = 128
STROKES = 3000

needs_java = pytest.mark.skipif(
    converter.java_executable() is None or converter.jar_path() is None,
    reason="needs Java and the opendataloader-pdf JAR",
)


@pytest.fixture
def dense_pdf(tmp_path):
    return dense_line_pdf(tmp_path / "plots.pdf", STROKES)


# -- when the patch applies ------------------------------------------------- #


@needs_java
def test_patch_applies_to_the_pinned_release():
    patch = converter.verapdf_patch(converter.jar_path())

    assert patch is not None, (
        "the installed opendataloader-pdf is not the one the patch was measured "
        "against - see patches/README.md"
    )
    folder, main = patch
    assert main == "org.opendataloader.pdf.cli.CLIMain"


def fake_jar(path, chunkparser: bytes):
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("META-INF/MANIFEST.MF", "Main-Class: some.Main\n")
        z.writestr(converter.PATCHED_CLASS, chunkparser)
    return str(path)


def test_any_other_jar_runs_untouched(tmp_path):
    jar = fake_jar(tmp_path / "other.jar", b"a different ChunkParser")

    assert converter.verapdf_patch(jar) is None
    command = converter.java_command("java", jar, ["in.pdf"])
    assert command[-3:] == ["-jar", jar, "in.pdf"]
    assert "-cp" not in command


def test_unreadable_jar_runs_untouched(tmp_path):
    broken = tmp_path / "broken.jar"
    broken.write_bytes(b"not a zip")

    assert converter.verapdf_patch(str(broken)) is None
    assert converter.verapdf_patch(str(tmp_path / "missing.jar")) is None


@needs_java
def test_patched_command_puts_the_patch_first():
    jar = converter.jar_path()

    command = converter.java_command("java", jar, ["in.pdf"])

    cp = command[command.index("-cp") + 1].split(converter.os.pathsep)
    assert cp == [str(converter.PATCH_ROOT), jar]
    assert command[-2:] == ["org.opendataloader.pdf.cli.CLIMain", "in.pdf"]


# -- what it buys ------------------------------------------------------------ #


@needs_java
def test_plot_pages_convert_in_a_small_heap(qapp, dense_pdf, tmp_path, monkeypatch):
    monkeypatch.delenv("JAVA_TOOL_OPTIONS", raising=False)
    monkeypatch.setattr(converter, "max_heap_mb", lambda: HEAP_MB)
    out = tmp_path / "out"
    worker = ConvertWorker(
        [Job(str(dense_pdf), str(out), "plots.pdf")],
        str(out), {"format": "markdown", "image_output": "off"}, 120,
        converter.supported_option_names(),
    )
    result, log = {}, []
    worker.finished.connect(result.update)
    worker.log.connect(log.append)

    worker.run()

    text = "\n".join(log)
    assert "OutOfMemoryError" not in text
    assert result["ok"] == 1, text[-2000:]
    assert "Typical Characteristics" in (out / "plots.md").read_text(encoding="utf-8")
    assert "заплатка veraPDF: включена" in text


@needs_java
def test_patch_still_needed(dense_pdf, tmp_path):
    """The unpatched jar must still fail here; when it stops failing, upstream
    has fixed the regression and patches/verapdf should go."""
    out = tmp_path / "out"
    out.mkdir()
    result = subprocess.run(
        [
            converter.java_executable(),
            f"-Xmx{HEAP_MB}m",
            "-Djava.awt.headless=true",
            "-jar", converter.jar_path(),
            str(dense_pdf), "--output-dir", str(out),
            "--format", "markdown", "--image-output", "off",
        ],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        timeout=300,
    )

    assert "OutOfMemoryError" in result.stdout + result.stderr, (
        "opendataloader-pdf now handles dense line art without the patch: "
        "remove patches/verapdf - see patches/README.md"
    )
