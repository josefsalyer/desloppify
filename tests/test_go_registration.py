"""Test that the Go language plugin registers and validates correctly."""
import pytest
from desloppify.lang import get_lang, available_langs, auto_detect_lang


class TestGoRegistration:
    def test_go_in_available_langs(self):
        langs = available_langs()
        assert "go" in langs

    def test_get_lang_returns_config(self):
        lang = get_lang("go")
        assert lang.name == "go"
        assert lang.extensions == [".go"]
        assert lang.default_src == "."

    def test_auto_detect_with_go_mod(self, tmp_path):
        (tmp_path / "go.mod").write_text("module example.com/test\n\ngo 1.21\n")
        (tmp_path / "main.go").write_text("package main\n")
        from unittest.mock import patch
        import desloppify.utils as utils_mod
        with patch.object(utils_mod, "PROJECT_ROOT", tmp_path):
            result = auto_detect_lang(tmp_path)
        assert result == "go"
