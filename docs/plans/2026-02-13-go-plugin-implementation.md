# Go Language Plugin Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add Go language support to desloppify as a plugin under `desloppify/lang/go/`

**Architecture:** Hybrid approach — Go helper binary for AST extraction, standard Go tools (`go list`, `go vet`) for deps/unused, regex fallback. Per-repo config via `.desloppify/go.yaml`.

**Tech Stack:** Python 3.10+, Go 1.21+, pytest, go/ast

---

### Task 1: Scaffold plugin directory structure

**Files:**
- Create: `desloppify/lang/go/__init__.py`
- Create: `desloppify/lang/go/commands.py`
- Create: `desloppify/lang/go/extractors.py`
- Create: `desloppify/lang/go/detectors/__init__.py`
- Create: `desloppify/lang/go/detectors/smells.py`
- Create: `desloppify/lang/go/detectors/deps.py`
- Create: `desloppify/lang/go/detectors/unused.py`
- Create: `desloppify/lang/go/detectors/complexity.py`
- Create: `desloppify/lang/go/fixers/__init__.py`
- Test: `tests/test_go_registration.py`

**Step 1: Write the failing test**

```python
# tests/test_go_registration.py
"""Test that the Go language plugin registers and validates correctly."""
import pytest
from desloppify.lang import get_lang, available_langs, auto_detect_lang


class TestGoRegistration:
    def test_go_in_available_langs(self):
        langs = available_langs()
        assert "go" in langs

    def test_get_lang_returns_config(self):
        lang = get_lang("go")
        assert lang.name == "go"
        assert lang.extensions == [".go"]
        assert lang.default_src == "."

    def test_auto_detect_with_go_mod(self, tmp_path):
        (tmp_path / "go.mod").write_text("module example.com/test\n\ngo 1.21\n")
        (tmp_path / "main.go").write_text("package main\n")
        from unittest.mock import patch
        import desloppify.utils as utils_mod
        with patch.object(utils_mod, "PROJECT_ROOT", tmp_path):
            result = auto_detect_lang(tmp_path)
        assert result == "go"
```

**Step 2: Run test to verify it fails**

Run: `cd /Users/josef.salyer/projects/atat/desloppify && python -m pytest tests/test_go_registration.py -v`
Expected: FAIL — module not found

**Step 3: Create the directory structure with minimal files**

Create all directories and files. The key file is `desloppify/lang/go/__init__.py` with a minimal GoConfig:

```python
# desloppify/lang/go/__init__.py
"""Go language configuration for desloppify."""
from __future__ import annotations

from pathlib import Path

from .. import register_lang
from ..base import DetectorPhase, LangConfig, phase_dupes
from ...detectors.base import ComplexitySignal, GodRule
from ...utils import find_source_files, log
from ...zones import ZoneRule, Zone, COMMON_ZONE_RULES


def find_go_files(path: str | Path) -> list[str]:
    """Find all .go files under a path, excluding test files."""
    return find_source_files(path, [".go"])


# ── Zone classification rules ──
GO_ZONE_RULES = [
    ZoneRule(Zone.GENERATED, [".pb.go", "_pb2.go", "_string.go"]),
    ZoneRule(Zone.TEST, ["_test.go", "/testdata/", "/testutil/"]),
    ZoneRule(Zone.CONFIG, ["go.mod", "go.sum"]),
] + COMMON_ZONE_RULES

GO_ENTRY_PATTERNS = [
    "main.go", "/cmd/", "_test.go", "/testdata/",
    "/lambda/", "handler.go", "/migrations/",
    ".pb.go", "_gen.go", "_mock.go", "doc.go",
]

GO_EXCLUSIONS = ["vendor", ".git", "testdata", "bin"]


def _get_go_area(filepath: str) -> str:
    """Derive area name from Go file path for grouping."""
    parts = filepath.split("/")
    if len(parts) > 2:
        return "/".join(parts[:2])
    return parts[0] if parts else filepath


def _go_build_dep_graph(path: Path) -> dict:
    from .detectors.deps import build_dep_graph
    return build_dep_graph(path)


def _go_extract_functions(path: Path) -> list:
    from .extractors import extract_go_functions
    functions = []
    for filepath in find_go_files(path):
        functions.extend(extract_go_functions(filepath))
    return functions


@register_lang("go")
class GoConfig(LangConfig):
    def __init__(self):
        from .commands import get_detect_commands
        super().__init__(
            name="go",
            extensions=[".go"],
            exclusions=GO_EXCLUSIONS,
            default_src=".",
            build_dep_graph=_go_build_dep_graph,
            entry_patterns=GO_ENTRY_PATTERNS,
            barrel_names=set(),
            phases=[],  # Added in later tasks
            fixers={},
            get_area=_get_go_area,
            detect_commands=get_detect_commands(),
            boundaries=[],
            typecheck_cmd="",
            file_finder=find_go_files,
            large_threshold=500,
            complexity_threshold=20,
            extract_functions=_go_extract_functions,
            zone_rules=GO_ZONE_RULES,
        )
```

Stub files:

```python
# desloppify/lang/go/commands.py
"""Go detector CLI commands."""


def get_detect_commands() -> dict[str, callable]:
    """Build the Go detector command registry."""
    return {}
```

```python
# desloppify/lang/go/extractors.py
"""Go source code extraction — AST helper with regex fallback."""
from __future__ import annotations

from pathlib import Path

from ...detectors.base import FunctionInfo, ClassInfo


def extract_go_functions(filepath: Path) -> list[FunctionInfo]:
    """Extract all functions from a Go file."""
    return _extract_functions_regex(filepath)


def extract_go_structs(filepath: Path | str) -> list[ClassInfo]:
    """Extract all structs from a Go file."""
    return _extract_structs_regex(filepath)


def _extract_functions_regex(filepath: Path) -> list[FunctionInfo]:
    """Regex-based Go function extraction (fallback)."""
    return []


def _extract_structs_regex(filepath: Path | str) -> list[ClassInfo]:
    """Regex-based Go struct extraction (fallback)."""
    return []
```

