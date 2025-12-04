"""Unit tests for Pydantic config validation."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from glyx_python_sdk import AgentConfig, ArgSpec


class TestArgSpecValidation:
    """Tests for ArgSpec Pydantic model validation."""

    def test_valid_argspec_loads_successfully(self) -> None:
        """Test that a valid ArgSpec passes validation."""
        arg = ArgSpec(flag="--message", type="string", required=True, description="Test argument")

        assert arg.flag == "--message"
        assert arg.type == "string"
        assert arg.required is True
        assert arg.description == "Test argument"

    def test_argspec_defaults(self) -> None:
        """Test that ArgSpec has correct default values."""
        arg = ArgSpec()

        assert arg.flag == ""
        assert arg.type == "string"
        assert arg.required is False
        assert arg.default is None
        assert arg.description == ""

    def test_invalid_arg_type_raises_validation_error(self) -> None:
        """Test that invalid argument types are caught."""
        with pytest.raises(ValidationError) as exc_info:
            ArgSpec(flag="--test", type="invalid_type", required=False)  # Should only be string/bool/int

        error_str = str(exc_info.value)
        assert "type" in error_str.lower()

    def test_arg_type_literal_enforcement(self) -> None:
        """Test that only valid arg types are accepted."""
        # Valid types should work
        valid_types = ["string", "bool", "int"]
        for arg_type in valid_types:
            arg = ArgSpec(flag="--test", type=arg_type)
            assert arg.type == arg_type

        # Invalid types should fail
        invalid_types = ["float", "list", "dict", "tuple"]
        for invalid_type in invalid_types:
            with pytest.raises(ValidationError):
                ArgSpec(flag="--test", type=invalid_type)

    def test_argspec_with_all_fields(self) -> None:
        """Test ArgSpec with all fields specified."""
        arg = ArgSpec(flag="--verbose", type="bool", required=False, default=True, description="Enable verbose output")

        assert arg.flag == "--verbose"
        assert arg.type == "bool"
        assert arg.required is False
        assert arg.default is True
        assert arg.description == "Enable verbose output"


class TestAgentConfigValidation:
    """Tests for AgentConfig Pydantic model validation."""

    def test_valid_config_loads_successfully(self) -> None:
        """Test that a valid config passes Pydantic validation."""
        config = AgentConfig(
            agent_key="test",
            command="test_cli",
            args={
                "prompt": ArgSpec(flag="--message", type="string", required=True),
            },
            description="Test agent",
        )

        assert config.agent_key == "test"
        assert config.command == "test_cli"
        assert "prompt" in config.args
        assert config.description == "Test agent"

    def test_missing_required_field_raises_validation_error(self) -> None:
        """Test that missing required fields are caught."""
        with pytest.raises(ValidationError) as exc_info:
            AgentConfig(
                agent_key="test",
                # Missing 'command' - required field
                args={},
            )

        error = exc_info.value
        assert "command" in str(error).lower()
        assert "required" in str(error).lower()

    def test_empty_command_raises_validation_error(self) -> None:
        """Test that empty command string is rejected."""
        with pytest.raises(ValidationError) as exc_info:
            AgentConfig(agent_key="test", command="", args={})  # Empty string should fail min_length validation

        assert "command" in str(exc_info.value).lower()

    def test_config_with_empty_args_dict(self) -> None:
        """Test that config with no arguments is valid."""
        config = AgentConfig(agent_key="simple", command="simple_cli", args={})

        assert config.agent_key == "simple"
        assert config.command == "simple_cli"
        assert len(config.args) == 0

    def test_config_with_capabilities(self) -> None:
        """Test that optional capabilities field works."""
        config = AgentConfig(
            agent_key="test", command="test_cli", args={}, capabilities=["code_generation", "reasoning", "analysis"]
        )

        assert len(config.capabilities) == 3
        assert "code_generation" in config.capabilities
        assert "reasoning" in config.capabilities

    def test_config_defaults(self) -> None:
        """Test that optional fields have correct defaults."""
        config = AgentConfig(agent_key="minimal", command="minimal_cli", args={})

        assert config.description is None
        assert config.version is None
        assert config.capabilities == []

    def test_config_with_version(self) -> None:
        """Test that version field is stored correctly."""
        config = AgentConfig(agent_key="test", command="test_cli", args={}, version=">=1.0.0")

        assert config.version == ">=1.0.0"

    def test_config_with_complex_args(self) -> None:
        """Test config with multiple argument types."""
        config = AgentConfig(
            agent_key="complex",
            command="complex_cli",
            args={
                "message": ArgSpec(flag="--message", type="string", required=True),
                "verbose": ArgSpec(flag="--verbose", type="bool", default=False),
                "count": ArgSpec(flag="--count", type="int", default=10),
                "subcmd": ArgSpec(flag="", type="string", default="run"),
            },
        )

        assert len(config.args) == 4
        assert config.args["message"].type == "string"
        assert config.args["verbose"].type == "bool"
        assert config.args["count"].type == "int"
        assert config.args["subcmd"].flag == ""  # Positional


class TestConfigFromFile:
    """Tests for loading configs from JSON files."""

    def test_config_from_file_validates_automatically(self, tmp_path: Path) -> None:
        """Test that loading from file validates the config."""

        # Create a valid config file
        config_file = tmp_path / "valid.json"
        config_file.write_text(
            json.dumps(
                {
                    "test_agent": {
                        "command": "test_cli",
                        "args": {"prompt": {"flag": "--message", "type": "string", "required": True}},
                    }
                }
            )
        )

        config = AgentConfig.from_file(config_file)
        assert config.agent_key == "test_agent"
        assert config.command == "test_cli"

    def test_config_from_file_rejects_invalid_config(self, tmp_path: Path) -> None:
        """Test that invalid config files are rejected."""

        # Create an invalid config file (missing command)
        invalid_file = tmp_path / "invalid.json"
        invalid_file.write_text(
            json.dumps(
                {
                    "bad_agent": {
                        "args": {}
                        # Missing 'command'
                    }
                }
            )
        )

        with pytest.raises(ValidationError):
            AgentConfig.from_file(invalid_file)

    def test_config_from_file_with_invalid_arg_type(self, tmp_path: Path) -> None:
        """Test that invalid arg types in file are caught."""

        config_file = tmp_path / "bad_type.json"
        config_file.write_text(
            json.dumps(
                {
                    "test": {
                        "command": "test_cli",
                        "args": {"bad_arg": {"flag": "--bad", "type": "float", "required": False}},  # Invalid type
                    }
                }
            )
        )

        with pytest.raises(ValidationError) as exc_info:
            AgentConfig.from_file(config_file)

        assert "type" in str(exc_info.value).lower()

    def test_config_from_file_with_all_optional_fields(self, tmp_path: Path) -> None:
        """Test loading config with all optional fields."""

        config_file = tmp_path / "full.json"
        config_file.write_text(
            json.dumps(
                {
                    "full_agent": {
                        "command": "full_cli",
                        "args": {},
                        "description": "A fully specified agent",
                        "version": ">=1.0.0",
                        "capabilities": ["coding", "reasoning"],
                    }
                }
            )
        )

        config = AgentConfig.from_file(config_file)
        assert config.agent_key == "full_agent"
        assert config.description == "A fully specified agent"
        assert config.version == ">=1.0.0"
        assert len(config.capabilities) == 2


class TestExistingAgentConfigs:
    """Tests that all existing agent configs are valid."""

    def test_all_existing_configs_are_valid(self) -> None:
        """Test that all existing agent config files pass validation."""
        config_dir = Path(__file__).parent.parent / "src" / "glyx" / "mcp" / "config"

        if not config_dir.exists():
            pytest.skip("Config directory not found")

        config_files = list(config_dir.glob("*.json"))
        assert len(config_files) > 0, "No config files found"

        # Files that are not agent configs (e.g., database configs)
        skip_files = {"zilliz.json"}

        errors = []
        valid_count = 0
        skipped_count = 0

        for config_file in config_files:
            if config_file.name in skip_files:
                print(f"⊘ {config_file.name} skipped (not an agent config)")
                skipped_count += 1
                continue

            try:
                config = AgentConfig.from_file(config_file)
                assert config.agent_key is not None
                assert config.command is not None
                assert len(config.command) > 0
                print(f"✓ {config_file.name} is valid (agent: {config.agent_key})")
                valid_count += 1
            except ValidationError as e:
                errors.append(f"{config_file.name}: {e}")
            except Exception as e:
                errors.append(f"{config_file.name}: Unexpected error - {e}")

        print(f"\nValidated {valid_count} agent configs, skipped {skipped_count}")

        if errors:
            pytest.fail(f"Config validation failed:\n" + "\n".join(errors))

    def test_aider_config_structure(self) -> None:
        """Test that aider.json has expected structure."""
        config_dir = Path(__file__).parent.parent / "src" / "glyx" / "mcp" / "config"
        aider_config = config_dir / "aider.json"

        if not aider_config.exists():
            pytest.skip("aider.json not found")

        config = AgentConfig.from_file(aider_config)

        assert config.agent_key == "aider"
        assert config.command == "aider"
        assert "prompt" in config.args or "message" in config.args
        assert "model" in config.args
        assert "files" in config.args or "file" in config.args

    def test_grok_config_structure(self) -> None:
        """Test that grok.json has expected structure."""
        config_dir = Path(__file__).parent.parent / "src" / "glyx" / "mcp" / "config"
        grok_config = config_dir / "grok.json"

        if not grok_config.exists():
            pytest.skip("grok.json not found")

        config = AgentConfig.from_file(grok_config)

        assert config.agent_key == "grok"
        assert config.command == "opencode"
        assert "prompt" in config.args
        assert "model" in config.args

    def test_all_configs_have_unique_agent_keys(self) -> None:
        """Test that all config files have unique agent keys."""
        config_dir = Path(__file__).parent.parent / "src" / "glyx" / "mcp" / "config"

        if not config_dir.exists():
            pytest.skip("Config directory not found")

        config_files = list(config_dir.glob("*.json"))
        skip_files = {"zilliz.json"}

        agent_keys = set()
        agent_config_count = 0

        for config_file in config_files:
            if config_file.name in skip_files:
                continue

            config = AgentConfig.from_file(config_file)
            assert config.agent_key not in agent_keys, f"Duplicate agent key: {config.agent_key}"
            agent_keys.add(config.agent_key)
            agent_config_count += 1

        assert (
            len(agent_keys) == agent_config_count
        ), "Number of unique agent keys doesn't match number of agent configs"

    def test_all_configs_have_valid_commands(self) -> None:
        """Test that all configs have non-empty command strings."""
        config_dir = Path(__file__).parent.parent / "src" / "glyx" / "mcp" / "config"

        if not config_dir.exists():
            pytest.skip("Config directory not found")

        config_files = list(config_dir.glob("*.json"))
        skip_files = {"zilliz.json"}

        for config_file in config_files:
            if config_file.name in skip_files:
                continue

            config = AgentConfig.from_file(config_file)
            assert config.command, f"{config_file.name} has empty command"
            assert len(config.command) > 0, f"{config_file.name} has empty command string"
            assert isinstance(config.command, str), f"{config_file.name} command is not a string"
