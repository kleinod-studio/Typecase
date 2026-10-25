# Custom editor themes for Typecase

An editor theme decides the colors of the writing area: page background, text, the faint Markdown marks, links, headings, and code. Every theme except “Standard” also tints the rest of the window to match, so the sidebar, header bars, and menus become shades of the same colors.

You choose a theme under **Preferences → Writing**, in the tiles below “Style”. Each theme has a light and a dark variant, and Typecase picks the one that fits the current style (follow system, light, or dark). Focus mode can have a theme of its own once “Use Editor Settings” is switched off.

A theme is not a Typecase invention: it is a **GtkSourceView style scheme**, an XML file in the format that GNOME Text Editor and GNOME Builder use. You can import schemes made for those programs, or build your own.

## Quick start: begin with a built-in theme

1. In Typecase, open **Preferences → Writing** and scroll to **Editor Themes**.
2. Next to a built-in theme, for example “Paper”, click **Save as File…** and choose a folder. You get two files: `Paper (custom).xml` and `Paper (custom) (dark).xml`.
3. Open them in a text editor and change the colors. Every line has a comment that says what it colors.
4. Back in **Editor Themes**, click **Import…** and select both files at once.
5. The theme appears as a new tile. Click it to use it.

The saved files already have their own ID, so they import next to the original instead of replacing it. Change the `name` attribute if you want a different name on the tile.

## What a theme file contains

```xml
<?xml version="1.0" encoding="UTF-8"?>
<style-scheme id="my-paper" name="My Paper" version="1.0" parent-scheme="Adwaita">
  <metadata>
    <property name="variant">light</property>
    <property name="dark-variant">my-paper-dark</property>
  </metadata>
  <style name="text" foreground="#4A3F35" background="#F8F1E3"/>
  <style name="selection" background="#E8D9BC"/>
  <style name="cursor" foreground="#7A5C3E"/>
  <style name="typecase:syntax" foreground="#B3A592"/>
  <style name="typecase:heading" foreground="#3B2F25"/>
  <style name="typecase:link" foreground="#9C5B2E"/>
  <style name="typecase:code" background="#EFE5D2"/>
  <style name="typecase:code-block" foreground="#E0D3BC" background="#F2E9D8"/>
</style-scheme>
```

The root element needs an `id` (letters, digits, and dashes; it must not start with `typecase-`, which is reserved for the built-in themes) and a `name`, which appears on the tile.

### The styles Typecase uses

| Style | Attribute | What it colors | If missing |
| --- | --- | --- | --- |
| `text` | `foreground`, `background` | Text color and page background | Taken from the parent scheme |
| `selection` | `background` | Selected text | Taken from the parent scheme |
| `cursor` | `foreground` | Text cursor | Text color |
| `typecase:syntax` | `foreground` | Markdown marks such as `#`, `**`, `_`, shown faintly | Text color at 40 % opacity |
| `typecase:heading` | `foreground` | Headings | Text color |
| `typecase:link` | `foreground` | Links; also the accent color of the window (selection in the library, switches, progress rings) | `def:net-address`, then blue |
| `typecase:list-marker` | `foreground` | List bullets and numbers | Link color |
| `typecase:code` | `background` | Background of `inline code` | Text color at low opacity |
| `typecase:code-block` | `foreground`, `background` | Code blocks: frame and fill | Text color at low opacity |

Colors are written as `#RRGGBB`, or `#RRGGBBAA` with transparency (for example `#00000059` is black at 35 %).

Syntax highlighting inside code blocks (` ```python `) uses the scheme’s regular GtkSourceView styles (`def:keyword`, `def:string`, `def:comment`, …). The easiest way to get good code colors is `parent-scheme`: the theme then takes everything it does not define itself from that scheme. GtkSourceView always includes `Adwaita`, `Adwaita-dark`, `solarized-light`, `solarized-dark`, `classic`, `classic-dark`, `kate`, `kate-dark`, `cobalt`, `cobalt-light`, `oblivion`, and `tango`.

### Light and dark variants

A theme with two variants consists of two files. Typecase pairs them in one of two ways:

- **Metadata**, as in the example above: the light file names its partner with `dark-variant`, the dark file names its partner with `light-variant` and has `<property name="variant">dark</property>`.
- **File IDs**: the dark variant’s ID is the light one’s plus `-dark`, for example `my-paper` and `my-paper-dark`.

Import both files to get both variants. A theme with only one file is used for light and dark alike. Without the `variant` property, Typecase decides by the brightness of the page background.

### The window colors

For every theme except “Standard”, Typecase derives the colors of the whole window from the theme: header bars take the page background, the sidebar and properties pane a slightly darker shade (lighter in dark themes), menus and dialogs a shade in between, and the accent color comes from `typecase:link`. You do not need to define anything extra for this.

## Using themes from elsewhere

Many color schemes exist in this format, often published as themes for gedit, GNOME Text Editor, or GtkSourceView (for example Catppuccin, Dracula, Nord, or Gruvbox). Such schemes do not know the `typecase:` styles, so Typecase derives the Markdown colors from their text and link colors. To fine-tune them, add `typecase:` styles to a copy of the file and import it again.

## Checking and sharing

On import, Typecase checks that the file is a style scheme that GtkSourceView can load, that it has an ID and a name, and that it is not larger than 512 KB. A broken file is never imported. Importing a file with the same ID as an already imported theme replaces it. Removing a theme moves its files to the trash.

You can share the `.xml` files as they are. Imported themes are available on the computer where you imported them.
