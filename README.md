# PDF → Markdown

Desktop front-end for
[opendataloader-pdf](https://github.com/opendataloader-project/opendataloader-pdf),
aimed at people who never open a terminal: drag PDFs in, tick the options,
press one button.

![screenshot](docs/screenshot-light.png)

## Features

- Drag & drop for PDF files and whole folders — into the window, or onto the
  exe itself (also works through "Open with")
- Output as Markdown, JSON, HTML, plain text or tagged PDF, plus an annotated
  PDF that paints every detected element over the original page — the way to
  see why a table came out wrong
- Image extraction as external files, embedded Base64 or off, with an
  adjustable render resolution (144 DPI by default; 96 keeps the images at a
  fraction of the memory)
- Page ranges (`1,3,5-7`), reading order, table method, space threshold,
  threads, PDF password
- Per-file timeout with a working Cancel, and an automatic retry without
  images for files that run over it
- One file per run, so a PDF the converter chokes on no longer kills the batch
- Folders keep their structure in the results; two files with the same name
  never overwrite each other, and the previous run's output is not picked up as
  new input
- Every option is remembered between launches, except the page range and the
  PDF password
- Light and dark theme, follows the system setting until you pick one
- Runs the conversion off the UI thread, with a log that unfolds on demand

Markdown defaults are tuned for technical documents: HTML tables (merged cells
survive), page separators, invalid characters replaced with `?` instead of being
dropped, and the hidden/tiny/off-page text filters off.

### Where results go

| Selected | Result |
|---|---|
| `a.pdf` | `<dest>/a.md` |
| folder `src` with `TI/x.pdf` | `<dest>/TI/x.md` |
| folders `TI` and `ADI` | `<dest>/TI/…`, `<dest>/ADI/…` |
| `a/doc.pdf` and `b/doc.pdf` | `<dest>/doc.md` and `<dest>/doc (2)/doc.md` |

The converter names every output after its input (`doc.md`, `doc_images/`,
`doc_annotated.pdf`), so name clashes are resolved with folders: renaming the
files would break the links from the `.md` to its images.

### opendataloader-pdf version and the veraPDF patch

Pinned to **2.5.13** in `requirements.txt`. It fixed the table cells that
2.5.1–2.5.5 wrote as `&lt;td&gt;` and dropped the `hancom-ai` hybrid backend.

The same 2.5.9 release that fixed the tables brought in a veraPDF version whose
line-art parsing needs memory out of all proportion: a 48-page TI datasheet
went from 512 MB to about 14 GB. [patches/](patches/README.md) holds the one
class that fixes it, loaded ahead of the jar; output is byte-for-byte the same,
and the datasheet converts in 3 s within 1 GB again. The patch only applies to
the exact jar it was measured against, and `tests/test_memory.py` says when it
is no longer needed.

The version in use, and whether the patch is active, are printed at the top of
the log.

## Requirements

- Python 3.10+
- Java 11 or newer (`opendataloader-pdf` runs a JVM under the hood)

The optional AI mode needs a hybrid backend running separately:

```
pip install "opendataloader-pdf[hybrid]"
opendataloader-pdf-hybrid --port 5002
```

The app probes the server before starting and offers to convert without it when
nothing answers.

## Run from source

```
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python gui.py
```

## Build a Windows executable

On Windows, double-click [build.bat](build.bat): it sets up a virtualenv,
bundles a trimmed JRE with `jlink`, runs PyInstaller and — if Inno Setup is
installed — produces `Output\PDF-to-Markdown-Setup.exe`. The app itself ends up
in `dist\PDF to Markdown\`; copy the whole folder, not just the exe.

PyInstaller does not cross-compile, so a Windows build needs Windows. See
[BUILD.md](BUILD.md) for the manual steps and the prerequisites.

Installers for sharing come from GitHub Actions rather than a local build:
pushing a `v*` tag runs the tests, builds the app with a Temurin 21 runtime and
attaches `PDF-to-Markdown-Setup.exe` to the release. A local `build.bat` bundles
whatever JDK is installed, and Oracle's licence only allows redistributing an
unmodified JDK — a jlink-trimmed one is not. Tests also run on every pull
request.

## Layout

| File | Purpose |
|---|---|
| `gui.py` | Window, drag & drop, remembered settings |
| `converter.py` | Running the JAR: options, where each file goes, the worker thread |
| `theme.py` | Colour palettes and generated stylesheet |
| `patches/` | veraPDF line-art fix loaded ahead of the jar |
| `tests/` | pytest suite, the `table.pdf` fixture, a generator for plot-heavy pages |
| `build.bat` | One-click Windows build: venv, JRE, exe, installer |
| `app.spec` | PyInstaller build definition |
| `installer.iss` | Inno Setup installer script |
