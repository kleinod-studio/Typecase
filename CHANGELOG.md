# Changelog

All notable changes to Typecase are listed here. Versions follow [semantic versioning](https://semver.org).

## 0.9.0 – 2026-10-25

First public release. Typecase is usable day to day; 1.0 will follow together with the release on Flathub (see the [roadmap](ROADMAP.md)).

### Library
- Any folder becomes your library; subfolders are groups, `.md` files are sheets
- Create, rename, move (also by drag and drop) and delete sheets and groups; deleted items go to the system trash
- Full-text search across the library
- Keywords on sheets and filtering by keyword
- Progress rings next to sheets with a writing goal

### Writing
- Live Markdown styling with dimmed syntax characters and highlighted code blocks
- Floating formatting bar and keyboard shortcuts for bold, italic, underline, headings, lists, quotes, links and code
- Lists continue on Enter; Tab and Shift+Tab indent and outdent list items
- Find and replace in the current sheet
- Word and character count; writing goals per sheet with a progress ring in the properties pane and a floating badge
- Optional underline caret

### Focus mode
- Full screen with only your text, with its own font settings
- Typewriter scrolling keeps the current line centered; surrounding paragraphs are dimmed

### Organize
- Sheet properties (title, subtitle, author, status, language, keywords) stored as YAML front matter, which stays hidden in the editor

### Export
- Export to PDF, Word (DOCX) and HTML through Pandoc (bundled in the Flatpak)
- Export templates as single `.typecase-template` files, imported in the preferences; a built-in "Text" template
- A [Claude skill](skills/typecase-template/) that builds templates from a description, and a [guide](docs/templates.md) for building them by hand

### Safety and privacy
- Autosave with atomic writes; changes made by other programs never overwrite unsaved input, and conflicts keep both versions
- No telemetry, no accounts, no network access

### Desktop
- GNOME-native interface with libadwaita, light and dark style, fully usable with the keyboard
- English and German user interface
