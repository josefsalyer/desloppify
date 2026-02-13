"""Test regex-hoist fixer: move regexp.Compile out of loops."""
import textwrap

import pytest


@pytest.fixture(autouse=True)
def _set_project_root(tmp_path, monkeypatch):
    import desloppify.utils as utils_mod
    monkeypatch.setattr(utils_mod, "PROJECT_ROOT", tmp_path)
    import desloppify.lang.base as base_mod
    monkeypatch.setattr(base_mod, "PROJECT_ROOT", tmp_path)
    import desloppify.lang.go.fixers.common as common_mod
    monkeypatch.setattr(common_mod, "PROJECT_ROOT", tmp_path)
    utils_mod._find_source_files_cached.cache_clear()


@pytest.fixture
def go_file_regex_loop(tmp_path):
    (tmp_path / "go.mod").write_text("module test\n\ngo 1.21\n")
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
        compile_line = next(i for i, ln in enumerate(lines) if "MustCompile" in ln)
        for_line = next(i for i, ln in enumerate(lines) if ln.strip().startswith("for "))
        assert compile_line < for_line
        # Inside the loop, re should still be used
        assert "re.MatchString" in content

    def test_dry_run(self, go_file_regex_loop):
        from desloppify.lang.go.fixers.regex_hoist import detect_regex_in_loop, fix_regex_hoist
        entries = detect_regex_in_loop(go_file_regex_loop.parent)
        original = go_file_regex_loop.read_text()
        fix_regex_hoist(entries, dry_run=True)
        assert go_file_regex_loop.read_text() == original
