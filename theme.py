"""Theme palettes and QSS generation for the PDF to Markdown converter UI.

The stylesheet is generated from a palette dictionary so that light and dark
variants stay in sync: add a colour once, use it in both themes.
"""

import tempfile
from pathlib import Path

# Qt stylesheets do not understand data: URIs, so the generated icons are
# written to a temp folder once and referenced by path.
_ICON_DIR = Path(tempfile.mkdtemp(prefix="pdf2md-icons-"))


def _icon(name: str, svg: str) -> str:
    """Write an SVG to the icon cache and return a QSS-safe path."""
    path = _ICON_DIR / f"{name}.svg"
    if not path.exists():
        path.write_text(svg, encoding="utf-8")
    return path.as_posix()

DARK = {
    "bg": "#16181d",
    "surface": "#1e2128",
    "surface_alt": "#252932",
    "border": "#31363f",
    "border_strong": "#3d4450",
    "text": "#e6e8ec",
    "text_muted": "#9aa1ad",
    "accent": "#5b8cff",
    "accent_hover": "#6f9bff",
    "accent_pressed": "#4a78e0",
    "accent_soft": "#1f2a44",
    "success": "#3fbf7f",
    "danger": "#e5484d",
    "log_bg": "#12141a",
}

LIGHT = {
    "bg": "#f4f5f7",
    "surface": "#ffffff",
    "surface_alt": "#f0f1f4",
    "border": "#dfe1e6",
    "border_strong": "#c5c9d1",
    "text": "#1c1f26",
    "text_muted": "#6b7280",
    "accent": "#3b6fe0",
    "accent_hover": "#4d7de8",
    "accent_pressed": "#2f5cc0",
    "accent_soft": "#e8eefc",
    "success": "#1f9d5f",
    "danger": "#d13438",
    "log_bg": "#fbfbfc",
}

FONT_STACK = '"Inter", "Segoe UI Variable", "Segoe UI", "SF Pro Text", system-ui, sans-serif'
MONO_STACK = '"JetBrains Mono", "Cascadia Mono", "SF Mono", Consolas, monospace'


