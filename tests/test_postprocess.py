"""Clean-ups of the converter's Markdown (postprocess.py)."""

import converter
import i18n
from converter import ConvertWorker, Job
from postprocess import drop_figure_tables, is_figure_table


def grid(rows, cols, filled=None):
    """An HTML table like the converter writes; `filled` maps (r, c) -> text."""
    filled = filled or {}
    out = ["<table>"]
    for r in range(rows):
        out.append("  <tr>")
        for c in range(cols):
            out.append(f"    <td>{filled.get((r, c), ' ')}</td>")
        out.append("  </tr>")
    out.append("</table>")
    return "\n".join(out)


PLOT = grid(10, 10, {(0, 0): "0", (9, 0): "100", (9, 9): "VIN = 5 V", (5, 5): "25°C"})
REAL = grid(4, 4, {(r, c): f"v{r}{c}" for r in range(4) for c in range(4)})


def test_a_plot_is_told_from_a_real_table():
    assert is_figure_table(PLOT)
    assert not is_figure_table(REAL)


def test_small_tables_are_left_alone():
    assert not is_figure_table(grid(2, 3))  # too few cells to judge


def test_plot_becomes_a_note_with_its_page():
    md = f"---- page 7 ----\n\nText before.\n\n{PLOT}\n\nFigure 6-3. Dropout Voltage vs Output Current\n\n{REAL}\n"

    out, dropped = drop_figure_tables(md)

    assert dropped == 1
    assert "<td>0</td>" not in out and "25°C" not in out
    assert "*" + "[Figure omitted, page 7]" + "*" in out
    assert "Figure 6-3. Dropout Voltage vs Output Current" in out, "the caption stays"
    assert REAL in out and "Text before." in out


def test_note_without_page_separators():
    out, _ = drop_figure_tables(f"{PLOT}\n")

    assert "*" + "[Figure omitted]" + "*" in out


def test_caption_inside_the_table_is_kept_in_the_note():
    plot = grid(10, 10, {(0, 0): "Figure 28. Dropout voltage vs junction temperature   VI-Vo (V)  -75 2"})

    out, _ = drop_figure_tables(plot)

    assert out.startswith("*" + "[Figure omitted]" + ": Figure 28. Dropout voltage vs junction temperature")


def test_sentences_in_a_flow_chart_survive():
    chart = grid(6, 5, {
        (0, 0): "Measure temperature (oversampling set by osrs_t)",
        (2, 1): "Copy filter memory to output registers",
        (4, 3): "Yes",
    })

    out, _ = drop_figure_tables(chart)

    assert "- Measure temperature (oversampling set by osrs_t)" in out
    assert "- Copy filter memory to output registers" in out
    assert "Yes" not in out


def test_tick_labels_left_around_the_plot_go_too():
    md = (f"Intro sentence stays here.\n\n7.0\n\n5.0\n\nCAPACITANCE (pF)\n\n{PLOT}\n\n"
          "0.2 0.3 0.5 1.0 2.0\n\nREVERSE BIAS VOLTAGE (VOLTS)\n\nFigure 3. Capacitance\n\nThe next paragraph.\n")

    out, _ = drop_figure_tables(md)

    for gone in ("7.0", "5.0", "CAPACITANCE (pF)", "0.2 0.3 0.5", "REVERSE BIAS VOLTAGE"):
        assert gone not in out, gone
    for kept in ("Intro sentence stays here.", "Figure 3. Capacitance", "The next paragraph."):
        assert kept in out, kept


def test_numbers_far_from_any_figure_are_untouched():
    md = f"{REAL}\n\n4.20\n\nplain text\n"

    assert drop_figure_tables(md) == (md, 0)


# -- in the worker ---------------------------------------------------------------- #


def worker_for(tmp_path, clean, html_tables=True):
    pdf = tmp_path / "part.pdf"
    options = {"format": "markdown"}
    if html_tables:
        options["markdown_with_html"] = True
    return Job(str(pdf), str(tmp_path), "part.pdf"), ConvertWorker(
        [], str(tmp_path), options, 30, None, clean_figures=clean
    )


def test_worker_cleans_the_markdown_it_wrote(qapp, tmp_path):
    job, worker = worker_for(tmp_path, clean=True)
    (tmp_path / "part.md").write_text(f"{PLOT}\n", encoding="utf-8")

    worker._postprocess(job)

    assert "<table>" not in (tmp_path / "part.md").read_text(encoding="utf-8")


