"""Go code smell detection."""

import re
from pathlib import Path

from ....utils import find_source_files


def _smell(id: str, label: str, severity: str, pattern: str | None = None) -> dict:
    return {"id": id, "label": label, "pattern": pattern, "severity": severity}


SMELL_CHECKS = [
    # ── Error handling ──────────────────────────────────────────
    _smell("bare_error_return",
           "Bare error return without wrapping context",
           "medium", r"^\s*return\s+err\s*$"),
    _smell("ignored_error",
           "Error assigned to _ (ignored)",
           "high", r"_\s*(?:,\s*_\s*)?=\s*\w+.*\("),
    _smell("panic_in_lib",
           "panic() outside main/test files",
           "high", r"(?<!\w)panic\s*\("),
    _smell("empty_error_check",
           "if err != nil { return err } without context",
           "medium"),  # multi-line detector
    _smell("error_string_format",
           "Error string starts with capital letter or ends with punctuation",
           "low", r'(?:errors\.New|fmt\.Errorf)\s*\(\s*"[A-Z]'),
    _smell("nil_error_init",
           "var err error without immediate use",
           "low", r"^\s*var\s+err\s+error\s*$"),

    # ── Code quality ────────────────────────────────────────────
    _smell("init_function",
           "func init() usage",
           "medium", r"^func\s+init\s*\(\s*\)\s*\{"),
    _smell("global_mutable",
           "Package-level var with mutable type (slice/map)",
           "medium", r"^var\s+\w+\s*=?\s*(?:map\[|(?:\[\]))"),
    _smell("magic_number",
           "Magic numbers (>1000 in logic)",
           "low", r"(?:==|!=|>=?|<=?|[+\-*/])\s*\d{4,}"),
    _smell("todo_fixme",
           "TODO/FIXME/HACK/XXX comments",
           "low", r"//\s*(?:TODO|FIXME|HACK|XXX)"),
    _smell("hardcoded_url",
           "Hardcoded URL in source code",
           "medium", r"""(?:["'])https?://[^\s"']+(?:["'])"""),
    _smell("empty_interface",
           "interface{} or any as parameter type",
           "low", r"func\s+\w+\([^)]*\b(?:interface\{\}|\bany\b)"),

    # ── Performance ─────────────────────────────────────────────
    _smell("string_concat_loop",
           "String concatenation with += inside a for loop",
           "medium"),  # multi-line detector
    _smell("defer_in_loop",
           "defer inside a for/range loop",
           "high"),  # multi-line detector
    _smell("regex_in_loop",
           "regexp.Compile/MustCompile inside a for loop",
           "medium"),  # multi-line detector

    # ── Goroutine ───────────────────────────────────────────────
    _smell("goroutine_leak",
           "go func() without WaitGroup or channel signal",
           "medium", r"go\s+func\s*\("),
    _smell("mutex_copy",
           "Passing sync.Mutex by value",
           "high", r"func\s+\w+\([^)]*\bsync\.Mutex\b"),
    _smell("unbuffered_channel",
           "make(chan ...) without buffer size",
           "low", r"make\(\s*chan\s+\w+\s*\)"),
]


# ── String-literal line tracking ────────────────────────────


def _build_string_line_set(lines: list[str]) -> set[int]:
    """Build a set of 0-indexed line numbers inside raw string literals (backticks).

    Go raw strings are delimited by backticks (`) and can span multiple lines.
    Regular strings use double-quotes and cannot span lines.
    """
    in_raw_string = False
    string_lines: set[int] = set()

    for i, line in enumerate(lines):
        if in_raw_string:
            string_lines.add(i)
            if "`" in line:
                in_raw_string = False
            continue

        # Scan the line for backtick-delimited raw strings
        pos = 0
        while pos < len(line):
            ch = line[pos]
            # Skip regular strings (double-quoted, single line only)
            if ch == '"':
                pos += 1
                while pos < len(line):
                    if line[pos] == '\\':
                        pos += 2
                        continue
                    if line[pos] == '"':
                        pos += 1
                        break
                    pos += 1
                continue
            # Skip line comments
            if ch == '/' and pos + 1 < len(line) and line[pos + 1] == '/':
                break
            # Raw string literal
            if ch == '`':
                # Find closing backtick on same line
                close = line.find('`', pos + 1)
                if close == -1:
                    # Opens a multi-line raw string
                    in_raw_string = True
                    break
                else:
                    pos = close + 1
                    continue
            pos += 1

    return string_lines


def _match_is_in_string(line: str, match_start: int) -> bool:
    """Check if a regex match position falls inside a string literal or comment."""
    i = 0
    in_string = None  # None, '"', or '`'

    while i < len(line):
        if i == match_start:
            return in_string is not None

        ch = line[i]

        if in_string is None:
            # Check for line comment
            if ch == '/' and i + 1 < len(line) and line[i + 1] == '/':
                return match_start > i  # rest of line is comment
            if ch == '"':
                in_string = '"'
                i += 1
                continue
            if ch == '`':
                in_string = '`'
                i += 1
                continue
        elif in_string == '"':
            if ch == '\\' and i + 1 < len(line):
                i += 2
                continue
            if ch == '"':
                in_string = None
                i += 1
                continue
        elif in_string == '`':
            if ch == '`':
                in_string = None
                i += 1
                continue

        i += 1

    return in_string is not None


# ── Multi-line detectors ────────────────────────────────────


