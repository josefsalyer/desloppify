"""Test Go smell detection rules."""
import textwrap
from pathlib import Path

import pytest

import desloppify.utils as utils_mod


@pytest.fixture(autouse=True)
def _set_project_root(tmp_path, monkeypatch):
    """Point PROJECT_ROOT at the tmp directory so file resolution works."""
    monkeypatch.setenv("DESLOPPIFY_ROOT", str(tmp_path))
    monkeypatch.setattr(utils_mod, "PROJECT_ROOT", tmp_path)
    utils_mod._find_source_files_cached.cache_clear()


def _write_go(tmp_path, code, filename="main.go"):
    f = tmp_path / filename
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(textwrap.dedent(code))
    return f


class TestGoSmells:
    def test_bare_error_return(self, tmp_path):
        _write_go(tmp_path, """\
            package main
            func foo() error {
                err := doSomething()
                return err
            }
        """)
        from desloppify.lang.go.detectors.smells import detect_smells
        entries, _ = detect_smells(tmp_path)
        ids = [e["id"] for e in entries]
        assert "bare_error_return" in ids

    def test_panic_in_lib_detected(self, tmp_path):
        _write_go(tmp_path, """\
            package mylib
            func DoWork() {
                panic("oh no")
            }
        """, "lib.go")
        from desloppify.lang.go.detectors.smells import detect_smells
        entries, _ = detect_smells(tmp_path)
        ids = [e["id"] for e in entries]
        assert "panic_in_lib" in ids

    def test_panic_in_main_skipped(self, tmp_path):
        _write_go(tmp_path, """\
            package main
            func main() {
                panic("fatal")
            }
        """)
        from desloppify.lang.go.detectors.smells import detect_smells
        entries, _ = detect_smells(tmp_path)
        ids = [e["id"] for e in entries]
        assert "panic_in_lib" not in ids

    def test_defer_in_loop(self, tmp_path):
        _write_go(tmp_path, """\
            package main
            func process() {
                for _, f := range files {
                    defer f.Close()
                }
            }
        """)
        from desloppify.lang.go.detectors.smells import detect_smells
        entries, _ = detect_smells(tmp_path)
        ids = [e["id"] for e in entries]
        assert "defer_in_loop" in ids

    def test_init_function(self, tmp_path):
        _write_go(tmp_path, """\
            package main
            func init() {
                setup()
            }
        """)
        from desloppify.lang.go.detectors.smells import detect_smells
        entries, _ = detect_smells(tmp_path)
        ids = [e["id"] for e in entries]
        assert "init_function" in ids

    def test_no_smells(self, tmp_path):
        _write_go(tmp_path, """\
            package main
            func Hello() string {
                return "hello"
            }
        """)
        from desloppify.lang.go.detectors.smells import detect_smells
        entries, _ = detect_smells(tmp_path)
        assert entries == []

    def test_ignored_error(self, tmp_path):
        _write_go(tmp_path, """\
            package main
            func foo() {
                _ = doSomething()
            }
        """)
        from desloppify.lang.go.detectors.smells import detect_smells
        entries, _ = detect_smells(tmp_path)
        ids = [e["id"] for e in entries]
        assert "ignored_error" in ids

    def test_empty_error_check_single_line(self, tmp_path):
        _write_go(tmp_path, """\
            package main
            func foo() error {
                err := doSomething()
                if err != nil { return err }
                return nil
            }
        """)
        from desloppify.lang.go.detectors.smells import detect_smells
        entries, _ = detect_smells(tmp_path)
        ids = [e["id"] for e in entries]
        assert "empty_error_check" in ids

    def test_empty_error_check_multi_line(self, tmp_path):
        _write_go(tmp_path, """\
            package main
            func foo() error {
                err := doSomething()
                if err != nil {
                    return err
                }
                return nil
            }
        """)
        from desloppify.lang.go.detectors.smells import detect_smells
        entries, _ = detect_smells(tmp_path)
        ids = [e["id"] for e in entries]
        assert "empty_error_check" in ids

    def test_error_string_format(self, tmp_path):
        _write_go(tmp_path, """\
            package main
            import "errors"
            func foo() error {
                return errors.New("Something went wrong")
            }
        """)
        from desloppify.lang.go.detectors.smells import detect_smells
        entries, _ = detect_smells(tmp_path)
        ids = [e["id"] for e in entries]
        assert "error_string_format" in ids

    def test_nil_error_init(self, tmp_path):
        _write_go(tmp_path, """\
            package main
            func foo() error {
                var err error
                return err
            }
        """)
        from desloppify.lang.go.detectors.smells import detect_smells
        entries, _ = detect_smells(tmp_path)
        ids = [e["id"] for e in entries]
        assert "nil_error_init" in ids

    def test_global_mutable(self, tmp_path):
        _write_go(tmp_path, """\
            package main
            var items = []string{}
        """)
        from desloppify.lang.go.detectors.smells import detect_smells
        entries, _ = detect_smells(tmp_path)
        ids = [e["id"] for e in entries]
        assert "global_mutable" in ids

    def test_todo_fixme(self, tmp_path):
        _write_go(tmp_path, """\
            package main
            func foo() {
                // TODO fix this later
            }
        """)
        from desloppify.lang.go.detectors.smells import detect_smells
        entries, _ = detect_smells(tmp_path)
        ids = [e["id"] for e in entries]
        assert "todo_fixme" in ids

    def test_goroutine_leak(self, tmp_path):
        _write_go(tmp_path, """\
            package main
            func foo() {
                go func() {
                    doWork()
                }()
            }
        """)
        from desloppify.lang.go.detectors.smells import detect_smells
        entries, _ = detect_smells(tmp_path)
        ids = [e["id"] for e in entries]
        assert "goroutine_leak" in ids

    def test_mutex_copy(self, tmp_path):
        _write_go(tmp_path, """\
            package main
            import "sync"
            func foo(mu sync.Mutex) {
                mu.Lock()
            }
        """)
        from desloppify.lang.go.detectors.smells import detect_smells
        entries, _ = detect_smells(tmp_path)
        ids = [e["id"] for e in entries]
        assert "mutex_copy" in ids

    def test_unbuffered_channel(self, tmp_path):
        _write_go(tmp_path, """\
            package main
            func foo() {
                ch := make(chan int)
                _ = ch
            }
        """)
        from desloppify.lang.go.detectors.smells import detect_smells
        entries, _ = detect_smells(tmp_path)
        ids = [e["id"] for e in entries]
        assert "unbuffered_channel" in ids

    def test_string_concat_loop(self, tmp_path):
        _write_go(tmp_path, """\
            package main
            func foo() string {
                result := ""
                for _, s := range items {
                    result += s
                }
                return result
            }
        """)
        from desloppify.lang.go.detectors.smells import detect_smells
        entries, _ = detect_smells(tmp_path)
        ids = [e["id"] for e in entries]
        assert "string_concat_loop" in ids

    def test_regex_in_loop(self, tmp_path):
        _write_go(tmp_path, """\
            package main
            import "regexp"
            func foo() {
                for _, s := range items {
                    re := regexp.MustCompile("[0-9]+")
                    _ = re.FindString(s)
                }
            }
        """)
        from desloppify.lang.go.detectors.smells import detect_smells
        entries, _ = detect_smells(tmp_path)
        ids = [e["id"] for e in entries]
        assert "regex_in_loop" in ids

    def test_empty_interface(self, tmp_path):
        _write_go(tmp_path, """\
            package main
            func DoStuff(data interface{}) {
            }
        """)
        from desloppify.lang.go.detectors.smells import detect_smells
        entries, _ = detect_smells(tmp_path)
        ids = [e["id"] for e in entries]
        assert "empty_interface" in ids

    def test_panic_in_test_file_skipped(self, tmp_path):
        _write_go(tmp_path, """\
            package mylib
            func TestCrash() {
                panic("expected")
            }
        """, "lib_test.go")
        from desloppify.lang.go.detectors.smells import detect_smells
        entries, _ = detect_smells(tmp_path)
        ids = [e["id"] for e in entries]
        assert "panic_in_lib" not in ids

    def test_hardcoded_url(self, tmp_path):
        _write_go(tmp_path, """\
            package main
            func foo() string {
                return "https://example.com/api"
            }
        """)
        from desloppify.lang.go.detectors.smells import detect_smells
        entries, _ = detect_smells(tmp_path)
        ids = [e["id"] for e in entries]
        assert "hardcoded_url" in ids

    def test_magic_number(self, tmp_path):
        _write_go(tmp_path, """\
            package main
            func foo() bool {
                return count >= 10000
            }
        """)
        from desloppify.lang.go.detectors.smells import detect_smells
        entries, _ = detect_smells(tmp_path)
        ids = [e["id"] for e in entries]
        assert "magic_number" in ids

    def test_severity_ordering(self, tmp_path):
        """High severity smells sort before low severity."""
        _write_go(tmp_path, """\
            package mylib
            func DoWork() {
                panic("oh no")
                // TODO fix this
            }
        """, "lib.go")
        from desloppify.lang.go.detectors.smells import detect_smells
        entries, _ = detect_smells(tmp_path)
        severities = [e["severity"] for e in entries]
        sev_order = {"high": 0, "medium": 1, "low": 2}
        assert severities == sorted(severities, key=lambda s: sev_order[s])

    def test_file_count(self, tmp_path):
        """Total files checked is returned correctly."""
        _write_go(tmp_path, "package main\nfunc Hello() {}\n", "a.go")
        _write_go(tmp_path, "package main\nfunc World() {}\n", "b.go")
        from desloppify.lang.go.detectors.smells import detect_smells
        _, total = detect_smells(tmp_path)
        assert total == 2
