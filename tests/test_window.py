"""The window: options it sends, settings it keeps, files it is handed."""

import gui


def test_defaults(window):
    opts = window._collect_options()

    assert opts["format"] == "markdown"
    assert opts["markdown_with_html"] is True
    assert opts["markdown_page_separator"] == gui.PAGE_SEPARATOR
    assert opts["content_safety_off"] == gui.CONTENT_SAFETY_OFF
    assert opts["replace_invalid_chars"] == "?"
    assert opts["image_output"] == "external"
    # Left at the CLI's own default, so not sent at all.
    assert "image_resolution" not in opts and "space_ratio" not in opts
    assert "hybrid" not in opts
    assert window.timeout_box.currentData() == "30"


def test_annotated_pdf_alone_is_a_valid_run(window):
    window.format_boxes["markdown"].setChecked(False)
    window.format_boxes["pdf"].setChecked(True)

    opts = window._collect_options()

    assert opts["format"] == "pdf"
    assert "markdown_with_html" not in opts


def test_ai_mode_always_carries_timeout_and_fallback(window):
    window.hybrid.setCurrentIndex(window.hybrid.findData("docling-fast"))

    opts = window._collect_options()

    assert opts["hybrid"] == "docling-fast"
    assert opts["hybrid_timeout"] == gui.HYBRID_TIMEOUT_MS
    assert opts["hybrid_fallback"] is True


def test_hancom_ai_is_gone(window):
    """Removed upstream in 2.5.13."""
    assert window.hybrid.findData("hancom-ai") == -1


def test_settings_survive_a_restart(qapp, settings_file):
    first = gui.MainWindow()
    first.format_boxes["json"].setChecked(True)
    first.format_boxes["pdf"].setChecked(True)
    first.image_mode.setCurrentIndex(first.image_mode.findData("off"))
    first.image_dpi.setCurrentIndex(first.image_dpi.findData("96"))
    first.timeout_box.setCurrentIndex(first.timeout_box.findData("120"))
    first.table_method.setCurrentIndex(first.table_method.findData("cluster"))
    first.space_ratio.setValue(0.25)
    first.opt_header_footer.setChecked(True)
    first.more_btn.setChecked(True)
    first._save_settings()
    first.close()

    second = gui.MainWindow()

    assert second.format_boxes["json"].isChecked()
    assert second.format_boxes["pdf"].isChecked()
    assert second.format_boxes["markdown"].isChecked()
    assert second.image_mode.currentData() == "off"
    assert second.image_dpi.currentData() == "96"
    assert second.timeout_box.currentData() == "120"
    assert second.table_method.currentData() == "cluster"
    assert abs(second.space_ratio.value() - 0.25) < 1e-9
    assert second.opt_header_footer.isChecked()
    assert second.advanced.isVisibleTo(second)
    second.close()


def test_password_and_pages_are_never_stored(qapp, settings_file):
    w = gui.MainWindow()
    w.password_edit.setText("hunter2")
    w.pages_edit.setText("1-3")
    w._save_settings()
    w.close()

    stored = settings_file.read_text(encoding="utf-8")
    assert "hunter2" not in stored
    assert "1-3" not in stored

    again = gui.MainWindow()
    assert again.password_edit.text() == ""
    assert again.pages_edit.text() == ""
    again.close()


def test_stale_stored_value_is_ignored(qapp, settings_file):
    """An AI mode saved by an older version (hancom-ai) must not break startup."""
    gui.app_settings().setValue("options/hybrid", "hancom-ai")
    gui.app_settings().setValue("options/image_dpi", "not a number")

    w = gui.MainWindow()

    assert w.hybrid.currentData() is None
    assert w.image_dpi.currentData() == str(gui.IMAGE_DPI_DEFAULT)
    w.close()


def test_output_folder_is_remembered(qapp, settings_file, tmp_path):
    w = gui.MainWindow()
    w.output_edit.setText(str(tmp_path))
    w._remember_output_dir()
    w.close()

    assert gui.MainWindow().output_edit.text() == str(tmp_path)


def test_theme_follows_system_until_chosen_by_hand(qapp, settings_file):
    w = gui.MainWindow()
    assert gui.app_settings().value("dark") is None
    was = w.dark
    w._set_theme("light" if was else "dark")
    w.close()

    assert gui.MainWindow().dark is (not was)


def _drop(window, *paths):
    from PySide6.QtCore import QMimeData, QPoint, QPointF, Qt, QUrl
    from PySide6.QtGui import QDragEnterEvent, QDropEvent

    mime = QMimeData()
    mime.setUrls([QUrl.fromLocalFile(str(p)) for p in paths])
    args = (
        Qt.DropAction.CopyAction, mime,
        Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier,
    )
    # PySide6 6.12 deprecates the QPoint form; 6.11 only has that one.
    try:
        enter = QDragEnterEvent(QPointF(10, 10), *args)
    except TypeError:
        enter = QDragEnterEvent(QPoint(10, 10), *args)
    window.dragEnterEvent(enter)
    assert enter.isAccepted()
    drop = QDropEvent(
        QPointF(10, 10), Qt.DropAction.CopyAction, mime,
        Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier,
    )
    window.dropEvent(drop)


def test_a_second_file_can_be_dropped(window, tmp_path):
    """The drop zone hides after the first file; the window takes the rest."""
    first, second = tmp_path / "a.pdf", tmp_path / "b.pdf"
    for p in (first, second):
        p.write_bytes(b"%PDF")
    _drop(window, first)
    assert window.drop.isHidden() and not window.file_list.isHidden()

    _drop(window, second)

    assert window.inputs == [str(first), str(second)]
    # Drops on the list reach the window only if the list does not keep them.
    assert window.acceptDrops()
    assert not window.file_list.acceptDrops()
    assert not window.file_list.viewport().acceptDrops()
    assert window.file_list.property("dragActive") is False


def test_files_added_mid_run_do_not_enable_convert(window, tmp_path):
    first, second = tmp_path / "a.pdf", tmp_path / "b.pdf"
    for p in (first, second):
        p.write_bytes(b"%PDF")
    window.add_paths([str(first)])
    window.thread = object()  # a run in progress
    window._set_busy(True, 1)

    window.add_paths([str(second)])

    assert not window.run_btn.isEnabled()
    assert window.inputs == [str(first), str(second)]
    window.thread = None
