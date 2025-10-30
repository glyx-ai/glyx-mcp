from agents import function_tool
from langfuse import observe

from glyx.adapters.composable_agent import AgentKey, ComposableAgent
from utils.annotations import annotate_agent_tool


@function_tool
@observe
async def use_claude(task: str) -> str:
    return await ComposableAgent.from_key(AgentKey.CLAUDE).execute({"prompt": task}, timeout=300)


@function_tool
@observe
async def use_gemini(task: str) -> str:
    return await ComposableAgent.from_key(AgentKey.GEMINI).execute({"prompt": task}, timeout=300)


@function_tool
@observe
async def use_aider(task: str) -> str:
    return await ComposableAgent.from_key(AgentKey.AIDER).execute({"prompt": task}, timeout=300)


@function_tool
@observe
async def use_grok(prompt: str) -> str:
    """Composable 'grok' agent implemented as an opencode-backed CLI call with Grok model.

    Schema updated: function now expects a top-level 'prompt' field (JSON input
    must include {"prompt": "..."}). This makes the tool's JSON schema
    align with how Glyx composes prompts and the ComposableAgent configuration.
    """
    # Execute the configured opencode-backed ComposableAgent. This will shell
    # out to the opencode CLI with subcommand 'run' and pass the prompt as the
    # positional message argument (no simulation/fallback; failures propagate).
    return await ComposableAgent.from_key(AgentKey.GROK).execute({"prompt": prompt}, timeout=300)


@function_tool
@observe
async def use_codex(task: str) -> str:
    return await ComposableAgent.from_key(AgentKey.CODEX).execute({"prompt": task}, timeout=300)


@function_tool
@observe
async def use_opencode(task: str) -> str:
    return await ComposableAgent.from_key(AgentKey.OPENCODE).execute({"prompt": task}, timeout=300)


@function_tool
@observe
async def use_deepseek_r1(prompt: str) -> str:
    """Use DeepSeek R1 reasoning model via OpenCode CLI and OpenRouter.

    DeepSeek R1 is optimized for complex reasoning tasks and step-by-step problem solving.
    """
    return await ComposableAgent.from_key(AgentKey.DEEPSEEK_R1).execute({"prompt": prompt}, timeout=300)


@function_tool
@observe
async def use_kimi_k2(prompt: str) -> str:
    """Use Kimi K2 model via OpenCode CLI and OpenRouter.

    Kimi K2 provides strong multilingual capabilities and context understanding.
    """
    return await ComposableAgent.from_key(AgentKey.KIMI_K2).execute({"prompt": prompt}, timeout=300)


annotate_agent_tool(use_claude, AgentKey.CLAUDE, "Claude", "Anthropic", "🤖")
annotate_agent_tool(use_gemini, AgentKey.GEMINI, "Gemini", "Google", "🔷")
annotate_agent_tool(use_aider, AgentKey.AIDER, "Aider", "Open Source", "🛠️")
annotate_agent_tool(use_grok, AgentKey.GROK, "Grok", "xAI", "🧩")
annotate_agent_tool(use_codex, AgentKey.CODEX, "Codex", "OpenAI", "🧠")
annotate_agent_tool(use_opencode, AgentKey.OPENCODE, "OpenCode", "OpenCode", "🟢")
annotate_agent_tool(use_deepseek_r1, AgentKey.DEEPSEEK_R1, "DeepSeek R1", "DeepSeek", "🔍")
annotate_agent_tool(use_kimi_k2, AgentKey.KIMI_K2, "Kimi K2", "Moonshot AI", "🌐")
