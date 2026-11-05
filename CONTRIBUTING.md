# Contributing to Typecase

Thank you for your interest! Typecase is a hobby project without commercial intent, and help is very welcome. Please allow a few days for a reply.

The most useful contribution right now is a **translation** into your language. You don't need to know how to program for that.

## Translating Typecase

Typecase is available in English and German. Its texts live in the [`po/`](po/) folder as [gettext](https://www.gnu.org/software/gettext/) files, with one `.po` file per language. English is the source language, and `po/typecase.pot` is the template for new translations.

### Start a new language

1. Make sure nobody is working on your language yet: look through the [issues](https://github.com/kleinod-studio/Typecase/issues) and [pull requests](https://github.com/kleinod-studio/Typecase/pulls). Then open an issue to say which language you are taking on.
2. Download [`po/typecase.pot`](po/typecase.pot).
3. Open it in a translation editor, such as [Poedit](https://poedit.net) or [GTranslator](https://apps.gnome.org/Gtranslator/), and create a new translation for your language. A plain text editor works too. On the command line, for French:

   ```bash
   msginit --locale=fr --input=po/typecase.pot --output-file=po/fr.po
   ```

4. Translate the texts and save the file as `po/<language code>.po`, for example `fr.po` or `pt_BR.po`.
5. Add the language code on a new line in [`po/LINGUAS`](po/LINGUAS).
6. Send both files as a pull request.

**Not familiar with Git?** That's fine. Attach your `.po` file to an issue (zip it first if GitHub refuses the file type), and it will be added for you.

### Improve an existing language

Change the language's `.po` file in `po/` and send a pull request, or simply open an issue with your suggestion. A translation can be incomplete: texts that are still missing appear in English.

### Tips for translating

- **Placeholders** stay exactly as they are, but you can move them within the sentence: `%(count)s`, `%(name)s`, `%s` and `{address}` are filled in by the app. A missing or changed placeholder can cause errors.
- **Comments** that start with `Translators:` explain where a text appears.
- **Your name**: the text `translator-credits` is not meant to be translated. Replace it with your name, one translator per line, and it appears in the About dialog.
- **Punctuation**: use the quotation marks of your language. German, for example, turns “this” into „this“.
- **Tone**: Typecase is calm and friendly. Short, plain wording fits it better than a literal translation.
- **Key terms**: keep these consistent throughout the app:

| English | Meaning | German, as an example |
|---|---|---|
| Library | The folder that holds all your texts | Bibliothek |
| Group | A subfolder in the library | Gruppe |
| Sheet | A single text, stored as a `.md` file | Blatt |
| Template | Decides what an export looks like | Vorlage |
| Attachment | A file kept together with a sheet | Anhang |
| Outline | The list of headings to jump to | Gliederung |

### Try out your translation

You can see your translation in the running app if you have the [requirements for development](README.md#development) and gettext's `msgfmt` installed. `run-dev.sh` compiles all translations when it starts. For French:

```bash
LANGUAGE=fr ./run-dev.sh
```

If that is too much effort, just send the file. Check it afterwards in the next release.

### When new texts are added

New versions of Typecase bring new texts, which then appear in English until they are translated. To update your file, open it in your translation editor and update it from `po/typecase.pot`, or run:

```bash
msgmerge --update --backup=none po/fr.po po/typecase.pot
```

## Reporting bugs and sharing ideas

[Open an issue](https://github.com/kleinod-studio/Typecase/issues). For a bug, please tell us what you did, what you expected and what happened instead, and which version and Linux distribution you use. You will find the version under *Menu → About Typecase*.

Security problems should not go into a public issue; see the [security policy](SECURITY.md). If something is hard to use because of a disability, please tell us as well; see [accessibility](ACCESSIBILITY.md).

Before you suggest a feature, have a look at the [roadmap](ROADMAP.md). It lists what is planned, and also what Typecase deliberately will not do, such as cloud sync or user accounts.

## Contributing code

Please open an issue first, so that we can agree on the idea before you put work into it. Then:

- Follow the principles in the [roadmap](ROADMAP.md#principles). The most important ones: texts are never lost, files stay plain Markdown, and there is no telemetry and no network access.
- Use standard libadwaita widgets where they exist, and make everything usable with the keyboard.
- Write code, comments and commit messages in English.
- Mark new interface texts for translation with `_()`, using English source strings and named placeholders. Then update the template as described below.
- Add new Python files to `src/meson.build`, and to `po/POTFILES.in` if they contain texts.
- Keep pull requests small and focused on one thing.
- Run both test suites first. See [Development](README.md#development) for how to set up and run Typecase.

```bash
python3 -m unittest discover -s tests
python3 tests/gui_smoke.py
```

To update the translation template after changing texts:

```bash
xgettext --from-code=UTF-8 -L Python -k --keyword=_ --keyword=ngettext:1,2 --add-comments=Translators --package-name=typecase -f po/POTFILES.in -o po/typecase.pot
```

## License

Typecase is licensed under the [GPL-3.0-or-later](LICENSE). By contributing, you agree that your contribution is published under the same license.

Please be kind and respectful to everyone involved. Our [code of conduct](CODE_OF_CONDUCT.md) applies to all contributions.
