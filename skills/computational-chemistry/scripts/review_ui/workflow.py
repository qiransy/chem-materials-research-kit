"""Process, lock, archive, browser, and decision helpers for review gates."""

from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
import uuid
import webbrowser
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from review_ui.server import (
    ALLOWED_DECISIONS,
    SCHEMA_VERSION,
    atomic_write_json,
    content_sha256,
    normalize_text,
    read_json,
)

HOST = "127.0.0.1"
DEFAULT_START_PORT = 5050


class ReviewWorkflowError(RuntimeError):
    """Raised when the local browser review gate cannot complete safely."""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def _timestamp_token() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")


def _load_optional_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        return read_json(path)
    except (ValueError, OSError):
        return None


def _pid_alive(pid: Any) -> bool:
    try:
        numeric_pid = int(pid)
    except (TypeError, ValueError):
        return False
    if numeric_pid <= 0:
        return False
    if os.name == "nt":
        import ctypes
        from ctypes import wintypes

        process_query_limited_information = 0x1000
        still_active = 259
        win_dll = getattr(ctypes, "WinDLL", None)
        if win_dll is None:
            return False
        kernel32 = win_dll("kernel32", use_last_error=True)
        kernel32.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
        kernel32.OpenProcess.restype = wintypes.HANDLE
        kernel32.GetExitCodeProcess.argtypes = (wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD))
        kernel32.GetExitCodeProcess.restype = wintypes.BOOL
        kernel32.CloseHandle.argtypes = (wintypes.HANDLE,)
        kernel32.CloseHandle.restype = wintypes.BOOL
        handle = kernel32.OpenProcess(process_query_limited_information, False, numeric_pid)
        if not handle:
            return False
        try:
            exit_code = wintypes.DWORD()
            if not kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code)):
                return False
            return exit_code.value == still_active
        finally:
            kernel32.CloseHandle(handle)
    try:
        os.kill(numeric_pid, 0)
    except OSError:
        return False
    return True


def _archive_path(path: Path, history_dir: Path, label: str) -> Path | None:
    if not path.exists():
        return None
    history_dir.mkdir(parents=True, exist_ok=True)
    target = history_dir / f"{_timestamp_token()}_{label}_{path.name}"
    counter = 1
    while target.exists():
        target = history_dir / f"{_timestamp_token()}_{label}_{counter}_{path.name}"
        counter += 1
    os.replace(path, target)
    return target


def _archive_previous_session(review_dir: Path) -> list[str]:
    history_dir = review_dir / "history"
    archived: list[str] = []
    for name in ("review_request.json", "review_decision.json", "session.json"):
        target = _archive_path(review_dir / name, history_dir, "previous")
        if target:
            archived.append(str(target))
    return archived


def _guard_or_archive_lock(review_dir: Path, stage: str) -> None:
    lock_path = review_dir / "lock.json"
    if not lock_path.exists():
        return
    lock = _load_optional_json(lock_path)
    if lock and _pid_alive(lock.get("pid")):
        raise ReviewWorkflowError(
            "A browser review is already active "
            f"(stage={lock.get('stage')}, request_id={lock.get('request_id')}, "
            f"pid={lock.get('pid')}, port={lock.get('port')})."
        )
    _archive_path(lock_path, review_dir / "history", f"stale-lock-{stage}")


def prepare_review_request(
    project_dir: Path,
    stage: str,
    title: str,
    content_file: Path,
) -> dict[str, Any]:
    """Archive the previous session and atomically create a fresh request."""

    project_dir = project_dir.resolve()
    content_file = content_file.resolve()
    if not content_file.is_file():
        raise ReviewWorkflowError(f"Review content file is missing: {content_file}")
    review_dir = project_dir / "review"
    review_dir.mkdir(parents=True, exist_ok=True)
    _guard_or_archive_lock(review_dir, stage)
    archived = _archive_previous_session(review_dir)

    content = normalize_text(content_file.read_text(encoding="utf-8"))
    try:
        content_file_value = content_file.relative_to(project_dir).as_posix()
    except ValueError:
        content_file_value = str(content_file)
    request_payload: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "request_id": f"{stage}-{uuid.uuid4().hex}",
        "stage": stage,
        "title": title,
        "content_file": content_file_value,
        "content_hash": content_sha256(content),
        "content": content,
        "created_at": utc_now(),
        "status": "pending",
    }
    atomic_write_json(review_dir / "review_request.json", request_payload)
    if archived:
        request_payload["archived_previous_files"] = archived
    return request_payload


def _find_available_port(start_port: int = DEFAULT_START_PORT) -> int:
    for port in range(start_port, 65536):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
            probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                probe.bind((HOST, port))
            except OSError:
                continue
            return port
    raise ReviewWorkflowError(f"No available local port was found from {start_port}.")