def test_worker_leaves_it_when_switched_off_or_plain(qapp, tmp_path):
    for clean, html in ((False, True), (True, False)):
        job, worker = worker_for(tmp_path, clean=clean, html_tables=html)
        (tmp_path / "part.md").write_text(f"{PLOT}\n", encoding="utf-8")

        worker._postprocess(job)

        assert "<table>" in (tmp_path / "part.md").read_text(encoding="utf-8")


def test_a_missing_markdown_file_is_no_error(qapp, tmp_path):
    job, worker = worker_for(tmp_path, clean=True)

    worker._postprocess(job)  # e.g. only JSON was asked for


# -- images ------------------------------------------------------------------------ #

from postprocess import REPEATED_IMAGE, tidy_images


def images(tmp_path, files):
    folder = tmp_path / "doc_images"
    folder.mkdir()
    for name, data in files.items():
        (folder / name).write_bytes(data)
    return folder


def link(name):
    return f"![](<doc_images/{name}>)"


def test_identical_files_become_one(tmp_path):
    folder = images(tmp_path, {"imageFile1.png": b"A", "imageFile2.png": b"A", "imageFile3.png": b"B"})
    md = f"{link('imageFile1.png')}\n{link('imageFile2.png')}\n{link('imageFile3.png')}\n"

    new, removed, deleted = tidy_images(md, folder)

    assert new == f"{link('imageFile1.png')}\n{link('imageFile1.png')}\n{link('imageFile3.png')}\n"
    assert (removed, deleted) == (0, 1)
    assert sorted(p.name for p in folder.iterdir()) == ["imageFile1.png", "imageFile3.png"]


def test_a_picture_on_every_page_is_a_decoration(tmp_path):
    files = {f"imageFile{i}.png": b"LOGO" for i in range(1, REPEATED_IMAGE + 1)}
    files["imageFile99.png"] = b"FIGURE"
    folder = images(tmp_path, files)
    md = "\n".join(link(n) for n in files) + "\n"

    new, removed, _ = tidy_images(md, folder)

    assert removed == REPEATED_IMAGE
    assert new.strip() == link("imageFile99.png")
    assert [p.name for p in folder.iterdir()] == ["imageFile99.png"]


def test_files_nothing_links_to_are_deleted(tmp_path):
    folder = images(tmp_path, {"imageFile1.png": b"A", "imageFile2.png": b"B"})

    _, _, deleted = tidy_images(f"{link('imageFile1.png')}\n", folder)

    assert deleted == 1 and not (folder / "imageFile2.png").exists()


def test_files_other_outputs_use_are_kept(tmp_path):
    folder = images(tmp_path, {"imageFile1.png": b"A", "imageFile2.png": b"B"})

    tidy_images(f"{link('imageFile1.png')}\n", folder, keep={"imageFile2.png"})

    assert (folder / "imageFile2.png").exists()


def test_an_emptied_folder_goes(tmp_path):
    folder = images(tmp_path, {"imageFile1.png": b"A"})

    tidy_images("no pictures left\n", folder)

    assert not folder.exists()


# -- escaped signs ------------------------------------------------------------------ #

def test_escaped_signs_come_back():
    from postprocess import unescape_signs

    md = "t = (adc_T &gt;&gt; 4); VDD &lt; 3.6 V; R &amp; D; x &lt;&lt; 2"

    out, n = unescape_signs(md)

    assert out == "t = (adc_T >> 4); VDD < 3.6 V; R & D; x << 2"
    assert n == 6


def test_signs_that_could_be_markup_stay_escaped():
    from postprocess import unescape_signs

    # Any "<" before a letter opens a tag in HTML - inside a table it would
    # swallow cells. A run of them stays whole.
    md = "jump to &lt;instr&gt; here; &lt;/td&gt; (1&lt;&lt;EEMPE); &amp;lt; is how &lt; is written"

    out, _ = unescape_signs(md)

    assert out == "jump to &lt;instr> here; &lt;/td> (1&lt;&lt;EEMPE); &amp;lt; is how < is written"


# -- scans --------------------------------------------------------------------------- #

def test_a_scan_has_no_text():
    from postprocess import looks_scanned

    scan = "\n\n---- page 1 ----\n\n![image 1](a_images/imageFile1.png)\n\n---- page 2 ----\n\n"
    real = scan + "VRRM Repetitive peak reverse voltage 100 V " * 2

    assert looks_scanned(scan, 2)
    assert not looks_scanned(real, 2)


# -- drawings that are not grids: label bags and label runs -------------------------- #

