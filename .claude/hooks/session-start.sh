#!/bin/bash
set -euo pipefail

# Only run in Claude Code on the web
if [ "${CLAUDE_CODE_REMOTE:-}" != "true" ]; then
  exit 0
fi

echo "==> Installing frontend dependencies (npm)..."
cd "$CLAUDE_PROJECT_DIR/frontend"
npm install

echo "==> Installing backend dependencies (pip)..."
cd "$CLAUDE_PROJECT_DIR/backend"
pip install -r requirements.txt --quiet

echo "==> Setup complete."
