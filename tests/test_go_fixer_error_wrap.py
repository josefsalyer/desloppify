"""Test error-wrap fixer: bare return err -> fmt.Errorf wrapping."""
import textwrap
from pathlib import Path

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
def go_file_bare_return(tmp_path):
    """Go file with bare return err."""
    (tmp_path / "go.mod").write_text("module test\n\ngo 1.21\n")
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
    (tmp_path / "go.mod").write_text("module test\n\ngo 1.21\n")
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
        assert "processOrder" in content
        # The bare "return err" should be gone
        for line in content.splitlines():
            stripped = line.strip()
            assert stripped != "return err", f"Bare return err still present: {line}"

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
