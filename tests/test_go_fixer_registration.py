"""Test Go fixer registration in GoConfig."""
import pytest

from desloppify.lang import get_lang


class TestGoFixerRegistration:
    def test_fixers_registered(self):
        lang = get_lang("go")
        assert len(lang.fixers) == 5

    def test_expected_fixer_names(self):
        lang = get_lang("go")
        expected = {"error-wrap", "error-strings", "regex-hoist",
                    "string-builder", "mutex-pointer"}
        assert set(lang.fixers.keys()) == expected

    def test_all_fixers_have_required_fields(self):
        lang = get_lang("go")
        for name, fc in lang.fixers.items():
            assert fc.label, f"{name} missing label"
            assert callable(fc.detect), f"{name} missing detect"
            assert callable(fc.fix), f"{name} missing fix"
            assert fc.detector, f"{name} missing detector"

    def test_fixer_detect_callable(self, tmp_path, monkeypatch):
        """Each fixer's detect function runs without error on empty project."""
        import desloppify.utils as utils_mod
        monkeypatch.setattr(utils_mod, "PROJECT_ROOT", tmp_path)
        import desloppify.lang.base as base_mod
        monkeypatch.setattr(base_mod, "PROJECT_ROOT", tmp_path)
        utils_mod._find_source_files_cached.cache_clear()
        (tmp_path / "go.mod").write_text("module test\n\ngo 1.21\n")
        (tmp_path / "main.go").write_text("package main\n\nfunc main() {}\n")

        lang = get_lang("go")
        for name, fc in lang.fixers.items():
            entries = fc.detect(tmp_path)
            assert isinstance(entries, list), f"{name} detect didn't return list"
