"""Go source code extraction -- AST helper with regex fallback."""
from __future__ import annotations

import hashlib
import re
from pathlib import Path

from ...detectors.base import FunctionInfo, ClassInfo
from ...utils import PROJECT_ROOT


def _read_file(filepath: str | Path) -> str | None:
    """Read a file, returning None on error."""
    p = Path(filepath)
    if not p.is_absolute():
        p = PROJECT_ROOT / filepath
    try:
        return p.read_text()
    except (OSError, UnicodeDecodeError):
        return None


# -- Function patterns --

# Matches: func Name(  or  func (r *Recv) Name(
_FUNC_RE = re.compile(
    r"^func\s+"
    r"(?:\(([^)]+)\)\s+)?"   # optional receiver group
    r"(\w+)\s*\(",            # function name and opening paren
    re.MULTILINE,
)


def _extract_params_from_sig(sig_text: str) -> list[str]:
    """Extract parameter names from a Go function signature string."""
    # Remove the func keyword, receiver, name prefix to isolate param list
    # sig_text is everything between the opening ( after func name and closing )
    params = []
    for token in sig_text.split(","):
        token = token.strip()
        if not token:
            continue
        # Go params: "name type" or "name, name2 type"
        # Handle multi-name: "a, b int" becomes ["a", "b"]
        parts = token.split()
        if not parts:
            continue
        # The last token is the type; everything before is names
        # But a single token like "error" is a return type, not a param
        if len(parts) == 1:
            # Could be a bare type (no name) or a name without type (grouped)
            name = parts[0]
            if name[0].islower() and name.isidentifier():
                params.append(name)
        else:
            # "name type" or "name ...type"
            name = parts[0]
            if name.isidentifier():
                params.append(name)
    return params


def _find_matching_brace(lines: list[str], start_line: int, start_col: int = 0) -> int | None:
    """Find the line number of the closing brace matching the opening brace.

    Args:
        lines: All file lines
        start_line: Line index where the opening { is
        start_col: Column position to start scanning from on start_line

    Returns:
        Line index of the closing }, or None if not found.
    """
    depth = 0
    for i in range(start_line, len(lines)):
        line = lines[i]
        col_start = start_col if i == start_line else 0
        for j in range(col_start, len(line)):
            ch = line[j]
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    return i
    return None


def extract_go_functions(filepath: Path | str) -> list[FunctionInfo]:
    """Extract all functions from a Go file."""
    return _extract_functions_regex(filepath)


def extract_go_structs(filepath: Path | str) -> list[ClassInfo]:
    """Extract all structs from a Go file."""
    return _extract_structs_regex(filepath)


def _extract_functions_regex(filepath: Path | str) -> list[FunctionInfo]:
    """Regex-based Go function extraction."""
    content = _read_file(filepath)
    if content is None:
        return []

    lines = content.splitlines()
    functions = []
    filepath_str = str(filepath)

    for m in _FUNC_RE.finditer(content):
        receiver_text = m.group(1)  # e.g. "s *Server" or None
        func_name = m.group(2)

        # Find line number of match
        line_offset = content[:m.start()].count("\n")

        # Find the parameter list: scan from after func name's ( to closing )
        paren_start = m.end() - 1  # position of opening (
        depth = 1
        i = paren_start + 1
        while i < len(content) and depth > 0:
            if content[i] == "(":
                depth += 1
            elif content[i] == ")":
                depth -= 1
            i += 1
        if depth != 0:
            continue

        param_text = content[paren_start + 1:i - 1]
        params = _extract_params_from_sig(param_text)

        # Find opening brace
        rest = content[i:]
        brace_pos = rest.find("{")
        if brace_pos == -1:
            continue

        # The absolute position of the opening brace
        abs_brace_pos = i + brace_pos
        brace_line = content[:abs_brace_pos].count("\n")

        # Find matching closing brace
        brace_col = abs_brace_pos - content.rfind("\n", 0, abs_brace_pos) - 1
        end_line = _find_matching_brace(lines, brace_line, brace_col)
        if end_line is None:
            continue

        func_start = line_offset
        func_end = end_line + 1  # inclusive
        loc = func_end - func_start
        body = "\n".join(lines[func_start:func_end])
        normalized = _normalize_go_body(body)
        body_hash = hashlib.md5(normalized.encode()).hexdigest()

        functions.append(FunctionInfo(
            name=func_name,
            file=filepath_str,
            line=func_start + 1,
            end_line=func_end,
            loc=loc,
            body=body,
            normalized=normalized,
            body_hash=body_hash,
            params=params,
        ))

    return functions


def _normalize_go_body(body: str) -> str:
    """Normalize a Go function body for duplicate detection.

    Strips comments, blank lines, and logging statements.
    """
    normalized = []
    for line in body.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        # Skip single-line comments
        if stripped.startswith("//"):
            continue
        # Strip inline comments
        comment_idx = stripped.find("//")
        if comment_idx > 0:
            stripped = stripped[:comment_idx].rstrip()
        # Skip log/fmt.Print lines
        if re.match(r"(?:fmt\.Print|log\.Print|log\.Fatal|log\.Panic)", stripped):
            continue
        if stripped:
            normalized.append(stripped)
    return "\n".join(normalized)


# -- Struct patterns --

_STRUCT_RE = re.compile(
    r"^type\s+(\w+)\s+struct\s*\{",
    re.MULTILINE,
)


def _extract_structs_regex(filepath: Path | str) -> list[ClassInfo]:
    """Regex-based Go struct extraction."""
    content = _read_file(filepath)
    if content is None:
        return []

    lines = content.splitlines()
    structs = []
    filepath_str = str(filepath)

    for m in _STRUCT_RE.finditer(content):
        struct_name = m.group(1)
        start_line = content[:m.start()].count("\n")

        # Find the opening brace position
        brace_abs = m.end() - 1  # position of {
        brace_line = content[:brace_abs].count("\n")
        brace_col = brace_abs - content.rfind("\n", 0, brace_abs) - 1

        end_line = _find_matching_brace(lines, brace_line, brace_col)
        if end_line is None:
            continue

        # Parse fields and embedded types from struct body
        fields = []
        embedded = []
        for line_idx in range(brace_line + 1, end_line):
            if line_idx >= len(lines):
                break
            field_line = lines[line_idx].strip()
            if not field_line or field_line.startswith("//"):
                continue

            # Strip inline comments
            comment_pos = field_line.find("//")
            if comment_pos > 0:
                field_line = field_line[:comment_pos].rstrip()

            # Strip struct tags (backtick-delimited)
            tag_pos = field_line.find("`")
            if tag_pos > 0:
                field_line = field_line[:tag_pos].rstrip()

            parts = field_line.split()
            if not parts:
                continue

            if len(parts) == 1:
                # Embedded type: just a type name (e.g., "User" or "*User")
                type_name = parts[0].lstrip("*")
                if type_name and type_name[0].isupper():
                    embedded.append(type_name)
            else:
                # Named field: "Name Type" or "Name, Name2 Type"
                field_name = parts[0].rstrip(",")
                if field_name.isidentifier():
                    fields.append(field_name)

        loc = end_line - start_line + 1

        structs.append(ClassInfo(
            name=struct_name,
            file=filepath_str,
            line=start_line + 1,
            loc=loc,
            methods=[],  # Methods are found separately via func extraction
            attributes=fields,
            base_classes=embedded,
        ))

    return structs
