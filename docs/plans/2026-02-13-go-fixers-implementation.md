# Go Fixers Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add 5 auto-fixers for Go mechanical code quality issues, registered in the Go language plugin and invokable via `desloppify fix <name>`.

**Architecture:** Each fixer follows the existing TypeScript pattern: a `detect` function filters smell entries, a `fix` function uses `apply_fixer` to transform files, and a `FixerConfig` registers it in `GoConfig.fixers`. The shared `apply_fixer` template is copied into `lang/go/fixers/common.py` to avoid touching TypeScript code.

**Tech Stack:** Python, regex, text manipulation. No external dependencies.

---

### Task 1: Scaffold fixers package and common utilities

**Files:**
- Create: `desloppify/lang/go/fixers/__init__.py`
- Create: `desloppify/lang/go/fixers/common.py`
- Test: `tests/test_go_fixer_common.py`

**Step 1: Write the failing test**

Create `tests/test_go_fixer_common.py`:

```python
"""Test Go fixer common utilities."""
import textwrap
from pathlib import Path

import pytest


class TestApplyFixer:
    def test_transforms_file(self, tmp_path):
        from desloppify.lang.go.fixers.common import apply_fixer
        go_file = tmp_path / "main.go"
        go_file.write_text("package main\n\nfunc main() {}\n")

        def transform(lines, entries):
            new_lines = [l.replace("main", "app") if "func" in l else l for l in lines]
            return new_lines, ["main->app"]

        results = apply_fixer(
            [{"file": str(go_file), "line": 3, "name": "main"}],
            transform, dry_run=False)
        assert len(results) == 1
        assert results[0]["removed"] == ["main->app"]
        assert "func app()" in go_file.read_text()

    def test_dry_run_does_not_write(self, tmp_path):
        from desloppify.lang.go.fixers.common import apply_fixer
        go_file = tmp_path / "main.go"
        original = "package main\n\nfunc main() {}\n"
        go_file.write_text(original)

        def transform(lines, entries):
            return [l.replace("main", "app") for l in lines], ["main->app"]

        results = apply_fixer(
            [{"file": str(go_file), "line": 3, "name": "main"}],
            transform, dry_run=True)
        assert len(results) == 1
        assert go_file.read_text() == original

    def test_no_change_returns_empty(self, tmp_path):
        from desloppify.lang.go.fixers.common import apply_fixer
        go_file = tmp_path / "main.go"
        go_file.write_text("package main\n")

        def transform(lines, entries):
            return lines, []

        results = apply_fixer(
            [{"file": str(go_file), "line": 1, "name": "x"}],
            transform, dry_run=False)
        assert results == []


class TestFindEnclosingFunc:
    def test_finds_func(self):
        from desloppify.lang.go.fixers.common import find_enclosing_func
        lines = [
            "package main\n",
            "\n",
            "func processOrder(id string) error {\n",
            "\tresult, err := db.Get(id)\n",
            "\treturn err\n",
            "}\n",
        ]
        assert find_enclosing_func(lines, 4) == "processOrder"

    def test_finds_method(self):
        from desloppify.lang.go.fixers.common import find_enclosing_func
        lines = [
            "func (s *Service) HandleRequest(r *Request) error {\n",
            "\treturn err\n",
            "}\n",
        ]
        assert find_enclosing_func(lines, 1) == "HandleRequest"

    def test_returns_none_at_top_level(self):
        from desloppify.lang.go.fixers.common import find_enclosing_func
        lines = ["package main\n", "var x = 1\n"]
        assert find_enclosing_func(lines, 1) is None


class TestFindEnclosingFor:
    def test_finds_for_loop(self):
        from desloppify.lang.go.fixers.common import find_enclosing_for
        lines = [
            "func main() {\n",
            "\tfor i := 0; i < 10; i++ {\n",
            "\t\tdefer f()\n",
            "\t}\n",
            "}\n",
        ]
        assert find_enclosing_for(lines, 2) == 1

    def test_finds_range_loop(self):
        from desloppify.lang.go.fixers.common import find_enclosing_for
        lines = [
            "func main() {\n",
            "\tfor _, v := range items {\n",
            "\t\ts += v\n",
            "\t}\n",
            "}\n",
        ]
        assert find_enclosing_for(lines, 2) == 1

    def test_returns_none_outside_loop(self):
        from desloppify.lang.go.fixers.common import find_enclosing_for
        lines = [
            "func main() {\n",
            "\tfmt.Println()\n",
            "}\n",
        ]
        assert find_enclosing_for(lines, 1) is None


class TestCollapseBlankLines:
    def test_collapses(self):
        from desloppify.lang.go.fixers.common import collapse_blank_lines
        lines = ["a\n", "\n", "\n", "b\n"]
        assert collapse_blank_lines(lines) == ["a\n", "\n", "b\n"]

    def test_removes_indices(self):
        from desloppify.lang.go.fixers.common import collapse_blank_lines
        lines = ["a\n", "remove\n", "b\n"]
        assert collapse_blank_lines(lines, removed_indices={1}) == ["a\n", "b\n"]
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_go_fixer_common.py -v`
Expected: FAIL with "ModuleNotFoundError: No module named 'desloppify.lang.go.fixers'"