def build_qss(p: dict) -> str:
    """Return a full stylesheet for the given palette."""
    theme_id = "dark" if p is DARK else "light"
    arrow = _icon(
        f"arrow-{theme_id}",
        '<svg xmlns="http://www.w3.org/2000/svg" width="12" height="12" '
        'viewBox="0 0 12 12" fill="none">'
        f'<path d="M2.5 4.5L6 8l3.5-3.5" stroke="{p["text_muted"]}" stroke-width="1.6"'
        ' stroke-linecap="round" stroke-linejoin="round"/></svg>',
    )
    arrow_up = _icon(
        f"arrow-up-{theme_id}",
        '<svg xmlns="http://www.w3.org/2000/svg" width="12" height="12" '
        'viewBox="0 0 12 12" fill="none">'
        f'<path d="M2.5 7.5L6 4l3.5 3.5" stroke="{p["text_muted"]}" stroke-width="1.6"'
        ' stroke-linecap="round" stroke-linejoin="round"/></svg>',
    )
    menu_check = _icon(
        f"menu-check-{theme_id}",
        '<svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" '
        'viewBox="0 0 14 14" fill="none">'
        f'<path d="M3 7.3l2.6 2.6L11 4.5" stroke="{p["accent"]}" stroke-width="2"'
        ' stroke-linecap="round" stroke-linejoin="round"/></svg>',
    )
    check = _icon(
        "check",
        '<svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" '
        'viewBox="0 0 14 14" fill="none">'
        '<path d="M3 7.3l2.6 2.6L11 4.5" stroke="#ffffff" stroke-width="2"'
        ' stroke-linecap="round" stroke-linejoin="round"/></svg>',
    )
    return f"""
* {{
    font-family: {FONT_STACK};
    font-size: 13px;
    color: {p['text']};
    outline: none;
}}

QWidget#Root, QWidget#Body {{
    background: {p['bg']};
}}

QScrollArea#Scroll {{
    background: transparent;
    border: none;
}}

/* ---- Menu bar ---- */

QMenuBar {{
    background: {p['surface']};
    border-bottom: 1px solid {p['border']};
    padding: 2px 8px;
}}

QMenuBar::item {{
    background: transparent;
    padding: 6px 10px;
    border-radius: 6px;
}}

QMenuBar::item:selected, QMenuBar::item:pressed {{
    background: {p['surface_alt']};
}}

QMenu {{
    background: {p['surface']};
    border: 1px solid {p['border_strong']};
    border-radius: 8px;
    padding: 4px;
}}

QMenu::item {{
    padding: 6px 28px 6px 26px;
    border-radius: 6px;
}}

QMenu::item:selected {{
    background: {p['accent_soft']};
    color: {p['text']};
}}

QMenu::item:disabled {{
    color: {p['text_muted']};
}}

QMenu::separator {{
    height: 1px;
    background: {p['border']};
    margin: 4px 8px;
}}

QMenu::indicator {{
    width: 14px;
    height: 14px;
    left: 6px;
}}

QMenu::indicator:checked {{
    image: url("{menu_check}");
}}

/* Dialogs - message boxes included - otherwise take the background from
   Windows while the text colour comes from this sheet: with Windows in dark
   mode and the app in light, questions came out dark on dark. */
QDialog {{
    background: {p['bg']};
}}

/* ---- Header ---- */

QLabel#UpdateLink {{
    background: {p['accent_soft']};
    border-radius: 10px;
    padding: 2px 10px;
    margin: 3px 4px;
    font-weight: 600;
}}

QLabel#SectionLabel {{
    font-size: 11px;
    font-weight: 600;
    letter-spacing: 0.6px;
    color: {p['text_muted']};
}}

/* ---- Cards ---- */

QFrame#Card {{
    background: {p['surface']};
    border: 1px solid {p['border']};
    border-radius: 12px;
}}

/* ---- Drop zone ---- */

QFrame#DropZone {{
    background: {p['surface']};
    border: 2px dashed {p['border_strong']};
    border-radius: 12px;
}}

QFrame#DropZone[dragActive="true"] {{
    background: {p['accent_soft']};
    border: 2px dashed {p['accent']};
}}

QLabel#DropHint {{
    color: {p['text_muted']};
    font-size: 13px;
}}

QLabel#DropIcon {{
    font-size: 30px;
}}

/* ---- File list ---- */

QListWidget {{
    background: {p['surface_alt']};
    border: 1px solid {p['border']};
    border-radius: 8px;
    padding: 4px;
}}

/* Files dragged over the window land in the list: show it, like the drop zone. */
QListWidget[dragActive="true"] {{
    background: {p['accent_soft']};
    border: 2px dashed {p['accent']};
}}

QListWidget::item {{
    padding: 7px 10px;
    border-radius: 6px;
}}

QListWidget::item:selected {{
    background: {p['accent_soft']};
    color: {p['text']};
}}

QListWidget::item:hover {{
    background: {p['surface']};
}}

/* ---- Buttons ---- */

QPushButton {{
    background: {p['surface_alt']};
    border: 1px solid {p['border_strong']};
    border-radius: 8px;
    padding: 8px 16px;
    font-weight: 500;
}}

QPushButton:hover {{
    background: {p['surface']};
    border-color: {p['accent']};
}}

QPushButton:pressed {{
    background: {p['border']};
}}

QPushButton:disabled {{
    color: {p['text_muted']};
    border-color: {p['border']};
    background: {p['surface_alt']};
}}

QPushButton#Primary {{
    background: {p['accent']};
    border: 1px solid {p['accent']};
    color: #ffffff;
    font-size: 14px;
    font-weight: 600;
    padding: 12px 24px;
    border-radius: 10px;
}}

QPushButton#Primary:hover {{
    background: {p['accent_hover']};
    border-color: {p['accent_hover']};
}}

QPushButton#Primary:pressed {{
    background: {p['accent_pressed']};
}}

QPushButton#Primary:disabled {{
    background: {p['border']};
    border-color: {p['border']};
    color: {p['text_muted']};
}}

QPushButton#Danger {{
    background: transparent;
    border: 1px solid {p['border_strong']};
    color: {p['danger']};
}}

QPushButton#Danger:hover {{
    border-color: {p['danger']};
    background: {p['surface_alt']};
}}

QPushButton#Ghost {{
    background: transparent;
    border: none;
    color: {p['text_muted']};
    padding: 6px 10px;
}}

QPushButton#Ghost:hover {{
    color: {p['accent']};
    background: {p['surface_alt']};
}}

/* "Reset" at the end of a section caption: there, not shouting. */
QPushButton#Small {{
    background: transparent;
    border: 1px solid {p['border']};
    border-radius: 6px;
    color: {p['text_muted']};
    padding: 3px 10px;
    font-size: 12px;
}}

QPushButton#Small:hover {{
    color: {p['accent']};
    border-color: {p['accent']};
}}

/* A saved destination: the whole row is the button. */
QPushButton#Favorite {{
    text-align: left;
    padding: 7px 12px;
    font-weight: 400;
}}

QPushButton#Favorite[current="true"] {{
    background: {p['accent_soft']};
    border-color: {p['accent']};
    color: {p['accent']};
    font-weight: 600;
}}

QPushButton#FavoriteRemove {{
    background: transparent;
    border: 1px solid transparent;
    color: {p['text_muted']};
    padding: 6px 10px;
}}

QPushButton#FavoriteRemove:hover {{
    color: {p['danger']};
    border-color: {p['danger']};
}}

/* ---- Help ---- */

/* The box a (?) opens; the (?) itself is drawn in gui.HelpMark. */
QLabel#HelpPopup {{
    background: {p['surface']};
    color: {p['text']};
    border: 1px solid {p['border_strong']};
    padding: 4px 12px;
}}

/* ---- User guide ---- */

QTextBrowser#GuideText {{
    background: {p['surface']};
    border: 1px solid {p['border']};
    border-radius: 8px;
    padding: 12px 16px;
    font-size: 13px;
}}

/* ---- Inputs ---- */

QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox {{
    background: {p['surface_alt']};
    border: 1px solid {p['border_strong']};
    border-radius: 8px;
    padding: 8px 12px;
    selection-background-color: {p['accent']};
    selection-color: #ffffff;
}}

QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus {{
    border-color: {p['accent']};
}}

QLineEdit:disabled, QComboBox:disabled, QSpinBox:disabled,
QDoubleSpinBox:disabled {{
    color: {p['text_muted']};
}}

/* The spin buttons are tiny and hard to hit; the field is meant to be typed
   into, so they only need to stay out of the way. */
QSpinBox::up-button, QSpinBox::down-button,
QDoubleSpinBox::up-button, QDoubleSpinBox::down-button {{
    width: 16px;
    border: none;
    background: transparent;
}}

QSpinBox::up-arrow, QDoubleSpinBox::up-arrow {{
    width: 8px;
    height: 8px;
    image: url("{arrow_up}");
}}

QSpinBox::down-arrow, QDoubleSpinBox::down-arrow {{
    width: 8px;
    height: 8px;
    image: url("{arrow}");
}}

QLabel#Hint {{
    color: {p['text_muted']};
    font-size: 12px;
}}

QComboBox::drop-down {{
    subcontrol-origin: padding;
    subcontrol-position: center right;
    border: none;
    width: 24px;
}}

QComboBox::down-arrow {{
    width: 10px;
    height: 10px;
    image: url("{arrow}");
}}

QComboBox QAbstractItemView {{
    background: {p['surface']};
    border: 1px solid {p['border_strong']};
    border-radius: 8px;
    padding: 4px;
    selection-background-color: {p['accent_soft']};
    selection-color: {p['text']};
    outline: none;
}}

/* ---- Checkboxes ---- */

QCheckBox {{
    spacing: 9px;
    padding: 3px 0;
    min-height: 22px;
}}

QCheckBox::indicator {{
    width: 17px;
    height: 17px;
    border: 1px solid {p['border_strong']};
    border-radius: 5px;
    background: {p['surface_alt']};
}}

QCheckBox::indicator:hover {{
    border-color: {p['accent']};
}}

QCheckBox::indicator:checked {{
    background: {p['accent']};
    border-color: {p['accent']};
    image: url("{check}");
}}

QCheckBox:disabled {{
    color: {p['text_muted']};
}}

/* ---- Progress ---- */

QProgressBar {{
    background: {p['surface_alt']};
    border: none;
    border-radius: 4px;
    height: 6px;
    text-align: center;
}}

QProgressBar::chunk {{
    background: {p['accent']};
    border-radius: 4px;
}}

QLabel#StatusText {{
    color: {p['text_muted']};
    font-size: 12px;
}}

QLabel#StatusText[state="ok"] {{
    color: {p['success']};
    font-weight: 500;
}}

QLabel#StatusText[state="error"] {{
    color: {p['danger']};
    font-weight: 500;
}}

/* ---- Log ---- */

QPlainTextEdit#Log {{
    background: {p['log_bg']};
    border: 1px solid {p['border']};
    border-radius: 8px;
    padding: 8px;
    font-family: {MONO_STACK};
    font-size: 12px;
    color: {p['text_muted']};
}}

/* ---- Scrollbars ---- */

QScrollBar:vertical {{
    background: transparent;
    width: 10px;
    margin: 2px;
}}

QScrollBar::handle:vertical {{
    background: {p['border_strong']};
    border-radius: 4px;
    min-height: 28px;
}}

QScrollBar::handle:vertical:hover {{
    background: {p['text_muted']};
}}

QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical,
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
    background: none;
    height: 0;
}}

QScrollBar:horizontal {{
    background: transparent;
    height: 10px;
    margin: 2px;
}}

QScrollBar::handle:horizontal {{
    background: {p['border_strong']};
    border-radius: 4px;
    min-width: 28px;
}}

QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal,
QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {{
    background: none;
    width: 0;
}}

QToolTip {{
    background: {p['surface']};
    color: {p['text']};
    border: 1px solid {p['border_strong']};
    border-radius: 6px;
    padding: 6px 8px;
}}
"""