```python
# desloppify/lang/go/detectors/__init__.py
"""Go-specific detectors."""
```

```python
# desloppify/lang/go/detectors/smells.py
"""Go code smell detection."""


def detect_smells(path):
    """Detect Go code smells. Returns (entries, file_count)."""
    return [], 0
```

```python
# desloppify/lang/go/detectors/deps.py
"""Go dependency graph builder."""
from collections import defaultdict
from pathlib import Path


def build_dep_graph(path: Path) -> dict:
    """Build a dependency graph for Go files."""
    return {}
```

```python
# desloppify/lang/go/detectors/unused.py
"""Go unused detection via go vet + gopls."""
from pathlib import Path


def detect_unused(path: Path, category: str = "all") -> tuple[list[dict], int]:
    """Detect unused imports and variables."""
    return [], 0
```

```python
# desloppify/lang/go/detectors/complexity.py
"""Go-specific complexity signal compute functions."""


def compute_max_params(content: str, lines: list[str]):
    """Compute max parameter count across Go functions."""
    return None


def compute_nesting_depth(content: str, lines: list[str]):
    """Compute max nesting depth."""
    return None


def compute_long_functions(content: str, lines: list[str]):
    """Compute longest function LOC."""
    return None
```

```python
# desloppify/lang/go/fixers/__init__.py
"""Go auto-fixers (not yet implemented)."""
```

**Step 4: Run test to verify it passes**

Run: `cd /Users/josef.salyer/projects/atat/desloppify && python -m pytest tests/test_go_registration.py -v`
Expected: PASS (3 tests)

**Step 5: Commit**

```bash
git add desloppify/lang/go/ tests/test_go_registration.py
git commit -m "feat(go): scaffold Go language plugin with registration"
```

---

### Task 2: Implement regex-based Go function extraction

**Files:**
- Modify: `desloppify/lang/go/extractors.py`
- Test: `tests/test_go_extractors.py`

**Step 1: Write the failing test**

```python
# tests/test_go_extractors.py
"""Test Go function and struct extraction."""
import textwrap
from pathlib import Path

import pytest

from desloppify.lang.go.extractors import extract_go_functions, extract_go_structs


def _write_go(tmp_path: Path, code: str, filename: str = "main.go") -> Path:
    f = tmp_path / filename
    f.write_text(textwrap.dedent(code))
    return f


class TestExtractGoFunctions:
    def test_simple_function(self, tmp_path):
        f = _write_go(tmp_path, """\
            package main

            func Hello(name string) string {
            \treturn "Hello, " + name
            }
        """)
        funcs = extract_go_functions(f)
        assert len(funcs) == 1
        assert funcs[0].name == "Hello"
        assert funcs[0].params == ["name"]
        assert funcs[0].loc >= 2

    def test_method_with_receiver(self, tmp_path):
        f = _write_go(tmp_path, """\
            package main

            type Server struct{}

            func (s *Server) Start() error {
            \treturn nil
            }
        """)
        funcs = extract_go_functions(f)
        assert len(funcs) == 1
        assert funcs[0].name == "Start"

    def test_multiline_params(self, tmp_path):
        f = _write_go(tmp_path, """\
            package main

            func Create(
            \tctx context.Context,
            \tname string,
            \tage int,
            ) error {
            \treturn nil
            }
        """)
        funcs = extract_go_functions(f)
        assert len(funcs) == 1
        assert "ctx" in funcs[0].params

    def test_empty_file(self, tmp_path):
        f = _write_go(tmp_path, "package main\n")
        funcs = extract_go_functions(f)
        assert funcs == []


class TestExtractGoStructs:
    def test_simple_struct(self, tmp_path):
        f = _write_go(tmp_path, """\
            package main

            type User struct {
            \tName  string
            \tEmail string
            \tAge   int
            }
        """)
        structs = extract_go_structs(f)
        assert len(structs) == 1
        assert structs[0].name == "User"
        assert len(structs[0].attributes) == 3
        assert "Name" in structs[0].attributes

    def test_struct_with_embedded(self, tmp_path):
        f = _write_go(tmp_path, """\
            package main

            type Admin struct {
            \tUser
            \tRole string
            }
        """)
        structs = extract_go_structs(f)
        assert len(structs) == 1
        assert "User" in structs[0].base_classes
```

**Step 2: Run test to verify it fails**

Run: `cd /Users/josef.salyer/projects/atat/desloppify && python -m pytest tests/test_go_extractors.py -v`
Expected: FAIL — functions return empty lists

**Step 3: Implement regex extraction in extractors.py**

Replace `_extract_functions_regex` and `_extract_structs_regex` in `desloppify/lang/go/extractors.py` with real regex parsing:

- Function pattern: `^func\s+(?:\([^)]+\)\s+)?(\w+)\s*\(` — captures function name, handles receiver
- Track brace depth to find function end
- Extract params from signature between parens
- Struct pattern: `^type\s+(\w+)\s+struct\s*\{` — captures struct name
- Extract fields and embedded types from struct body
- Compute body hash via hashlib for duplicate detection
- Build normalized body (whitespace-collapsed) for near-dupe matching

The implementation should populate all FunctionInfo and ClassInfo fields that the detectors need.

**Step 4: Run test to verify it passes**

Run: `cd /Users/josef.salyer/projects/atat/desloppify && python -m pytest tests/test_go_extractors.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add desloppify/lang/go/extractors.py tests/test_go_extractors.py
git commit -m "feat(go): implement regex-based function and struct extraction"
```
### Task 3: Implement Go helper binary (cmd/go-extract)

**Files:**
- Create: `cmd/go-extract/go.mod`
- Create: `cmd/go-extract/main.go`
- Create: `cmd/go-extract/extract.go`
- Create: `cmd/go-extract/extract_test.go`

**Step 1: Write Go test for extraction**

```go
// cmd/go-extract/extract_test.go
package main

import (
	"os"
	"path/filepath"
	"testing"
)

func TestExtractFunctions(t *testing.T) {
	dir := t.TempDir()
	src := filepath.Join(dir, "main.go")
	os.WriteFile(src, []byte(`package main

