"""Fixer: lowercase error strings and strip trailing punctuation."""

import re
from pathlib import Path

from .common import apply_fixer


def detect_error_strings(path: Path) -> list[dict]:
    """Detect error strings starting with capitals."""
    from ..detectors.smells import detect_smells
    entries, _ = detect_smells(path)
    flat = []
    for e in entries:
        if e["id"] == "error_string_format":
            for m in e["matches"]:
                flat.append({
                    "file": m["file"], "line": m["line"],
                    "name": f"error_string::{m['line']}",
                    "content": m["content"],
                })
    return flat


_ERROR_STRING_RE = re.compile(
    r'((?:errors\.New|fmt\.Errorf)\s*\(\s*")([A-Z])((?:[^"\\]|\\.)*")')


def fix_error_strings(entries: list[dict], *, dry_run: bool = False) -> list[dict]:
    """Lowercase first char of error strings and strip trailing period."""
    def _transform(lines, file_entries):
        removed = []
        entry_lines = {e["line"] for e in file_entries}

        for i in range(len(lines)):
            if (i + 1) not in entry_lines:
                continue

            m = _ERROR_STRING_RE.search(lines[i])
            if not m:
                continue

            prefix = m.group(1)       # errors.New("
            first_char = m.group(2)   # Capital letter
            rest = m.group(3)         # ...rest of string"

            # Lowercase first char
            new_first = first_char.lower()

            # Strip trailing period before closing quote
            if rest.endswith('."'):
                rest = rest[:-2] + '"'

            new_segment = prefix + new_first + rest
            lines[i] = lines[i][:m.start()] + new_segment + lines[i][m.end():]
            removed.append(f"error-string::{i + 1}")

        return lines, removed

    return apply_fixer(entries, _transform, dry_run=dry_run)