def test_a_cell_stuffed_with_labels_is_a_drawing():
    # ESP32's peripheral schematic: one cell, dozens of net names.
    labels = "<br><br>".join(["EN", "TXD RXD", "IO0", "IO21 IO19 IO18 IO5", "GND", "R2 100R", "C1 10uF"] * 5)
    md = ("<table>\n  <tr>\n    <th>MTDI should be kept at a low electric level when powering up the module."
          f"<br><br>{labels}</th>\n  </tr>\n</table>")

    out, n = drop_figure_tables("\n\n---- page 35 ----\n\n" + md)

    assert n == 1
    assert "IO21" not in out
    assert "MTDI should be kept at a low electric level" in out


def test_a_cell_of_examples_is_kept():
    # MCP73831's ordering examples look like labels but are content.
    lines = ["a) MCP73831-2ACI/OT: 4.20V VREG, Options AC, 5LD SOT23 package",
             "b) MCP73831T-2ACI/OT: Tape and Reel, 4.20V VREG",
             "c) MCP73831-3ACI/MC: 4.35V VREG, Options AC, 8LD DFN package"] + ["X"] * 25
    md = "<table>\n  <tr>\n    <td>" + "<br><br>".join(lines) + "</td>\n  </tr>\n</table>"

    out, n = drop_figure_tables(md)

    assert n == 0 and out == md


def test_a_run_of_tick_labels_is_a_drawing():
    ticks = "\n\n".join(["100", "0.7", "0.6", "2nd line", "0.5", "0.4", "10", "0.3", "0.2", "0.1",
                         "0", "Axis Title", "1st line", "1000"])
    md = ("Some text before the plot that is a real sentence of the datasheet.\n\n"
          "---- page 4 ----\n\n" + ticks + "\n\nFig. 2 - Pulse Length and Sensitivity\n\n"
          "The next real paragraph, written as a sentence for the reader.")

    out, n = drop_figure_tables(md)

    assert n == 1
    assert "Axis Title" not in out
    assert "*[" in out and "Fig. 2 - Pulse Length and Sensitivity" in out
    assert "---- page 4 ----" in out
    assert out.startswith("Some text before") and out.endswith("for the reader.")


def test_table_rows_set_as_text_are_kept():
    # NEO-6: a table that came out as short paragraphs - rows, not ticks.
    rows = "\n\n".join(["VCC = 3.6 V16 / 1.95 V17", "Max. supply current 15 Iccp All 67 mA",
                        "Icc Acquisition All 47 mA", "NEO-6G/Q/T 40 mA NEO-6M/P/V 39 mA",
                        "Icc Tracking", "(Max Performance mode)", "VCC = 3.0 V16 / 1.8 V17",
                        "Average supply current18", "NEO-6G/Q/T 38 mA NEO-6M/P/V 37 mA",
                        "Icc Tracking", "(Eco mode)", "VCC = 3.0 V16 / 1.8 V17", "Backup current 22 µA"])

    out, n = drop_figure_tables(rows)

    assert n == 0 and out == rows


def test_labels_around_nested_tables_are_a_drawing():
    # ESP32's module dimensions: labels in the outer cell, around nested tables.
    before = "<br><br>".join(["18.00±0.15", "0.85", "0.90", "9.68", "ESP32-WROOM-32 Dimensions", "3.10±0.15"] * 3)
    after = "<br><br>".join(["0.1", "Unit: mm", "4.10", "25.50±0.15", "11.43", "8.89"] * 3)
    nested = "<table>\n  <tr>\n    <td>0.1</td>\n  </tr>\n</table>"
    md = f"<table>\n  <tr>\n    <th>{before}{nested}{after}</th>\n  </tr>\n</table>"

    out, n = drop_figure_tables("---- page 36 ----\n\n" + md)

    assert n == 1 and "25.50" not in out


def test_real_table_wrapped_in_an_outer_cell_stays():
    # Data a converter nested in one outer cell: the cells are inside.
    rows = "".join(f"<tr><td>Param {i}</td><td>{i}.5</td><td>V</td></tr>" for i in range(30))
    md = f"<table>\n  <tr>\n    <td><table>{rows}</table></td>\n  </tr>\n</table>"

    out, n = drop_figure_tables(md)

    assert n == 0 and out == md


def test_memory_maps_are_kept():
    # PIC's register file map: a drawing, but the addresses matter.
    labels = "<br><br>".join(f"{a:02X}h<br><br>REG{a}" for a in range(20))
    md = f"<table>\n  <tr>\n    <td>{labels}</td>\n  </tr>\n</table>"

    out, n = drop_figure_tables(md)

    assert n == 0


# -- drawing numbers, captions, pin lists ------------------------------------------ #

