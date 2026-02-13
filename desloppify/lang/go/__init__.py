"""Go language configuration for desloppify."""
from __future__ import annotations

import os
from pathlib import Path

from .. import register_lang
from ..base import (DetectorPhase, FixerConfig, LangConfig,
                    add_structural_signal, merge_structural_signals,
                    make_single_use_findings, make_cycle_findings,
                    make_orphaned_findings, make_smell_findings,
                    make_facade_findings, phase_dupes)
from ...detectors.base import ComplexitySignal, GodRule
from ...utils import find_source_files, log
from ...zones import ZoneRule, Zone, COMMON_ZONE_RULES, adjust_potential, filter_entries
from .detectors.complexity import compute_max_params, compute_nesting_depth, compute_long_functions


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


# -- Config data --

GO_COMPLEXITY_SIGNALS = [
    ComplexitySignal("imports", r'^\t"', weight=1, threshold=15),
    ComplexitySignal("many_params", None, weight=2, threshold=6, compute=compute_max_params),
    ComplexitySignal("deep_nesting", None, weight=3, threshold=5, compute=compute_nesting_depth),
    ComplexitySignal("long_functions", None, weight=1, threshold=80, compute=compute_long_functions),
    ComplexitySignal("goroutines", r"go\s+(?:func\b|\w+\()", weight=2, threshold=5),
    ComplexitySignal("TODOs", r"//\s*(?:TODO|FIXME|HACK|XXX)", weight=2, threshold=0),
    ComplexitySignal("type_switches", r"switch\s+.*\.\(type\)", weight=1, threshold=3),
]

GO_GOD_RULES = [
    GodRule("methods", "methods", lambda c: len(c.methods), 15),
    GodRule("fields", "fields (attributes)", lambda c: len(c.attributes), 12),
    GodRule("embedded", "embedded types", lambda c: len(c.base_classes), 4),
    GodRule("long_methods", "long methods (>50 LOC)",
            lambda c: sum(1 for m in c.methods if m.loc > 50), 2),
]

GO_SKIP_NAMES: set[str] = set()


def _get_go_area(filepath: str) -> str:
    """Derive area name from Go file path for grouping."""
    parts = filepath.split("/")
    if len(parts) > 2:
        return "/".join(parts[:2])
    return parts[0] if parts else filepath


# -- Phase runners --


def _phase_unused(path: Path, lang: LangConfig) -> tuple[list[dict], dict[str, int]]:
    from .detectors.unused import detect_unused
    from ..base import make_unused_findings
    entries, total_files = detect_unused(path)
    return make_unused_findings(entries, log), {
        "unused": adjust_potential(lang._zone_map, total_files),
    }


def _phase_structural(path: Path, lang: LangConfig) -> tuple[list[dict], dict[str, int]]:
    """Merge large + complexity + god structs into structural findings."""
    from ...detectors.large import detect_large_files
    from ...detectors.complexity import detect_complexity
    from ...detectors.gods import detect_gods
    from ...detectors.flat_dirs import detect_flat_dirs
    from .extractors import extract_go_structs

    structural: dict[str, dict] = {}

    large_entries, file_count = detect_large_files(path, file_finder=lang.file_finder,
                                                    threshold=lang.large_threshold)
    for e in large_entries:
        add_structural_signal(structural, e["file"], f"large ({e['loc']} LOC)",
                              {"loc": e["loc"]})

    complexity_entries, _ = detect_complexity(path, signals=GO_COMPLEXITY_SIGNALS,
                                              file_finder=lang.file_finder,
                                              threshold=lang.complexity_threshold)
    for e in complexity_entries:
        add_structural_signal(structural, e["file"], f"complexity score {e['score']}",
                              {"complexity_score": e["score"],
                               "complexity_signals": e["signals"]})

    # God struct detection: collect structs from all files
    all_structs = []
    for filepath in find_go_files(path):
        all_structs.extend(extract_go_structs(filepath))
    god_entries, god_count = detect_gods(all_structs, GO_GOD_RULES)
    for e in god_entries:
        add_structural_signal(structural, e["file"], e["signal_text"], e["detail"])

    results = merge_structural_signals(structural, log)

    # Flat directories
    from ...state import make_finding
    flat_entries, dir_count = detect_flat_dirs(path, file_finder=lang.file_finder)
    for e in flat_entries:
        results.append(make_finding(
            "flat_dirs", e["directory"], "",
            tier=3, confidence="medium",
            summary=f"Flat directory: {e['file_count']} files — consider grouping by domain",
            detail={"file_count": e["file_count"]},
        ))
    if flat_entries:
        log(f"         flat dirs: {len(flat_entries)} directories with 20+ files")

    potentials = {
        "structural": adjust_potential(lang._zone_map, file_count),
        "flat_dirs": dir_count,
    }
    return results, potentials


