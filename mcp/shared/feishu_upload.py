# /// script
# requires-python = ">=3.9"
# dependencies = ["requests"]
# ///
"""Upload a local report file to Feishu Drive and print the file URL.

Usage:
  .venv/bin/python mcp/shared/feishu_upload.py \
      --file var/ad-agent/report.html \
      --upload-name "Animal 广告分析报告 - 2026-05-13.html"

Feishu config is read from project-root config.json:
  {
    "feishu_app": {"app_id": "cli_xxx", "app_secret": "xxx"},
    "feishu_drive": {"parent_node": "folder_token"}
  }
"""

import argparse
import json
import os
import sys

import requests


CONFIG_PATH = os.path.normpath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "config.json")
)
BASE = "https://open.feishu.cn/open-apis"


def load_config() -> dict:
    try:
        with open(CONFIG_PATH, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def require_config(**items: str) -> None:
    missing = [name for name, value in items.items() if not value]
    if missing:
        print("missing Feishu config: " + ", ".join(missing), file=sys.stderr)
        sys.exit(1)


def get_token(app_id: str, app_secret: str) -> str:
    resp = requests.post(
        f"{BASE}/auth/v3/tenant_access_token/internal",
        json={"app_id": app_id, "app_secret": app_secret},
        timeout=10,
    )
    resp.raise_for_status()
    body = resp.json()
    if body.get("code") != 0:
        raise RuntimeError(f"failed to get Feishu tenant token: {body}")
    return body["tenant_access_token"]


def list_files(token: str, folder_token: str) -> list[dict]:
    files: list[dict] = []
    page_token = ""
    while True:
        params = {"folder_token": folder_token, "page_size": 200}
        if page_token:
            params["page_token"] = page_token
        resp = requests.get(
            f"{BASE}/drive/v1/files",
            params=params,
            headers={"Authorization": f"Bearer {token}"},
            timeout=15,
        )
        resp.raise_for_status()
        body = resp.json()
        if body.get("code") != 0:
            raise RuntimeError(f"failed to list Feishu files: {body}")
        data = body.get("data") or {}
        files.extend(data.get("files") or [])
        if not data.get("has_more"):
            return files
        page_token = data.get("next_page_token") or ""
        if not page_token:
            return files


def delete_file(token: str, file_token: str) -> None:
    resp = requests.delete(
        f"{BASE}/drive/v1/files/{file_token}",
        params={"type": "file"},
        headers={"Authorization": f"Bearer {token}"},
        timeout=15,
    )
    resp.raise_for_status()
    body = resp.json()
    if body.get("code") != 0:
        raise RuntimeError(f"failed to delete existing Feishu file: {body}")


def upload_file(token: str, path: str, upload_name: str, folder_token: str, content_type: str) -> str:
    with open(path, "rb") as f:
        resp = requests.post(
            f"{BASE}/drive/v1/files/upload_all",
            headers={"Authorization": f"Bearer {token}"},
            data={
                "file_name": upload_name,
                "parent_type": "explorer",
                "parent_node": folder_token,
                "size": str(os.path.getsize(path)),
            },
            files={"file": (upload_name, f, content_type)},
            timeout=60,
        )
    resp.raise_for_status()
    body = resp.json()
    if body.get("code") != 0:
        raise RuntimeError(f"failed to upload Feishu file: {body}")
    return body["data"]["url"]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--file", required=True, help="local file path")
    parser.add_argument("--upload-name", default=None, help="file name shown in Feishu Drive")
    parser.add_argument("--content-type", default="text/html", help="MIME type")
    parser.add_argument(
        "--keep-existing",
        action="store_true",
        help="do not delete an existing Feishu file with the same name in the target folder",
    )
    args = parser.parse_args()

    cfg = load_config()
    app_cfg = cfg.get("feishu_app") or {}
    drive_cfg = cfg.get("feishu_drive") or {}
    app_id = app_cfg.get("app_id")
    app_secret = app_cfg.get("app_secret")
    folder_token = drive_cfg.get("parent_node")
    upload_name = args.upload_name or os.path.basename(args.file)

    require_config(
        FEISHU_APP_ID=app_id,
        FEISHU_APP_SECRET=app_secret,
        **{"feishu_drive.parent_node in config.json": folder_token},
    )

    token = get_token(app_id, app_secret)
    if not args.keep_existing:
        for item in list_files(token, folder_token):
            if item.get("name") == upload_name and item.get("token"):
                delete_file(token, item["token"])
                break

    print(upload_file(token, args.file, upload_name, folder_token, args.content_type))


if __name__ == "__main__":
    main()
