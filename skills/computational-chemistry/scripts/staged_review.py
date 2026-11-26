#!/usr/bin/env python3
"""Validate staged intake data and generate one overwrite-in-place review page."""

from __future__ import annotations

import argparse
import html
import json
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any

BASE_REQUIRED = (
    "calculation_goal",
    "structure",
    "software",
    "software_version",
    "run_location",
    "environment",
    "requested_files",
    "return_files",
    "key_parameters",
)


class IntakeIncompleteError(ValueError):
    """Raised when a review is requested before intake is complete."""


def _present(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (Mapping, list, tuple, set)):
        return bool(value)
    return True


def missing_fields(payload: Mapping[str, Any]) -> list[str]:
    """Return required fields that are absent for the selected execution route."""
    missing = [name for name in BASE_REQUIRED if not _present(payload.get(name))]
    run_location = str(payload.get("run_location", "")).lower()
    wants_submit = bool(payload.get("generate_submit_script"))

    if any(token in run_location for token in ("server", "cluster", "集群", "服务器")):
        if not _present(payload.get("server_environment")):
            missing.append("server_environment")
        if not _present(payload.get("scheduler")):
            missing.append("scheduler")
    elif any(token in run_location for token in ("wsl", "windows", "local", "本地")):
        if not _present(payload.get("local_environment")):
            missing.append("local_environment")

    if wants_submit and not _present(payload.get("scheduler_resources")):
        missing.append("scheduler_resources")
    return list(dict.fromkeys(missing))


def next_question_fields(payload: Mapping[str, Any], limit: int = 2) -> list[str]:
    """Return only the next small group of missing fields for progressive intake."""
    if limit < 1:
        raise ValueError("limit must be positive")
    return missing_fields(payload)[:limit]


def execution_route(payload: Mapping[str, Any]) -> str:
    """Select an executor family without launching an external program."""
    location = str(payload.get("run_location", "")).lower()
    if any(token in location for token in ("wsl", "linux", "cluster", "server", "集群", "服务器")):
        return "bash_or_native"
    if "windows" in location or "win11" in location:
        return "controlled_pwsh7_or_native"
    return "native_or_manual"


def _flatten(prefix: str, value: Any) -> list[tuple[str, str]]:
    if isinstance(value, Mapping):
        rows: list[tuple[str, str]] = []
        for key, item in value.items():
            rows.extend(_flatten(f"{prefix}.{key}" if prefix else str(key), item))
        return rows
    if isinstance(value, list):
        return [(prefix, "\n".join(str(item) for item in value))]
    return [(prefix, "" if value is None else str(value))]


def _lookup(payload: Mapping[str, Any], dotted_name: str, fallback: Any) -> Any:
    current: Any = payload
    for part in dotted_name.split("."):
        if not isinstance(current, Mapping) or part not in current:
            return fallback
        current = current[part]
    return current