def _phase_coupling(path: Path, lang: LangConfig) -> tuple[list[dict], dict[str, int]]:
    from .detectors.deps import build_dep_graph
    from ...detectors.graph import detect_cycles
    from ...detectors.orphaned import detect_orphaned_files
    from ...detectors.single_use import detect_single_use_abstractions
    from ...detectors.facade import detect_reexport_facades

    graph = build_dep_graph(path)
    lang._dep_graph = graph
    zm = lang._zone_map

    single_entries, single_candidates = detect_single_use_abstractions(
        path, graph, barrel_names=lang.barrel_names)
    single_entries = filter_entries(zm, single_entries, "single_use")
    results = make_single_use_findings(single_entries, lang.get_area,
                                       skip_dir_names={"cmd"}, stderr_fn=log)

    cycle_entries, _ = detect_cycles(graph)
    cycle_entries = filter_entries(zm, cycle_entries, "cycles", file_key="files")
    results.extend(make_cycle_findings(cycle_entries, log))

    orphan_entries, total_graph_files = detect_orphaned_files(
        path, graph, extensions=lang.extensions,
        extra_entry_patterns=lang.entry_patterns,
        extra_barrel_names=lang.barrel_names)
    orphan_entries = filter_entries(zm, orphan_entries, "orphaned")
    results.extend(make_orphaned_findings(orphan_entries, log))

    facade_entries, _ = detect_reexport_facades(graph, lang="go")
    facade_entries = filter_entries(zm, facade_entries, "facade")
    results.extend(make_facade_findings(facade_entries, log))

    log(f"         -> {len(results)} coupling/structural findings total")
    potentials = {
        "single_use": adjust_potential(zm, single_candidates),
        "cycles": adjust_potential(zm, total_graph_files),
        "orphaned": adjust_potential(zm, total_graph_files),
        "facade": adjust_potential(zm, total_graph_files),
    }
    return results, potentials


def _phase_smells(path: Path, lang: LangConfig) -> tuple[list[dict], dict[str, int]]:
    from .detectors.smells import detect_smells
    from ...detectors.signature import detect_signature_variance
    from ...state import make_finding
    entries, total_files = detect_smells(path)
    results = make_smell_findings(entries, log)

    # Cross-file: signature variance
    functions = lang.extract_functions(path) if lang.extract_functions else []
    sig_entries, _ = detect_signature_variance(functions)
    for e in sig_entries:
        results.append(make_finding(
            "smells", e["files"][0], f"sig_variance::{e['name']}",
            tier=3, confidence="medium",
            summary=f"Signature variance: {e['name']}() has {e['signature_count']} "
                    f"different signatures across {e['file_count']} files",
            detail={"function": e["name"], "file_count": e["file_count"],
                    "signature_count": e["signature_count"],
                    "variants": e["variants"][:5]},
        ))
    if sig_entries:
        log(f"         signature variance: {len(sig_entries)} functions with inconsistent signatures")

    return results, {
        "smells": adjust_potential(lang._zone_map, total_files),
    }


def _find_external_test_files(path: Path) -> set[str]:
    """Find test files in standard locations outside the scanned path."""
    from ...utils import PROJECT_ROOT
    extra = set()
    for test_dir in ("tests", "test"):
        d = PROJECT_ROOT / test_dir
        if not d.is_dir():
            continue
        try:
            d.resolve().relative_to(path.resolve())
            continue
        except ValueError:
            pass
        for root, _, files in os.walk(d):
            for f in files:
                if f.endswith("_test.go"):
                    extra.add(os.path.join(root, f))
    return extra


