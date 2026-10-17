"""Give unreadable fonts a character map before the converter reads the PDF.

A PDF font says which character each code draws in a ToUnicode map, or else
through glyph names ("H", "minus", "mu"). Some producers leave the map out and
number the glyphs instead, and then the converter can only print "?":

    Infineon   /G72 /G69 /G88 ...   the code of the character: H E X
    TI         /c45 /c109 /c176     the same, in the Symbol font's own
                                    encoding: minus, mu, degree
    Microchip  /g27 /g16 /g47 ...   the glyph's place in the font program:
                                    8 - L (the order of Arial itself)

A whole Infineon datasheet came out as question marks this way, and TI plot
labels lost their minus signs. A dingbat font can be wrong the other way: an
ADI datasheet maps its "full temperature range" bullet to the letter "l".

fix_fonts() writes a copy of the PDF with a ToUnicode map added to (or, for
dingbats, corrected in) just those fonts. Pages look exactly the same - the
map is only read when text is extracted - and the original file is never
touched. A PDF that needs nothing is not copied.
"""

from __future__ import annotations

import os
import re
from functools import lru_cache

import pikepdf
from fontTools import agl
from fontTools.ttLib.standardGlyphOrder import standardGlyphOrder

# Names made of a short prefix and a number: the producer's own numbering.
_NUMBERED = re.compile(r"^(G|g|c)(\d{1,4})$")
# Interleaf text fonts (onsemi's older datasheets) put symbols in as /C0109:
# the code in the Symbol font, so mu here.
_INTERLEAF = re.compile(r"^C0(\d{3})$")

# Adobe Symbol encoding, the codes that differ from ASCII.
SYMBOL = {
    0x22: "∀", 0x24: "∃", 0x27: "∋", 0x2A: "∗", 0x2D: "−", 0x40: "≅", 0x5C: "∴",
    0x5E: "⊥", 0x60: "‾", 0x7E: "∼",
    **dict(zip(range(0x41, 0x5B), "ΑΒΧΔΕΦΓΗΙϑΚΛΜΝΟΠΘΡΣΤΥςΩΞΨΖ")),
    **dict(zip(range(0x61, 0x7B), "αβχδεφγηιϕκλμνοπθρστυϖωξψζ")),
    0xA1: "ϒ", 0xA2: "′", 0xA3: "≤", 0xA4: "⁄", 0xA5: "∞", 0xA6: "ƒ", 0xA7: "♣",
    0xA8: "♦", 0xA9: "♥", 0xAA: "♠", 0xAB: "↔", 0xAC: "←", 0xAD: "↑", 0xAE: "→",
    0xAF: "↓", 0xB0: "°", 0xB1: "±", 0xB2: "″", 0xB3: "≥", 0xB4: "×", 0xB5: "∝",
    0xB6: "∂", 0xB7: "•", 0xB8: "÷", 0xB9: "≠", 0xBA: "≡", 0xBB: "≈", 0xBC: "…",
    0xC0: "ℵ", 0xC4: "⊗", 0xC5: "⊕", 0xC6: "∅", 0xC7: "∩", 0xC8: "∪", 0xC9: "⊃",
    0xCA: "⊇", 0xCB: "⊄", 0xCC: "⊂", 0xCD: "⊆", 0xCE: "∈", 0xCF: "∉", 0xD0: "∠",
    0xD1: "∇", 0xD2: "®", 0xD3: "©", 0xD4: "™", 0xD5: "∏", 0xD6: "√", 0xD7: "⋅",
    0xD8: "¬", 0xD9: "∧", 0xDA: "∨", 0xDB: "⇔", 0xDC: "⇐", 0xDD: "⇑", 0xDE: "⇒",
    0xDF: "⇓", 0xE0: "◊", 0xE1: "〈", 0xE5: "∑", 0xF1: "〉", 0xF2: "∫",
}
# Dingbat fonts (ZapfDingbats, Wingdings and their look-alikes): the few
# symbols datasheets use. Anything else keeps the font's own map.
DINGBATS = {0x6C: "●", 0x6E: "■", 0x75: "◆", 0x9F: "•", 0xA7: "▪"}

# Installed fonts whose glyph order decodes /gNN names, by family. The first
# 258 glyphs of these follow the old Macintosh standard order closely but not
# exactly (Arial has no "nonbreakingspace", so from 172 on it is one off).
_SYSTEM_FONTS = {
    "arial": "arial.ttf",
    "timesnewroman": "times.ttf",
    "times": "times.ttf",
    "calibri": "calibri.ttf",
    "couriernew": "cour.ttf",
    "verdana": "verdana.ttf",
    "tahoma": "tahoma.ttf",
}
_FONTS_DIR = os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts")


