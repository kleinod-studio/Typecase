# Changelog

All notable changes to Typecase are listed here. Versions follow [semantic versioning](https://semver.org).

## Unreleased

- Links open in the browser with Ctrl+click, or from the context menu while the caret is in a link. Hovering over a link shows its address. Bare web addresses and addresses in angle brackets are styled as links too, and underscores in them no longer turn into italics.
- Footnotes: Ctrl+Alt+F or the new button in the formatting bar inserts a note right in the text (`^[note]`). Notes are set smaller and dimmed in the editor, PDF and Word exports put them at the bottom of their page; web pages collect them at the end. Classic `[^1]` footnotes are styled too.
- Outline: a new button in the header bar (or Ctrl+Shift+O) lists the headings of the sheet, indented by level, with the current one selected. Choosing one jumps there. In a group, it starts with the group's name and shows each subgroup, such as the parts of a novel, with the headings of its sheets below.
- PDFs are now laid out by WeasyPrint instead of being printed by WebKit. They look as before, with text at exactly the size the template sets (WebKit printed it slightly larger), and real pages open the way to footnotes on their page and, later, page numbers and a table of contents.
- The keyword filter uses the icon theme's own tag icon where there is one, and an outline icon of its own otherwise, so it matches the other icons.

## 1.1.2 – 2026-11-01

- The keyword filter button shows its icon on every system. It used an icon that the default Adwaita theme lacks, so the button was empty unless another icon theme filled the gap. Thanks to Akash Mondal for reporting it ([#1](https://github.com/kleinod-studio/Typecase/issues/1)).

## 1.1.1 – 2026-10-31

- Wrapped lines of a list item line up with its text, instead of starting under the bullet or number. This works for nested items, numbers of any length and task boxes too.
- A window that is closed stops watching files at once.

## 1.1.0 – 2026-10-30

A first feature update.

- Card view for plotting: a switch in the header bar (or Ctrl+Alt+C) shows the sheets of a group as cards with title, status, keywords, notes and word count. Notes are edited right on the card, and dragging a card or pressing Alt+arrow keys changes the order of the sheets. Each group remembers whether it shows text or cards.
- A new sheet takes its first heading as its name as soon as you leave the heading line, but only while it is still called “Untitled”; renaming by hand works as before.

## 1.0.0 – 2026-10-27

The first stable version. Typecase is complete for everyday writing; the submission to Flathub follows.

- Fuller description for software centers, with the supported input devices and the smallest usable window size
- New screenshots of the editor, writing goals, focus mode and preferences, in light and dark style
- A manifest for Flathub that builds Typecase from a release tag

## 0.10.0 – 2026-10-25

### Library
- Your own order for sheets and groups: drag between rows, or Alt+Up and Alt+Down
- Duplicate sheets (with their attachments) and whole groups
- Group view: selecting a group shows all of its sheets one after another, directly editable; each sheet is still saved to its own file, subgroups are marked with their names, and the arrow keys move across sheets

### Writing
- Spell checking while you type, offline, in each sheet's language, with suggestions in the right-click menu; a button in the formatting bar and F7 switch it on and off, and focus mode has its own setting
- Notes per sheet, stored in the front matter, and attachments: copies of files that move along with the sheet
- Editor themes: Standard, Paper, Solarized, Calm and High Contrast, each with a light and a dark variant; focus mode can have its own theme, and the window takes on the theme's colors
- Import GtkSourceView style schemes as themes, or save a built-in one as a starting point ([guide](docs/themes.md))

### Export
- Export a whole group (subgroups included) as one document, with a title, optionally with every subgroup on a new page
- The export dialog says right away when PDF export is not possible (WebKitGTK missing outside the Flatpak)

### Fixes and details
- Dragging an entry in the library no longer leaves the pointer stuck on Wayland
- Screen readers: progress rings, group view sections and subgroup titles are announced properly
- The preferences gather editor, focus mode and themes on one "Writing" page

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
