#!/usr/bin/env python3
"""End-to-end API, versioning, and browser-approval regression for the Stage-1 editor."""

from __future__ import annotations

import argparse
import copy
import json
import os
import sys
import threading
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from http.server import ThreadingHTTPServer
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import stage1_review as stage1  # noqa: E402


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def http_json(url: str, method: str = "GET", payload: dict[str, Any] | None = None) -> dict[str, Any]:
    data = None if payload is None else json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=data,
        method=method,
        headers={"Content-Type": "application/json", "Cache-Control": "no-cache"},
    )
    with urllib.request.urlopen(request, timeout=20) as response:
        result = json.loads(response.read().decode("utf-8"))
    if not isinstance(result, dict):
        raise RuntimeError(f"Expected JSON object from {url}")
    return result


def wait_for(getter: Callable[[], Any], predicate: Callable[[Any], bool], label: str, timeout: float = 30.0) -> Any:
    deadline = time.monotonic() + timeout
    last: Any = None
    while time.monotonic() < deadline:
        try:
            last = getter()
            if predicate(last):
                return last
        except (OSError, ValueError, urllib.error.URLError) as exc:
            last = str(exc)
        time.sleep(0.1)
    raise RuntimeError(f"Timed out waiting for {label}; last={last!r}")


class EditorServer:
    def __init__(self, planning_dir: Path):
        stage1.ensure_review_html(planning_dir)
        handler = type("ValidationReviewHandler", (stage1.ReviewHandler,), {"planning_dir": planning_dir})
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}/"

    def __enter__(self) -> EditorServer:
        self.thread.start()
        wait_for(lambda: http_json(self.url + "api/state"), lambda value: bool(value.get("plan")), "editor server")
        return self

    def __exit__(self, *_: object) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)


def prepare_project(root: Path, source_plan: dict[str, Any], label: str) -> tuple[Path, Path]:
    project = root / label
    planning = project / "planning"
    project.mkdir(parents=True, exist_ok=False)
    plan = copy.deepcopy(source_plan)
    plan["project_id"] = f"EDITOR-E2E-{label.upper()}"
    source = project / "stage1_plan_source.json"
    write_json(source, plan)
    stage1.initialize(planning, source)
    return project, planning


