from __future__ import annotations

import logging
import time
from pathlib import Path

logger = logging.getLogger(__name__)

__all__ = ["cache_token", "safe_remove", "safe_rename"]


def safe_remove(path: Path) -> None:
    """Safely remove a file from disk.

    Directories are not removed; missing files are silently ignored after a debug log.
    """

    target = Path(path)
    if target.is_dir():
        message = f"safe_remove refuses to delete directories: {target}"
        logger.error(message)
        raise IsADirectoryError(message)

    try:
        target.unlink()
    except FileNotFoundError:
        logger.debug("safe_remove skipped missing file: %s", target)
    except OSError as exc:  # pragma: no cover - exercised in failure cases
        message = f"Unable to remove {target}: {exc}"
        logger.error(message)
        raise OSError(message) from exc
    else:
        logger.debug("Removed file: %s", target)


def safe_rename(src: Path, dest: Path) -> None:
    """Rename *src* to *dest* with helpful error reporting."""

    origin = Path(src)
    target = Path(dest)

    if not origin.exists():
        message = f"Source path does not exist: {origin}"
        logger.error(message)
        raise FileNotFoundError(message)

    if not target.parent.exists():
        message = f"Destination directory does not exist: {target.parent}"
        logger.error(message)
        raise FileNotFoundError(message)

    try:
        origin.replace(target)
    except OSError as exc:  # pragma: no cover - exercised in failure cases
        message = f"Unable to rename {origin} -> {target}: {exc}"
        logger.error(message)
        raise OSError(message) from exc
    else:
        logger.debug("Renamed %s -> %s", origin, target)


def cache_token(path: Path) -> str:
    """Return a stable cache token derived from file metadata."""

    target = Path(path)
    try:
        stat = target.stat()
    except OSError as exc:
        logger.debug("Falling back to timestamp cache token for %s: %s", target, exc)
        return f"{int(time.time() * 1_000_000):x}"

    inode = getattr(stat, "st_ino", 0)
    token = f"{stat.st_mtime_ns:x}-{stat.st_size:x}-{inode:x}"
    logger.debug("cache_token generated for %s: %s", target, token)
    return token
