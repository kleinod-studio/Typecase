#!/usr/bin/env python3
"""Packt einen Skill-Ordner als .skill-Datei (ZIP mit dem Ordner darin), z. B. zum Download auf der Webseite.
Testfälle (evals/) und Zwischendateien kommen nicht mit hinein.

Aufruf: python3 skills/package.py skills/typecase-template [Zielordner, Standard: dist]"""

import sys
import zipfile
from pathlib import Path

SKIP_PARTS = {"__pycache__", "evals"}


def package(skill: Path, target_dir: Path) -> Path:
    if not (skill / "SKILL.md").is_file():
        raise SystemExit(f"{skill} enthält keine SKILL.md")
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / f"{skill.name}.skill"
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED, strict_timestamps=False) as archive:
        for file in sorted(skill.rglob("*")):
            relative = file.relative_to(skill)
            if file.is_file() and not SKIP_PARTS & set(relative.parts) and file.suffix != ".pyc":
                archive.write(file, (Path(skill.name) / relative).as_posix())
    return target


if __name__ == "__main__":
    if len(sys.argv) < 2:
        raise SystemExit(__doc__)
    result = package(Path(sys.argv[1]).resolve(), Path(sys.argv[2] if len(sys.argv) > 2 else "dist"))
    print(f"{result} ({result.stat().st_size // 1024 + 1} KB)")
