"""fontfix.py: character maps for fonts the converter could only print as "?"."""

import pikepdf
import pytest

import converter
import fontfix
from converter import ConvertWorker, Job


def font(pdf, base, differences, tounicode=None, subtype="/Type1"):
    f = pikepdf.Dictionary(
        Type=pikepdf.Name.Font,
        Subtype=pikepdf.Name(subtype),
        BaseFont=pikepdf.Name(base),
        FirstChar=1,
        LastChar=255,
        Encoding=pikepdf.Dictionary(
            Type=pikepdf.Name.Encoding,
            Differences=pikepdf.Array(
                [x if isinstance(x, int) else pikepdf.Name(x) for x in differences]
            ),
        ),
    )
    if tounicode is not None:
        f.ToUnicode = pdf.make_stream(tounicode)
    return pdf.make_indirect(f)


def make_pdf(path, fonts_and_text):
    """One page; each (font, raw string) drawn on a line of its own."""
    pdf = pikepdf.new()
    names, ops = {}, []
    for i, (make, text) in enumerate(fonts_and_text):
        names[f"/F{i}"] = make(pdf)
        ops.append(f"BT /F{i} 12 Tf 50 {780 - 30 * i} Td ({text}) Tj ET".encode("latin-1"))
    page = pikepdf.Page(pikepdf.Dictionary(
        Type=pikepdf.Name.Page,
        MediaBox=[0, 0, 595, 842],
        Resources=pikepdf.Dictionary(Font=pikepdf.Dictionary(names)),
        Contents=pdf.make_stream(b"\n".join(ops)),
    ))
    pdf.pages.append(page)
    pdf.save(path)
    return path


def mapping_of(pdf_path):
    with pikepdf.open(pdf_path) as pdf:
        return [fontfix.font_map(f, ignore_existing=True) for f in pdf.pages[0].Resources.Font.values()]


# -- what each kind of font decodes to ---------------------------------------------- #

# Infineon: the number is the character code, in a font with no map at all.
INFINEON = [1, "/G72", "/G69", "/G88", "/G70", "/G69", "/G84", "/G174"]
# TI plot labels: Symbol font, numbers are Symbol codes.
TI_SYMBOL = [45, "/c45", 109, "/c109", 176, "/c176"]
# Microchip: numbers count glyphs in the font program (standard order).
GLYPH_INDEX = [2, "/g27", "/g16", "/g47", "/g72", "/g68", "/g71", "/g3"]


def test_numbers_that_are_character_codes(tmp_path):
    pdf = make_pdf(tmp_path / "a.pdf", [(lambda p: font(p, "/ABCDEF+Arial050", INFINEON), "\x01")])

    m = mapping_of(pdf)[0]

    assert "".join(m[c] for c in range(1, 8)) == "HEXFET®"


def test_symbol_font_numbers_are_symbol_codes(tmp_path):
    pdf = make_pdf(tmp_path / "a.pdf", [(lambda p: font(p, "/XYZ+Symbol", TI_SYMBOL), "-")])

    m = mapping_of(pdf)[0]

    assert (m[45], m[109], m[176]) == ("−", "μ", "°")


def test_numbers_below_32_count_glyphs(tmp_path):
    # A family not installed anywhere: the standard glyph order decides.
    pdf = make_pdf(tmp_path / "a.pdf", [(lambda p: font(p, "/XYZ+NoSuchSans", GLYPH_INDEX), "\x02")])

    m = mapping_of(pdf)[0]

    assert "".join(m[c] for c in range(2, 9)) == "8-Lead "


def test_space_named_notdef_is_a_space(tmp_path):
    pdf = make_pdf(tmp_path / "a.pdf", [(lambda p: font(p, "/Helvetica", [32, "/.notdef"]), "a b")])

    m = mapping_of(pdf)[0]

    assert m[32] == " " and m[ord("a")] == "a"


def test_dingbat_bullet_is_a_bullet_not_the_letter_l(tmp_path):
    wrong = fontfix._cmap({0x6C: "l"})
    pdf = make_pdf(tmp_path / "a.pdf", [(lambda p: font(p, "/XYZ+LinearDingbats", [], wrong), "l")])
    out = tmp_path / "fixed.pdf"

    assert fontfix.fix_fonts(str(pdf), str(out)) == 1
    with pikepdf.open(out) as fixed:
        f = list(fixed.pages[0].Resources.Font.values())[0]
        assert fontfix._parse_cmap(f.ToUnicode.read_bytes().decode())[(1, 0x6C)] == "●"


