"""Go auto-fixers for mechanical cleanup tasks."""

from .error_wrap import detect_bare_errors, fix_error_wrap
from .error_strings import detect_error_strings, fix_error_strings
from .regex_hoist import detect_regex_in_loop, fix_regex_hoist
from .string_builder import detect_string_concat, fix_string_builder
from .mutex_pointer import detect_mutex_copy, fix_mutex_pointer

__all__ = [
    "detect_bare_errors", "fix_error_wrap",
    "detect_error_strings", "fix_error_strings",
    "detect_regex_in_loop", "fix_regex_hoist",
    "detect_string_concat", "fix_string_builder",
    "detect_mutex_copy", "fix_mutex_pointer",
]
