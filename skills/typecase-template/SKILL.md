---
name: typecase-template
description: Build export templates for the Typecase writing app as ready-to-import .typecase-template files (PDF, Word/DOCX and HTML look in one file). Use this whenever someone wants a Typecase export template or "Vorlage" — e.g. a manuscript layout for an editor/Lektorat, a business letter, an essay or thesis format, a novel manuscript, a report with a logo, custom fonts or page margins for exports from Typecase — or wants to change, fix or check an existing .typecase-template file, even if they only describe how their exported document should look.
---

# Typecase export templates

Typecase is a Markdown writing app for Linux (GNOME). It exports a sheet to PDF, DOCX and HTML through Pandoc. How the result looks is defined by a **template file** with the extension `.typecase-template`: a ZIP archive containing a description (`template.json`), a Pandoc HTML template, CSS, and optionally a Word reference document. The user imports it in Typecase under **Preferences → Templates → Import…** and picks it in the export dialog.

Your job is to turn the user's description of a document ("double-spaced manuscript with a wide margin for my editor", "my business letter with logo") into such a file, and hand it over ready to import.

The full format specification is in `references/format.md`. Read it before writing the HTML template or CSS the first time — it lists the available variables, what is and is not supported in the PDF, and the pitfalls (the most common: forgetting the `header-includes` loop, which silently drops all CSS).

## Workflow

### 1. Understand the document

Find out what the document is for and what must be true of it. Typical decisions:

- purpose and name (shown in Typecase's dropdown — give it in English and the user's language)
- paper size and margins (PDF and Word)
- fonts and sizes for body text and headings, line spacing, paragraph style (spacing between paragraphs vs. first-line indent), alignment (left or justified)
- title block: show title, subtitle, author, date? where and how?
- chapters on new pages? special elements (logo, letterhead, coloured headings)?

Fill gaps with sensible conventions for the document type rather than interrogating the user; ask only about things that genuinely change the result and that you cannot infer (for example, the user's name for a letterhead). State the choices you made so the user can correct them. Conventions that help:

- *Manuscript for an editor / Lektorat*: 12 pt serif, line spacing 1.5–2, wide right margin (40–50 mm) for notes, left-aligned, no justification, first-line indent, chapters on new pages.
- *Business letter (DIN 5008 in German-speaking countries)*: A4, left margin 25 mm, right 20 mm, 11–12 pt sans or serif, sender line and date at the top right.
- *Essay/thesis*: A4, 25 mm margins (often 30–35 mm left for binding), 12 pt, line spacing 1.5, justified with hyphenation, numbered-looking headings.
- *Novel manuscript (Normseite)*: monospace or serif 12 pt, double spacing, wide margins.

### 2. Write the files

Work in a fresh folder. Start from the bundled starter — it is Typecase's own built-in "Text" template and already handles screen vs. print correctly:

```bash
cp -r <skill-dir>/assets/starter my-template
```

Then edit:

- **template.json** — name and description (per language), `pdf.paper`, `pdf.margins_mm`. PDF margins can only be set here, not in CSS.
- **template.html** — keep `$body$` and the `$for(header-includes)$…$endfor$` loop in `<head>`. Change the title block or add elements (e.g. a letterhead with `$author$` and `$date$`). Keep `<body$if(pdf)$ class="pdf"$endif$>` so the CSS can tell print from screen.
- **style.css** — the look for HTML and PDF. Keep `body.pdf { max-width: none; margin: 0; padding: 0; }`. Scope rules for the text to `main` (`main h1`, `main p`): the title block sits outside `<main>` and its title is an `h1` too, so a plain `h1 { break-before: page }` would start the PDF with an empty page and a plain `p { … }` rule would undo the title block's alignment. Use fonts that exist on a GNOME system or embed font files (see `references/format.md` §4); if you embed fonts, make sure their licence allows it and mention the licence to the user.

### 3. Make the Word part

Create `reference.docx` from Pandoc's default with the bundled script, mirroring the CSS decisions so Word and PDF match:

```bash
python3 <skill-dir>/scripts/style_docx.py <skill-dir>/assets/reference.docx my-template/reference.docx \
    --body-font "Liberation Serif" --body-size 12 --heading-font "Liberation Sans" \
    --line-spacing 2 --paragraph-spacing 0 --first-line-indent 1.25 \
    --chapter-page-break --paper a4 --margins 25,50,25,25
```

Run it with `--help` for all options — it also adds page numbers (`--page-numbers center`) and a small letterhead in the Word header (`--header-lines "Name|Street|City" --header-first-page-only`), so there is no need to hand-edit the DOCX XML. If the user only cares about PDF/HTML you may skip this step; Word exports then use Pandoc's defaults.

### 4. Check and pack

```bash
python3 <skill-dir>/scripts/build_template.py my-template "Manuskript Lektorat.typecase-template"
```

The script runs the same checks Typecase runs on import, plus warnings for things that would silently look wrong. Fix every error and take warnings seriously (they usually mean CSS or fonts will not apply). The file name becomes the template's id, so name the file after the template.

If Pandoc happens to be available, you can preview the HTML output to sanity-check the CSS:

```bash
printf -- '---\ntitle: Probe\nauthor: Anna\n---\n# Kapitel\n\nErster Absatz.\nZweite Zeile.\n\n> Ein Zitat\n' | \
  pandoc -f markdown+hard_line_breaks -t html5 --standalone --template my-template/template.html \
  --include-in-header <(printf '<style>%s</style>' "$(cat my-template/style.css)") -o preview.html
```

(Typecase itself embeds the CSS the same way.) Without Pandoc, skip the preview — the build script's checks are enough. If you print the preview to PDF with a browser, remember Typecase prints with WebKit, which differs in details (see `references/format.md` §4); suggest the user does one test export in Typecase.

### 5. Hand it over

Give the user the `.typecase-template` file and a short note, in their language:

- what the template does (the choices you made: paper, margins, fonts, spacing)
- how to use it: Typecase → Preferences → Templates → **Import…**, then choose it in the export dialog (Ctrl+E)
- anything that does not carry over (e.g. "PDF has no page numbers — Typecase's PDF export cannot do running footers yet")
- only describe Typecase features that exist: sheets have a title, subtitle, author, keywords, status and language in the properties pane; there is no date field there (`$date$` is the export date)

## Changing an existing template

Unzip the `.typecase-template` file into a folder (it is a plain ZIP), edit, and pack again with `build_template.py` under the **same file name** — Typecase then offers to replace the installed version. Users can export any installed template (including the built-in one) via Preferences → Templates → "Save as File…", which is a good starting point for a variation.

## Bundled files

- `references/format.md` — the format specification: template.json fields, template variables, CSS notes, Markdown-to-HTML mapping, reference.docx styles, limits.
- `assets/starter/` — Typecase's built-in "Text" template (template.json, template.html, style.css) to start from.
- `assets/reference.docx` — Pandoc's default Word reference document (GPL-2.0-or-later, from Pandoc).
- `scripts/style_docx.py` — adjust fonts, sizes, spacing, indent, paper and margins in a reference.docx (standard library only).
- `scripts/build_template.py` — validate a template folder and pack it into a `.typecase-template` file (standard library only).
