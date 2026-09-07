"""Render allowlisted report templates from schema-validated JSON payloads."""

from __future__ import annotations

import json
import math
import os
import re
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker


PLACEHOLDER = "__REPORT_DATA_JSON__"
TEMPLATE_ID_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,63}$")
CONFIG_PATH_RE = re.compile(r"^[A-Za-z0-9_-]+(?:\.[A-Za-z0-9_-]+)*$")
MAX_PAYLOAD_BYTES = 2 * 1024 * 1024


@dataclass(frozen=True)
class ReportTemplate:
    template_id: str
    template_path: Path
    schema_path: Path
    schema_version: str
    config_bindings: dict[str, str]


def _inside(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


def _asset_path(assets_dir: Path, value: Any, field: str) -> Path:
    relative = Path(str(value or ""))
    if not str(relative) or relative.is_absolute():
        raise ValueError(f"report manifest {field} must be a relative path")
    resolved = (assets_dir / relative).resolve()
    if not _inside(resolved, assets_dir.resolve()) or not resolved.is_file():
        raise ValueError(f"report manifest {field} is outside assets or missing: {relative}")
    return resolved


def discover_templates(root: Path) -> dict[str, ReportTemplate]:
    """Discover report manifests owned by installed skills."""
    skills_root = (root / ".agents" / "skills").resolve()
    registry: dict[str, ReportTemplate] = {}
    for manifest_path in sorted(skills_root.glob("*/assets/report_manifest.json")):
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        template_id = str(manifest.get("template_id") or "")
        if not TEMPLATE_ID_RE.fullmatch(template_id):
            raise ValueError(f"invalid template_id in {manifest_path}: {template_id!r}")
        if template_id in registry:
            raise ValueError(f"duplicate report template_id: {template_id}")
        assets_dir = manifest_path.parent.resolve()
        template_path = _asset_path(assets_dir, manifest.get("template"), "template")
        schema_path = _asset_path(assets_dir, manifest.get("schema"), "schema")
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(schema)
        config_bindings = manifest.get("config_bindings") or {}
        if not isinstance(config_bindings, dict) or any(
            not isinstance(target, str)
            or not isinstance(source, str)
            or not CONFIG_PATH_RE.fullmatch(target)
            or not CONFIG_PATH_RE.fullmatch(source)
            for target, source in config_bindings.items()
        ):
            raise ValueError(f"invalid config_bindings in {manifest_path}")
        registry[template_id] = ReportTemplate(
            template_id=template_id,
            template_path=template_path,
            schema_path=schema_path,
            schema_version=str(manifest.get("schema_version") or "1"),
            config_bindings=dict(config_bindings),
        )
    return registry


def _config_value(config: dict[str, Any], path: str) -> Any:
    value: Any = config
    for part in path.split("."):
        if not isinstance(value, dict) or part not in value:
            raise ValueError(f"config.json is missing required field: {path}")
        value = value[part]
    if value is None or (isinstance(value, str) and not value.strip()):
        raise ValueError(f"config.json field is empty: {path}")
    return value.strip() if isinstance(value, str) else value


def _apply_config_bindings(
    payload: dict[str, Any], bindings: dict[str, str], config: dict[str, Any] | None
) -> dict[str, Any]:
    if not bindings:
        return payload
    if config is None:
        raise ValueError("config.json is required by this report template")
    result = deepcopy(payload)
    for target, source in bindings.items():
        current = result
        parts = target.split(".")
        for part in parts[:-1]:
            child = current.get(part)
            if child is None:
                child = {}
                current[part] = child
            if not isinstance(child, dict):
                raise ValueError(f"report_data.{part} must be an object for config injection")
            current = child
        current[parts[-1]] = _config_value(config, source)
    return result


def _json_for_script(payload: dict[str, Any]) -> str:
    def reject_nonfinite(value: Any) -> None:
        if isinstance(value, float) and not math.isfinite(value):
            raise ValueError("report_data must not contain NaN or Infinity")
        if isinstance(value, dict):
            for item in value.values():
                reject_nonfinite(item)
        elif isinstance(value, list):
            for item in value:
                reject_nonfinite(item)

    reject_nonfinite(payload)
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
    )
    if len(encoded.encode("utf-8")) > MAX_PAYLOAD_BYTES:
        raise ValueError(f"report_data exceeds {MAX_PAYLOAD_BYTES} bytes")
    return (
        encoded.replace("&", "\\u0026")
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("\u2028", "\\u2028")
        .replace("\u2029", "\\u2029")
    )


def _format_validation_errors(errors: list[Any]) -> str:
    lines: list[str] = []
    for error in errors[:8]:
        path = "report_data"
        for part in error.absolute_path:
            path += f"[{part}]" if isinstance(part, int) else f".{part}"
        lines.append(f"{path}: {error.message}")
    if len(errors) > 8:
        lines.append(f"... and {len(errors) - 8} more errors")
    return "; ".join(lines)


def render_report(
    root: Path,
    runtime_dir: Path,
    arguments: dict[str, Any],
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    template_id = str(arguments.get("template_id") or "").strip()
    report_data = arguments.get("report_data")
    if not template_id:
        raise ValueError("template_id is required")
    if not isinstance(report_data, dict):
        raise ValueError("report_data must be an object")

    registry = discover_templates(root)
    spec = registry.get(template_id)
    if spec is None:
        available = ", ".join(sorted(registry)) or "(none)"
        raise ValueError(f"unknown template_id: {template_id}; available: {available}")
    report_data = _apply_config_bindings(report_data, spec.config_bindings, config)

    schema = json.loads(spec.schema_path.read_text(encoding="utf-8"))
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    errors = sorted(
        validator.iter_errors(report_data),
        key=lambda item: tuple(str(part) for part in item.absolute_path),
    )
    if errors:
        raise ValueError("report_data validation failed: " + _format_validation_errors(errors))

    template = spec.template_path.read_text(encoding="utf-8")
    if template.count(PLACEHOLDER) != 1:
        raise ValueError(f"template must contain exactly one {PLACEHOLDER} placeholder")
    html = template.replace(PLACEHOLDER, _json_for_script(report_data))
    if "<!doctype html>" not in html.lower() or '<html lang="zh">' not in html.lower():
        raise ValueError("rendered report must be a Chinese HTML document")

    local_name = str(arguments.get("local_name") or "report.html").strip()
    if not local_name or Path(local_name).name != local_name or not local_name.endswith(".html"):
        raise ValueError("local_name must be an HTML file name without a directory path")
    runtime_dir.mkdir(parents=True, exist_ok=True)
    output_path = (runtime_dir / local_name).resolve()
    runtime_root = runtime_dir.resolve()
    if not _inside(output_path, runtime_root):
        raise ValueError("rendered report path must stay inside the runtime directory")
    temp_path = output_path.with_suffix(output_path.suffix + ".tmp")
    temp_path.write_text(html, encoding="utf-8")
    os.replace(temp_path, output_path)
    return {
        "template_id": template_id,
        "schema_version": spec.schema_version,
        "report_file": str(output_path),
        "bytes": output_path.stat().st_size,
    }
