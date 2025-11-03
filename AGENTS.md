# AGENTS.md

## Essential Commands

**Install**: `uv pip install -e ".[dev]"`  
**Run server**: `glyx-mcp`  
**All tests**: `uv run pytest`  
**Single test**: `uv run pytest tests/test_file.py::test_function_name`  
**Integration tests**: `uv run pytest -m integration`  
**E2E tests**: `uv run pytest -m e2e`  
**Type check**: `mypy src/`  
**Lint**: `ruff check src/`  
**Client integration**: `uv run pytest tests/test_client_integration.py -vv -ss`

## Code Style Guidelines

- **Python version**: 3.11 minimum
- **Type checking**: Strict mypy enabled (`mypy.strict = true`)
- **Validation**: Use Pydantic models for all configs and structured data
- **Async**: All agent execution is async (`asyncio`)
- **Line length**: 120 characters (ruff)
- **Imports**: Always at top of file
- **Error handling**: No defensive programming, prefer flat expressive style
- **Coverage**: 40% minimum threshold
- **Naming**: Follow existing patterns in codebase</content>
<parameter name="filePath">/home/parallels/glyx-mcp/AGENTS.md