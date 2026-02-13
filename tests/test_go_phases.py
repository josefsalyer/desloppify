"""Test Go detection phase runners."""
import textwrap
from pathlib import Path

import pytest

from desloppify.lang import get_lang


@pytest.fixture(autouse=True)
def _set_project_root(tmp_path, monkeypatch):
    import desloppify.utils as utils_mod
    monkeypatch.setattr(utils_mod, "PROJECT_ROOT", tmp_path)
    # Also patch modules that import PROJECT_ROOT by value at import time
    import desloppify.detectors.large as large_mod
    monkeypatch.setattr(large_mod, "PROJECT_ROOT", tmp_path)
    import desloppify.lang.base as base_mod
    monkeypatch.setattr(base_mod, "PROJECT_ROOT", tmp_path)
    # Clear the LRU cache so file discovery uses the monkeypatched PROJECT_ROOT
    utils_mod._find_source_files_cached.cache_clear()


class TestGoPhases:
    def test_has_phases(self):
        lang = get_lang("go")
        assert len(lang.phases) >= 5

    def test_phase_labels(self):
        lang = get_lang("go")
        labels = [p.label for p in lang.phases]
        assert "Unused (go vet)" in labels
        assert "Structural analysis" in labels
        assert "Code smells" in labels

    def test_smell_phase_runs(self, tmp_path):
        (tmp_path / "go.mod").write_text("module test\n\ngo 1.21\n")
        (tmp_path / "main.go").write_text(textwrap.dedent("""\
            package main
            // TODO: fix this
            func main() {}
        """))
        lang = get_lang("go")
        # Find smell phase
        smell_phase = [p for p in lang.phases if "smell" in p.label.lower()][0]
        findings, potentials = smell_phase.run(tmp_path, lang)
        assert isinstance(findings, list)

    def test_unused_phase_runs(self, tmp_path):
        (tmp_path / "go.mod").write_text("module test\n\ngo 1.21\n")
        (tmp_path / "main.go").write_text("package main\n\nfunc main() {}\n")
        lang = get_lang("go")
        unused_phase = [p for p in lang.phases if "unused" in p.label.lower()][0]
        findings, potentials = unused_phase.run(tmp_path, lang)
        assert isinstance(findings, list)
        assert isinstance(potentials, dict)

    def test_structural_phase_runs(self, tmp_path):
        (tmp_path / "go.mod").write_text("module test\n\ngo 1.21\n")
        body = "\n".join(f"\tx_{i} := {i}" for i in range(600))
        (tmp_path / "big.go").write_text(f"package main\n\nfunc bigFunc() {{\n{body}\n}}\n")
        lang = get_lang("go")
        structural_phase = [p for p in lang.phases if "structural" in p.label.lower()][0]
        findings, potentials = structural_phase.run(tmp_path, lang)
        assert isinstance(findings, list)
        # Should detect the large file
        assert len(findings) > 0

    def test_coupling_phase_runs(self, tmp_path):
        (tmp_path / "go.mod").write_text("module test\n\ngo 1.21\n")
        (tmp_path / "main.go").write_text("package main\n\nfunc main() {}\n")
        lang = get_lang("go")
        coupling_phase = [p for p in lang.phases if "coupling" in p.label.lower()][0]
        findings, potentials = coupling_phase.run(tmp_path, lang)
        assert isinstance(findings, list)
        assert isinstance(potentials, dict)
