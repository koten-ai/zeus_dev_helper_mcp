#!/usr/bin/env bash
# Stdio entry for MCP Inspector (ZDH-39). Inspector needs a single executable.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
candidates=()
[[ -n "${PYTHON:-}" ]] && candidates+=("${PYTHON}")
candidates+=("$ROOT/.venv/bin/python" python python3)
for py in "${candidates[@]}"; do
  if [[ -x "$py" ]] || command -v "$py" >/dev/null 2>&1; then
    if "$py" -c "import zeus_dev_helper_mcp" >/dev/null 2>&1; then
      exec "$py" -m zeus_dev_helper_mcp
    fi
  fi
done
echo "run-helper-mcp.sh: no interpreter with zeus_dev_helper_mcp installed" >&2
exit 1
