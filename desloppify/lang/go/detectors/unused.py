"""Go unused detection via go vet with regex fallback."""
from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

from ....utils import find_source_files
from .... import utils as _utils_mod


def detect_unused(path: Path, category: str = "all") -> tuple[list[dict], int]:
    """Detect unused symbols in Go code.

    Tries ``go vet`` first, falls back to regex-based detection.
    Returns ``(entries, total_files)`` matching the Python plugin pattern.
    """
    files = find_source_files(path, [".go"])
    total = len(files)

    entries = _try_go_vet(path)
    if entries is None:
        entries = _detect_unused_regex(path, files)

    if category != "all":
        entries = [e for e in entries if e["category"] == category]

    return entries, total


def _try_go_vet(path: Path) -> list[dict] | None:
    """Try running ``go vet`` to detect unused code.

    Returns ``None`` when the tool is unavailable or unusable so the
    caller can fall back to the regex approach.
    """
    if not shutil.which("go"):
        return None

    go_mod = path / "go.mod"
    if not go_mod.exists():
        return None

    try:
        result = subprocess.run(
            ["go", "vet", "./..."],
            capture_output=True,
            text=True,
            timeout=60,
            cwd=str(path),
        )
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        return None

    entries: list[dict] = []
    # go vet output format: path/file.go:line:col: message
    line_pattern = re.compile(r"^(.+\.go):(\d+):\d+:\s+(.+)$", re.MULTILINE)

    for m in line_pattern.finditer(result.stderr):
        filepath = m.group(1)
        lineno = int(m.group(2))
        message = m.group(3)

        # Resolve to absolute path for consistent reporting
        abs_path = (path / filepath).resolve()
        abs_path_str = str(abs_path) if abs_path.exists() else filepath

        # Apply global exclusions
        if _utils_mod._extra_exclusions and any(
            _utils_mod.matches_exclusion(filepath, ex)
            for ex in _utils_mod._extra_exclusions
        ):
            continue

        cat, name = _categorise_vet_message(message)

        entries.append({
            "file": abs_path_str,
            "line": lineno,
            "name": name,
            "category": cat,
        })

    return entries


def _categorise_vet_message(message: str) -> tuple[str, str]:
    """Return ``(category, name)`` for a ``go vet`` diagnostic message."""
    lower = message.lower()

    if "imported and not used" in lower:
        pkg_m = re.search(r'"([^"]+)"', message)
        return "unused_import", pkg_m.group(1) if pkg_m else message

    if "unused" in lower:
        var_m = re.search(
            r"unused\s+(?:variable|parameter)\s+'?(\w+)'?", message, re.I
        )
        return "unused_var", var_m.group(1) if var_m else message

    return "other", message


def _detect_unused_regex(path: Path, files: list[str]) -> list[dict]:
    """Regex fallback: detect explicitly ignored errors (``_ = ...``).

    Full static analysis without Go tooling is impractical, so this
    fallback focuses on the single most valuable pattern -- assignments
    to the blank identifier that silence returned errors.
    """
    entries: list[dict] = []
    # Matches lines like:  _ = doSomething()  or  _, _ = fn()
    ignored_err_re = re.compile(r"^\s*(_\s*(?:,\s*_\s*)*)=\s*\w+")

    for filepath in files:
        try:
            p = Path(filepath)
            if not p.is_absolute():
                p = path / filepath
            content = p.read_text()
            lines = content.splitlines()
        except (OSError, UnicodeDecodeError):
            continue

        # Apply global exclusions
        if _utils_mod._extra_exclusions and any(
            _utils_mod.matches_exclusion(filepath, ex)
            for ex in _utils_mod._extra_exclusions
        ):
            continue

        for i, line in enumerate(lines):
            stripped = line.strip()

            # Skip blank lines, comments, and for-range loops
            if not stripped or stripped.startswith("//"):
                continue
            if stripped.startswith("for "):
                continue

            if ignored_err_re.match(stripped):
                # Must not be a := (short variable declaration) -- those
                # are assignments, not discards of existing values.
                if ":=" in stripped:
                    continue
                entries.append({
                    "file": filepath,
                    "line": i + 1,
                    "name": stripped[:60],
                    "category": "ignored_error",
                })

    return entries