func Hello(name string) string {
	return "Hello, " + name
}

func (s *Server) Start(ctx context.Context) error {
	return nil
}
`), 0644)

	result, err := extractFile(src)
	if err != nil {
		t.Fatalf("extractFile failed: %v", err)
	}
	if len(result.Functions) != 2 {
		t.Fatalf("expected 2 functions, got %d", len(result.Functions))
	}
	if result.Functions[0].Name != "Hello" {
		t.Errorf("expected Hello, got %s", result.Functions[0].Name)
	}
	if result.Functions[1].Receiver != "Server" {
		t.Errorf("expected receiver Server, got %s", result.Functions[1].Receiver)
	}
}

func TestExtractStructs(t *testing.T) {
	dir := t.TempDir()
	src := filepath.Join(dir, "types.go")
	os.WriteFile(src, []byte(`package main

type User struct {
	Name  string
	Email string
}

type Admin struct {
	User
	Role string
}
`), 0644)

	result, err := extractFile(src)
	if err != nil {
		t.Fatalf("extractFile failed: %v", err)
	}
	if len(result.Structs) != 2 {
		t.Fatalf("expected 2 structs, got %d", len(result.Structs))
	}
	if result.Structs[0].Name != "User" {
		t.Errorf("expected User, got %s", result.Structs[0].Name)
	}
	if len(result.Structs[0].Fields) != 2 {
		t.Errorf("expected 2 fields, got %d", len(result.Structs[0].Fields))
	}
}
```

**Step 2: Run test to verify it fails**

Run: `cd /Users/josef.salyer/projects/atat/desloppify/cmd/go-extract && go test -v`
Expected: FAIL — functions not implemented

**Step 3: Implement go.mod and extraction code**

`cmd/go-extract/go.mod`:
```go
module github.com/josefsalyer/desloppify/cmd/go-extract

go 1.21
```

`cmd/go-extract/main.go`:
```go
package main

import (
	"encoding/json"
	"fmt"
	"os"
)

type ExtractResult struct {
	Functions  []FunctionInfo  `json:"functions"`
	Structs    []StructInfo    `json:"structs"`
	Interfaces []InterfaceInfo `json:"interfaces"`
}

type FunctionInfo struct {
	Name     string   `json:"name"`
	File     string   `json:"file"`
	Line     int      `json:"line"`
	EndLine  int      `json:"end_line"`
	LOC      int      `json:"loc"`
	Body     string   `json:"body"`
	Params   []string `json:"params"`
	Receiver string   `json:"receiver,omitempty"`
	Exported bool     `json:"exported"`
}

type StructInfo struct {
	Name     string   `json:"name"`
	File     string   `json:"file"`
	Line     int      `json:"line"`
	LOC      int      `json:"loc"`
	Methods  []string `json:"methods"`
	Fields   []string `json:"fields"`
	Embedded []string `json:"embedded"`
	Exported bool     `json:"exported"`
}

type InterfaceInfo struct {
	Name    string   `json:"name"`
	File    string   `json:"file"`
	Line    int      `json:"line"`
	Methods []string `json:"methods"`
}

func main() {
	if len(os.Args) < 2 {
		fmt.Fprintf(os.Stderr, "usage: go-extract <file|dir> [...]\n")
		os.Exit(1)
	}

	combined := ExtractResult{}
	for _, arg := range os.Args[1:] {
		result, err := extractFile(arg)
		if err != nil {
			fmt.Fprintf(os.Stderr, "warning: %s: %v\n", arg, err)
			continue
		}
		combined.Functions = append(combined.Functions, result.Functions...)
		combined.Structs = append(combined.Structs, result.Structs...)
		combined.Interfaces = append(combined.Interfaces, result.Interfaces...)
	}

	enc := json.NewEncoder(os.Stdout)
	enc.SetIndent("", "  ")
	enc.Encode(combined)
}
```

`cmd/go-extract/extract.go` — uses `go/ast` and `go/parser` to:
- Parse each file with `parser.ParseFile`
- Walk AST for `*ast.FuncDecl` nodes → extract name, receiver, params, line range, body text
- Walk for `*ast.GenDecl` with `token.TYPE` specs → extract struct fields, embedded types
- Walk for `*ast.InterfaceType` → extract interface methods
- Return `ExtractResult` with all three slices populated

**Step 4: Run Go tests**

Run: `cd /Users/josef.salyer/projects/atat/desloppify/cmd/go-extract && go test -v`
Expected: PASS

**Step 5: Wire Go helper into Python extractors**

Update `desloppify/lang/go/extractors.py` to try calling the Go helper before falling back to regex. Add `_try_go_helper(filepath)` that:
1. Checks for `go-extract` binary on PATH
2. Falls back to `go run cmd/go-extract/main.go <filepath>`
3. Parses JSON output into `FunctionInfo`/`ClassInfo` lists
4. Returns None if Go not available (triggers regex fallback)

**Step 6: Run Python tests**

Run: `cd /Users/josef.salyer/projects/atat/desloppify && python -m pytest tests/test_go_extractors.py -v`
Expected: PASS (Go helper used if Go installed, regex fallback otherwise)

**Step 7: Commit**

```bash
git add cmd/go-extract/ desloppify/lang/go/extractors.py
git commit -m "feat(go): add go-extract AST helper binary with Python integration"
```

---

### Task 4: Implement Go smell detection (18 rules)

**Files:**
- Modify: `desloppify/lang/go/detectors/smells.py`
- Test: `tests/test_go_smells.py`

**Step 1: Write failing tests for regex-based smells**

