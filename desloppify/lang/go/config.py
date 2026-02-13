"""Per-repo Go configuration loader."""
from __future__ import annotations

import copy
from pathlib import Path

import yaml


GO_DEFAULTS = {
    "zones": {
        "generated": ["_gen.go", "_mock.go", "_string.go"],
        "test": ["/testutil/"],
        "config": ["Makefile", "Dockerfile"],
        "script": ["/tools/"],
    },
    "entry_patterns": [
        "main.go", "/cmd/", "_test.go", "/testdata/",
        "/lambda/", "handler.go", "/migrations/",
        ".pb.go", "_gen.go", "_mock.go", "doc.go",
    ],
    "exclusions": ["vendor", ".git", "testdata", "bin"],
    "boundaries": [],
    "thresholds": {
        "large_file": 500,
        "complexity": 20,
        "monster_function": 150,
    },
}


def load_go_config(project_root: Path) -> dict:
    """Load Go config, merging per-repo overrides with defaults."""
    config = copy.deepcopy(GO_DEFAULTS)
    config_file = project_root / ".desloppify" / "go.yaml"
    if config_file.exists():
        try:
            overrides = yaml.safe_load(config_file.read_text()) or {}
        except Exception:
            return config
        _merge_config(config, overrides)
    return config


def _merge_config(base: dict, overrides: dict) -> None:
    """Merge overrides into base. Lists are extended, dicts are recursive, scalars replaced."""
    for key, value in overrides.items():
        if key not in base:
            base[key] = value
        elif isinstance(base[key], dict) and isinstance(value, dict):
            _merge_config(base[key], value)
        elif isinstance(base[key], list) and isinstance(value, list):
            for item in value:
                if item not in base[key]:
                    base[key].append(item)
        else:
            base[key] = value