def _detect_empty_error_check(filepath: str, lines: list[str],
                               smell_counts: dict[str, list]):
    """Detect `if err != nil { return err }` without wrapping context.

    Matches single-line form:  if err != nil { return err }
    and multi-line form:
        if err != nil {
            return err
        }
    """
    single_line_re = re.compile(
        r'if\s+err\s*!=\s*nil\s*\{\s*return\s+err\s*\}'
    )

    for i, line in enumerate(lines):
        stripped = line.strip()
        # Single-line form
        if single_line_re.search(stripped):
            smell_counts["empty_error_check"].append({
                "file": filepath, "line": i + 1,
                "content": stripped[:100],
            })
            continue
        # Multi-line form: if err != nil {
        if re.match(r'if\s+err\s*!=\s*nil\s*\{', stripped):
            # Look at next non-blank line
            j = i + 1
            while j < len(lines) and lines[j].strip() == "":
                j += 1
            if j < len(lines) and re.match(r'\s*return\s+err\s*$', lines[j]):
                # Check that the block closes shortly after
                k = j + 1
                while k < len(lines) and lines[k].strip() == "":
                    k += 1
                if k < len(lines) and lines[k].strip() == "}":
                    smell_counts["empty_error_check"].append({
                        "file": filepath, "line": i + 1,
                        "content": stripped[:100],
                    })


def _detect_loop_smells(filepath: str, lines: list[str],
                         string_lines: set[int],
                         smell_counts: dict[str, list]):
    """Detect smells inside for/range loops: defer, string +=, regexp.Compile.

    Uses brace tracking to identify loop body boundaries.
    """
    for_re = re.compile(r'^\s*for\s+')
    defer_re = re.compile(r'^\s*defer\s+')
    concat_re = re.compile(r'\w+\s*\+=\s*')
    regexp_re = re.compile(r'regexp\.(?:Compile|MustCompile)\s*\(')

    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        if i in string_lines:
            i += 1
            continue

        if not for_re.match(line):
            i += 1
            continue

        # Found a for loop — track brace depth to find the loop body
        loop_start = i
        brace_depth = 0
        found_open = False

        j = i
        while j < len(lines):
            if j in string_lines:
                j += 1
                continue
            for ch in lines[j]:
                if ch == '{':
                    brace_depth += 1
                    found_open = True
                elif ch == '}':
                    brace_depth -= 1
            if found_open and brace_depth <= 0:
                break
            j += 1

        loop_end = j

        # Scan loop body for smells
        for k in range(loop_start + 1, min(loop_end + 1, len(lines))):
            if k in string_lines:
                continue
            body_line = lines[k]
            body_stripped = body_line.strip()

            if defer_re.match(body_stripped):
                smell_counts["defer_in_loop"].append({
                    "file": filepath, "line": k + 1,
                    "content": body_stripped[:100],
                })

            if concat_re.search(body_stripped):
                smell_counts["string_concat_loop"].append({
                    "file": filepath, "line": k + 1,
                    "content": body_stripped[:100],
                })

            if regexp_re.search(body_stripped):
                smell_counts["regex_in_loop"].append({
                    "file": filepath, "line": k + 1,
                    "content": body_stripped[:100],
                })

        i = loop_end + 1


# ── Main entry point ────────────────────────────────────────


def detect_smells(path: Path) -> tuple[list[dict], int]:
    """Detect Go code smell patterns. Returns (entries, total_files_checked)."""
    smell_counts: dict[str, list[dict]] = {s["id"]: [] for s in SMELL_CHECKS}
    files = find_source_files(path, [".go"])

    for filepath in files:
        try:
            p = Path(filepath) if Path(filepath).is_absolute() else Path(path) / filepath
            content = p.read_text()
            lines = content.splitlines()
        except (OSError, UnicodeDecodeError):
            continue

        # Build set of lines inside raw string literals to skip
        string_lines = _build_string_line_set(lines)

        # Determine if this is a main package or test file (for panic_in_lib)
        is_main = "package main" in content
        is_test = filepath.endswith("_test.go")
        basename = Path(filepath).name

        for check in SMELL_CHECKS:
            if check["pattern"] is None:
                continue

            # panic_in_lib: skip main.go, package main files, and test files
            if check["id"] == "panic_in_lib":
                if basename == "main.go" or is_main or is_test:
                    continue

            for i, line in enumerate(lines):
                if i in string_lines:
                    continue
                m = re.search(check["pattern"], line)
                if m and not _match_is_in_string(line, m.start()):
                    # For ignored_error, verify the _ is specifically the error
                    # position (not just any blank identifier usage)
                    if check["id"] == "ignored_error":
                        # Skip if line is just a blank import or variable declaration
                        stripped = line.strip()
                        if stripped.startswith("import") or stripped.startswith("var"):
                            continue

                    smell_counts[check["id"]].append({
                        "file": filepath, "line": i + 1,
                        "content": line.strip()[:100],
                    })

        # Multi-line detectors
        _detect_empty_error_check(filepath, lines, smell_counts)
        _detect_loop_smells(filepath, lines, string_lines, smell_counts)

    severity_order = {"high": 0, "medium": 1, "low": 2}
    entries = []
    for check in SMELL_CHECKS:
        matches = smell_counts[check["id"]]
        if matches:
            entries.append({
                "id": check["id"], "label": check["label"],
                "severity": check["severity"],
                "count": len(matches),
                "files": len(set(m["file"] for m in matches)),
                "matches": matches[:50],
            })
    entries.sort(key=lambda e: (severity_order.get(e["severity"], 9), -e["count"]))
    return entries, len(files)