**Step 3: Create the fixers package**

Create `desloppify/lang/go/fixers/__init__.py`:

```python
"""Go auto-fixers for mechanical cleanup tasks."""
```

Create `desloppify/lang/go/fixers/common.py` — copy `apply_fixer`, `collapse_blank_lines`, and `find_balanced_end` from the TypeScript version, then add Go-specific helpers:

```python
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
        if brace_depth < 0:
            # We've exited the enclosing block
            return None
        if _FOR_RE.match(lines[i]) and brace_depth == 0:
            return i
    return None
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_go_fixer_common.py -v`
Expected: All 10 tests PASS

**Step 5: Commit**

```bash
git add desloppify/lang/go/fixers/__init__.py desloppify/lang/go/fixers/common.py tests/test_go_fixer_common.py
git commit -m "feat(go): scaffold fixer package with common utilities"
```

---

### Task 2: error-wrap fixer

**Files:**
- Create: `desloppify/lang/go/fixers/error_wrap.py`
- Test: `tests/test_go_fixer_error_wrap.py`

**Step 1: Write the failing test**

Create `tests/test_go_fixer_error_wrap.py`:

```python
"""Test error-wrap fixer: bare return err -> fmt.Errorf wrapping."""
import textwrap
from pathlib import Path

import pytest


@pytest.fixture
def go_file_bare_return(tmp_path):
    """Go file with bare return err."""
    content = textwrap.dedent("""\
        package main

        import "fmt"

        func processOrder(id string) error {
        \tresult, err := db.Get(id)
        \tif err != nil {
        \t\treturn err
        \t}
        \tfmt.Println(result)
        \treturn nil
        }
    """)
    f = tmp_path / "order.go"
    f.write_text(content)
    return f


@pytest.fixture
def go_file_empty_check(tmp_path):
    """Go file with if err != nil { return err }."""
    content = textwrap.dedent("""\
        package main

        func handleRequest(r *Request) error {
        \tif err := validate(r); err != nil {
        \t\treturn err
        \t}
        \tresult, err := process(r)
        \tif err != nil { return err }
        \treturn save(result)
        }
    """)
    f = tmp_path / "handler.go"
    f.write_text(content)
    return f


class TestDetectBareErrors:
    def test_detects_bare_return(self, go_file_bare_return):
        from desloppify.lang.go.fixers.error_wrap import detect_bare_errors
        entries = detect_bare_errors(go_file_bare_return.parent)
        assert len(entries) >= 1
        assert any(e["line"] == 8 for e in entries)

    def test_detects_empty_error_check(self, go_file_empty_check):
        from desloppify.lang.go.fixers.error_wrap import detect_bare_errors
        entries = detect_bare_errors(go_file_empty_check.parent)
        assert len(entries) >= 1


class TestFixErrorWrap:
    def test_wraps_bare_return(self, go_file_bare_return):
        from desloppify.lang.go.fixers.error_wrap import detect_bare_errors, fix_error_wrap
        entries = detect_bare_errors(go_file_bare_return.parent)
        results = fix_error_wrap(entries, dry_run=False)
        assert len(results) >= 1
        content = go_file_bare_return.read_text()
        assert "fmt.Errorf" in content
        assert "processOrder" in content  # function name used as context
        assert "return err\n" not in content

    def test_wraps_single_line_check(self, go_file_empty_check):
        from desloppify.lang.go.fixers.error_wrap import detect_bare_errors, fix_error_wrap
        entries = detect_bare_errors(go_file_empty_check.parent)
        results = fix_error_wrap(entries, dry_run=False)
        content = go_file_empty_check.read_text()
        assert "fmt.Errorf" in content

    def test_dry_run(self, go_file_bare_return):
        from desloppify.lang.go.fixers.error_wrap import detect_bare_errors, fix_error_wrap
        entries = detect_bare_errors(go_file_bare_return.parent)
        original = go_file_bare_return.read_text()
        results = fix_error_wrap(entries, dry_run=True)
        assert len(results) >= 1
        assert go_file_bare_return.read_text() == original
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_go_fixer_error_wrap.py -v`
Expected: FAIL — "cannot import name 'detect_bare_errors'"

