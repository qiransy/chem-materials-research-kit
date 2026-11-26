#!/usr/bin/env python3
"""Run real local-HTTP end-to-end validation for every registered browser gate."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import signal
import socket
import sys
import threading
import time
import urllib.error
import urllib.request
import uuid
from collections.abc import Callable
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parents[1]
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from review_ui.server import atomic_write_json, content_sha256  # noqa: E402
from review_ui.stage_gate import WAITING_FOR_REVIEW_DECISION, execute_stage_review  # noqa: E402
from review_ui.stage_registry import REVIEW_GATES  # noqa: E402


def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise AssertionError(f"Expected JSON object: {path}")
    return value


def wait_until(predicate: Callable[[], Any], timeout: float = 15.0, interval: float = 0.05) -> Any:
    deadline = time.monotonic() + timeout
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            value = predicate()
            if value:
                return value
        except Exception as exc:  # transient file/HTTP state
            last_error = exc
        time.sleep(interval)
    raise AssertionError(f"Timed out waiting for condition; last_error={last_error!r}")


def get_text(url: str) -> tuple[int, str]:
    try:
        with urllib.request.urlopen(url, timeout=3) as response:
            return response.status, response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode("utf-8")


def get_json(url: str) -> tuple[int, dict[str, Any]]:
    status, text = get_text(url)
    value = json.loads(text)
    return status, value if isinstance(value, dict) else {"value": value}


def post_json(url: str, payload: dict[str, Any]) -> tuple[int, dict[str, Any]]:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=3) as response:
            value = json.loads(response.read().decode("utf-8"))
            return response.status, value
    except urllib.error.HTTPError as exc:
        value = json.loads(exc.read().decode("utf-8"))
        return exc.code, value


def scan_registered_gates(skill_root: Path) -> list[dict[str, Any]]:
    inventory: list[dict[str, Any]] = []
    common_gate_path = skill_root / "scripts" / "review_ui" / "stage_gate.py"
    common_gate_source = common_gate_path.read_text(encoding="utf-8")
    common_gate_sets_waiting = WAITING_FOR_REVIEW_DECISION in common_gate_source
    for gate in REVIEW_GATES:
        script_path = skill_root / "scripts" / str(gate["script"])
        source = script_path.read_text(encoding="utf-8")
        delegates_to_common_gate = "execute_stage_review(" in source
        waiting_state_present = WAITING_FOR_REVIEW_DECISION in source or (
            delegates_to_common_gate and common_gate_sets_waiting
        )
        inventory.append(
            {
                **gate,
                "script_path": str(script_path),
                "script_exists": script_path.is_file(),
                "stage_id_present": str(gate["stage"]) in source,
                "command_present": f'"{gate["command"]}"' in source,
                "waiting_state_present": waiting_state_present,
                "waiting_state_source": (
                    "stage_script"
                    if WAITING_FOR_REVIEW_DECISION in source
                    else "common_stage_gate"
                    if delegates_to_common_gate and common_gate_sets_waiting
                    else "missing"
                ),
                "overall_status": "PASSED"
                if script_path.is_file()
                and str(gate["stage"]) in source
                and f'"{gate["command"]}"' in source
                and waiting_state_present
                else "FAILED",
            }
        )
    return inventory


def seed_previous_review(review_dir: Path, stage: str) -> None:
    review_dir.mkdir(parents=True, exist_ok=True)
    atomic_write_json(
        review_dir / "review_request.json",
        {
            "schema_version": "1.0",
            "request_id": f"old-{uuid.uuid4().hex}",
            "stage": stage,
            "title": "old",
            "content_file": "old.json",
            "content_hash": "sha256:" + "0" * 64,
            "content": "old",
            "created_at": "2000-01-01T00:00:00+00:00",
            "status": "pending",
        },
    )
    atomic_write_json(
        review_dir / "review_decision.json",
        {
            "schema_version": "1.0",
            "request_id": "old-request",
            "stage": stage,
            "content_hash": "sha256:" + "0" * 64,
            "decision": "approved",
            "comment": "stale",
            "status": "confirmed",
            "confirmed_at": "2000-01-01T00:00:01+00:00",
        },
    )
    atomic_write_json(review_dir / "session.json", {"state": "old"})
    atomic_write_json(
        review_dir / "lock.json",
        {"pid": 99999999, "port": 5050, "request_id": "old-request", "stage": stage},
    )


def run_branch_case(
    output_root: Path,
    gate: dict[str, Any],
    decision_name: str,
    *,
    open_real_browser: bool,
    occupy_default_port: bool = False,
) -> dict[str, Any]:
    case_root = output_root / "gates" / str(gate["stage"]) / decision_name
    if case_root.exists():
        shutil.rmtree(case_root)
    case_root.mkdir(parents=True)
    content_file = case_root / "candidate.json"
    content = json.dumps(
        {
            "stage": gate["stage"],
            "gate_name": gate["name"],
            "branch": decision_name,
            "nonce": uuid.uuid4().hex,
            "complete_content_marker": "FULL_REVIEW_CONTENT_VISIBLE",
        },
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    ) + "\n"
    content_file.write_text(content, encoding="utf-8", newline="\n")
    stage_status_path = case_root / "stage_status.json"
    atomic_write_json(stage_status_path, {"status": "READY", "next_stage_access": False})
    stage_log_path = case_root / "stage_log.json"
    atomic_write_json(stage_log_path, [])
    seed_previous_review(case_root / "review", str(gate["stage"]))
    browser_test_log = case_root / "browser_open_test_hook.jsonl"
    if open_real_browser:
        os.environ.pop("CC_REVIEW_TEST_BROWSER_LOG", None)
    else:
        os.environ["CC_REVIEW_TEST_BROWSER_LOG"] = str(browser_test_log)

    def load_status() -> dict[str, Any]:
        return read_json(stage_status_path)

    def save_status(value: dict[str, Any]) -> None:
        atomic_write_json(stage_status_path, value)

    def append_log(value: dict[str, Any]) -> None:
        records = json.loads(stage_log_path.read_text(encoding="utf-8"))
        records.append(value)
        atomic_write_json(stage_log_path, {"records": records})
        normalized = read_json(stage_log_path)["records"]
        stage_log_path.write_text(json.dumps(normalized, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    def approve(comment: str) -> dict[str, Any]:
        status = load_status()
        status.update({"status": gate["approved_state"], "next_stage_access": True, "approval_comment": comment})
        save_status(status)
        return {"status": status}

    box: dict[str, Any] = {}

    def worker() -> None:
        try:
            box["result"] = execute_stage_review(
                project_dir=case_root,
                stage_dir=case_root,
                stage=str(gate["stage"]),
                title=str(gate["name"]),
                content_file=content_file,
                allowed_statuses={"READY"},
                revision_status=str(gate["revision_state"]),
                rejected_status=str(gate["rejected_state"]),
                load_status=load_status,
                save_status=save_status,
                append_log=append_log,
                approve=approve,
                error_type=RuntimeError,
                blocked_access_updates={"next_stage_access": False},
                revision_updates={"next_stage_access": False},
                rejected_updates={"next_stage_access": False},
                start_port=5050,
                timeout_seconds=20,
            )
        except Exception as exc:
            box["error"] = repr(exc)

    occupied_socket: socket.socket | None = None
    if occupy_default_port:
        occupied_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        occupied_socket.bind(("127.0.0.1", 5050))
        occupied_socket.listen(1)
    thread = threading.Thread(target=worker, name=f"review-{gate['stage']}-{decision_name}", daemon=True)
    thread.start()
    session_path = case_root / "review" / "session.json"
    session = wait_until(
        lambda: (read_json(session_path) if session_path.exists() and read_json(session_path).get("server_ready") else None),
        timeout=15,
    )
    if occupied_socket:
        occupied_socket.close()
    server_url = str(session["server_url"])
    request_path = case_root / "review" / "review_request.json"
    review_request = read_json(request_path)
    health_status, health = get_json(server_url + "api/health")
    api_status, api_request = get_json(server_url + "api/review-request")
    page_status, page_html = get_text(server_url)
    js_status, app_js = get_text(server_url + "static/app.js")

    waiting_state = read_json(stage_status_path)
    time.sleep(0.35)
    waiting_before_submit = thread.is_alive() and waiting_state.get("status") == WAITING_FOR_REVIEW_DECISION

    stale_during_wait = {
        "schema_version": "1.0",
        "request_id": "stale-during-wait",
        "stage": gate["stage"],
        "content_hash": "sha256:" + "1" * 64,
        "decision": "approved",
        "comment": "must not unblock",
        "status": "confirmed",
        "confirmed_at": "2000-01-01T00:00:02+00:00",
    }
    atomic_write_json(case_root / "review" / "review_decision.json", stale_during_wait)
    stale_result_rejected = bool(
        wait_until(
            lambda: thread.is_alive()
            and not (case_root / "review" / "review_decision.json").exists()
            and any((case_root / "review" / "history").glob("*mismatched-request_id*")),
            timeout=5,
        )
    )

    base_payload = {
        "request_id": review_request["request_id"],
        "stage": review_request["stage"],
        "content_hash": review_request["content_hash"],
        "decision": decision_name,
        "comment": f"{decision_name} comment for {gate['stage']}",
    }
    mismatch_results: list[bool] = []
    for field, wrong in (
        ("request_id", "wrong-request"),
        ("stage", "wrong-stage"),
        ("content_hash", "sha256:" + "f" * 64),
    ):
        bad = dict(base_payload)
        bad[field] = wrong
        code, response = post_json(server_url + "api/review-decision", bad)
        mismatch_results.append(code == 400 and response.get("ok") is False and not (case_root / "review" / "review_decision.json").exists())
    invalid_decision_payload = dict(base_payload)
    invalid_decision_payload["decision"] = "auto_approved"
    invalid_code, invalid_response = post_json(server_url + "api/review-decision", invalid_decision_payload)
    invalid_decision_rejected = (
        invalid_code == 400
        and invalid_response.get("ok") is False
        and not (case_root / "review" / "review_decision.json").exists()
    )

    code, valid_response = post_json(server_url + "api/review-decision", base_payload)
    thread.join(15)
    if thread.is_alive():
        raise AssertionError(f"Review worker did not finish for {gate['stage']}/{decision_name}")
    if box.get("error"):
        raise AssertionError(box["error"])
    decision_path = case_root / "review" / "review_decision.json"
    decision = read_json(decision_path)
    final_status = read_json(stage_status_path)
    final_session = read_json(session_path)
    expected_state = (
        gate["approved_state"]
        if decision_name == "approved"
        else gate["revision_state"]
        if decision_name == "revision_required"
        else gate["rejected_state"]
    )
    history = list((case_root / "review" / "history").glob("*"))
    page_content_visible = (
        page_status == 200
        and api_status == 200
        and api_request.get("content") == content
        and api_request.get("request_id") == review_request["request_id"]
        and all(token in page_html for token in ("stage", "request-id", "content-file", "created-at", "review-content", "content-hash"))
        and all(token in app_js for token in ("payload.stage", "payload.request_id", "payload.content_file", "payload.created_at", "payload.content", "payload.content_hash"))
    )
    hash_visible = page_content_visible and api_request.get("content_hash") == content_sha256(content)
    request_bound = all(decision.get(field) == review_request.get(field) for field in ("request_id", "stage", "content_hash"))
    branch_ok = final_status.get("status") == expected_state and (
        final_status.get("next_stage_access") is True if decision_name == "approved" else final_status.get("next_stage_access") is False
    )
    order_ok = str(final_session.get("server_ready_at", "")) <= str(final_session.get("browser_open_attempted_at", ""))
    checks = {
        "request_schema": all(
            field in review_request
            for field in ("schema_version", "request_id", "stage", "title", "content_file", "content_hash", "content", "created_at", "status")
        ),
        "server_ready": health_status == 200 and health.get("status") == "ready",
        "page_content_visible": page_content_visible,
        "hash_visible": hash_visible,
        "waiting_before_submit": waiting_before_submit,
        "stale_result_rejected": stale_result_rejected and len(history) >= 4,
        "hash_mismatch_rejected": all(mismatch_results),
        "invalid_decision_rejected": invalid_decision_rejected,
        "decision_written": code == 200 and valid_response.get("ok") is True,
        "decision_bound": request_bound and decision.get("status") == "confirmed" and bool(decision.get("confirmed_at")),
        "branch_ok": branch_ok,
        "health_before_browser": order_ok,
        "server_shutdown": final_session.get("server_shutdown") is True,
        "lock_released": final_session.get("lock_released") is True and not (case_root / "review" / "lock.json").exists(),
        "port_fallback": (not occupy_default_port) or not server_url.startswith("http://127.0.0.1:5050/"),
    }
    return {
        "decision": decision_name,
        "request_id": review_request["request_id"],
        "content_hash": review_request["content_hash"],
        "server_url": server_url,
        "server_ready": checks["server_ready"],
        "browser_open_attempted": final_session.get("browser_open_attempted") is True,
        "browser_open_success": final_session.get("browser_open_success") is True,
        "page_content_visible": page_content_visible,
        "hash_visible": hash_visible,
        "waiting_before_submit": waiting_before_submit,
        "stale_result_rejected": checks["stale_result_rejected"],
        "hash_mismatch_rejected": checks["hash_mismatch_rejected"],
        "final_state": final_status.get("status"),
        "expected_state": expected_state,
        "server_shutdown": checks["server_shutdown"],
        "lock_released": checks["lock_released"],
        "request_path": str(request_path),
        "decision_path": str(decision_path),
        "session_path": str(session_path),
        "server_log_path": str(case_root / "review" / "server.log"),
        "checks": checks,
        "overall_status": "PASSED" if all(checks.values()) and final_session.get("browser_open_attempted") is True and final_session.get("browser_open_success") is True else "FAILED",
    }


def validate_live_lock(output_root: Path) -> bool:
    review_dir = output_root / "lock_validation" / "review"
    review_dir.mkdir(parents=True, exist_ok=True)
    atomic_write_json(
        review_dir / "lock.json",
        {"pid": os.getpid(), "port": 65500, "request_id": "live", "stage": "lock-test"},
    )
    content = output_root / "lock_validation" / "content.txt"
    content.write_text("lock", encoding="utf-8")
    from review_ui.workflow import ReviewWorkflowError, prepare_review_request

    try:
        prepare_review_request(output_root / "lock_validation", "lock-test", "Lock", content)
    except ReviewWorkflowError:
        return True
    return False


def validate_browser_failure_waits(output_root: Path) -> bool:
    from review_ui import workflow

    root = output_root / "browser_failure_validation"
    root.mkdir(parents=True, exist_ok=True)
    content = root / "content.txt"
    content.write_text("browser failure must remain blocked\n", encoding="utf-8")
    request_payload = workflow.prepare_review_request(root, "browser-failure", "Browser failure", content)
    original_open = workflow._open_browser
    def fail_open(_url: str) -> tuple[bool, str | None]:
        return False, "synthetic browser launch failure"

    vars(workflow)["_open_browser"] = fail_open
    box: dict[str, Any] = {}

    def worker() -> None:
        try:
            box["result"] = workflow.run_review_session(root, request_payload, decision_timeout_seconds=10)
        except Exception as exc:
            box["error"] = repr(exc)

    thread = threading.Thread(target=worker, daemon=True)
    thread.start()
    try:
        session = wait_until(
            lambda: (
                read_json(root / "review" / "session.json")
                if (root / "review" / "session.json").exists()
                and read_json(root / "review" / "session.json").get("browser_open_attempted")
                else None
            ),
            timeout=10,
        )
        blocked = (
            session.get("browser_open_success") is False
            and thread.is_alive()
            and not (root / "review" / "review_decision.json").exists()
        )
        payload = {
            "request_id": request_payload["request_id"],
            "stage": request_payload["stage"],
            "content_hash": request_payload["content_hash"],
            "decision": "revision_required",
            "comment": "test cleanup",
        }
        code, _ = post_json(str(session["server_url"]) + "api/review-decision", payload)
        thread.join(10)
        return blocked and code == 200 and not thread.is_alive()
    finally:
        vars(workflow)["_open_browser"] = original_open


def validate_server_exit_never_approves(output_root: Path) -> bool:
    from review_ui import workflow

    root = output_root / "server_exit_validation"
    root.mkdir(parents=True, exist_ok=True)
    content = root / "content.txt"
    content.write_text("server exit must not approve\n", encoding="utf-8")
    request_payload = workflow.prepare_review_request(root, "server-exit", "Server exit", content)
    os.environ["CC_REVIEW_TEST_BROWSER_LOG"] = str(root / "browser_hook.jsonl")
    box: dict[str, Any] = {}

    def worker() -> None:
        try:
            box["result"] = workflow.run_review_session(root, request_payload, decision_timeout_seconds=10)
        except Exception as exc:
            box["error"] = repr(exc)

    thread = threading.Thread(target=worker, daemon=True)
    thread.start()
    lock = wait_until(
        lambda: (
            read_json(root / "review" / "lock.json")
            if (root / "review" / "lock.json").exists()
            and (root / "review" / "session.json").exists()
            and read_json(root / "review" / "session.json").get("server_ready")
            else None
        ),
        timeout=10,
    )
    os.kill(int(lock["pid"]), signal.SIGTERM)
    thread.join(10)
    session = read_json(root / "review" / "session.json")
    return (
        not thread.is_alive()
        and "error" in box
        and "result" not in box
        and not (root / "review" / "review_decision.json").exists()
        and session.get("state") == "STOPPED_WITHOUT_DECISION"
        and session.get("lock_released") is True
    )


def validate_independent_stage_sessions(output_root: Path) -> bool:
    from review_ui import workflow

    root = output_root / "independent_stage_sequence"
    root.mkdir(parents=True, exist_ok=True)
    os.environ["CC_REVIEW_TEST_BROWSER_LOG"] = str(root / "browser_hook.jsonl")
    records: list[dict[str, Any]] = []
    for gate in REVIEW_GATES:
        content = root / f"{gate['stage']}.txt"
        content.write_text(f"{gate['stage']} {uuid.uuid4().hex}\n", encoding="utf-8")
        request_payload = workflow.prepare_review_request(root, str(gate["stage"]), str(gate["name"]), content)
        box: dict[str, Any] = {}

        def worker(
            box: dict[str, Any] = box,
            request_payload: dict[str, Any] = request_payload,
        ) -> None:
            try:
                box["result"] = workflow.run_review_session(root, request_payload, decision_timeout_seconds=10)
            except Exception as exc:
                box["error"] = repr(exc)

        thread = threading.Thread(target=worker, daemon=True)
        thread.start()
        session = wait_until(
            lambda: (
                read_json(root / "review" / "session.json")
                if (root / "review" / "session.json").exists()
                and read_json(root / "review" / "session.json").get("server_ready")
                else None
            ),
            timeout=10,
        )
        payload = {
            "request_id": request_payload["request_id"],
            "stage": request_payload["stage"],
            "content_hash": request_payload["content_hash"],
            "decision": "approved",
            "comment": "independent sequence",
        }
        code, _ = post_json(str(session["server_url"]) + "api/review-decision", payload)
        thread.join(10)
        final_session = read_json(root / "review" / "session.json")
        if code != 200 or thread.is_alive() or box.get("error"):
            return False
        records.append(
            {
                "request_id": request_payload["request_id"],
                "content_hash": request_payload["content_hash"],
                "pid": final_session.get("pid"),
                "server_shutdown": final_session.get("server_shutdown"),
                "lock_released": final_session.get("lock_released"),
                "browser_open_attempted": final_session.get("browser_open_attempted"),
            }
        )
    history = list((root / "review" / "history").glob("*"))
    return (
        len({item["request_id"] for item in records}) == len(REVIEW_GATES)
        and len({item["content_hash"] for item in records}) == len(REVIEW_GATES)
        and all(item["server_shutdown"] and item["lock_released"] and item["browser_open_attempted"] for item in records)
        and len(history) >= (len(REVIEW_GATES) - 1) * 3
        and not (root / "review" / "lock.json").exists()
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--skip-real-browser", action="store_true", help="Use only the browser-order test hook.")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    output_root = args.output_root.resolve()
    if output_root.exists() and any(output_root.iterdir()):
        raise SystemExit(f"Refusing to overwrite nonempty validation root: {output_root}")
    output_root.mkdir(parents=True, exist_ok=True)
    skill_root = Path(__file__).resolve().parents[2]
    inventory = scan_registered_gates(skill_root)
    atomic_write_json(output_root / "stage_inventory.json", {"gates": inventory})
    stage_results: list[dict[str, Any]] = []
    for index, gate in enumerate(REVIEW_GATES):
        approved = run_branch_case(
            output_root,
            gate,
            "approved",
            open_real_browser=not args.skip_real_browser,
            occupy_default_port=index == 0,
        )
        revision = run_branch_case(output_root, gate, "revision_required", open_real_browser=False)
        rejected = run_branch_case(output_root, gate, "rejected", open_real_browser=False)
        stage_checks = {
            "stage": gate["stage"],
            "main_stage": gate["main_stage"],
            "name": gate["name"],
            "request_id": approved["request_id"],
            "content_hash": approved["content_hash"],
            "server_url": approved["server_url"],
            "server_ready": approved["server_ready"],
            "browser_open_attempted": approved["browser_open_attempted"],
            "page_content_visible": approved["page_content_visible"],
            "hash_visible": approved["hash_visible"],
            "waiting_before_submit": approved["waiting_before_submit"],
            "approved_result": approved,
            "revision_required_result": revision,
            "rejected_result": rejected,
            "stale_result_rejected": approved["stale_result_rejected"],
            "hash_mismatch_rejected": approved["hash_mismatch_rejected"],
            "invalid_decision_rejected": approved["checks"]["invalid_decision_rejected"],
            "server_shutdown": all(item["server_shutdown"] for item in (approved, revision, rejected)),
            "lock_released": all(item["lock_released"] for item in (approved, revision, rejected)),
        }
        stage_checks["overall_status"] = (
            "PASSED"
            if all(item["overall_status"] == "PASSED" for item in (approved, revision, rejected))
            and all(
                stage_checks[key]
                for key in (
                    "server_ready",
                    "browser_open_attempted",
                    "page_content_visible",
                    "hash_visible",
                    "waiting_before_submit",
                    "stale_result_rejected",
                    "hash_mismatch_rejected",
                    "invalid_decision_rejected",
                    "server_shutdown",
                    "lock_released",
                )
            )
            else "FAILED"
        )
        stage_results.append(stage_checks)

    unique_requests = len({item["request_id"] for item in stage_results}) == len(stage_results)
    unique_hashes = len({item["content_hash"] for item in stage_results}) == len(stage_results)
    inventory_passed = all(item["overall_status"] == "PASSED" for item in inventory)
    live_lock_rejected = validate_live_lock(output_root)
    browser_failure_waits = validate_browser_failure_waits(output_root)
    server_exit_never_approves = validate_server_exit_never_approves(output_root)
    independent_stage_sessions = validate_independent_stage_sessions(output_root)
    overall = (
        "PASSED"
        if inventory_passed
        and unique_requests
        and unique_hashes
        and live_lock_rejected
        and browser_failure_waits
        and server_exit_never_approves
        and independent_stage_sessions
        and all(item["overall_status"] == "PASSED" for item in stage_results)
        else "FAILED"
    )
    report = {
        "schema_version": "1.0",
        "validation_kind": "browser_review_end_to_end",
        "skill_root": str(skill_root),
        "identified_main_stages": sorted({str(item["main_stage"]) for item in REVIEW_GATES}),
        "identified_review_gates": [str(item["stage"]) for item in REVIEW_GATES],
        "inventory_path": str(output_root / "stage_inventory.json"),
        "inventory_passed": inventory_passed,
        "unique_request_ids": unique_requests,
        "unique_content_hashes": unique_hashes,
        "live_lock_rejected": live_lock_rejected,
        "browser_failure_waits": browser_failure_waits,
        "server_exit_never_approves": server_exit_never_approves,
        "independent_stage_sessions": independent_stage_sessions,
        "stages": stage_results,
        "overall_status": overall,
    }
    validation_path = output_root / "browser_enforcement_validation.json"
    atomic_write_json(validation_path, report)
    print(json.dumps({"validation_path": str(validation_path), "overall_status": overall}, ensure_ascii=False, indent=2))
    return 0 if overall == "PASSED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
