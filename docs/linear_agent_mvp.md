# Linear Agent MVP

Integration guide for Linear agent sessions with glyx-mcp orchestration.

## Overview

The Linear Agent MVP enables Linear workspace agents to trigger orchestration tasks via webhooks. When a Linear agent session is created, it:

1. Acknowledges the session within 10 seconds (Linear requirement)
2. Creates an orchestration task in Supabase
3. Executes the task using the Orchestrator
4. Streams activity updates back to Linear via GraphQL

## Setup

### 1. Linear App Configuration

Create a Linear app with the following OAuth scopes:
- `actor=app` - Required for agent sessions
- `app:assignable` - Allow app to be assigned to issues
- `app:mentionable` - Allow app to be mentioned in comments

Configure webhook subscriptions for:
- `Agent Session` events (specifically `session.created` and `session.updated`)

### 2. Environment Variables

Add to your `.env` file:

```bash
# Linear App Configuration
LINEAR_API_KEY=lin_api_...          # Linear API key for GraphQL operations
LINEAR_CLIENT_ID=...                # OAuth client ID
LINEAR_CLIENT_SECRET=...            # OAuth client secret
LINEAR_WEBHOOK_SECRET=...           # Webhook signature verification secret
```

### 3. Webhook Endpoint

Configure your Linear app webhook URL to point to:
```
https://your-domain.com/webhooks/linear
```

The webhook handler:
- Verifies HMAC SHA256 signatures using `LINEAR_WEBHOOK_SECRET`
- Parses `AgentSessionEvent` payloads
- Acknowledges sessions within 10 seconds
- Creates orchestration tasks for session events

## Architecture

### Components

1. **`integrations/linear.py`**
   - `AgentSessionEvent`: Pydantic model for webhook payloads
   - `LinearGraphQLClient`: GraphQL client for emitting activities

2. **`webhooks/linear.py`**
   - Webhook router with signature verification
   - Event handlers for `session.created` and `session.updated`
   - Health check endpoint at `/webhooks/linear/health`

3. **`orchestration/linear_service.py`**
   - `LinearService`: Converts session events to orchestration tasks
   - Streams orchestration results back to Linear as activities

4. **Task Model Extensions**
   - `linear_session_id`: Links tasks to Linear sessions
   - `linear_workspace_id`: Tracks workspace context

### Flow

```
Linear Session Created
  ↓
Webhook → Verify Signature
  ↓
Acknowledge Session (< 10s)
  ↓
Create Task in Supabase
  ↓
Orchestrator.orchestrate()
  ↓
Stream Activities → Linear GraphQL API
  ↓
Update Task Status
```

## Dashboard Integration

### API Endpoints

- `GET /api/tasks/linear/{session_id}` - Get task by Linear session ID
- `GET /api/tasks/linear/workspace/{workspace_id}` - List all tasks for a workspace

### Supabase Tables

Tasks are stored in the `tasks` table with:
- `linear_session_id`: Session identifier
- `linear_workspace_id`: Workspace identifier
- `organization_id`: Organization context

Activities are stored in the `activities` table and streamed to Linear.

## Testing

Run unit tests:
```bash
uv run pytest tests/test_linear_webhook.py -v
```

Integration tests require:
- `LINEAR_API_KEY` environment variable
- Mock Linear GraphQL responses

## Troubleshooting

### Webhook Signature Verification Fails

- Verify `LINEAR_WEBHOOK_SECRET` matches Linear app configuration
- Check that webhook payload is not modified in transit
- Enable `WEBHOOK_TEST_MODE=true` for development (disables verification)

### Session Acknowledgment Timeout

- Ensure `LINEAR_API_KEY` is configured and valid
- Check network connectivity to `api.linear.app`
- Verify GraphQL mutation permissions

### Activities Not Appearing in Linear

- Confirm API key has `agentActivityCreate` mutation permission
- Check session ID matches active Linear session
- Review GraphQL response for errors

## References

- [Linear Agents Getting Started](https://linear.app/docs/agents/getting-started)
- [Linear GraphQL API](https://developers.linear.app/docs/graphql/working-with-the-graphql-api)
