"""Removing files, help marks, resetting options, the password eye,
favourite folders and the way to the log."""

import json

import pytest
from PySide6.QtCore import QPoint, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QLineEdit

import gui
import i18n
from tests.conftest import must_be_complete


def pdfs(tmp_path, *names):
    paths = []
    for name in names:
        path = tmp_path / name
        path.write_bytes(b"%PDF")
        paths.append(str(path))
    return paths


def select(window, *rows):
    window.file_list.clearSelection()
    for row in rows:
        window.file_list.item(row).setSelected(True)


# -- removing single files ------------------------------------------------------ #


def test_remove_takes_only_the_selected_files(window, tmp_path):
    a, b, c = pdfs(tmp_path, "a.pdf", "b.pdf", "c.pdf")
    window.add_paths([a, b, c])
    assert not window.remove_btn.isEnabled(), "nothing selected yet"

    select(window, 1)
    assert window.remove_btn.isEnabled()
    window.remove_btn.click()

    assert window.inputs == [a, c]
    assert (tmp_path / "b.pdf").exists(), "only the list entry goes, not the file"


def test_several_at_once(window, tmp_path):
    a, b, c = pdfs(tmp_path, "a.pdf", "b.pdf", "c.pdf")
    window.add_paths([a, b, c])

    select(window, 0, 2)
    window.remove_selected()

    assert window.inputs == [b]


def test_delete_key_removes_and_moves_on(window, tmp_path):
    a, b, c = pdfs(tmp_path, "a.pdf", "b.pdf", "c.pdf")
    window.add_paths([a, b, c])
    window.show()
    window.file_list.setFocus()
    select(window, 0)

    QTest.keyClick(window.file_list, Qt.Key.Key_Delete)
    assert window.inputs == [b, c]
    # The selection moved to the next file: Delete again takes that one.
    QTest.keyClick(window.file_list, Qt.Key.Key_Delete)
    assert window.inputs == [c]


def test_removing_the_last_file_brings_the_drop_zone_back(window, tmp_path):
    (a,) = pdfs(tmp_path, "a.pdf")
    window.add_paths([a])

    select(window, 0)
    window.remove_selected()

    assert window.inputs == []
    assert window.drop.isVisibleTo(window) and not window.file_list.isVisibleTo(window)
    assert not window.run_btn.isEnabled()


def test_nothing_is_removed_during_a_run(window, tmp_path):
    a, b = pdfs(tmp_path, "a.pdf", "b.pdf")
    window.add_paths([a, b])
    select(window, 0)
    window.thread = object()  # a run in progress
    window._set_busy(True, 2)

    assert not window.remove_btn.isEnabled()
    window.remove_selected()
    assert window.inputs == [a, b]
    window.thread = None


# -- help marks ------------------------------------------------------------------ #


HELP_KEYS = [
    "format.tagged_pdf_tooltip", "format.pdf_tooltip",
    "images.tooltip", "dpi.tooltip", "pages.tooltip", "timeout.tooltip",
    "struct.tooltip", "sanitize.tooltip", "page_sep.tooltip", "plain_md.tooltip",
    "clean_figures.tooltip",
    "reading_order.tooltip", "tables.tooltip", "image_format.tooltip",
    "threads.tooltip", "password.tooltip", "space_ratio.tooltip",
    *(["hybrid.tooltip", "hybrid_url.tooltip"] if gui.AI_MODE else []),
    "line_breaks.tooltip", "header_footer.tooltip", "strikethrough.tooltip",
    "hidden_text.tooltip",
]


def marks(window):
    return window.findChildren(gui.HelpMark)


def test_every_setting_has_its_question_mark(window):
    texts = [m.accessibleDescription() for m in marks(window)]

    assert sorted(texts) == sorted(gui.tr(key) for key in HELP_KEYS)