def _get_json(url: str, timeout: float = 1.0) -> dict[str, Any]:
    request = urllib.request.Request(url, headers={"Cache-Control": "no-cache"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        payload = json.loads(response.read().decode("utf-8"))
    if not isinstance(payload, dict):
        raise ReviewWorkflowError(f"Expected a JSON object from {url}.")
    return payload


def _wait_for_health(
    url: str,
    request_payload: dict[str, Any],
    process: subprocess.Popen[Any],
    timeout_seconds: float,
) -> dict[str, Any]:
    deadline = time.monotonic() + timeout_seconds
    last_error = "no response"
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise ReviewWorkflowError(
                f"Review server exited before becoming healthy (exit code {process.returncode})."
            )
        try:
            health = _get_json(url + "api/health")
            if (
                health.get("ok") is True
                and health.get("status") == "ready"
                and health.get("request_id") == request_payload["request_id"]
                and health.get("stage") == request_payload["stage"]
                and health.get("content_hash") == request_payload["content_hash"]
            ):
                return health
            last_error = f"health payload did not match active request: {health}"
        except (OSError, ValueError, urllib.error.URLError, json.JSONDecodeError) as exc:
            last_error = str(exc)
        time.sleep(0.1)
    raise ReviewWorkflowError(f"Review server health check timed out: {last_error}")


def _open_browser(url: str) -> tuple[bool, str | None]:
    """Open the browser after health succeeds; test hooks only record the attempt."""

    test_log = os.environ.get("CC_REVIEW_TEST_BROWSER_LOG")
    if test_log:
        Path(test_log).parent.mkdir(parents=True, exist_ok=True)
        with Path(test_log).open("a", encoding="utf-8") as handle:
            handle.write(json.dumps({"event": "browser_open_attempted", "url": url, "at": utc_now()}) + "\n")
        return True, None
    try:
        if os.name == "nt":
            startfile = getattr(os, "startfile", None)
            if startfile is None:
                return False, "os.startfile is unavailable"
            startfile(url)
            return True, None
        opened = bool(webbrowser.open(url, new=1))
        return opened, None if opened else "webbrowser.open returned false"
    except Exception as exc:  # Browser failure must not become approval.
        return False, str(exc)


def _archive_invalid_decision(review_dir: Path, reason: str) -> Path | None:
    safe_reason = "".join(character if character.isalnum() or character in "-_" else "-" for character in reason)
    return _archive_path(review_dir / "review_decision.json", review_dir / "history", f"invalid-{safe_reason}")


def _validated_decision(path: Path, request_payload: dict[str, Any]) -> tuple[dict[str, Any] | None, str | None]:
    if not path.exists():
        return None, None
    try:
        decision = read_json(path)
    except (ValueError, OSError) as exc:
        return None, f"invalid-json-{type(exc).__name__}"
    for field in ("request_id", "stage", "content_hash"):
        if decision.get(field) != request_payload.get(field):
            return None, f"mismatched-{field}"
    if decision.get("status") != "confirmed":
        return None, "status-not-confirmed"
    if decision.get("decision") not in ALLOWED_DECISIONS:
        return None, "invalid-decision"
    if not str(decision.get("confirmed_at", "")).strip():
        return None, "missing-confirmed-at"
    return decision, None


def _wait_for_decision(
    review_dir: Path,
    request_payload: dict[str, Any],
    process: subprocess.Popen[Any],
    timeout_seconds: float | None,
) -> dict[str, Any]:
    deadline = None if not timeout_seconds or timeout_seconds <= 0 else time.monotonic() + timeout_seconds
    decision_path = review_dir / "review_decision.json"
    while True:
        if process.poll() is not None:
            raise ReviewWorkflowError(
                f"Review server exited before a confirmed decision was received (exit code {process.returncode})."
            )
        decision, invalid_reason = _validated_decision(decision_path, request_payload)
        if decision is not None:
            return decision
        if invalid_reason:
            _archive_invalid_decision(review_dir, invalid_reason)
        if deadline is not None and time.monotonic() >= deadline:
            raise ReviewWorkflowError("Timed out while waiting for a matching confirmed browser decision.")
        time.sleep(0.2)


def _stop_process(process: subprocess.Popen[Any]) -> bool:
    if process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)
    return process.poll() is not None


def _release_lock(review_dir: Path, request_id: str) -> bool:
    lock_path = review_dir / "lock.json"
    lock = _load_optional_json(lock_path)
    if lock and lock.get("request_id") == request_id:
        lock_path.unlink(missing_ok=True)
    return not lock_path.exists()


def run_review_session(
    project_dir: Path,
    request_payload: dict[str, Any],
    *,
    start_port: int = DEFAULT_START_PORT,
    health_timeout_seconds: float = 15.0,
    decision_timeout_seconds: float | None = None,
    waiting_callback: Callable[[dict[str, Any]], None] | None = None,
) -> dict[str, Any]:
    """Start the isolated service, open the browser, and block for a bound decision."""

    project_dir = project_dir.resolve()
    review_dir = project_dir / "review"
    active_request = read_json(review_dir / "review_request.json")
    for field in ("request_id", "stage", "content_hash"):
        if active_request.get(field) != request_payload.get(field):
            raise ReviewWorkflowError(f"Active review request changed before server start: {field}.")

    _guard_or_archive_lock(review_dir, str(request_payload["stage"]))
    port = _find_available_port(start_port)
    url = f"http://{HOST}:{port}/"
    server_path = Path(__file__).resolve().parent / "server.py"
    log_path = review_dir / "server.log"
    log_handle = log_path.open("a", encoding="utf-8", buffering=1)
    creation_flags = int(getattr(subprocess, "CREATE_NO_WINDOW", 0)) if os.name == "nt" else 0
    process = subprocess.Popen(
        [
            sys.executable,
            str(server_path),
            "--project-dir",
            str(project_dir),
            "--host",
            HOST,
            "--port",
            str(port),
        ],
        cwd=str(project_dir),
        stdin=subprocess.DEVNULL,
        stdout=log_handle,
        stderr=subprocess.STDOUT,
        creationflags=creation_flags,
    )
    lock = {
        "schema_version": SCHEMA_VERSION,
        "pid": process.pid,
        "port": port,
        "request_id": request_payload["request_id"],
        "stage": request_payload["stage"],
        "created_at": utc_now(),
    }
    atomic_write_json(review_dir / "lock.json", lock)
    session = {
        **lock,
        "server_url": url,
        "server_ready": False,
        "browser_open_attempted": False,
        "browser_open_success": False,
        "state": "STARTING_SERVER",
    }
    atomic_write_json(review_dir / "session.json", session)
    decision: dict[str, Any] | None = None
    try:
        health = _wait_for_health(url, request_payload, process, health_timeout_seconds)
        session.update({"server_ready": True, "server_ready_at": utc_now(), "health": health, "state": "WAITING_FOR_REVIEW_DECISION"})
        atomic_write_json(review_dir / "session.json", session)
        print(f"Review URL: {url}", flush=True)
        print("State: WAITING_FOR_REVIEW_DECISION", flush=True)

        opened, browser_error = _open_browser(url)
        session.update(
            {
                "browser_open_attempted": True,
                "browser_open_attempted_at": utc_now(),
                "browser_open_success": opened,
                "browser_open_error": browser_error,
            }
        )
        atomic_write_json(review_dir / "session.json", session)
        if not opened:
            print(f"Browser opening failed; use this URL manually: {url}", file=sys.stderr, flush=True)
        if waiting_callback:
            waiting_callback(dict(session))

        decision = _wait_for_decision(review_dir, request_payload, process, decision_timeout_seconds)
        session.update({"state": "DECISION_RECEIVED", "decision_received_at": utc_now(), "decision": decision["decision"]})
        atomic_write_json(review_dir / "session.json", session)
        return decision
    finally:
        server_stopped = _stop_process(process)
        lock_released = _release_lock(review_dir, str(request_payload["request_id"]))
        session.update(
            {
                "server_shutdown": server_stopped,
                "server_shutdown_at": utc_now(),
                "lock_released": lock_released,
                "state": "COMPLETED" if decision else "STOPPED_WITHOUT_DECISION",
            }
        )
        atomic_write_json(review_dir / "session.json", session)
        log_handle.close()


def archive_review_artifacts(project_dir: Path, label: str) -> list[str]:
    """Archive request/decision/session and a stale lock before an isolated test."""

    review_dir = project_dir.resolve() / "review"
    review_dir.mkdir(parents=True, exist_ok=True)
    lock_path = review_dir / "lock.json"
    lock = _load_optional_json(lock_path)
    if lock and _pid_alive(lock.get("pid")):
        raise ReviewWorkflowError(f"Cannot archive an active review lock for {label}.")
    archived = _archive_previous_session(review_dir)
    target = _archive_path(lock_path, review_dir / "history", f"{label}-stale-lock")
    if target:
        archived.append(str(target))
    for temporary in review_dir.glob(".*.tmp"):
        target = _archive_path(temporary, review_dir / "history", f"{label}-temporary")
        if target:
            archived.append(str(target))
    return archived
