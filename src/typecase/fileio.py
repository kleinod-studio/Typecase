import os
import tempfile
from pathlib import Path


def atomic_write_text(path: Path, text: str) -> None:
    """Schreibt erst in eine temporäre Datei im selben Ordner und benennt sie dann um,
    damit nie eine halb geschriebene Datei übrig bleibt."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as tmp:
            tmp.write(text)
            tmp.flush()
            os.fsync(tmp.fileno())
        os.replace(tmp_name, path)
    except BaseException:
        try:
            os.unlink(tmp_name)
        except FileNotFoundError:
            pass
        raise
