# CompositeDebugAgent Roadmap

**Status**: Planning
**Owner**: TBD
**Target Completion**: TBD
**Priority**: High

---

## Overview

The **CompositeDebugAgent** is an intelligent debugging orchestrator that automates the investigation and resolution of runtime errors. It combines multiple debugging primitives (error parsing, signature inspection, documentation lookup, code analysis) into a single cohesive workflow.

### Goals

1. **Reduce manual debugging time** from 10+ minutes to <2 minutes
2. **Automate repetitive investigation steps** (log parsing → attribute inspection → doc lookup → fix generation)
3. **Provide actionable fixes** with code diffs, not just explanations
4. **Handle environment complexity** (Docker, virtual envs, package version mismatches)

### Non-Goals

- Real-time debugging/breakpoints (use a proper debugger)
- Performance profiling (separate tool)
- Test generation (separate agent)

---

## High-Level Architecture

```
┌─────────────────────────────────────────────────────────┐
│              CompositeDebugAgent                        │
│                                                         │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐ │
│  │ ErrorParser  │→ │ Inspector    │→ │ DocLookup    │ │
│  │              │  │              │  │              │ │
│  │ - Parse logs │  │ - Signatures │  │ - Context7   │ │
│  │ - Extract    │  │ - Attributes │  │ - Official   │ │
│  │   context    │  │ - Types      │  │   docs       │ │
│  └──────────────┘  └──────────────┘  └──────────────┘ │
│         │                  │                  │        │
│         └──────────────────┴──────────────────┘        │
│                            ↓                           │
│                  ┌──────────────────┐                  │
│                  │   FixGenerator   │                  │
│                  │                  │                  │
│                  │ - Analyze        │                  │
│                  │ - Synthesize     │                  │
│                  │ - Generate diff  │                  │
│                  └──────────────────┘                  │
└─────────────────────────────────────────────────────────┘
```

### Components

1. **ErrorParser**: Extracts structured error info from logs/stack traces
2. **RuntimeInspector**: Inspects signatures, attributes, types at runtime
3. **DocLookup**: Fetches authoritative documentation via Context7
4. **FixGenerator**: Synthesizes findings into actionable code fixes
5. **Orchestrator**: Coordinates workflow, manages state, handles retries

---

## Implementation Phases

### Phase 1: Foundation (Week 1-2)

**Goal**: Build core debugging primitives as standalone tools

#### Tasks

- [ ] **ErrorParser Tool** (`src/glyx_mcp/tools/parse_error.py`)
  - Parse Python stack traces (AttributeError, TypeError, etc.)
  - Extract: exception type, message, file, line, problematic symbol
  - Handle multi-line errors, chained exceptions
  - Return structured `ErrorContext` Pydantic model

- [ ] **InspectSignature Tool** (`src/glyx_mcp/tools/inspect_signature.py`)
  - Support: functions, classes, dataclasses, Pydantic models
  - Show: parameters, type hints, return types, docstrings
  - Handle: Union types, Generics, Protocols
  - Execute in target environment (local/docker)

- [ ] **InspectAttributes Tool** (`src/glyx_mcp/tools/inspect_attributes.py`)
  - List all attributes on class/instance
  - Filter: public, private, methods, properties, data
  - Show types and values (optional)
  - Handle dynamic attributes (Pydantic, dataclasses)

- [ ] **Config Definitions**
  - Create JSON configs for each tool in `src/glyx_mcp/config/`
  - Add to `AgentKey` enum
  - Write unit tests for config validation

**Success Criteria**:
- All 3 tools work standalone via MCP
- Can inspect `ToolCallItem` and return `.raw_item.name` attribute
- 80%+ test coverage for each tool

---

### Phase 2: Integration (Week 3)

**Goal**: Combine tools into orchestrated workflow

#### Tasks

- [ ] **CompositeDebugAgent** (`src/glyx_mcp/orchestration/debug_orchestrator.py`)
  - Implement 5-step workflow:
    1. Parse error from logs
    2. Identify problematic class/attribute
    3. Inspect available attributes
    4. Lookup official documentation
    5. Generate fix with code diff
  - Use OpenAI Agents SDK for orchestration
  - Stream intermediate results (tool calls, thinking)
  - Handle errors/retries gracefully

- [ ] **EnvironmentExecutor** (`src/glyx_mcp/utils/environment.py`)
  - Abstract execution across environments (local, docker, venv)
  - Auto-detect environment from context
  - Handle `docker exec` for containerized inspection
  - Support environment switching mid-workflow

- [ ] **FixGenerator** (`src/glyx_mcp/orchestration/fix_generator.py`)
  - Synthesize findings into code diff
  - Use `diff` library for clean patches
  - Validate fix against original error
  - Support multiple fix strategies (attribute rename, type cast, etc.)

**Success Criteria**:
- End-to-end workflow from error → fix
- Can resolve the `item.name` → `item.raw_item.name` bug automatically
- Generates valid unified diff output

---

### Phase 3: Enhancement (Week 4)

**Goal**: Add intelligence, caching, multi-language support

#### Tasks

- [ ] **Smart Error Classification**
  - Detect error patterns (AttributeError, ImportError, TypeError)
  - Route to specialized sub-workflows
  - Learn from previous fixes (optional: vector DB)

- [ ] **Context7 Integration Improvements**
  - Cache documentation lookups (15min TTL)
  - Prioritize version-specific docs
  - Fallback to web search if no docs found

