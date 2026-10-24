# Custom export templates for Typecase

Typecase exports sheets as PDF, Word document (DOCX), and web page (HTML). The **template** determines what the result looks like. A template is a single file with the extension `.typecase-template`. You can share it with others and load it in Typecase under **Preferences → Templates → Import…**. When exporting (Ctrl+E), you then pick it under “Template” in the export dialog, next to “Format”.

This guide describes how a template is structured and how to build your own. The easiest way is the **Claude skill “typecase-template”**: you describe to Claude what your document should look like and get a finished template file. The skill can be downloaded from https://kleinod.studio/typecase. If you prefer to do it by hand, you will find everything you need here.

## Quick start: begin with an existing template

1. In Typecase, open **Preferences → Templates**.
2. Next to “Text”, click **Save as File…**. You get `Text.typecase-template`.
3. Rename the file to `Letter.typecase-template` (the file name becomes the template’s identifier).
4. Open it with an archive manager (the file is a ZIP archive; if necessary, temporarily change the extension to `.zip`), edit the files inside, and pack them up again.
5. Import it into Typecase and try it out.

## What a template contains

| File | Required | Purpose |
| --- | --- | --- |
| `template.json` | yes | Name, description, paper size, and margins for PDF |
| `template.html` | yes | Skeleton for HTML and PDF (a Pandoc template) |
| `style.css` | no | Styling for HTML and PDF |
| `reference.docx` | no | Styles for Word; without it, Pandoc uses its default reference document |
| other files | no | Fonts, logos, etc. referenced by `style.css` |

All files sit at the top level of the archive (or together in exactly one folder inside it).

### template.json

```json
{
  "format": 1,
  "name": {"en": "Letter", "de": "Brief"},
  "description": {"en": "DIN 5008 business letter", "de": "Geschäftsbrief nach DIN 5008"},
  "author": "Your Name",
  "version": "1.0",
  "pdf": {
    "paper": "a4",
    "margins_mm": {"top": 45, "right": 20, "bottom": 25, "left": 25}
  }
}
```

- **format**: always `1`. Typecase rejects templates that require a newer version of the format.
- **name** (required) and **description**: either plain text or one entry per language (`"de"`, `"en"`, …). Typecase shows the UI language if available, otherwise English.
- **author**, **version**: informational only.
- **pdf.paper**: `a4`, `a5`, `a3`, `letter`, or `legal`. If omitted, Typecase uses the usual paper size for the system locale.
- **pdf.margins_mm**: page margins of the PDF in millimeters (0 to 100). Any side not specified gets 25 mm.

Paper size and margins for **Word** are not set here but in `reference.docx` (page setup).

### template.html

