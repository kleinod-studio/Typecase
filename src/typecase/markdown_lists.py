import re

_ITEM = re.compile(r"^(?P<indent>[ \t]*)(?P<marker>[-*+]|\d{1,9}[.)]|>)(?P<space>[ \t]+)(?P<box>\[[ xX]\][ \t]+)?")


def on_enter(line: str, column: int) -> tuple[str, str] | None:
    """Entscheidet, was die Eingabetaste in einer Zeile mit Listenzeichen tut.

    Liefert ("continue", Präfix) für die neue Zeile, ("end", "") wenn der leere Listenpunkt
    die Liste beendet, oder None, wenn die Zeile keine Liste ist oder der Cursor im
    Listenzeichen steht (dann gilt der normale Zeilenumbruch)."""
    match = _ITEM.match(line)
    if match is None or column < match.end():
        return None
    if line[match.end() :].strip() == "":
        return ("end", "")

    marker = match["marker"]
    if marker[0].isdigit():
        marker = f"{int(marker[:-1]) + 1}{marker[-1]}"
    box = "[ ]" + match["box"][3:] if match["box"] else ""
    return ("continue", f"{match['indent']}{marker}{match['space']}{box}")
