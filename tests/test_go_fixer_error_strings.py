"""Test error-strings fixer: lowercase + strip punctuation from error strings."""
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
def go_file_bad_errors(tmp_path):
    (tmp_path / "go.mod").write_text("module test\n\ngo 1.21\n")
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
        lines_found = {e["line"] for e in entries}
        assert 9 in lines_found
        assert 13 in lines_found


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
