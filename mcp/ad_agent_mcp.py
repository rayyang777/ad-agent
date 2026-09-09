#!/usr/bin/env python3
"""Local MCP server exposing minimal ad-agent infrastructure tools."""

from __future__ import annotations

import datetime as dt
import json
import os
import sys
from pathlib import Path
from typing import Any

from sqlglot import exp, parse
from sqlglot.errors import ParseError

from shared.sql_query import DEFAULT_FETCH_ROWS, DataFortressClient, required_config, write_csv
from shared.report_renderer import render_report

ROOT = Path(os.environ.get("AD_AGENT_HOME", Path(__file__).resolve().parents[1])).expanduser().resolve()
RUNTIME_DIR = Path(os.environ.get("AD_AGENT_RUNTIME_DIR", ROOT / "var" / "ad-agent")).expanduser().resolve()
DEBUG_LOG = RUNTIME_DIR / "mcp-debug.log"
SUPPORTED_PROTOCOL_VERSIONS = {"2025-11-25", "2025-06-18", "2025-03-26", "2024-11-05", "2024-10-07"}
LATEST_PROTOCOL_VERSION = "2025-11-25"
ALLOWED_ENGINES = {"trino_new", "tez_new", "spark_on_ack", "presto", "tez"}

def debug_log(message: str) -> None:
    try:
        RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
        if DEBUG_LOG.exists() and DEBUG_LOG.stat().st_size > 1024 * 1024:
            DEBUG_LOG.unlink()
        with DEBUG_LOG.open("a", encoding="utf-8") as handle:
            handle.write(f"{dt.datetime.now().isoformat(timespec='seconds')} {message}\n")
    except Exception:
        pass

def read_message() -> dict[str, Any] | None:
    headers: dict[str, str] = {}
    while True:
        raw = sys.stdin.buffer.readline()
        if not raw:
            return None
        line = raw.decode("utf-8").strip()
        if line.startswith("{"):
            return json.loads(line)
        if not line:
            break
        key, _, value = line.partition(":")
        if value:
            headers[key.lower()] = value.strip()
    length = int(headers.get("content-length", "0"))
    return json.loads(sys.stdin.buffer.read(length).decode("utf-8")) if length > 0 else None

def respond(request_id: Any, result: Any = None, error: dict[str, Any] | None = None) -> None:
    payload: dict[str, Any] = {"jsonrpc": "2.0", "id": request_id}
    payload["error" if error else "result"] = error if error else result
    sys.stdout.write(json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n")
    sys.stdout.flush()

def run_stage(stage: str, args: list[str], timeout: int) -> str:
    import subprocess

    proc = subprocess.run(args, cwd=ROOT, env=os.environ.copy(), text=True,
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=timeout)
    if proc.returncode != 0:
        raise RuntimeError(f"[{stage}失败] {proc.stderr.strip() or proc.stdout.strip()}")
    return proc.stdout.strip()

def safe_name(value: Any, default: str) -> str:
    name = str(value or default).strip()
    if not name or Path(name).name != name:
        raise ValueError("file name must not contain a directory path")
    return name

def load_project_config() -> dict[str, Any]:
    path = ROOT / "config.json"
    try:
        config = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValueError("config.json is missing; run install.sh first") from exc
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"config.json cannot be read: {exc}") from exc
    if not isinstance(config, dict):
        raise ValueError("config.json must contain a JSON object")
    return config

def default_upload_name(title: str, today: str) -> str:
    display_title = title.replace("/", "、").replace("\\", "、").strip()
    if not display_title:
        display_title = "Animal 广告分析报告"
    return f"{display_title} - {today}.html"

def validate_query(sql: str, engine: str) -> None:
    if len(sql) > 100_000:
        raise ValueError("sql exceeds the 100000 character limit")
    dialect = "hive" if engine in {"tez", "tez_new", "spark_on_ack"} else "trino"
    try:
        statements = [statement for statement in parse(sql, read=dialect) if statement is not None]
    except ParseError as exc:
        raise ValueError(f"invalid {dialect} SQL: {exc}") from exc
    if len(statements) != 1:
        raise ValueError("exactly one SQL statement is required")
    statement = statements[0]
    if not isinstance(statement, exp.Query):
        raise ValueError("only read-only query statements are allowed")

def normalize_engine(arguments: dict[str, Any]) -> str:
    engine = str(arguments.get("engine") or "trino_new")
    if engine not in ALLOWED_ENGINES:
        raise ValueError(f"unsupported engine: {engine}")
    return engine

def data_fortress_client() -> DataFortressClient:
    config = load_project_config()
    platform_user = required_config(config, "data_fortress_platform_user")
    aes_key = required_config(config, "data_fortress_aes_key")
    return DataFortressClient(platform_user, aes_key)