```python
# tests/test_go_smells.py
"""Test Go code smell detection."""
import textwrap
from pathlib import Path

import pytest

from desloppify.lang.go.detectors.smells import detect_smells


def _write_go(tmp_path: Path, code: str, filename: str = "main.go") -> Path:
    f = tmp_path / filename
    f.write_text(textwrap.dedent(code))
    return tmp_path


def _smell_ids(entries: list[dict]) -> set[str]:
    return {e["id"] for e in entries}


class TestIgnoredError:
    def test_detected(self, tmp_path):
        path = _write_go(tmp_path, """\
            package main
            func foo() {
            \t_ = doSomething()
            }
        """)
        entries, count = detect_smells(path)
        assert "ignored_error" in _smell_ids(entries)

    def test_not_for_range(self, tmp_path):
        path = _write_go(tmp_path, """\
            package main
            func foo() {
            \tfor _, v := range items {
            \t\t_ = v
            \t}
            }
        """)
        entries, _ = detect_smells(path)
        ids = _smell_ids(entries)
        # Range blank identifiers are idiomatic, not errors
        assert "ignored_error" not in ids


class TestTodoFixme:
    def test_detected(self, tmp_path):
        path = _write_go(tmp_path, """\
            package main
            // TODO: fix this later
            func foo() {}
        """)
        entries, _ = detect_smells(path)
        assert "todo_fixme" in _smell_ids(entries)


class TestMonsterFunction:
    def test_detected(self, tmp_path):
        body = "\n".join(f"\tx_{i} := {i}" for i in range(160))
        code = f"package main\n\nfunc monster() {{\n{body}\n}}\n"
        path = _write_go(tmp_path, code)
        entries, _ = detect_smells(path)
        assert "monster_function" in _smell_ids(entries)


class TestBareGoroutine:
    def test_detected(self, tmp_path):
        path = _write_go(tmp_path, """\
            package main
            func foo() {
            \tgo func() {
            \t\tdoWork()
            \t}()
            }
        """)
        entries, _ = detect_smells(path)
        assert "bare_goroutine" in _smell_ids(entries)


class TestHardcodedUrl:
    def test_detected(self, tmp_path):
        path = _write_go(tmp_path, """\
            package main
            var endpoint = "https://api.example.com/v1"
        """)
        entries, _ = detect_smells(path)
        assert "hardcoded_url" in _smell_ids(entries)


class TestErrorNoWrap:
    def test_detected(self, tmp_path):
        path = _write_go(tmp_path, """\
            package main
            import "fmt"
            func foo() error {
            \tif err != nil {
            \t\treturn fmt.Errorf("failed: %v", err)
            \t}
            \treturn nil
            }
        """)
        entries, _ = detect_smells(path)
        assert "error_no_wrap" in _smell_ids(entries)

    def test_not_for_wrapped(self, tmp_path):
        path = _write_go(tmp_path, """\
            package main
            import "fmt"
            func foo() error {
            \tif err != nil {
            \t\treturn fmt.Errorf("failed: %w", err)
            \t}
            \treturn nil
            }
        """)
        entries, _ = detect_smells(path)
        assert "error_no_wrap" not in _smell_ids(entries)
```

**Step 2: Run to verify failures**

Run: `cd /Users/josef.salyer/projects/atat/desloppify && python -m pytest tests/test_go_smells.py -v`
Expected: FAIL — detect_smells returns empty

**Step 3: Implement all 18 smell rules**

Implement in `desloppify/lang/go/detectors/smells.py` following the Python pattern from `desloppify/lang/python/detectors/smells.py`:

Define `SMELL_CHECKS` list with `_smell(id, label, severity, pattern)` helper. Implement `detect_smells(path)` that:
1. Finds all `.go` files under path
2. For each file, runs regex checks line-by-line
3. For multi-line checks (monster_function, bare_goroutine, etc.), tracks brace depth
4. Groups matches by smell ID
5. Returns `(entries, file_count)` where entries have `id`, `label`, `severity`, `count`, `matches`, `files`

The 18 rules (regex patterns):

**Error handling:**
- `ignored_error`: `r"_\s*(?:,\s*_\s*)?=\s*\w+[\w.]*\("` but NOT in `for _, v := range` context
- `bare_error_return`: `r"return\s+err\s*$"` (no wrapping)
- `error_no_wrap`: `r"fmt\.Errorf\([^)]*%v[^)]*err"` (uses %v not %w)
- `empty_error_branch`: multi-line — `if err != nil {` followed by `}`
- `swallowed_error`: multi-line — log.Print/Println/Printf in error branch without return
- `unchecked_error`: multi-line — function call returning error with no assignment

**Code quality:**
- `monster_function`: brace-tracked, >150 LOC
- `dead_function`: brace-tracked, body is only `return` or empty
- `init_abuse`: `r"^func\s+init\s*\(\s*\)"` — flagged if body has side effects
- `global_state`: `r"^var\s+\w+\s+"` at package level (not `var err` or `var Err`)
- `magic_number`: `r"(?:==|!=|>=?|<=?|[+\-*/])\s*\d{4,}"`
- `todo_fixme`: `r"//\s*(?:TODO|FIXME|HACK|XXX)"`

**Safety:**
- `bare_goroutine`: multi-line — `go func()` without `recover` or `errgroup` in body
- `mutex_copy`: `r"func\s+\w+\([^)]*sync\.Mutex[^*]"` (non-pointer Mutex param)
- `context_background`: `r"context\.Background\(\)"` inside non-main, non-init functions

**Naming:**
- `inconsistent_receiver`: compute — uses extractor to check receiver name consistency
- `stutter_name`: compute — checks `type PkgFoo` where `Pkg` matches package name
- `hardcoded_url`: `r"""(?:['"\x60])https?://[^\s'"\x60]+(?:['"\x60])"""`

**Step 4: Run tests**

Run: `cd /Users/josef.salyer/projects/atat/desloppify && python -m pytest tests/test_go_smells.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add desloppify/lang/go/detectors/smells.py tests/test_go_smells.py
git commit -m "feat(go): implement 18 Go-specific smell detection rules"
```
### Task 5: Implement Go dependency graph builder

**Files:**
- Modify: `desloppify/lang/go/detectors/deps.py`
- Test: `tests/test_go_deps.py`

**Step 1: Write failing tests**

