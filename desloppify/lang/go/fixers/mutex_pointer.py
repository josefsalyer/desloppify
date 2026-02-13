"""Fixer: change sync.Mutex value parameters to pointer parameters."""

import re
from pathlib import Path

from .common import apply_fixer


def detect_mutex_copy(path: Path) -> list[dict]:
    """Detect sync.Mutex passed by value in function params."""
    from ..detectors.smells import detect_smells
    entries, _ = detect_smells(path)
    flat = []
    for e in entries:
        if e["id"] == "mutex_copy":
            for m in e["matches"]:
                flat.append({
                    "file": m["file"], "line": m["line"],
                    "name": f"mutex_copy::{m['line']}",
                    "content": m["content"],
                })
    return flat


_MUTEX_VALUE_RE = re.compile(r'(\w+)\s+sync\.Mutex\b')


def fix_mutex_pointer(entries: list[dict], *, dry_run: bool = False) -> list[dict]:
    """Change `mu sync.Mutex` to `mu *sync.Mutex` in function signatures."""
    def _transform(lines, file_entries):
        removed = []
        entry_lines = {e["line"] for e in file_entries}

        for i in range(len(lines)):
            if (i + 1) not in entry_lines:
                continue

            # Only replace value params, not pointer params (already *sync.Mutex)
            if "*sync.Mutex" in lines[i]:
                continue

            new_line = _MUTEX_VALUE_RE.sub(r'\1 *sync.Mutex', lines[i])
            if new_line != lines[i]:
                lines[i] = new_line
                removed.append(f"mutex-pointer::{i + 1}")

        return lines, removed

    return apply_fixer(entries, _transform, dry_run=dry_run)
