# Route Extraction Plan

## Current State

- `src/glyx/mcp/server.py` - 1471 lines, monolithic server with all routes
- `src/api/routes/health.py` - Health routes already extracted ✅
- `src/mcp/server.py` - Clean MCP protocol server (66 lines)

## Target Structure

```
src/api/routes/
  ├── health.py          ✅ Done
  ├── root.py            ⏳ Root route (GET /)
  ├── streaming.py       ⏳ SSE and WebSocket routes
  ├── sequences.py       ⏳ Agent sequences (5 routes)
  ├── workflows.py       ⏳ Agent workflows (5 routes)
  ├── organizations.py   ⏳ Organizations (4 routes)
  ├── tasks.py           ⏳ Tasks (7 routes)
  ├── auth.py            ⏳ Auth (4 routes)
  ├── memory.py          ⏳ Memory (3 routes)
  ├── agents.py          ⏳ Agents (1 route)
  └── deployments.py     ⏳ Deployments (4 routes)
```

## Routes to Extract

### Already Done ✅
- Health routes (3 routes)

### Remaining (39 routes)

1. **Root Route** (1 route)
   - GET `/` - Serve static HTML

2. **Streaming Routes** (2 routes)
   - POST `/stream/cursor` - SSE streaming
   - WebSocket `/ws` - WebSocket endpoint

3. **Agent Sequences** (5 routes)
   - GET `/agent-sequences`
   - POST `/agent-sequences`
   - GET `/agent-sequences/{sequence_id}`
   - PATCH `/agent-sequences/{sequence_id}`
   - DELETE `/agent-sequences/{sequence_id}`

4. **Agent Workflows** (5 routes)
   - GET `/agent-workflows`
   - POST `/agent-workflows`
   - GET `/agent-workflows/{workflow_id}`
   - PATCH `/agent-workflows/{workflow_id}`
   - DELETE `/agent-workflows/{workflow_id}`
   - POST `/agent-workflows/{workflow_id}/execute`

5. **Organizations** (4 routes)
   - GET `/organizations`
   - POST `/organizations`
   - GET `/organizations/{org_id}`
   - DELETE `/organizations/{org_id}`

6. **Tasks** (7 routes)
   - GET `/tasks`
   - POST `/tasks`
   - GET `/tasks/{task_id}`
   - GET `/tasks/linear/{session_id}`
   - GET `/tasks/linear/workspace/{workspace_id}`
   - PATCH `/tasks/{task_id}`
   - DELETE `/tasks/{task_id}`
   - POST `/tasks/smart`

7. **Auth** (4 routes)
   - POST `/auth/signup`
   - POST `/auth/signin`
   - POST `/auth/signout`
   - GET `/auth/user`

8. **Memory** (3 routes)
   - POST `/memory/save`
   - POST `/memory/search`
   - POST `/memory/infer`

9. **Agents** (1 route)
   - GET `/agents`

10. **Deployments** (4 routes)
    - GET `/deployments`
    - GET `/deployments/{deployment_id}`
    - PATCH `/deployments/{deployment_id}`
    - DELETE `/deployments/{deployment_id}`

## Dependencies

Each route file will need:
- Proper imports from `glyx_python_sdk`
- Import of `get_supabase` from `api.utils`
- Constants like `DEFAULT_PROJECT_ID`
- Router creation: `router = APIRouter(prefix="/api", tags=["..."])`

## After Extraction

1. Update `src/api/server.py` to import and register all route modules
2. Update imports in moved files (webhooks, integrations)
3. Remove `src/glyx/mcp/` directory
4. Update tests that reference old imports

## Notes

- The old `src/glyx/mcp/server.py` contains both MCP server setup and FastAPI routes
- MCP server setup is already extracted to `src/mcp/server.py`
- All routes should go to `src/api/routes/`
- Webhooks and integrations already moved to `src/api/`
