# Go Language Plugin Design

## Summary

Add Go language support to desloppify as a new plugin under `desloppify/lang/go/`. Uses a hybrid architecture: a Go helper binary for precise AST-based extraction, standard Go tools (`go list`, `go vet`, `gopls`) for dependency graphs and unused detection, and regex fallback when Go isn't installed. Per-repo configuration via `.desloppify/go.yaml` overrides hardcoded universal defaults.

Target repositories: `gw-api`, `gw-auth`, `gw-test-data`.

## Architecture

### Hybrid Approach

Three layers of Go tooling, each with fallback:

| Component | Primary | Fallback |
|-----------|---------|----------|
| Function/struct extraction | `go-extract` binary (go/ast) | Regex parsing |
| Dependency graph | `go list -json ./...` | Regex import block parsing |
| Unused detection | `go vet` + `gopls` | `goimports -l` or skip with warning |

Every tool call follows: try preferred -> try fallback -> skip with warning. Scans never fail due to missing tools. Scan metadata records which tools were used so the user understands coverage.

### File Structure

```
desloppify/lang/go/
├── __init__.py          # GoConfig + phase runners + @register_lang("go")
├── commands.py          # CLI subcommands (detect large, detect smells, etc.)
├── extractors.py        # Calls Go helper or falls back to regex
├── detectors/
│   ├── __init__.py
│   ├── smells.py        # 18 Go-specific SmellRules
│   ├── deps.py          # Wraps 'go list -json' for import graph
│   ├── unused.py        # Wraps 'go vet' / 'gopls' for unused detection
│   └── complexity.py    # Go-specific ComplexitySignal compute functions
└── fixers/
    └── __init__.py      # Empty initially

cmd/go-extract/          # Go helper binary (at desloppify repo root)
├── main.go              # CLI: accepts file paths, outputs JSON
├── extract.go           # go/ast-based function/struct/interface extraction
└── go.mod               # Module definition
```

## Go Helper Binary (`cmd/go-extract/`)

Accepts file paths via args, outputs JSON to stdout.

### Output Schema

```json
{
  "functions": [
    {
      "name": "HandleRequest",
      "file": "/abs/path/handler.go",
      "line": 15,
      "end_line": 42,
      "loc": 28,
      "body": "func HandleRequest(ctx context.Context...",
      "params": ["ctx", "req"],
      "receiver": "Server",
      "exported": true
    }
  ],
  "structs": [
    {
      "name": "Server",
      "file": "/abs/path/server.go",
      "line": 8,
      "loc": 35,
      "methods": ["HandleRequest", "Start", "Stop"],
      "fields": ["host", "port", "db"],
      "embedded": ["http.Handler"],
      "exported": true
    }
  ],
  "interfaces": [
    {
      "name": "Repository",
      "file": "/abs/path/repo.go",
      "line": 5,
      "methods": ["Get", "Put", "Delete"]
    }
  ]
}
```

### Invocation Order in extractors.py