def test_editor_api(root: Path, source_plan: dict[str, Any]) -> dict[str, Any]:
    project, planning = prepare_project(root, source_plan, "editor_api")
    with EditorServer(planning) as server:
        initial = http_json(server.url + "api/state")
        if initial["status"]["status"] != stage1.WAITING_FOR_USER_APPROVAL:
            raise RuntimeError("Unexpected initial workflow state")
        if not initial["candidate_content_hash"].startswith("sha256:"):
            raise RuntimeError("Candidate hash was not exposed")

        invalid = copy.deepcopy(initial["plan"])
        invalid["research_goal"]["core_question"] = ""
        invalid_check = http_json(server.url + "api/check", "POST", {"plan": invalid})["result"]
        if invalid_check["valid"] or not any("research_goal.core_question" in item for item in invalid_check["errors"]):
            raise RuntimeError("Field-level Schema error was not reported")

        draft_plan = copy.deepcopy(initial["plan"])
        draft_plan["research_goal"]["comparison_object"] = "API 草稿比较对象"
        draft_result = http_json(server.url + "api/draft", "POST", {"plan": draft_plan})["result"]
        after_draft = http_json(server.url + "api/state")
        if after_draft["status"]["status"] != stage1.WAITING_FOR_USER_APPROVAL or after_draft["versions"] != ["v001"]:
            raise RuntimeError("Draft save changed status or version history")
        draft_file = read_json(planning / "stage1_plan_draft.json")
        if draft_file["draft_status"] != "SAVED_NOT_SUBMITTED" or draft_file["plan"]["research_goal"]["comparison_object"] != "API 草稿比较对象":
            raise RuntimeError("Draft artifact did not preserve edited data")

        protected_plan = copy.deepcopy(initial["plan"])
        old_project_id = protected_plan["project_id"]
        protected_plan["project_id"] = old_project_id + "-CORRECTED"
        protected_plan["manual_overrides"] = [{
            "path": "project_id",
            "old_value": old_project_id,
            "new_value": protected_plan["project_id"],
            "reason": "API validation of generated protected-field audit record",
            "modified_at": "2026-07-19T00:00:00Z",
            "actor": "workflow-validation",
            "stage": 1,
            "manual_override": True,
        }]
        protected_check = http_json(server.url + "api/check", "POST", {"plan": protected_plan})["result"]
        if not protected_check["valid"]:
            raise RuntimeError(f"Generated manual_overrides was rejected: {protected_check['errors']}")

        submitted = copy.deepcopy(initial["plan"])
        submitted["research_goal"]["comparison_object"] = "已版本化的 API 比较对象"
        submit_result = http_json(
            server.url + "api/submit",
            "POST",
            {"plan": submitted, "reason": "Validate immutable versioning from structured editor"},
        )["result"]
        if submit_result["status"]["current_candidate_version"] != "v002" or submit_result["status"]["status"] != stage1.IMPACT_ANALYSIS_READY:
            raise RuntimeError("Formal submit did not create v002 and impact analysis")
        v001 = read_json(planning / "stage1_plan_v001.json")
        v002 = read_json(planning / "stage1_plan_v002.json")
        if v001["research_goal"]["comparison_object"] == v002["research_goal"]["comparison_object"]:
            raise RuntimeError("Immutable old version or submitted version is incorrect")
        state_after_submit = http_json(server.url + "api/state")
        if not state_after_submit["analysis"] or not state_after_submit["change_log"]:
            raise RuntimeError("Difference analysis or history was lost")

        rejected = http_json(
            server.url + "api/action", "POST", {"action": "reject", "reason": "Validate existing reject branch"}
        )["result"]
        if rejected["status"]["status"] != stage1.WAITING_FOR_FINAL_APPROVAL or rejected["status"]["current_candidate_version"] != "v001":
            raise RuntimeError("Existing modification reject branch changed semantics")

    return {
        "status_before": initial["status"]["status"],
        "candidate_content_hash": initial["candidate_content_hash"],
        "invalid_schema_detected": True,
        "draft_result": draft_result,
        "draft_did_not_create_version": True,
        "manual_overrides_accepted": True,
        "submitted_version": "v002",
        "history_preserved": True,
        "impact_analysis_preserved": True,
        "old_version_preserved": True,
        "reject_branch_status": rejected["status"]["status"],
        "project": str(project),
    }


