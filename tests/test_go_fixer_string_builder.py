"""Test string-builder fixer: replace += concat with strings.Builder."""
import textwrap

import pytest


@pytest.fixture(autouse=True)
def _set_project_root(tmp_path, monkeypatch):
    import desloppify.utils as utils_mod
    monkeypatch.setattr(utils_mod, "PROJECT_ROOT", tmp_path)
    import desloppify.lang.base as base_mod
    monkeypatch.setattr(base_mod, "PROJECT_ROOT", tmp_path)
    import desloppify.lang.go.fixers.common as go_common_mod
    monkeypatch.setattr(go_common_mod, "PROJECT_ROOT", tmp_path)
    utils_mod._find_source_files_cached.cache_clear()


@pytest.fixture
def go_file_concat_loop(tmp_path):
    (tmp_path / "go.mod").write_text("module test\n\ngo 1.21\n")
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
        from desloppify.lang.go.fixers.string_builder import (
            detect_string_concat,
            fix_string_builder,
        )
        entries = detect_string_concat(go_file_concat_loop.parent)
        fix_string_builder(entries, dry_run=False)
        content = go_file_concat_loop.read_text()
        assert "strings.Builder" in content
        assert "WriteString" in content
        # The += should be gone from loop body
        lines = content.splitlines()
        in_loop = False
        for line in lines:
            if "for " in line:
                in_loop = True
            if in_loop and "+=" in line:
                pytest.fail(f"Found += in loop body: {line}")
            if in_loop and line.strip() == "}":
                break

    def test_dry_run(self, go_file_concat_loop):
        from desloppify.lang.go.fixers.string_builder import (
            detect_string_concat,
            fix_string_builder,
        )
        entries = detect_string_concat(go_file_concat_loop.parent)
        original = go_file_concat_loop.read_text()
        fix_string_builder(entries, dry_run=True)
        assert go_file_concat_loop.read_text() == original
