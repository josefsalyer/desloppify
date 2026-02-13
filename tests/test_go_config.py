"""Test per-repo Go config loading."""
import textwrap
from pathlib import Path

import pytest

from desloppify.lang.go.config import load_go_config


class TestLoadGoConfig:
    def test_no_config_returns_defaults(self, tmp_path):
        cfg = load_go_config(tmp_path)
        assert cfg["thresholds"]["large_file"] == 500
        assert cfg["thresholds"]["complexity"] == 20

    def test_overrides_thresholds(self, tmp_path):
        config_dir = tmp_path / ".desloppify"
        config_dir.mkdir()
        (config_dir / "go.yaml").write_text(textwrap.dedent("""\
            thresholds:
              large_file: 600
              complexity: 25
        """))
        cfg = load_go_config(tmp_path)
        assert cfg["thresholds"]["large_file"] == 600
        assert cfg["thresholds"]["complexity"] == 25

    def test_overrides_entry_patterns(self, tmp_path):
        config_dir = tmp_path / ".desloppify"
        config_dir.mkdir()
        (config_dir / "go.yaml").write_text(textwrap.dedent("""\
            entry_patterns:
              - "/lambda/"
              - "handler.go"
        """))
        cfg = load_go_config(tmp_path)
        assert "/lambda/" in cfg["entry_patterns"]
        assert "handler.go" in cfg["entry_patterns"]
        assert "main.go" in cfg["entry_patterns"]

    def test_overrides_exclusions(self, tmp_path):
        config_dir = tmp_path / ".desloppify"
        config_dir.mkdir()
        (config_dir / "go.yaml").write_text(textwrap.dedent("""\
            exclusions:
              - "dist"
        """))
        cfg = load_go_config(tmp_path)
        assert "dist" in cfg["exclusions"]
        assert "vendor" in cfg["exclusions"]
