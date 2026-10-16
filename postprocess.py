"""Clean-ups applied to the converter's Markdown after it is written.

opendataloader-pdf reads a plot, a package drawing or a flow chart as a table:
the grid lines become cell borders and the tick labels end up scattered over
hundreds of empty cells. In a datasheet that can be three quarters of the
file - text nobody can use, and for whoever reads the result (often a
language model) a heap of tokens. drop_figure_tables() swaps each such table
for one line saying a figure was there, with its caption and page, and keeps
any real sentences that were written inside it (a flow chart's steps).
"""

from __future__ import annotations

import re

from i18n import tr

# A table is taken for a drawing when at least this share of its cells is
# empty and it has enough cells for that to mean something. Tuned on 23
# datasheets from 13 makers: every table above it was a plot, a package
# drawing, a land pattern, a schematic or a flow chart; the closest real one
# (a pinout drawn as a grid, 74HC595) sat at 51%.
EMPTY_SHARE = 0.6
MIN_CELLS = 12

_TABLE_TAG = re.compile(r"<table>|</table>")
_CELL = re.compile(r"<t[dh][^>]*>(.*?)</t[dh]>", re.S)
_TAG = re.compile(r"<[^>]+>")
_PAGE = re.compile(r"---- page (\d+) ----")
_CAPTION = re.compile(
    r"((?:Figure|FIGURE|Fig\.?|Рисунок|Рис\.|図)\s*\d[\w\-–.]*[.:]?\s+\S.*)"
)
_WORD = re.compile(r"[^\W\d_]{2,}")


def _top_level_tables(md: str) -> list[tuple[int, int]]:
    spans, depth, start = [], 0, None
    for m in _TABLE_TAG.finditer(md):
        if m.group() == "<table>":
            if depth == 0:
                start = m.start()
            depth += 1
        elif depth:
            depth -= 1
            if depth == 0 and start is not None:
                spans.append((start, m.end()))
    return spans


def _cell_texts(table: str) -> list[str]:
    texts = []
    for raw in _CELL.findall(table):
        # Nested tables are part of the same drawing: their cells count too,
        # and their markup is no text of the outer cell.
        if "<table>" in raw:
            raw = raw.split("<table>", 1)[0]
        texts.append(_TAG.sub("\n", raw.replace("&lt;", "<").replace("&gt;", ">").replace("&amp;", "&")))
    return texts


def _fragments(text: str) -> list[str]:
    """A cell's text split where the converter glued separate labels."""
    parts = re.split(r"\n+|\s{2,}", text)
    return [p.strip() for p in parts if p.strip()]


def _is_phrase(fragment: str) -> bool:
    """Real words, not tick labels or scattered syllables."""
    words = _WORD.findall(fragment)
    letters = sum(len(w) for w in words)
    return len(words) >= 3 and letters >= 0.5 * len(fragment.replace(" ", ""))


def is_figure_table(table: str) -> bool:
    cells = _cell_texts(table)
    if len(cells) < MIN_CELLS:
        return False
    empty = sum(1 for c in cells if not c.strip())
    return empty / len(cells) >= EMPTY_SHARE


def _describe(table: str) -> tuple[str, list[str]]:
    """(caption found inside the table, sentences worth keeping)."""
    caption, phrases = "", []
    for cell in _cell_texts(table):
        for fragment in _fragments(cell):
            found = _CAPTION.search(fragment)
            if found and not caption:
                caption = found.group(1).strip()
            elif _is_phrase(fragment) and fragment not in phrases:
                phrases.append(fragment)
    return caption, phrases


# Lines a plot leaves around its table: tick values and axis titles that the
# converter set as paragraphs of their own.
_NUMERIC_LINE = re.compile(
    r"^[\s+\-–−±~.,0-9×x/%°µΩ]*(?:\s*(?:[munpkMG]?(?:V|A|W|Hz|s|Ω|F|C|dB|°C|%)|ppm|div)\b[\s+\-–−.,0-9/]*)*$"
)
_AXIS_LINE = re.compile(r"^[^\W\d_][\w ,.\-–/'’]{0,60}\([^()]{1,16}\)$")
_NOTE_LINE = re.compile(r"^\*\[.+\]\*$")
# How far from a dropped figure stray labels are looked for, in lines.
_STRAY_REACH = 60


def _is_stray(line: str) -> bool:
    text = line.strip()
    if not text or _CAPTION.match(text):
        return False
    return bool(_NUMERIC_LINE.match(text) or _AXIS_LINE.match(text))


def _drop_stray_labels(md: str) -> str:
    """Remove the tick values and axis titles left around each figure note."""
    lines = md.split("\n")
    doomed: set[int] = set()
    for i, line in enumerate(lines):
        if not _NOTE_LINE.match(line.strip()):
            continue
        for step in (-1, 1):
            j = i + step
            while 0 <= j < len(lines) and abs(j - i) <= _STRAY_REACH:
                text = lines[j].strip()
                if not text or j in doomed:
                    j += step
                    continue
                if _NOTE_LINE.match(text) or not _is_stray(text):
                    break
                doomed.add(j)
                j += step
    if not doomed:
        return md
    kept = [line for i, line in enumerate(lines) if i not in doomed]
    # Collapse the blank runs the removed lines leave behind.
    return re.sub(r"\n{4,}", "\n\n\n", "\n".join(kept))


def drop_figure_tables(md: str) -> tuple[str, int]:
    """Replace tables that are really drawings; return the text and how many."""
    out, last, dropped = [], 0, 0
    pages = [(m.start(), m.group(1)) for m in _PAGE.finditer(md)]
    for start, end in _top_level_tables(md):
        table = md[start:end]
        if not is_figure_table(table):
            continue
        page = next((n for pos, n in reversed(pages) if pos < start), None)
        caption, phrases = _describe(table)
        note = tr("figure.omitted_page", page=page) if page else tr("figure.omitted")
        if caption:
            note += ": " + caption
        lines = [f"*{note}*"]
        lines += [f"- {p}" for p in phrases]
        out.append(md[last:start])
        out.append("\n".join(lines))
        last = end
        dropped += 1
    out.append(md[last:])
    result = "".join(out)
    if dropped:
        result = _drop_stray_labels(result)
    return result, dropped
