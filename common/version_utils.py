"""Version suffix handling utilities."""
from __future__ import annotations

import os
import re


def parse_version_suffix(filename: str) -> tuple[str, str]:
    """Parse version suffix from a filename.
    
    Version suffixes are 1-2 uppercase ASCII letters appended before the extension.
    Returns (valid_suffix, invalid_suffix) where at most one is non-empty.
    """
    stem = os.path.splitext(filename)[0]
    match = re.search(r'([A-Za-z]{1,3})$', stem)
    
    if not match:
        return ("", "")
    
    suffix = match.group(1)
    
    # Validate: 1-2 chars, all uppercase, no repeated letters
    if len(suffix) > 2 or not suffix.isupper() or len(suffix) != len(set(suffix)):
        return ("", suffix)
    
    return (suffix, "")


def strip_version_suffix(filename: str) -> str:
    """Remove version suffix from a filename."""
    stem = os.path.splitext(filename)[0]
    ext = os.path.splitext(filename)[1]
    stem_without_suffix = re.sub(r'[A-Za-z]{1,3}$', '', stem)
    return stem_without_suffix + ext


def add_version_suffix(filename: str, suffix: str) -> str:
    """Add a version suffix to a filename."""
    stem = os.path.splitext(filename)[0]
    ext = os.path.splitext(filename)[1]
    
    if not suffix:
        return filename
    
    return stem + suffix + ext
