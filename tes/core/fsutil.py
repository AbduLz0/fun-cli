"""Small, careful file helpers."""
from __future__ import annotations

import os
import tempfile
from pathlib import Path


def atomic_write(path: Path, text: str, mode: int | None = None) -> None:
    """Write `text` to `path` atomically.

    * follows symlinks, so dotfile managers (stow, chezmoi...) keep working
    * preserves the existing permission bits
    * never leaves a half-written file behind
    """
    path = Path(os.path.realpath(path))
    path.parent.mkdir(parents=True, exist_ok=True)
    if mode is None:
        try:
            mode = path.stat().st_mode & 0o777
        except OSError:
            mode = 0o644
    fd, tmp = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(text)
            fh.flush()
            os.fsync(fh.fileno())
        os.chmod(tmp, mode)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def read_text(path: Path) -> str:
    try:
        return Path(path).read_text(encoding="utf-8")
    except FileNotFoundError:
        return ""