1. Pre-compiled `go-extract` binary (on PATH or in desloppify's `bin/`)
2. `go run cmd/go-extract/main.go` (if Go is installed)
3. Regex fallback (~85% coverage of real Go code)

If Go helper fails, log warning, fall back to regex, set `confidence="medium"` on structural findings. `extraction_method` stored in scan metadata.

Go structs map to `ClassInfo` (methods, fields as attributes, embedded types as base_classes). Interfaces extracted separately for coupling analysis.

## Detection Phases

7 phases run in order:

| # | Phase | Tool Used | Tier |
|---|-------|-----------|------|
| 1 | Unused | `go vet` + `gopls` | T1 (imports), T2 (vars) |
| 2 | Structural | go-extract + regex signals | T3/T4 |
| 3 | Coupling | `go list -json` graph | T2/T3 |
| 4 | Test coverage | File matching (`_test.go`) | T2 |
| 5 | Smells | Regex + multi-line | T1-T3 |
| 6 | Duplicates | go-extract bodies | T2/T3 (slow) |

### Complexity Signals

| Signal | Pattern/Compute | Weight | Threshold |
|--------|----------------|--------|-----------|
| imports | `^import\s` or `^\t"` | 1 | 15 |
| deep nesting | compute: indent depth | 3 | 5 |
| long functions | compute: max func LOC | 1 | 80 |
| many params | compute: max param count | 2 | 6 |
| goroutines | `go\s+func\b\|go\s+\w+\(` | 2 | 5 |
| TODOs | `//\s*(?:TODO\|FIXME\|HACK\|XXX)` | 2 | 0 |
| type switches | `switch.*\.\(type\)` | 1 | 3 |

### God Struct Rules

| Rule | Extract | Threshold |
|------|---------|-----------|
| methods | method count | 15 |
| fields | field count | 12 |
| embedded | embedded type count | 4 |
| long methods | methods > 50 LOC | 2 |

## Smell Rules (18 rules)

### Error Handling (6)

| ID | Label | Pattern Type | Severity |
|----|-------|-------------|----------|
| `ignored_error` | Assigned to `_` blank identifier | Regex: `_\s*=\s*\w+\(` | HIGH |
| `unchecked_error` | Error return not checked | Multi-line | HIGH |
| `bare_error_return` | `return err` without wrapping context | Regex | MEDIUM |
| `error_no_wrap` | `fmt.Errorf` without `%w` verb | Regex: `Errorf\([^)]*[^%]"` | MEDIUM |
| `empty_error_branch` | `if err != nil { }` empty block | Multi-line | HIGH |
| `swallowed_error` | Log error then continue (no return) | Multi-line | MEDIUM |

### Code Quality (6)

| ID | Label | Pattern Type | Severity |
|----|-------|-------------|----------|
| `monster_function` | Function > 150 LOC | Brace-tracked | HIGH |
| `dead_function` | Empty or return-only function body | Brace-tracked | MEDIUM |
| `init_abuse` | `init()` with side effects beyond simple assignment | Multi-line | MEDIUM |
| `global_state` | Package-level `var` that isn't a const or error | Regex | MEDIUM |
| `magic_number` | Numeric literal > 1000 outside const block | Regex | LOW |
| `todo_fixme` | TODO/FIXME/HACK/XXX comments | Regex | LOW |

### Safety & Concurrency (3)

| ID | Label | Pattern Type | Severity |
|----|-------|-------------|----------|
| `bare_goroutine` | `go func()` without recover or errgroup | Multi-line | HIGH |
| `mutex_copy` | Passing sync.Mutex by value (not pointer) | Regex | HIGH |
| `context_background` | `context.Background()` inside handler (should propagate) | Regex | MEDIUM |

### Naming & Style (3)

| ID | Label | Pattern Type | Severity |
|----|-------|-------------|----------|
| `inconsistent_receiver` | Same struct uses different receiver names | Compute (go-extract) | MEDIUM |
| `stutter_name` | Type name repeats package name | Compute | LOW |
| `hardcoded_url` | Hardcoded URL strings | Regex | MEDIUM |

## Zone Classification & Per-Repo Config

### Universal Defaults (hardcoded, always true for Go)

- `_test.go` -> test zone
- `.pb.go` -> generated zone
- `go.mod`, `go.sum` -> config zone
- `vendor/` -> vendor zone (from COMMON_ZONE_RULES)
- Extensions: `[".go"]`
- Default src: `"."`

### Per-Repo Config (`.desloppify/go.yaml`)

Everything else is overridable per repository:

```yaml
# .desloppify/go.yaml
zones:
  generated:
    - "_gen.go"
    - "_mock.go"
  test:
    - "/testutil/"
  config:
    - "Makefile"
  script:
    - "/tools/"

entry_patterns:
  - "/lambda/"
  - "handler.go"

exclusions:
  - "bin"
  - "dist"

boundaries:
  - name: "pkg->internal"
    from: "pkg/"
    to: "internal/"

thresholds:
  large_file: 500
  complexity: 20
  monster_function: 150
```

The plugin merges: hardcoded Go universals + per-repo overrides. Overrides win for lists, replace for scalars.

### Default Entry Patterns

```python
GO_ENTRY_PATTERNS = [
    "main.go", "/cmd/", "_test.go", "/testdata/",
    "/lambda/", "handler.go",
    "/migrations/", "init.go",
    ".pb.go", "_gen.go", "_mock.go",
    "doc.go",
]
```

### Default Exclusions

```python
GO_EXCLUSIONS = ["vendor", ".git", "testdata", "bin"]
```

### Default Thresholds

- `large_threshold`: 500
- `complexity_threshold`: 20
- `default_src`: `"."`

## Go Tool Integration Details

### go-extract helper

```
extractors.py calls:
  1. go-extract binary (pre-compiled, on PATH or ./bin/)
  2. go run cmd/go-extract/main.go (Go installed)
  3. regex fallback (no Go)
```

### go list -json (dependency graph)

```
deps.py calls:
  go list -json -deps ./...

Parses:
  - ImportPath -> file mapping
  - Imports[] array -> edges in the graph
  - Internal package boundaries automatically respected

Fallback:
  - Regex: parse import (...) blocks, resolve relative to go.mod module path
  - Cycle detection and orphan detection still work with partial graph
```

### go vet + gopls (unused detection)

```
unused.py calls:
  go vet ./...          -> unused variables, unreachable code
  gopls check ./...     -> unused imports (if gopls available)

Fallback:
  - If gopls not available, use 'goimports -l' to detect unused imports
  - If neither available, skip unused phase with warning
```

## Testing Strategy

- Unit tests for each detector (regex patterns, smell rules) using Go code fixtures
- Unit tests for the Go helper binary (standard Go tests)
- Integration test: scan a small fixture Go project end-to-end
- Fixture files in `tests/fixtures/go/` with known issues to detect

## Excluded from v1 (YAGNI)

- Auto-fixers (empty `fixers/` directory for registration only)
- Pattern families (not needed for Go v1)
- AST-based smell rules (regex and multi-line cover all 18 rules)
- `golangci-lint` integration (users already have that separately)
