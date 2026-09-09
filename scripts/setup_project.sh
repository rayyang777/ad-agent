#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON_CMD="${AD_AGENT_PYTHON:-python3}"
VENV_DIR="$PROJECT_ROOT/.venv"
PROJECT_CONFIG="$PROJECT_ROOT/.codex/config.toml"

if ! command -v "$PYTHON_CMD" >/dev/null 2>&1; then
  echo "Error: Python 3.9 or newer is required. Install Python and rerun this command." >&2
  exit 1
fi

if ! "$PYTHON_CMD" -c 'import sys; raise SystemExit(sys.version_info < (3, 9))'; then
  echo "Error: Python 3.9 or newer is required. Install Python and rerun this command." >&2
  exit 1
fi

mkdir -p "$PROJECT_ROOT/.codex" "$PROJECT_ROOT/var/ad-agent"

if [[ ! -x "$VENV_DIR/bin/python" ]]; then
  echo ">>> Creating project Python environment ..."
  "$PYTHON_CMD" -m venv "$VENV_DIR"
fi

echo ">>> Installing ad-agent dependencies ..."
"$VENV_DIR/bin/python" -m pip install \
  --disable-pip-version-check \
  --quiet \
  -r "$PROJECT_ROOT/mcp/requirements.txt"

PROJECT_ROOT="$PROJECT_ROOT" \
PROJECT_CONFIG="$PROJECT_CONFIG" \
"$VENV_DIR/bin/python" <<'PYEOF'
from pathlib import Path
import json
import os

root = Path(os.environ["PROJECT_ROOT"]).resolve()
config = Path(os.environ["PROJECT_CONFIG"])
start = "# BEGIN ad-agent MCP"
end = "# END ad-agent MCP"

def toml_string(value) -> str:
    return json.dumps(str(value), ensure_ascii=False)

block = "\n".join([
    start,
    "[mcp_servers.ad_agent]",
    f"command = {toml_string(root / '.venv' / 'bin' / 'python')}",
    f"args = [{toml_string(root / 'mcp' / 'ad_agent_mcp.py')}]",
    f"cwd = {toml_string(root)}",
    "startup_timeout_sec = 120",
    "",
    "[mcp_servers.ad_agent.env]",
    f"AD_AGENT_HOME = {toml_string(root)}",
    "",
    "[mcp_servers.ad_agent.tools.ad_query]",
    'approval_mode = "approve"',
    "",
    "[mcp_servers.ad_agent.tools.ad_query_submit]",
    'approval_mode = "approve"',
    "",
    "[mcp_servers.ad_agent.tools.ad_query_status]",
    'approval_mode = "approve"',
    "",
    "[mcp_servers.ad_agent.tools.ad_query_result]",
    'approval_mode = "approve"',
    "",
    "[mcp_servers.ad_agent.tools.ad_render_report]",
    'approval_mode = "approve"',
    "",
    "[mcp_servers.ad_agent.tools.ad_upload_report]",
    'approval_mode = "approve"',
    end,
])

text = config.read_text(encoding="utf-8") if config.exists() else ""
if start in text and end in text:
    before, remainder = text.split(start, 1)
    _, after = remainder.split(end, 1)
    text = before.rstrip() + "\n\n" + block + after
elif "[mcp_servers.ad_agent]" in text:
    raise SystemExit(
        f"Error: {config} already contains an unmarked ad_agent MCP block. "
        "Remove that block and rerun setup."
    )
else:
    text = text.rstrip()
    text = (text + "\n\n" if text else "") + block + "\n"

config.write_text(text, encoding="utf-8")
PYEOF

GITIGNORE="$PROJECT_ROOT/.gitignore"
IGNORE_START="# BEGIN ad-agent local files"
if [[ ! -f "$GITIGNORE" ]] || ! grep -Fq "$IGNORE_START" "$GITIGNORE"; then
  {
    echo ""
    echo "$IGNORE_START"
    echo "/.codex/config.toml"
    echo "/.venv/"
    echo "/var/"
    echo "/config.json"
    echo "# END ad-agent local files"
  } >> "$GITIGNORE"
fi

echo ""
echo "ad-agent project environment is ready:"
echo "  Python: $VENV_DIR/bin/python"
echo "  MCP   : $PROJECT_CONFIG"
echo "  Config: $PROJECT_ROOT/config.json"
echo "  Data  : $PROJECT_ROOT/var/"
echo "Restart Codex or open a new task to load the project MCP."
