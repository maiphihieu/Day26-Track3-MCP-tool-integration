#!/usr/bin/env bash
# Start MCP Inspector for the SQLite Lab server.
# Usage: ./start_inspector.sh

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PYTHON="${PYTHON:-python}"

echo "Starting MCP Inspector..."
echo "   Server: $SCRIPT_DIR/mcp_server.py"
echo ""

mkdir -p "$SCRIPT_DIR/.npm-cache"
NPM_CONFIG_CACHE="$SCRIPT_DIR/.npm-cache" npx -y @modelcontextprotocol/inspector "$PYTHON" "$SCRIPT_DIR/mcp_server.py"
