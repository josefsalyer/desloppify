"""Shared Go fixer utilities: apply_fixer template and Go-specific helpers."""

import os
import re
import sys
from collections import defaultdict
from pathlib import Path

from ....utils import PROJECT_ROOT, c, rel


def find_balanced_end(lines: list[str], start: int, *, track: str = "parens",
                      max_lines: int = 80) -> int | None:
    """Find the line where brackets opened at *start* balance to zero."""
    paren_depth = 0
    brace_depth = 0
    for idx in range(start, min(start + max_lines, len(lines))):
        line = lines[idx]
        in_str = None
        prev_ch = ""
        for ch in line:
            if in_str:
                if ch == in_str and prev_ch != "\\":
                    in_str = None
                prev_ch = ch
                continue
            if ch in "'\"`":
                in_str = ch
            elif ch == "(":
                paren_depth += 1
            elif ch == ")":
                paren_depth -= 1
                if track == "parens" and paren_depth <= 0:
                    return idx
            elif ch == "{":
                brace_depth += 1
            elif ch == "}":
                brace_depth -= 1
                if track == "braces" and brace_depth <= 0:
                    return idx
            prev_ch = ch
    return None


def apply_fixer(entries: list[dict], transform_fn, *, dry_run: bool = False,
                file_key: str = "file") -> list[dict]:
    """Shared file-loop template for fixers.

    Groups *entries* by file, reads each file, calls
    ``transform_fn(lines, file_entries) -> (new_lines, removed_names)``
    and writes back if changed.
    """
    by_file: dict[str, list[dict]] = defaultdict(list)
    for e in entries:
        by_file[e[file_key]].append(e)

    results = []
    for filepath, file_entries in sorted(by_file.items()):
        try:
            p = Path(filepath) if Path(filepath).is_absolute() else PROJECT_ROOT / filepath
            original = p.read_text()
            lines = original.splitlines(keepends=True)

            new_lines, removed_names = transform_fn(lines, file_entries)
            new_content = "".join(new_lines)

            if new_content != original:
                lines_removed = len(original.splitlines()) - len(new_content.splitlines())
                results.append({
                    "file": filepath,
                    "removed": removed_names,
                    "lines_removed": lines_removed,
                })
                if not dry_run:
                    tmp = p.with_suffix(p.suffix + ".tmp")
                    try:
                        tmp.write_text(new_content)
                        os.replace(str(tmp), str(p))
                    except BaseException:
                        tmp.unlink(missing_ok=True)
                        raise
        except (OSError, UnicodeDecodeError) as ex:
            print(c(f"  Skip {rel(filepath)}: {ex}", "yellow"), file=sys.stderr)

    return results


def collapse_blank_lines(lines: list[str], removed_indices: set[int] | None = None) -> list[str]:
    """Filter out removed lines and collapse double blank lines."""
    result = []
    prev_blank = False
    for idx, line in enumerate(lines):
        if removed_indices and idx in removed_indices:
            continue
        is_blank = line.strip() == ""
        if is_blank and prev_blank:
            continue
        result.append(line)
        prev_blank = is_blank
    return result


_FUNC_RE = re.compile(r'^func\s+(?:\([^)]*\)\s+)?(\w+)\s*\(')


def find_enclosing_func(lines: list[str], line_idx: int) -> str | None:
    """Scan backward from line_idx to find the enclosing function name.

    Handles both standalone functions and methods:
      func FuncName(...)       -> "FuncName"
      func (r *Recv) Method()  -> "Method"

    Returns None if no enclosing function is found.
    """
    for i in range(line_idx, -1, -1):
        m = _FUNC_RE.match(lines[i])
        if m:
            return m.group(1)
    return None


_FOR_RE = re.compile(r'^\s*for\s+')


def find_enclosing_for(lines: list[str], line_idx: int) -> int | None:
    """Scan backward from line_idx to find the enclosing for/range loop.

    Returns the 0-indexed line number of the for statement, or None.
    Uses brace tracking to ensure we don't cross function boundaries.
    """
    brace_depth = 0
    for i in range(line_idx, -1, -1):
        for ch in reversed(lines[i]):
            if ch == '}':
                brace_depth += 1
            elif ch == '{':
                brace_depth -= 1
        # A for line with its opening brace will push depth to -1.
        # Check for the for match before bailing on negative depth.
        if _FOR_RE.match(lines[i]) and brace_depth == -1:
            return i
        if brace_depth < 0:
            return None
    return None
