"""Merged MIN/TYP/MAX cells put back into their columns (postprocess.py)."""

import json

from converter import ConvertWorker, Job
from postprocess import split_limit_columns

# Header "MIN TYP MAX" set at 9 pt between x = 450 and x = 528: the words sit
# at about 457, 489 and 520.
HEADER_BOX = [450.0, 667.0, 528.0, 678.0]


def para(text, x0, x1, y_top, lines=1, size=9.0):
    return {"type": "paragraph", "content": text, "font size": size,
            "bounding box": [x0, y_top - 11.25 * lines, x1, y_top]}


def cell(row, col, *paragraphs, span=1):
    return {"type": "table cell", "row number": row, "column number": col,
            "column span": span, "kids": list(paragraphs)}


def json_table(rows):
    return {"kids": [{"type": "table", "rows": [{"cells": r} for r in rows]}]}


def md_table(rows):
    out = ["<table>"]
    for r in rows:
        out.append("  <tr>")
        out += [f"    {c}" for c in r]
        out.append("  </tr>")
    out.append("</table>")
    return "\n".join(out)


def cells_of(md):
    import re
    return [re.sub(r"<[^>]+>", "", c) for c in re.findall(r"<t[hd][^>]*>.*?</t[hd]>", md)]


HEAD = cell(1, 2, para("MIN TYP MAX", *HEADER_BOX[::2], 678.0))


def test_values_go_under_their_words():
    doc = json_table([
        [cell(1, 1, para("PARAMETER", 60, 120, 678)), HEAD],
        [cell(2, 1, para("Accuracy", 60, 100, 660)), cell(2, 2, para("–1 1", 452, 526, 660))],
        [cell(3, 1, para("Line regulation", 60, 130, 640)), cell(3, 2, para("5", 486, 492, 640))],
        [cell(4, 1, para("Current", 60, 100, 620)), cell(4, 2, para("99 98", 453, 463, 620, lines=2))],
    ])
    md = md_table([
        ["<th>PARAMETER</th>", "<th>MIN TYP MAX<br><br></th>"],
        ["<td>Accuracy</td>", "<td>–1 1<br><br></td>"],
        ["<td>Line regulation</td>", "<td>5<br><br></td>"],
        ["<td>Current</td>", "<td>99 98<br><br></td>"],
    ])

    out, n = split_limit_columns(md, doc)

    assert n == 1
    assert cells_of(out) == [
        "PARAMETER", "MIN", "TYP", "MAX",
        "Accuracy", "–1", " ", "1",
        "Line regulation", " ", "5", " ",
        "Current", "9998", " ", " ",
    ]
    assert "<td>99<br>98</td>" in out, "a column of values stays one above the other"


def test_unclear_cells_stay_whole_across_the_columns():
    # Two lines spread over two columns: which number is in which row is lost.
    doc = json_table([[HEAD], [cell(2, 2, para("3 0.1 0.5", 484, 525, 660, lines=2))]])
    md = md_table([["<th>MIN TYP MAX</th>"], ["<td>3 0.1 0.5</td>"]])

    out, _ = split_limit_columns(md, doc)

    assert '<td colspan="3">3 0.1 0.5</td>' in out


def test_cells_spanning_the_column_widen():
    doc = json_table([[HEAD], [cell(2, 1, para("POWER SUPPLY", 60, 200, 660), span=3)]])
    md = md_table([["<th>MIN TYP MAX</th>"], ['<td colspan="3">POWER SUPPLY</td>']])

    out, _ = split_limit_columns(md, doc)

    assert '<td colspan="5">POWER SUPPLY</td>' in out


