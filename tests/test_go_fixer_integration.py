"""End-to-end integration test: detect smells, fix them, verify fixed."""
import textwrap
from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def _set_project_root(tmp_path, monkeypatch):
    import desloppify.utils as utils_mod
    monkeypatch.setattr(utils_mod, "PROJECT_ROOT", tmp_path)
    import desloppify.detectors.large as large_mod
    monkeypatch.setattr(large_mod, "PROJECT_ROOT", tmp_path)
    import desloppify.lang.base as base_mod
    monkeypatch.setattr(base_mod, "PROJECT_ROOT", tmp_path)
    import desloppify.lang.go.fixers.common as go_common_mod
    monkeypatch.setattr(go_common_mod, "PROJECT_ROOT", tmp_path)
    utils_mod._find_source_files_cached.cache_clear()


def _create_fixable_project(tmp_path):
    """Create a Go project with known fixable issues."""
    (tmp_path / "go.mod").write_text("module example.com/test\n\ngo 1.21\n")

    (tmp_path / "service.go").write_text(textwrap.dedent("""\
        package main

        import (
        \t"errors"
        \t"fmt"
        \t"regexp"
        \t"sync"
        )

        func processItem(id string) error {
        \tresult, err := fetch(id)
        \tif err != nil {
        \t\treturn err
        \t}
        \tfmt.Println(result)
        \treturn nil
        }

        func validate() error {
        \treturn errors.New("Invalid input provided.")
        }

        func search(items []string) []string {
        \tvar results []string
        \tfor _, item := range items {
        \t\tre := regexp.MustCompile(`\\d+`)
        \t\tif re.MatchString(item) {
        \t\t\tresults = append(results, item)
        \t\t}
        \t}
        \treturn results
        }

        func buildCSV(items []string) string {
        \tresult := ""
        \tfor _, item := range items {
        \t\tresult += item + ","
        \t}
        \treturn result
        }

        func withLock(mu sync.Mutex) {
        \tmu.Lock()
        \tdefer mu.Unlock()
        }
    """))
    return tmp_path


class TestGoFixerIntegration:
    def test_all_fixers_detect(self, tmp_path):
        """Every registered fixer can detect entries from the test project."""
        _create_fixable_project(tmp_path)
        from desloppify.lang import get_lang
        lang = get_lang("go")
        detected = {}
        for name, fc in lang.fixers.items():
            entries = fc.detect(tmp_path)
            detected[name] = len(entries)
        # Each fixer should find at least one issue
        for name, count in detected.items():
            assert count > 0, f"Fixer {name} detected 0 entries"

    def test_all_fixers_fix_dry_run(self, tmp_path):
        """All fixers produce results in dry-run mode without changing files."""
        _create_fixable_project(tmp_path)
        original = (tmp_path / "service.go").read_text()
        from desloppify.lang import get_lang
        lang = get_lang("go")
        for name, fc in lang.fixers.items():
            entries = fc.detect(tmp_path)
            results = fc.fix(entries, dry_run=True)
            assert isinstance(results, list), f"{name} fix didn't return list"
        assert (tmp_path / "service.go").read_text() == original

    def test_fixers_modify_files(self, tmp_path):
        """Each fixer actually modifies the source file."""
        _create_fixable_project(tmp_path)
        original = (tmp_path / "service.go").read_text()
        from desloppify.lang import get_lang
        lang = get_lang("go")
        total_fixed = 0
        for name, fc in lang.fixers.items():
            entries = fc.detect(tmp_path)
            results = fc.fix(entries, dry_run=False)
            total_fixed += sum(len(r["removed"]) for r in results)
        # 5 fixers, but error-wrap's bare_error_return and empty_error_check
        # overlap on the same line, so one fix resolves both entries
        assert total_fixed >= 4
        assert (tmp_path / "service.go").read_text() != original
