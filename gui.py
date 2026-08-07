"""Desktop front-end for opendataloader-pdf.

A single-window Qt application aimed at people who never open a terminal:
drag PDFs in, tick the options, press one button.

The heavy lifting is done by opendataloader_pdf.convert(), which starts a JVM
under the hood, so conversion runs on a worker thread and the whole batch is
passed in one call rather than one call per file.
"""

from __future__ import annotations

import inspect
import io
import os
import shutil
import sys
import traceback
from pathlib import Path

from PySide6.QtCore import (
    QElapsedTimer,
    QObject,
    Qt,
    QThread,
    QTimer,
    QUrl,
    Signal,
)
from PySide6.QtGui import QDesktopServices, QGuiApplication
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

import theme

APP_NAME = "PDF → Markdown"
FORMATS = [
    ("markdown", "Markdown"),
    ("json", "JSON"),
    ("html", "HTML"),
    ("text", "Текст"),
    ("tagged-pdf", "Tagged PDF"),
]


# --------------------------------------------------------------------------- #
# Conversion worker
# --------------------------------------------------------------------------- #


class _SignalStream(io.TextIOBase):
    """File-like object that forwards written text to a Qt signal."""

    def __init__(self, emit):
        self._emit = emit

    def write(self, text: str) -> int:
        stripped = text.rstrip()
        if stripped:
            self._emit(stripped)
        return len(text)

    def flush(self) -> None:  # pragma: no cover - required by the io interface
        pass


class ConvertWorker(QObject):
    log = Signal(str)
    finished = Signal(bool, str)

    def __init__(self, inputs: list[str], output_dir: str, options: dict):
        super().__init__()
        self.inputs = inputs
        self.output_dir = output_dir
        self.options = options

    def run(self) -> None:
        try:
            import opendataloader_pdf
        except ImportError:
            self.finished.emit(
                False,
                "Пакет opendataloader-pdf не установлен (pip install opendataloader-pdf).",
            )
            return

        kwargs = {
            "input_path": self.inputs,
            "output_dir": self.output_dir,
            **self.options,
        }
        kwargs = self._filter_supported(opendataloader_pdf.convert, kwargs)

        self.log.emit(f"Файлов на входе: {len(self.inputs)}")
        self.log.emit(f"Папка результата: {self.output_dir}")
        self.log.emit("Запуск JVM, первый файл может занять несколько секунд…")

        stream = _SignalStream(self.log.emit)
        try:
            with _redirect_std(stream):
                opendataloader_pdf.convert(**kwargs)
        except Exception as exc:  # noqa: BLE001 - surface anything to the user
            self.log.emit(traceback.format_exc())
            self.finished.emit(False, f"Ошибка конвертации: {exc}")
            return

        self.finished.emit(True, "")

    def _filter_supported(self, func, kwargs: dict) -> dict:
        """Drop kwargs the installed version of convert() does not accept.

        The option set of opendataloader-pdf changes between releases; passing
        an unknown keyword would raise TypeError and lose the whole run.
        """
        try:
            params = inspect.signature(func).parameters
        except (TypeError, ValueError):
            return kwargs
        if any(p.kind is inspect.Parameter.VAR_KEYWORD for p in params.values()):
            return kwargs

        supported, dropped = {}, []
        for key, value in kwargs.items():
            if key in params:
                supported[key] = value
            else:
                dropped.append(key)
        if dropped:
            self.log.emit(
                "Пропущены опции, не поддержанные установленной версией: "
                + ", ".join(dropped)
            )
        return supported


class _redirect_std:
    """Redirect sys.stdout/sys.stderr, tolerating the None streams of a
    windowed (--noconsole) build."""

    def __init__(self, stream):
        self.stream = stream

    def __enter__(self):
        self._out, self._err = sys.stdout, sys.stderr
        sys.stdout = sys.stderr = self.stream
        return self.stream

    def __exit__(self, *exc_info):
        sys.stdout, sys.stderr = self._out, self._err
        return False


