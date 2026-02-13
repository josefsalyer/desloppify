"""Test Go unused detection."""
import textwrap
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

import desloppify.utils as utils_mod
from desloppify.lang.go.detectors.unused import (
    detect_unused,
    _detect_unused_regex,
    _try_go_vet,
    _categorise_vet_message,
)


@pytest.fixture(autouse=True)
def _set_project_root(tmp_path, monkeypatch):
    """Point PROJECT_ROOT at tmp_path so find_source_files works."""
    monkeypatch.setattr(utils_mod, "PROJECT_ROOT", tmp_path)
    utils_mod._find_source_files_cached.cache_clear()
    yield
    utils_mod._find_source_files_cached.cache_clear()


# ── helpers ──────────────────────────────────────────────────


def _write_go(tmp_path: Path, code: str, filename: str = "main.go") -> Path:
    f = tmp_path / filename
    f.write_text(textwrap.dedent(code))
    return f


# ── _detect_unused_regex tests ───────────────────────────────


class TestGoUnusedRegex:
    def test_ignored_error(self, tmp_path):
        _write_go(tmp_path, """\
            package main
            func main() {
            \t_ = doSomething()
            }
        """)
        files = [str(tmp_path / "main.go")]
        entries = _detect_unused_regex(tmp_path, files)
        assert len(entries) >= 1
        assert entries[0]["category"] == "ignored_error"
        assert entries[0]["line"] == 3

    def test_multiple_blank_identifiers(self, tmp_path):
        _write_go(tmp_path, """\
            package main
            func main() {
            \t_, _ = twoReturns()
            }
        """)
        files = [str(tmp_path / "main.go")]
        entries = _detect_unused_regex(tmp_path, files)
        # _, _ = ... without := is an ignored error
        assert len(entries) >= 1
        assert entries[0]["category"] == "ignored_error"

    def test_short_var_decl_not_flagged(self, tmp_path):
        _write_go(tmp_path, """\
            package main
            func main() {
            \t_ := doSomething()
            }
        """)
        files = [str(tmp_path / "main.go")]
        entries = _detect_unused_regex(tmp_path, files)
        # := is a short variable declaration, not an ignored error discard
        assert entries == []

    def test_for_range_not_flagged(self, tmp_path):
        _write_go(tmp_path, """\
            package main
            func main() {
            \tfor _ = range items {
            \t}
            }
        """)
        files = [str(tmp_path / "main.go")]
        entries = _detect_unused_regex(tmp_path, files)
        assert entries == []

    def test_clean_code(self, tmp_path):
        _write_go(tmp_path, """\
            package main
            func main() {
            \tresult := doSomething()
            \tuse(result)
            }
        """)
        files = [str(tmp_path / "main.go")]
        entries = _detect_unused_regex(tmp_path, files)
        assert entries == []

    def test_comment_lines_skipped(self, tmp_path):
        _write_go(tmp_path, """\
            package main
            // _ = ignoredComment
            func main() {}
        """)
        files = [str(tmp_path / "main.go")]
        entries = _detect_unused_regex(tmp_path, files)
        assert entries == []

    def test_unreadable_file(self, tmp_path):
        """Non-existent file in file list is silently skipped."""
        entries = _detect_unused_regex(tmp_path, [str(tmp_path / "missing.go")])
        assert entries == []


# ── _categorise_vet_message tests ────────────────────────────


class TestCategoriseVetMessage:
    def test_unused_import(self):
        cat, name = _categorise_vet_message('"fmt" imported and not used')
        assert cat == "unused_import"
        assert name == "fmt"

    def test_unused_variable(self):
        cat, name = _categorise_vet_message("unused variable 'x'")
        assert cat == "unused_var"
        assert name == "x"

    def test_unused_parameter(self):
        cat, name = _categorise_vet_message("unused parameter 'ctx'")
        assert cat == "unused_var"
        assert name == "ctx"

    def test_other_message(self):
        cat, name = _categorise_vet_message("unreachable code")
        assert cat == "other"
        assert name == "unreachable code"


# ── _try_go_vet tests ───────────────────────────────────────


