"""Tests for the pairing script and CLI."""

from api.routes.pair import PAIR_SCRIPT


class TestPairScript:
    """The bash wrapper must be minimal — just install uv and run the CLI."""

    def test_bash_shebang(self):
        assert PAIR_SCRIPT.strip().startswith("#!/bin/bash")

    def test_installs_uv_if_missing(self):
        assert "astral.sh/uv/install.sh" in PAIR_SCRIPT

    def test_runs_python_cli_via_uvx(self):
        assert "uvx" in PAIR_SCRIPT
        assert "glyx-pair" in PAIR_SCRIPT

    def test_no_spinners_or_traps(self):
        assert "spin()" not in PAIR_SCRIPT
        assert "trap" not in PAIR_SCRIPT

    def test_no_git_clone(self):
        assert "git clone" not in PAIR_SCRIPT

    def test_under_ten_lines(self):
        lines = [l for l in PAIR_SCRIPT.strip().splitlines() if l.strip()]
        assert len(lines) <= 10


class TestPairCLI:
    """The Python CLI module must be importable and have key functions."""

    def test_importable(self):
        from cli.pair import app
        assert app is not None

    def test_has_pair_command(self):
        from cli.pair import pair
        assert callable(pair)

    def test_has_qr_payload(self):
        from cli.pair import qr_payload
        env = {
            "device_id": "test-id",
            "hostname": "test-host",
            "username": "test-user",
            "ip": "192.168.1.1",
            "port": 8000,
            "agents": ["claude"],
            "has_claude_token": True,
        }
        payload = qr_payload(env)
        assert payload.startswith("glyx://pair?")
        assert "device_id=test-id" in payload
        assert "has_claude_token=1" in payload

    def test_has_free_port(self):
        from cli.pair import free_port
        assert callable(free_port)