def approval_scenario(root: Path, source_plan: dict[str, Any], decision: str) -> dict[str, Any]:
    project, planning = prepare_project(root, source_plan, f"approval_{decision}")
    browser_log = project / "review" / "browser_open_test.jsonl"
    previous_hook = os.environ.get("CC_REVIEW_TEST_BROWSER_LOG")
    os.environ["CC_REVIEW_TEST_BROWSER_LOG"] = str(browser_log)
    try:
        with EditorServer(planning) as server:
            accepted = http_json(
                server.url + "api/action",
                "POST",
                {"action": "accept", "reason": "Validated candidate ready for browser approval"},
            )["result"]
            if accepted["status"]["status"] != stage1.WAITING_FOR_FINAL_APPROVAL:
                raise RuntimeError("Candidate did not enter WAITING_FOR_FINAL_APPROVAL")
            started = http_json(server.url + "api/start-review", "POST", {})["result"]
            request_path = project / "review" / "review_request.json"
            request = wait_for(lambda: read_json(request_path), lambda value: value.get("request_id") == started.get("request_id"), "review request")
            if request["stage"] != "stage1" or request["content_hash"] != started["content_hash"]:
                raise RuntimeError("Review request was not bound to stage and content hash")
            waiting = wait_for(
                lambda: read_json(planning / "stage1_status.json"),
                lambda value: value.get("status") == stage1.WAITING_FOR_REVIEW_DECISION,
                "WAITING_FOR_REVIEW_DECISION",
            )
            session_path = project / "review" / "session.json"
            session = wait_for(
                lambda: read_json(session_path),
                lambda value: value.get("server_ready") is True and bool(value.get("server_url")),
                "ready approval server",
            )
            health = http_json(session["server_url"] + "api/health")
            if health.get("request_id") != request["request_id"] or health.get("content_hash") != request["content_hash"]:
                raise RuntimeError("Approval health response did not match active request")
            decision_response = http_json(
                session["server_url"] + "api/review-decision",
                "POST",
                {
                    "request_id": request["request_id"],
                    "stage": request["stage"],
                    "content_hash": request["content_hash"],
                    "decision": decision,
                    "comment": f"workflow validation {decision}",
                },
            )
            if not decision_response.get("ok"):
                raise RuntimeError("Approval server did not accept matching decision")
            expected = {
                "approved": stage1.APPROVED,
                "revision_required": stage1.WAITING_FOR_USER_APPROVAL,
                "rejected": stage1.STAGE1_REVIEW_REJECTED,
            }[decision]
            final_status = wait_for(
                lambda: read_json(planning / "stage1_status.json"),
                lambda value: value.get("status") == expected,
                f"final status {expected}",
                timeout=40,
            )
            final_session = wait_for(
                lambda: read_json(session_path),
                lambda value: value.get("server_shutdown") is True and value.get("lock_released") is True,
                "approval server shutdown and lock release",
                timeout=20,
            )
            decision_file = read_json(project / "review" / "review_decision.json")
            for field in ("request_id", "stage", "content_hash"):
                if decision_file[field] != request[field]:
                    raise RuntimeError(f"Decision binding mismatch: {field}")
            if decision_file.get("status") != "confirmed" or decision_file.get("decision") != decision:
                raise RuntimeError("Decision file was not confirmed")
            if decision == "approved":
                for name in ("stage1_plan_approved.json", "stage1_plan_approved.md", "stage1_approval_record.json"):
                    if not (planning / name).exists():
                        raise RuntimeError(f"Approved baseline artifact missing: {name}")
            else:
                if (planning / "stage1_plan_approved.json").exists():
                    raise RuntimeError("Non-approved decision created an approved baseline")
            if not browser_log.exists() or "browser_open_attempted" not in browser_log.read_text(encoding="utf-8"):
                raise RuntimeError("Review process did not attempt to open the independent browser page")
    finally:
        if previous_hook is None:
            os.environ.pop("CC_REVIEW_TEST_BROWSER_LOG", None)
        else:
            os.environ["CC_REVIEW_TEST_BROWSER_LOG"] = previous_hook

    return {
        "decision": decision,
        "request_id": request["request_id"],
        "stage": request["stage"],
        "content_hash": request["content_hash"],
        "waiting_status": waiting["status"],
        "final_status": final_status["status"],
        "server_url": session["server_url"],
        "server_ready": session["server_ready"],
        "browser_open_attempted": True,
        "decision_confirmed": True,
        "server_shutdown": final_session["server_shutdown"],
        "lock_released": final_session["lock_released"],
        "request_example": str(request_path),
        "decision_example": str(project / "review" / "review_decision.json"),
        "server_log": str(project / "review" / "server.log"),
        "gate_log": str(planning / "stage1_review_gate.log"),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-plan", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    output = args.output_dir.resolve()
    if output.exists():
        raise SystemExit(f"Output directory already exists: {output}")
    output.mkdir(parents=True)
    source_plan = read_json(args.source_plan.resolve())
    results: list[dict[str, Any]] = []

    tests: list[tuple[str, Callable[[], dict[str, Any]]]] = [
        ("editor_api_version_draft_and_diff", lambda: test_editor_api(output, source_plan)),
        ("approval_approved", lambda: approval_scenario(output, source_plan, "approved")),
        ("approval_revision_required", lambda: approval_scenario(output, source_plan, "revision_required")),
        ("approval_rejected", lambda: approval_scenario(output, source_plan, "rejected")),
    ]
    for name, callback in tests:
        try:
            evidence = callback()
            results.append({"name": name, "status": "PASSED", "evidence": evidence})
        except Exception as exc:  # Continue to collect all evidence.
            results.append({"name": name, "status": "FAILED", "error": f"{type(exc).__name__}: {exc}"})

    report = {
        "schema_version": "1.0",
        "generated_at": stage1.utc_now(),
        "source_plan": str(args.source_plan.resolve()),
        "results": results,
        "overall_status": "PASSED" if all(item["status"] == "PASSED" for item in results) else "FAILED",
    }
    report_path = output / "stage1_editor_workflow_validation.json"
    write_json(report_path, report)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["overall_status"] == "PASSED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