def read_fetch_rows(arguments: dict[str, Any]) -> int:
    fetch_rows = int(arguments.get("fetch_rows") or DEFAULT_FETCH_ROWS)
    if not 100 <= fetch_rows <= 1000:
        raise ValueError("fetch_rows must be between 100 and 1000")
    return fetch_rows

def write_query_csv(query_id: str, arguments: dict[str, Any], client: DataFortressClient) -> dict[str, Any]:
    max_chars = int(arguments.get("max_chars") or 200000)
    if not 1 <= max_chars <= 200000:
        raise ValueError("max_chars must be between 1 and 200000")
    output_path = RUNTIME_DIR / safe_name(arguments.get("output_name"), "query.csv")
    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    columns, rows = client.fetch_rows(query_id, fetch_rows=read_fetch_rows(arguments))
    write_csv(output_path, columns, rows)
    csv_text = output_path.read_text(encoding="utf-8")
    return {
        "query_id": query_id,
        "file": str(output_path),
        "row_count": len(rows),
        "column_count": len(columns),
        "rows_text_length": len(csv_text),
        "truncated": len(csv_text) > max_chars,
        "csv": csv_text[:max_chars],
    }

def summarize_progress(progress: Any) -> dict[str, Any]:
    return {
        "query_id": progress.query_id,
        "is_success": progress.is_success,
        "is_failure": progress.is_failure,
        "log": progress.log,
    }

def ad_query(arguments: dict[str, Any]) -> dict[str, Any]:
    """Execute one read-only business query and return CSV."""
    sql = str(arguments.get("sql") or "").strip()
    if not sql:
        raise ValueError("sql is required")
    engine = normalize_engine(arguments)
    validate_query(sql, engine)
    wait_seconds = int(arguments.get("wait") or 300)
    poll_interval = float(arguments.get("poll_interval") or 2)
    if not 1 <= wait_seconds <= 3600:
        raise ValueError("wait must be between 1 and 3600 seconds")
    if poll_interval <= 0:
        raise ValueError("poll_interval must be greater than zero")
    client = data_fortress_client()
    query_id = client.execute(sql, engine)
    progress = client.wait_for_success(query_id, timeout=wait_seconds, poll_interval=poll_interval)
    result = write_query_csv(query_id, arguments, client)
    result["engine"] = engine
    result["progress"] = summarize_progress(progress)
    return result

def ad_query_submit(arguments: dict[str, Any]) -> dict[str, Any]:
    """Submit one read-only SQL query and return its query id."""
    sql = str(arguments.get("sql") or "").strip()
    if not sql:
        raise ValueError("sql is required")
    engine = normalize_engine(arguments)
    validate_query(sql, engine)
    query_id = data_fortress_client().execute(sql, engine)
    return {"query_id": query_id, "engine": engine, "submitted": True}

def ad_query_status(arguments: dict[str, Any]) -> dict[str, Any]:
    """Check execution status for one submitted Data Fortress query."""
    query_id = str(arguments.get("query_id") or "").strip()
    if not query_id:
        raise ValueError("query_id is required")
    return summarize_progress(data_fortress_client().watch(query_id))

def ad_query_result(arguments: dict[str, Any]) -> dict[str, Any]:
    """Fetch a successful query result and return CSV."""
    query_id = str(arguments.get("query_id") or "").strip()
    if not query_id:
        raise ValueError("query_id is required")
    client = data_fortress_client()
    progress = client.watch(query_id)
    if progress.is_failure:
        raise RuntimeError(progress.log or str(progress.body))
    if not progress.is_success:
        raise RuntimeError(f"query is still running: {progress.log or query_id}")
    result = write_query_csv(query_id, arguments, client)
    result["progress"] = summarize_progress(progress)
    return result

def ad_render_report(arguments: dict[str, Any]) -> dict[str, Any]:
    """Render one allowlisted skill template from schema-validated report data."""
    return render_report(ROOT, RUNTIME_DIR, arguments, config=load_project_config())

def ad_upload_report(arguments: dict[str, Any]) -> dict[str, Any]:
    """Upload an existing local HTML report; never renders a report."""
    report_file = str(arguments.get("report_file") or "").strip()
    if not report_file:
        raise ValueError("report_file is required")
    title = str(arguments.get("title") or "Animal 广告分析报告").strip()
    today = str(arguments.get("today") or dt.date.today().isoformat())
    upload_name = safe_name(arguments.get("upload_name"), default_upload_name(title, today))
    report_path = Path(report_file).expanduser().resolve()
    if not report_path.is_file() or report_path.suffix.lower() != ".html":
        raise ValueError("report_file must be an existing local HTML file")
    url = run_stage("飞书上传", [sys.executable, "mcp/shared/feishu_upload.py", "--file",
                    str(report_path), "--upload-name", upload_name], 700).splitlines()[-1].strip()
    return {"report_html": str(report_path), "upload_name": upload_name, "url": url}

