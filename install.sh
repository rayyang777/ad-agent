#!/usr/bin/env bash
set -euo pipefail

ARCHIVE_URL="${AD_AGENT_ARCHIVE_URL:-https://github.com/rayyang777/ad-agent/archive/refs/heads/main.tar.gz}"
SOURCE_DIR="${AD_AGENT_SOURCE_DIR:-}"
SKILLS_SRC=".agents/skills"
MCP_SRC="mcp"
SCRIPTS_SRC="scripts"
DEFAULT_LIST="default-skills.txt"
CONFIG_FILE="config.json"
TEMP_DIR=""
SOURCE_ROOT=""
CLONED=0

usage() {
  cat >&2 <<EOF
Usage: $0 [--scope <default|all>] [--user <username>]

Options:
  --scope  Install scope: default installs skills listed in default-skills.txt;
           all installs every skill under .agents/skills. Default: default
  --user   Username shown as report producer. Default: 乐元素

Environment:
  AD_AGENT_ARCHIVE_URL         Optional source archive URL
  AD_AGENT_SOURCE_DIR          Local ad-agent source directory (skips download)
  AD_AGENT_FEISHU_FOLDER_TOKEN Feishu Drive target folder
  AD_AGENT_FEISHU_APP_ID       Feishu application ID
  AD_AGENT_FEISHU_APP_SECRET   Feishu application secret
EOF
}

DEFAULT_USER="乐元素"
DEFAULT_FEISHU_FOLDER_TOKEN=""

SCOPE="default"
INPUT_USER=""

cleanup() {
  if [[ "$CLONED" -eq 1 ]]; then
    rm -rf "$TEMP_DIR"
  fi
}
trap cleanup EXIT

