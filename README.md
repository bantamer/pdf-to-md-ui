# PDF → Markdown

Desktop front-end for
[opendataloader-pdf](https://github.com/opendataloader-project/opendataloader-pdf),
aimed at people who never open a terminal: drag PDFs in, tick the options,
press one button.

![screenshot](docs/screenshot-light.png)

## Features

- Drag & drop for PDF files and whole folders
- Output as Markdown, JSON, HTML, plain text or tagged PDF
- OCR for scans, LaTeX formulas, picture descriptions, data sanitising
- Light and dark theme, follows the system setting on start
- Runs the conversion off the UI thread, with a log that unfolds on demand

## Requirements

- Python 3.10+
- Java 11 or newer (`opendataloader-pdf` runs a JVM under the hood)

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

## Layout

| File | Purpose |
|---|---|
| `gui.py` | Window, drag & drop, conversion worker thread |
| `theme.py` | Colour palettes and generated stylesheet |
| `build.bat` | One-click Windows build: venv, JRE, exe, installer |
| `app.spec` | PyInstaller build definition |
| `installer.iss` | Inno Setup installer script |