**Step 3: Implement error_wrap.py**

Create `desloppify/lang/go/fixers/error_wrap.py`:

```python
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


def fix_error_wrap(entries: list[dict], *, dry_run: bool = False) -> list[dict]:
    """Replace bare `return err` with `return fmt.Errorf("<func>: %w", err)`."""
    def _transform(lines, file_entries):
        removed = []
        entry_lines = {e["line"] for e in file_entries}

        for i in range(len(lines)):
            line_num = i + 1
            if line_num not in entry_lines:
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

            # Bare: return err
            m = _BARE_RETURN_RE.match(lines[i])
            if m:
                indent = m.group(1)
                lines[i] = f'{indent}return fmt.Errorf("{func_name}: %w", err)\n'
                removed.append(f"error-wrap::{line_num}")
                continue

        return lines, removed

    return apply_fixer(entries, _transform, dry_run=dry_run)
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_go_fixer_error_wrap.py -v`
Expected: All 5 tests PASS

**Step 5: Commit**

```bash
git add desloppify/lang/go/fixers/error_wrap.py tests/test_go_fixer_error_wrap.py
git commit -m "feat(go): add error-wrap fixer for bare error returns"
```

---

### Task 3: error-strings fixer

**Files:**
- Create: `desloppify/lang/go/fixers/error_strings.py`
- Test: `tests/test_go_fixer_error_strings.py`

**Step 1: Write the failing test**

Create `tests/test_go_fixer_error_strings.py`:

```python
"""Test error-strings fixer: lowercase + strip punctuation from error strings."""
import textwrap
from pathlib import Path

import pytest


@pytest.fixture
def go_file_bad_errors(tmp_path):
    content = textwrap.dedent("""\
        package main

        import (
        \t"errors"
        \t"fmt"
        )

        func validate() error {
        \treturn errors.New("Invalid input provided.")
        }

        func process() error {
        \treturn fmt.Errorf("Connection failed: %w", err)
        }

        func other() error {
        \treturn errors.New("already lowercase")
        }
    """)
    f = tmp_path / "errs.go"
    f.write_text(content)
    return f


class TestDetectErrorStrings:
    def test_detects_capital_errors(self, go_file_bad_errors):
        from desloppify.lang.go.fixers.error_strings import detect_error_strings
        entries = detect_error_strings(go_file_bad_errors.parent)
        # Should detect "Invalid..." and "Connection..." but not "already lowercase"
        assert len(entries) >= 2
        assert all(e["line"] in (9, 13) for e in entries)


class TestFixErrorStrings:
    def test_lowercases_first_char(self, go_file_bad_errors):
        from desloppify.lang.go.fixers.error_strings import detect_error_strings, fix_error_strings
        entries = detect_error_strings(go_file_bad_errors.parent)
        fix_error_strings(entries, dry_run=False)
        content = go_file_bad_errors.read_text()
        assert 'errors.New("invalid input provided")' in content
        assert 'fmt.Errorf("connection failed: %w", err)' in content
        assert 'errors.New("already lowercase")' in content  # unchanged

    def test_dry_run(self, go_file_bad_errors):
        from desloppify.lang.go.fixers.error_strings import detect_error_strings, fix_error_strings
        entries = detect_error_strings(go_file_bad_errors.parent)
        original = go_file_bad_errors.read_text()
        fix_error_strings(entries, dry_run=True)
        assert go_file_bad_errors.read_text() == original
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_go_fixer_error_strings.py -v`
Expected: FAIL — ModuleNotFoundError

