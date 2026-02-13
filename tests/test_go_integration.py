"""End-to-end integration test for Go language plugin."""
import textwrap
from pathlib import Path

import pytest

from desloppify.lang import get_lang, auto_detect_lang
from desloppify.plan import generate_findings


@pytest.fixture(autouse=True)
def _set_project_root(tmp_path, monkeypatch):
    import desloppify.utils as utils_mod
    monkeypatch.setattr(utils_mod, "PROJECT_ROOT", tmp_path)
    import desloppify.detectors.large as large_mod
    monkeypatch.setattr(large_mod, "PROJECT_ROOT", tmp_path)
    import desloppify.lang.base as base_mod
    monkeypatch.setattr(base_mod, "PROJECT_ROOT", tmp_path)
    utils_mod._find_source_files_cached.cache_clear()


def _create_go_project(tmp_path):
    """Create a Go project with known issues."""
    (tmp_path / "go.mod").write_text("module example.com/test\n\ngo 1.21\n")
    (tmp_path / "main.go").write_text(textwrap.dedent("""\
        package main

        import "fmt"

        // TODO: clean this up
        func main() {
        \t_ = doSomething()
        \tfmt.Println("hello")
        }

        func doSomething() error {
        \treturn nil
        }
    """))
    # Large file
    body = "\n".join(f"\tx_{i} := {i}" for i in range(600))
    (tmp_path / "big.go").write_text(f"package main\n\nfunc bigFunc() {{\n{body}\n}}\n")
    return tmp_path


class TestGoIntegration:
    def test_auto_detects_go(self, tmp_path):
        _create_go_project(tmp_path)
        assert auto_detect_lang(tmp_path) == "go"

    def test_generate_findings(self, tmp_path):
        _create_go_project(tmp_path)
        lang = get_lang("go")
        findings, potentials = generate_findings(
            tmp_path, include_slow=False, lang=lang)
        assert isinstance(findings, list)
        assert isinstance(potentials, dict)

    def test_finds_known_issues(self, tmp_path):
        _create_go_project(tmp_path)
        lang = get_lang("go")
        findings, _ = generate_findings(
            tmp_path, include_slow=False, lang=lang)
        # Should find at least smells (todo_fixme, ignored_error) and structural (large file)
        assert len(findings) > 0

    def test_zone_classification(self, tmp_path):
        _create_go_project(tmp_path)
        (tmp_path / "main_test.go").write_text("package main\n")
        (tmp_path / "gen.pb.go").write_text("package main\n")
        lang = get_lang("go")
        from desloppify.zones import classify_file
        assert classify_file("main_test.go", lang.zone_rules).value == "test"
        assert classify_file("gen.pb.go", lang.zone_rules).value == "generated"
        assert classify_file("main.go", lang.zone_rules).value == "production"
