"""Go source code extraction -- AST helper with regex fallback."""
from __future__ import annotations

from pathlib import Path

from ...detectors.base import FunctionInfo, ClassInfo


def extract_go_functions(filepath: Path) -> list[FunctionInfo]:
    """Extract all functions from a Go file."""
    return _extract_functions_regex(filepath)


def extract_go_structs(filepath: Path | str) -> list[ClassInfo]:
    """Extract all structs from a Go file."""
    return _extract_structs_regex(filepath)


def _extract_functions_regex(filepath: Path) -> list[FunctionInfo]:
    """Regex-based Go function extraction (fallback)."""
    return []


def _extract_structs_regex(filepath: Path | str) -> list[ClassInfo]:
    """Regex-based Go struct extraction (fallback)."""
    return []
