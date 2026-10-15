"""Draw the application icon and write icon.ico (plus docs/icon.png).

    python tools/make_icon.py

A blue rounded square in the app's accent colour, a white page with a folded
corner, and the Markdown mark "M↓" on it. Drawn with plain shapes rather than
a font so it renders the same everywhere, and drawn separately at every size
instead of scaled down from one bitmap, so 16 px stays crisp.

The .ico holds PNG-compressed images, which Windows has read since Vista;
PyInstaller embeds it into the exe and Inno Setup into the installer.
"""

from __future__ import annotations

import struct
import sys
from pathlib import Path

from PySide6.QtCore import QBuffer, QByteArray, QIODevice, QPointF, QRectF, Qt
from PySide6.QtGui import (
    QBrush,
    QColor,
    QGuiApplication,
    QImage,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
    QPolygonF,
)

ROOT = Path(__file__).resolve().parent.parent
SIZES = (16, 20, 24, 32, 40, 48, 64, 96, 128, 256)

TOP = QColor("#4f80ee")  # a shade above the light theme's accent #3b6fe0
BOTTOM = QColor("#2f5cc0")  # the accent's pressed shade
FOLD = QColor("#c9d6f5")
MARK = QColor("#2f5cc0")


def draw(size: int) -> QImage:
    image = QImage(size, size, QImage.Format.Format_ARGB32)
    image.fill(Qt.GlobalColor.transparent)
    p = QPainter(image)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.scale(size / 256, size / 256)  # everything below is on a 256 grid

    gradient = QLinearGradient(0, 12, 0, 244)
    gradient.setColorAt(0, TOP)
    gradient.setColorAt(1, BOTTOM)
    square = QPainterPath()
    square.addRoundedRect(QRectF(12, 12, 232, 232), 52, 52)
    p.fillPath(square, QBrush(gradient))

    page = QPolygonF(
        [QPointF(70, 40), QPointF(156, 40), QPointF(196, 80),
         QPointF(196, 216), QPointF(70, 216)]
    )
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor("white"))
    p.drawPolygon(page)
    p.setBrush(FOLD)
    p.drawPolygon(QPolygonF([QPointF(156, 40), QPointF(156, 80), QPointF(196, 80)]))

    # Small sizes get heavier strokes, or the mark melts into the page.
    width = 22 if size <= 24 else 16
    pen = QPen(MARK, width, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap,
               Qt.PenJoinStyle.RoundJoin)
    p.setPen(pen)
    p.setBrush(Qt.BrushStyle.NoBrush)
    m = QPainterPath(QPointF(86, 186))
    for x, y in ((86, 118), (109, 150), (132, 118), (132, 186)):
        m.lineTo(x, y)
    p.drawPath(m)
    p.drawLine(QPointF(164, 118), QPointF(164, 166))
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(MARK)
    p.drawPolygon(QPolygonF([QPointF(146, 160), QPointF(182, 160), QPointF(164, 190)]))
    p.end()
    return image


def png_bytes(image: QImage) -> bytes:
    data = QByteArray()
    buffer = QBuffer(data)
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    image.save(buffer, "PNG")
    return bytes(data)


def write_ico(path: Path, images: list[tuple[int, bytes]]) -> None:
    header = struct.pack("<HHH", 0, 1, len(images))
    offset = len(header) + 16 * len(images)
    entries, blobs = b"", b""
    for size, blob in images:
        side = 0 if size >= 256 else size  # 0 means 256 in the ICO format
        entries += struct.pack("<BBBBHHII", side, side, 0, 0, 1, 32, len(blob), offset)
        blobs += blob
        offset += len(blob)
    path.write_bytes(header + entries + blobs)


def main() -> None:
    QGuiApplication.instance() or QGuiApplication(sys.argv[:1])
    images = [(s, png_bytes(draw(s))) for s in SIZES]
    write_ico(ROOT / "icon.ico", images)
    draw(128).save(str(ROOT / "docs" / "icon.png"))
    print(f"icon.ico: {len(images)} sizes, {(ROOT / 'icon.ico').stat().st_size} bytes")


if __name__ == "__main__":
    main()
