#!/bin/bash
# Update OpenAPI specification from running FastAPI server

set -e

SERVER_URL="${SERVER_URL:-http://localhost:8000}"
OUTPUT_FILE="docs/openapi.json"

echo "Checking if FastAPI server is running at $SERVER_URL..."
if ! curl -sf "$SERVER_URL/api/healthz" > /dev/null; then
    echo "Error: FastAPI server not running at $SERVER_URL"
    echo "Start the server with: uv run python -m glyx.mcp.server"
    exit 1
fi

echo "Fetching OpenAPI specification..."
curl -sf "$SERVER_URL/openapi.json" -o "$OUTPUT_FILE"

if [ $? -eq 0 ]; then
    echo "✅ OpenAPI spec updated successfully: $OUTPUT_FILE"
    echo "File size: $(wc -c < "$OUTPUT_FILE") bytes"
    echo "Endpoints: $(jq '.paths | length' "$OUTPUT_FILE")"
else
    echo "❌ Failed to fetch OpenAPI spec"
    exit 1
fi
