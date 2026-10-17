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


# -- MIN / TYP / MAX in one cell ------------------------------------------------ #
#
# Datasheet tables that draw no lines between MIN, TYP and MAX (TI, ADI) come
# out with one cell holding all three: "-1 1" or just "5" - and which column
# was empty is lost. The converter's JSON still has where each piece of text
# sat on the page, which is enough to put every number back under its word.

_LIMIT_WORDS = {"MIN", "TYP", "NOM", "MAX"}
# A word may carry a footnote mark: "MIN TYP(1) MAX".
_LIMIT_WORD = r"(?:MIN|TYP|NOM|MAX)\.?(?:\s*\(\d+\))?"
_LIMIT_HEADER = re.compile(rf"^\s*{_LIMIT_WORD}(?:\s+{_LIMIT_WORD}){{1,2}}\s*$", re.I)
_NUMBER = re.compile(r"^[-–−+±]?\d+(?:[.,]\d+)?$")
_SIGN = re.compile(r"^[-–−+×/]$")
_CHAR_WIDTH = 0.55  # of the font size, for an average digit
_LINE_HEIGHT = 1.25  # of the font size


def _json_tables(doc) -> list[dict]:
    """Every table of the converter's JSON, in the order the Markdown has them."""
    found: list[dict] = []

    def walk(node):
        if isinstance(node, dict):
            if node.get("type") == "table":
                found.append(node)
            for key in ("kids", "rows", "cells"):
                for child in node.get(key) or []:
                    walk(child)
        elif isinstance(node, list):
            for child in node:
                walk(child)

    walk(doc)
    return found


def _paragraphs(cell: dict) -> list[dict]:
    out = []
    for kid in cell.get("kids") or []:
        if "content" in kid and "bounding box" in kid:
            out.append(kid)
        out += _paragraphs(kid)
    return out


def _word_centres(text: str, box, size: float, words: list[str] | None = None) -> list[tuple[str, float]]:
    """Words of a one-line text and the x each is centred on.

    The first word starts at the left edge and the last ends at the right;
    words between are placed by their position in the text. The gaps in a
    table row are much wider than a space, so this is close enough to tell
    columns apart. `words` may group the text differently ("GND – 0.3").
    """
    words = words or text.split()
    left, right = box[0], box[2]
    if len(words) == 1:
        return [(words[0], (left + right) / 2)]
    first = left + len(words[0]) * size * _CHAR_WIDTH / 2
    last = right - len(words[-1]) * size * _CHAR_WIDTH / 2
    starts, pos = [], 0
    for word in words:
        pos = text.index(word, pos)
        starts.append(pos + len(word) / 2)
        pos += len(word)
    span = (starts[-1] - starts[0]) or 1
    return [(w, first + (s - starts[0]) / span * (last - first)) for w, s in zip(words, starts)]


def _operands(text: str) -> list[str]:
    """The words of a cell, with "GND – 0.3" and "(V+) – 1.5" kept as one.

    A sign standing alone between two words joins them: it is one limit,
    not two.
    """
    out: list[str] = []
    words = text.split()
    i = 0
    while i < len(words):
        if _SIGN.match(words[i]) and out and i + 1 < len(words):
            out[-1] = f"{out[-1]} {words[i]} {words[i + 1]}"
            i += 2
            continue
        out.append(words[i])
        i += 1
    return out


def _lines(paragraph: dict) -> int:
    box = paragraph["bounding box"]
    size = float(paragraph.get("font size") or 8)
    return max(1, round((box[3] - box[1]) / (size * _LINE_HEIGHT)))


