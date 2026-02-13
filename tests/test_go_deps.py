"""Tests for desloppify.lang.go.detectors.deps — Go dependency graph builder."""

import textwrap
from pathlib import Path

import pytest

from desloppify.lang.go.detectors.deps import (
    build_dep_graph,
    _extract_imports,
    _parse_module_path,
)


# ── Import extraction ────────────────────────────────────


class TestExtractImports:
    def test_single_import(self):
        code = 'import "fmt"\n'
        assert _extract_imports(code) == ["fmt"]

    def test_grouped_imports(self):
        code = textwrap.dedent('''\
            import (
                "fmt"
                "os"
                "github.com/foo/bar"
            )
        ''')
        imports = _extract_imports(code)
        assert "fmt" in imports
        assert "os" in imports
        assert "github.com/foo/bar" in imports

    def test_no_imports(self):
        assert _extract_imports("package main\n") == []

    def test_aliased_import(self):
        code = 'import pb "github.com/foo/proto"\n'
        assert "github.com/foo/proto" in _extract_imports(code)

    def test_aliased_grouped_import(self):
        code = textwrap.dedent('''\
            import (
                "fmt"
                pb "github.com/foo/proto"
                _ "github.com/lib/pq"
            )
        ''')
        imports = _extract_imports(code)
        assert "fmt" in imports
        assert "github.com/foo/proto" in imports
        assert "github.com/lib/pq" in imports

    def test_dot_import(self):
        code = 'import . "github.com/foo/bar"\n'
        assert "github.com/foo/bar" in _extract_imports(code)

    def test_multiple_import_groups(self):
        code = textwrap.dedent('''\
            import "fmt"

            import (
                "os"
                "strings"
            )
        ''')
        imports = _extract_imports(code)
        assert "fmt" in imports
        assert "os" in imports
        assert "strings" in imports

    def test_no_duplicate_from_group_and_single(self):
        """A grouped import should not also appear as a single import."""
        code = textwrap.dedent('''\
            import (
                "fmt"
            )
        ''')
        imports = _extract_imports(code)
        assert imports.count("fmt") == 1


# ── Module path parsing ──────────────────────────────────


class TestParseModulePath:
    def test_parse_go_mod(self, tmp_path):
        (tmp_path / "go.mod").write_text("module example.com/myapp\n\ngo 1.21\n")
        assert _parse_module_path(tmp_path) == "example.com/myapp"

    def test_no_go_mod(self, tmp_path):
        assert _parse_module_path(tmp_path) is None

    def test_go_mod_with_version(self, tmp_path):
        (tmp_path / "go.mod").write_text(
            "module github.com/org/repo\n\ngo 1.22.0\n\nrequire (\n)\n"
        )
        assert _parse_module_path(tmp_path) == "github.com/org/repo"

    def test_go_mod_in_parent(self, tmp_path):
        (tmp_path / "go.mod").write_text("module example.com/root\n\ngo 1.21\n")
        sub = tmp_path / "sub" / "pkg"
        sub.mkdir(parents=True)
        assert _parse_module_path(sub) == "example.com/root"


# ── Dependency graph construction ────────────────────────


