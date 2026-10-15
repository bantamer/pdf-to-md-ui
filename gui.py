"""Desktop front-end for opendataloader-pdf.

A single-window Qt application aimed at people who never open a terminal:
drag PDFs in, tick the options, press one button. The conversion itself lives
in converter.py; this module is the window around it.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from PySide6.QtCore import (
    QElapsedTimer,
    QEvent,
    QObject,
    QSettings,
    Qt,
    QThread,
    QTimer,
    QUrl,
    Signal,
)
from PySide6.QtGui import QDesktopServices, QGuiApplication
from PySide6.QtWidgets import (
    QAbstractScrollArea,
    QAbstractSpinBox,
    QApplication,
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
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
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

import theme
from converter import (
    CONTENT_SAFETY_OFF,
    HYBRID_DEFAULT_URL,
    HYBRID_TIMEOUT_MS,
    IMAGE_DPI_DEFAULT,
    PAGE_SEPARATOR,
    SPACE_RATIO_DEFAULT,
    ConvertWorker,
    _no_window,
    java_executable,
    odl_version,
    plan_jobs,
    server_reachable,
    supported_option_names,
    use_bundled_jre,
)

APP_NAME = "PDF → Markdown"
FORMATS = [
    ("markdown", "Markdown"),
    ("json", "JSON"),
    ("html", "HTML"),
    ("text", "Текст"),
    ("tagged-pdf", "Tagged PDF"),
    ("pdf", "PDF с разметкой"),
]

# Not an output format like the others - it carries no extracted text - but it
# belongs in the same row anyway: it is a file the run produces, and hiding it
# among the settings left people guessing what the checkbox did.
FORMAT_HINTS = {
    "pdf": (
        "Копия исходного PDF, поверх которой залиты распознанные элементы:\n"
        "ячейки таблиц с их границами, текстовые блоки, заголовки.\n"
        "Текста внутри нет — это способ увидеть, почему таблица вышла не так.\n"
        "Файл имя_annotated.pdf; на скорость почти не влияет."
    ),
    "tagged-pdf": "Исходный PDF с проставленными тегами структуры.",
}

IMAGE_HINT = (
    "Извлечение картинок — самая тяжёлая часть работы: каждая иллюстрация "
    "рендерится заново. На обычных документах разница незаметна, но у "
    "даташитов бывают десятки страниц графиков, и на них конвертация может "
    "идти минутами."
)


def app_settings() -> QSettings:
    """Per-user settings store: the registry on Windows, an ini file elsewhere."""
    return QSettings("pdf-to-md-ui", "settings")


# --------------------------------------------------------------------------- #
# Remembering the options between launches
# --------------------------------------------------------------------------- #


def widget_value(widget: QWidget):
    if isinstance(widget, QCheckBox) or (
        isinstance(widget, QPushButton) and widget.isCheckable()
    ):
        return widget.isChecked()
    if isinstance(widget, QComboBox):
        data = widget.currentData()
        return "" if data is None else data
    if isinstance(widget, (QSpinBox, QDoubleSpinBox)):
        return widget.value()
    if isinstance(widget, QLineEdit):
        return widget.text()
    raise TypeError(f"no stored value for {type(widget).__name__}")


def set_widget_value(widget: QWidget, value) -> None:
    """Apply a stored value; anything that no longer fits is left alone.

    The registry hands everything back as strings, and a value saved by an
    older version may name a choice that has since gone (hancom-ai left the AI
    modes in 2.5.13) - neither is worth failing the launch over.
    """
    try:
        if isinstance(widget, QCheckBox) or isinstance(widget, QPushButton):
            widget.setChecked(str(value).lower() in ("true", "1"))
        elif isinstance(widget, QComboBox):
            wanted = None if value in ("", None) else str(value)
            index = widget.findData(wanted)
            if index >= 0:
                widget.setCurrentIndex(index)
        elif isinstance(widget, QDoubleSpinBox):
            widget.setValue(float(value))
        elif isinstance(widget, QSpinBox):
            widget.setValue(int(float(value)))
        elif isinstance(widget, QLineEdit):
            widget.setText(str(value))
    except (TypeError, ValueError):
        pass


def startup_paths(arguments: list[str]) -> list[str]:
    """Files handed to the program on launch.

    That is how a PDF dropped onto the exe, or opened through "Open with",
    arrives: as command-line arguments. Anything that is not an existing path
    is ignored rather than reported - it can only be a stray switch.
    """
    return [a for a in arguments if a and os.path.exists(a)]


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


class WheelGuard(QObject):
    """Keep the mouse wheel from editing whatever it happens to be hovering.

    Every selector and spin box sits inside a scroll area, so scrolling the
    page over one of them would silently change a setting instead - and the
    user has no reason to suspect the timeout or the DPI just moved. The
    gesture is handed to the scroll area behind the widget, which is what the
    person meant by it.
    """

    def eventFilter(self, obj, event):
        if event.type() != QEvent.Type.Wheel:
            return False
        parent = obj.parentWidget() if isinstance(obj, QWidget) else None
        while parent is not None:
            if isinstance(parent, QAbstractScrollArea):
                QApplication.sendEvent(parent.viewport(), event)
                break
            parent = parent.parentWidget()
        return True


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


def hint(text: str) -> QLabel:
    label = QLabel(text)
    label.setObjectName("Hint")
    label.setWordWrap(True)
    return label


def field_row(*pairs, spacing: int = 10) -> QHBoxLayout:
    """A row of (label, widget) pairs; a bare widget is added as-is."""
    row = QHBoxLayout()
    row.setSpacing(spacing)
    for item in pairs:
        if isinstance(item, tuple):
            text, widget = item
            row.addWidget(QLabel(text))
            row.addWidget(widget)
        else:
            row.addWidget(item)
    row.addStretch()
    return row


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
        self.output_dir = ""
        stored_theme = app_settings().value("dark", None)
        self.dark = (
            _system_prefers_dark()
            if stored_theme is None
            else str(stored_theme).lower() in ("true", "1")
        )
        self.elapsed = QElapsedTimer()
        self.current_file = ""
        self.tick = QTimer(self)
        self.tick.setInterval(500)
        self.tick.timeout.connect(self._update_elapsed)

        self._build_ui()
        self._restore_settings()
        self._apply_theme()
        # Open at the natural content height where the screen allows it, but
        # never demand more than a small laptop can give.
        natural = self.sizeHint().height()
        self.setMinimumHeight(min(560, natural))
        self.resize(820, min(natural, self.screen().availableGeometry().height() - 80))
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
        # Destination sits right under the source: both are answered before the
        # run and neither is worth scrolling past the options block to reach.
        self.body_layout.addWidget(self._output_card())
        self.body_layout.addWidget(self._options_card())
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

        self._wheel_guard = WheelGuard(self)
        for widget in self.findChildren(QComboBox) + self.findChildren(QAbstractSpinBox):
            widget.installEventFilter(self._wheel_guard)
            # Qt hands focus to a WheelFocus widget before the wheel event is
            # even delivered, so the guard alone still leaves a cursor blinking
            # in whatever the pointer passed over. StrongFocus is the same
            # policy minus the wheel.
            widget.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    def _header(self) -> QHBoxLayout:
        title = QLabel(APP_NAME)
        title.setObjectName("Title")
        subtitle = QLabel(
            "Извлечение структурированного текста из PDF · opendataloader-pdf"
        )
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
            if key in FORMAT_HINTS:
                box.setToolTip(FORMAT_HINTS[key])
            self.format_boxes[key] = box
            formats.addWidget(box)
        formats.addStretch()

        # -- images: the single setting that decides how long a datasheet takes
        self.image_mode = QComboBox()
        self.image_mode.addItem("Сохранять отдельными файлами", "external")
        self.image_mode.addItem("Встроить в документ", "embedded")
        self.image_mode.addItem("Не сохранять", "off")
        self.image_mode.setFixedWidth(280)
        self.image_mode.setToolTip(
            "Отдельными файлами — PNG рядом с документом, в тексте ссылки на них.\n"
            "Встроить — картинки внутри .md в виде Base64: один самодостаточный\n"
            "файл, но размер вырастает в разы.\n"
            "Не сохранять — только текст и таблицы."
        )
        self.image_mode.currentIndexChanged.connect(self._toggle_image_dpi)

        # Worth trying before turning images off entirely: 96 DPI keeps the
        # illustrations but cuts the memory the renderer needs for them.
        self.image_dpi = QSpinBox()
        self.image_dpi.setRange(36, 600)
        self.image_dpi.setValue(IMAGE_DPI_DEFAULT)
        self.image_dpi.setSuffix(" DPI")
        self.image_dpi.setFixedWidth(130)
        self.image_dpi.setToolTip(
            "Разрешение рендеринга картинок. Меньше — меньше расход памяти\n"
            "и быстрее, но грубее. 144 — по умолчанию, 96 обычно достаточно."
        )

        self.pages_edit = QLineEdit()
        self.pages_edit.setPlaceholderText("все")
        self.pages_edit.setFixedWidth(140)
        self.pages_edit.setToolTip(
            "Например 1,3,5-7. Для даташитов удобно взять описание и таблицы\n"
            "параметров, пропустив десятки страниц графиков."
        )

        self.timeout_spin = QSpinBox()
        self.timeout_spin.setRange(0, 36000)
        self.timeout_spin.setValue(30)
        self.timeout_spin.setSuffix(" с")
        self.timeout_spin.setSpecialValueText("без ограничения")
        self.timeout_spin.setFixedWidth(150)
        self.timeout_spin.setToolTip(
            "Если файл не уложился — он будет повторён без картинок,\n"
            "и только потом помечен как неудачный."
        )

        self.opt_struct = QCheckBox("Использовать теги из PDF")
        self.opt_struct.setToolTip(
            "Читать встроенную структуру документа вместо анализа вёрстки.\n"
            "Точнее — но только для PDF, где теги действительно есть."
        )
        self.opt_sanitize = QCheckBox("Скрыть чувствительные данные")

        grid = QGridLayout()
        grid.setHorizontalSpacing(24)
        grid.setVerticalSpacing(6)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.addWidget(self.opt_struct, 0, 0)
        grid.addWidget(self.opt_sanitize, 0, 1)
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)

        self.more_btn = QPushButton("Дополнительно  ▾")
        self.more_btn.setObjectName("Ghost")
        self.more_btn.setCheckable(True)
        self.more_btn.toggled.connect(self._toggle_advanced)
        more_row = QHBoxLayout()
        more_row.addWidget(self.more_btn)
        more_row.addStretch()

        return card(
            section("Форматы вывода"),
            formats,
            section("Опции"),
            field_row(
                ("Картинки:", self.image_mode),
                ("Разрешение:", self.image_dpi),
            ),
            hint(IMAGE_HINT),
            field_row(
                ("Страницы:", self.pages_edit),
                ("Таймаут на файл:", self.timeout_spin),
            ),
            grid,
            more_row,
            self._advanced_panel(),
        )

    def _advanced_panel(self) -> QWidget:
        panel = QWidget()
        panel.setVisible(False)
        self.advanced = panel

        self.reading_order = QComboBox()
        self.reading_order.addItem("xycut", "xycut")
        self.reading_order.addItem("выключен", "off")
        self.reading_order.setFixedWidth(200)
        self.reading_order.setToolTip(
            "Запасной вариант для страниц, где рекурсивное разрезание вырождается."
        )

        self.table_method = QComboBox()
        self.table_method.addItem("по разлиновке", "default")
        self.table_method.addItem("по кластерам", "cluster")
        self.table_method.setFixedWidth(200)
        self.table_method.setToolTip(
            "У многих производителей таблицы с неполной разлиновкой —\n"
            "режим по кластерам собирает их лучше."
        )

        self.image_format = QComboBox()
        self.image_format.addItem("PNG", "png")
        self.image_format.addItem("JPEG", "jpeg")
        self.image_format.setFixedWidth(200)

        self.threads_spin = QSpinBox()
        self.threads_spin.setRange(1, max(1, os.cpu_count() or 1))
        self.threads_spin.setValue(1)
        self.threads_spin.setFixedWidth(200)
        self.threads_spin.setToolTip(
            "Больше одного — страницы обрабатываются параллельно (быстрее,\n"
            "но результат на некоторых PDF может слегка отличаться)."
        )

        self.space_ratio = QDoubleSpinBox()
        self.space_ratio.setRange(0.01, 1.00)
        self.space_ratio.setSingleStep(0.01)
        self.space_ratio.setDecimals(2)
        self.space_ratio.setValue(SPACE_RATIO_DEFAULT)
        self.space_ratio.setFixedWidth(200)
        self.space_ratio.setToolTip(
            "Порог вставки пробела: доля от кегля. Если промежуток между\n"
            "соседними символами больше — между ними ставится пробел.\n"
            "Меньше — слова начинают разрываться, больше — слипаются."
        )

        self.password_edit = QLineEdit()
        self.password_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.password_edit.setPlaceholderText("для зашифрованных PDF")
        self.password_edit.setFixedWidth(200)

        self.opt_line_breaks = QCheckBox("Сохранять переносы строк")
        self.opt_header_footer = QCheckBox("Включать колонтитулы")
        self.opt_strikethrough = QCheckBox("Отмечать зачёркнутый текст")

        self.hybrid = QComboBox()
        self.hybrid.addItem("Выключен", None)
        self.hybrid.addItem("docling-fast", "docling-fast")
        self.hybrid.setFixedWidth(200)
        self.hybrid.currentIndexChanged.connect(self._toggle_hybrid)

        self.hybrid_url = QLineEdit()
        self.hybrid_url.setPlaceholderText(HYBRID_DEFAULT_URL)
        self.hybrid_url.setFixedWidth(200)
        self.hybrid_url.setEnabled(False)

        grid = QGridLayout(panel)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(14)
        grid.setVerticalSpacing(8)
        rows = [
            ("Порядок чтения:", self.reading_order, "Таблицы:", self.table_method),
            ("Формат картинок:", self.image_format, "Потоков:", self.threads_spin),
            ("Пароль PDF:", self.password_edit, "AI-режим:", self.hybrid),
            ("Порог пробела:", self.space_ratio, "Адрес сервера:", self.hybrid_url),
        ]
        for r, (l1, w1, l2, w2) in enumerate(rows):
            if l1:
                grid.addWidget(QLabel(l1), r, 0)
                grid.addWidget(w1, r, 1)
            grid.addWidget(QLabel(l2), r, 2)
            grid.addWidget(w2, r, 3)
        grid.setColumnStretch(4, 1)

        checks = QHBoxLayout()
        checks.setSpacing(24)
        checks.addWidget(self.opt_line_breaks)
        checks.addWidget(self.opt_header_footer)
        checks.addWidget(self.opt_strikethrough)
        checks.addStretch()
        grid.addLayout(checks, len(rows), 0, 1, 5)

        grid.addWidget(
            hint(
                "AI-режим требует отдельно установленного и запущенного сервера "
                "(pip install \"opendataloader-pdf[hybrid]\", затем "
                "opendataloader-pdf-hybrid --port 5002). Если сервер не отвечает, "
                "программа скажет об этом до начала работы."
            ),
            len(rows) + 1,
            0,
            1,
            5,
        )
        return panel

    def _output_card(self) -> QFrame:
        self.output_edit = QLineEdit()
        self.output_edit.setPlaceholderText("Папка рядом с исходными файлами")
        self.output_edit.setText(app_settings().value("output_dir", "", str))
        self.output_edit.editingFinished.connect(self._remember_output_dir)
        browse = QPushButton("Обзор…")
        browse.clicked.connect(self.pick_output)

        row = QHBoxLayout()
        row.setSpacing(8)
        row.addWidget(self.output_edit, 1)
        row.addWidget(browse)
        return card(
            section("Куда сохранить"),
            row,
            hint(
                "Папка запоминается и подставляется при следующем запуске. "
                "Очистите поле — и результат снова будет ложиться рядом "
                "с исходными файлами."
            ),
        )

    def _log_card(self) -> QFrame:
        self.log_view = QPlainTextEdit()
        self.log_view.setObjectName("Log")
        self.log_view.setReadOnly(True)
        self.log_view.setMinimumHeight(90)
        # An unbounded document is what turns a long conversion into a frozen
        # window; 5000 lines is far more than anyone scrolls back through.
        self.log_view.setMaximumBlockCount(5000)
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

        self.cancel_btn = QPushButton("Отмена")
        self.cancel_btn.setObjectName("Danger")
        self.cancel_btn.clicked.connect(self.cancel)
        self.cancel_btn.setVisible(False)

        self.run_btn = QPushButton("Конвертировать")
        self.run_btn.setObjectName("Primary")
        self.run_btn.setEnabled(False)
        self.run_btn.clicked.connect(self.start)

        row = QHBoxLayout()
        row.addWidget(self.status, 1)
        row.addWidget(self.log_btn)
        row.addWidget(self.open_btn)
        row.addWidget(self.cancel_btn)
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
        # Only a theme picked by hand is remembered; until then the window
        # keeps following the system setting.
        app_settings().setValue("dark", self.dark)

    # -- remembered settings ---------------------------------------------- #

    def _persisted_widgets(self) -> list[tuple[str, QWidget]]:
        """Everything worth having back on the next launch.

        Left out on purpose: the page range, which belongs to one document, and
        the PDF password, which has no business sitting in the registry. The
        destination folder is saved on its own, the moment it is chosen.
        """
        widgets: list[tuple[str, QWidget]] = [
            (f"format/{key}", box) for key, box in self.format_boxes.items()
        ]
        widgets += [
            ("image_mode", self.image_mode),
            ("image_dpi", self.image_dpi),
            ("timeout", self.timeout_spin),
            ("use_struct_tree", self.opt_struct),
            ("sanitize", self.opt_sanitize),
            ("reading_order", self.reading_order),
            ("table_method", self.table_method),
            ("image_format", self.image_format),
            ("threads", self.threads_spin),
            ("space_ratio", self.space_ratio),
            ("keep_line_breaks", self.opt_line_breaks),
            ("include_header_footer", self.opt_header_footer),
            ("detect_strikethrough", self.opt_strikethrough),
            ("hybrid", self.hybrid),
            ("hybrid_url", self.hybrid_url),
            ("advanced_open", self.more_btn),
        ]
        return widgets

    def _save_settings(self) -> None:
        settings = app_settings()
        for key, widget in self._persisted_widgets():
            settings.setValue(f"options/{key}", widget_value(widget))

    def _restore_settings(self) -> None:
        settings = app_settings()
        for key, widget in self._persisted_widgets():
            value = settings.value(f"options/{key}")
            if value is not None:
                set_widget_value(widget, value)

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
            self,
            "Куда сохранить результат",
            self.output_edit.text() or str(Path.home()),
        )
        if path:
            self.output_edit.setText(path)
            self._remember_output_dir()

    def _remember_output_dir(self) -> None:
        app_settings().setValue("output_dir", self.output_edit.text().strip())

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

    def _toggle_advanced(self, shown: bool) -> None:
        self.advanced.setVisible(shown)
        self.more_btn.setText("Дополнительно  ▴" if shown else "Дополнительно  ▾")

    def _toggle_image_dpi(self) -> None:
        self.image_dpi.setEnabled(self.image_mode.currentData() != "off")

    def _toggle_hybrid(self) -> None:
        self.hybrid_url.setEnabled(bool(self.hybrid.currentData()))

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
            QMessageBox.warning(self, APP_NAME, "Выберите хотя бы один формат вывода.")
            return None

        options: dict = {
            "format": ",".join(formats),
            "content_safety_off": CONTENT_SAFETY_OFF,
            # TI and friends ship subset fonts without ToUnicode; the default
            # replacement is a space, so those glyphs vanish silently.
            "replace_invalid_chars": "?",
            "image_output": self.image_mode.currentData(),
            "use_struct_tree": self.opt_struct.isChecked(),
            "sanitize": self.opt_sanitize.isChecked(),
            "keep_line_breaks": self.opt_line_breaks.isChecked(),
            "include_header_footer": self.opt_header_footer.isChecked(),
            "detect_strikethrough": self.opt_strikethrough.isChecked(),
            "reading_order": self.reading_order.currentData(),
            "table_method": self.table_method.currentData(),
            "image_format": self.image_format.currentData(),
        }

        if "markdown" in formats:
            # Electrical Characteristics tables are built on merged cells and
            # fall apart in plain Markdown.
            options["markdown_with_html"] = True
            options["markdown_page_separator"] = PAGE_SEPARATOR
        if "text" in formats:
            options["text_page_separator"] = PAGE_SEPARATOR
        if "html" in formats:
            options["html_page_separator"] = PAGE_SEPARATOR

        if self.image_dpi.value() != IMAGE_DPI_DEFAULT:
            options["image_resolution"] = str(self.image_dpi.value())
        if round(self.space_ratio.value(), 2) != SPACE_RATIO_DEFAULT:
            options["space_ratio"] = f"{self.space_ratio.value():.2f}"

        pages = self.pages_edit.text().strip()
        if pages:
            options["pages"] = pages
        if self.threads_spin.value() > 1:
            options["threads"] = str(self.threads_spin.value())
        if self.password_edit.text():
            options["password"] = self.password_edit.text()

        hybrid = self.hybrid.currentData()
        if hybrid:
            options["hybrid"] = hybrid
            # Never again without these two: no timeout means an unanswered
            # request waits forever, no fallback means no way back to Java.
            options["hybrid_timeout"] = HYBRID_TIMEOUT_MS
            options["hybrid_fallback"] = True
            url = self.hybrid_url.text().strip()
            if url:
                options["hybrid_url"] = url
        return options

    def _confirm_hybrid(self, options: dict) -> bool:
        """Check the hybrid server before handing it the whole batch."""
        if not options.get("hybrid"):
            return True
        url = options.get("hybrid_url") or HYBRID_DEFAULT_URL
        if server_reachable(url):
            return True
        answer = QMessageBox.question(
            self,
            APP_NAME,
            f"AI-режим включён, но сервер {url} не отвечает.\n\n"
            "Он ставится и запускается отдельно:\n"
            '    pip install "opendataloader-pdf[hybrid]"\n'
            "    opendataloader-pdf-hybrid --port 5002\n\n"
            "Конвертировать обычным способом, без AI-режима?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return False
        for key in ("hybrid", "hybrid_timeout", "hybrid_fallback", "hybrid_url"):
            options.pop(key, None)
        return True

    def _confirm_unsupported(self, options: dict, supported: set[str] | None) -> bool:
        """Say out loud which options the installed version will ignore."""
        if supported is None:
            return True
        dropped = sorted(k for k in options if k not in supported)
        if not dropped:
            return True
        answer = QMessageBox.question(
            self,
            APP_NAME,
            "Установленная версия opendataloader-pdf не поддерживает эти "
            "настройки, они будут проигнорированы:\n\n    "
            + "\n    ".join(dropped)
            + "\n\nОбновить пакет: pip install -U opendataloader-pdf\n\n"
            "Продолжить без них?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
        )
        return answer == QMessageBox.StandardButton.Yes

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
        jobs = plan_jobs(self.inputs, output_dir)
        if not jobs:
            QMessageBox.warning(
                self, APP_NAME, "В выбранных папках не нашлось ни одного PDF."
            )
            return

        supported = supported_option_names()
        if not self._confirm_unsupported(options, supported):
            return
        if not self._confirm_hybrid(options):
            return

        # A path typed and never tabbed away from would otherwise be forgotten;
        # the options are saved here too, as the set the user actually ran with.
        self._remember_output_dir()
        self._save_settings()
        try:
            os.makedirs(output_dir, exist_ok=True)
        except OSError as exc:
            QMessageBox.critical(
                self, APP_NAME, f"Не удалось создать папку результата:\n{exc}"
            )
            return

        self.output_dir = output_dir
        self.log_view.clear()
        if options.get("hybrid"):
            self.append_log(
                f"AI-режим: {options['hybrid']} · "
                f"{options.get('hybrid_url') or HYBRID_DEFAULT_URL} (сервер отвечает)"
            )
        self._set_busy(True, len(jobs))
        self.elapsed.start()
        self.tick.start()

        self.thread = QThread(self)
        self.worker = ConvertWorker(
            jobs, output_dir, options, self.timeout_spin.value(), supported
        )
        self.worker.moveToThread(self.thread)
        self.thread.started.connect(self.worker.run)
        self.worker.log.connect(self.append_log)
        self.worker.progress.connect(self.on_progress)
        self.worker.finished.connect(self.on_finished)
        self.thread.start()

    def cancel(self) -> None:
        if self.worker is not None:
            self.cancel_btn.setEnabled(False)
            self.tick.stop()  # otherwise the next tick overwrites the message
            self._set_status("Останавливаю…")
            self.worker.cancel()

    def on_progress(self, index: int, total: int, name: str) -> None:
        self.current_file = name
        self.progress.setValue(index - 1)
        self._update_elapsed()

    def on_finished(self, summary: dict) -> None:
        self.tick.stop()
        if self.thread is not None:
            self.thread.quit()
            self.thread.wait()
        self.thread = None
        self.worker = None
        self._set_busy(False)

        seconds = self.elapsed.elapsed() / 1000
        ok, total = summary["ok"], summary["total"]

        if summary["error"]:
            self._set_status("Не удалось", state="error")
            self.append_log(summary["error"])
            self._toggle_log(True)  # the details are the point when it breaks
            QMessageBox.critical(self, APP_NAME, summary["error"])
            return

        notes = []
        if summary["degraded"]:
            notes.append(
                "без картинок (не укладывались во время): "
                + ", ".join(summary["degraded"])
            )
        if summary["timed_out"]:
            notes.append("прерваны по таймауту: " + ", ".join(summary["timed_out"]))
        if summary["failed"]:
            notes.append("с ошибкой: " + ", ".join(summary["failed"]))

        if summary["cancelled"]:
            headline = f"Отменено · готово {ok} из {total}"
            state = "error" if ok == 0 else ""
        elif ok == total and not notes:
            headline = f"Готово за {seconds:.1f} с"
            state = "ok"
        elif ok:
            headline = f"Сконвертировано {ok} из {total} за {seconds:.1f} с"
            state = "ok"
        else:
            headline = f"Не удалось сконвертировать ни одного файла из {total}"
            state = "error"

        self._set_status(headline, state=state)
        self.append_log(headline + ("; " + "; ".join(notes) if notes else ""))
        if ok:
            self.open_btn.setVisible(True)
        if notes:
            QMessageBox.information(
                self, APP_NAME, headline + ":\n\n" + "\n".join(notes)
            )
        elif ok == 0 and not summary["cancelled"]:
            self._toggle_log(True)
            QMessageBox.critical(self, APP_NAME, headline)

    def open_output(self) -> None:
        QDesktopServices.openUrl(QUrl.fromLocalFile(self.output_dir))

    # -- small helpers ------------------------------------------------------ #

    def _set_busy(self, busy: bool, total: int = 0) -> None:
        self.progress.setVisible(busy)
        self.progress.setRange(0, total if busy else 1)
        self.progress.setValue(0)
        self.run_btn.setEnabled(not busy)
        self.run_btn.setText("Конвертация…" if busy else "Конвертировать")
        self.cancel_btn.setVisible(busy)
        self.cancel_btn.setEnabled(busy)
        if busy:
            self.open_btn.setVisible(False)
            self.current_file = ""
            self._set_status("Работаю…")

    def _set_status(self, text: str, state: str = "") -> None:
        self.status.setText(text)
        self.status.setProperty("state", state)
        self.status.style().unpolish(self.status)
        self.status.style().polish(self.status)

    def _update_elapsed(self) -> None:
        seconds = self.elapsed.elapsed() / 1000
        total = self.progress.maximum()
        done = self.progress.value()
        prefix = f"Файл {done + 1} из {total}" if total > 1 else "Работаю"
        name = f" · {self.current_file}" if self.current_file else ""
        self._set_status(f"{prefix}{name} · {seconds:.0f} с")

    def append_log(self, text: str) -> None:
        self.log_view.appendPlainText(text)
        self.log_view.verticalScrollBar().setValue(
            self.log_view.verticalScrollBar().maximum()
        )

    def _check_java(self) -> None:
        """opendataloader-pdf needs a JVM; say so early and in plain words."""
        self.append_log(f"opendataloader-pdf {odl_version()}")
        java = java_executable()
        if java:
            self.append_log(f"Java найдена: {java}")
            # The path alone does not tell which runtime actually answers; when
            # something goes wrong the version is the first thing worth knowing.
            try:
                result = subprocess.run(
                    [java, "-version"],
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    timeout=15,
                    creationflags=_no_window(),
                )
                line = (result.stderr or result.stdout or "").strip().splitlines()
                if line:
                    self.append_log(f"Версия: {line[0].strip()}")
            except (OSError, subprocess.SubprocessError):
                pass
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
            # Stop the JVM explicitly: it is a child process and would keep
            # running - and keep writing files - after the window is gone.
            if self.worker is not None:
                self.worker.cancel()
            self.thread.quit()
            self.thread.wait(15000)
        self._save_settings()
        event.accept()


def _system_prefers_dark() -> bool:
    hints = QGuiApplication.styleHints()
    scheme = getattr(hints, "colorScheme", None)
    if scheme is None:  # Qt < 6.5
        return True
    return scheme() == Qt.ColorScheme.Dark


def main() -> int:
    use_bundled_jre()
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    window = MainWindow()
    # app.arguments() rather than sys.argv: Qt has already taken its own
    # switches out of it.
    window.add_paths(startup_paths(app.arguments()[1:]))
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