**Step 3: Implement error_strings.py**

Create `desloppify/lang/go/fixers/error_strings.py`:

```python
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
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_go_fixer_error_strings.py -v`
Expected: All 3 tests PASS

**Step 5: Commit**

```bash
git add desloppify/lang/go/fixers/error_strings.py tests/test_go_fixer_error_strings.py
git commit -m "feat(go): add error-strings fixer for Go error conventions"
```

---

### Task 4: regex-hoist fixer

**Files:**
- Create: `desloppify/lang/go/fixers/regex_hoist.py`
- Test: `tests/test_go_fixer_regex_hoist.py`

**Step 1: Write the failing test**

Create `tests/test_go_fixer_regex_hoist.py`:

```python
"""Test regex-hoist fixer: move regexp.Compile out of loops."""
import textwrap
from pathlib import Path

import pytest


@pytest.fixture
def go_file_regex_loop(tmp_path):
    content = textwrap.dedent("""\
        package main

        import "regexp"

        func process(items []string) []string {
        \tvar results []string
        \tfor _, item := range items {
        \t\tre := regexp.MustCompile(`\\d+`)
        \t\tif re.MatchString(item) {
        \t\t\tresults = append(results, item)
        \t\t}
        \t}
        \treturn results
        }
    """)
    f = tmp_path / "process.go"
    f.write_text(content)
    return f


class TestDetectRegexInLoop:
    def test_detects_regex_in_loop(self, go_file_regex_loop):
        from desloppify.lang.go.fixers.regex_hoist import detect_regex_in_loop
        entries = detect_regex_in_loop(go_file_regex_loop.parent)
        assert len(entries) == 1
        assert entries[0]["line"] == 8


class TestFixRegexHoist:
    def test_hoists_above_loop(self, go_file_regex_loop):
        from desloppify.lang.go.fixers.regex_hoist import detect_regex_in_loop, fix_regex_hoist
        entries = detect_regex_in_loop(go_file_regex_loop.parent)
        fix_regex_hoist(entries, dry_run=False)
        content = go_file_regex_loop.read_text()
        lines = content.splitlines()
        # MustCompile should appear before the for loop
        compile_line = next(i for i, l in enumerate(lines) if "MustCompile" in l)
        for_line = next(i for i, l in enumerate(lines) if "for " in l)
        assert compile_line < for_line
        # Inside the loop, re should still be used
        assert "re.MatchString" in content

    def test_dry_run(self, go_file_regex_loop):
        from desloppify.lang.go.fixers.regex_hoist import detect_regex_in_loop, fix_regex_hoist
        entries = detect_regex_in_loop(go_file_regex_loop.parent)
        original = go_file_regex_loop.read_text()
        fix_regex_hoist(entries, dry_run=True)
        assert go_file_regex_loop.read_text() == original
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_go_fixer_regex_hoist.py -v`
Expected: FAIL — ModuleNotFoundError

**Step 3: Implement regex_hoist.py**

Create `desloppify/lang/go/fixers/regex_hoist.py`:

```python
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

            m = _REGEX_ASSIGN_RE.match(lines[idx])
            if not m:
                continue

            var_name = m.group(2)
            regex_call = m.group(3)

            for_idx = find_enclosing_for(lines, idx)
            if for_idx is None:
                continue

            # Determine indentation of the for loop
            for_indent = len(lines[for_idx]) - len(lines[for_idx].lstrip())
            hoist_indent = "\t" * (for_indent // len("\t")) if "\t" in lines[for_idx] else " " * for_indent

            # Remove the line from inside the loop
            lines[idx] = ""

            # Insert above the for loop
            hoist_line = f"{hoist_indent}{var_name} := {regex_call}\n"
            lines.insert(for_idx, hoist_line)

            removed.append(f"regex-hoist::{entry['line']}")

        # Clean up empty lines
        lines = [l for l in lines if l != ""]
        return lines, removed

    return apply_fixer(entries, _transform, dry_run=dry_run)
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_go_fixer_regex_hoist.py -v`
Expected: All 3 tests PASS

**Step 5: Commit**

```bash
git add desloppify/lang/go/fixers/regex_hoist.py tests/test_go_fixer_regex_hoist.py
git commit -m "feat(go): add regex-hoist fixer for regexp.Compile in loops"
```

