"""Test Go function and struct extraction."""
import textwrap
from pathlib import Path

import pytest

from desloppify.lang.go.extractors import extract_go_functions, extract_go_structs


def _write_go(tmp_path: Path, code: str, filename: str = "main.go") -> Path:
    f = tmp_path / filename
    f.write_text(textwrap.dedent(code))
    return f


class TestExtractGoFunctions:
    def test_simple_function(self, tmp_path):
        f = _write_go(tmp_path, """\
            package main

            func Hello(name string) string {
            \treturn "Hello, " + name
            }
        """)
        funcs = extract_go_functions(f)
        assert len(funcs) == 1
        assert funcs[0].name == "Hello"
        assert funcs[0].params == ["name"]
        assert funcs[0].loc >= 2

    def test_method_with_receiver(self, tmp_path):
        f = _write_go(tmp_path, """\
            package main

            type Server struct{}

            func (s *Server) Start() error {
            \treturn nil
            }
        """)
        funcs = extract_go_functions(f)
        assert len(funcs) == 1
        assert funcs[0].name == "Start"

    def test_multiline_params(self, tmp_path):
        f = _write_go(tmp_path, """\
            package main

            func Create(
            \tctx context.Context,
            \tname string,
            \tage int,
            ) error {
            \treturn nil
            }
        """)
        funcs = extract_go_functions(f)
        assert len(funcs) == 1
        assert "ctx" in funcs[0].params

    def test_empty_file(self, tmp_path):
        f = _write_go(tmp_path, "package main\n")
        funcs = extract_go_functions(f)
        assert funcs == []


class TestExtractGoStructs:
    def test_simple_struct(self, tmp_path):
        f = _write_go(tmp_path, """\
            package main

            type User struct {
            \tName  string
            \tEmail string
            \tAge   int
            }
        """)
        structs = extract_go_structs(f)
        assert len(structs) == 1
        assert structs[0].name == "User"
        assert len(structs[0].attributes) == 3
        assert "Name" in structs[0].attributes

    def test_struct_with_embedded(self, tmp_path):
        f = _write_go(tmp_path, """\
            package main

            type Admin struct {
            \tUser
            \tRole string
            }
        """)
        structs = extract_go_structs(f)
        assert len(structs) == 1
        assert "User" in structs[0].base_classes