def test_a_numbered_drawing_goes_but_its_captions_and_notes_stay():
    # Nexperia's waveform page: drawing numbers, labels, a note, captions.
    cell = "<br><br>".join([
        "mna557", "SHCP input", "Q7S output", "tPLH tPHL", "tW", "1/fmax", "VM", "VOH", "GND",
        "Measurement points are given in Table 8. VOL and VOH are typical output voltage levels.",
        "Fig. 6. Shift clock pulse, maximum frequency and input to output propagation delays",
        "mna558", "STCP input", "Qn output", "tsu", "VM", "VI",
        "Fig. 7. Storage clock to output propagation delays",
    ])
    md = f"<table>\n  <tr>\n    <th>{cell}</th>\n  </tr>\n</table>"

    out, n = drop_figure_tables("---- page 11 ----\n\n" + md)

    assert n == 1 and "mna557" not in out and "tPLH" not in out
    assert "Fig. 6. Shift clock pulse" in out and "Fig. 7. Storage clock" in out
    assert "Measurement points are given in Table 8." in out


def test_a_numbered_drawing_keeps_its_dimension_table():
    dims = ("<table><tr><td>UNIT</td><td>A</td><td>A1</td><td>bp</td></tr>"
            "<tr><td>mm</td><td>1.1 0.9</td><td>0.1</td><td>0.48 0.38</td></tr></table>")
    labels = "<br><br>".join(["sot023_po", "bp", "D", "e1", "detail X", "HE", "w M", "0 1 2 mm scale"])
    md = f"<table>\n  <tr>\n    <th>{labels}{dims}</th>\n  </tr>\n</table>"

    out, n = drop_figure_tables(md)

    assert n == 1 and "detail X" not in out
    assert "<td>0.48 0.38</td>" in out


def test_a_small_table_by_a_figure_caption_is_the_figure():
    cell = "<br><br>".join(["50 150", "0", "25", "1 ~ 3 ℃/s", "200", "250", "Cooling zone", "217", "100 250"])
    md = f"<table>\n  <tr>\n    <th>{cell}</th>\n  </tr>\n</table>\n\n###### Figure 9: Reflow Profile"

    out, n = drop_figure_tables(md)

    assert n == 1 and "Cooling zone" not in out and "Figure 9: Reflow Profile" in out


def test_a_table_set_as_lines_without_a_caption_stays():
    # DS18B20's DC characteristics: short lines, but data.
    md = "\n".join(["Parasite power", "+3.0 +5.5", "V Local power +3.0 VDD", "(Notes 1, 2)",
                    "Pullup Supply Voltage VPU", "-10°C to +85°C", "±0.5", "Thermometer Error tERR"])

    out, n = drop_figure_tables("Some text.\n\n" + md + "\n\nMore text follows here, as a sentence.")

    assert n == 0 and "±0.5" in out


def test_figure_hint_only_when_figures_were_dropped():
    from postprocess import FIGURE_HINT, add_figure_hint

    with_figure = "Text.\n\n*[Figure omitted, page 3]: Fig 1. Pinout*"
    out = add_figure_hint(with_figure)

    assert out.startswith(FIGURE_HINT) and out.endswith(with_figure)
    assert add_figure_hint(out) == out, "added once"
    assert add_figure_hint("Text without drawings.") == "Text without drawings."


# -- plain Markdown tables ------------------------------------------------------------ #

def test_html_tables_become_pipe_tables_with_split_limits():
    from postprocess import tables_to_markdown

    md = ("Text.\n\n<table>\n  <tr>\n    <th>PARAMETER</th>\n    <th colspan=\"2\">CONDITIONS</th>\n"
          "    <th>MIN</th><th>TYP</th><th>MAX</th>\n  </tr>\n  <tr>\n"
          "    <td rowspan=\"2\">VOS<br><br></td>\n    <td>VS = 5 V</td>\n    <td>LM358</td>\n"
          "    <td> </td><td>3</td><td>7</td>\n  </tr>\n  <tr>\n    <td>TA = 0°C to 70°C</td>\n"
          "    <td>a|b</td>\n    <td> </td><td> </td><td>9</td>\n  </tr>\n</table>\n\nMore.")

    out = tables_to_markdown(md)

    assert "<table" not in out and "<td" not in out
    assert out.startswith("Text.") and out.endswith("More.")
    lines = [l for l in out.split("\n") if l.startswith("|")]
    assert lines[0] == "|PARAMETER|CONDITIONS||MIN|TYP|MAX|"
    assert lines[1] == "|---|---|---|---|---|---|"
    assert lines[2] == "|VOS|VS = 5 V|LM358||3|7|"
    assert lines[3] == "||TA = 0°C to 70°C|a\\|b|||9|", "rowspan leaves its place empty"
