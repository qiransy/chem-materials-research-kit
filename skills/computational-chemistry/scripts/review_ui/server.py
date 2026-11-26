#!/usr/bin/env python3
"""Serve one hash-bound browser review request and record its decision."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import tempfile
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from flask import Flask, jsonify, request, send_from_directory

SCHEMA_VERSION = "1.0"
ALLOWED_DECISIONS = {"approved", "revision_required", "rejected"}
REQUIRED_REQUEST_FIELDS = {
    "schema_version",
    "request_id",
    "stage",
    "title",
    "content_file",
    "content_hash",
    "content",
    "created_at",
    "status",
}
STATIC_DIR = Path(__file__).resolve().parent / "static"


class ReviewServiceError(ValueError):
    """Raised when a review request or decision is invalid."""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def normalize_text(value: str) -> str:
    """Return the canonical text representation used for review hashes."""

    if not isinstance(value, str):
        raise ReviewServiceError("Review content must be text.")
    return unicodedata.normalize("NFC", value.replace("\r\n", "\n").replace("\r", "\n"))


def content_sha256(value: str) -> str:
    normalized = normalize_text(value)
    return "sha256:" + hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def read_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ReviewServiceError(f"Required file is missing: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ReviewServiceError(f"Invalid JSON in {path.name}: {exc}") from exc
    if not isinstance(payload, dict):
        raise ReviewServiceError(f"{path.name} must contain a JSON object.")
    return payload


def atomic_write_json(path: Path, payload: Any) -> None:
    """Atomically replace a JSON file after flushing it to disk."""

    path.parent.mkdir(parents=True, exist_ok=True)
    serialized = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    temporary_name: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="\n",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temporary_name = handle.name
            handle.write(serialized)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_name, path)
    finally:
        if temporary_name and os.path.exists(temporary_name):
            os.unlink(temporary_name)


def validate_review_request(payload: dict[str, Any]) -> dict[str, Any]:
    missing = sorted(REQUIRED_REQUEST_FIELDS - payload.keys())
    if missing:
        raise ReviewServiceError("review_request.json is missing fields: " + ", ".join(missing))
    if payload.get("schema_version") != SCHEMA_VERSION:
        raise ReviewServiceError(f"Unsupported schema_version: {payload.get('schema_version')!r}")
    for field in ("request_id", "stage", "title", "content_file", "created_at", "status"):
        if not str(payload.get(field, "")).strip():
            raise ReviewServiceError(f"review_request.{field} must not be empty.")
    content = payload.get("content")
    if not isinstance(content, str):
        raise ReviewServiceError("review_request.content must be text.")
    expected_hash = content_sha256(content)
    if payload.get("content_hash") != expected_hash:
        raise ReviewServiceError("review_request.content_hash does not match its normalized content.")
    if payload.get("status") != "pending":
        raise ReviewServiceError("Only a pending review request can accept a decision.")
    return payload


def create_app(project_dir: Path) -> Flask:
    project_dir = project_dir.resolve()
    review_dir = project_dir / "review"
    request_path = review_dir / "review_request.json"
    decision_path = review_dir / "review_decision.json"
    app = Flask(__name__, static_folder=str(STATIC_DIR), static_url_path="/static")
    app.config.update(PROJECT_DIR=str(project_dir), JSON_AS_ASCII=False)

    @app.after_request
    def disable_cache(response: Any) -> Any:
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        response.headers["Pragma"] = "no-cache"
        return response

    @app.errorhandler(ReviewServiceError)
    def handle_review_error(exc: ReviewServiceError) -> Any:
        return jsonify({"ok": False, "error": str(exc)}), 400

    @app.get("/")
    def index() -> Any:
        return send_from_directory(STATIC_DIR, "index.html")

    @app.get("/api/health")
    def health() -> Any:
        try:
            review_request = validate_review_request(read_json(request_path))
        except ReviewServiceError as exc:
            return jsonify({"ok": False, "status": "error", "error": str(exc)}), 503
        return jsonify(
            {
                "ok": True,
                "status": "ready",
                "pid": os.getpid(),
                "request_id": review_request["request_id"],
                "stage": review_request["stage"],
                "content_hash": review_request["content_hash"],
            }
        )

    @app.get("/api/review-request")
    def get_review_request() -> Any:
        return jsonify(validate_review_request(read_json(request_path)))

    @app.post("/api/review-decision")
    def submit_review_decision() -> Any:
        review_request = validate_review_request(read_json(request_path))
        payload = request.get_json(silent=False)
        if not isinstance(payload, dict):
            raise ReviewServiceError("The decision body must be a JSON object.")

        for field in ("request_id", "stage", "content_hash"):
            if payload.get(field) != review_request.get(field):
                raise ReviewServiceError(f"Decision {field} does not match the active review request.")
        decision = payload.get("decision")
        if decision not in ALLOWED_DECISIONS:
            raise ReviewServiceError(
                "decision must be one of: approved, revision_required, rejected."
            )
        comment = payload.get("comment", "")
        if not isinstance(comment, str):
            raise ReviewServiceError("comment must be text.")

        if decision_path.exists():
            existing = read_json(decision_path)
            if all(existing.get(key) == review_request.get(key) for key in ("request_id", "stage", "content_hash")):
                return jsonify({"ok": False, "error": "This request already has a confirmed decision."}), 409
            raise ReviewServiceError("A stale decision file is present; archive it before starting a new request.")

        result = {
            "schema_version": SCHEMA_VERSION,
            "request_id": review_request["request_id"],
            "stage": review_request["stage"],
            "content_hash": review_request["content_hash"],
            "decision": decision,
            "comment": comment,
            "status": "confirmed",
            "confirmed_at": utc_now(),
        }
        atomic_write_json(decision_path, result)
        return jsonify({"ok": True, "decision": result})

    return app


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-dir", type=Path, required=True)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, required=True)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    app = create_app(args.project_dir)
    app.run(host=args.host, port=args.port, threaded=True, use_reloader=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
