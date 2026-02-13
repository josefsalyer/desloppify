"""Fixer: wrap bare `return err` with fmt.Errorf context."""

import re
from pathlib import Path

from .common import apply_fixer, find_enclosing_func


def detect_bare_errors(path: Path) -> list[dict]:
    """Detect bare error returns and empty error checks, returning flat entries."""
    from ..detectors.smells import detect_smells
    entries, _ = detect_smells(path)
    flat = []
    for e in entries:
        if e["id"] in ("bare_error_return", "empty_error_check"):
            for m in e["matches"]:
                flat.append({
                    "file": m["file"], "line": m["line"],
                    "name": f"{e['id']}::{m['line']}",
                    "content": m["content"], "smell_id": e["id"],
                })
    return flat


_BARE_RETURN_RE = re.compile(r'^(\s*)return\s+err\s*$')
_SINGLE_LINE_CHECK_RE = re.compile(
    r'^(\s*)if\s+err\s*!=\s*nil\s*\{\s*return\s+err\s*\}')
_MULTI_LINE_IF_RE = re.compile(r'^\s*if\s+err\s*!=\s*nil\s*\{')


def fix_error_wrap(entries: list[dict], *, dry_run: bool = False) -> list[dict]:
    """Replace bare `return err` with `return fmt.Errorf("<func>: %w", err)`."""
    def _transform(lines, file_entries):
        removed = []
        entry_lines = {e["line"] for e in file_entries}
        # Track which bare-return lines we've already fixed (to avoid double-fix)
        fixed_lines: set[int] = set()

        for i in range(len(lines)):
            line_num = i + 1
            if line_num not in entry_lines:
                continue
            if i in fixed_lines:
                continue

            func_name = find_enclosing_func(lines, i) or "operation"

            # Single-line: if err != nil { return err }
            m = _SINGLE_LINE_CHECK_RE.match(lines[i])
            if m:
                indent = m.group(1)
                lines[i] = (f'{indent}if err != nil '
                            f'{{ return fmt.Errorf("{func_name}: %w", err) }}\n')
                removed.append(f"error-wrap::{line_num}")
                continue

            # Multi-line: if err != nil { \n return err \n }
            if _MULTI_LINE_IF_RE.match(lines[i]):
                # Scan forward for the bare return err inside this block
                for j in range(i + 1, min(i + 5, len(lines))):
                    m2 = _BARE_RETURN_RE.match(lines[j])
                    if m2:
                        indent2 = m2.group(1)
                        lines[j] = f'{indent2}return fmt.Errorf("{func_name}: %w", err)\n'
                        fixed_lines.add(j)
                        removed.append(f"error-wrap::{line_num}")
                        break
                continue

            # Bare: return err
            m = _BARE_RETURN_RE.match(lines[i])
            if m:
                indent = m.group(1)
                lines[i] = f'{indent}return fmt.Errorf("{func_name}: %w", err)\n'
                removed.append(f"error-wrap::{line_num}")
                continue

        return lines, removed

    return apply_fixer(entries, _transform, dry_run=dry_run)
