"""Go detect-subcommand wrappers + command registry."""
from __future__ import annotations

from pathlib import Path

from ...utils import c, display_entries, print_table, rel
from . import find_go_files, GO_ENTRY_PATTERNS
from ..commands_base import (make_cmd_large, make_cmd_single_use,
                             make_cmd_smells, make_cmd_facade)


def _build_dep_graph(path):
    from .detectors.deps import build_dep_graph
    return build_dep_graph(path)


# Shared command factories
cmd_large = make_cmd_large(find_go_files, default_threshold=500)

cmd_single_use = make_cmd_single_use(_build_dep_graph, barrel_names=set())


def _detect_go_smells(path):
    from .detectors.smells import detect_smells
    return detect_smells(path)

cmd_smells = make_cmd_smells(_detect_go_smells)

cmd_facade = make_cmd_facade(_build_dep_graph, lang="go")


def cmd_complexity(args):
    from ...detectors.complexity import detect_complexity
    from .detectors.complexity import (compute_max_params, compute_nesting_depth,
                                       compute_long_functions)
    from ...detectors.base import ComplexitySignal

    go_complexity_signals = [
        ComplexitySignal("if_else", r"\bif\b.*\belse\b", weight=1),
        ComplexitySignal("switch", r"\bswitch\b", weight=2),
        ComplexitySignal("select", r"\bselect\b", weight=2),
        ComplexitySignal("goroutine", r"\bgo\s+\w", weight=2),
        ComplexitySignal("channel_op", r"<-", weight=1),
        ComplexitySignal("nested_func", r"\bfunc\s*\(", weight=2),
        ComplexitySignal("max_params", compute=compute_max_params, weight=3, threshold=5),
        ComplexitySignal("nesting_depth", compute=compute_nesting_depth, weight=3, threshold=4),
        ComplexitySignal("long_function", compute=compute_long_functions, weight=2, threshold=80),
    ]

    entries, _ = detect_complexity(Path(args.path), signals=go_complexity_signals,
                                   file_finder=find_go_files, threshold=20)
    display_entries(args, entries,
        label="Complexity signals",
        empty_msg="No significant complexity signals found.",
        columns=["File", "LOC", "Score", "Signals"], widths=[55, 5, 6, 45],
        row_fn=lambda e: [rel(e["file"]), str(e["loc"]), str(e["score"]),
                          ", ".join(e["signals"][:4])])


def cmd_gods(args):
    from ...detectors.gods import detect_gods
    from ...detectors.base import GodRule
    from .extractors import extract_go_structs

    go_god_rules = [
        GodRule("loc", "lines of code", extract=lambda c: c.loc, threshold=500),
        GodRule("methods", "methods", extract=lambda c: len(c.methods), threshold=15),
        GodRule("fields", "fields", extract=lambda c: len(c.attributes), threshold=20),
        GodRule("embedded", "embedded types", extract=lambda c: len(c.base_classes), threshold=5),
    ]

    all_structs = []
    for filepath in find_go_files(Path(args.path)):
        all_structs.extend(extract_go_structs(filepath))
    entries, _ = detect_gods(all_structs, go_god_rules)
    display_entries(args, entries,
        label="God structs",
        empty_msg="No god structs found.",
        columns=["File", "Struct", "LOC", "Why"], widths=[50, 20, 5, 40],
        row_fn=lambda e: [rel(e["file"]), e["name"], str(e["loc"]),
                          ", ".join(e["reasons"])])


def cmd_orphaned(args):
    import json
    from .detectors.deps import build_dep_graph
    from ...detectors.orphaned import detect_orphaned_files
    graph = build_dep_graph(Path(args.path))
    entries, _ = detect_orphaned_files(
        Path(args.path), graph, extensions=[".go"],
        extra_entry_patterns=GO_ENTRY_PATTERNS,
        extra_barrel_names=set())
    if getattr(args, "json", False):
        print(json.dumps({"count": len(entries), "entries": [
            {"file": rel(e["file"]), "loc": e["loc"]} for e in entries
        ]}, indent=2))
        return
    if not entries:
        print(c("\nNo orphaned files found.", "green"))
        return
    total_loc = sum(e["loc"] for e in entries)
    print(c(f"\nOrphaned files: {len(entries)} files, {total_loc} LOC\n", "bold"))
    top = getattr(args, "top", 20)
    rows = [[rel(e["file"]), str(e["loc"])] for e in entries[:top]]
    print_table(["File", "LOC"], rows, [80, 6])


