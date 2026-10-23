import re

# Ein Wort: Buchstaben/Ziffern, auch mit Bindestrich oder Apostroph verbunden ("E-Mail", "geht's").
# Markdown-Zeichen wie #, *, - oder > zählen dadurch nicht als Wörter.
_WORD = re.compile(r"\w+(?:[-'’]\w+)*")
# Nummern am Anfang nummerierter Listen ("1. ", "12) ") sind Markdown, kein Text.
_LIST_NUMBER = re.compile(r"^[ \t]*(?:>[ \t]*)*\d{1,9}[.)][ \t]+", re.MULTILINE)


def count_words(text: str) -> int:
    return sum(1 for _match in _WORD.finditer(_LIST_NUMBER.sub("", text)))


def count_characters(text: str) -> int:
    """Zeichen einschließlich Leerzeichen, ohne Zeilenumbrüche."""
    return len(text) - text.count("\n") - text.count("\r")
