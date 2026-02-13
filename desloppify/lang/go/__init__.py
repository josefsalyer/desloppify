"""Go language configuration for desloppify."""
from __future__ import annotations

from pathlib import Path

from .. import register_lang
from ..base import DetectorPhase, LangConfig, phase_dupes
from ...detectors.base import ComplexitySignal, GodRule
from ...utils import find_source_files, log
from ...zones import ZoneRule, Zone, COMMON_ZONE_RULES


def find_go_files(path: str | Path) -> list[str]:
    """Find all .go files under a path, excluding test files."""
    return find_source_files(path, [".go"])


# -- Zone classification rules --

GO_ZONE_RULES = [
    ZoneRule(Zone.GENERATED, [".pb.go", "_pb2.go", "_string.go"]),
    ZoneRule(Zone.TEST, ["_test.go", "/testdata/", "/testutil/"]),
    ZoneRule(Zone.CONFIG, ["go.mod", "go.sum"]),
] + COMMON_ZONE_RULES

GO_ENTRY_PATTERNS = [
    "main.go", "/cmd/", "_test.go", "/testdata/",
    "/lambda/", "handler.go", "/migrations/",
    ".pb.go", "_gen.go", "_mock.go", "doc.go",
]

GO_EXCLUSIONS = ["vendor", ".git", "testdata", "bin"]


def _get_go_area(filepath: str) -> str:
    """Derive area name from Go file path for grouping."""
    parts = filepath.split("/")
    if len(parts) > 2:
        return "/".join(parts[:2])
    return parts[0] if parts else filepath


def _go_build_dep_graph(path: Path) -> dict:
    from .detectors.deps import build_dep_graph
    return build_dep_graph(path)


def _go_extract_functions(path: Path) -> list:
    from .extractors import extract_go_functions
    functions = []
    for filepath in find_go_files(path):
        functions.extend(extract_go_functions(filepath))
    return functions


@register_lang("go")
class GoConfig(LangConfig):
    def __init__(self):
        from .commands import get_detect_commands
        super().__init__(
            name="go",
            extensions=[".go"],
            exclusions=GO_EXCLUSIONS,
            default_src=".",
            build_dep_graph=_go_build_dep_graph,
            entry_patterns=GO_ENTRY_PATTERNS,
            barrel_names=set(),
            phases=[],  # Added in later tasks
            fixers={},
            get_area=_get_go_area,
            detect_commands=get_detect_commands(),
            boundaries=[],
            typecheck_cmd="",
            file_finder=find_go_files,
            large_threshold=500,
            complexity_threshold=20,
            extract_functions=_go_extract_functions,
            zone_rules=GO_ZONE_RULES,
        )