def test_private_use_targets_become_characters(tmp_path):
    pua = fontfix._cmap_text(["<0003> <F020>", "<0050> <F06D>", "<0071> <F0B0>"], "<0000> <FFFF>")
    pdf = make_pdf(tmp_path / "a.pdf", [(lambda p: font(p, "/XYZ+Symbol", [], pua), "x")])
    out = tmp_path / "fixed.pdf"

    assert fontfix.fix_fonts(str(pdf), str(out)) == 1
    with pikepdf.open(out) as fixed:
        f = list(fixed.pages[0].Resources.Font.values())[0]
        m = fontfix._parse_cmap(f.ToUnicode.read_bytes().decode())
        assert (m[(2, 3)], m[(2, 0x50)], m[(2, 0x71)]) == (" ", "μ", "°")


def test_a_map_missing_the_codes_in_use_is_completed(tmp_path):
    partial = fontfix._cmap({0x41: "A"})
    differences = [2, "/g39", "/g54", "/g3"]  # glyph indices: D, S, space
    pdf = make_pdf(tmp_path / "a.pdf", [(lambda p: font(p, "/XYZ+NoSuchSans", differences, partial), "\x02")])
    out = tmp_path / "fixed.pdf"

    assert fontfix.fix_fonts(str(pdf), str(out)) == 1
    with pikepdf.open(out) as fixed:
        f = list(fixed.pages[0].Resources.Font.values())[0]
        m = fontfix._parse_cmap(f.ToUnicode.read_bytes().decode())
        assert (m[(1, 0x41)], m[(1, 2)], m[(1, 3)], m[(1, 4)]) == ("A", "D", "S", " ")


# -- what is left alone ------------------------------------------------------------------ #


def test_a_healthy_pdf_is_not_copied(tmp_path):
    pdf = make_pdf(tmp_path / "a.pdf", [(lambda p: font(p, "/Helvetica", [65, "/A"]), "A")])
    out = tmp_path / "fixed.pdf"

    assert fontfix.fix_fonts(str(pdf), str(out)) == 0
    assert not out.exists()


def test_fonts_with_a_good_map_keep_it(tmp_path):
    good = fontfix._cmap({c: chr(c) for c in range(32, 127)})
    pdf = make_pdf(tmp_path / "a.pdf", [(lambda p: font(p, "/ABC+Arial", [72, "/G72"], good), "H")])

    assert fontfix.fix_fonts(str(pdf), str(tmp_path / "x.pdf")) == 0


def test_original_is_never_changed(tmp_path):
    pdf = make_pdf(tmp_path / "a.pdf", [(lambda p: font(p, "/ABCDEF+Arial050", INFINEON), "\x01")])
    before = pdf.read_bytes()

    fontfix.fix_fonts(str(pdf), str(tmp_path / "fixed.pdf"))

    assert pdf.read_bytes() == before


# -- through the real converter ------------------------------------------------------------ #


@pytest.mark.skipif(
    converter.java_executable() is None or converter.jar_path() is None,
    reason="needs Java and the opendataloader-pdf JAR",
)
def test_unreadable_text_comes_out_readable(tmp_path, qapp):
    pdf = make_pdf(tmp_path / "irf.pdf", [
        (lambda p: font(p, "/ABCDEF+Arial050", INFINEON), "".join(chr(c) for c in range(1, 8))),
        (lambda p: font(p, "/XYZ+Symbol", TI_SYMBOL), "-40 \xb0"),
    ])
    out = tmp_path / "out"
    worker = ConvertWorker([Job(str(pdf), str(out), "irf.pdf")], str(out),
                           {"format": "markdown", "image_output": "off",
                            "replace_invalid_chars": "?"}, 120, None)
    result, log = {}, []
    worker.finished.connect(result.update)
    worker.log.connect(log.append)
    worker.run()
    assert result["ok"] == 1, log

    md = (out / "irf.md").read_text(encoding="utf-8")
    assert "HEXFET®" in md
    assert "−40 °" in md
    assert "?" not in md
    assert (tmp_path / "irf.pdf").exists() and not (out / "irf.pdf").exists()
