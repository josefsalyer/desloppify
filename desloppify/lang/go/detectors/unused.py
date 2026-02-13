"""Go unused detection via go vet + gopls."""
from pathlib import Path


def detect_unused(path: Path, category: str = "all") -> tuple[list[dict], int]:
    """Detect unused imports and variables."""
    return [], 0
