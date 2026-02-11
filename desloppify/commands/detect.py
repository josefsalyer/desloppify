"""detect command: run a single detector directly (bypass state tracking)."""

import sys

from ..utils import c


def cmd_detect(args):
    """Run a single detector directly (bypass state tracking)."""
    # Apply --exclude to file discovery
    exclude = getattr(args, "exclude", None)
    if exclude:
        from ..utils import _find_source_files_cached
        import desloppify.utils as _utils
        _utils._extra_exclusions = tuple(exclude)
        _find_source_files_cached.cache_clear()

    detector = args.detector

    # Resolve language (from --lang flag, default to typescript)
    from ..cli import _resolve_lang
    lang = _resolve_lang(args)

    if not lang:
        # Default to TypeScript when no --lang flag is passed
        from ..lang import get_lang
        lang = get_lang("typescript")

    # Validate detector name
    if lang.detector_names and detector not in lang.detector_names:
        print(c(f"Unknown detector for {lang.name}: {detector}", "red"))
        print(f"  Available: {', '.join(sorted(lang.detector_names))}")
        sys.exit(1)

    # Check for language-specific command
    if detector not in lang.detect_commands:
        print(c(f"No command registered for {lang.name}:{detector}", "red"))
        sys.exit(1)

    # Set default thresholds for detectors that expect them
    if getattr(args, "threshold", None) is None:
        if detector == "large":
            args.threshold = lang.large_threshold
        elif detector == "dupes":
            args.threshold = 0.8

    lang.detect_commands[detector](args)