def _split_cell(cell: dict, centres: list[float]) -> list[list[str]] | None:
    """The cell's values per column, top to bottom; None if it cannot tell."""
    columns: list[list[str]] = [[] for _ in centres]
    pitch = min(b - a for a, b in zip(centres, centres[1:]))
    nearest = lambda x: min(range(len(centres)), key=lambda i: abs(centres[i] - x))  # noqa: E731
    paragraphs = sorted(_paragraphs(cell), key=lambda p: -p["bounding box"][3])
    for paragraph in paragraphs:
        text = paragraph["content"].strip()
        if not text:
            continue
        box = paragraph["bounding box"]
        size = float(paragraph.get("font size") or 8)
        lines = _lines(paragraph)
        words = text.split()
        # Only numbers on one line ("3 7") are values side by side, however
        # close together: the header estimate can make the columns look wider
        # than they are (LM358's "TYP(2)"). "VDD - 1" is one value.
        numbers = lines == 1 and len(words) > 1 and all(_NUMBER.match(w) for w in words)
        narrow = box[2] - box[0] < pitch * 0.8 and not numbers
        if narrow:
            column = columns[nearest((box[0] + box[2]) / 2)]
            # A column of values, one per line - or a value with a space in it.
            column.extend(words if lines > 1 and len(words) == lines else [text])
        elif lines == 1:
            placed: list[tuple[int, str]] = []
            line = " ".join(text.split())
            for word, x in _word_centres(line, box, size, _operands(line)):
                index = nearest(x)
                if placed and placed[-1][0] == index:
                    placed[-1] = (index, placed[-1][1] + " " + word)
                else:
                    placed.append((index, word))
            for index, value in placed:
                columns[index].append(value)
        else:
            return None  # several lines across several columns: no telling
    return columns


def _header_centres(cell: dict) -> tuple[list[str], list[float]] | None:
    paragraphs = _paragraphs(cell)
    if len(paragraphs) != 1:
        return None
    text = paragraphs[0]["content"].strip()
    if not _LIMIT_HEADER.match(text):
        return None
    size = float(paragraphs[0].get("font size") or 8)
    placed: list[tuple[str, float]] = []
    for word, x in _word_centres(text, paragraphs[0]["bounding box"], size):
        if placed and re.fullmatch(r"\(\d+\)", word):
            continue  # "TYP (2)": the mark belongs to the word, not a column
        placed.append((word, x))
    return [re.sub(r"\.?(\s*\(\d+\))?$", "", w).upper() for w, _ in placed], [x for _, x in placed]


# A tiny reader for the converter's own HTML tables: rows and cells, with
# nested tables kept whole inside the cell they belong to.
_TABLE_PART = re.compile(r"<(/?)(table|tr|td|th)\b([^>]*)>", re.I)


def _table_rows(table: str) -> list[list[tuple[int, int, str, str]]] | None:
    """Rows of (start, end, tag, attributes) for each cell of the outer table."""
    rows: list[list[tuple[int, int, str, str]]] = []
    depth, cell = 0, None
    for m in _TABLE_PART.finditer(table):
        closing, tag, attrs = m.group(1) == "/", m.group(2).lower(), m.group(3)
        if tag == "table":
            depth += -1 if closing else 1
            continue
        if depth != 1:
            continue
        if tag == "tr" and not closing:
            rows.append([])
        elif tag in ("td", "th") and not closing:
            if not rows:
                return None
            cell = (m.start(), tag, attrs)
        elif tag in ("td", "th") and closing and cell is not None:
            rows[-1].append((cell[0], m.end(), cell[1], cell[2]))
            cell = None
    return rows


def _colspan(attrs: str) -> int:
    m = re.search(r'colspan="(\d+)"', attrs)
    return int(m.group(1)) if m else 1


def _with_colspan(attrs: str, span: int) -> str:
    attrs = re.sub(r'\s*colspan="\d+"', "", attrs)
    return f'{attrs} colspan="{span}"' if span > 1 else attrs


def _rowspan(attrs: str) -> int:
    m = re.search(r'rowspan="(\d+)"', attrs)
    return int(m.group(1)) if m else 1


