"""Agent configuration JSON files loaded as AgentConfig instances."""

from pathlib import Path

from glyx_python_sdk.agent_types import AgentConfig

_CONFIGS_DIR = Path(__file__).parent

aider = AgentConfig.from_file(_CONFIGS_DIR / "aider.json")
claude = AgentConfig.from_file(_CONFIGS_DIR / "claude.json")
codex = AgentConfig.from_file(_CONFIGS_DIR / "codex.json")
cursor = AgentConfig.from_file(_CONFIGS_DIR / "cursor.json")
deepseek_r1 = AgentConfig.from_file(_CONFIGS_DIR / "deepseek_r1.json")
gemini = AgentConfig.from_file(_CONFIGS_DIR / "gemini.json")
grok = AgentConfig.from_file(_CONFIGS_DIR / "grok.json")
kimi_k2 = AgentConfig.from_file(_CONFIGS_DIR / "kimi_k2.json")
opencode = AgentConfig.from_file(_CONFIGS_DIR / "opencode.json")

ALL_CONFIGS = [aider, claude, codex, cursor, deepseek_r1, gemini, grok, kimi_k2, opencode]

__all__ = [
    "aider",
    "claude",
    "codex",
    "cursor",
    "deepseek_r1",
    "gemini",
    "grok",
    "kimi_k2",
    "opencode",
    "ALL_CONFIGS",
]
