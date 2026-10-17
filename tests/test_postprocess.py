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
    assert "*" + i18n.tr("figure.omitted_page", page="7") + "*" in out
    assert "Figure 6-3. Dropout Voltage vs Output Current" in out, "the caption stays"
    assert REAL in out and "Text before." in out


def test_note_without_page_separators():
    out, _ = drop_figure_tables(f"{PLOT}\n")

    assert "*" + i18n.tr("figure.omitted") + "*" in out


def test_caption_inside_the_table_is_kept_in_the_note():
    plot = grid(10, 10, {(0, 0): "Figure 28. Dropout voltage vs junction temperature   VI-Vo (V)  -75 2"})

    out, _ = drop_figure_tables(plot)

    assert out.startswith("*" + i18n.tr("figure.omitted") + ": Figure 28. Dropout voltage vs junction temperature")


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