def review_html(payload: Mapping[str, Any]) -> str:
    """Return a self-contained, editable review form for the current intake payload."""
    fields = []
    for key, value in payload.items():
        if key.startswith("_"):
            continue
        fields.extend(_flatten(str(key), value))

    controls = []
    for name, value in fields:
        escaped_name = html.escape(name, quote=True)
        escaped_value = html.escape(value, quote=True)
        raw_value = _lookup(payload, name, value)
        if name in {"run_location", "scheduler"}:
            standard = (
                ("windows", "wsl", "local_linux", "local_macos", "linux_cluster", "remote_server")
                if name == "run_location"
                else ("none", "slurm", "pbs", "lsf", "other")
            )
            options = list(standard)
            if value and value.lower() not in standard:
                options.insert(0, value)
            option_html = "".join(
                f'<option value="{html.escape(option, quote=True)}"'
                f'{" selected" if option.lower() == value.lower() else ""}>'
                f'{html.escape(option)}</option>'
                for option in options
            )
            control = f'<label><span>{escaped_name}</span><select name="{escaped_name}">{option_html}</select></label>'
        elif isinstance(raw_value, bool):
            control = (
                f'<label class="switch"><span>{escaped_name}</span>'
                f'<input type="checkbox" name="{escaped_name}" value="true"'
                f'{" checked" if raw_value else ""}></label>'
            )
        elif isinstance(raw_value, (int, float)) and not isinstance(raw_value, bool):
            control = (
                f'<label><span>{escaped_name}</span>'
                f'<input type="number" name="{escaped_name}" value="{escaped_value}"></label>'
            )
        elif "\n" in value or len(value) > 100:
            control = (
                f'<label><span>{escaped_name}</span>'
                f'<textarea name="{escaped_name}" rows="4">{html.escape(value)}</textarea></label>'
            )
        else:
            control = (
                f'<label><span>{escaped_name}</span>'
                f'<input name="{escaped_name}" value="{escaped_value}"></label>'
            )
        controls.append(control)

    return """<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>计算方案最终审查</title>
<style>
body{font-family:system-ui,sans-serif;max-width:960px;margin:2rem auto;padding:0 1rem;color:#172033}
h1{margin-bottom:.3rem}.hint{color:#526174}.grid{display:grid;grid-template-columns:1fr 1fr;gap:1rem}
label{display:flex;flex-direction:column;gap:.35rem;font-weight:650}.switch{flex-direction:row;align-items:center}
input,textarea,select{font:inherit;padding:.65rem;border:1px solid #aab5c6;border-radius:.45rem}
textarea{resize:vertical}.actions{display:flex;gap:.75rem;margin-top:1.5rem}
button{font:inherit;padding:.7rem 1rem;border:0;border-radius:.45rem;background:#155eef;color:white}
@media(max-width:720px){.grid{grid-template-columns:1fr}}
</style>
</head>
<body>
<h1>计算方案最终审查</h1>
<p class="hint">请检查并修改表单。确认后可下载结构化回传；也可以在聊天中明确确认。</p>
<form id="reviewForm"><div class="grid">""" + "".join(controls) + """</div>
<div class="actions">
<button type="button" id="approve">确认并下载回传</button>
<button type="button" id="revision">下载修改回传</button>
</div></form>
<script>
function response(decision){
  const form=document.getElementById('reviewForm');
  const values=Object.fromEntries(new FormData(form).entries());
  for(const checkbox of form.querySelectorAll('input[type=checkbox]')) values[checkbox.name]=checkbox.checked;
  const blob=new Blob([JSON.stringify({decision,status:'confirmed',values},null,2)],{type:'application/json'});
  const link=document.createElement('a');link.href=URL.createObjectURL(blob);
  link.download='review_response.json';link.click();URL.revokeObjectURL(link.href);
}
document.getElementById('approve').onclick=()=>response('approved');
document.getElementById('revision').onclick=()=>response('revision_required');
</script>
</body></html>
"""


def render_review(payload: Mapping[str, Any], project_dir: Path) -> Path:
    """Validate intake and overwrite the single review page."""
    missing = missing_fields(payload)
    if missing:
        raise IntakeIncompleteError("missing required intake fields: " + ", ".join(missing))
    review_dir = project_dir / ".review"
    review_dir.mkdir(parents=True, exist_ok=True)
    target = review_dir / "review.html"
    target.write_text(review_html(payload), encoding="utf-8")
    return target


def _load_payload(path: str) -> dict[str, Any]:
    text = sys.stdin.read() if path == "-" else Path(path).read_text(encoding="utf-8")
    data = json.loads(text)
    if not isinstance(data, dict):
        raise ValueError("intake payload must be a JSON object")
    return data


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    for name in ("check", "render"):
        subparser = subparsers.add_parser(name)
        subparser.add_argument("source", help="UTF-8 JSON file or '-' for stdin")
        if name == "render":
            subparser.add_argument("--project-dir", type=Path, default=Path.cwd())
    return parser


def main() -> int:
    args = build_parser().parse_args()
    payload = _load_payload(args.source)
    missing = missing_fields(payload)
    if args.command == "check":
        print(
            json.dumps(
                {
                    "complete": not missing,
                    "missing": missing,
                    "next_questions": next_question_fields(payload),
                    "executor": execution_route(payload),
                },
                ensure_ascii=False,
            )
        )
        return 0 if not missing else 2
    try:
        target = render_review(payload, args.project_dir)
    except IntakeIncompleteError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    print(target)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