def _escape(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _key(text: str) -> str:
    """Text reduced for comparing a Markdown cell with a JSON one."""
    text = _ANY_TAG.sub(" ", text)
    text = text.replace("&lt;", "<").replace("&gt;", ">").replace("&amp;", "&")
    return re.sub(r"\s+", "", text)


def _limit_pool(doc) -> list[dict]:
    """Every JSON cell under a MIN/TYP/MAX header, in document order.

    A table with two groups (INA219A and INA219B side by side) lists the
    first group's column top to bottom, then the second's - the order the
    Markdown side walks them in.
    """
    pool: list[dict] = []
    for table in _json_tables(doc):
        cells = [c for row in table.get("rows") or [] for c in row.get("cells") or []]
        heads: dict[int, tuple] = {}
        for c in cells:
            if int(c.get("column span") or 1) == 1:
                found = _header_centres(c)
                if found:
                    heads.setdefault(int(c["column number"]), (c, *found))
        for col in sorted(heads):
            head, words, centres = heads[col]
            for c in sorted(cells, key=lambda c: int(c["row number"])):
                if int(c["column number"]) == col and int(c.get("column span") or 1) == 1:
                    pool.append({
                        "key": _key("".join(p["content"] for p in _paragraphs(c))),
                        "cell": c, "words": words, "centres": centres, "head": c is head,
                    })
    return pool


def _grid(rows) -> list[list[tuple[int, int, str, str, int, int]]]:
    """Each cell with the grid column it starts in and how many it spans."""
    taken: set[tuple[int, int]] = set()
    out = []
    for r, row in enumerate(rows):
        col, placed = 0, []
        for start, end, tag, attrs in row:
            while (r, col) in taken:
                col += 1
            span = _colspan(attrs)
            placed.append((start, end, tag, attrs, col, span))
            for dr in range(_rowspan(attrs)):
                for dc in range(span):
                    taken.add((r + dr, col + dc))
            col += span
        out.append(placed)
    return out


class _Cursor:
    """Hands out the pool's headers in document order, each once.

    A Markdown header takes the first unused JSON header with the same text;
    the values of that column are then looked for right after it. Repeated
    headers ("MIN MAX" in ten tables) pair up in order this way, and one
    table that finds no partner does not throw the rest off.
    """

    WINDOW = 80

    def __init__(self, pool):
        self.pool = pool
        self.used: set[int] = set()

    def head(self, key: str) -> int | None:
        for i, entry in enumerate(self.pool):
            if entry["head"] and entry["key"] == key and i not in self.used:
                self.used.add(i)
                return i
        return None

    def cell(self, key: str, after: int) -> tuple[dict | None, int]:
        """The next value entry with this text after index `after`."""
        for i in range(after + 1, min(len(self.pool), after + 1 + self.WINDOW)):
            entry = self.pool[i]
            if not entry["head"] and entry["key"] == key:
                return entry, i
        return None, after


def _split_table(table: str, cursor: _Cursor) -> str | None:
    rows = _table_rows(table)
    if not rows:
        return None
    grid = _grid(rows)

    def inner(start, end, tag):
        return table[table.index(">", start) + 1: end - len(f"</{tag}>")]

    # Header cells: a MIN/TYP/MAX cell of one column, found in the JSON too.
    targets: dict[int, dict] = {}
    for row in grid:
        for start, end, tag, attrs, col, span in row:
            text = re.sub(r"\s+", " ", _ANY_TAG.sub(" ", inner(start, end, tag))).strip()
            if span == 1 and _LIMIT_HEADER.match(text) and col not in targets:
                found = cursor.head(_key(text))
                if found is not None:
                    targets[col] = {**cursor.pool[found], "at": found}
    if not targets:
        return None

    replaced: dict[tuple[int, int], str] = {}
    for col in sorted(targets):
        head = targets[col]
        parts = len(head["words"])
        at = head["at"]
        for row in grid:
            for start, end, tag, attrs, first, span in row:
                if span != 1 or first != col:
                    continue
                content = inner(start, end, tag)
                key = _key(content)
                if head["key"] == key and not replaced.get((start, end)):
                    new = "".join(f"<{tag}{attrs}>{w}</{tag}>" for w in head["words"])
                elif not key:
                    new = f"<{tag}{attrs}> </{tag}>" * parts
                else:
                    entry, at = cursor.cell(key, at)
                    split = _split_cell(entry["cell"], head["centres"]) if entry else None
                    if split is None:
                        new = f"<{tag}{_with_colspan(attrs, parts)}>{content}</{tag}>"
                    else:
                        new = "".join(
                            f"<{tag}{attrs}>{'<br>'.join(_escape(v) for v in values) or ' '}</{tag}>"
                            for values in split
                        )
                replaced[(start, end)] = new
    # Cells spanning a split column get wider by the columns it gained.
    for row in grid:
        for start, end, tag, attrs, first, span in row:
            if span > 1:
                extra = sum(len(targets[c]["words"]) - 1 for c in targets if first <= c < first + span)
                if extra:
                    replaced[(start, end)] = (
                        f"<{tag}{_with_colspan(attrs, span + extra)}>{inner(start, end, tag)}</{tag}>"
                    )
    for (start, end), new in sorted(replaced.items(), reverse=True):
        table = table[:start] + new + table[end:]
    return table


def split_limit_columns(md: str, doc) -> tuple[str, int]:
    """Split merged MIN/TYP/MAX columns using the converter's JSON `doc`.

    The Markdown is not a cell-for-cell copy of the JSON - a table continued
    on the next page is one table in it, and column spans differ - so cells
    are found by their text, in document order. A cell that cannot be found
    stays whole, spread over the new columns: never worse than before.
    """
    pool = _limit_pool(doc)
    if not pool:
        return md, 0
    cursor = _Cursor(pool)
    out, last, changed = [], 0, 0
    for start, end in _top_level_tables(md):
        table = md[start:end]
        if not _LIMIT_TEXT.search(table) or "<table>" in table[7:]:
            continue
        new = _split_table(table, cursor)
        if new is None or new == table:
            continue
        out.append(md[last:start])
        out.append(new)
        last = end
        changed += 1
    out.append(md[last:])
    return "".join(out), changed


_ANY_TAG = re.compile(r"<[^>]+>")
_LIMIT_TEXT = re.compile(
    r"<t[hd][^>]*>\s*(?:MIN|TYP|NOM|MAX)\.?(?:\s*\(\d+\))?\s+(?:MIN|TYP|NOM|MAX)", re.I
)


# -- images ---------------------------------------------------------------------- #
#
# With images saved as files the converter writes one file per picture it
# meets: ST's logo once per page (40 identical files, 40 links), and the
# pictures inside drawings that drop_figure_tables() has since removed
# (BME280: 204 files, 28 still linked).

_IMAGE_LINK = re.compile(r"!\[[^\]]*\]\(<?([^)<>]+?)>?\)")
# An identical picture linked this often is a logo or a page decoration,
# not a figure: its links go.
REPEATED_IMAGE = 5


def tidy_images(md: str, folder, keep: set[str] = frozenset()) -> tuple[str, int, int]:
    """Merge identical image files, drop page decorations, delete strays.

    `folder` is the <name>_images folder next to the Markdown; `keep` names
    files other outputs (HTML, JSON) link to. Returns the new Markdown, the
    number of links removed and the number of files deleted.
    """
    import hashlib
    from pathlib import Path

    folder = Path(folder)
    if not folder.is_dir():
        return md, 0, 0
    digest: dict[str, str] = {}
    for f in folder.iterdir():
        if f.is_file():
            digest[f.name] = hashlib.md5(f.read_bytes()).hexdigest()
    first: dict[str, str] = {}
    for name in sorted(digest, key=lambda n: (len(n), n)):
        first.setdefault(digest[name], name)

    links = [m for m in _IMAGE_LINK.finditer(md) if Path(m.group(1)).name in digest]
    uses: dict[str, int] = {}
    for m in links:
        h = digest[Path(m.group(1)).name]
        uses[h] = uses.get(h, 0) + 1

    out, last, removed = [], 0, 0
    for m in links:
        name = Path(m.group(1)).name
        h = digest[name]
        out.append(md[last:m.start()])
        if uses[h] >= REPEATED_IMAGE:
            removed += 1
        else:
            target = m.group(1)[: -len(name)] + first[h]
            out.append(f"![](<{target}>)")
        last = m.end()
    out.append(md[last:])
    new = "".join(out)
    if removed:
        new = re.sub(r"\n{4,}", "\n\n\n", new)

    used = {Path(m.group(1)).name for m in _IMAGE_LINK.finditer(new)} | set(keep)
    deleted = 0
    for name in digest:
        if name not in used:
            try:
                (folder / name).unlink()
                deleted += 1
            except OSError:
                pass
    try:
        if not any(folder.iterdir()):
            folder.rmdir()
    except OSError:
        pass
    return new, removed, deleted
