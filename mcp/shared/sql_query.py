from __future__ import annotations

import base64
import csv
import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

import requests

try:
    from Crypto.Cipher import AES
except ModuleNotFoundError as exc:  # pragma: no cover - exercised before tests can import
    raise ModuleNotFoundError(
        "Missing dependency: pycryptodome. Run `.venv/bin/python -m pip install -r mcp/requirements.txt`."
    ) from exc


DEFAULT_BASE_URL = "https://smesser.happyelements.cn/data_fortress/external_api/v2"
DEFAULT_FETCH_ROWS = 1000
DEFAULT_POLL_INTERVAL = 2.0
DEFAULT_TIMEOUT = 600
BLOCK_SIZE = AES.block_size


@dataclass(frozen=True)
class QueryProgress:
    query_id: str
    is_success: bool
    is_failure: bool
    log: str
    body: dict[str, Any]


def load_config(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValueError(f"config file not found: {path}") from exc
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot read config file {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ValueError("config.json must contain a JSON object")
    return value


def required_config(config: dict[str, Any], field: str) -> str:
    value = config.get(field)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"config.json field is required: {field}")
    return value.strip()


def encrypt_sig(aes_key: str, execution_user: str, value: str, timestamp: int) -> str:
    plaintext = f"{execution_user}&{value}&{timestamp}".encode("utf-8")
    padding = BLOCK_SIZE - len(plaintext) % BLOCK_SIZE
    padded = plaintext + bytes([padding]) * padding
    try:
        cipher = AES.new(aes_key.encode("utf-8"), AES.MODE_ECB)
    except ValueError as exc:
        raise ValueError("data_fortress_aes_key must be 16, 24, or 32 UTF-8 bytes") from exc
    return base64.b64encode(cipher.encrypt(padded)).decode("ascii")


def decrypt_result(aes_key: str, encrypted: str) -> Any:
    try:
        cipher = AES.new(aes_key.encode("utf-8"), AES.MODE_ECB)
        decoded = cipher.decrypt(base64.b64decode(encrypted))
        padding = decoded[-1]
        if not 1 <= padding <= BLOCK_SIZE or decoded[-padding:] != bytes([padding]) * padding:
            raise ValueError("invalid PKCS#7 padding")
        text = decoded[:-padding].decode("utf-8")
        return json.loads(text)
    except (ValueError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"failed to decrypt API results: {exc}") from exc


class DataFortressClient:
    def __init__(
        self,
        platform_user: str,
        aes_key: str,
        base_url: str = DEFAULT_BASE_URL,
        request_timeout: int = 30,
    ) -> None:
        self.platform_user = platform_user
        self.aes_key = aes_key
        self.base_url = base_url.rstrip("/")
        self.request_timeout = request_timeout
        self.session = requests.Session()

    def _request(self, path: str, value: str, **params: Any) -> dict[str, Any]:
        timestamp = int(time.time())
        query = {
            "platform_user": self.platform_user,
            "sig": encrypt_sig(self.aes_key, self.platform_user, value, timestamp),
            **params,
        }
        response = self.session.get(
            f"{self.base_url}/{path.lstrip('/')}",
            params=query,
            timeout=self.request_timeout,
        )
        response.raise_for_status()
        try:
            body = response.json()
        except ValueError as exc:
            raise RuntimeError(f"Data Fortress returned non-JSON response: {response.text[:300]}") from exc
        if not isinstance(body, dict):
            raise RuntimeError("Data Fortress response must be a JSON object")
        if body.get("status") == -1:
            raise RuntimeError(str(body.get("message") or body.get("log") or body))
        return body

    def execute(self, sql: str, engine: str | None) -> str:
        params = {"engine": engine} if engine else {}
        body = self._request("query/execute", sql, **params)
        query_id = body.get("id")
        if body.get("status") != 0 or query_id is None:
            raise RuntimeError(f"SQL execute failed: {body}")
        return str(query_id)

    def watch(self, query_id: str) -> QueryProgress:
        body = self._request("watch/json", query_id)
        return QueryProgress(
            query_id=query_id,
            is_success=body.get("isSuccess") is True,
            is_failure=body.get("isFailure") is True,
            log=str(body.get("log") or body.get("message") or ""),
            body=body,
        )

    def wait_for_success(
        self,
        query_id: str,
        timeout: int = DEFAULT_TIMEOUT,
        poll_interval: float = DEFAULT_POLL_INTERVAL,
        on_progress: Callable[[QueryProgress], None] | None = None,
    ) -> QueryProgress:
        deadline = time.monotonic() + timeout
        last_progress: QueryProgress | None = None
        while time.monotonic() < deadline:
            progress = self.watch(query_id)
            last_progress = progress
            if on_progress is not None:
                on_progress(progress)
            if progress.is_success:
                return progress
            if progress.is_failure:
                raise RuntimeError(progress.log or str(progress.body))
            time.sleep(poll_interval)
        suffix = f": {last_progress.log}" if last_progress and last_progress.log else ""
        raise TimeoutError(f"SQL query timed out after {timeout} seconds: {query_id}{suffix}")

    def fetch_rows(self, query_id: str, fetch_rows: int = DEFAULT_FETCH_ROWS) -> tuple[list[str], list[list[Any]]]:
        columns: list[str] | None = None
        rows: list[list[Any]] = []
        first_row = 0
        while True:
            body = self._request(
                "results/raw",
                query_id,
                first_row=first_row,
                fetch_rows=fetch_rows,
            )
            if body.get("error") is True:
                raise RuntimeError(str(body.get("message") or body))
            current_columns = [str(item.get("name") or "") for item in body.get("columns", [])]
            if columns is None:
                columns = current_columns
            encrypted = body.get("results")
            decoded = decrypt_result(self.aes_key, encrypted) if isinstance(encrypted, str) and encrypted else []
            if isinstance(decoded, str):
                decoded = json.loads(decoded)
            if not isinstance(decoded, list):
                raise ValueError("decrypted results must be a JSON array")
            for row in decoded:
                if isinstance(row, dict):
                    rows.append([row.get(column) for column in columns or current_columns])
                elif isinstance(row, list):
                    rows.append(row)
                else:
                    raise ValueError("decrypted result row must be an array or object")
            if not body.get("has_more"):
                break
            next_row = body.get("next_row")
            if next_row is None or int(next_row) <= first_row:
                raise RuntimeError(f"invalid pagination response: {body}")
            first_row = int(next_row)
        return columns or [], rows


def write_csv(path: Path, columns: list[str], rows: list[list[Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(columns)
        writer.writerows(rows)