if [[ $# -gt 0 && ( "$1" == "default" || "$1" == "all" ) ]]; then
  SCOPE="$1"
  shift
fi

while [[ $# -gt 0 ]]; do
  case "$1" in
    --scope)
      SCOPE="${2:-}"
      if [[ "$SCOPE" != "default" && "$SCOPE" != "all" ]]; then
        echo "Invalid --scope: $SCOPE. Expected default or all." >&2
        exit 1
      fi
      shift 2
      ;;
    --user)
      INPUT_USER="${2:-}"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown option: $1" >&2
      usage
      exit 1
      ;;
  esac
done

if [[ "$SOURCE_DIR" == file://* ]]; then
  SOURCE_ROOT="${SOURCE_DIR#file://}"
elif [[ -n "$SOURCE_DIR" ]]; then
  SOURCE_ROOT="$SOURCE_DIR"
fi

if [[ -n "$SOURCE_ROOT" ]]; then
  if [[ ! -d "$SOURCE_ROOT/$SKILLS_SRC" ]]; then
    echo "Error: local source does not contain $SKILLS_SRC: $SOURCE_ROOT" >&2
    exit 1
  fi
  echo ">>> Installing Codex ad-agent skills from $SOURCE_ROOT (scope=$SCOPE) ..."
else
  echo ">>> Downloading Codex ad-agent (scope=$SCOPE) ..."
  TEMP_DIR="$(mktemp -d)"
  curl -fsSL "$ARCHIVE_URL" | tar -xz -C "$TEMP_DIR" --strip-components=1
  SOURCE_ROOT="$TEMP_DIR"
  CLONED=1
fi

mkdir -p "$SKILLS_SRC"

if [[ "$SCOPE" == "all" ]]; then
  cp -R "$SOURCE_ROOT/$SKILLS_SRC/"* "$SKILLS_SRC/"
else
  if [[ ! -f "$SOURCE_ROOT/$DEFAULT_LIST" ]]; then
    echo "Error: $DEFAULT_LIST not found in repo; cannot resolve default skill list." >&2
    exit 1
  fi

  COPIED=0
  while IFS= read -r line || [[ -n "$line" ]]; do
    skill="${line%%#*}"
    skill="$(printf '%s' "$skill" | tr -d '[:space:]')"
    [[ -z "$skill" ]] && continue

    src="$SOURCE_ROOT/$SKILLS_SRC/$skill"
    if [[ -d "$src" ]]; then
      cp -R "$src" "$SKILLS_SRC/"
      COPIED=$((COPIED + 1))
    else
      echo "Warning: skill '$skill' listed in $DEFAULT_LIST but missing from repo, skipped." >&2
    fi
  done < "$SOURCE_ROOT/$DEFAULT_LIST"

  if [[ "$COPIED" -eq 0 ]]; then
    echo "Error: no skills installed. Check $DEFAULT_LIST or use '$0 --scope all'." >&2
    exit 1
  fi
fi

if [[ -d "$SOURCE_ROOT/$MCP_SRC" ]]; then
  SOURCE_MCP_ROOT="$(cd "$SOURCE_ROOT/$MCP_SRC" && pwd)"
  mkdir -p "$MCP_SRC"
  TARGET_MCP_ROOT="$(cd "$MCP_SRC" && pwd)"
  if [[ "$SOURCE_MCP_ROOT" != "$TARGET_MCP_ROOT" ]]; then
    mkdir -p "$MCP_SRC/shared"
    cp "$SOURCE_MCP_ROOT/ad_agent_mcp.py" "$MCP_SRC/ad_agent_mcp.py"
    cp "$SOURCE_MCP_ROOT/requirements.txt" "$MCP_SRC/requirements.txt"
    cp "$SOURCE_MCP_ROOT/shared/feishu_upload.py" "$MCP_SRC/shared/feishu_upload.py"
    cp "$SOURCE_MCP_ROOT/shared/sql_query.py" "$MCP_SRC/shared/sql_query.py"
    cp "$SOURCE_MCP_ROOT/shared/report_renderer.py" "$MCP_SRC/shared/report_renderer.py"
  fi
fi

if [[ -d "$SOURCE_ROOT/$SCRIPTS_SRC" ]]; then
  mkdir -p "$SCRIPTS_SRC"
  cp -R "$SOURCE_ROOT/$SCRIPTS_SRC/"* "$SCRIPTS_SRC/"
  chmod +x "$SCRIPTS_SRC"/*.sh 2>/dev/null || true
fi

echo ""
echo ">>> Preparing the project-local MCP environment ..."
bash "$SCRIPTS_SRC/setup_project.sh"

mkdir -p "$(dirname "$CONFIG_FILE")"

CONFIG_FILE="$CONFIG_FILE" \
INPUT_USER="$INPUT_USER" \
DEFAULT_USER="$DEFAULT_USER" \
INPUT_FOLDER_TOKEN="${AD_AGENT_FEISHU_FOLDER_TOKEN:-}" \
INPUT_FEISHU_APP_ID="${AD_AGENT_FEISHU_APP_ID:-}" \
INPUT_FEISHU_APP_SECRET="${AD_AGENT_FEISHU_APP_SECRET:-}" \
DEFAULT_FEISHU_FOLDER_TOKEN="$DEFAULT_FEISHU_FOLDER_TOKEN" \
SCOPE="$SCOPE" \
".venv/bin/python" <<'PYEOF'
import json
import os

path = os.environ["CONFIG_FILE"]
cfg = {}
if os.path.exists(path):
    try:
        with open(path, encoding="utf-8") as f:
            cfg = json.load(f)
    except Exception:
        cfg = {}

cfg["skills_scope"] = os.environ["SCOPE"]
cfg.setdefault("data_fortress_platform_user", "")
cfg.setdefault("data_fortress_aes_key", "")
cfg.pop("chat_id", None)
cfg.pop("feishu_card", None)

username = os.environ.get("INPUT_USER") or cfg.get("username") or os.environ.get("DEFAULT_USER") or ""
if os.environ.get("INPUT_USER"):
    username_src = "from arg"
elif cfg.get("username"):
    username_src = "from existing config"
else:
    username_src = "from default"
cfg["username"] = username

folder_token = (
    os.environ.get("INPUT_FOLDER_TOKEN")
    or (cfg.get("feishu_drive") or {}).get("parent_node")
    or os.environ.get("DEFAULT_FEISHU_FOLDER_TOKEN", "")
)
app_id = os.environ.get("INPUT_FEISHU_APP_ID") or (cfg.get("feishu_app") or {}).get("app_id") or ""
raw_secret = os.environ.get("INPUT_FEISHU_APP_SECRET") or (cfg.get("feishu_app") or {}).get("app_secret") or ""

cfg["feishu_drive"] = {"parent_node": folder_token}
cfg["feishu_app"] = {
    "app_id": app_id,
    "app_secret": raw_secret,
}

with open(path, "w", encoding="utf-8") as f:
    json.dump(cfg, f, ensure_ascii=False, indent=2)
    f.write("\n")

print(f"username    : {username or '(empty)'}  ({username_src})")
print(f"folder_token: {folder_token or '(empty)'}")
print(f"feishu_app_id: {app_id or '(empty)'}")
print(f"feishu_secret: {'***' if raw_secret else '(empty)'}")
print(f"-> {path}")
PYEOF

echo ""
echo "Done! ad-agent is installed in this project (scope=$SCOPE)."
echo "Installed skills:"
ls "$SKILLS_SRC"
