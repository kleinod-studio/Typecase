import os
import shutil
import tempfile
from pathlib import Path


def atomic_write_text(path: Path, text: str) -> None:
    """Schreibt erst in eine temporäre Datei im selben Ordner und benennt sie dann um,
    damit nie eine halb geschriebene Datei übrig bleibt.

    Zeilenenden bleiben unverändert, Dateirechte bleiben erhalten, und ein Link auf
    die Datei bleibt ein Link (geschrieben wird in das Ziel)."""
    target = Path(os.path.realpath(path))
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(dir=target.parent, prefix=f".{target.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as tmp:
            tmp.write(text)
            tmp.flush()
            os.fsync(tmp.fileno())
        if target.exists():
            shutil.copymode(target, tmp_name)
        else:
            os.chmod(tmp_name, 0o666 & ~_current_umask())
        os.replace(tmp_name, target)
    except BaseException:
        try:
            os.unlink(tmp_name)
        except FileNotFoundError:
            pass
        raise


def read_text(path: Path) -> str:
    """Liest eine UTF-8-Datei, ohne Zeilenenden umzuwandeln. Wirft UnicodeDecodeError bei
    anderen Kodierungen, damit eine Datei nie beschädigt zurückgeschrieben wird."""
    return path.read_bytes().decode("utf-8")


def _current_umask() -> int:
    mask = os.umask(0)
    os.umask(mask)
    return mask