def test_two_groups_side_by_side():
    head_b = cell(1, 3, para("MIN TYP MAX", 550, 628, 678))
    doc = json_table([
        [HEAD, head_b],
        [cell(2, 2, para("100 120", 452, 494, 660)), cell(2, 3, para("100 120", 552, 594, 660))],
    ])
    md = md_table([
        ["<th>MIN TYP MAX</th>", "<th>MIN TYP MAX</th>"],
        ["<td>100 120</td>", "<td>100 120</td>"],
    ])

    out, _ = split_limit_columns(md, doc)

    assert cells_of(out) == ["MIN", "TYP", "MAX"] * 2 + ["100", "120", " "] * 2


def test_footnote_mark_in_the_header():
    head = cell(1, 1, para("MIN TYP(1) MAX", 450, 532, 678))
    doc = json_table([[head], [cell(2, 1, para("1.8", 455, 467, 660))]])
    md = md_table([["<th>MIN TYP(1) MAX</th>"], ["<td>1.8</td>"]])

    out, _ = split_limit_columns(md, doc)

    assert cells_of(out) == ["MIN", "TYP", "MAX", "1.8", " ", " "]


def test_two_word_header():
    head = cell(1, 1, para("MIN MAX", 450, 500, 678))
    doc = json_table([[head], [cell(2, 1, para("5.5", 488, 499, 660))]])
    md = md_table([["<th>MIN MAX</th>"], ["<td>5.5</td>"]])

    out, _ = split_limit_columns(md, doc)

    assert cells_of(out) == ["MIN", "MAX", " ", "5.5"]


def test_table_without_a_json_partner_is_left_alone():
    md = md_table([["<th>MIN TYP MAX</th>"], ["<td>1 2 3</td>"]])

    assert split_limit_columns(md, {"kids": []}) == (md, 0)


def test_tables_without_limits_are_untouched():
    doc = json_table([[cell(1, 1, para("A", 1, 2, 678))]])
    md = md_table([["<th>A</th>"]])

    assert split_limit_columns(md, doc) == (md, 0)


# -- in the worker ------------------------------------------------------------------ #


def run_post(tmp_path, extra_json):
    doc = json_table([[HEAD], [cell(2, 2, para("–1 1", 452, 526, 660))]])
    (tmp_path / "part.json").write_text(json.dumps(doc), encoding="utf-8")
    (tmp_path / "part.md").write_text(
        md_table([["<th>MIN TYP MAX</th>"], ["<td>–1 1</td>"]]), encoding="utf-8"
    )
    worker = ConvertWorker([], str(tmp_path), {"markdown_with_html": True}, 30, None)
    worker._extra_json = extra_json
    worker._postprocess(Job(str(tmp_path / "part.pdf"), str(tmp_path), "part.pdf"))
    return (tmp_path / "part.md").read_text(encoding="utf-8")


def test_worker_splits_and_removes_the_json_it_asked_for(qapp, tmp_path):
    md = run_post(tmp_path, extra_json=True)

    assert "<th>MIN</th>" in md
    assert not (tmp_path / "part.json").exists()


def test_worker_keeps_a_json_the_user_asked_for(qapp, tmp_path):
    run_post(tmp_path, extra_json=False)

    assert (tmp_path / "part.json").exists()


def test_worker_asks_for_json_only_when_it_needs_it(qapp, monkeypatch, tmp_path):
    import converter

    seen = []
    monkeypatch.setattr(converter, "jar_path", lambda: "fake.jar")
    monkeypatch.setattr(converter, "java_executable", lambda: "java")
    monkeypatch.setattr(ConvertWorker, "_run_one", lambda self, java, jar, job, options, heap, source=None:
                        seen.append(options["format"]) or "ok")
    for options in ({"format": "markdown", "markdown_with_html": True},
                    {"format": "markdown"},
                    {"format": "markdown,json", "markdown_with_html": True}):
        worker = ConvertWorker([Job(str(tmp_path / "a.pdf"), str(tmp_path), "a.pdf")],
                               str(tmp_path), options, 30, None)
        worker.run()

    assert seen == ["markdown,json", "markdown", "markdown,json"]