TOOLS = [
    {"name": "ad_query", "description": "执行一条只读广告业务 SQL，轮询到成功后返回 CSV；不包含业务分析或报告生成。",
     "inputSchema": {"type": "object", "properties": {"sql": {"type": "string"},
         "engine": {"type": "string", "default": "trino_new"}, "wait": {"type": "integer", "default": 300},
         "poll_interval": {"type": "number", "default": 2}, "fetch_rows": {"type": "integer", "default": 1000},
         "output_name": {"type": "string"}, "max_chars": {"type": "integer", "default": 200000}},
         "required": ["sql"], "additionalProperties": False}},
    {"name": "ad_query_submit", "description": "提交一条只读广告业务 SQL 并返回 query_id；不等待结果。",
     "inputSchema": {"type": "object", "properties": {"sql": {"type": "string"},
         "engine": {"type": "string", "default": "trino_new"}},
         "required": ["sql"], "additionalProperties": False}},
    {"name": "ad_query_status", "description": "查询已提交 SQL 的执行进度；输入 query_id，返回是否成功、失败和执行日志。",
     "inputSchema": {"type": "object", "properties": {"query_id": {"type": "string"}},
         "required": ["query_id"], "additionalProperties": False}},
    {"name": "ad_query_result", "description": "获取已成功 SQL 的结果，写入 CSV 并把 CSV 内容返回给 AI。",
     "inputSchema": {"type": "object", "properties": {"query_id": {"type": "string"},
         "fetch_rows": {"type": "integer", "default": 1000}, "output_name": {"type": "string"},
         "max_chars": {"type": "integer", "default": 200000}},
         "required": ["query_id"], "additionalProperties": False}},
    {"name": "ad_render_report", "description": "用已安装 Skill 的固定模板和 Schema 将结构化分析结果渲染为 HTML；不查询、不上传。",
     "inputSchema": {"type": "object", "properties": {"template_id": {"type": "string"},
         "report_data": {"type": "object"}, "local_name": {"type": "string"}},
         "required": ["template_id", "report_data"], "additionalProperties": False}},
    {"name": "ad_upload_report", "description": "上传本地已有的 HTML 报告并返回 URL；文件可以来自 MCP 渲染、Skill、Codex 或其他本地流程，不生成报告。",
     "inputSchema": {"type": "object", "properties": {"report_file": {"type": "string"},
         "title": {"type": "string"}, "today": {"type": "string"}, "upload_name": {"type": "string"}},
         "required": ["report_file"], "additionalProperties": False}},
]
HANDLERS = {"ad_query": ad_query, "ad_query_submit": ad_query_submit,
            "ad_query_status": ad_query_status, "ad_query_result": ad_query_result,
            "ad_render_report": ad_render_report, "ad_upload_report": ad_upload_report}

def handle(request: dict[str, Any]) -> None:
    method, request_id = request.get("method"), request.get("id")
    try:
        if method == "initialize":
            requested = (request.get("params") or {}).get("protocolVersion")
            respond(request_id, {"protocolVersion": requested if requested in SUPPORTED_PROTOCOL_VERSIONS else LATEST_PROTOCOL_VERSION,
                                 "capabilities": {"tools": {}}, "serverInfo": {"name": "ad-agent", "version": "0.3.0"}})
        elif method == "ping": respond(request_id, {})
        elif method == "resources/list": respond(request_id, {"resources": []})
        elif method == "prompts/list": respond(request_id, {"prompts": []})
        elif method == "tools/list": respond(request_id, {"tools": TOOLS})
        elif method == "tools/call":
            params = request.get("params") or {}
            handler = HANDLERS.get(params.get("name"))
            if handler is None:
                raise ValueError(f"unknown tool: {params.get('name')}")
            result = handler(params.get("arguments") or {})
            respond(request_id, {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False, indent=2)}], "isError": False})
        elif method and method.startswith("notifications/"): return
        else: respond(request_id, error={"code": -32601, "message": f"method not found: {method}"})
    except Exception as exc:
        if method == "tools/call":
            respond(request_id, {"content": [{"type": "text", "text": str(exc)}], "isError": True})
        else:
            respond(request_id, error={"code": -32000, "message": str(exc)})

def main() -> None:
    debug_log("server starting")
    while (message := read_message()) is not None:
        handle(message)

if __name__ == "__main__":
    main()
