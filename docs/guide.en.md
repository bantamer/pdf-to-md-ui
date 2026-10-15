# User guide: PDF → Markdown

The program turns PDFs — datasheets and technical documents especially — into
Markdown, JSON, HTML or plain text. Everything it needs, Java included, comes
with it.

## Quick start

1. Add PDFs or a whole folder.
2. Tick the output formats you want.
3. Press **Convert**.

By default the results go to an `output` folder next to the source files.

## Adding files

- Drag PDFs or a folder into the window.
- Or press **Add files** / **Add folder** (Ctrl+O / Ctrl+Shift+O).
- Or drop PDFs onto the program's icon.
- Or right-click PDFs or a folder in Explorer and pick
  **Open in PDF → Markdown**. On Windows 11 it is under
  **Show more options**.

If the program is already open, new files join the same window.

**Removing a file you don't need:** select it in the list and press
**Remove** or the **Delete** key; Ctrl and Shift select several. The
right-click menu has the same. **Clear** empties the whole list. Nothing is
deleted from the disk.

## Output formats

| Format | What you get |
|---|---|
| Markdown | Text with headings and tables. Tables are written as HTML, so merged cells stay intact. |
| JSON | The document's structure for other programs: blocks, positions, types. |
| HTML | A page for the browser. |
| Text | Just the text, no markup. |
| Tagged PDF | The source PDF with structure tags — for screen readers and other programs. |
| Annotated PDF | The source PDF with everything recognised drawn over it. Shows why a table came out wrong. |

You can tick several formats at once.

## Options

- **Images** — save as separate files, embed in the document, or don't save.
  Images are the slowest part of the work.
- **Resolution** — how sharp the images are. 96 DPI is usually enough for
  plots.
- **Pages** — e.g. `1-12` or `1,3,5-7`. Empty means all pages.
- **Timeout per file** — a file that runs over is tried once more without
  images.
- **Page separators** — a `---- page 3 ----` line between the pages; untick
  it for one continuous text.
- **Plain Markdown tables** — tables in Markdown's own markup instead of
  HTML, for editors and sites that don't show HTML. Merged cells fall apart
  that way, which is why it is off by default.

Next to every setting there is a **?** — point at it for a detailed
explanation. **Reset** puts the defaults back: one button for the formats
and options, another inside **More options**.

## More options

Press **More options** for the settings you rarely need: reading order, table
detection, image format, PDF password, AI mode and others. Usually there is
no need to touch them — each is explained under its **?**.

The password for encrypted PDFs is never saved. The eye button in the
password field shows what you typed.

## Where to save

- Empty field — results go to an `output` folder next to the source files.
- **Browse…** — pick another folder. It is remembered for next time.
- The cross in the field — back to "next to the source files".

**Favourite folders** — up to 5 folders to switch between with one click.
Open them with the button under the field, pick a folder with **Browse…** and
press **Add current folder**. The cross on the right removes a folder from
the favourites (the folder itself stays on the disk).

## After converting

- Every file in the list gets a mark: a green tick — done; an amber "!" —
  converted without images (ran out of time); a red cross — it didn't work.
- Double-click a file to open the result.
- **Open results folder** opens the folder in Explorer.
- If something went wrong, a **Details** link appears next to the status line;
  it opens the log. The log is always at **Settings → Show log** (Ctrl+L).

## Tips for datasheets

- Take only the pages you need — the description and the parameter tables,
  say `1-12` — and skip dozens of pages of plots.
- Too slow? Set **Resolution** to 96 DPI or **Images → Don't save**.
- A table came out broken? Tick **Annotated PDF** to see what the converter
  found, and try **More options → Tables: by clusters**.

## Settings

- **Settings → Language** — the program's language.
- **Settings → Theme** — light, dark, or as in Windows.
- **Settings → Check for updates at startup** — at startup the program asks
  GitHub whether there is a newer version and shows a link in the corner of
  the window. To check by hand: **Help → Check for updates**.
- **Settings → Reset settings** — everything back as after installing.

## Keyboard shortcuts

| Keys | Action |
|---|---|
| Ctrl+O | Add files |
| Ctrl+Shift+O | Add folder |
| Delete | Remove the selected files from the list |
| Ctrl+Enter | Convert |
| Esc | Stop |
| Ctrl+L | Show or hide the log |
| F1 | This guide |
| Ctrl+Q | Exit |

## If something doesn't work

- **Windows says it protected your PC** when installing: click
  **More info → Run anyway**. The installer is not code-signed; that is
  expected.
- **A file was not converted** — press **Details** or open the log. A broken
  or password-protected PDF never stops the other files.
- **Found a bug** — **Help → Report a problem**.
