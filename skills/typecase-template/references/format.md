# Typecase template format (format 1)

Reference for building `.typecase-template` files. Read the section you need.

Contents: 1. File layout · 2. template.json · 3. template.html · 4. style.css · 5. How Markdown is converted · 6. reference.docx · 7. Limits and pitfalls

## 1. File layout

A `.typecase-template` file is a ZIP archive. Files sit at the top level (or all inside exactly one folder):

| File | Required | Used for |
| --- | --- | --- |
| `template.json` | yes | name, description, PDF paper and margins |
| `template.html` | yes | Pandoc HTML template for HTML and PDF export |
| `style.css` | no | look of HTML and PDF |
| `reference.docx` | no | Word styles and page layout (otherwise Pandoc's defaults) |
| other files | no | fonts, images referenced from `style.css` via `url(...)` |

The file name (without extension) becomes the template id: lower-cased, non-alphanumerics → `-`. "Business Letter.typecase-template" → `business-letter`. Importing a file with an existing id replaces that template after the user confirms. The built-in id `text` is reserved (an import named "text" becomes `text-custom`).

## 2. template.json

```json
{
  "format": 1,
  "name": {"en": "Manuscript for Editing", "de": "Manuskript fürs Lektorat"},
  "description": {"en": "Double spacing and a wide right margin for notes", "de": "Doppelter Zeilenabstand und breiter Rand für Anmerkungen"},
  "author": "",
  "version": "1.0",
  "pdf": {"paper": "a4", "margins_mm": {"top": 25, "right": 50, "bottom": 25, "left": 25}}
}
```

- `format`: always `1`.
- `name` (required), `description`: a string, or an object per language code (`en`, `de`, ...). Typecase shows the UI language, falls back to `en`, then to the first entry. Provide at least `en` plus the user's language.
- `pdf.paper`: `a4`, `a5`, `a3`, `letter`, `legal`. Omit for the system's usual paper.
- `pdf.margins_mm`: PDF page margins in millimetres, 0–100 each; missing sides get 25. These are the *only* way to set PDF margins — CSS `@page` margins are not used by Typecase's PDF printer.
- Word page size/margins are not here; they live in `reference.docx`.

## 3. template.html

A [Pandoc template](https://pandoc.org/MANUAL.html#templates) rendered to HTML5. Typecase uses it for HTML export and as the intermediate for PDF (WebKit prints the HTML).

Must contain:
- `$body$` — the sheet's text. Typecase rejects templates without it.
- `$for(header-includes)$$header-includes$$endfor$` inside `<head>` — Typecase injects `style.css` (as a `<style>` block, with `url()` assets embedded as data URIs) through this. Without it, the CSS is ignored.

Variables:

| Variable | Value |
| --- | --- |
| `$title$`, `$subtitle$` | from the sheet's properties (YAML front matter) |
| `$for(author)$$author$$sep$, $endfor$` | author; falls back to the default author from Typecase's preferences |
| `$date$` | the export date in the user's locale format, unless the sheet's front matter has a `date:` field. Typecase's properties pane has **no** date field — a fixed date can only be set by editing the `.md` file's front matter outside Typecase, so don't tell users to "set the date in the properties". |
| `$lang$` | e.g. `de-DE` (use in `<html lang="$lang$">`; enables correct hyphenation) |
| `$pagetitle$` | sheet name; only set when there is no title |
| `$title-meta$`, `$author-meta$` | plain-text versions for `<title>` and `<meta>` |
| any front-matter key | e.g. `$created$` (ISO date-time), `$status$` (draft/revision/final), `$keywords$` (list) |
| `$pdf$` | true only when exporting PDF — use `<body$if(pdf)$ class="pdf"$endif$>` |
| `$highlighting-css$` | syntax colours for code blocks |

Syntax: `$if(x)$...$else$...$endif$`, `$for(list)$$it$$sep$, $endfor$` (inside a for loop the variable itself is also available by name, e.g. `$for(author)$$author$$endfor$`). A literal dollar sign is `$$`.

Starting point: `assets/starter/template.html` (the built-in "Text" template).

## 4. style.css

Applies to HTML and PDF. PDF is produced by WebKitGTK printing the HTML (no JavaScript, no network).

- **Screen vs. PDF**: give the web page a readable column (`max-width: 38em; margin: 3em auto;`) and reset it for print: `body.pdf { max-width: none; margin: 0; padding: 0; }`. Paper width and margins come from `template.json`.
- **Units**: use `pt` for type sizes (12pt body is typical), `em` for spacing.
- **Scope text rules to `main`.** The starter prints the title block (`header.title-block` with `h1.title`, `p.subtitle`, `p.author`) *outside* `<main>`, and the sheet's text inside `<main>`. Generic selectors hit both: `h1 { break-before: page }` also breaks before the title (→ an **empty first page** in Typecase's PDF), and `p { text-align: left; text-indent: … }` overrides the centring/indent of `.subtitle`/`.author`. Write `main h1`, `main p`, `main p + p`, … for the text, and style the title block separately.
- **Page breaks**: `main h1 { break-before: page; }` (chapters on new pages — never on a selector that can match the first element of the page), `h2, h3 { break-after: avoid; }`, `p { orphans: 3; widows: 3; }`, `pre, blockquote { break-inside: avoid; }`. To put the title block on its own page, use `.title-block { break-after: page; }` instead.
- **Fonts**: the PDF uses fonts installed on the user's machine. Typecase runs as a Flatpak on the GNOME runtime; reliably present are "Liberation Serif/Sans/Mono" (metric-compatible with Times New Roman/Arial/Courier), "DejaVu Serif/Sans/Mono", "Carlito" (≈ Calibri), "Caladea" (≈ Cambria), "Cantarell", "Noto Sans". Always end a stack with a generic family (`serif`, `sans-serif`, `monospace`). For a specific typeface, embed it: put the font file in the template (e.g. `fonts/Name-Regular.woff2`, also `.ttf`/`.otf`) and declare `@font-face { font-family: "Name"; src: url("fonts/Name-Regular.woff2"); }` — one rule per weight/style. Only embed fonts whose licence allows redistribution (SIL OFL fonts are fine).
- **Images** (logos, letterhead): include the file and reference it with `url("logo.svg")`.
- **Not supported**: running headers/footers and page numbers in the PDF (CSS `@page` margin boxes are not implemented by WebKit), remote URLs, JavaScript. (Word can have both — see §6.)
- **WebKit, not Chromium**: Typecase prints with WebKitGTK. A preview printed with Chromium or a browser can differ (Chromium silently drops a page break before the first element; WebKit prints an empty page). Treat such previews as approximate.
- Use `hyphens: auto;` with `<html lang="$lang$">` for justified text.

## 5. How Markdown is converted

Typecase reads Markdown as `markdown+hard_line_breaks`: every line break the user typed stays a line break (`<br>`), a blank line starts a new paragraph.

| Markdown in Typecase | HTML element |
| --- | --- |
| `#` … `######` | `h1` … `h6` (with `id` attributes) |
| `**bold**`, `*italic*`, `~~strike~~` | `strong`, `em`, `del` |
| `<u>underline</u>` | `u` |
| `> quote` | `blockquote` |
| `- item`, `1. item` | `ul`/`ol` with `li` |
| `` `code` ``, fenced code blocks | `code`; `pre > code.sourceCode` with spans for highlighting |
| `[text](url)` | `a` |
| `---` on its own line | `hr` |
| tables (pipe tables) | `table`, `th`, `td` |

The title block (title, subtitle, author) is whatever the template prints from `$title$` etc.; the starter uses `header.title-block` with `.title`, `.subtitle`, `.author`.

## 6. reference.docx

Pandoc takes only styles and page layout from it — never its text. Relevant paragraph styles (style ids): `Normal`, `BodyText` (all ordinary paragraphs), `FirstParagraph` (first paragraph after a heading), `Compact` (list items), `Title`, `Subtitle`, `Author`, `Date`, `Heading1`–`Heading9`, `BlockText` (quotes), `SourceCode`; character styles `VerbatimChar` (inline code), `Hyperlink`. Page size and margins come from the document's section properties.

Build it with `scripts/style_docx.py` from `assets/reference.docx` (Pandoc's default). Options: `--body-font`, `--body-size`, `--heading-font`, `--heading-color`, `--heading-sizes`, `--line-spacing`, `--paragraph-spacing`, `--first-line-indent`, `--align`, `--title-align`, `--chapter-page-break`, `--paper`, `--margins top,right,bottom,left` (mm), `--page-numbers center|right` (footer with the page number), `--header-lines "Line 1|Line 2"` (small right-aligned header, e.g. a letterhead) with `--header-first-page-only`. Keep these consistent with `style.css` and `template.json` so Word and PDF look alike. With `--header-first-page-only`, page numbers start on page 2 (usual for letters).

Pandoc writes the sheet's title, subtitle and author as the first paragraphs of the Word document (styles `Title`, `Subtitle`, `Author`, `Date`), always in that order before the text; positioned layouts from the HTML (address windows, side-by-side blocks) cannot be reproduced in Word. Say so when it matters (e.g. letters).

Fonts in Word are referenced by name only (not embedded); the recipient's Word substitutes missing fonts. Prefer common fonts for DOCX ("Liberation Serif" maps to Times New Roman metrics; "Carlito" ↔ Calibri).

## 7. Limits and pitfalls

- At most 200 files and 50 MB unpacked; no symbolic links; no paths leaving the folder. Typecase rejects violations.
- `url()` references in `style.css` that point outside the template or to the internet stay unresolved (and will be missing).
- A missing `header-includes` loop is the most common reason a template "ignores" its CSS.
- PDF margins: `template.json` only. Word margins: `reference.docx` only. HTML: CSS only.
- Line breaks are hard breaks — style `p` spacing knowing that a "paragraph" in Typecase is separated by a blank line.
