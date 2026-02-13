# Go Fixers Design

## Overview

Add 5 auto-fixers for Go mechanical code quality issues. These follow the existing TypeScript fixer architecture: detect entries, apply text transforms, write back.

## Architecture

```
desloppify/lang/go/fixers/
├── __init__.py          # Exports all fix functions
├── common.py            # apply_fixer + Go-specific utilities (copied from TS)
├── error_wrap.py        # fix_bare_error_return
├── error_strings.py     # fix_error_strings
├── regex_hoist.py       # fix_regex_in_loop
├── string_builder.py    # fix_string_concat_loop
└── mutex_pointer.py     # fix_mutex_copy
```

## Fixers

### 1. error-wrap

**Source smells:** `bare_error_return`, `empty_error_check`

**Transform:** `return err` → `return fmt.Errorf("<funcName>: %w", err)`

Detects the enclosing function name by scanning backwards from the match line for `func <name>`. Also handles `if err != nil { return err }` → `if err != nil { return fmt.Errorf("<funcName>: %w", err) }`.

### 2. error-strings

**Source smell:** `error_string_format`

**Transform:** Lowercases first character of error string argument, strips trailing period. Per Go conventions enforced by `go vet`.

Example: `errors.New("Error message.")` → `errors.New("error message")`

### 3. regex-hoist

**Source smell:** `regex_in_loop`

**Transform:** Finds `regexp.Compile`/`MustCompile` inside `for`/`range` loops, hoists the assignment above the enclosing loop. For `MustCompile`, creates a package-level `var`. For `Compile`, preserves error handling.

### 4. string-builder

**Source smell:** `string_concat_loop`

**Transform:** Finds `s += expr` inside `for`/`range` loops. Inserts `var sb strings.Builder` before the loop, replaces `s += expr` with `sb.WriteString(expr)` inside, and adds `s = sb.String()` after the loop.

### 5. mutex-pointer

**Source smell:** `mutex_copy`

**Transform:** `func Foo(mu sync.Mutex)` → `func Foo(mu *sync.Mutex)`. Simple regex substitution on the function signature.

## Detection → Fix Data Flow

Each fixer has a `detect` function that calls `detect_smells(path)`, filters to the relevant smell IDs, and flattens matches into `[{file, line, content, name}]` format for `apply_fixer`.

```python
def detect_bare_errors(path):
    entries, _ = detect_smells(path)
    flat = []
    for e in entries:
        if e["id"] in ("bare_error_return", "empty_error_check"):
            for m in e["matches"]:
                flat.append({"file": m["file"], "line": m["line"],
                             "name": f"{e['id']}::{m['line']}",
                             "content": m["content"]})
    return flat
```

## Registration

Fixers are registered in `GoConfig.__init__` via the `fixers` dict parameter, using `FixerConfig` dataclass instances. The `detector` field is `"smells"` for all 5 fixers since they all source from smell detection.

## Shared Utilities (common.py)

Copied from `desloppify/lang/typescript/fixers/common.py`:
- `apply_fixer(entries, transform_fn, *, dry_run)` — groups by file, reads, transforms, writes
- `collapse_blank_lines(lines, removed_indices)` — clean up after removals
- `find_balanced_end(lines, start, *, track, max_lines)` — bracket balancing

Plus Go-specific:
- `find_enclosing_func(lines, line_idx)` — scan backward for `func <name>` declaration
- `find_enclosing_for(lines, line_idx)` — scan backward for `for`/`range` loop start

## Testing Strategy

Each fixer gets a test file with:
- Go source fixtures containing the target smell
- Verify `detect()` returns expected entries
- Verify `fix(entries, dry_run=True)` returns results without modifying files
- Verify `fix(entries, dry_run=False)` writes corrected Go source
- Verify corrected source matches expected output