def test_every_advanced_setting_is_explained(window):
    advanced = [m for m in marks(window) if window.advanced.isAncestorOf(m)]

    assert len(advanced) == (12 if gui.AI_MODE else 10)


def test_help_text_wraps_and_keeps_its_paragraphs(window):
    mark = next(m for m in marks(window) if m.accessibleDescription() == gui.tr("tables.tooltip"))

    tip = mark.help_text
    assert tip.startswith("<p>") and tip.count("<p>") == 3


def hover(widget, inside=True):
    from PySide6.QtCore import QEvent, QPointF
    from PySide6.QtGui import QEnterEvent

    if inside:
        event = QEnterEvent(QPointF(5, 5), QPointF(5, 5), QPointF(5, 5))
        QApplication.sendEvent(widget, event)
    else:
        QApplication.sendEvent(widget, QEvent(QEvent.Type.Leave))


def test_hovering_opens_the_help_at_once_under_the_mark(window):
    window.show()
    mark = marks(window)[0]
    popup = gui.help_popup()

    hover(mark)

    assert popup.isVisible(), "no waiting for a tooltip delay"
    assert popup.text() == mark.help_text
    below = mark.mapToGlobal(QPoint(0, mark.height()))
    assert popup.y() >= below.y() or popup.y() + popup.height() <= mark.mapToGlobal(QPoint(0, 0)).y()

    hover(mark, inside=False)
    assert not popup.isVisible()


def test_the_help_does_not_come_up_a_second_time(window):
    """Qt's own tooltip used to open again at the pointer - the jump."""
    mark = marks(window)[0]

    assert mark.toolTip() == ""


def test_folding_more_options_closes_its_help(window):
    window.show()
    window.more_btn.setChecked(True)
    mark = next(m for m in marks(window) if window.advanced.isAncestorOf(m))
    hover(mark)
    assert gui.help_popup().isVisible()

    window.more_btn.setChecked(False)

    assert not gui.help_popup().isVisible()