---

### Task 5: string-builder fixer

**Files:**
- Create: `desloppify/lang/go/fixers/string_builder.py`
- Test: `tests/test_go_fixer_string_builder.py`

**Step 1: Write the failing test**

Create `tests/test_go_fixer_string_builder.py`:

```python
"""Test string-builder fixer: replace += concat with strings.Builder."""
import textwrap
from pathlib import Path

import pytest


@pytest.fixture
def go_file_concat_loop(tmp_path):
    content = textwrap.dedent("""\
        package main

        func buildCSV(items []string) string {
        \tresult := ""
        \tfor _, item := range items {
        \t\tresult += item + ","
        \t}
        \treturn result
        }
    """)
    f = tmp_path / "csv.go"
    f.write_text(content)
    return f


class TestDetectStringConcat:
    def test_detects_concat_in_loop(self, go_file_concat_loop):
        from desloppify.lang.go.fixers.string_builder import detect_string_concat
        entries = detect_string_concat(go_file_concat_loop.parent)
        assert len(entries) == 1
        assert entries[0]["line"] == 6


class TestFixStringBuilder:
    def test_replaces_with_builder(self, go_file_concat_loop):
        from desloppify.lang.go.fixers.string_builder import detect_string_concat, fix_string_builder
        entries = detect_string_concat(go_file_concat_loop.parent)
        fix_string_builder(entries, dry_run=False)
        content = go_file_concat_loop.read_text()
        assert "strings.Builder" in content
        assert "WriteString" in content
        # The += should be gone from loop body
        lines = content.splitlines()
        for_started = False
        for line in lines:
            if "for " in line:
                for_started = True
            if for_started and "+=" in line:
                pytest.fail(f"Found += in loop body: {line}")
            if for_started and "}" in line and "for" not in line:
                break

    def test_dry_run(self, go_file_concat_loop):
        from desloppify.lang.go.fixers.string_builder import detect_string_concat, fix_string_builder
        entries = detect_string_concat(go_file_concat_loop.parent)
        original = go_file_concat_loop.read_text()
        fix_string_builder(entries, dry_run=True)
        assert go_file_concat_loop.read_text() == original
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_go_fixer_string_builder.py -v`
Expected: FAIL — ModuleNotFoundError

**Step 3: Implement string_builder.py**

Create `desloppify/lang/go/fixers/string_builder.py`:

```python
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
                # Adjust indices since we inserted a line
                idx += 1

                # Find the end of the for loop to insert .String()
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

                # Insert assignment after loop
                assign_line = f"{for_indent}{var_name} = sb.String()\n"
                lines.insert(loop_end + 1, assign_line)

        return lines, removed

    return apply_fixer(entries, _transform, dry_run=dry_run)
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_go_fixer_string_builder.py -v`
Expected: All 3 tests PASS

**Step 5: Commit**

```bash
git add desloppify/lang/go/fixers/string_builder.py tests/test_go_fixer_string_builder.py
git commit -m "feat(go): add string-builder fixer for concat in loops"
```

---

### Task 6: mutex-pointer fixer

**Files:**
- Create: `desloppify/lang/go/fixers/mutex_pointer.py`
- Test: `tests/test_go_fixer_mutex_pointer.py`

**Step 1: Write the failing test**

Create `tests/test_go_fixer_mutex_pointer.py`:

```python
"""Test mutex-pointer fixer: change sync.Mutex value param to pointer."""
import textwrap
from pathlib import Path

import pytest


@pytest.fixture
def go_file_mutex_copy(tmp_path):
    content = textwrap.dedent("""\
        package main

        import "sync"

        func withLock(mu sync.Mutex) {
        \tmu.Lock()
        \tdefer mu.Unlock()
        }

        func alreadyPointer(mu *sync.Mutex) {
        \tmu.Lock()
        \tdefer mu.Unlock()
        }

        func multiParam(name string, mu sync.Mutex, count int) {
        \tmu.Lock()
        \tdefer mu.Unlock()
        }
    """)
    f = tmp_path / "lock.go"
    f.write_text(content)
    return f


class TestDetectMutexCopy:
    def test_detects_value_mutex(self, go_file_mutex_copy):
        from desloppify.lang.go.fixers.mutex_pointer import detect_mutex_copy
        entries = detect_mutex_copy(go_file_mutex_copy.parent)
        # Should detect lines 5 and 15, not line 10 (already pointer)
        lines = {e["line"] for e in entries}
        assert 5 in lines
        assert 15 in lines
        assert 10 not in lines


class TestFixMutexPointer:
    def test_adds_pointer(self, go_file_mutex_copy):
        from desloppify.lang.go.fixers.mutex_pointer import detect_mutex_copy, fix_mutex_pointer
        entries = detect_mutex_copy(go_file_mutex_copy.parent)
        fix_mutex_pointer(entries, dry_run=False)
        content = go_file_mutex_copy.read_text()
        assert "mu *sync.Mutex" in content
        # The already-pointer one should be unchanged
        assert content.count("*sync.Mutex") == 3  # two fixed + one original

    def test_dry_run(self, go_file_mutex_copy):
        from desloppify.lang.go.fixers.mutex_pointer import detect_mutex_copy, fix_mutex_pointer
        entries = detect_mutex_copy(go_file_mutex_copy.parent)
        original = go_file_mutex_copy.read_text()
        fix_mutex_pointer(entries, dry_run=True)
        assert go_file_mutex_copy.read_text() == original
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_go_fixer_mutex_pointer.py -v`
Expected: FAIL — ModuleNotFoundError

**Step 3: Implement mutex_pointer.py**

Create `desloppify/lang/go/fixers/mutex_pointer.py`:

```python
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
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_go_fixer_mutex_pointer.py -v`
Expected: All 3 tests PASS

**Step 5: Commit**

```bash
git add desloppify/lang/go/fixers/mutex_pointer.py tests/test_go_fixer_mutex_pointer.py
git commit -m "feat(go): add mutex-pointer fixer for sync.Mutex by value"
```

---

### Task 7: Register fixers in GoConfig and update exports

**Files:**
- Modify: `desloppify/lang/go/__init__.py` (the `fixers={}` in GoConfig)
- Modify: `desloppify/lang/go/fixers/__init__.py` (exports)
- Test: `tests/test_go_fixer_registration.py`

**Step 1: Write the failing test**

Create `tests/test_go_fixer_registration.py`:

```python
"""Test Go fixer registration in GoConfig."""
import pytest

from desloppify.lang import get_lang


class TestGoFixerRegistration:
    def test_fixers_registered(self):
        lang = get_lang("go")
        assert len(lang.fixers) == 5

    def test_expected_fixer_names(self):
        lang = get_lang("go")
        expected = {"error-wrap", "error-strings", "regex-hoist",
                    "string-builder", "mutex-pointer"}
        assert set(lang.fixers.keys()) == expected

    def test_all_fixers_have_required_fields(self):
        lang = get_lang("go")
        for name, fc in lang.fixers.items():
            assert fc.label, f"{name} missing label"
            assert callable(fc.detect), f"{name} missing detect"
            assert callable(fc.fix), f"{name} missing fix"
            assert fc.detector, f"{name} missing detector"

    def test_fixer_detect_callable(self, tmp_path, monkeypatch):
        """Each fixer's detect function runs without error on empty project."""
        import desloppify.utils as utils_mod
        monkeypatch.setattr(utils_mod, "PROJECT_ROOT", tmp_path)
        import desloppify.lang.base as base_mod
        monkeypatch.setattr(base_mod, "PROJECT_ROOT", tmp_path)
        utils_mod._find_source_files_cached.cache_clear()
        (tmp_path / "go.mod").write_text("module test\n\ngo 1.21\n")
        (tmp_path / "main.go").write_text("package main\n\nfunc main() {}\n")

        lang = get_lang("go")
        for name, fc in lang.fixers.items():
            entries = fc.detect(tmp_path)
            assert isinstance(entries, list), f"{name} detect didn't return list"
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_go_fixer_registration.py -v`
Expected: FAIL — `assert len(lang.fixers) == 5` fails (currently 0)

**Step 3: Wire up registration**

Update `desloppify/lang/go/fixers/__init__.py`:

