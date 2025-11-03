#!/bin/bash
# Quick reload script for glyx-mcp development
# Usage: ./reload.sh

set -e

echo "🔄 Rebuilding glyx-mcp Docker image..."
docker compose build

echo "🧹 Cleaning up old containers..."
docker rm -f $(docker ps -aq --filter "name=glyx-mcp") 2>/dev/null || echo "No old containers to clean"

echo ""
echo "✅ Rebuild complete!"
echo ""
echo "📝 To reconnect Claude Code:"
echo "   1. Type /reload in Claude Code, or"
echo "   2. Restart Claude Code entirely"
echo ""
