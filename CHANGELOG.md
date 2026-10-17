# Changes

## Unreleased

- **MIN / TYP / MAX split more often.** Two numbers close together ("3 7"
  under MIN TYP MAX in LM358) were kept in one cell; a footnote mark written
  apart ("TYP (2)") added an empty column; "GND – 0.3" and "(V+) – 1.5" were
  cut at the minus. All three now land in their columns.
- **Drop hidden text** explains that it also takes thin signs (+, −, =) out
  of formulas and code — not for such documents.

## 2.0.0

A ground-up rework since 1.0.0: results you can hand to a person or a
language model, and a program that behaves like a Windows application.

### Better results

- **Figure clutter removed.** Plots, package drawings and flow charts used to
  come out as huge tables of empty cells — up to three quarters of a
  datasheet. Each is now one line, "[Figure omitted, page N]" with its
  caption; real sentences inside (flow chart steps) are kept. Over 23 test
  datasheets from 13 makers: 17% fewer tokens, up to 78% on single files.
- **Unreadable fonts fixed.** Fonts that number their glyphs instead of
  naming them came out as "?": a whole Infineon datasheet, minus signs in TI
  plot labels, µ in onsemi tables. The program now restores them before
  converting (the original PDF is never changed). Question marks over the
  test set: 8970 → 90.
- **MIN / TYP / MAX put back apart.** TI and ADI tables with no lines between
  those columns came out with all three values in one cell. They are now
  split by where each number sits on the page; cells that cannot be read
  reliably are left whole.
- **Images tidied.** Identical image files are merged, decorations repeated on
  every page are left out, and files nothing links to are deleted.
- **Drop hidden text** (More options): for results that go to an AI —
  invisible, white-on-white, microscopic and off-page text is left out.
- **Page separators** and **plain Markdown tables** can be switched.
- Plot-heavy datasheets convert in seconds instead of running out of memory
  (veraPDF memory fix, reported upstream).
- Every file has a timeout; a file that runs over is retried without images;
  **Cancel** really stops; one broken PDF never stops the batch.

### A proper Windows program

- **File / Settings / Help** menu with the usual shortcuts; About dialog.
- **Six languages**: English, Русский, Polski, Français, Español, Italiano.
- Light and dark theme or as in Windows — title bars included.
- **Open in PDF → Markdown** in the Explorer context menu; one window — files
  sent while it is open join it.
- Icon; the window reopens where it was left; a mark next to each file after a
  run, double-click opens the result.
- A **?** next to every setting explains it; **Reset** puts a section back to
  its defaults.
- Remove single files from the list (Delete, button or right-click).
- Up to five **favourite output folders**.
- Resolution and timeout chosen from the usual values; eye button for the PDF
  password.
- **User guide** built in (F1), works offline.
- Tells you when a new version is out (can be turned off).
- Bundled Java 25; installer for Windows 10/11, no admin rights needed.

Licence: GNU GPL v3.

