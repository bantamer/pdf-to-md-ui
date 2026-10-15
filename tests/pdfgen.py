"""A dependency-free writer for the one kind of PDF the memory tests need.

A datasheet's plot pages are thousands of separate stroke operations - axis
ticks, grid lines, curves drawn segment by segment. That is what veraPDF's
line-art parsing chokes on, so that is what this produces: one page, a title,
and `strokes` short lines each painted on its own.
"""

from pathlib import Path


def dense_line_pdf(path: Path, strokes: int) -> Path:
    ops = ["BT /F1 12 Tf 50 800 Td (Typical Characteristics) Tj ET", "0.3 w"]
    for i in range(strokes):
        x = 50 + (i % 500) * 1.0
        y = 780 - (i // 500) * 6.0
        ops.append(f"{x:.1f} {y:.1f} m {x + 0.8:.1f} {y - 3:.1f} l S")
    content = "\n".join(ops).encode("ascii")

    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] "
        b"/Resources << /Font << /F1 5 0 R >> >> /Contents 4 0 R >>",
        b"<< /Length %d >>\nstream\n" % len(content) + content + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]

    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for number, body in enumerate(objects, 1):
        offsets.append(len(out))
        out += b"%d 0 obj\n" % number + body + b"\nendobj\n"
    xref = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objects) + 1)
    for offset in offsets:
        out += b"%010d 00000 n \n" % offset
    out += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (
        len(objects) + 1,
        xref,
    )
    path.write_bytes(bytes(out))
    return path