def _family(base_font: str) -> str:
    name = base_font.split("+", 1)[-1]
    name = re.split(r"[,\-]", name, maxsplit=1)[0]
    name = re.sub(r"(MT|PS)$", "", name)
    return re.sub(r"[^a-z]", "", name.lower())


@lru_cache(maxsize=16)
def _glyph_order(family: str) -> tuple[str, ...] | None:
    filename = _SYSTEM_FONTS.get(family)
    if not filename:
        return None
    try:
        from fontTools.ttLib import TTFont

        return tuple(TTFont(os.path.join(_FONTS_DIR, filename), lazy=True).getGlyphOrder())
    except Exception:  # noqa: BLE001 - no such font here: fall back below
        return None


def _glyph_name_at(index: int, family: str) -> str | None:
    order = _glyph_order(family)
    if order is not None and index < len(order):
        return order[index]
    # The standard order is safe up to the first place fonts commonly skip.
    if index < 172:
        return standardGlyphOrder[index]
    return None


def _from_code(code: int, kind: str) -> str | None:
    if kind == "symbol" and code in SYMBOL:
        return SYMBOL[code]
    if kind == "dingbats" and code in DINGBATS:
        return DINGBATS[code]
    if code < 32:
        return None
    try:
        return bytes([code]).decode("cp1252") if code < 256 else chr(code)
    except UnicodeDecodeError:
        return None


def _kind(base_font: str) -> str:
    name = base_font.lower()
    if "dingbat" in name or "wingding" in name:
        return "dingbats"
    if "symbol" in name:
        return "symbol"
    return "text"


def _differences(font) -> list[tuple[int, str]]:
    encoding = font.get("/Encoding")
    if not isinstance(encoding, pikepdf.Dictionary):
        return []
    pairs, code = [], 0
    for item in encoding.get("/Differences", []):
        if isinstance(item, pikepdf.Name):
            pairs.append((code, str(item)[1:]))
            code += 1
        else:
            code = int(item)
    return pairs


def font_map(font, ignore_existing: bool = False) -> dict[int, str] | None:
    """Code -> text for a font that needs a new map, or None if it does not.

    ignore_existing: work it out even if the font has a map already (to fill
    the gaps of a map that leaves the codes in use out).
    """
    if font.get("/Subtype") not in ("/Type1", "/TrueType", "/MMType1"):
        return None
    base = str(font.get("/BaseFont", ""))
    kind = _kind(base)
    pairs = _differences(font)
    numbered = [(c, _NUMBERED.match(n)) for c, n in pairs]
    numbered = [(c, int(m.group(2))) for c, m in numbered if m]
    family_name = base.split("+", 1)[-1]
    interleaf = family_name.startswith("Int") and not re.search(r"Symbol|Math", family_name)
    symbol_coded = {c: int(m.group(1)) for c, n in pairs if interleaf and (m := _INTERLEAF.match(n))}
    # A Symbol font with neither a map nor glyph names: its codes are
    # Symbol codes, which the converter does not know (a TI pin label's
    # "IN1-" lost its minus).
    bare_symbol = kind == "symbol" and "/Encoding" not in font
    # TI's plotting tool names the space glyph ".notdef": every gap in a
    # plot label then reads as an unknown character.
    blank_space = any(code == 32 and name == ".notdef" for code, name in pairs)
    if "/ToUnicode" in font and kind != "dingbats" and not ignore_existing:
        return None
    if not numbered and not blank_space and not symbol_coded and not bare_symbol and kind != "dingbats":
        return None

    # The number is a character code unless it cannot be one: control codes
    # mean it counts glyphs in the font program instead.
    by_glyph_index = any(n < 32 for _, n in numbered)
    family = _family(base)
    names = dict(pairs)
    first = int(font.get("/FirstChar", 0))
    last = int(font.get("/LastChar", 255))
    mapping: dict[int, str] = {}
    for code in range(first, min(last, 255) + 1):
        text = None
        name = names.get(code)
        match = _NUMBERED.match(name) if name else None
        if code in symbol_coded:
            text = _from_code(symbol_coded[code], "symbol")
        elif match:
            n = int(match.group(2))
            if by_glyph_index:
                glyph = _glyph_name_at(n, family)
                text = agl.toUnicode(glyph) if glyph else None
            else:
                text = _from_code(n, kind)
        elif name == ".notdef":
            text = " " if code == 32 else None
        elif name:
            text = (DINGBATS.get(code) if kind == "dingbats" else None) or agl.toUnicode(name) or None
        else:
            text = _from_code(code, kind)
        if text:
            mapping[code] = text
    if kind == "dingbats" and not numbered and not any(
        code in DINGBATS for code in mapping
    ):
        return None
    return mapping or None


