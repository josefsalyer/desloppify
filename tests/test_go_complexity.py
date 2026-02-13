"""Test Go complexity signal compute functions."""
from desloppify.lang.go.detectors.complexity import (
    compute_max_params,
    compute_nesting_depth,
    compute_long_functions,
)


class TestComputeMaxParams:
    def test_many_params(self):
        code = "func Create(ctx context.Context, name string, age int, email string, phone string, addr string) error {\n\treturn nil\n}\n"
        lines = code.splitlines()
        result = compute_max_params(code, lines)
        assert result is not None
        count, label = result
        assert count == 6

    def test_few_params(self):
        code = "func Hello(name string) string {\n\treturn name\n}\n"
        lines = code.splitlines()
        result = compute_max_params(code, lines)
        assert result is None

    def test_method_params(self):
        code = "func (s *Server) Handle(ctx context.Context, req Request, opts Options, logger Logger, timeout int, retries int) error {\n\treturn nil\n}\n"
        lines = code.splitlines()
        result = compute_max_params(code, lines)
        assert result is not None
        count, _ = result
        assert count == 6


class TestComputeNestingDepth:
    def test_deep_nesting(self):
        code = """func foo() {
    if true {
        for i := 0; i < 10; i++ {
            if i > 5 {
                switch {
                case true:
                    if i > 7 {
                        doSomething()
                    }
                }
            }
        }
    }
}
"""
        lines = code.splitlines()
        result = compute_nesting_depth(code, lines)
        assert result is not None
        depth, _ = result
        assert depth > 4

    def test_shallow(self):
        code = "func foo() {\n\treturn nil\n}\n"
        lines = code.splitlines()
        result = compute_nesting_depth(code, lines)
        assert result is None


class TestComputeLongFunctions:
    def test_long_function(self):
        body_lines = ["    x := 1\n"] * 90
        code = "func Long() {\n" + "".join(body_lines) + "}\n"
        lines = code.splitlines()
        result = compute_long_functions(code, lines)
        assert result is not None
        loc, label = result
        assert loc > 80
        assert "Long" in label

    def test_short_function(self):
        code = "func Short() {\n\treturn\n}\n"
        lines = code.splitlines()
        result = compute_long_functions(code, lines)
        assert result is None