class TestBuildDepGraph:
    def test_simple_graph(self, tmp_path):
        (tmp_path / "go.mod").write_text("module example.com/app\n\ngo 1.21\n")

        pkg_dir = tmp_path / "pkg"
        pkg_dir.mkdir()
        (pkg_dir / "util.go").write_text(textwrap.dedent('''\
            package pkg
            func Helper() {}
        '''))

        (tmp_path / "main.go").write_text(textwrap.dedent('''\
            package main
            import "example.com/app/pkg"
            func main() { pkg.Helper() }
        '''))

        graph = build_dep_graph(tmp_path)
        main_file = str((tmp_path / "main.go").resolve())
        util_file = str((pkg_dir / "util.go").resolve())

        assert main_file in graph
        assert util_file in graph
        assert util_file in graph[main_file]["imports"]
        assert main_file in graph[util_file]["importers"]

    def test_empty_project(self, tmp_path):
        (tmp_path / "go.mod").write_text("module example.com/empty\n\ngo 1.21\n")
        graph = build_dep_graph(tmp_path)
        assert graph == {}

    def test_no_go_mod(self, tmp_path):
        """Project without go.mod should still build a graph (no local imports resolve)."""
        (tmp_path / "main.go").write_text(textwrap.dedent('''\
            package main
            import "fmt"
            func main() { fmt.Println("hi") }
        '''))
        graph = build_dep_graph(tmp_path)
        main_file = str((tmp_path / "main.go").resolve())
        assert main_file in graph
        # fmt is external, so no edges
        assert graph[main_file]["import_count"] == 0

    def test_external_imports_ignored(self, tmp_path):
        (tmp_path / "go.mod").write_text("module example.com/app\n\ngo 1.21\n")
        (tmp_path / "main.go").write_text(textwrap.dedent('''\
            package main
            import (
                "fmt"
                "net/http"
                "github.com/external/lib"
            )
            func main() {}
        '''))
        graph = build_dep_graph(tmp_path)
        main_file = str((tmp_path / "main.go").resolve())
        assert main_file in graph
        assert graph[main_file]["import_count"] == 0

    def test_test_files_excluded(self, tmp_path):
        (tmp_path / "go.mod").write_text("module example.com/app\n\ngo 1.21\n")
        (tmp_path / "main.go").write_text("package main\nfunc main() {}\n")
        (tmp_path / "main_test.go").write_text(
            'package main\nimport "testing"\nfunc TestMain(t *testing.T) {}\n'
        )
        graph = build_dep_graph(tmp_path)
        test_file = str((tmp_path / "main_test.go").resolve())
        assert test_file not in graph

    def test_multi_package_graph(self, tmp_path):
        """Multiple packages with cross-imports produce correct edges."""
        (tmp_path / "go.mod").write_text("module example.com/app\n\ngo 1.21\n")

        # Package: example.com/app/core
        core = tmp_path / "core"
        core.mkdir()
        (core / "core.go").write_text(textwrap.dedent('''\
            package core
            func Init() {}
        '''))

        # Package: example.com/app/api (imports core)
        api = tmp_path / "api"
        api.mkdir()
        (api / "handler.go").write_text(textwrap.dedent('''\
            package api
            import "example.com/app/core"
            func Handle() { core.Init() }
        '''))

        # Package: main (imports both)
        (tmp_path / "main.go").write_text(textwrap.dedent('''\
            package main
            import (
                "example.com/app/core"
                "example.com/app/api"
            )
            func main() {
                core.Init()
                api.Handle()
            }
        '''))

        graph = build_dep_graph(tmp_path)
        main_file = str((tmp_path / "main.go").resolve())
        core_file = str((core / "core.go").resolve())
        handler_file = str((api / "handler.go").resolve())

        # main.go imports core.go and handler.go
        assert core_file in graph[main_file]["imports"]
        assert handler_file in graph[main_file]["imports"]
        assert graph[main_file]["import_count"] == 2

        # handler.go imports core.go
        assert core_file in graph[handler_file]["imports"]
        assert graph[handler_file]["import_count"] == 1

        # core.go is imported by both main.go and handler.go
        assert main_file in graph[core_file]["importers"]
        assert handler_file in graph[core_file]["importers"]
        assert graph[core_file]["importer_count"] == 2


# ── Graph structure (finalized) ──────────────────────────


class TestGraphStructure:
    def test_finalized_keys(self, tmp_path):
        (tmp_path / "go.mod").write_text("module example.com/app\n\ngo 1.21\n")
        (tmp_path / "main.go").write_text("package main\nfunc main() {}\n")
        graph = build_dep_graph(tmp_path)
        for entry in graph.values():
            assert "imports" in entry
            assert "importers" in entry
            assert "import_count" in entry
            assert "importer_count" in entry

    def test_multiple_files_in_package(self, tmp_path):
        """Importing a package with multiple files creates edges to all files."""
        (tmp_path / "go.mod").write_text("module example.com/app\n\ngo 1.21\n")

        lib = tmp_path / "lib"
        lib.mkdir()
        (lib / "a.go").write_text("package lib\nfunc A() {}\n")
        (lib / "b.go").write_text("package lib\nfunc B() {}\n")

        (tmp_path / "main.go").write_text(textwrap.dedent('''\
            package main
            import "example.com/app/lib"
            func main() { lib.A() }
        '''))

        graph = build_dep_graph(tmp_path)
        main_file = str((tmp_path / "main.go").resolve())
        a_file = str((lib / "a.go").resolve())
        b_file = str((lib / "b.go").resolve())

        # main.go should import both files in the lib package
        assert a_file in graph[main_file]["imports"]
        assert b_file in graph[main_file]["imports"]
        assert graph[main_file]["import_count"] == 2