```python
"""Go auto-fixers for mechanical cleanup tasks."""

from .error_wrap import detect_bare_errors, fix_error_wrap
from .error_strings import detect_error_strings, fix_error_strings
from .regex_hoist import detect_regex_in_loop, fix_regex_hoist
from .string_builder import detect_string_concat, fix_string_builder
from .mutex_pointer import detect_mutex_copy, fix_mutex_pointer

__all__ = [
    "detect_bare_errors", "fix_error_wrap",
    "detect_error_strings", "fix_error_strings",
    "detect_regex_in_loop", "fix_regex_hoist",
    "detect_string_concat", "fix_string_builder",
    "detect_mutex_copy", "fix_mutex_pointer",
]
```

Update `desloppify/lang/go/__init__.py` — change `fixers={}` to:

```python
from ..base import FixerConfig
# ... in GoConfig.__init__:
fixers={
    "error-wrap": FixerConfig(
        label="bare error returns",
        detect=lambda path: __import__(
            "desloppify.lang.go.fixers.error_wrap",
            fromlist=["detect_bare_errors"]).detect_bare_errors(path),
        fix=lambda entries, **kw: __import__(
            "desloppify.lang.go.fixers.error_wrap",
            fromlist=["fix_error_wrap"]).fix_error_wrap(entries, **kw),
        detector="smells",
        verb="Wrapped", dry_verb="Would wrap",
    ),
    "error-strings": FixerConfig(
        label="error string format",
        detect=lambda path: __import__(
            "desloppify.lang.go.fixers.error_strings",
            fromlist=["detect_error_strings"]).detect_error_strings(path),
        fix=lambda entries, **kw: __import__(
            "desloppify.lang.go.fixers.error_strings",
            fromlist=["fix_error_strings"]).fix_error_strings(entries, **kw),
        detector="smells",
        verb="Fixed", dry_verb="Would fix",
    ),
    "regex-hoist": FixerConfig(
        label="regex in loop",
        detect=lambda path: __import__(
            "desloppify.lang.go.fixers.regex_hoist",
            fromlist=["detect_regex_in_loop"]).detect_regex_in_loop(path),
        fix=lambda entries, **kw: __import__(
            "desloppify.lang.go.fixers.regex_hoist",
            fromlist=["fix_regex_hoist"]).fix_regex_hoist(entries, **kw),
        detector="smells",
        verb="Hoisted", dry_verb="Would hoist",
    ),
    "string-builder": FixerConfig(
        label="string concat in loop",
        detect=lambda path: __import__(
            "desloppify.lang.go.fixers.string_builder",
            fromlist=["detect_string_concat"]).detect_string_concat(path),
        fix=lambda entries, **kw: __import__(
            "desloppify.lang.go.fixers.string_builder",
            fromlist=["fix_string_builder"]).fix_string_builder(entries, **kw),
        detector="smells",
        verb="Replaced", dry_verb="Would replace",
    ),
    "mutex-pointer": FixerConfig(
        label="mutex by value",
        detect=lambda path: __import__(
            "desloppify.lang.go.fixers.mutex_pointer",
            fromlist=["detect_mutex_copy"]).detect_mutex_copy(path),
        fix=lambda entries, **kw: __import__(
            "desloppify.lang.go.fixers.mutex_pointer",
            fromlist=["fix_mutex_pointer"]).fix_mutex_pointer(entries, **kw),
        detector="smells",
        verb="Fixed", dry_verb="Would fix",
    ),
},
```

Also add `FixerConfig` to the imports at top of `__init__.py`:

```python
from ..base import (DetectorPhase, FixerConfig, LangConfig,
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_go_fixer_registration.py -v`
Expected: All 4 tests PASS

**Step 5: Run full test suite**

Run: `pytest --tb=short -q`
Expected: All tests pass (existing + new)

**Step 6: Commit**

```bash
git add desloppify/lang/go/__init__.py desloppify/lang/go/fixers/__init__.py tests/test_go_fixer_registration.py
git commit -m "feat(go): register 5 fixers in GoConfig"
```

---

### Task 8: Integration test — run fixers against synthetic Go project

**Files:**
- Create: `tests/test_go_fixer_integration.py`

**Step 1: Write the integration test**

Create `tests/test_go_fixer_integration.py`:

```python
"""End-to-end integration test: detect smells, fix them, verify fixed."""
import textwrap
from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def _set_project_root(tmp_path, monkeypatch):
    import desloppify.utils as utils_mod
    monkeypatch.setattr(utils_mod, "PROJECT_ROOT", tmp_path)
    import desloppify.detectors.large as large_mod
    monkeypatch.setattr(large_mod, "PROJECT_ROOT", tmp_path)
    import desloppify.lang.base as base_mod
    monkeypatch.setattr(base_mod, "PROJECT_ROOT", tmp_path)
    utils_mod._find_source_files_cached.cache_clear()


def _create_fixable_project(tmp_path):
    """Create a Go project with known fixable issues."""
    (tmp_path / "go.mod").write_text("module example.com/test\n\ngo 1.21\n")

    (tmp_path / "service.go").write_text(textwrap.dedent("""\
        package main

        import (
        \t"errors"
        \t"fmt"
        \t"regexp"
        \t"sync"
        )

        func processItem(id string) error {
        \tresult, err := fetch(id)
        \tif err != nil {
        \t\treturn err
        \t}
        \tfmt.Println(result)
        \treturn nil
        }

        func validate() error {
        \treturn errors.New("Invalid input provided.")
        }

        func search(items []string) []string {
        \tvar results []string
        \tfor _, item := range items {
        \t\tre := regexp.MustCompile(`\\d+`)
        \t\tif re.MatchString(item) {
        \t\t\tresults = append(results, item)
        \t\t}
        \t}
        \treturn results
        }

        func buildCSV(items []string) string {
        \tresult := ""
        \tfor _, item := range items {
        \t\tresult += item + ","
        \t}
        \treturn result
        }

        func withLock(mu sync.Mutex) {
        \tmu.Lock()
        \tdefer mu.Unlock()
        }
    """))
    return tmp_path


class TestGoFixerIntegration:
    def test_all_fixers_detect(self, tmp_path):
        """Every registered fixer can detect entries from the test project."""
        _create_fixable_project(tmp_path)
        from desloppify.lang import get_lang
        lang = get_lang("go")
        detected = {}
        for name, fc in lang.fixers.items():
            entries = fc.detect(tmp_path)
            detected[name] = len(entries)
        # Each fixer should find at least one issue
        for name, count in detected.items():
            assert count > 0, f"Fixer {name} detected 0 entries"

    def test_all_fixers_fix_dry_run(self, tmp_path):
        """All fixers produce results in dry-run mode without changing files."""
        _create_fixable_project(tmp_path)
        original = (tmp_path / "service.go").read_text()
        from desloppify.lang import get_lang
        lang = get_lang("go")
        for name, fc in lang.fixers.items():
            entries = fc.detect(tmp_path)
            results = fc.fix(entries, dry_run=True)
            assert isinstance(results, list), f"{name} fix didn't return list"
        assert (tmp_path / "service.go").read_text() == original

    def test_fixers_modify_files(self, tmp_path):
        """Each fixer actually modifies the source file."""
        _create_fixable_project(tmp_path)
        original = (tmp_path / "service.go").read_text()
        from desloppify.lang import get_lang
        lang = get_lang("go")
        total_fixed = 0
        for name, fc in lang.fixers.items():
            entries = fc.detect(tmp_path)
            results = fc.fix(entries, dry_run=False)
            total_fixed += sum(len(r["removed"]) for r in results)
        assert total_fixed >= 5
        assert (tmp_path / "service.go").read_text() != original
```

**Step 2: Run test**

Run: `pytest tests/test_go_fixer_integration.py -v`
Expected: All 3 tests PASS

**Step 3: Run full test suite**

Run: `pytest --tb=short -q`
Expected: All tests pass

**Step 4: Commit**

```bash
git add tests/test_go_fixer_integration.py
git commit -m "test(go): add end-to-end fixer integration test"
```

---

### Task 9: Push and validate

**Step 1: Run full test suite one final time**

Run: `pytest --tb=short -q`
Expected: All tests pass

**Step 2: Push to remote**

```bash
git push origin main
```

**Step 3: Validate against real Go repo (optional)**

Clone gw-api to /tmp, run each fixer in dry-run mode, verify no crashes:

```python
from desloppify.lang import get_lang
from pathlib import Path

lang = get_lang("go")
path = Path("/tmp/gw-api-test")
for name, fc in lang.fixers.items():
    entries = fc.detect(path)
    results = fc.fix(entries, dry_run=True)
    print(f"{name}: {len(entries)} detected, {len(results)} fixable")
```
