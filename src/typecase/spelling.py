"""Spell checking while typing, through libspelling (the GNOME library GNOME Text Editor uses).

Dictionaries come from the system (Hunspell via Enchant); in the Flatpak, from the GNOME
runtime's language packs. Without libspelling, spell checking is simply not offered."""

try:
    import gi

    gi.require_version("Spelling", "1")
    from gi.repository import Spelling
except (ImportError, ValueError):
    Spelling = None


def available() -> bool:
    return Spelling is not None


def languages() -> list[str]:
    """Codes of the installed dictionaries, e.g. ["de_DE", "en_US"]."""
    if Spelling is None:
        return []
    return [language.get_code() for language in Spelling.Provider.get_default().list_languages()]


def dictionary_for(lang: str | None, installed: list[str] | None = None) -> str | None:
    """The best installed dictionary for a sheet language such as "de-DE": the exact one, then
    another variant of the same language (de_AT for de-DE), else None."""
    if not lang:
        return None
    installed = languages() if installed is None else installed
    wanted = lang.strip().replace("-", "_")
    if wanted in installed:
        return wanted
    primary = wanted.split("_")[0].casefold()
    for code in installed:
        if code.casefold() == primary:
            return code
    variants = sorted(code for code in installed if code.split("_")[0].casefold() == primary)
    return variants[0] if variants else None