```python
# tests/test_go_deps.py
"""Test Go dependency graph builder."""
import textwrap
from pathlib import Path
from unittest.mock import patch

import pytest

from desloppify.lang.go.detectors.deps import build_dep_graph


def _write_go_project(tmp_path):
    """Create a minimal Go project with imports."""
    (tmp_path / "go.mod").write_text("module example.com/test\n\ngo 1.21\n")
    (tmp_path / "main.go").write_text(textwrap.dedent("""\
        package main

        import "example.com/test/pkg"

        func main() {
        \tpkg.Hello()
        }
    """))
    pkg_dir = tmp_path / "pkg"
    pkg_dir.mkdir()
    (pkg_dir / "hello.go").write_text(textwrap.dedent("""\
        package pkg

        func Hello() string {
        \treturn "hello"
        }
    """))
    return tmp_path


class TestBuildDepGraphRegex:
    """Test the regex fallback when Go tools aren't available."""

    def test_finds_imports(self, tmp_path):
        _write_go_project(tmp_path)
        import desloppify.utils as utils_mod
        with patch.object(utils_mod, "PROJECT_ROOT", tmp_path):
            graph = build_dep_graph(tmp_path)
        main_key = [k for k in graph if "main.go" in k]
        assert len(main_key) == 1
        assert len(graph[main_key[0]]["imports"]) > 0

    def test_empty_project(self, tmp_path):
        (tmp_path / "go.mod").write_text("module example.com/empty\n\ngo 1.21\n")
        (tmp_path / "main.go").write_text("package main\n\nfunc main() {}\n")
        import desloppify.utils as utils_mod
        with patch.object(utils_mod, "PROJECT_ROOT", tmp_path):
            graph = build_dep_graph(tmp_path)
        assert len(graph) >= 1
```

**Step 2: Run to verify failures**

Run: `cd /Users/josef.salyer/projects/atat/desloppify && python -m pytest tests/test_go_deps.py -v`
Expected: FAIL — empty graph returned

**Step 3: Implement dep graph builder**

Update `desloppify/lang/go/detectors/deps.py` with:

1. `_try_go_list(path)` — runs `go list -json ./...`, parses JSON output, builds graph from `ImportPath` and `Imports` fields. Maps import paths to actual file paths using `Dir` field.

2. `_build_graph_regex(path)` — fallback that:
   - Reads `go.mod` to get module path
   - Parses `import (...)` blocks in each .go file
   - Resolves local imports (those starting with module path) to files
   - Ignores stdlib imports

3. `build_dep_graph(path)` — tries `_try_go_list` first, falls back to `_build_graph_regex`.

Both return the same format: `{resolved_path: {"imports": set, "importers": set}}`, passed through `finalize_graph()` from `desloppify.detectors.graph`.

**Step 4: Run tests**

Run: `cd /Users/josef.salyer/projects/atat/desloppify && python -m pytest tests/test_go_deps.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add desloppify/lang/go/detectors/deps.py tests/test_go_deps.py
git commit -m "feat(go): implement dependency graph builder with go list fallback"
```

---

### Task 6: Implement Go unused detection

**Files:**
- Modify: `desloppify/lang/go/detectors/unused.py`
- Test: `tests/test_go_unused.py`

**Step 1: Write failing tests**

```python
# tests/test_go_unused.py
"""Test Go unused detection."""
import textwrap
from pathlib import Path
from unittest.mock import patch

import pytest

from desloppify.lang.go.detectors.unused import detect_unused


def _write_go(tmp_path: Path, code: str, filename: str = "main.go") -> Path:
    (tmp_path / "go.mod").write_text("module example.com/test\n\ngo 1.21\n")
    f = tmp_path / filename
    f.write_text(textwrap.dedent(code))
    return tmp_path


class TestDetectUnused:
    def test_returns_tuple(self, tmp_path):
        path = _write_go(tmp_path, "package main\n\nfunc main() {}\n")
        entries, count = detect_unused(path)
        assert isinstance(entries, list)
        assert isinstance(count, int)

    def test_entry_structure(self, tmp_path):
        """If go vet finds unused vars, entries have correct keys."""
        path = _write_go(tmp_path, """\
            package main

            import "fmt"

            func main() {
            \tx := 5
            \tfmt.Println("hello")
            }
        """)
        entries, _ = detect_unused(path)
        # May or may not find issues depending on tool availability
        for e in entries:
            assert "file" in e
            assert "line" in e
            assert "name" in e
            assert "category" in e
```

**Step 2: Run to verify failures**

Run: `cd /Users/josef.salyer/projects/atat/desloppify && python -m pytest tests/test_go_unused.py -v`
Expected: FAIL or PASS depending on current stub

**Step 3: Implement unused detection**

Update `desloppify/lang/go/detectors/unused.py`:

1. `_try_go_vet(path)` — runs `go vet ./...`, parses stderr for unused variable warnings. Returns list of `{file, line, name, category: "vars"}`.

2. `_try_gopls(path)` — runs `gopls check ./...` if available, extracts unused import diagnostics. Returns list of `{file, line, name, category: "imports"}`.

3. `_try_goimports(path)` — fallback for imports: runs `goimports -l`, identifies files with unused imports.

4. `detect_unused(path, category)` — orchestrates: tries go vet for vars, gopls/goimports for imports. Returns `(entries, total_files)`.

Pattern follows `desloppify/lang/python/detectors/unused.py:11-19` — try preferred tool, then fallback, then return empty.

**Step 4: Run tests**

Run: `cd /Users/josef.salyer/projects/atat/desloppify && python -m pytest tests/test_go_unused.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add desloppify/lang/go/detectors/unused.py tests/test_go_unused.py
git commit -m "feat(go): implement unused detection via go vet and gopls"
```

---

### Task 7: Implement Go complexity signals

**Files:**
- Modify: `desloppify/lang/go/detectors/complexity.py`
- Modify: `desloppify/lang/go/__init__.py` (add GO_COMPLEXITY_SIGNALS, GO_GOD_RULES)
- Test: `tests/test_go_complexity.py`

**Step 1: Write failing tests**

