"""Go-specific complexity signal compute functions.

Used by ComplexitySignal definitions in __init__.py for the structural phase.
"""
import re


def compute_max_params(content: str, lines: list[str]) -> tuple[int, str] | None:
    """Find the Go function with the most parameters. Returns (count, label) or None."""
    func_re = re.compile(r"^func\s+(?:\([^)]+\)\s+)?\w+\s*\(", re.MULTILINE)
    max_params = 0
    for m in func_re.finditer(content):
        # Track paren depth to find matching close-paren
        depth = 1
        start = m.end()
        i = start
        while i < len(content) and depth > 0:
            ch = content[i]
            if ch == "(":
                depth += 1
            elif ch == ")":
                depth -= 1
            i += 1
        if depth != 0:
            continue
        param_str = content[start:i - 1]
        # Go params: "name type, name2 type2" — count commas + 1 if non-empty
        param_str = param_str.strip()
        if not param_str:
            continue
        # Split by comma, count entries
        params = [p.strip() for p in param_str.split(",") if p.strip()]
        if len(params) > max_params:
            max_params = len(params)
    if max_params > 5:
        return max_params, f"function with {max_params} params"
    return None


def compute_nesting_depth(content: str, lines: list[str]) -> tuple[int, str] | None:
    """Find maximum nesting depth by brace counting. Returns (depth, label) or None."""
    max_depth = 0
    current_depth = 0
    in_string = False
    in_raw_string = False

    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("//"):
            continue
        for ch in stripped:
            if in_raw_string:
                if ch == "`":
                    in_raw_string = False
                continue
            if in_string:
                if ch == '"':
                    in_string = False
                elif ch == "\\":
                    continue  # skip next char approximation
                continue
            if ch == '"':
                in_string = True
            elif ch == "`":
                in_raw_string = True
            elif ch == "{":
                current_depth += 1
                if current_depth > max_depth:
                    max_depth = current_depth
            elif ch == "}":
                current_depth -= 1
    # Subtract 1 for the package-level/function-level braces
    effective_depth = max_depth - 1
    if effective_depth > 4:
        return effective_depth, f"nesting depth {effective_depth}"
    return None


def compute_long_functions(content: str, lines: list[str]) -> tuple[int, str] | None:
    """Find Go functions >80 LOC. Returns (longest_loc, label) or None."""
    func_re = re.compile(r"^func\s+", re.MULTILINE)
    results = []

    for m in func_re.finditer(content):
        fn_line = content[:m.start()].count("\n")
        # Find the opening brace
        rest = content[m.start():]
        brace_idx = rest.find("{")
        if brace_idx == -1:
            continue

        # Count braces to find function end
        depth = 0
        abs_start = m.start() + brace_idx
        for i in range(abs_start, len(content)):
            if content[i] == "{":
                depth += 1
            elif content[i] == "}":
                depth -= 1
                if depth == 0:
                    end_line = content[:i + 1].count("\n")
                    loc = end_line - fn_line + 1
                    # Extract function name
                    name_m = re.search(r"func\s+(?:\([^)]+\)\s+)?(\w+)", rest)
                    fn_name = name_m.group(1) if name_m else "?"
                    if loc > 80:
                        results.append((fn_name, loc))
                    break

    if results:
        longest = max(results, key=lambda x: x[1])
        return longest[1], f"long function ({longest[0]}: {longest[1]} LOC)"
    return None