def _phase_test_coverage(path: Path, lang: LangConfig) -> tuple[list[dict], dict[str, int]]:
    from ...detectors.test_coverage import detect_test_coverage
    from ...state import make_finding

    zm = lang._zone_map
    if zm is None:
        return [], {}

    graph = lang._dep_graph or lang.build_dep_graph(path)
    extra = _find_external_test_files(path)
    entries, potential = detect_test_coverage(graph, zm, lang.name,
                                              extra_test_files=extra or None)
    entries = filter_entries(zm, entries, "test_coverage")

    results = []
    for e in entries:
        results.append(make_finding(
            "test_coverage", e["file"], e.get("name", ""),
            tier=e["tier"], confidence=e["confidence"],
            summary=e["summary"], detail=e.get("detail", {}),
        ))

    if results:
        log(f"         test coverage: {len(results)} findings ({potential} production files)")
    else:
        log(f"         test coverage: clean ({potential} production files)")

    return results, {"test_coverage": potential}


# -- Build the config --


def _go_build_dep_graph(path: Path) -> dict:
    from .detectors.deps import build_dep_graph
    return build_dep_graph(path)


def _go_extract_functions(path: Path) -> list:
    from .extractors import extract_go_functions
    functions = []
    for filepath in find_go_files(path):
        functions.extend(extract_go_functions(filepath))
    return functions


def _get_go_fixers() -> dict[str, FixerConfig]:
    """Build the Go fixer registry (lazy-loaded)."""
    _imp = lambda mod, fn: getattr(
        __import__(f"desloppify.lang.go.fixers.{mod}", fromlist=[fn]), fn)
    return {
        "error-wrap": FixerConfig(
            label="bare error returns",
            detect=lambda p: _imp("error_wrap", "detect_bare_errors")(p),
            fix=lambda e, **kw: _imp("error_wrap", "fix_error_wrap")(e, **kw),
            detector="smells",
            verb="Wrapped", dry_verb="Would wrap",
        ),
        "error-strings": FixerConfig(
            label="error string format",
            detect=lambda p: _imp("error_strings", "detect_error_strings")(p),
            fix=lambda e, **kw: _imp("error_strings", "fix_error_strings")(e, **kw),
            detector="smells",
            verb="Fixed", dry_verb="Would fix",
        ),
        "regex-hoist": FixerConfig(
            label="regex in loop",
            detect=lambda p: _imp("regex_hoist", "detect_regex_in_loop")(p),
            fix=lambda e, **kw: _imp("regex_hoist", "fix_regex_hoist")(e, **kw),
            detector="smells",
            verb="Hoisted", dry_verb="Would hoist",
        ),
        "string-builder": FixerConfig(
            label="string concat in loop",
            detect=lambda p: _imp("string_builder", "detect_string_concat")(p),
            fix=lambda e, **kw: _imp("string_builder", "fix_string_builder")(e, **kw),
            detector="smells",
            verb="Replaced", dry_verb="Would replace",
        ),
        "mutex-pointer": FixerConfig(
            label="mutex by value",
            detect=lambda p: _imp("mutex_pointer", "detect_mutex_copy")(p),
            fix=lambda e, **kw: _imp("mutex_pointer", "fix_mutex_pointer")(e, **kw),
            detector="smells",
            verb="Fixed", dry_verb="Would fix",
        ),
    }


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
            phases=[
                DetectorPhase("Unused (go vet)", _phase_unused),
                DetectorPhase("Structural analysis", _phase_structural),
                DetectorPhase("Coupling + cycles + orphaned", _phase_coupling),
                DetectorPhase("Test coverage", _phase_test_coverage),
                DetectorPhase("Code smells", _phase_smells),
                DetectorPhase("Duplicates", phase_dupes, slow=True),
            ],
            fixers=_get_go_fixers(),
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
