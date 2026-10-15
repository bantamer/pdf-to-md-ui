"""Turning options into a command line: build_args(), startup_paths()."""

from converter import build_args
from gui import startup_paths


def test_values_flags_and_skips():
    args = build_args(
        "in.pdf",
        "out",
        {
            "format": "markdown,pdf",
            "markdown_with_html": True,
            "sanitize": False,
            "pages": "",
            "password": None,
            "threads": 4,
        },
        supported=None,
    )

    assert args == [
        "in.pdf", "--output-dir", "out",
        "--format", "markdown,pdf",
        "--markdown-with-html",
        "--threads", "4",
    ]


def test_options_the_installed_version_lacks_are_left_out():
    args = build_args(
        "in.pdf", "out", {"format": "markdown", "enrich_formula": True},
        supported={"format"},
    )

    assert "--enrich-formula" not in args


def test_page_separator_survives_as_one_argument():
    sep = "\n\n---- page %page-number% ----\n\n"
    args = build_args("in.pdf", "out", {"markdown_page_separator": sep}, None)

    assert args[-2:] == ["--markdown-page-separator", sep]


def test_startup_paths_keep_only_existing_files(tmp_path):
    pdf = tmp_path / "doc.pdf"
    pdf.write_bytes(b"%PDF")

    assert startup_paths([str(pdf), "--some-switch", "", str(tmp_path / "nope.pdf")]) == [
        str(pdf)
    ]
