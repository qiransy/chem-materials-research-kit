"""Map the common browser decision gate onto an existing stage state machine."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

from review_ui.workflow import (
    ReviewWorkflowError,
    prepare_review_request,
    run_review_session,
    utc_now,
)

WAITING_FOR_REVIEW_DECISION = "WAITING_FOR_REVIEW_DECISION"


def execute_stage_review(
    *,
    project_dir: Path,
    stage_dir: Path,
    stage: str,
    title: str,
    content_file: Path,
    allowed_statuses: set[str],
    revision_status: str,
    rejected_status: str,
    load_status: Callable[[], dict[str, Any]],
    save_status: Callable[[dict[str, Any]], None],
    append_log: Callable[[dict[str, Any]], None],
    approve: Callable[[str], dict[str, Any]],
    error_type: type[Exception],
    blocked_access_updates: dict[str, Any] | None = None,
    revision_updates: dict[str, Any] | None = None,
    rejected_updates: dict[str, Any] | None = None,
    status_field: str = "status",
    start_port: int = 5050,
    timeout_seconds: float | None = None,
) -> dict[str, Any]:
    """Prepare, wait, validate, and map one browser decision without copying stage logic."""

    del stage_dir  # Kept in the interface to make each owning stage explicit.
    status = load_status()
    resume_status = str(status.get(status_field, ""))
    if resume_status not in allowed_statuses:
        raise error_type(
            f"Browser review cannot start from {resume_status!r}; expected one of {sorted(allowed_statuses)}."
        )
    try:
        request_payload = prepare_review_request(project_dir, stage, title, content_file)
    except ReviewWorkflowError as exc:
        raise error_type(str(exc)) from exc

    status.update(blocked_access_updates or {})
    status.update(
        {
            status_field: WAITING_FOR_REVIEW_DECISION,
            "updated_at": utc_now(),
            "review_request_id": request_payload["request_id"],
            "review_content_hash": request_payload["content_hash"],
            "review_resume_status": resume_status,
            "review_comment": None,
        }
    )
    save_status(status)
    append_log(
        {
            "event": "BROWSER_REVIEW_REQUESTED",
            "timestamp": utc_now(),
            "stage": stage,
            "request_id": request_payload["request_id"],
            "content_hash": request_payload["content_hash"],
            "status_before": resume_status,
            "status_after": WAITING_FOR_REVIEW_DECISION,
        }
    )
    try:
        decision = run_review_session(
            project_dir,
            request_payload,
            start_port=start_port,
            decision_timeout_seconds=timeout_seconds,
        )
    except ReviewWorkflowError as exc:
        status = load_status()
        status.update(
            {
                status_field: WAITING_FOR_REVIEW_DECISION,
                "updated_at": utc_now(),
                "last_review_error": str(exc),
            }
        )
        save_status(status)
        raise error_type(str(exc)) from exc

    status = load_status()
    status.update(
        {
            "review_decision": decision["decision"],
            "review_comment": decision.get("comment", ""),
            "review_confirmed_at": decision["confirmed_at"],
            "updated_at": utc_now(),
        }
    )
    if decision["decision"] == "approved":
        status[status_field] = resume_status
        save_status(status)
        return approve(decision.get("comment", ""))

    if decision["decision"] == "revision_required":
        status.update(revision_updates or {})
        status[status_field] = revision_status
        event = "BROWSER_REVISION_REQUIRED"
    else:
        status.update(rejected_updates or {})
        status[status_field] = rejected_status
        event = "BROWSER_REVIEW_REJECTED"
    save_status(status)
    append_log(
        {
            "event": event,
            "timestamp": utc_now(),
            "stage": stage,
            "request_id": decision["request_id"],
            "content_hash": decision["content_hash"],
            "comment": decision.get("comment", ""),
            "status_before": WAITING_FOR_REVIEW_DECISION,
            "status_after": status[status_field],
        }
    )
    return {"status": status, "review_decision": decision}