# -- maps that point into the private use area ------------------------------ #

_HEX = r"<([0-9A-Fa-f]+)>"
_BFCHAR = re.compile(r"beginbfchar(.*?)endbfchar", re.S)
_BFRANGE = re.compile(r"beginbfrange(.*?)endbfrange", re.S)
_CODESPACE = re.compile(r"begincodespacerange(.*?)endcodespacerange", re.S)


def _utf16(hex_text: str) -> str:
    try:
        return bytes.fromhex(hex_text).decode("utf-16-be")
    except (ValueError, UnicodeDecodeError):
        return ""


def _parse_cmap(data: str) -> dict[tuple[int, int], str] | None:
    """(code width in bytes, code) -> text, or None if it is not plain."""
    mapping: dict[tuple[int, int], str] = {}
    for block in _BFCHAR.findall(data):
        for src, dst in re.findall(_HEX + r"\s*" + _HEX, block):
            mapping[(len(src) // 2, int(src, 16))] = _utf16(dst)
    for block in _BFRANGE.findall(data):
        for lo, hi, rest in re.findall(_HEX + r"\s*" + _HEX + r"\s*(<[0-9A-Fa-f]+>|\[[^\]]*\])", block):
            start, end, width = int(lo, 16), int(hi, 16), len(lo) // 2
            if end - start > 4096:
                return None
            if rest.startswith("["):
                for i, dst in enumerate(re.findall(_HEX, rest)):
                    mapping[(width, start + i)] = _utf16(dst)
            else:
                first = _utf16(rest[1:-1])
                if not first:
                    continue
                for i in range(end - start + 1):
                    mapping[(width, start + i)] = first[:-1] + chr(ord(first[-1]) + i)
    return mapping


def _private_use_fixed(font, kind: str) -> bytes | None:
    """A new map for one whose characters sit in U+F000-U+F0FF, else None.

    Symbol-style fonts map their glyphs there (U+F020 is the space, U+F06D
    Symbol's mu); the converter has no idea what those are.
    """
    if "/ToUnicode" not in font:
        return None
    try:
        data = font["/ToUnicode"].read_bytes().decode("latin-1")
    except Exception:  # noqa: BLE001 - unreadable map: leave it alone
        return None
    mapping = _parse_cmap(data)
    if not mapping:
        return None
    changed = False
    for key, text in mapping.items():
        if len(text) == 1 and 0xF000 <= ord(text) <= 0xF0FF:
            low = ord(text) - 0xF000
            new = _from_code(low, "symbol" if kind == "text" and "symbol" in str(font.get("/BaseFont", "")).lower() else kind)
            if new:
                mapping[key] = new
                changed = True
    if not changed:
        return None
    space = _CODESPACE.search(data)
    width = max(w for w, _ in mapping)
    codespace = space.group(1).strip() if space else f"<{'00' * width}> <{'FF' * width}>"
    entries = [
        f"<{code:0{w * 2}X}> <{text.encode('utf-16-be').hex().upper()}>"
        for (w, code), text in sorted(mapping.items())
        if text
    ]
    return _cmap_text(entries, codespace)


def _completed(font) -> bytes | None:
    """A simple font's map with the numbered glyphs it forgot added.

    Microchip's package drawings carry a map for the plain Latin codes while
    the text is set in codes 2, 3, 4 ... named /g39 /g54: all of it unknown.
    What the map does say is kept as it is.
    """
    if "/ToUnicode" not in font or font.get("/Subtype") not in ("/Type1", "/TrueType", "/MMType1"):
        return None
    if not any(_NUMBERED.match(name) for _, name in _differences(font)):
        return None
    decoded = font_map(font, ignore_existing=True)
    if not decoded:
        return None
    try:
        existing = _parse_cmap(font["/ToUnicode"].read_bytes().decode("latin-1")) or {}
    except Exception:  # noqa: BLE001 - unreadable map: replace it outright
        existing = {}
    merged = {code: text for (width, code), text in existing.items() if width == 1 and text}
    numbered_codes = {code for code, name in _differences(font) if _NUMBERED.match(name)}
    added = {
        code: text for code, text in decoded.items()
        if code in numbered_codes and code not in merged
    }
    if not added:
        return None
    merged.update(added)
    return _cmap(merged)


def _cmap_text(entries: list[str], codespace: str) -> bytes:
    blocks = []
    for i in range(0, len(entries), 100):
        chunk = entries[i:i + 100]
        blocks.append(f"{len(chunk)} beginbfchar\n" + "\n".join(chunk) + "\nendbfchar")
    count = codespace.count("<") // 2
    return (
        "/CIDInit /ProcSet findresource begin\n12 dict begin\nbegincmap\n"
        "/CIDSystemInfo << /Registry (Adobe) /Ordering (UCS) /Supplement 0 >> def\n"
        "/CMapName /Adobe-Identity-UCS def\n/CMapType 2 def\n"
        f"{count} begincodespacerange\n{codespace}\nendcodespacerange\n"
        + "\n".join(blocks)
        + "\nendcmap\nCMapName currentdict /CMap defineresource pop\nend\nend\n"
    ).encode("ascii")


def _cmap(mapping: dict[int, str]) -> bytes:
    entries = [
        f"<{code:02X}> <{text.encode('utf-16-be').hex().upper()}>"
        for code, text in sorted(mapping.items())
    ]
    return _cmap_text(entries, "<00> <FF>")


def _fonts(resources, seen: set, depth: int = 0):
    """Every font of a page, including those inside form XObjects (plots)."""
    if not isinstance(resources, pikepdf.Dictionary) or depth > 6:
        return
    fonts = resources.get("/Font")
    if isinstance(fonts, pikepdf.Dictionary):
        for font in fonts.values():
            key = font.objgen if font.is_indirect else id(font)
            if key not in seen:
                seen.add(key)
                yield font
    xobjects = resources.get("/XObject")
    if isinstance(xobjects, pikepdf.Dictionary):
        for xobject in xobjects.values():
            key = ("x", xobject.objgen) if xobject.is_indirect else id(xobject)
            if key in seen:
                continue
            seen.add(key)
            if xobject.get("/Subtype") == "/Form":
                yield from _fonts(xobject.get("/Resources"), seen, depth + 1)


# -- symbolic TrueType subsets with no map at all ---------------------------- #
#
# TI's pin drawings and plots set single characters in small symbolic
# TrueType subsets with no encoding and no map - the converter prints "?":
#
#   Arial_00     code 177, the minus of "IN1-": reads as "±" in every
#                encoding, but the subset still numbers its glyphs as Arial
#                does (4453 of them, all empty but one), and glyph 177 of
#                Arial is "endash".
#   SymbolMT     codes 1 and 2 of a renumbered subset: only the outline says
#                they are the degree sign and mu of the Symbol font.
#   FF10 Symbol  the font program still names its glyphs: "mu", "equal".
#
# Each character is taken from the glyph's own name when it has a real one;
# else from the installed font when the subset kept its numbering and the
# outline and width match; else, for Symbol, from the one glyph of the
# installed Symbol font with the very same width and outline box.

_SYMBOLIC = 4  # /Flags bit 3
_GENERIC_NAME = re.compile(r"^(\.notdef|glyph\d+|uni[Ff]0[0-9A-Fa-f]{2}|g\d+|G\d+|c\d+)$")
_SYMBOL_FONT = "symbol.ttf"


@lru_cache(maxsize=16)
def _system_font(filename: str):
    try:
        from fontTools.ttLib import TTFont

        return TTFont(os.path.join(_FONTS_DIR, filename), lazy=True)
    except Exception:  # noqa: BLE001 - no such font here
        return None


def _code_glyphs(tt) -> dict[int, str]:
    """Code -> glyph name from a symbolic TrueType font's own cmap."""
    out: dict[int, str] = {}
    for table in tt["cmap"].tables:
        if (table.platformID, table.platEncID) == (3, 0):
            for uni, name in table.cmap.items():
                if 0xF000 <= uni <= 0xF0FF:
                    out.setdefault(uni - 0xF000, name)
                elif uni < 0x100:
                    out.setdefault(uni, name)
        elif (table.platformID, table.platEncID) == (1, 0):
            for code, name in table.cmap.items():
                out.setdefault(code, name)
    return out


def _metrics(tt, name: str, width: float | None = None) -> tuple[float, ...] | None:
    """Width and outline box of a glyph, in ems; None for an empty glyph.

    width: the PDF's own, for subsets whose hmtx table was cut short.
    """
    glyph = tt["glyf"][name]
    if not glyph.numberOfContours:
        return None
    upm = tt["head"].unitsPerEm
    box = (glyph.xMin, glyph.yMin, glyph.xMax, glyph.yMax)
    if width is None:
        width = tt["hmtx"][name][0] / upm
    return (width, *(v / upm for v in box))


def _pdf_width(font, code: int) -> float | None:
    widths = font.get("/Widths")
    first = int(font.get("/FirstChar", 0))
    try:
        return float(widths[code - first]) / 1000 if widths is not None and code >= first else None
    except (IndexError, TypeError, ValueError):
        return None


def _same(a, b, tolerance: float) -> bool:
    return a is not None and b is not None and all(abs(x - y) <= tolerance for x, y in zip(a, b))


@lru_cache(maxsize=1)
def _symbol_shapes() -> list[tuple[tuple[float, ...], str]]:
    """(metrics, text) of every glyph of the installed Symbol font."""
    font = _system_font(_SYMBOL_FONT)
    if font is None:
        return []
    out = []
    for code, name in _code_glyphs(font).items():
        metrics = _metrics(font, name)
        text = _from_code(code, "symbol")
        if metrics and text:
            out.append((metrics, text))
    return out


def _by_shape(metrics) -> str | None:
    found = {text for shape, text in _symbol_shapes() if _same(shape, metrics, 0.005)}
    return found.pop() if len(found) == 1 else None


def _unmapped_symbolic(font) -> bytes | None:
    if font.get("/Subtype") != "/TrueType" or "/ToUnicode" in font or "/Encoding" in font:
        return None
    descriptor = font.get("/FontDescriptor")
    if not isinstance(descriptor, pikepdf.Dictionary) or not int(descriptor.get("/Flags", 0)) & _SYMBOLIC:
        return None
    program = descriptor.get("/FontFile2")
    if program is None:
        return None
    base = str(font.get("/BaseFont", ""))
    filename = _SYSTEM_FONTS.get(_family(base))
    system = _system_font(filename) if filename else None
    try:
        import io

        from fontTools.ttLib import TTFont

        tt = TTFont(io.BytesIO(program.read_bytes()))
        order = tt.getGlyphOrder()
        index = {name: i for i, name in enumerate(order)}
        mapping: dict[int, str] = {}
        for code, name in _code_glyphs(tt).items():
            text = None
            metrics = _metrics(tt, name, _pdf_width(font, code))
            if not _GENERIC_NAME.match(name):
                text = agl.toUnicode(name)
                if text and any(0xE000 <= ord(ch) <= 0xF8FF for ch in text):
                    text = None
            elif system is not None and len(order) >= 258:
                gid = index.get(name)
                system_order = system.getGlyphOrder()
                if not gid or gid >= len(system_order):
                    continue
                system_name = system_order[gid]
                if not _same(metrics, _metrics(system, system_name), 0.02):
                    return None  # another version of the font, or another font
                text = agl.toUnicode(system_name)
            elif _kind(base) == "symbol":
                text = _by_shape(metrics)
            if text:
                mapping[code] = text
    except Exception:  # noqa: BLE001 - a font program we cannot read
        return None
    return _cmap(mapping) if mapping else None


def fix_fonts(source: str, target: str, password: str = "") -> int:
    """Write `target` with maps for the fonts that need them; return how many.

    Nothing is written when no font needs a map. Raises pikepdf.PdfError
    (and the like) when the file cannot be read - the caller converts the
    original then.
    """
    fixed = 0
    with pikepdf.open(source, password=password or "") as pdf:
        seen: set = set()
        for page in pdf.pages:
            for font in _fonts(page.obj.get("/Resources"), seen):
                mapping = font_map(font)
                if mapping:
                    font["/ToUnicode"] = pdf.make_stream(_cmap(mapping))
                    fixed += 1
                    continue
                completed = _completed(font)
                if completed:
                    font["/ToUnicode"] = pdf.make_stream(completed)
                    fixed += 1
                    continue
                remapped = _private_use_fixed(font, _kind(str(font.get("/BaseFont", ""))))
                if remapped:
                    font["/ToUnicode"] = pdf.make_stream(remapped)
                    fixed += 1
                    continue
                kept = _unmapped_symbolic(font)
                if kept:
                    font["/ToUnicode"] = pdf.make_stream(kept)
                    fixed += 1
        if fixed:
            # Saved without encryption: the copy only lives in a temp folder
            # for the converter, which then needs no password for it.
            pdf.save(target, encryption=False)
    return fixed