- [ ] **Multi-Language Support**
  - Start with JavaScript/TypeScript
  - Add inspectors for JS objects, TS types
  - Generate fixes for common JS errors

- [ ] **Interactive Mode**
  - Ask user for clarification when ambiguous
  - Confirm before applying fixes
  - Explain reasoning at each step

**Success Criteria**:
- 90%+ accuracy on common error types (AttributeError, TypeError)
- <5s cache hit latency for repeated errors
- Can debug JS/TS errors in addition to Python

---

### Phase 4: Production Readiness (Week 5-6)

**Goal**: Polish, optimize, deploy

#### Tasks

- [ ] **Performance Optimization**
  - Parallel tool execution where possible
  - Reduce docker exec overhead (persistent connections?)
  - Optimize token usage for LLM calls

- [ ] **Error Handling**
  - Graceful degradation when tools fail
  - Retry logic with exponential backoff
  - Clear error messages for users

- [ ] **Testing & Validation**
  - E2E tests for 10+ real-world error scenarios
  - Integration tests with mocked environments
  - Regression test suite

- [ ] **Documentation**
  - User guide with examples
  - Architecture diagrams
  - Troubleshooting guide

- [ ] **Deployment**
  - Add to default MCP server tools
  - Docker image with all dependencies
  - CI/CD pipeline for testing

**Success Criteria**:
- <10s end-to-end latency for typical errors
- 95%+ uptime in production
- Comprehensive docs published

---

## API Design

### Tool Signature

```python
@mcp.tool()
def debug_agent(
    error_context: str,           # Stack trace or error message
    code_context: str | None,     # Optional: relevant code snippet
    environment: str = "auto",    # "local", "docker:name", "auto"
    strategy: str = "comprehensive",  # "quick", "comprehensive"
    auto_apply: bool = False      # Apply fix automatically
) -> DebugResult:
    """
    Orchestrate debugging workflow to analyze and fix errors.

    Returns:
        DebugResult with:
        - analysis: Step-by-step investigation
        - root_cause: Identified issue
        - suggested_fix: Code diff
        - confidence: 0-100
        - alternative_fixes: List of other approaches
    """
    pass
```

### Data Models

```python
@dataclass
class ErrorContext:
    exception_type: str          # "AttributeError"
    message: str                 # "'ToolCallItem' has no attribute 'name'"
    file_path: str               # "orchestrator.py"
    line_number: int             # 198
    symbol: str                  # "item.name"
    stack_trace: str             # Full trace

@dataclass
class InspectionResult:
    available_attributes: list[str]
    attribute_types: dict[str, str]
    similar_attributes: list[str]  # Fuzzy match suggestions
    documentation_url: str | None

@dataclass
class DebugResult:
    analysis: str                # Multi-step investigation log
    root_cause: str              # "Should use item.raw_item.name"
    suggested_fix: str           # Unified diff
    confidence: int              # 0-100
    alternative_fixes: list[str] # Other approaches
    documentation_refs: list[str]
```

---

## Dependencies

### Required

- **OpenAI Agents SDK** (orchestration)
- **Context7 MCP** (documentation lookup)
- **Docker** (environment isolation)
- Existing `ComposableAgent` infrastructure

### Optional

- **difflib** or **unified-diff** (patch generation)
- **tree-sitter** (AST parsing for better code understanding)
- **langfuse** (observability, already integrated)

---

## Success Metrics

### User-Facing

- **Time to resolution**: <2 minutes for 80% of AttributeError/TypeError cases
- **Accuracy**: 90%+ fixes work on first try
- **User satisfaction**: Qualitative feedback (saves time vs manual debugging)

### Technical

- **Latency**: <10s end-to-end (P95)
- **Cache hit rate**: >70% for documentation lookups
- **Test coverage**: >80% for orchestration logic
- **Error rate**: <5% tool failures

---

## Risks & Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| Docker exec overhead too high | High latency | Cache inspection results, use persistent connections |
| Context7 rate limits | Workflow failures | Implement caching, fallback to web search |
| Complex errors too hard to parse | Low accuracy | Start with simple error types, expand gradually |
| Generated fixes break code | User frustration | Always show diff before applying, require confirmation |
| LLM costs too high | Budget overrun | Use cheaper models for inspection, reserve expensive models for synthesis |

---

## Future Enhancements

### V2 Features (Post-Launch)

- **Learning from past fixes**: Store error → fix mappings in vector DB
- **IDE integration**: LSP server for real-time debugging
- **Proactive error detection**: Scan code for potential issues before runtime
- **Multi-repo debugging**: Debug errors across microservices
- **Performance profiling**: Extend to performance issues, not just errors

### Research Directions

- **Symbolic execution**: Combine with static analysis for deeper understanding
- **Test generation**: Auto-generate tests to prevent regression
- **Root cause analysis**: Go beyond immediate fix to systemic issues

---

## Open Questions

1. **LLM Selection**: Which model for orchestration? (GPT-4, Claude, Gemini?)
2. **Caching Strategy**: Redis? SQLite? In-memory?
3. **User Feedback Loop**: How to collect data on fix success/failure?
4. **Error Taxonomy**: Start with Python-only or multi-language from day 1?
5. **Deployment Model**: MCP tool only, or also standalone CLI?

---

## References

- Original debugging interaction: [Session Nov 2, 2025]
- OpenAI Agents SDK: https://github.com/openai/openai-agents-python
- Context7 MCP: [Internal docs]
- Related work: GitHub Copilot Chat, Cursor's error fixing

---

**Last Updated**: 2025-11-02
**Next Review**: TBD