def test_mark_is_drawn_as_one_icon(window):
    """Ring and "?" are painted together; the "?" sits in the middle."""
    mark = marks(window)[0]
    image = mark.grab().toImage()
    side = gui.HelpMark.SIZE
    ink = [(x, y) for x in range(4, side - 4) for y in range(4, side - 4)
           if image.pixelColor(x, y).alpha() > 128 and image.pixelColor(x, y) != image.pixelColor(side // 2, 1)]
    xs = [x for x, _ in ink]
    ys = [y for _, y in ink]
    assert ink, "no question mark drawn"
    assert abs((min(xs) + max(xs)) / 2 - (side - 1) / 2) <= 1.5
    assert abs((min(ys) + max(ys)) / 2 - (side - 1) / 2) <= 1.5


def test_help_text_is_escaped():
    assert gui.help_html("<del> & co") == "<p>&lt;del&gt; &amp; co</p>"


@pytest.mark.parametrize("code", list(i18n.LANGUAGES))
def test_help_is_written_in_every_language(code):
    i18n.set_language(code)
    english = json.loads((gui.Path(i18n.__file__).parent / "locales" / "en.json").read_text("utf-8"))
    table = i18n.load_table(code)
    for key in HELP_KEYS:
        if key not in table and not must_be_complete(code):
            continue  # waits for the pre-release translation pass
        assert gui.tr(key) and (code == "en" or gui.tr(key) != english[key]), (code, key)


# -- reset to defaults ------------------------------------------------------------- #


def test_reset_puts_formats_and_options_back(window):
    window.format_boxes["markdown"].setChecked(False)
    window.format_boxes["json"].setChecked(True)
    window.timeout_box.setCurrentIndex(window.timeout_box.findData("300"))
    window.pages_edit.setText("1-3")
    window.image_mode.setCurrentIndex(window.image_mode.findData("off"))
    window.threads_spin.setValue(2)  # an advanced one: must stay

    window.reset_main_btn.click()

    assert window.format_boxes["markdown"].isChecked()
    assert not window.format_boxes["json"].isChecked()
    assert window.timeout_box.currentData() == "30"
    assert window.pages_edit.text() == ""
    assert window.image_mode.currentData() == "external"
    assert window.threads_spin.value() == 2


def test_reset_puts_advanced_options_back(window):
    window.table_method.setCurrentIndex(window.table_method.findData("cluster"))
    window.space_ratio.setValue(0.5)
    window.password_edit.setText("secret")
    window.opt_header_footer.setChecked(True)
    window.hybrid.setCurrentIndex(1)
    window.timeout_box.setCurrentIndex(window.timeout_box.findData("300"))  # a main one: must stay

    window.reset_advanced_btn.click()

    assert window.table_method.currentData() == "default"
    assert window.space_ratio.value() == pytest.approx(0.17)
    assert window.password_edit.text() == ""
    assert not window.opt_header_footer.isChecked()
    assert window.hybrid.currentData() is None
    assert window.timeout_box.currentData() == "300"


def test_defaults_are_the_untouched_ones_not_the_saved_ones(qapp, settings_file):
    first = gui.MainWindow()
    first.timeout_box.setCurrentIndex(first.timeout_box.findData("120"))
    first._save_settings()

    again = gui.MainWindow()
    assert again.timeout_box.currentData() == "120"  # restored as saved...
    again.reset_main_btn.click()
    assert again.timeout_box.currentData() == "30"  # ...but reset goes to the default


# -- password ------------------------------------------------------------------------ #


def test_eye_shows_and_hides_the_password(window):
    window.password_edit.setText("secret")
    assert window.password_edit.echoMode() == QLineEdit.EchoMode.Password

    window.password_eye.trigger()
    assert window.password_edit.echoMode() == QLineEdit.EchoMode.Normal
    assert window.password_eye.toolTip() == gui.tr("password.hide")

    window.password_eye.trigger()
    assert window.password_edit.echoMode() == QLineEdit.EchoMode.Password
    assert window.password_eye.toolTip() == gui.tr("password.show")


# -- favourite folders ----------------------------------------------------------------- #


def favorite_buttons(window):
    return [b for b in window.fav_panel.findChildren(gui.QPushButton) if b.objectName() == "Favorite"
            and not b.property("deleted")]


def flush():
    from PySide6.QtCore import QCoreApplication, QEvent

    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)


def test_favorites_are_folded_away_at_first(window):
    assert not window.fav_panel.isVisibleTo(window)
    assert window.fav_btn.text().startswith(gui.tr("favorites.button", count=0))


def test_add_use_and_remove_a_favorite(window, tmp_path):
    one, two = tmp_path / "one", tmp_path / "two"
    window.fav_btn.click()

    assert not window.fav_add.isEnabled(), "nothing to add while the field is empty"
    window.output_edit.setText(str(one))
    window.fav_add.click()
    window.output_edit.setText(str(two))
    window.fav_add.click()
    assert window.favorites == [str(one), str(two)]
    assert not window.fav_add.isEnabled(), "the current folder is in already"

    window.use_favorite(str(one))
    assert window.output_edit.text() == str(one)
    assert gui.app_settings().value("output_dir") == str(one)
    flush()
    current = [b for b in favorite_buttons(window) if b.property("current")]
    assert len(current) == 1 and current[0].toolTip() == gui.tr("favorites.use", path=str(one))

    window.remove_favorite(str(one))
    assert window.favorites == [str(two)]


def test_no_more_than_five(window, tmp_path):
    for i in range(gui.FAVORITES_MAX + 1):
        window.output_edit.setText(str(tmp_path / f"f{i}"))
        window.add_favorite()

    assert len(window.favorites) == gui.FAVORITES_MAX
    window.output_edit.setText(str(tmp_path / "another"))
    assert not window.fav_add.isEnabled()
    assert window.fav_add.toolTip() == gui.tr("favorites.full", max=gui.FAVORITES_MAX)


def test_same_folder_written_differently_is_not_added_twice(window, tmp_path):
    window.output_edit.setText(str(tmp_path / "out"))
    window.add_favorite()
    window.output_edit.setText(str(tmp_path / "OUT") + "\\")
    window.add_favorite()

    assert len(window.favorites) == 1


def test_favorites_survive_a_restart(qapp, settings_file, tmp_path):
    w = gui.MainWindow()
    w.output_edit.setText(str(tmp_path / "only"))
    w.add_favorite()  # a single item: the registry likes to hand that back as a bare string
    w.fav_btn.click()
    w._save_settings()

    again = gui.MainWindow()
    assert again.favorites == [str(tmp_path / "only")]
    assert again.fav_panel.isVisibleTo(again), "folded open as it was left"


def test_broken_favorites_setting_is_ignored(qapp, settings_file):
    gui.app_settings().setValue("favorite_dirs", "not json")

    assert gui.MainWindow().favorites == []


def test_reset_settings_forgets_favorites(qapp, settings_file, tmp_path):
    w = gui.open_window()
    w.output_edit.setText(str(tmp_path / "x"))
    w.add_favorite()

    new = gui.reset_settings(w)

    assert new.favorites == []


# -- the log ----------------------------------------------------------------------------- #


def finish(window, failed):
    window.elapsed.start()
    window.on_finished(
        {"ok": 0 if failed else 1, "total": 1, "failed": ["a.pdf"] if failed else [],
         "timed_out": [], "degraded": [], "cancelled": False, "error": "", "results": []}
    )


def test_details_link_appears_only_when_something_went_wrong(window):
    finish(window, failed=False)
    assert not window.details_link.isVisibleTo(window)

    finish(window, failed=True)
    assert window.details_link.isVisibleTo(window)


def test_details_link_opens_the_log(window):
    finish(window, failed=True)
    window._toggle_log(False)

    window.details_link.linkActivated.emit("#log")

    assert not window.log_card.isHidden()
    assert window.act_show_log.isChecked()


def test_details_link_goes_away_with_the_next_run(window):
    finish(window, failed=True)

    window.thread = object()
    window._set_busy(True, 1)

    assert not window.details_link.isVisibleTo(window)
    window.thread = None



# -- page separators and plain Markdown tables ------------------------------------------ #


def tick(window, *formats):
    for key, box in window.format_boxes.items():
        box.setChecked(key in formats)


def test_defaults_keep_separators_and_html_tables(window):
    tick(window, "markdown", "text", "html")

    opts = window._collect_options()

    assert opts["markdown_with_html"] is True
    for key in ("markdown_page_separator", "text_page_separator", "html_page_separator"):
        assert opts[key] == gui.PAGE_SEPARATOR


def test_separators_off(window):
    tick(window, "markdown", "text", "html")
    window.opt_page_sep.setChecked(False)

    opts = window._collect_options()

    assert not any(key.endswith("_page_separator") for key in opts)
    assert opts["markdown_with_html"] is True, "tables are a separate choice"


def test_plain_markdown_tables(window):
    tick(window, "markdown")
    window.opt_plain_md.setChecked(True)

    opts = window._collect_options()

    assert "markdown_with_html" not in opts
    assert opts["markdown_page_separator"] == gui.PAGE_SEPARATOR


def test_options_grey_out_when_their_formats_are_off(window):
    tick(window, "json")
    assert not window.opt_page_sep.isEnabled() and not window.opt_plain_md.isEnabled()

    tick(window, "text")
    assert window.opt_page_sep.isEnabled() and not window.opt_plain_md.isEnabled()

    tick(window, "markdown")
    assert window.opt_page_sep.isEnabled() and window.opt_plain_md.isEnabled()


def test_both_are_remembered_and_reset(qapp, settings_file):
    w = gui.MainWindow()
    w.opt_page_sep.setChecked(False)
    w.opt_plain_md.setChecked(True)
    w._save_settings()

    again = gui.MainWindow()
    assert not again.opt_page_sep.isChecked() and again.opt_plain_md.isChecked()

    again.reset_main_btn.click()
    assert again.opt_page_sep.isChecked() and not again.opt_plain_md.isChecked()


# -- two even columns ----------------------------------------------------------------------- #


@pytest.mark.parametrize("width", [760, 1900])
def test_options_and_more_options_line_up(window, width):
    """Same box size everywhere, and both sections' columns at the same x -
    in a narrow window and in a maximised one."""
    from PySide6.QtWidgets import QGridLayout

    window.more_btn.setChecked(True)
    window.resize(width, 900)
    window.show()
    QApplication.processEvents()
    grids = [g for g in window.findChildren(QGridLayout) if g.columnCount() >= 8]
    assert len(grids) == 2

    starts = [[g.cellRect(0, c).x() for c in range(7)] for g in grids]
    assert starts[0] == starts[1]
    boxes = [window.image_mode, window.image_dpi, window.pages_edit, window.timeout_box,
             window.reading_order, window.table_method, window.image_format,
             window.threads_spin, window.password_edit, window.space_ratio]
    if gui.AI_MODE:
        boxes += [window.hybrid, window.hybrid_url]
    assert {b.width() for b in boxes} == {gui.FIELD_WIDTH}
    # The second half sits right after the first: spare width goes to the right.
    assert starts[0][4] - (starts[0][2] + 18) <= 40


# -- resolution ------------------------------------------------------------------------------ #


def test_resolution_is_a_list_of_usual_values(window):
    values = [int(window.image_dpi.itemData(i)) for i in range(window.image_dpi.count())]

    assert values == gui.IMAGE_DPI_CHOICES and 96 in values and 300 in values
    assert window.image_dpi.currentData() == "144"
    assert "image_resolution" not in window._collect_options(), "default: nothing to pass"

    window.image_dpi.setCurrentIndex(window.image_dpi.findData("96"))
    assert window._collect_options()["image_resolution"] == "96"


def test_resolution_saved_by_the_old_counter_still_loads(qapp, settings_file):
    """The counter stored 96 as a number; an odd value like 150 falls back."""
    gui.app_settings().setValue("options/image_dpi", 96)
    assert gui.MainWindow().image_dpi.currentData() == "96"

    gui.app_settings().setValue("options/image_dpi", 150)
    assert gui.MainWindow().image_dpi.currentData() == "144"


def test_timeout_is_a_list_of_usual_values(window):
    box = window.timeout_box
    values = [int(box.itemData(i)) for i in range(box.count())]
    texts = [box.itemText(i) for i in range(box.count())]

    assert values == gui.TIMEOUT_CHOICES
    assert box.currentData() == "30"
    assert texts[0] == "15" + gui.tr("timeout.suffix")
    assert texts[values.index(120)] == gui.tr("timeout.minutes", n=2)
    assert texts[-1] == gui.tr("timeout.none")


def test_timeout_saved_by_the_old_counter_still_loads(qapp, settings_file):
    gui.app_settings().setValue("options/timeout", 120)
    assert gui.MainWindow().timeout_box.currentData() == "120"

    gui.app_settings().setValue("options/timeout", 45)  # not on the list
    assert gui.MainWindow().timeout_box.currentData() == "30"


# -- hidden text --------------------------------------------------------------------------------- #


def test_hidden_text_is_kept_unless_asked(window):
    assert not window.opt_hidden.isChecked(), "off by default: slower, and thin symbols go"
    assert window._collect_options()["content_safety_off"] == gui.CONTENT_SAFETY_OFF

    window.opt_hidden.setChecked(True)
    options = window._collect_options()

    assert options["content_safety_off"] is None, "every built-in filter stays on"