The skeleton is a [Pandoc template](https://pandoc.org/MANUAL.html#templates): plain HTML with placeholders enclosed in dollar signs. Typecase fills them in during export.

These are essential:

- `$body$`: the text of the sheet. Typecase rejects a template without it.
- `$for(header-includes)$$header-includes$$endfor$` in the `<head>`: this is where Typecase embeds `style.css`. If this line is missing, your CSS is not applied.

Other placeholders:

| Placeholder | Content |
| --- | --- |
| `$title$`, `$subtitle$` | Title and subtitle from the sheet’s properties |
| `$for(author)$$author$$endfor$` | Author; if the sheet has none, the default from Preferences |
| `$date$` | Date from the `date` field in the front matter, otherwise the export date |
| `$lang$` | Language, e.g. `de-DE` (for `<html lang="…">`, important for hyphenation) |
| `$pagetitle$` | Window title if the sheet has no title (the sheet name) |
| `$created$`, `$status$`, `$keywords$`, … | any other field from the sheet’s front matter |
| `$if(pdf)$…$endif$` | PDF export only; the bundled template uses it to set `<body class="pdf">` |
| `$highlighting-css$` | Colors for code blocks |

Conditionals: `$if(subtitle)$<p class="subtitle">$subtitle$</p>$endif$`.

A complete, minimal skeleton:

```html
<!DOCTYPE html>
<html lang="$lang$">
<head>
<meta charset="utf-8">
<title>$if(title-meta)$$title-meta$$else$$pagetitle$$endif$</title>
$if(highlighting-css)$<style>$highlighting-css$</style>$endif$
$for(header-includes)$
$header-includes$
$endfor$
</head>
<body$if(pdf)$ class="pdf"$endif$>
$if(title)$
<header class="title-block">
<h1 class="title">$title$</h1>
$if(subtitle)$<p class="subtitle">$subtitle$</p>$endif$
</header>
$endif$
$body$
</body>
</html>
```

### style.css

Applies to both HTML and PDF. Some tips:

- **Distinguish print from screen**: in the PDF, `<body>` has the class `pdf` (if the skeleton sets it). The web page may have a limited line length and outer margins; in the PDF, the paper size and margins from `template.json` determine the width, so use `max-width: none; margin: 0;` there.
- **Scope text rules to `main`**: the skeleton places the title block outside `<main>` and the sheet’s text inside it, and the title is also an `h1` heading. So write `main h1`, `main p`, and so on. Otherwise the PDF starts with a blank page (the page break before the title), or paragraph rules override the alignment of the title block.
- **Page breaks**: `main h1 { break-before: page; }` to start chapters on a new page, `.title-block { break-after: page; }` for a separate title page, `break-after: avoid` for headings, `orphans`/`widows` to prevent single stranded lines.
- **Page numbers and headers** are currently not available in PDF (Typecase prints with WebKit, which does not fill these page margin areas). In Word documents, you can add them via `reference.docx`.
- **Fonts**: rely only on widely available fonts (e.g. “Liberation Serif”, “DejaVu Serif”, “Noto Sans”) or embed your own: put the font file in the archive and include it with `@font-face { font-family: "MyFont"; src: url("fonts/MyFont-Regular.woff2"); }`. Typecase embeds files referenced by `url(…)` in HTML and PDF. Mind the font’s license.
- **Images** (such as a logo) work the same way: `background-image: url("logo.svg")`.
- References to files outside the template and internet addresses are left unchanged; Typecase does not download anything from the network.

Here is what Typecase turns Markdown into, so you can style it:

| Markdown | HTML |
| --- | --- |
| `# Heading` through `######` | `h1` … `h6` |
| `**bold**`, `*italic*`, `~~strikethrough~~` | `strong`, `em`, `del` |
| `<u>underlined</u>` | `u` |
| `> Quote` | `blockquote` |
| Lists | `ul`, `ol`, `li` |
| `` `code` ``, code blocks | `code`, `pre` |
| Title block (from the properties) | `.title-block`, `.title`, `.subtitle`, `.author` (if the skeleton names them that way) |

Every line in the editor stays a separate line in the export (`<br>`); paragraphs are separated by a blank line.

### reference.docx

For Word, Pandoc uses the styles of a reference document: font and size of “Normal”, “Heading 1”, and so on, page size, and margins. Pandoc does not take over the content of the reference document, only its look.

To create one:

1. Get Pandoc’s default: `pandoc -o reference.docx --print-default-data-file reference.docx`
2. Open it in LibreOffice or Word and change the **styles** (do not format the text directly): “Normal”/“Body Text”, “Heading 1–3”, “Title”, “Subtitle”, “Block Text” (quotes), “Source Code”. Set page margins under Format → Page Style.
3. Save it as DOCX and put it in the archive.

Without a word processor, you can use the `style_docx.py` script from the Claude skill: it sets fonts, sizes, line spacing, indentation, paper size, and margins, and can optionally add page numbers and a small letterhead (`python3 style_docx.py --help`).

In Word documents, Pandoc always writes the title, subtitle, and author as the first paragraphs before the text; freely positioned areas from the HTML (such as an address field) cannot be reproduced in Word.

## Checking and sharing

On import, Typecase checks the file and reports clearly what is missing. It also rejects archives that try to create files outside their folder, contain links, or are larger than 50 MB. An installed template with the same file name is replaced after confirmation.

You can share the `.typecase-template` file as is. Imported templates are available on the computer where you imported them.