# --------------------------------------------------------------------------- #
# Widgets
# --------------------------------------------------------------------------- #


class DropZone(QFrame):
    """Dashed panel that accepts dropped PDF files and folders."""

    filesDropped = Signal(list)
    clicked = Signal()

    def __init__(self):
        super().__init__()
        self.setObjectName("DropZone")
        self.setProperty("dragActive", False)
        self.setAcceptDrops(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMinimumHeight(120)

        icon = QLabel("⬇")
        icon.setObjectName("DropIcon")
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)

        hint = QLabel("Перетащите сюда PDF или папку — либо нажмите, чтобы выбрать")
        hint.setObjectName("DropHint")
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)

        layout = QVBoxLayout(self)
        layout.setSpacing(6)
        layout.addStretch()
        layout.addWidget(icon)
        layout.addWidget(hint)
        layout.addStretch()

    def _refresh(self, active: bool) -> None:
        self.setProperty("dragActive", active)
        self.style().unpolish(self)
        self.style().polish(self)

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
            self._refresh(True)

    def dragLeaveEvent(self, event):
        self._refresh(False)

    def dropEvent(self, event):
        self._refresh(False)
        paths = [u.toLocalFile() for u in event.mimeData().urls() if u.isLocalFile()]
        if paths:
            self.filesDropped.emit(paths)
            event.acceptProposedAction()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()


def card(*widgets, spacing: int = 12, expand: bool = False) -> QFrame:
    frame = QFrame()
    frame.setObjectName("Card")
    # Without a fixed vertical policy Qt shrinks the cards past their sizeHint
    # when the window is short, and the option labels start overlapping.
    frame.setSizePolicy(
        QSizePolicy.Policy.Preferred,
        QSizePolicy.Policy.Expanding if expand else QSizePolicy.Policy.Fixed,
    )
    layout = QVBoxLayout(frame)
    layout.setContentsMargins(16, 14, 16, 16)
    layout.setSpacing(spacing)
    for w in widgets:
        if isinstance(w, QWidget):
            layout.addWidget(w)
        else:
            layout.addLayout(w)
    return frame


def section(text: str) -> QLabel:
    label = QLabel(text.upper())
    label.setObjectName("SectionLabel")
    return label


# --------------------------------------------------------------------------- #
# Main window
# --------------------------------------------------------------------------- #


class MainWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setObjectName("Root")
        self.setWindowTitle(APP_NAME)
        self.setMinimumWidth(720)

        self.inputs: list[str] = []
        self.thread: QThread | None = None
        self.worker: ConvertWorker | None = None
        self.dark = _system_prefers_dark()
        self.elapsed = QElapsedTimer()
        self.tick = QTimer(self)
        self.tick.setInterval(500)
        self.tick.timeout.connect(self._update_elapsed)

        self._build_ui()
        self._apply_theme()
        # Open at the natural content height where the screen allows it, but
        # never demand more than a small laptop can give.
        natural = self.sizeHint().height()
        self.setMinimumHeight(min(560, natural))
        self.resize(800, min(natural, self.screen().availableGeometry().height() - 80))
        QTimer.singleShot(0, self._check_java)

    # -- construction ------------------------------------------------------ #

    def _build_ui(self) -> None:
        # Cards live inside a scroll area so a short window scrolls instead of
        # compressing the cards into each other; the header and the action bar
        # stay pinned.
        body = QWidget()
        body.setObjectName("Body")
        self.body_layout = QVBoxLayout(body)
        self.body_layout.setContentsMargins(0, 0, 8, 0)
        self.body_layout.setSpacing(16)
        self.body_layout.addWidget(self._files_card())
        self.body_layout.addWidget(self._options_card())
        self.body_layout.addWidget(self._output_card())
        self.log_card = self._log_card()
        self.body_layout.addWidget(self.log_card, 1)
        self.body_layout.addStretch()

        scroll = QScrollArea()
        scroll.setObjectName("Scroll")
        scroll.setWidget(body)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        root = QVBoxLayout(self)
        root.setContentsMargins(22, 20, 22, 20)
        root.setSpacing(16)
        root.addLayout(self._header())
        root.addWidget(scroll, 1)
        root.addLayout(self._action_bar())

    def _header(self) -> QHBoxLayout:
        title = QLabel(APP_NAME)
        title.setObjectName("Title")
        subtitle = QLabel("Извлечение структурированного текста из PDF · opendataloader-pdf")
        subtitle.setObjectName("Subtitle")

        text = QVBoxLayout()
        text.setSpacing(2)
        text.addWidget(title)
        text.addWidget(subtitle)

        self.theme_btn = QPushButton("☾" if not self.dark else "☀")
        self.theme_btn.setObjectName("Ghost")
        self.theme_btn.setToolTip("Светлая / тёмная тема")
        self.theme_btn.setFixedWidth(40)
        self.theme_btn.clicked.connect(self._toggle_theme)

        row = QHBoxLayout()
        row.addLayout(text)
        row.addStretch()
        row.addWidget(self.theme_btn, alignment=Qt.AlignmentFlag.AlignTop)
        return row

    def _files_card(self) -> QFrame:
        self.drop = DropZone()
        self.drop.filesDropped.connect(self.add_paths)
        self.drop.clicked.connect(self.pick_files)

        self.file_list = QListWidget()
        self.file_list.setVisible(False)
        self.file_list.setMaximumHeight(150)

        add_btn = QPushButton("Добавить файлы")
        add_btn.clicked.connect(self.pick_files)
        add_folder_btn = QPushButton("Добавить папку")
        add_folder_btn.clicked.connect(self.pick_folder)
        self.clear_btn = QPushButton("Очистить")
        self.clear_btn.setObjectName("Danger")
        self.clear_btn.clicked.connect(self.clear_inputs)
        self.clear_btn.setVisible(False)

        buttons = QHBoxLayout()
        buttons.setSpacing(8)
        buttons.addWidget(add_btn)
        buttons.addWidget(add_folder_btn)
        buttons.addStretch()
        buttons.addWidget(self.clear_btn)

        return card(section("Исходные файлы"), self.drop, self.file_list, buttons)

    def _options_card(self) -> QFrame:
        self.format_boxes: dict[str, QCheckBox] = {}
        formats = QHBoxLayout()
        formats.setSpacing(14)
        for key, label in FORMATS:
            box = QCheckBox(label)
            box.setChecked(key == "markdown")
            self.format_boxes[key] = box
            formats.addWidget(box)
        formats.addStretch()

        self.opt_struct = QCheckBox("Использовать теги из PDF")
        self.opt_struct.setToolTip(
            "Читать встроенную структуру документа вместо анализа вёрстки.\n"
            "Точнее — но только для PDF, где теги действительно есть."
        )
        self.opt_sanitize = QCheckBox("Скрыть чувствительные данные")
        self.opt_formula = QCheckBox("Формулы в LaTeX")
        self.opt_picture = QCheckBox("Описания картинок и графиков")
        self.opt_ocr = QCheckBox("OCR для сканов")
        self.opt_ocr.toggled.connect(self._toggle_ocr)

        # Two even columns keep the labels from colliding regardless of how
        # long the translated text turns out to be.
        grid = QGridLayout()
        grid.setHorizontalSpacing(24)
        grid.setVerticalSpacing(6)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.addWidget(self.opt_struct, 0, 0)
        grid.addWidget(self.opt_sanitize, 0, 1)
        grid.addWidget(self.opt_formula, 1, 0)
        grid.addWidget(self.opt_picture, 1, 1)
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)

        self.ocr_lang = QLineEdit("rus,eng")
        self.ocr_lang.setPlaceholderText("rus,eng")
        self.ocr_lang.setFixedWidth(160)
        self.ocr_lang.setEnabled(False)
        ocr_row = QHBoxLayout()
        ocr_row.setSpacing(10)
        ocr_row.addWidget(self.opt_ocr)
        ocr_row.addSpacing(14)
        ocr_row.addWidget(QLabel("Языки:"))
        ocr_row.addWidget(self.ocr_lang)
        ocr_row.addStretch()

        self.hybrid = QComboBox()
        self.hybrid.addItem("Выключен (быстро)", None)
        self.hybrid.addItem("docling-fast", "docling-fast")
        self.hybrid.setFixedWidth(200)
        hybrid_row = QHBoxLayout()
        hybrid_row.setSpacing(10)
        hybrid_row.addWidget(QLabel("AI-режим:"))
        hybrid_row.addWidget(self.hybrid)
        hybrid_row.addStretch()

        return card(
            section("Форматы вывода"),
            formats,
            section("Опции"),
            grid,
            ocr_row,
            hybrid_row,
        )

    def _output_card(self) -> QFrame:
        self.output_edit = QLineEdit()
        self.output_edit.setPlaceholderText("Папка рядом с исходными файлами")
        browse = QPushButton("Обзор…")
        browse.clicked.connect(self.pick_output)

        row = QHBoxLayout()
        row.setSpacing(8)
        row.addWidget(self.output_edit, 1)
        row.addWidget(browse)
        return card(section("Куда сохранить"), row)

    def _log_card(self) -> QFrame:
        self.log_view = QPlainTextEdit()
        self.log_view.setObjectName("Log")
        self.log_view.setReadOnly(True)
        self.log_view.setMinimumHeight(90)
        self.log_view.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        self.log_view.setPlaceholderText("Здесь появится ход работы.")

        frame = card(section("Журнал"), self.log_view, expand=True)
        # Hidden until asked for: a log is noise for the audience this app
        # targets, and it costs ~140 px of window height.
        frame.setVisible(False)
        return frame

    def _action_bar(self) -> QVBoxLayout:
        self.progress = QProgressBar()
        self.progress.setTextVisible(False)
        self.progress.setRange(0, 1)
        self.progress.setValue(0)
        self.progress.setVisible(False)

        self.status = QLabel("Добавьте хотя бы один PDF.")
        self.status.setObjectName("StatusText")

        self.open_btn = QPushButton("Открыть папку результата")
        self.open_btn.clicked.connect(self.open_output)
        self.open_btn.setVisible(False)

        self.log_btn = QPushButton("Журнал")
        self.log_btn.setObjectName("Ghost")
        self.log_btn.setCheckable(True)
        self.log_btn.toggled.connect(self._toggle_log)

        self.run_btn = QPushButton("Конвертировать")
        self.run_btn.setObjectName("Primary")
        self.run_btn.setEnabled(False)
        self.run_btn.clicked.connect(self.start)

        row = QHBoxLayout()
        row.addWidget(self.status, 1)
        row.addWidget(self.log_btn)
        row.addWidget(self.open_btn)
        row.addWidget(self.run_btn)

        bar = QVBoxLayout()
        bar.setSpacing(10)
        bar.addWidget(self.progress)
        bar.addLayout(row)
        return bar

    # -- theming ----------------------------------------------------------- #

    def _apply_theme(self) -> None:
        palette = theme.DARK if self.dark else theme.LIGHT
        QApplication.instance().setStyleSheet(theme.build_qss(palette))

    def _toggle_theme(self) -> None:
        self.dark = not self.dark
        self.theme_btn.setText("☀" if self.dark else "☾")
        self._apply_theme()

    # -- input handling ---------------------------------------------------- #

    def pick_files(self) -> None:
        paths, _ = QFileDialog.getOpenFileNames(
            self, "Выберите PDF", str(Path.home()), "PDF (*.pdf)"
        )
        self.add_paths(paths)

    def pick_folder(self) -> None:
        path = QFileDialog.getExistingDirectory(
            self, "Выберите папку с PDF", str(Path.home())
        )
        if path:
            self.add_paths([path])

    def pick_output(self) -> None:
        path = QFileDialog.getExistingDirectory(
            self, "Куда сохранить результат", self.output_edit.text() or str(Path.home())
        )
        if path:
            self.output_edit.setText(path)

    def add_paths(self, paths: list[str]) -> None:
        added = 0
        for raw in paths:
            path = os.path.abspath(raw)
            if path in self.inputs:
                continue
            if os.path.isdir(path) or path.lower().endswith(".pdf"):
                self.inputs.append(path)
                added += 1
        if added:
            self._refresh_file_list()

    def clear_inputs(self) -> None:
        self.inputs.clear()
        self._refresh_file_list()

    def _refresh_file_list(self) -> None:
        self.file_list.clear()
        for path in self.inputs:
            marker = "📁" if os.path.isdir(path) else "📄"
            item = QListWidgetItem(f"{marker}  {os.path.basename(path)}")
            item.setToolTip(path)
            self.file_list.addItem(item)

        has_files = bool(self.inputs)
        self.file_list.setVisible(has_files)
        self.clear_btn.setVisible(has_files)
        self.drop.setVisible(not has_files)
        self.run_btn.setEnabled(has_files)
        self._set_status(
            f"Готово к работе: {len(self.inputs)} шт."
            if has_files
            else "Добавьте хотя бы один PDF."
        )

    def _toggle_ocr(self, checked: bool) -> None:
        self.ocr_lang.setEnabled(checked)

    def _toggle_log(self, shown: bool) -> None:
        if self.log_btn.isChecked() != shown:
            self.log_btn.setChecked(shown)  # re-enters here via the signal
            return

        self.log_card.setVisible(shown)
        # Grow the window to make room rather than pushing the cards into the
        # scroll area, and give the space back when the log is folded away.
        delta = self.log_card.sizeHint().height() + self.body_layout.spacing()
        available = self.screen().availableGeometry().height()
        if shown:
            self.resize(self.width(), min(self.height() + delta, available))
        else:
            self.resize(self.width(), max(self.height() - delta, self.minimumHeight()))

    # -- run --------------------------------------------------------------- #

    def _collect_options(self) -> dict | None:
        formats = [key for key, box in self.format_boxes.items() if box.isChecked()]
        if not formats:
            QMessageBox.warning(
                self, APP_NAME, "Выберите хотя бы один формат вывода."
            )
            return None

        options: dict = {
            "format": ",".join(formats),
            "use_struct_tree": self.opt_struct.isChecked(),
            "sanitize": self.opt_sanitize.isChecked(),
            "enrich_formula": self.opt_formula.isChecked(),
            "enrich_picture_description": self.opt_picture.isChecked(),
            "force_ocr": self.opt_ocr.isChecked(),
        }
        if self.opt_ocr.isChecked() and self.ocr_lang.text().strip():
            options["ocr_lang"] = self.ocr_lang.text().strip()
        if self.hybrid.currentData():
            options["hybrid"] = self.hybrid.currentData()
        return options

    def _resolve_output_dir(self) -> str:
        chosen = self.output_edit.text().strip()
        if chosen:
            return chosen
        first = Path(self.inputs[0])
        base = first if first.is_dir() else first.parent
        return str(base / "output")

    def start(self) -> None:
        options = self._collect_options()
        if options is None:
            return

        output_dir = self._resolve_output_dir()
        try:
            os.makedirs(output_dir, exist_ok=True)
        except OSError as exc:
            QMessageBox.critical(
                self, APP_NAME, f"Не удалось создать папку результата:\n{exc}"
            )
            return

        self.output_dir = output_dir
        self.log_view.clear()
        self._set_busy(True)
        self.elapsed.start()
        self.tick.start()

        self.thread = QThread(self)
        self.worker = ConvertWorker(list(self.inputs), output_dir, options)
        self.worker.moveToThread(self.thread)
        self.thread.started.connect(self.worker.run)
        self.worker.log.connect(self.append_log)
        self.worker.finished.connect(self.on_finished)
        self.thread.start()

    def on_finished(self, ok: bool, error: str) -> None:
        self.tick.stop()
        self.thread.quit()
        self.thread.wait()
        self.thread = None
        self.worker = None
        self._set_busy(False)

        seconds = self.elapsed.elapsed() / 1000
        if ok:
            self._set_status(f"Готово за {seconds:.1f} с", state="ok")
            self.append_log(f"Завершено за {seconds:.1f} с.")
            self.open_btn.setVisible(True)
        else:
            self._set_status("Не удалось", state="error")
            self.append_log(error)
            self._toggle_log(True)  # the details are the point when it breaks
            QMessageBox.critical(self, APP_NAME, error)

    def open_output(self) -> None:
        QDesktopServices.openUrl(QUrl.fromLocalFile(self.output_dir))

    # -- small helpers ------------------------------------------------------ #

    def _set_busy(self, busy: bool) -> None:
        self.progress.setVisible(busy)
        self.progress.setRange(0, 0 if busy else 1)
        self.run_btn.setEnabled(not busy)
        self.run_btn.setText("Конвертация…" if busy else "Конвертировать")
        if busy:
            self.open_btn.setVisible(False)
            self._set_status("Работаю…")

    def _set_status(self, text: str, state: str = "") -> None:
        self.status.setText(text)
        self.status.setProperty("state", state)
        self.status.style().unpolish(self.status)
        self.status.style().polish(self.status)

    def _update_elapsed(self) -> None:
        self._set_status(f"Работаю… {self.elapsed.elapsed() / 1000:.0f} с")

    def append_log(self, text: str) -> None:
        self.log_view.appendPlainText(text)
        self.log_view.verticalScrollBar().setValue(
            self.log_view.verticalScrollBar().maximum()
        )

    def _check_java(self) -> None:
        """opendataloader-pdf needs a JVM; say so early and in plain words."""
        java = shutil.which("java")
        if not java and os.environ.get("JAVA_HOME"):
            candidate = Path(os.environ["JAVA_HOME"]) / "bin" / "java"
            java = str(candidate) if candidate.exists() else None
        if java:
            self.append_log(f"Java найдена: {java}")
            return
        self.append_log("Java не найдена.")
        QMessageBox.warning(
            self,
            APP_NAME,
            "Не найдена Java 11 или новее — без неё конвертация не запустится.\n\n"
            "Если программа устанавливалась через установщик, переустановите её: "
            "нужная версия Java идёт в комплекте.",
        )

    def closeEvent(self, event):
        if self.thread is not None and self.thread.isRunning():
            answer = QMessageBox.question(
                self, APP_NAME, "Конвертация ещё идёт. Закрыть программу?"
            )
            if answer != QMessageBox.StandardButton.Yes:
                event.ignore()
                return
        event.accept()


def _use_bundled_jre() -> None:
    """Point JAVA_HOME at the JRE shipped next to the executable, if present.

    The installer puts a trimmed jlink runtime in a "jre" folder beside the
    application so that users do not have to install Java themselves. A JVM
    the user installed on their own still wins if it is already configured.
    """
    if os.environ.get("JAVA_HOME"):
        return
    base = Path(sys.executable if getattr(sys, "frozen", False) else __file__).parent
    jre = base / "jre"
    launcher = jre / "bin" / ("java.exe" if os.name == "nt" else "java")
    if not launcher.exists():
        return
    os.environ["JAVA_HOME"] = str(jre)
    os.environ["PATH"] = str(jre / "bin") + os.pathsep + os.environ.get("PATH", "")


def _system_prefers_dark() -> bool:
    hints = QGuiApplication.styleHints()
    scheme = getattr(hints, "colorScheme", None)
    if scheme is None:  # Qt < 6.5
        return True
    return scheme() == Qt.ColorScheme.Dark


def main() -> int:
    _use_bundled_jre()
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
