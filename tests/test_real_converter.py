"""End to end through the real JAR, on tests/fixtures/table.pdf.

This is the guard against upstream regressions in the output itself:
opendataloader-pdf 2.5.1-2.5.5 wrote every table cell as &lt;td&gt;, which the
app had to repair by hand. 2.5.13 is clean; if a later release breaks it again,
this is where it shows.

table.pdf: page 1 is a parameter table with merged cells and a literal "<" in a
cell, page 2 a second table, page 3 plain text.
"""

import re

import pytest

import converter
from converter import ConvertWorker, Job
from tests.conftest import FIXTURES

pytestmark = pytest.mark.skipif(
    converter.java_executable() is None or converter.jar_path() is None,
    reason="needs Java and the opendataloader-pdf JAR",
)


@pytest.fixture(scope="module")
def converted(tmp_path_factory, qapp):
    out = tmp_path_factory.mktemp("out")
    options = {
        "format": "markdown,html",
        "content_safety_off": converter.CONTENT_SAFETY_OFF,
        "replace_invalid_chars": "?",
        "image_output": "off",
        "markdown_with_html": True,
        "markdown_page_separator": converter.PAGE_SEPARATOR,
    }
    worker = ConvertWorker(
        [Job(str(FIXTURES / "table.pdf"), str(out), "table.pdf")],
        str(out), options, 120, converter.supported_option_names(),
    )
    result = {}
    worker.finished.connect(result.update)
    worker.run()
    assert result["ok"] == 1, result
    return {
        "md": (out / "table.md").read_text(encoding="utf-8"),
        "html": (out / "table.html").read_text(encoding="utf-8"),
    }


def test_markdown_tables_are_real_html(converted):
    md = converted["md"]

    assert md.count("<table") == 2
    assert "&lt;td" not in md and "&lt;th" not in md, "table cells came out escaped"
    assert "&lt;tr" not in md


def test_merged_cells_survive(converted):
    md = converted["md"]

    assert re.search(r'<t[dh][^>]*colspan="2"[^>]*>\s*TEST CONDITIONS', md)
    assert re.search(r'<td[^>]*rowspan="2"[^>]*>\s*Accuracy', md)


def test_comparison_in_a_cell_stays_escaped(converted):
    """A real "<" in cell text must stay &lt;, or the table markup breaks."""
    assert "VOUT &lt; 1.5 V" in converted["md"]


def test_every_cell_is_accounted_for(converted):
    """37 cells drawn; header rows may come out as <th>, but none go missing."""
    md = converted["md"]
    cells = len(re.findall(r"<t[dh][\s>]", md))

    assert cells == 37


def test_page_separators(converted):
    md = converted["md"]

    assert [int(n) for n in re.findall(r"---- page (\d+) ----", md)] == [1, 2, 3]


def test_html_output_matches(converted):
    html = converted["html"]

    assert html.count("<table") == 2
    assert "&lt;td" not in html


def test_plain_markdown_without_separators(tmp_path, qapp):
    """The two switches in Options: pipe tables instead of HTML, no page lines."""
    options = {
        "format": "markdown",
        "content_safety_off": converter.CONTENT_SAFETY_OFF,
        "replace_invalid_chars": "?",
        "image_output": "off",
    }
    worker = ConvertWorker(
        [Job(str(FIXTURES / "table.pdf"), str(tmp_path), "table.pdf")],
        str(tmp_path), options, 120, converter.supported_option_names(),
    )
    result = {}
    worker.finished.connect(result.update)
    worker.run()
    assert result["ok"] == 1, result
    md = (tmp_path / "table.md").read_text(encoding="utf-8")

    assert "<table" not in md
    assert re.search(r"^\|.*TEST CONDITIONS.*\|\s*$", md, re.M), "the table is gone"
    assert "---- page" not in md
