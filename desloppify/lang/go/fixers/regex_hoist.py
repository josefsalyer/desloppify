"""Fixer: hoist regexp.Compile/MustCompile out of for loops."""

import re
from pathlib import Path

from .common import apply_fixer, find_enclosing_for


def detect_regex_in_loop(path: Path) -> list[dict]:
    """Detect regexp.Compile/MustCompile inside for loops."""
    from ..detectors.smells import detect_smells
    entries, _ = detect_smells(path)
    flat = []
    for e in entries:
        if e["id"] == "regex_in_loop":
            for m in e["matches"]:
                flat.append({
                    "file": m["file"], "line": m["line"],
                    "name": f"regex_in_loop::{m['line']}",
                    "content": m["content"],
                })
    return flat


_REGEX_ASSIGN_RE = re.compile(
    r'^(\s*)(\w+)\s*:?=\s*(regexp\.(?:MustCompile|Compile)\s*\(.*\))\s*$')


def fix_regex_hoist(entries: list[dict], *, dry_run: bool = False) -> list[dict]:
    """Move regexp.Compile/MustCompile above the enclosing for loop."""
    def _transform(lines, file_entries):
        removed = []
        # Sort by line descending so insertions don't shift line numbers
        sorted_entries = sorted(file_entries, key=lambda e: -e["line"])

        for entry in sorted_entries:
            idx = entry["line"] - 1
            if idx < 0 or idx >= len(lines):
                continue

            line_text = lines[idx]
            m = _REGEX_ASSIGN_RE.match(line_text)
            if not m:
                continue

            var_name = m.group(2)
            regex_call = m.group(3)

            for_idx = find_enclosing_for(lines, idx)
            if for_idx is None:
                continue

            # Determine indentation of the for loop
            for_line = lines[for_idx]
            for_indent = for_line[:len(for_line) - len(for_line.lstrip())]

            # Remove the line from inside the loop
            lines[idx] = ""

            # Insert above the for loop
            hoist_line = f"{for_indent}{var_name} := {regex_call}\n"
            lines.insert(for_idx, hoist_line)

            removed.append(f"regex-hoist::{entry['line']}")

        # Clean up empty lines left behind
        lines = [ln for ln in lines if ln != ""]
        return lines, removed

    return apply_fixer(entries, _transform, dry_run=dry_run)