```python
# tests/test_go_complexity.py
"""Test Go complexity signal computation."""
import textwrap

import pytest

from desloppify.lang.go.detectors.complexity import (
    compute_max_params,
    compute_nesting_depth,
    compute_long_functions,
)


class TestComputeMaxParams:
    def test_below_threshold(self):
        content = "func foo(a int, b string) {}\n"
        lines = content.splitlines()
        assert compute_max_params(content, lines) is None

    def test_above_threshold(self):
        params = ", ".join(f"p{i} int" for i in range(10))
        content = f"func many({params}) {{}}\n"
        lines = content.splitlines()
        result = compute_max_params(content, lines)
        assert result is not None
        count, label = result
        assert count >= 10


class TestComputeNestingDepth:
    def test_deep_nesting(self):
        content = textwrap.dedent("""\
            func deep() {
            \tif true {
            \t\tfor i := 0; i < 10; i++ {
            \t\t\tif x > 0 {
            \t\t\t\tfor j := range items {
            \t\t\t\t\tif y > 0 {
            \t\t\t\t\t\tdoWork()
            \t\t\t\t\t}
            \t\t\t\t}
            \t\t\t}
            \t\t}
            \t}
            }
        """)
        lines = content.splitlines()
        result = compute_nesting_depth(content, lines)
        assert result is not None
        count, label = result
        assert count >= 5


class TestComputeLongFunctions:
    def test_long_function(self):
        body = "\n".join(f"\tx_{i} := {i}" for i in range(100))
        content = f"func long() {{\n{body}\n}}\n"
        lines = content.splitlines()
        result = compute_long_functions(content, lines)
        assert result is not None
        count, label = result
        assert count >= 100
```

**Step 2: Run to verify failures**

Run: `cd /Users/josef.salyer/projects/atat/desloppify && python -m pytest tests/test_go_complexity.py -v`
Expected: FAIL — functions return None

**Step 3: Implement complexity compute functions**

Update `desloppify/lang/go/detectors/complexity.py`:

- `compute_max_params(content, lines)`: Parse `func` signatures, count params. Return `(count, f"{count} params in funcName")` if above threshold (6), else None.

- `compute_nesting_depth(content, lines)`: Track indent depth via tab/space counting inside functions. Return `(depth, f"nesting depth {depth}")` if above threshold (5), else None.

- `compute_long_functions(content, lines)`: Track function boundaries via brace depth, measure LOC. Return `(max_loc, f"longest function {max_loc} LOC")` if above threshold (80), else None.

Then update `desloppify/lang/go/__init__.py` to define:

```python
GO_COMPLEXITY_SIGNALS = [
    ComplexitySignal("imports", r"^\t\"", weight=1, threshold=15),
    ComplexitySignal("many_params", None, weight=2, threshold=6, compute=compute_max_params),
    ComplexitySignal("deep_nesting", None, weight=3, threshold=5, compute=compute_nesting_depth),
    ComplexitySignal("long_functions", None, weight=1, threshold=80, compute=compute_long_functions),
    ComplexitySignal("goroutines", r"go\s+(?:func\b|\w+\()", weight=2, threshold=5),
    ComplexitySignal("TODOs", r"//\s*(?:TODO|FIXME|HACK|XXX)", weight=2, threshold=0),
    ComplexitySignal("type_switches", r"switch\s+.*\.\(type\)", weight=1, threshold=3),
]

GO_GOD_RULES = [
    GodRule("methods", "methods", lambda c: len(c.methods), 15),
    GodRule("fields", "fields (attributes)", lambda c: len(c.attributes), 12),
    GodRule("embedded", "embedded types", lambda c: len(c.base_classes), 4),
    GodRule("long_methods", "long methods (>50 LOC)",
            lambda c: sum(1 for m in c.methods if m.loc > 50), 2),
]
```

**Step 4: Run tests**

Run: `cd /Users/josef.salyer/projects/atat/desloppify && python -m pytest tests/test_go_complexity.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add desloppify/lang/go/detectors/complexity.py desloppify/lang/go/__init__.py tests/test_go_complexity.py
git commit -m "feat(go): implement complexity signals and god struct rules"
```
### Task 8: Wire up detection phases and per-repo config

**Files:**
- Modify: `desloppify/lang/go/__init__.py` (add phase runners, config loading)
- Create: `desloppify/lang/go/config.py` (per-repo config loader)
- Test: `tests/test_go_config.py`
- Test: `tests/test_go_phases.py`

**Step 1: Write failing tests for config loading**

```python
# tests/test_go_config.py
"""Test per-repo Go config loading."""
import textwrap
from pathlib import Path

import pytest

from desloppify.lang.go.config import load_go_config


class TestLoadGoConfig:
    def test_no_config_returns_defaults(self, tmp_path):
        cfg = load_go_config(tmp_path)
        assert cfg["thresholds"]["large_file"] == 500
        assert cfg["thresholds"]["complexity"] == 20

    def test_overrides_thresholds(self, tmp_path):
        config_dir = tmp_path / ".desloppify"
        config_dir.mkdir()
        (config_dir / "go.yaml").write_text(textwrap.dedent("""\
            thresholds:
              large_file: 600
              complexity: 25
        """))
        cfg = load_go_config(tmp_path)
        assert cfg["thresholds"]["large_file"] == 600
        assert cfg["thresholds"]["complexity"] == 25

    def test_overrides_entry_patterns(self, tmp_path):
        config_dir = tmp_path / ".desloppify"
        config_dir.mkdir()
        (config_dir / "go.yaml").write_text(textwrap.dedent("""\
            entry_patterns:
              - "/lambda/"
              - "handler.go"
        """))
        cfg = load_go_config(tmp_path)
        assert "/lambda/" in cfg["entry_patterns"]
        assert "handler.go" in cfg["entry_patterns"]
        # Defaults should still be present
        assert "main.go" in cfg["entry_patterns"]

    def test_overrides_exclusions(self, tmp_path):
        config_dir = tmp_path / ".desloppify"
        config_dir.mkdir()
        (config_dir / "go.yaml").write_text(textwrap.dedent("""\
            exclusions:
              - "dist"
        """))
        cfg = load_go_config(tmp_path)
        assert "dist" in cfg["exclusions"]
        assert "vendor" in cfg["exclusions"]
```

**Step 2: Run to verify failures**

Run: `cd /Users/josef.salyer/projects/atat/desloppify && python -m pytest tests/test_go_config.py -v`
Expected: FAIL — module not found

