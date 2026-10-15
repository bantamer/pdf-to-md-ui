# Patches

Two single classes, each put in front of the opendataloader-pdf jar on the
classpath so it wins over the copy inside; the jar itself is not modified.
Each applies only to the exact class it was made for (a SHA-256 check in
`converter.py`), so a different opendataloader-pdf runs untouched.

- [veraPDF line-art patch](#verapdf-line-art-patch) — memory on plot pages.
- [Hidden-text switch](#hidden-text-switch) — lets "Drop hidden text" work.

# veraPDF line-art patch

`verapdf/org/verapdf/gf/model/factory/chunks/ChunkParser.class` is the
`ChunkParser` from veraPDF wcag-validation 1.31.169, as bundled in
opendataloader-pdf **2.5.8**. `converter.py` puts this folder in front of the
opendataloader-pdf jar on the classpath, so this class wins over the one inside
the jar. The jar itself is not modified.

## Why

opendataloader-pdf parses PDFs with veraPDF. From 2.5.9 on it bundles a veraPDF
whose `ChunkParser` handles vector line art differently, and memory grows
steeply with the number of separate stroke operations on a page — exactly what
the plot pages of a datasheet are made of:

| | TI tps7a02 (48 pages) | TI lm2917-n |
|---|---|---|
| 2.5.13 as shipped | OutOfMemoryError up to 12 GB heap; ok at 14 GB, 9 s | OOM at 1 GB |
| 2.5.13 + this class | ok in 1 GB, 3 s | ok in 1 GB, 3 s |

### Cause

From wcag-validation 1.31.175 on, `ChunkParser.processLineArts` records for
every graphic element which drawing operations of the page stream it came from
(`StreamInfo`, the new `int` parameter on `processS`, `processf`, …). It does so
in a nested loop: every line chunk, and every line-art box, receives a copy of
*every* `StreamInfo` of its marked-content group. On an untagged page — a TI
datasheet, for one — all graphics form a single group, so N strokes cost N²
objects: 3000 strokes are 9 million copies, a plot page with 5000+ lines over
25 million. Memory measured on a generated page fits that exactly: 1000
strokes are fine, 2000 need more than 64 MB, 3000 more than 256 MB.

Ordinary documents never reach those numbers, which is presumably how it went
unnoticed; it arrived in opendataloader-pdf 2.5.9 with a wholesale dependency
update.

### Effect on the output

None found. Converted with enough memory for both, the patched and unpatched
2.5.13 produce byte-for-byte identical Markdown and JSON on five documents
(both datasheets, two forms, the test fixture), and identical tagged PDFs on
four of them — page content streams compared byte for byte over 100 pages,
structure trees element by element. The only difference is memory and time.

The rest of 2.5.13 is kept — notably the fix for table cells written as
`&lt;td&gt;`, which arrived in the same 2.5.9 release as the regression.

## When it applies

Only when the `ChunkParser` inside the jar has the SHA-256 listed in
`converter.PATCH_TARGETS` — the one from 2.5.13. Any other jar runs untouched,
and the log says so ("заплатка veraPDF: не применяется к этой версии").

## Upstream

Reported as
[veraPDF/veraPDF-library#1641](https://github.com/veraPDF/veraPDF-library/issues/1641),
with the generator, measurements and cause, and linked from
[opendataloader-pdf#790](https://github.com/opendataloader-project/opendataloader-pdf/issues/790).
When it is fixed and the fix reaches an opendataloader-pdf release, the patch
can go.

## Upgrading opendataloader-pdf

`requirements.txt` pins the exact version. After raising it, run the tests:

- `test_patch_still_needed` runs the new jar **without** the patch on a page
  of 3000 strokes in 128 MB. If that now passes, upstream has fixed it: delete
  this folder, `PATCH_TARGETS` and the `patches` entry in `app.spec`.
- If it still fails, the problem remains. Check the patch against the new jar
  (convert real datasheets with and without it, compare the output), and add
  the new jar's `ChunkParser` hash to `PATCH_TARGETS` only if the output is
  unchanged.

## Licence (veraPDF)

`ChunkParser.class` is part of veraPDF, © veraPDF Consortium, dual-licensed
under the GNU GPL v3 or later and the Mozilla Public License 2.0 or later. It is
redistributed here unmodified under the **MPL 2.0**. Its source code is
[`ChunkParser.java` at veraPDF-validation tag v1.31.169](https://github.com/veraPDF/veraPDF-validation/blob/v1.31.169/wcag-validation/src/main/java/org/verapdf/gf/model/factory/chunks/ChunkParser.java);
the licence texts are in the
[veraPDF-library repository](https://github.com/veraPDF/veraPDF-library).

# Hidden-text switch

`hidden-text/org/opendataloader/pdf/api/FilterConfig.class` is opendataloader-pdf
2.5.13's `FilterConfig` with one line changed; the source, with the change
marked, is [`hidden-text-src/FilterConfig.java`](hidden-text-src/FilterConfig.java).

## Why

opendataloader-pdf can drop text a reader cannot see: it renders each page and
compares every piece of text with what is behind it, and text with almost no
contrast — invisible, or white on white — goes. That is the classic way of
smuggling instructions to an AI inside a document. But 2.5.13 leaves this
filter off (`filterHiddenText = false`), and its command line can only switch
filters off (`--content-safety-off hidden-text`), never on. The tiny-text,
off-page and hidden-layer filters are on by default and the CLI handles them;
this one cannot be reached at all.

The patched class takes the default from a system property instead:

```java
private boolean filterHiddenText = Boolean.getBoolean("opendataloader.filterHiddenText");
```

`converter.java_command` adds `-Dopendataloader.filterHiddenText=true` and the
patch folder only when **More options → Drop hidden text** is ticked; without
the property the patched class behaves exactly like the original.

Compiled with `javac --release 11` against the 2.5.13 jar. The unmodified
2.5.13 source compiled the same way gives bytecode identical to the class in
the jar (`javap -c` compared), so the patch differs from the shipped class in
that one field initialiser and nothing else.

## What it does to the output

On a generated page (`tests/pdfgen.py: hidden_text_pdf`) with a visible line
and four hidden ones:

| | invisible | white on white | half a point | off the page |
|---|---|---|---|---|
| filters off (the app's default) | kept | kept | kept | kept |
| all CLI filters on | kept | kept | dropped | dropped |
| all CLI filters + this switch | dropped | dropped | dropped | dropped |

The visible line stays in every case. `tests/test_real_converter.py` checks
this on every run.

On real datasheets it costs about twice the time — 1 to 3 s more per file
(tps7a02 3.1 → 5.2 s, stm32u083kc 2.4 → 5.1 s, lm2917-n 1.3 → 3.1 s, MCP1700
1.1 → 2.1 s) — and the contrast test has false positives: from the Microchip
MCP1700 datasheet it dropped the minus and equals signs in two formulas, from
TI tps7a02 a "Width (mm)" label. It also, correctly, dropped invisible "SPACER"
text from TI lm2917-n. Hence off by default, with the trade-off spelled out
under the setting's (?).

## When it applies

Only when the jar's `FilterConfig` has the SHA-256 in
`converter.HIDDEN_PATCH_TARGETS` (the 2.5.13 one). With any other jar "Drop
hidden text" still switches every CLI filter on, and the log says that
invisible and same-colour text stays.

## Upgrading opendataloader-pdf

`test_hidden_text_patch_fits_the_pinned_jar` fails when the new jar's
`FilterConfig` differs. Then: if upstream has added a way to switch the filter
on, use that and delete `hidden-text/` and `hidden-text-src/`; otherwise take
`FilterConfig.java` from the new release tag, make the same one-line change,
compile it as above and replace the hash.

## Licence (opendataloader-pdf)

`FilterConfig` is part of opendataloader-pdf, © 2025–2026 Hancom Inc., under
the Apache License 2.0. The modified source is in `hidden-text-src/`, with a
notice of the change at the top as the licence asks.
