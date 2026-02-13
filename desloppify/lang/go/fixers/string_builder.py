"""Fixer: replace string concatenation (+=) in loops with strings.Builder."""

import re
from pathlib import Path

from .common import apply_fixer, find_enclosing_for


def detect_string_concat(path: Path) -> list[dict]:
    """Detect string concatenation with += inside for loops."""
    from ..detectors.smells import detect_smells
    entries, _ = detect_smells(path)
    flat = []
    for e in entries:
        if e["id"] == "string_concat_loop":
            for m in e["matches"]:
                flat.append({
                    "file": m["file"], "line": m["line"],
                    "name": f"string_concat::{m['line']}",
                    "content": m["content"],
                })
    return flat


_CONCAT_RE = re.compile(r'^(\s*)(\w+)\s*\+=\s*(.+)$')


def fix_string_builder(entries: list[dict], *, dry_run: bool = False) -> list[dict]:
    """Replace `s += expr` in loops with strings.Builder pattern."""
    def _transform(lines, file_entries):
        removed = []
        # Group by enclosing for-loop to avoid multiple builder vars per loop
        processed_loops: set[int] = set()
        sorted_entries = sorted(file_entries, key=lambda e: e["line"])

        for entry in sorted_entries:
            idx = entry["line"] - 1
            if idx < 0 or idx >= len(lines):
                continue

            m = _CONCAT_RE.match(lines[idx])
            if not m:
                continue

            var_name = m.group(2)
            expr = m.group(3).strip()
            indent = m.group(1)

            for_idx = find_enclosing_for(lines, idx)
            if for_idx is None:
                continue

            # Replace += with WriteString
            lines[idx] = f"{indent}sb.WriteString({expr})\n"
            removed.append(f"string-builder::{entry['line']}")

            if for_idx not in processed_loops:
                processed_loops.add(for_idx)
                for_indent = lines[for_idx][:len(lines[for_idx]) - len(lines[for_idx].lstrip())]

                # Insert builder declaration before for loop
                lines.insert(for_idx, f"{for_indent}var sb strings.Builder\n")
                # Adjust idx since we inserted a line before it
                idx += 1

                # Find the end of the for loop body by tracking braces
                brace_depth = 0
                found_open = False
                loop_end = for_idx + 1
                for j in range(for_idx + 1, len(lines)):
                    for ch in lines[j]:
                        if ch == '{':
                            brace_depth += 1
                            found_open = True
                        elif ch == '}':
                            brace_depth -= 1
                    if found_open and brace_depth <= 0:
                        loop_end = j
                        break

                # Insert assignment after loop closes
                assign_line = f"{for_indent}{var_name} = sb.String()\n"
                lines.insert(loop_end + 1, assign_line)

        return lines, removed

    return apply_fixer(entries, _transform, dry_run=dry_run)
