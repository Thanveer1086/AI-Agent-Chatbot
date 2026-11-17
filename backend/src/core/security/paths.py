"""Filesystem path safety helpers (filename sanitization and directory containment)."""
import re
import unicodedata
from pathlib import Path

_UNSAFE_CHARS = re.compile(r"[^A-Za-z0-9._ ()-]+")
MAX_FILENAME_LENGTH = 200


def safe_filename(raw_name: str) -> str:
    """Reduce a user-supplied filename to a safe basename.

    Strips any directory components (both / and \\), control characters and
    unusual symbols. Raises ValueError if nothing usable remains.
    """
    if not raw_name:
        raise ValueError("Filename is empty.")

    name = unicodedata.normalize("NFKC", raw_name)
    # Drop any directory component, whatever separator the client used.
    name = re.split(r"[\\/]", name)[-1]
    name = _UNSAFE_CHARS.sub("_", name).strip(" .")

    if not name or name in {".", ".."}:
        raise ValueError(f"Invalid filename: {raw_name!r}")

    if len(name) > MAX_FILENAME_LENGTH:
        stem, dot, ext = name.rpartition(".")
        if dot and len(ext) <= 10:
            name = stem[: MAX_FILENAME_LENGTH - len(ext) - 1] + "." + ext
        else:
            name = name[:MAX_FILENAME_LENGTH]
    return name


def resolve_within(base_dir: Path, relative: str) -> Path:
    """Resolve `relative` under `base_dir`, refusing anything that escapes it."""
    base = base_dir.resolve()
    target = (base / relative).resolve()
    if target != base and base not in target.parents:
        raise ValueError(f"Path {relative!r} escapes the allowed directory.")
    return target
