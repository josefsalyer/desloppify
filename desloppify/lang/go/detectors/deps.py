"""Go dependency graph builder — parses import statements, resolves local packages to files."""

import os
import re
from collections import defaultdict
from pathlib import Path

from ....detectors.graph import finalize_graph
from ....utils import find_source_files, PROJECT_ROOT, resolve_path


# Regex for single-line imports: import "pkg" or import alias "pkg"
# Alias can be an identifier (\w+), a dot (.), or underscore (_).
_SINGLE_IMPORT_RE = re.compile(r'^\s*import\s+(?:[\w.]+\s+)?"([^"]+)"', re.MULTILINE)

# Regex for grouped import blocks: import ( ... )
_GROUP_IMPORT_RE = re.compile(r'import\s*\((.*?)\)', re.DOTALL)

# Regex for individual import lines within a group (with optional alias)
_IMPORT_LINE_RE = re.compile(r'(?:[\w.]+\s+)?"([^"]+)"')


def _parse_module_path(path: Path) -> str | None:
    """Parse go.mod to get the module path.

    Searches the given directory and its parents for a go.mod file.
    Returns the module path string or None if not found.
    """
    go_mod = path / "go.mod"
    if not go_mod.exists():
        for parent in list(path.parents):
            candidate = parent / "go.mod"
            if candidate.exists():
                go_mod = candidate
                break
        else:
            return None

    try:
        content = go_mod.read_text()
    except OSError:
        return None

    m = re.search(r"^module\s+(\S+)", content, re.MULTILINE)
    return m.group(1) if m else None


def _extract_imports(content: str) -> list[str]:
    """Extract import paths from Go source file content.

    Handles single imports, aliased imports, and grouped import blocks.
    Returns a list of import path strings.
    """
    imports: list[str] = []

    # Find grouped imports first and collect their spans so we can skip them
    # when searching for single imports
    group_spans: list[tuple[int, int]] = []
    for m in _GROUP_IMPORT_RE.finditer(content):
        group_spans.append(m.span())
        block = m.group(1)
        for line_match in _IMPORT_LINE_RE.finditer(block):
            imports.append(line_match.group(1))

    # Find single-line imports that are NOT inside a group block
    for m in _SINGLE_IMPORT_RE.finditer(content):
        start = m.start()
        in_group = any(gs <= start < ge for gs, ge in group_spans)
        if not in_group:
            imports.append(m.group(1))

    return imports


def _find_go_files(path: Path) -> list[str]:
    """Find all non-test .go files, excluding vendor/ and testdata/ directories."""
    all_go = find_source_files(path, [".go"], exclusions=["vendor", "testdata"])
    return [f for f in all_go if not f.endswith("_test.go")]


def build_dep_graph(path: Path) -> dict:
    """Build a dependency graph for Go files.

    Parses go.mod for the module path, discovers all .go files, extracts
    import statements, and resolves local (intra-module) imports to file
    paths. External imports are ignored.

    Returns ``{resolved_path: {"imports": set, "importers": set, "import_count", "importer_count"}}``.
    """
    path = Path(path).resolve()
    module_path = _parse_module_path(path)
    files = _find_go_files(path)

    # Map package import paths to their source files, and each file to its
    # package import path.
    pkg_to_files: dict[str, list[str]] = defaultdict(list)
    file_to_pkg: dict[str, str] = {}

    for filepath in files:
        # Determine the absolute directory of the file
        if os.path.isabs(filepath):
            abs_dir = os.path.dirname(filepath)
        else:
            abs_dir = str((PROJECT_ROOT / filepath).parent)

        rel_dir = os.path.relpath(abs_dir, path)

        if module_path:
            pkg_path = (module_path + "/" + rel_dir) if rel_dir != "." else module_path
        else:
            pkg_path = rel_dir

        # Normalise path separators (Windows)
        pkg_path = pkg_path.replace(os.sep, "/")

        resolved = resolve_path(filepath)
        pkg_to_files[pkg_path].append(resolved)
        file_to_pkg[resolved] = pkg_path

    # Initialise graph entries
    graph: dict[str, dict] = {}
    for filepath in files:
        resolved = resolve_path(filepath)
        graph[resolved] = {"imports": set(), "importers": set()}

    # Parse each file's imports and resolve local edges
    for filepath in files:
        resolved = resolve_path(filepath)
        abs_path = filepath if os.path.isabs(filepath) else str(PROJECT_ROOT / filepath)

        try:
            content = Path(abs_path).read_text()
        except (OSError, UnicodeDecodeError):
            continue

        imports = _extract_imports(content)

        for imp in imports:
            # Only resolve imports that belong to this module
            target_files = pkg_to_files.get(imp, [])
            for target in target_files:
                if target != resolved:
                    graph[resolved]["imports"].add(target)
                    graph[target]["importers"].add(resolved)

    return finalize_graph(graph)
