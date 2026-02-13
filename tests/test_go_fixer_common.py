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