**Step 3: Implement config loader**

Create `desloppify/lang/go/config.py`:

```python
"""Per-repo Go configuration loader."""
from __future__ import annotations

from pathlib import Path

import yaml


GO_DEFAULTS = {
    "zones": {
        "generated": ["_gen.go", "_mock.go", "_string.go"],
        "test": ["/testutil/"],
        "config": ["Makefile", "Dockerfile"],
        "script": ["/tools/"],
    },
    "entry_patterns": [
        "main.go", "/cmd/", "_test.go", "/testdata/",
        "/lambda/", "handler.go", "/migrations/",
        ".pb.go", "_gen.go", "_mock.go", "doc.go",
    ],
    "exclusions": ["vendor", ".git", "testdata", "bin"],
    "boundaries": [],
    "thresholds": {
        "large_file": 500,
        "complexity": 20,
        "monster_function": 150,
    },
}


def load_go_config(project_root: Path) -> dict:
    """Load Go config, merging per-repo overrides with defaults."""
    config = _deep_copy_defaults()
    config_file = project_root / ".desloppify" / "go.yaml"
    if config_file.exists():
        try:
            overrides = yaml.safe_load(config_file.read_text()) or {}
        except Exception:
            return config
        _merge_config(config, overrides)
    return config


def _deep_copy_defaults() -> dict:
    import copy
    return copy.deepcopy(GO_DEFAULTS)


def _merge_config(base: dict, overrides: dict):
    """Merge overrides into base. Lists are extended, dicts are recursive, scalars replaced."""
    for key, value in overrides.items():
        if key not in base:
            base[key] = value
        elif isinstance(base[key], dict) and isinstance(value, dict):
            _merge_config(base[key], value)
        elif isinstance(base[key], list) and isinstance(value, list):
            for item in value:
                if item not in base[key]:
                    base[key].append(item)
        else:
            base[key] = value
```

**Step 4: Run config tests**

Run: `cd /Users/josef.salyer/projects/atat/desloppify && python -m pytest tests/test_go_config.py -v`
Expected: PASS

**Step 5: Write failing phase integration test**

```python
# tests/test_go_phases.py
"""Test Go detection phase runners."""
import textwrap
from pathlib import Path
from unittest.mock import patch

import pytest

from desloppify.lang import get_lang


@pytest.fixture(autouse=True)
def _set_project_root(tmp_path, monkeypatch):
    import desloppify.utils as utils_mod
    monkeypatch.setattr(utils_mod, "PROJECT_ROOT", tmp_path)


class TestGoPhases:
    def test_has_phases(self):
        lang = get_lang("go")
        assert len(lang.phases) >= 5

    def test_phase_labels(self):
        lang = get_lang("go")
        labels = [p.label for p in lang.phases]
        assert "Unused (go vet)" in labels
        assert "Structural analysis" in labels
        assert "Code smells" in labels

    def test_smell_phase_runs(self, tmp_path):
        (tmp_path / "go.mod").write_text("module test\n\ngo 1.21\n")
        (tmp_path / "main.go").write_text(textwrap.dedent("""\
            package main
            // TODO: fix this
            func main() {}
        """))
        lang = get_lang("go")
        # Find smell phase
        smell_phase = [p for p in lang.phases if "smell" in p.label.lower()][0]
        findings, potentials = smell_phase.run(tmp_path, lang)
        assert isinstance(findings, list)
```

**Step 6: Wire up all phase runners in __init__.py**

Add to `desloppify/lang/go/__init__.py`:

Phase runners following the Python plugin pattern (see `desloppify/lang/python/__init__.py:86-312`):

- `_phase_unused` — calls `detectors.unused.detect_unused`, normalizes via `make_unused_findings`
- `_phase_structural` — calls `detect_large_files`, `detect_complexity`, `detect_gods`, `detect_flat_dirs`, merges via `merge_structural_signals`
- `_phase_coupling` — calls `build_dep_graph`, `detect_cycles`, `detect_orphaned_files`, `detect_single_use_abstractions`, `detect_reexport_facades`
- `_phase_test_coverage` — calls `detect_test_coverage` with Go zone map
- `_phase_smells` — calls `detectors.smells.detect_smells`, normalizes via `make_smell_findings`

Update the `GoConfig.__init__` to populate `phases`:

```python
phases=[
    DetectorPhase("Unused (go vet)", _phase_unused),
    DetectorPhase("Structural analysis", _phase_structural),
    DetectorPhase("Coupling + cycles + orphaned", _phase_coupling),
    DetectorPhase("Test coverage", _phase_test_coverage),
    DetectorPhase("Code smells", _phase_smells),
    DetectorPhase("Duplicates", phase_dupes, slow=True),
],
```

Also integrate config loading: in `GoConfig.__init__`, call `load_go_config` to apply per-repo overrides to thresholds, entry_patterns, exclusions, zone_rules, and boundaries.

**Step 7: Run phase tests**

Run: `cd /Users/josef.salyer/projects/atat/desloppify && python -m pytest tests/test_go_phases.py tests/test_go_config.py -v`
Expected: PASS

**Step 8: Commit**

```bash
git add desloppify/lang/go/ tests/test_go_config.py tests/test_go_phases.py
git commit -m "feat(go): wire up detection phases and per-repo config loading"
```

---

### Task 9: Implement Go CLI detect commands

**Files:**
- Modify: `desloppify/lang/go/commands.py`
- Test: `tests/test_go_commands.py`

**Step 1: Write failing test**

```python
# tests/test_go_commands.py
"""Test Go detector CLI commands."""
from desloppify.lang.go.commands import get_detect_commands


class TestGoCommands:
    def test_registry_not_empty(self):
        cmds = get_detect_commands()
        assert len(cmds) > 0

    def test_expected_commands(self):
        cmds = get_detect_commands()
        expected = {"unused", "large", "complexity", "gods", "smells",
                    "dupes", "deps", "cycles", "orphaned"}
        assert expected.issubset(set(cmds.keys()))

    def test_commands_are_callable(self):
        cmds = get_detect_commands()
        for name, cmd in cmds.items():
            assert callable(cmd), f"{name} is not callable"
```

