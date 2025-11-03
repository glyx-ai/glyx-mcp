#!/bin/bash
# MCP Tool Call Logger Hook
# Logs all glyx-mcp tool calls with timestamps and parameters

LOG_FILE="${CLAUDE_PROJECT_DIR:-.}/logs/mcp-tools.log"
mkdir -p "$(dirname "$LOG_FILE")"

# Read JSON input from stdin
INPUT=$(cat)

# Extract tool name and parameters
TOOL_NAME=$(echo "$INPUT" | jq -r '.tool.name // "unknown"')
TIMESTAMP=$(date '+%Y-%m-%d %H:%M:%S')

# Log the tool call
echo "[$TIMESTAMP] Tool: $TOOL_NAME" >> "$LOG_FILE"
echo "$INPUT" | jq '.' >> "$LOG_FILE"
echo "---" >> "$LOG_FILE"

# Return success (allow tool to proceed)
echo '{"allowed": true}'
