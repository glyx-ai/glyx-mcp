"""Tests for pairing script resilience and correctness."""

from pathlib import Path

import pytest

from api.routes.pair import PAIR_SCRIPT


# ── Script content ───────────────────────────────────────────


class TestPairScript:
    """The bash script served at /pair must be correct and resilient."""

    def test_bash_shebang(self):
        assert PAIR_SCRIPT.strip().startswith("#!/bin/bash")

    def test_uses_fresh_clone(self):
        """Fresh clone every time eliminates dirty-repo failures."""
        assert "rm -rf" in PAIR_SCRIPT
        assert "git clone" in PAIR_SCRIPT

    def test_no_git_pull(self):
        """No git pull = no dirty-state failures. Fresh clone is the strategy."""
        assert "git pull" not in PAIR_SCRIPT

    def test_shallow_clone(self):
        """--depth 1 keeps the download fast."""
        assert "--depth 1" in PAIR_SCRIPT

    def test_hands_off_to_python(self):
        assert "exec uv run python3 scripts/pair_display.py" in PAIR_SCRIPT


# ── pair_display.py content ──────────────────────────────────


class TestPairDisplay:
    """pair_display.py must handle port conflicts before starting the server."""

    @pytest.fixture(autouse=True)
    def _load(self):
        self.content = (Path(__file__).parent.parent / "scripts" / "pair_display.py").read_text()

    def test_has_free_port_function(self):
        assert "def free_port" in self.content

    def test_calls_free_port_before_server(self):
        free_pos = self.content.index("free_port(SERVER_PORT)")
        exec_pos = self.content.index("os.execvpe")
        assert free_pos < exec_pos