**Step 2: Run to verify failures**

Run: `cd /Users/josef.salyer/projects/atat/desloppify && python -m pytest tests/test_go_commands.py -v`
Expected: FAIL — empty registry

**Step 3: Implement commands**

Update `desloppify/lang/go/commands.py` following the Python pattern from `desloppify/lang/python/commands.py`. Use shared command factories from `desloppify/lang/commands_base.py` where available, and implement Go-specific display for: unused, large, complexity, gods, smells, dupes, deps, cycles, orphaned, single-use, facade.

**Step 4: Run tests**

Run: `cd /Users/josef.salyer/projects/atat/desloppify && python -m pytest tests/test_go_commands.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add desloppify/lang/go/commands.py tests/test_go_commands.py
git commit -m "feat(go): implement CLI detect commands for Go plugin"
```

---

### Task 10: End-to-end integration test

**Files:**
- Test: `tests/test_go_integration.py`

**Step 1: Write integration test**

```python
# tests/test_go_integration.py
"""End-to-end integration test for Go language plugin."""
import textwrap
from pathlib import Path
from unittest.mock import patch

import pytest

from desloppify.lang import get_lang, auto_detect_lang
from desloppify.plan import generate_findings


@pytest.fixture(autouse=True)
def _set_project_root(tmp_path, monkeypatch):
    import desloppify.utils as utils_mod
    monkeypatch.setattr(utils_mod, "PROJECT_ROOT", tmp_path)


def _create_go_project(tmp_path):
    """Create a Go project with known issues."""
    (tmp_path / "go.mod").write_text("module example.com/test\n\ngo 1.21\n")
    (tmp_path / "main.go").write_text(textwrap.dedent("""\
        package main

        import "fmt"

        // TODO: clean this up
        func main() {
        \t_ = doSomething()
        \tfmt.Println("hello")
        }

        func doSomething() error {
        \treturn nil
        }
    """))
    # Large file
    body = "\n".join(f"\tx_{i} := {i}" for i in range(600))
    (tmp_path / "big.go").write_text(f"package main\n\nfunc bigFunc() {{\n{body}\n}}\n")
    return tmp_path


class TestGoIntegration:
    def test_auto_detects_go(self, tmp_path):
        _create_go_project(tmp_path)
        assert auto_detect_lang(tmp_path) == "go"

    def test_generate_findings(self, tmp_path):
        _create_go_project(tmp_path)
        lang = get_lang("go")
        findings, potentials = generate_findings(
            tmp_path, include_slow=False, lang=lang)
        assert isinstance(findings, list)
        assert isinstance(potentials, dict)

    def test_finds_known_issues(self, tmp_path):
        _create_go_project(tmp_path)
        lang = get_lang("go")
        findings, _ = generate_findings(
            tmp_path, include_slow=False, lang=lang)
        detectors_found = {f["detector"] for f in findings}
        # Should find at least smells (todo_fixme, ignored_error) and structural (large file)
        assert len(findings) > 0

    def test_zone_classification(self, tmp_path):
        _create_go_project(tmp_path)
        (tmp_path / "main_test.go").write_text("package main\n")
        (tmp_path / "gen.pb.go").write_text("package main\n")
        lang = get_lang("go")
        from desloppify.zones import classify_file
        assert classify_file("main_test.go", lang.zone_rules).value == "test"
        assert classify_file("gen.pb.go", lang.zone_rules).value == "generated"
        assert classify_file("main.go", lang.zone_rules).value == "production"
```

**Step 2: Run integration tests**

Run: `cd /Users/josef.salyer/projects/atat/desloppify && python -m pytest tests/test_go_integration.py -v`
Expected: PASS

**Step 3: Run full test suite**

Run: `cd /Users/josef.salyer/projects/atat/desloppify && python -m pytest tests/ -v --tb=short`
Expected: ALL PASS (existing tests unaffected, all new Go tests pass)

**Step 4: Commit**

```bash
git add tests/test_go_integration.py
git commit -m "test(go): add end-to-end integration test for Go plugin"
```

---

### Task 11: Add PyYAML dependency

**Files:**
- Modify: `pyproject.toml`

**Step 1: Check if PyYAML is already a dependency**

Read `pyproject.toml` and check dependencies list.

**Step 2: Add PyYAML if missing**

Add `pyyaml >= 6.0` to the dependencies in `pyproject.toml` (needed for `.desloppify/go.yaml` config loading).

**Step 3: Install**

Run: `cd /Users/josef.salyer/projects/atat/desloppify && pip install -e .`
Expected: SUCCESS

**Step 4: Commit**

```bash
git add pyproject.toml
git commit -m "build: add pyyaml dependency for per-repo config"
```

---

### Task 12: Validate against real Go repos

**Files:** None (validation only)

**Step 1: Run scan on gw-api**

Run: `cd /Users/josef.salyer/projects/atat/desloppify && python -m desloppify scan --path ~/projects/gw/gw-api --lang go`
Expected: Scan completes, shows findings and score

**Step 2: Run scan on gw-auth**

Run: `cd /Users/josef.salyer/projects/atat/desloppify && python -m desloppify scan --path ~/projects/gw/gw-auth --lang go`
Expected: Scan completes

**Step 3: Run scan on gw-test-data**

Run: `cd /Users/josef.salyer/projects/atat/desloppify && python -m desloppify scan --path ~/projects/gw/gw-test-data --lang go`
Expected: Scan completes

**Step 4: Review findings for false positives**

Check each scan output for:
- False positives in smell detection (especially `ignored_error` in range loops)
- Correct zone classification (_test.go as test, .pb.go as generated)
- Reasonable threshold calibration (not too many/few findings)
- No crashes or unhandled exceptions

**Step 5: Fix any issues found, re-run tests**

Run: `cd /Users/josef.salyer/projects/atat/desloppify && python -m pytest tests/ -v --tb=short`
Expected: ALL PASS

**Step 6: Final commit**

```bash
git add -A
git commit -m "fix(go): address false positives from real-world Go repo validation"
```
