# Accessibility

Typecase should be usable by everyone who writes. Accessibility is one of the project's [principles](ROADMAP.md#principles), and this page describes where it stands.

Typecase has not had a formal accessibility audit, and this page is not a claim of conforming to a standard such as WCAG.

## What Typecase offers

- **Keyboard:** everything is meant to work with the keyboard, including alternatives to dragging (Alt+arrow keys change the order of sheets and cards). Ctrl+? lists the shortcuts.
- **Screen readers:** Typecase uses GTK's accessibility support and standard libadwaita widgets, and its own elements, such as progress rings, are labeled for screen readers.
- **Seeing the text:** font, font size, line width and line spacing can be changed, separately for focus mode if you like. There is a High Contrast theme, and every theme has a light and a dark variant that follows your system.
- **Color:** pills for images, links and footnotes also carry an icon, so they do not rely on color alone.
- **Less distraction:** dimming and typewriter scrolling in focus mode can each be switched off.
- **Images:** every image can have an alternative text, which Word and web page exports carry along.

## Supported environments

Typecase is built for GNOME and libadwaita on Linux, and is tested most on GNOME. It works with a keyboard and a pointing device, down to a window width of 360 pixels.

## Known limitations

- Exported PDFs are not tagged yet, so screen readers may not read them well. Word and web page exports are the better choice for now.
- Touch input has not been tested and refined yet. It is on the [roadmap](ROADMAP.md).
- The interface is available in English and German only so far. [Translations](CONTRIBUTING.md#translating-typecase) are welcome.

## Reporting a barrier

If something in Typecase gets in your way, please [tell us about it](https://github.com/kleinod-studio/Typecase/issues/new?template=accessibility.yml). If you prefer not to do that in public, write to [sascha@kleinod.studio](mailto:sascha@kleinod.studio). Please tell us what you tried to do, and which assistive technology you use, if any.
