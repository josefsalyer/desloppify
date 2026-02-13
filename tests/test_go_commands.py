"""Test Go detector CLI commands."""
from desloppify.lang.go.commands import get_detect_commands


class TestGoCommands:
    def test_registry_not_empty(self):
        cmds = get_detect_commands()
        assert len(cmds) > 0

    def test_expected_commands(self):
        cmds = get_detect_commands()
        expected = {"unused", "large", "complexity", "gods", "smells",
                    "dupes", "deps", "cycles", "orphaned"}
        assert expected.issubset(set(cmds.keys()))

    def test_commands_are_callable(self):
        cmds = get_detect_commands()
        for name, cmd in cmds.items():
            assert callable(cmd), f"{name} is not callable"
