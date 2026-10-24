import os
import shutil
import tempfile
from pathlib import Path


def atomic_write_text(path: Path, text: str) -> None:
    """Writes to a temporary file in the same folder first and then renames it,
    so that a half-written file is never left behind.

    Line endings stay unchanged, file permissions are preserved, and a symlink to
    the file stays a symlink (the write goes to its target)."""
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
    """Reads a UTF-8 file without converting line endings. Raises UnicodeDecodeError for
    other encodings, so that a file is never written back corrupted."""
    return path.read_bytes().decode("utf-8")


def _current_umask() -> int:
    mask = os.umask(0)
    os.umask(mask)
    return mask
