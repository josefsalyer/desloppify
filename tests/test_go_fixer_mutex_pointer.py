"""Test mutex-pointer fixer: change sync.Mutex value param to pointer."""
import textwrap

import pytest


@pytest.fixture(autouse=True)
def _set_project_root(tmp_path, monkeypatch):
    import desloppify.utils as utils_mod
    monkeypatch.setattr(utils_mod, "PROJECT_ROOT", tmp_path)
    import desloppify.lang.base as base_mod
    monkeypatch.setattr(base_mod, "PROJECT_ROOT", tmp_path)
    import desloppify.lang.go.fixers.common as go_common_mod
    monkeypatch.setattr(go_common_mod, "PROJECT_ROOT", tmp_path)
    utils_mod._find_source_files_cached.cache_clear()


@pytest.fixture
def go_file_mutex_copy(tmp_path):
    (tmp_path / "go.mod").write_text("module test\n\ngo 1.21\n")
    content = textwrap.dedent("""\
        package main

        import "sync"

        func withLock(mu sync.Mutex) {
        \tmu.Lock()
        \tdefer mu.Unlock()
        }

        func alreadyPointer(mu *sync.Mutex) {
        \tmu.Lock()
        \tdefer mu.Unlock()
        }

        func multiParam(name string, mu sync.Mutex, count int) {
        \tmu.Lock()
        \tdefer mu.Unlock()
        }
    """)
    f = tmp_path / "lock.go"
    f.write_text(content)
    return f


class TestDetectMutexCopy:
    def test_detects_value_mutex(self, go_file_mutex_copy):
        from desloppify.lang.go.fixers.mutex_pointer import detect_mutex_copy
        entries = detect_mutex_copy(go_file_mutex_copy.parent)
        # The smell regex matches any func param containing sync.Mutex,
        # including *sync.Mutex (the \b boundary matches after *).
        # The fixer is responsible for skipping already-pointer params.
        lines = {e["line"] for e in entries}
        assert 5 in lines
        assert 15 in lines
        # Detector also picks up line 10 (*sync.Mutex) -- the fixer handles filtering
        assert 10 in lines


class TestFixMutexPointer:
    def test_adds_pointer(self, go_file_mutex_copy):
        from desloppify.lang.go.fixers.mutex_pointer import detect_mutex_copy, fix_mutex_pointer
        entries = detect_mutex_copy(go_file_mutex_copy.parent)
        fix_mutex_pointer(entries, dry_run=False)
        content = go_file_mutex_copy.read_text()
        assert "mu *sync.Mutex" in content
        # The already-pointer one should be unchanged
        assert content.count("*sync.Mutex") == 3  # two fixed + one original

    def test_dry_run(self, go_file_mutex_copy):
        from desloppify.lang.go.fixers.mutex_pointer import detect_mutex_copy, fix_mutex_pointer
        entries = detect_mutex_copy(go_file_mutex_copy.parent)
        original = go_file_mutex_copy.read_text()
        fix_mutex_pointer(entries, dry_run=True)
        assert go_file_mutex_copy.read_text() == original
