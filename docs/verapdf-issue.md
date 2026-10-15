# Quadratic memory growth in `ChunkParser.processLineArts` (validation-model ≥ 1.31.175)

*Filed as [veraPDF/veraPDF-library#1641](https://github.com/veraPDF/veraPDF-library/issues/1641).
This file is the text as submitted.*

---

## Summary

Since `org.verapdf:validation-model` 1.31.175, parsing chunks of a page with many
separately painted strokes takes memory proportional to the **square** of the
number of strokes, and ends in `OutOfMemoryError`. 1.31.169 handles the same
pages in constant memory. The pages in question are ordinary: the plot pages of
an electronics datasheet are thousands of individually stroked segments.

Real-world impact, through opendataloader-pdf (which calls
`GFSAPDFDocument.parseChunks`):

| Document | validation-model 1.31.169 (ODL 2.5.8) | 1.31.200 (ODL 2.5.13) |
|---|---|---|
| TI TPS7A02 datasheet, SBVS277C, 48 pages | converts in 3 s with `-Xmx512m` | `OutOfMemoryError` up to `-Xmx12g`; converts with `-Xmx14g`, 9 s |
| TI LM2917-N datasheet | converts with `-Xmx1g` | `OutOfMemoryError` with `-Xmx1g` |

Both datasheets are public on ti.com.

Not the same as
[opendataloader-pdf#458](https://github.com/opendataloader-project/opendataloader-pdf/issues/458):
that one runs out of memory rasterising large images in PDFBox
(`PDDeviceRGB.toRGBImage`). This one is in chunk parsing of vector line art,
before any rendering, and happens just the same with image output switched off
(`--image-output off`).

## Versions

| | |
|---|---|
| Last good | validation-model **1.31.169** (bundled in opendataloader-pdf 2.5.8) |
| First bad | validation-model **1.31.175** (opendataloader-pdf 2.5.9) |
| Still bad | validation-model **1.31.200** (opendataloader-pdf 2.5.13) |
| Java | 26.0.2 (Oracle JDK and a jlink runtime), Windows 11 x64 |

## Reproduction

A dependency-free script that writes one page with a title and `N` short lines,
each stroked on its own (`x y m x2 y2 l S`), with no marked content:

```python
# dense_lines.py N out.pdf
import sys

def dense_line_pdf(path, strokes):
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
        len(objects) + 1, xref)
    open(path, "wb").write(bytes(out))

dense_line_pdf(sys.argv[2], int(sys.argv[1]))
```

```
python dense_lines.py 3000 lines3000.pdf
pip download opendataloader-pdf==2.5.13 --no-deps   # jar is inside the wheel
java -Xmx256m -jar opendataloader-pdf-cli.jar lines3000.pdf --output-dir out --format json
```

Result of that command, and of the same with other stroke counts and heap
sizes (one page, `--format json --image-output off`):

| Strokes | 1.31.169: 64 MB | 256 MB | 1 GB | 1.31.200: 64 MB | 256 MB | 1 GB | 4 GB |
|---|---|---|---|---|---|---|---|
| 1000 | ok | ok | ok | ok | ok | ok | ok |
| 2000 | ok | ok | ok | **OOM** | ok | ok | ok |
| 3000 | ok | ok | ok | **OOM** | **OOM** | ok | ok |
| 4000 | ok | ok | ok | **OOM** | **OOM** | ok | ok |
| 6000 | ok | ok | ok | **OOM** | **OOM** | **OOM** | ok |

With 1.31.169 every run takes ~0.45 s regardless of the count; with 1.31.200
time grows too (0.49 s at 1000 strokes, 0.94 s at 6000).

Stack trace (TPS7A02, opendataloader-pdf 2.5.13):

```
java.lang.OutOfMemoryError: Java heap space
    at org.verapdf.gf.model.factory.chunks.ChunkParser.processLineArts(ChunkParser.java:1166)
    at org.verapdf.gf.model.factory.chunks.ChunkParser.parseChunk(ChunkParser.java:261)
    at org.verapdf.gf.model.factory.chunks.ChunkFactory.chunksFromTokens(ChunkFactory.java:48)
    at org.verapdf.gf.model.impl.sa.GFSAContentStream.parseChunks(GFSAContentStream.java:89)
    at org.verapdf.gf.model.impl.sa.GFSAPDFDocument.parseChunks(GFSAPDFDocument.java:187)
    at org.opendataloader.pdf.processors.DocumentProcessor.preprocessing(DocumentProcessor.java:674)
```

## Cause

From the compiled classes (`javap -c -p`, so method names are certain, the
exact source lines are not):

In 1.31.169, `processLineArts` takes the `LineChunk`s of the current key from
`LineArtContainer.getLineChunks(Long)`, adds them to `artifacts` and clears the
list; then does the same for `getBoundingBoxes(Long)`, wrapping each box in a
`LineArtChunk`. Linear.

In 1.31.175+, the painting methods gained an `int` argument (`processS(int)`,
`processf(int)`, `processB(int)`, `processLineChunk(…, int)`,
`processBoundingBox(…, int)`), and `processLineArts` first fetches
`LineArtContainer.getStreamInfos(Long)` for the key. It then runs, in effect:

```java
for (LineChunk chunk : lineChunks)
    for (StreamInfo info : streamInfos)
        chunk.getStreamInfos().add(new StreamInfo(info));

for (BoundingBox box : boundingBoxes) {
    LineArtChunk lineArt = new LineArtChunk(box);
    for (StreamInfo info : streamInfos)
        lineArt.getStreamInfos().add(new StreamInfo(info));
    ...
}
```

Every chunk receives a copy of every `StreamInfo` of its key, not only the one
for the operator that painted it. On a page without marked content all graphics
share one key, so N strokes produce N line chunks × N stream infos: 9 million
`StreamInfo` objects for 3000 strokes, which matches the measured thresholds.

## Suggested fix

Attach to each chunk only the `StreamInfo` of the operator that produced it —
the operator index is already passed to `processS`/`processf`/`processB` — or,
if every chunk of the key really does need the whole list, share one list
instead of copying it into each chunk.

## Workaround

Putting the 1.31.169 `ChunkParser.class` ahead of the jar on the classpath
(`java -cp patch;opendataloader-pdf-cli.jar org.opendataloader.pdf.cli.CLIMain`)
restores the old memory profile. On five documents (both datasheets above, two
forms, a synthetic table) the Markdown and JSON output of opendataloader-pdf
2.5.13 is byte-for-byte identical with and without it, and so are the tagged
PDFs (page content streams and structure trees) on four of them — so for these
documents the per-chunk `StreamInfo` copies did not reach the output at all.