def cmd_unused(args):
    import json
    from .detectors.unused import detect_unused
    entries, _ = detect_unused(Path(args.path))
    if getattr(args, "json", False):
        print(json.dumps({"count": len(entries), "entries": entries}, indent=2))
        return
    if not entries:
        print(c("No unused symbols found.", "green"))
        return
    print(c(f"\nUnused symbols: {len(entries)}\n", "bold"))
    for e in entries[:getattr(args, "top", 20)]:
        print(f"  {rel(e['file'])}:{e['line']}  {e['category']}: {e['name']}")


def cmd_deps(args):
    import json
    from .detectors.deps import build_dep_graph
    graph = build_dep_graph(Path(args.path))
    if getattr(args, "json", False):
        print(json.dumps({"files": len(graph)}, indent=2))
        return
    print(c(f"\nGo dependency graph: {len(graph)} files\n", "bold"))
    by_importers = sorted(graph.items(), key=lambda x: -x[1]["importer_count"])
    print(c("Most imported:", "bold"))
    for filepath, entry in by_importers[:15]:
        print(f"  {rel(filepath):60s}  {entry['importer_count']:3d} importers  {len(entry['imports']):3d} imports")


def cmd_cycles(args):
    import json
    from .detectors.deps import build_dep_graph
    from ...detectors.graph import detect_cycles
    graph = build_dep_graph(Path(args.path))
    cycles, _ = detect_cycles(graph)
    if getattr(args, "json", False):
        print(json.dumps({"count": len(cycles), "cycles": cycles}, indent=2))
        return
    if not cycles:
        print(c("No import cycles found.", "green"))
        return
    print(c(f"\nImport cycles: {len(cycles)}\n", "bold"))
    for cy in cycles[:getattr(args, "top", 20)]:
        files = [rel(f) for f in cy["files"]]
        print(f"  [{cy['length']} files] {' -> '.join(files[:6])}"
              + (f" -> +{len(files) - 6}" if len(files) > 6 else ""))


def cmd_dupes(args):
    import json
    from ...detectors.dupes import detect_duplicates
    from .extractors import extract_go_functions
    functions = []
    for filepath in find_go_files(Path(args.path)):
        functions.extend(extract_go_functions(filepath))
    entries, _ = detect_duplicates(functions, threshold=getattr(args, "threshold", None) or 0.8)
    if getattr(args, "json", False):
        print(json.dumps({"count": len(entries), "entries": entries}, indent=2))
        return
    if not entries:
        print(c("No duplicate functions found.", "green"))
        return
    print(c(f"\nDuplicate functions: {len(entries)} pairs\n", "bold"))
    rows = []
    for e in entries[:getattr(args, "top", 20)]:
        a, b = e["fn_a"], e["fn_b"]
        rows.append([
            f"{a['name']} ({rel(a['file'])}:{a['line']})",
            f"{b['name']} ({rel(b['file'])}:{b['line']})",
            f"{e['similarity']:.0%}", e["kind"],
        ])
    print_table(["Function A", "Function B", "Sim", "Kind"], rows, [40, 40, 5, 14])


# -- Command registry --

def get_detect_commands() -> dict[str, callable]:
    """Build the Go detector command registry."""
    return {
        "unused":      cmd_unused,
        "large":       cmd_large,
        "complexity":  cmd_complexity,
        "gods":        cmd_gods,
        "smells":      cmd_smells,
        "dupes":       cmd_dupes,
        "deps":        cmd_deps,
        "cycles":      cmd_cycles,
        "orphaned":    cmd_orphaned,
        "single-use":  cmd_single_use,
        "facade":      cmd_facade,
    }