class TestTryGoVet:
    def test_returns_none_without_go_binary(self, tmp_path):
        with patch("desloppify.lang.go.detectors.unused.shutil.which", return_value=None):
            assert _try_go_vet(tmp_path) is None

    def test_returns_none_without_go_mod(self, tmp_path):
        with patch("desloppify.lang.go.detectors.unused.shutil.which", return_value="/usr/local/bin/go"):
            # No go.mod in tmp_path
            assert _try_go_vet(tmp_path) is None

    def test_returns_none_on_timeout(self, tmp_path):
        import subprocess
        (tmp_path / "go.mod").write_text("module example.com/test\n")
        with patch("desloppify.lang.go.detectors.unused.shutil.which", return_value="/usr/local/bin/go"), \
             patch("desloppify.lang.go.detectors.unused.subprocess.run",
                   side_effect=subprocess.TimeoutExpired(cmd="go vet", timeout=60)):
            assert _try_go_vet(tmp_path) is None

    def test_parses_stderr_output(self, tmp_path):
        (tmp_path / "go.mod").write_text("module example.com/test\n")
        _write_go(tmp_path, "package main\n")

        mock_result = MagicMock()
        mock_result.stderr = './main.go:5:2: "fmt" imported and not used\n'

        with patch("desloppify.lang.go.detectors.unused.shutil.which", return_value="/usr/local/bin/go"), \
             patch("desloppify.lang.go.detectors.unused.subprocess.run", return_value=mock_result):
            entries = _try_go_vet(tmp_path)
            assert entries is not None
            assert len(entries) == 1
            assert entries[0]["category"] == "unused_import"
            assert entries[0]["name"] == "fmt"
            assert entries[0]["line"] == 5

    def test_parses_multiple_issues(self, tmp_path):
        (tmp_path / "go.mod").write_text("module example.com/test\n")
        _write_go(tmp_path, "package main\n")

        mock_result = MagicMock()
        mock_result.stderr = (
            "./main.go:3:2: \"os\" imported and not used\n"
            "./main.go:10:5: unused variable 'err'\n"
        )

        with patch("desloppify.lang.go.detectors.unused.shutil.which", return_value="/usr/local/bin/go"), \
             patch("desloppify.lang.go.detectors.unused.subprocess.run", return_value=mock_result):
            entries = _try_go_vet(tmp_path)
            assert entries is not None
            assert len(entries) == 2
            assert entries[0]["category"] == "unused_import"
            assert entries[0]["name"] == "os"
            assert entries[1]["category"] == "unused_var"
            assert entries[1]["name"] == "err"

    def test_empty_output(self, tmp_path):
        (tmp_path / "go.mod").write_text("module example.com/test\n")

        mock_result = MagicMock()
        mock_result.stderr = ""

        with patch("desloppify.lang.go.detectors.unused.shutil.which", return_value="/usr/local/bin/go"), \
             patch("desloppify.lang.go.detectors.unused.subprocess.run", return_value=mock_result):
            entries = _try_go_vet(tmp_path)
            assert entries is not None
            assert entries == []


# ── detect_unused integration tests ─────────────────────────


class TestGoUnusedDetect:
    def test_returns_tuple(self, tmp_path):
        _write_go(tmp_path, "package main\n")
        entries, total = detect_unused(tmp_path)
        assert isinstance(entries, list)
        assert isinstance(total, int)
        assert total >= 1

    def test_total_counts_go_files(self, tmp_path):
        _write_go(tmp_path, "package main\n", "a.go")
        _write_go(tmp_path, "package main\n", "b.go")
        _write_go(tmp_path, "package main\n", "c.go")
        _, total = detect_unused(tmp_path)
        assert total == 3

    def test_category_filter(self, tmp_path):
        """Category filter removes non-matching entries."""
        _write_go(tmp_path, """\
            package main
            func main() {
            \t_ = doSomething()
            }
        """)
        # Without go vet, falls back to regex which produces "ignored_error"
        with patch("desloppify.lang.go.detectors.unused._try_go_vet", return_value=None):
            entries_all, _ = detect_unused(tmp_path, category="all")
            entries_err, _ = detect_unused(tmp_path, category="ignored_error")
            entries_imp, _ = detect_unused(tmp_path, category="unused_import")

        assert len(entries_all) >= 1
        assert len(entries_err) >= 1
        assert entries_imp == []

    def test_fallback_when_go_vet_unavailable(self, tmp_path):
        """When _try_go_vet returns None, regex fallback is used."""
        _write_go(tmp_path, """\
            package main
            func main() {
            \t_ = doSomething()
            }
        """)
        with patch("desloppify.lang.go.detectors.unused._try_go_vet", return_value=None):
            entries, _ = detect_unused(tmp_path)
        assert len(entries) >= 1
        assert entries[0]["category"] == "ignored_error"

    def test_go_vet_results_used_when_available(self, tmp_path):
        """When _try_go_vet returns entries, regex fallback is not called."""
        _write_go(tmp_path, "package main\n")
        vet_entries = [{"file": "main.go", "line": 3, "name": "fmt", "category": "unused_import"}]

        with patch("desloppify.lang.go.detectors.unused._try_go_vet", return_value=vet_entries) as mock_vet, \
             patch("desloppify.lang.go.detectors.unused._detect_unused_regex") as mock_regex:
            entries, _ = detect_unused(tmp_path)

        mock_vet.assert_called_once()
        mock_regex.assert_not_called()
        assert entries == vet_entries
