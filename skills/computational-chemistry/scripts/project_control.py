#!/usr/bin/env python3
"""Deterministic global controller for the computational chemistry skill.

This tool manages only project_control/, provenance/, and project_delivery/.
It never runs scientific software or changes a stage-owned file.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import shutil
import sys
import uuid
from collections.abc import Iterable
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from review_ui.stage_gate import execute_stage_review

SCHEMA_VERSION = 1
FALSE_EXECUTION_FLAGS = {
    "calculation_executed_by_skill": False,
    "postprocessing_executed_by_skill": False,
    "job_submitted_by_skill": False,
    "queue_queried_by_skill": False,
    "remote_result_retrieval": False,
    "background_monitoring": False,
}

GLOBAL_STATES = [
    "PROJECT_INITIALIZED",
    "PLANNING_IN_PROGRESS",
    "PLANNING_APPROVED",
    "SURFACE_DESIGN_IN_PROGRESS",
    "SURFACE_DESIGN_APPROVED",
    "INTERFACE_DESIGN_IN_PROGRESS",
    "INTERFACE_FILES_APPROVED",
    "WAITING_FOR_USER_CALCULATION",
    "USER_CALCULATION_RESULT_RECEIVED",
    "FORMAL_CALCULATION_FILES_IN_PROGRESS",
    "FORMAL_CALCULATION_FILES_APPROVED",
    "DATA_PROCESSING_IN_PROGRESS",
    "RESULT_ANALYSIS_IN_PROGRESS",
    "RESULTS_APPROVED",
    "MANUSCRIPT_GENERATION_IN_PROGRESS",
    "MANUSCRIPT_CONTENT_APPROVED",
    "DELIVERY_VALIDATION_IN_PROGRESS",
    "DELIVERY_ITEMS_MISSING",
    "DELIVERY_USER_REVIEW_REQUIRED",
    "DELIVERY_REVIEW_REJECTED",
    "DELIVERY_PACKAGE_READY",
    "PROJECT_ARCHIVED",
]

STATE_RANK = {state: index for index, state in enumerate(GLOBAL_STATES)}

LOCAL_STATUS_FILES = {
    "stage1": "planning/stage1_status.json",
    "surface": "surface_design/surface_status.json",
    "interface": "interface_design/interface_status.json",
    "geometry_result": "calculation_results/result_status.json",
    "formal": "formal_calculations/formal_status.json",
    "formal_result": "formal_calculations/formal_result_status.json",
    "analysis": "results_analysis/processing_status.json",
    "manuscript": "manuscript_generation/manuscript_status.json",
}

GATE_ARTIFACTS = {
    "stage1_approved": [
        "planning/stage1_plan_approved.json",
        "planning/stage1_plan_approved.md",
        "planning/stage1_approval_record.json",
    ],
    "surface_approved": [
        "surface_design/surface_design_approved.json",
        "surface_design/surface_design_approved.csv",
        "surface_design/surface_design_approved.md",
        "surface_design/surface_approval_record.json",
    ],
    "interface_approved": [
        "interface_design/interface_design_approved.json",
        "interface_design/optimization_parameters_approved.json",
        "interface_design/calculation_inputs_approved",
        "interface_design/hpc_scripts_approved",
        "interface_design/interface_design_approved.md",
        "interface_design/interface_file_approval_record.json",
    ],
    "geometry_accepted": [
        "calculation_results/result_status.json",
    ],
    "results_approved": [
        "results_analysis/processing_status.json",
    ],
    "manuscript_approved": [
        "manuscript_generation/method_statement_approved.md",
        "manuscript_generation/result_discussion_approved.md",
        "manuscript_generation/conclusion_approved.md",
        "manuscript_generation/software_citation_list_approved.md",
        "manuscript_generation/license_review_approved.md",
        "manuscript_generation/open_source_reproduction_note_approved.md",
        "manuscript_generation/manuscript_approval_record.json",
    ],
}

REGISTRY_FILES = {
    "MODEL": "model_registry.json",
    "CALC": "calculation_registry.json",
    "RESULT": "result_registry.json",
    "EVIDENCE": "evidence_registry.json",
    "CONCLUSION": "conclusion_registry.json",
}

DELIVERY_CATEGORIES = {
    "01_planning",
    "02_models",
    "03_calculation_inputs",
    "04_hpc_scripts",
    "05_user_results",
    "06_processed_data",
    "07_analysis",
    "08_manuscript",
    "09_open_source_reproduction",
    "10_provenance",
}

ERROR_ROUTES = {
    "FILE_ERROR": "supplement_or_repair_files",
    "SYNTAX_ERROR": "owning_input_generation_stage",
    "ENVIRONMENT_ERROR": "run_script_or_environment_guidance",
    "NUMERICAL_CONVERGENCE_ERROR": "owning_calculation_file_stage",
    "MODEL_ERROR": "surface_or_interface_redesign",
    "REFERENCE_SYSTEM_ERROR": "reference_system_redesign",
    "DATA_PROCESSING_ERROR": "stage_3_processing_step",
    "SCIENTIFIC_INTERPRETATION_ERROR": "stage_3_or_stage_4_conclusion_revision",
    "PROVENANCE_ERROR": "actual_input_output_or_version_completion",
}

ROUTES = [
    ("stage_5", "manuscript_approved", ["归档", "交付", "复现包", "文件清单", "archive", "delivery", "manifest"]),
    ("stage_4", "results_approved", ["计算方法", "结果讨论", "科学结论", "论文", "引用", "许可", "开源复现", "manuscript", "method section", "discussion"]),
    ("stage_3", "real_result_available", ["数据处理", "第4步", "单位", "对齐", "积分", "分析结果", "证据验证", "processed data", "interpret", "processing"]),
    ("stage_2_step_3", "geometry_accepted", ["pdos", "dos", "cohp", "qtaim", "bader", "电荷密度差", "结合能", "吸附能", "正式计算", "scf", "nscf", "formal calculation"]),
    ("geometry_result_return", "interface_approved", ["算完", "计算完成", "输出文件", "错误日志", "几何收敛", "优化结果", "重启", "calculation finished", "convergence", "restart"]),
    ("stage_2_step_2", "surface_approved", ["界面", "晶格匹配", "上下顺序", "几何优化文件", "interface", "lattice match", "optimization input"]),
    ("stage_2_step_1", "stage1_approved", ["表面", "晶面", "终止", "slab", "真空层", "缺陷", "掺杂", "官能化", "surface", "facet", "termination"]),
    ("stage_1", "project_initialized", ["研究目标", "科学问题", "方案设计", "证据链", "对照体系", "planning", "research goal", "evidence chain"]),
]

REQUIRED_REGISTRY_FIELDS = {
    "MODEL": ["model_version", "stage1_task_ids"],
    "CALC": ["model_ids", "stage1_task_ids", "planned_parameters"],
    "RESULT": ["calculation_ids", "data_quality", "comparability", "model_scope", "numerical_uncertainty", "interpretation_scope", "experimental_relevance"],
    "EVIDENCE": ["result_ids", "evidence_role", "validation_status"],
    "CONCLUSION": ["evidence_ids", "approved_strength", "scope", "limitations"],
}


class ControlError(RuntimeError):
    pass


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def json_dump(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2) + "\n"


def read_json(path: Path, required: bool = True) -> Any:
    if not path.exists():
        if required:
            raise ControlError(f"Missing required JSON file: {path}")
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ControlError(f"Cannot parse JSON file {path}: {exc}") from exc


def atomic_write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    temporary.write_text(content, encoding="utf-8", newline="\n")
    temporary.replace(path)


def write_json(path: Path, data: Any) -> None:
    atomic_write_text(path, json_dump(data))


def write_new_json(path: Path, data: Any) -> None:
    if path.exists():
        raise ControlError(f"Refusing to overwrite immutable file: {path}")
    write_json(path, data)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_directory(path: Path) -> str:
    digest = hashlib.sha256()
    for item in sorted((entry for entry in path.rglob("*") if entry.is_file()), key=lambda p: p.as_posix()):
        digest.update(item.relative_to(path).as_posix().encode("utf-8"))
        digest.update(bytes.fromhex(sha256_file(item)))
    return digest.hexdigest()


def file_record(path: Path, role: str | None = None, root: Path | None = None) -> dict[str, Any]:
    resolved = path.resolve()
    if not resolved.exists():
        raise ControlError(f"Source does not exist: {resolved}")
    record: dict[str, Any] = {
        "path": str(resolved),
        "type": "directory" if resolved.is_dir() else "file",
        "size": sum(p.stat().st_size for p in resolved.rglob("*") if p.is_file()) if resolved.is_dir() else resolved.stat().st_size,
        "sha256": sha256_directory(resolved) if resolved.is_dir() else sha256_file(resolved),
    }
    if root is not None:
        try:
            record["relative_path"] = resolved.relative_to(root.resolve()).as_posix()
        except ValueError:
            record["relative_path"] = None
    if role:
        record["role"] = role
    return record


def ensure_root(path: str) -> Path:
    root = Path(path).expanduser().resolve()
    if root == root.parent:
        raise ControlError("A filesystem root cannot be used as the project root")
    root.mkdir(parents=True, exist_ok=True)
    return root


def owned(root: Path, relative: str) -> Path:
    candidate = (root / relative).resolve()
    try:
        candidate.relative_to(root.resolve())
    except ValueError as exc:
        raise ControlError(f"Path escapes project root: {relative}") from exc
    return candidate


def next_version(directory: Path, stem: str, suffix: str = ".json") -> tuple[int, Path]:
    directory.mkdir(parents=True, exist_ok=True)
    pattern = re.compile(rf"^{re.escape(stem)}_v(\d{{3}}){re.escape(suffix)}$")
    versions = []
    for item in directory.iterdir():
        match = pattern.match(item.name)
        if match:
            versions.append(int(match.group(1)))
    version = max(versions, default=0) + 1
    return version, directory / f"{stem}_v{version:03d}{suffix}"


def stage_state_from_data(data: Any) -> str | None:
    if not isinstance(data, dict):
        return None
    for key in ("state", "status", "current_state", "workflow_state"):
        value = data.get(key)
        if isinstance(value, str):
            return value
    return None


def local_snapshot(root: Path) -> dict[str, Any]:
    snapshot: dict[str, Any] = {}
    for stage, relative in LOCAL_STATUS_FILES.items():
        path = owned(root, relative)
        if not path.exists():
            snapshot[stage] = {"exists": False, "path": str(path), "state": None}
            continue
        try:
            data = read_json(path)
            snapshot[stage] = {**file_record(path, "local_stage_status", root), "exists": True, "state": stage_state_from_data(data), "parse_ok": True}
        except ControlError as exc:
            snapshot[stage] = {"exists": True, "path": str(path), "state": None, "parse_ok": False, "error": str(exc)}
    return snapshot


def artifact_snapshot(root: Path, gate_name: str) -> list[dict[str, Any]]:
    records = []
    for relative in GATE_ARTIFACTS.get(gate_name, []):
        path = owned(root, relative)
        if path.exists():
            records.append(file_record(path, gate_name, root))
    return records


def gate_report(root: Path, gate: str, snapshot: dict[str, Any] | None = None) -> dict[str, Any]:
    snapshot = snapshot or local_snapshot(root)
    missing: list[str] = []
    detail: dict[str, Any] = {}
    if gate == "project_initialized":
        passed = owned(root, "project_control/project_manifest.json").is_file() and owned(root, "project_control/workflow_state.json").is_file()
        if not passed:
            missing.append("project_control initialization")
    elif gate == "stage1_approved":
        detail["local_state"] = snapshot["stage1"].get("state")
        if detail["local_state"] != "APPROVED":
            missing.append("planning/stage1_status.json: APPROVED")
        for relative in GATE_ARTIFACTS[gate]:
            if not owned(root, relative).exists():
                missing.append(relative)
        passed = not missing
    elif gate == "surface_approved":
        upstream = gate_report(root, "stage1_approved", snapshot)
        if not upstream["passed"]:
            missing.extend(upstream["missing"])
        detail["local_state"] = snapshot["surface"].get("state")
        if detail["local_state"] != "SURFACE_DESIGN_APPROVED":
            missing.append("surface_design/surface_status.json: SURFACE_DESIGN_APPROVED")
        for relative in GATE_ARTIFACTS[gate]:
            if not owned(root, relative).exists():
                missing.append(relative)
        passed = not missing
    elif gate == "interface_approved":
        upstream = gate_report(root, "surface_approved", snapshot)
        if not upstream["passed"]:
            missing.extend(upstream["missing"])
        detail["local_state"] = snapshot["interface"].get("state")
        if detail["local_state"] != "INTERFACE_FILES_APPROVED":
            missing.append("interface_design/interface_status.json: INTERFACE_FILES_APPROVED")
        for relative in GATE_ARTIFACTS[gate]:
            if not owned(root, relative).exists():
                missing.append(relative)
        passed = not missing
    elif gate == "geometry_accepted":
        detail["local_state"] = snapshot["geometry_result"].get("state")
        passed = detail["local_state"] == "OPTIMIZED_STRUCTURE_ACCEPTED"
        if not passed:
            missing.append("calculation_results/result_status.json: OPTIMIZED_STRUCTURE_ACCEPTED")
    elif gate == "real_result_available":
        states = {snapshot["geometry_result"].get("state"), snapshot["formal_result"].get("state"), snapshot["formal"].get("state")}
        waiting = {None, "WAITING_FOR_USER_CALCULATION_RESULT", "WAITING_FOR_FORMAL_CALCULATION_RESULT", "FORMAL_CALCULATION_FILES_APPROVED"}
        passed = any(state not in waiting for state in states)
        detail["observed_states"] = sorted(str(state) for state in states if state)
        if not passed:
            missing.append("real returned calculation result or accepted user-processed data")
    elif gate == "formal_files_approved":
        allowed = {"FORMAL_CALCULATION_FILES_APPROVED", "WAITING_FOR_FORMAL_CALCULATION_RESULT", "FORMAL_RESULT_RECEIVED", "FORMAL_RESULT_ACCEPTED", "FORMAL_EVIDENCE_NODE_COMPLETED", "FORMAL_CALCULATION_WORKFLOW_COMPLETED"}
        states = {snapshot["formal"].get("state"), snapshot["formal_result"].get("state")}
        passed = bool(states & allowed)
        detail["observed_states"] = sorted(str(state) for state in states if state)
        if not passed:
            missing.append("approved formal calculation batch")
    elif gate == "results_approved":
        detail["local_state"] = snapshot["analysis"].get("state")
        passed = detail["local_state"] == "RESULTS_APPROVED"
        if not passed:
            missing.append("results_analysis/processing_status.json: RESULTS_APPROVED")
    elif gate == "manuscript_approved":
        upstream = gate_report(root, "results_approved", snapshot)
        if not upstream["passed"]:
            missing.extend(upstream["missing"])
        detail["local_state"] = snapshot["manuscript"].get("state")
        if detail["local_state"] != "MANUSCRIPT_CONTENT_APPROVED":
            missing.append("manuscript_generation/manuscript_status.json: MANUSCRIPT_CONTENT_APPROVED")
        for relative in GATE_ARTIFACTS[gate]:
            if not owned(root, relative).exists():
                missing.append(relative)
        passed = not missing
    elif gate == "delivery_ready":
        report = read_json(owned(root, "project_delivery/delivery_status.json"), required=False) or {}
        manifest = read_json(owned(root, "project_control/project_manifest.json"), required=False) or {}
        passed = report.get("state") == "DELIVERY_PACKAGE_READY" and not report.get("blocking_missing_items") and report.get("project_version") == manifest.get("project_version")
        if not passed:
            missing.append("current-project-version user-reviewed delivery package with no blocking missing items")
    else:
        raise ControlError(f"Unknown gate: {gate}")
    gate_owner = {
        "stage1_approved": "stage1",
        "surface_approved": "surface",
        "interface_approved": "interface",
        "geometry_accepted": "geometry_result",
        "results_approved": "analysis",
        "manuscript_approved": "manuscript",
    }
    owner = gate_owner.get(gate)
    workflow = read_json(owned(root, "project_control/workflow_state.json"), required=False) or {}
    if owner:
        local = snapshot.get(owner, {})
        is_superseded = any(item.get("stage") == owner and item.get("state") == local.get("state") and item.get("sha256") == local.get("sha256") for item in workflow.get("superseded_local_states", []))
        if is_superseded:
            passed = False
            missing.append(f"current non-superseded {owner} approval for this project version")
            detail["superseded_local_approval"] = True
    return {"gate": gate, "passed": bool(passed), "missing": sorted(set(missing)), "detail": detail}


def state_gate(state: str) -> str:
    mapping = {
        "PROJECT_INITIALIZED": "project_initialized",
        "PLANNING_IN_PROGRESS": "project_initialized",
        "PLANNING_APPROVED": "stage1_approved",
        "SURFACE_DESIGN_IN_PROGRESS": "stage1_approved",
        "SURFACE_DESIGN_APPROVED": "surface_approved",
        "INTERFACE_DESIGN_IN_PROGRESS": "surface_approved",
        "INTERFACE_FILES_APPROVED": "interface_approved",
        "WAITING_FOR_USER_CALCULATION": "interface_approved",
        "USER_CALCULATION_RESULT_RECEIVED": "real_result_available",
        "FORMAL_CALCULATION_FILES_IN_PROGRESS": "geometry_accepted",
        "FORMAL_CALCULATION_FILES_APPROVED": "formal_files_approved",
        "DATA_PROCESSING_IN_PROGRESS": "real_result_available",
        "RESULT_ANALYSIS_IN_PROGRESS": "real_result_available",
        "RESULTS_APPROVED": "results_approved",
        "MANUSCRIPT_GENERATION_IN_PROGRESS": "results_approved",
        "MANUSCRIPT_CONTENT_APPROVED": "manuscript_approved",
        "DELIVERY_VALIDATION_IN_PROGRESS": "manuscript_approved",
        "DELIVERY_ITEMS_MISSING": "manuscript_approved",
        "DELIVERY_USER_REVIEW_REQUIRED": "manuscript_approved",
        "DELIVERY_REVIEW_REJECTED": "manuscript_approved",
        "DELIVERY_PACKAGE_READY": "delivery_ready",
        "PROJECT_ARCHIVED": "delivery_ready",
    }
    return mapping[state]


def default_dependencies() -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "dependencies": [
            {"id": "DEP-SURFACE", "route": "stage_2_step_1", "gate": "stage1_approved", "description": "surface design depends on the approved stage-1 plan"},
            {"id": "DEP-INTERFACE", "route": "stage_2_step_2", "gate": "surface_approved", "description": "interface design depends on approved surfaces"},
            {"id": "DEP-GEOMETRY-RESULT", "route": "geometry_result_return", "gate": "interface_approved", "description": "geometry execution/return depends on approved interface files"},
            {"id": "DEP-FORMAL", "route": "stage_2_step_3", "gate": "geometry_accepted", "description": "formal calculations depend on an accepted optimized structure"},
            {"id": "DEP-ANALYSIS", "route": "stage_3", "gate": "real_result_available", "description": "data analysis depends on real returned results or user-processed data"},
            {"id": "DEP-MANUSCRIPT", "route": "stage_4", "gate": "results_approved", "description": "manuscript content depends on approved stage-3 results"},
            {"id": "DEP-DELIVERY", "route": "stage_5", "gate": "manuscript_approved", "description": "delivery depends on approved manuscript content and project files"},
        ],
        "supplemental_return": {"from": "stage_3", "to": "stage_2_step_3", "rerun_all_upstream": False},
    }


def create_registry(path: Path, kind: str) -> None:
    if not path.exists():
        write_new_json(path, {"schema_version": SCHEMA_VERSION, "kind": kind, "entries": [], "retired_ids": []})


def render_dashboard(root: Path, audit_data: dict[str, Any] | None = None) -> Path:
    control = owned(root, "project_control")
    manifest = read_json(control / "project_manifest.json", required=False) or {}
    workflow = read_json(control / "workflow_state.json", required=False) or {}
    resume = read_json(control / "resume_context.json", required=False) or {}
    approvals = read_json(control / "user_approvals.json", required=False) or {"entries": []}
    trace = read_json(owned(root, "provenance/conclusion_traceability.json"), required=False) or {"entries": []}
    delivery = read_json(owned(root, "project_delivery/delivery_status.json"), required=False) or {}
    error_files = sorted((control / "error_reports").glob("error_v*.json")) if (control / "error_reports").exists() else []
    latest_error = read_json(error_files[-1]) if error_files else None
    stage_links = []
    for label, relative in [
        ("阶段一审查", "planning/stage1_review.html"),
        ("表面审查", "surface_design/surface_review.html"),
        ("界面审查", "interface_design/interface_review.html"),
        ("正式计算审查", "formal_calculations/formal_review.html"),
        ("结果审查", "results_analysis/result_review.html"),
        ("论文审查", "manuscript_generation/manuscript_review.html"),
    ]:
        target = owned(root, relative)
        if target.exists():
            stage_links.append({"label": label, "href": "../" + Path(relative).as_posix()})
    if audit_data is None:
        audit_files = sorted((control / "audits").glob("global_audit_v*.json")) if (control / "audits").exists() else []
        audit_data = read_json(audit_files[-1]) if audit_files else {}
    data = {
        "project": manifest,
        "workflow": workflow,
        "resume": resume,
        "latest_error": latest_error,
        "latest_approval": (approvals.get("entries") or [None])[-1],
        "traceability": trace.get("summary", {}),
        "delivery": delivery,
        "audit": audit_data,
        "stage_links": stage_links,
    }
    template = Path(__file__).resolve().parent.parent / "assets" / "project_dashboard.html"
    if not template.is_file():
        raise ControlError(f"Dashboard template is missing: {template}")
    payload = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
    rendered = template.read_text(encoding="utf-8").replace("__PROJECT_DASHBOARD_JSON__", payload)
    target = control / "project_dashboard.html"
    atomic_write_text(target, rendered)
    return target


def command_init(root: Path, args: argparse.Namespace) -> dict[str, Any]:
    control = owned(root, "project_control")
    provenance = owned(root, "provenance")
    control.mkdir(parents=True, exist_ok=True)
    provenance.mkdir(parents=True, exist_ok=True)
    manifest_path = control / "project_manifest.json"
    if manifest_path.exists():
        raise ControlError("project_control already exists; use audit/resume instead of reinitializing")
    temporary_id = "PROJECT-" + datetime.now(timezone.utc).strftime("%Y%m%d") + "-" + uuid.uuid4().hex[:8].upper()
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "project_id": temporary_id,
        "project_version": 1,
        "project_name": args.project_name,
        "research_object": args.research_object,
        "material_system": args.material_system,
        "research_goal": args.research_goal,
        "specified_software": args.software,
        "software_version": args.software_version,
        "compute_platform": args.compute_platform,
        "created_at": utc_now(),
        "current_stage": "global_control",
        "current_task": "project initialization",
        "current_model_id": None,
        "current_parameter_version": None,
        "current_result_id": None,
        "last_user_action": None,
    }
    state = {
        "schema_version": SCHEMA_VERSION,
        "project_id": temporary_id,
        "revision": 1,
        "state": "PROJECT_INITIALIZED",
        "last_transition": {"from": None, "to": "PROJECT_INITIALIZED", "actor": "skill", "at": utc_now()},
        "local_state_snapshot": local_snapshot(root),
        "locked_sources": [],
        **FALSE_EXECUTION_FLAGS,
    }
    resume = {
        "schema_version": SCHEMA_VERSION,
        "project_id": temporary_id,
        "source_state_revision": 1,
        "current_stage": "global_control",
        "current_task": "project initialization",
        "current_model_version": None,
        "current_input_version": None,
        "current_result_version": None,
        "completed_steps": ["project control initialized"],
        "incomplete_steps": ["define or recover the current scientific stage"],
        "last_decision": "PROJECT_INITIALIZED",
        "allowed_next_operations": ["stage_1 planning", "adopt an explicitly verified existing local stage state"],
        "updated_at": utc_now(),
    }
    write_new_json(manifest_path, manifest)
    write_new_json(control / "workflow_state.json", state)
    write_new_json(control / "stage_dependencies.json", default_dependencies())
    write_new_json(control / "decision_log.json", {"schema_version": SCHEMA_VERSION, "entries": [state["last_transition"]]})
    write_new_json(control / "user_approvals.json", {"schema_version": SCHEMA_VERSION, "entries": []})
    write_new_json(control / "resume_context.json", resume)
    write_new_json(control / "citation_registry.json", {"schema_version": SCHEMA_VERSION, "entries": []})
    atomic_write_text(control / "next_user_action.md", "# 下一步操作\n\n请确认或恢复当前科学工作流阶段。\n")
    atomic_write_text(control / "required_return_files.md", "# 需要回传的文件\n\n当前没有指定必须回传的文件。\n")
    for kind, name in REGISTRY_FILES.items():
        create_registry(provenance / name, kind)
    write_new_json(provenance / "conclusion_traceability.json", {"schema_version": SCHEMA_VERSION, "entries": [], "summary": {"complete": 0, "incomplete": 0}})
    dashboard = render_dashboard(root)
    return {"status": "initialized", "project_id": temporary_id, "state": "PROJECT_INITIALIZED", "dashboard": str(dashboard), **FALSE_EXECUTION_FLAGS}


def audit_locked_sources(root: Path, locked: Iterable[dict[str, Any]], superseded: Iterable[dict[str, Any]] = ()) -> list[dict[str, Any]]:
    conflicts: list[dict[str, Any]] = []
    inactive = {(item.get("path"), item.get("sha256")) for item in superseded}
    for expected in locked:
        path_text = expected.get("path")
        if (path_text, expected.get("sha256")) in inactive:
            continue
        if not path_text:
            conflicts.append({"type": "INVALID_LOCK_RECORD", "record": expected})
            continue
        path = Path(path_text)
        if not path.exists():
            conflicts.append({"type": "LOCKED_SOURCE_MISSING", "path": path_text, "expected_sha256": expected.get("sha256")})
            continue
        actual = sha256_directory(path) if path.is_dir() else sha256_file(path)
        if actual != expected.get("sha256"):
            conflicts.append({"type": "LOCKED_SOURCE_CHANGED", "path": path_text, "expected_sha256": expected.get("sha256"), "actual_sha256": actual})
    return conflicts


def minimum_global_for_local(stage: str, state: str | None, exists: bool) -> str | None:
    if not exists or not state:
        return None
    if stage == "stage1":
        return "PLANNING_APPROVED" if state == "APPROVED" else "PLANNING_IN_PROGRESS"
    if stage == "surface":
        return "SURFACE_DESIGN_APPROVED" if state == "SURFACE_DESIGN_APPROVED" else "SURFACE_DESIGN_IN_PROGRESS"
    if stage == "interface":
        return "INTERFACE_FILES_APPROVED" if state == "INTERFACE_FILES_APPROVED" else "INTERFACE_DESIGN_IN_PROGRESS"
    if stage == "geometry_result":
        if state == "WAITING_FOR_USER_CALCULATION_RESULT":
            return "WAITING_FOR_USER_CALCULATION"
        if state == "OPTIMIZED_STRUCTURE_ACCEPTED":
            return "FORMAL_CALCULATION_FILES_IN_PROGRESS"
        return "USER_CALCULATION_RESULT_RECEIVED"
    if stage in {"formal", "formal_result"}:
        approved_or_later = {"FORMAL_CALCULATION_FILES_APPROVED", "WAITING_FOR_FORMAL_CALCULATION_RESULT", "FORMAL_RESULT_RECEIVED", "FORMAL_RESULT_ACCEPTED", "FORMAL_EVIDENCE_NODE_COMPLETED", "FORMAL_CALCULATION_WORKFLOW_COMPLETED"}
        return "FORMAL_CALCULATION_FILES_APPROVED" if state in approved_or_later else "FORMAL_CALCULATION_FILES_IN_PROGRESS"
    if stage == "analysis":
        if state == "RESULTS_APPROVED":
            return "RESULTS_APPROVED"
        analysis_states = {"RESULT_ANALYSIS_COMPLETED", "EVIDENCE_CHAIN_VALIDATED", "WAITING_FOR_RESULT_APPROVAL"}
        return "RESULT_ANALYSIS_IN_PROGRESS" if state in analysis_states else "DATA_PROCESSING_IN_PROGRESS"
    if stage == "manuscript":
        return "MANUSCRIPT_CONTENT_APPROVED" if state == "MANUSCRIPT_CONTENT_APPROVED" else "MANUSCRIPT_GENERATION_IN_PROGRESS"
    return None


def detect_local_ahead(global_state: str, snapshot: dict[str, Any], superseded: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    conflicts = []
    superseded = superseded or []
    current_rank = STATE_RANK.get(global_state, -1)
    for stage, record in snapshot.items():
        local_state = record.get("state")
        minimum_global = minimum_global_for_local(stage, local_state, bool(record.get("exists")))
        explicitly_superseded = any(item.get("stage") == stage and item.get("state") == local_state and item.get("sha256") == record.get("sha256") for item in superseded)
        if minimum_global and current_rank < STATE_RANK[minimum_global] and not explicitly_superseded:
            conflicts.append({"type": "LOCAL_STATE_AHEAD_OF_GLOBAL", "stage": stage, "local_state": local_state, "global_state": global_state, "minimum_global_state": minimum_global})
    return conflicts


def command_audit(root: Path, write_report: bool = True) -> dict[str, Any]:
    control = owned(root, "project_control")
    manifest = read_json(control / "project_manifest.json")
    workflow = read_json(control / "workflow_state.json")
    snapshot = local_snapshot(root)
    conflicts: list[dict[str, Any]] = []
    auxiliary_paths = [
        control / "stage_dependencies.json",
        control / "decision_log.json",
        control / "user_approvals.json",
        control / "resume_context.json",
        control / "citation_registry.json",
        owned(root, "provenance/conclusion_traceability.json"),
    ] + [owned(root, f"provenance/{name}") for name in REGISTRY_FILES.values()]
    parsed_auxiliary: dict[str, Any] = {}
    for path in auxiliary_paths:
        if not path.is_file():
            conflicts.append({"type": "GLOBAL_CONTROL_FILE_MISSING", "path": str(path)})
            continue
        try:
            parsed_auxiliary[str(path)] = read_json(path)
        except ControlError as exc:
            conflicts.append({"type": "GLOBAL_CONTROL_JSON_ERROR", "path": str(path), "detail": str(exc)})
    state = workflow.get("state")
    if state not in GLOBAL_STATES:
        conflicts.append({"type": "INVALID_GLOBAL_STATE", "value": state})
    if manifest.get("project_id") != workflow.get("project_id"):
        conflicts.append({"type": "PROJECT_ID_MISMATCH", "manifest": manifest.get("project_id"), "workflow": workflow.get("project_id")})
    for flag, expected in FALSE_EXECUTION_FLAGS.items():
        if workflow.get(flag) is not expected:
            conflicts.append({"type": "FORBIDDEN_EXECUTION_FLAG", "field": flag, "value": workflow.get(flag)})
    seen_versions: set[tuple[str, int]] = set()
    id_kinds: dict[str, str] = {}
    for kind, name in REGISTRY_FILES.items():
        registry = parsed_auxiliary.get(str(owned(root, f"provenance/{name}")))
        if not isinstance(registry, dict):
            continue
        for entry in registry.get("entries", []):
            if not isinstance(entry, dict):
                conflicts.append({"type": "INVALID_REGISTRY_ENTRY", "registry": name})
                continue
            entry_id = entry.get("id")
            version = int(entry.get("version", 0)) if str(entry.get("version", "")).isdigit() else 0
            if not isinstance(entry_id, str) or not entry_id.startswith(f"{kind}-"):
                conflicts.append({"type": "REGISTRY_ID_KIND_MISMATCH", "registry": name, "id": entry_id, "kind": kind})
                continue
            if entry_id in id_kinds and id_kinds[entry_id] != kind:
                conflicts.append({"type": "PROVENANCE_ID_REUSED_ACROSS_KINDS", "id": entry_id, "kinds": [id_kinds[entry_id], kind]})
            id_kinds[entry_id] = kind
            key = (entry_id, version)
            if key in seen_versions:
                conflicts.append({"type": "DUPLICATE_PROVENANCE_VERSION", "id": entry_id, "version": version})
            seen_versions.add(key)
    for field, kind in (("current_model_id", "MODEL"), ("current_result_id", "RESULT")):
        value = manifest.get(field)
        if value and id_kinds.get(value) != kind:
            conflicts.append({"type": "MANIFEST_PROVENANCE_ID_NOT_REGISTERED", "field": field, "value": value, "expected_kind": kind})
    if state in GLOBAL_STATES:
        gate = gate_report(root, state_gate(state), snapshot)
        if not gate["passed"]:
            conflicts.append({"type": "GLOBAL_STATE_GATE_NOT_SATISFIED", "state": state, "gate": gate})
        conflicts.extend(detect_local_ahead(state, snapshot, workflow.get("superseded_local_states")))
    conflicts.extend(audit_locked_sources(root, workflow.get("locked_sources", []), workflow.get("superseded_local_states", [])))
    for name, record in snapshot.items():
        if record.get("exists") and not record.get("parse_ok", True):
            conflicts.append({"type": "LOCAL_STATUS_PARSE_ERROR", "stage": name, "detail": record})
        elif record.get("exists") and not record.get("state"):
            conflicts.append({"type": "LOCAL_STATUS_MISSING_STATE_FIELD", "stage": name, "path": record.get("path")})
    result = {
        "schema_version": SCHEMA_VERSION,
        "project_id": manifest.get("project_id"),
        "audited_at": utc_now(),
        "global_state": state,
        "local_state_snapshot": snapshot,
        "conflicts": conflicts,
        "audit_passed": not conflicts,
        **FALSE_EXECUTION_FLAGS,
    }
    if write_report:
        audit_dir = control / "audits"
        version, path = next_version(audit_dir, "global_audit")
        result["audit_version"] = version
        write_new_json(path, result)
        if conflicts:
            conflict_version, conflict_path = next_version(control / "state_conflicts", "state_conflict")
            conflict_report = {**result, "conflict_version": conflict_version, "resolution_policy": "Do not overwrite by timestamp; reconcile through verified local gates and an explicit global transition."}
            write_new_json(conflict_path, conflict_report)
            result["conflict_report"] = str(conflict_path)
        render_dashboard(root, result)
    return result


def transition_locked_sources(root: Path, state: str) -> list[dict[str, Any]]:
    gates_for_state = {
        "PLANNING_APPROVED": ["stage1_approved"],
        "SURFACE_DESIGN_APPROVED": ["stage1_approved", "surface_approved"],
        "INTERFACE_FILES_APPROVED": ["stage1_approved", "surface_approved", "interface_approved"],
        "WAITING_FOR_USER_CALCULATION": ["stage1_approved", "surface_approved", "interface_approved"],
        "FORMAL_CALCULATION_FILES_IN_PROGRESS": ["stage1_approved", "geometry_accepted"],
        "RESULTS_APPROVED": ["stage1_approved", "results_approved"],
        "MANUSCRIPT_CONTENT_APPROVED": ["stage1_approved", "results_approved", "manuscript_approved"],
        "DELIVERY_VALIDATION_IN_PROGRESS": ["stage1_approved", "surface_approved", "interface_approved", "geometry_accepted", "results_approved", "manuscript_approved"],
    }
    records: dict[str, dict[str, Any]] = {}
    gate_owner = {
        "stage1_approved": "stage1",
        "surface_approved": "surface",
        "interface_approved": "interface",
        "geometry_accepted": "geometry_result",
        "results_approved": "analysis",
        "manuscript_approved": "manuscript",
    }
    for gate in gates_for_state.get(state, []):
        if not gate_report(root, gate)["passed"]:
            continue
        for record in artifact_snapshot(root, gate):
            records[record["path"]] = record
        owner = gate_owner.get(gate)
        if owner:
            status_path = owned(root, LOCAL_STATUS_FILES[owner])
            if status_path.exists():
                record = file_record(status_path, f"{gate}_status", root)
                records[record["path"]] = record
    return [records[key] for key in sorted(records)]


def append_entry(path: Path, entry: dict[str, Any]) -> None:
    data = read_json(path)
    if not isinstance(data.get("entries"), list):
        raise ControlError(f"Invalid append-only file: {path}")
    data["entries"].append(entry)
    write_json(path, data)


def command_transition(root: Path, args: argparse.Namespace) -> dict[str, Any]:
    target = args.to_state
    if target not in GLOBAL_STATES:
        raise ControlError(f"Unsupported global state: {target}")
    control = owned(root, "project_control")
    workflow_path = control / "workflow_state.json"
    workflow = read_json(workflow_path)
    current = workflow.get("state")
    if current == "PROJECT_ARCHIVED" and target != "PROJECT_ARCHIVED" and not getattr(args, "allow_reopen", False):
        raise ControlError("An archived project can change state only through reopen")
    gate = gate_report(root, state_gate(target))
    if not gate["passed"]:
        raise ControlError(f"Cannot transition to {target}; unmet gate: {', '.join(gate['missing'])}")
    if target in {"PLANNING_APPROVED", "SURFACE_DESIGN_APPROVED", "INTERFACE_FILES_APPROVED", "RESULTS_APPROVED", "MANUSCRIPT_CONTENT_APPROVED", "DELIVERY_PACKAGE_READY", "PROJECT_ARCHIVED"} and not args.user_confirmed:
        raise ControlError(f"{target} requires --user-confirmed")
    if target == "PROJECT_ARCHIVED" and not (args.confirmation_note or "").strip():
        raise ControlError("PROJECT_ARCHIVED requires --confirmation-note")
    history_dir = control / "state_history"
    version, history_path = next_version(history_dir, "workflow")
    write_new_json(history_path, {**workflow, "history_version": version, "captured_at": utc_now()})
    transition = {"from": current, "to": target, "actor": args.actor, "at": utc_now(), "user_confirmed": bool(args.user_confirmed), "confirmation_note": args.confirmation_note, "gate": gate}
    workflow["revision"] = int(workflow.get("revision", 0)) + 1
    workflow["state"] = target
    workflow["last_transition"] = transition
    current_snapshot = local_snapshot(root)
    workflow["local_state_snapshot"] = current_snapshot
    if current in STATE_RANK and STATE_RANK[target] < STATE_RANK[current]:
        superseded = workflow.setdefault("superseded_local_states", [])
        known = {(item.get("stage"), item.get("sha256")) for item in superseded}
        for stage, record in current_snapshot.items():
            minimum_global = minimum_global_for_local(stage, record.get("state"), bool(record.get("exists")))
            is_ahead = bool(minimum_global and STATE_RANK[minimum_global] > STATE_RANK[target])
            if is_ahead and record.get("exists") and record.get("state") and record.get("sha256") and (stage, record.get("sha256")) not in known:
                superseded.append({"stage": stage, "state": record.get("state"), "sha256": record.get("sha256"), "path": record.get("path"), "superseded_by_global_revision": workflow["revision"], "reason": args.confirmation_note or args.task})
    existing_locks = {(item.get("path"), item.get("sha256")): item for item in workflow.get("locked_sources", []) if item.get("path") and item.get("sha256")}
    for record in transition_locked_sources(root, target):
        existing_locks.setdefault((record["path"], record["sha256"]), record)
    workflow["locked_sources"] = [existing_locks[key] for key in sorted(existing_locks)]
    workflow.update(FALSE_EXECUTION_FLAGS)
    write_json(workflow_path, workflow)
    manifest = read_json(control / "project_manifest.json")
    manifest["current_stage"] = target
    manifest["current_task"] = args.task or target.lower()
    if args.user_confirmed:
        manifest["last_user_action"] = args.confirmation_note or target
    write_json(control / "project_manifest.json", manifest)
    append_entry(control / "decision_log.json", {"decision_id": f"DECISION-{workflow['revision']:04d}", **transition})
    if args.user_confirmed:
        approvals = read_json(control / "user_approvals.json")
        approval_id = f"APPROVAL-{len(approvals['entries']) + 1:04d}"
        append_entry(control / "user_approvals.json", {"approval_id": approval_id, "level": "LOCKED_AFTER_APPROVAL", "subject": target, "subject_version": workflow["revision"], "actor": args.actor, "timestamp": transition["at"], "confirmation_text": args.confirmation_note, "source_files": transition_locked_sources(root, target)})
    render_dashboard(root)
    return {"status": "transitioned", "from": current, "to": target, "revision": workflow["revision"], "gate": gate, **FALSE_EXECUTION_FLAGS}


def classify_request(text: str) -> tuple[str, str, list[str]]:
    lowered = text.lower()
    best: tuple[int, str, str, list[str]] | None = None
    for route, gate, keywords in ROUTES:
        hits = [keyword for keyword in keywords if keyword.lower() in lowered]
        candidate = (len(hits), route, gate, hits)
        if hits and (best is None or candidate[0] > best[0]):
            best = candidate
    if best:
        return best[1], best[2], best[3]
    return "stage_1", "project_initialized", []


def command_route(root: Path, args: argparse.Namespace) -> dict[str, Any]:
    audit = command_audit(root, write_report=True)
    route, gate, hits = classify_request(args.request)
    report = gate_report(root, gate)
    closest = route if report["passed"] else next((dep["route"] for dep in default_dependencies()["dependencies"] if dep["gate"] == gate), "stage_1")
    if not report["passed"]:
        gate_to_route = {
            "stage1_approved": "stage_1",
            "surface_approved": "stage_2_step_1",
            "interface_approved": "stage_2_step_2",
            "geometry_accepted": "geometry_result_return",
            "real_result_available": "stage_2_step_3_result_return",
            "results_approved": "stage_3",
            "manuscript_approved": "stage_4",
        }
        closest = gate_to_route.get(gate, closest)
    if not audit["audit_passed"]:
        closest = "global_state_reconciliation"
    allowed = report["passed"] and audit["audit_passed"]
    result = {
        "request": args.request,
        "classified_route": route,
        "matched_terms": hits,
        "global_audit_passed": audit["audit_passed"],
        "state_conflicts": audit["conflicts"],
        "dependency": report,
        "allowed": allowed,
        "next_executable_route": closest,
        "instruction": "Route to the requested stage." if allowed else ("Resolve the global/local state or locked-source conflict without overwriting history." if not audit["audit_passed"] else "Complete only the nearest missing dependency; do not restart already approved stages."),
    }
    return result


def parse_json_argument(value: str) -> Any:
    candidate = Path(value)
    if candidate.is_file():
        return read_json(candidate)
    try:
        return json.loads(value)
    except json.JSONDecodeError as exc:
        raise ControlError("Expected a JSON file path or JSON value") from exc


def normalize_file_records(values: Any, root: Path, role: str) -> list[dict[str, Any]]:
    if not values:
        return []
    if not isinstance(values, list):
        raise ControlError(f"{role} must be a list")
    output = []
    for value in values:
        if isinstance(value, str):
            output.append(file_record(Path(value), role, root))
        elif isinstance(value, dict) and value.get("path"):
            record = file_record(Path(value["path"]), value.get("role", role), root)
            for key in ("original", "approved", "notes"):
                if key in value:
                    record[key] = value[key]
            output.append(record)
        else:
            raise ControlError(f"Invalid file record in {role}")
    return output


def load_registries(root: Path) -> dict[str, dict[str, Any]]:
    provenance = owned(root, "provenance")
    return {kind: read_json(provenance / name) for kind, name in REGISTRY_FILES.items()}


def latest_entries(registry: dict[str, Any]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for entry in registry.get("entries", []):
        entry_id = entry.get("id")
        if entry_id and (entry_id not in result or int(entry.get("version", 0)) > int(result[entry_id].get("version", 0))):
            result[entry_id] = entry
    return result


def allocated_ids(registries: dict[str, dict[str, Any]]) -> set[str]:
    ids: set[str] = set()
    for registry in registries.values():
        ids.update(entry.get("id") for entry in registry.get("entries", []) if entry.get("id"))
        ids.update(registry.get("retired_ids", []))
    return ids


def sanitize_subtype(value: str) -> str:
    subtype = re.sub(r"[^A-Z0-9]+", "-", value.upper()).strip("-")
    if not subtype:
        raise ControlError("Subtype must contain an ASCII letter or digit")
    return subtype[:32]


def allocate_id(kind: str, subtype: str, ids: set[str]) -> str:
    prefix = f"{kind}-{subtype}-"
    numbers = []
    for item in ids:
        if item.startswith(prefix):
            tail = item[len(prefix):]
            if tail.isdigit():
                numbers.append(int(tail))
    candidate = f"{prefix}{max(numbers, default=0) + 1:03d}"
    if candidate in ids:
        raise ControlError("ID allocation collision")
    return candidate


def command_register(root: Path, args: argparse.Namespace) -> dict[str, Any]:
    audit = command_audit(root, write_report=True)
    if not audit["audit_passed"]:
        raise ControlError("Cannot register provenance while the global/local state or a locked source is in conflict")
    kind = args.kind
    record = parse_json_argument(args.record)
    if not isinstance(record, dict):
        raise ControlError("Registry record must be a JSON object")
    missing = [field for field in REQUIRED_REGISTRY_FIELDS[kind] if field not in record]
    if missing:
        raise ControlError(f"Missing required {kind} fields: {', '.join(missing)}")
    source_files = normalize_file_records(record.pop("source_files", []), root, "source_file")
    if kind == "RESULT":
        result_files = normalize_file_records(record.pop("real_result_files", []), root, "real_result")
        processed = normalize_file_records(record.pop("processed_data_files", []), root, "processed_data")
        if not result_files and not record.get("detailed_user_description"):
            raise ControlError("RESULT requires real_result_files or a detailed_user_description")
        record["real_result_files"] = result_files
        record["processed_data_files"] = processed
    if kind == "EVIDENCE":
        record["processed_data_files"] = normalize_file_records(record.pop("processed_data_files", []), root, "processed_data")
    if kind == "CALC":
        record["actual_input_files"] = normalize_file_records(record.pop("actual_input_files", []), root, "actual_input")
        record["actual_output_files"] = normalize_file_records(record.pop("actual_output_files", []), root, "actual_output")
        record.setdefault("actual_parameters", None)
        record.setdefault("parameter_differences", [])
        record.setdefault("difference_classification", None)
        record.setdefault("difference_impact", None)
        record.setdefault("user_confirmation", None)
    registries = load_registries(root)
    subtype = sanitize_subtype(args.subtype)
    entry_id = allocate_id(kind, subtype, allocated_ids(registries))
    entry = {
        "id": entry_id,
        "kind": kind,
        "subtype": subtype,
        "version": 1,
        "status": args.status,
        "created_at": utc_now(),
        "source_files": source_files,
        "notes": args.notes,
        **record,
    }
    registry_path = owned(root, f"provenance/{REGISTRY_FILES[kind]}")
    append_entry(registry_path, entry)
    return {"status": "registered", "id": entry_id, "version": 1, "registry": str(registry_path)}


RUNTIME_KEYS = {"nodes", "node_count", "cores", "core_count", "queue", "partition", "walltime", "working_directory", "output_path", "scheduler"}
STABILITY_KEYS = {"mixing", "mixing_beta", "max_scf", "electron_maxstep", "max_iterations", "ionic_step", "trust_radius", "optimizer", "restart", "diagonalization"}
SCIENTIFIC_KEYS = {"functional", "xc", "pseudopotential", "potential", "basis", "basis_set", "dispersion", "hubbard_u", "k_points", "kpoints", "spin", "magnetization", "cutoff", "ecutwfc", "ecutrho", "smearing", "occupations"}
MODEL_KEYS = {"facet", "termination", "defect", "dopant", "doping", "functionalization", "supercell", "interface", "reference_system", "vacuum", "lattice", "model", "structure", "adsorption_site"}
CLASS_RANK = {"RUNTIME_ONLY": 0, "NUMERICAL_STABILITY": 1, "SCIENTIFICALLY_RELEVANT": 2, "MODEL_CHANGING": 3}


def flatten(data: Any, prefix: str = "") -> dict[str, Any]:
    if isinstance(data, dict):
        result: dict[str, Any] = {}
        for key in sorted(data):
            path = f"{prefix}.{key}" if prefix else str(key)
            result.update(flatten(data[key], path))
        return result
    if isinstance(data, list):
        return {prefix: data}
    return {prefix: data}


def classify_parameter(path: str) -> str:
    tokens = {token.lower() for token in re.split(r"[^A-Za-z0-9_]+", path)}
    if tokens & MODEL_KEYS:
        return "MODEL_CHANGING"
    if tokens & SCIENTIFIC_KEYS:
        return "SCIENTIFICALLY_RELEVANT"
    if tokens & STABILITY_KEYS:
        return "NUMERICAL_STABILITY"
    if tokens & RUNTIME_KEYS:
        return "RUNTIME_ONLY"
    return "SCIENTIFICALLY_RELEVANT"


def command_compare_parameters(root: Path, args: argparse.Namespace) -> dict[str, Any]:
    audit = command_audit(root, write_report=True)
    if not audit["audit_passed"]:
        raise ControlError("Cannot compare and version parameters while the global/local state or a locked source is in conflict")
    planned = parse_json_argument(args.planned)
    actual = parse_json_argument(args.actual)
    if not isinstance(planned, dict) or not isinstance(actual, dict):
        raise ControlError("Planned and actual parameters must be JSON objects")
    actual_sources = [file_record(Path(item), "actual_parameter_source", root) for item in args.actual_source]
    planned_sources = [file_record(Path(item), "planned_parameter_source", root) for item in args.planned_source]
    registries = load_registries(root)
    calc_latest = latest_entries(registries["CALC"])
    if args.calculation_id not in calc_latest:
        raise ControlError(f"Unknown calculation ID: {args.calculation_id}")
    before = calc_latest[args.calculation_id]
    planned_flat = flatten(planned)
    actual_flat = flatten(actual)
    differences = []
    for key in sorted(set(planned_flat) | set(actual_flat)):
        pv = planned_flat.get(key, {"missing": True})
        av = actual_flat.get(key, {"missing": True})
        if pv != av:
            classification = classify_parameter(key)
            differences.append({"path": key, "planned_value": pv, "actual_value": av, "classification": classification})
    highest = max((item["classification"] for item in differences), key=lambda item: CLASS_RANK[item], default="RUNTIME_ONLY")
    confirmation = args.confirmation_note if args.user_confirmed else None
    if highest in {"SCIENTIFICALLY_RELEVANT", "MODEL_CHANGING"} and not args.user_confirmed:
        impact = "explicit review required before comparability or manuscript use"
    elif differences:
        impact = "differences recorded; retain the actual version for method reporting"
    else:
        impact = "no differences detected in supplied normalized parameter objects"
    updated = deepcopy(before)
    updated["version"] = int(before.get("version", 1)) + 1
    updated["updated_at"] = utc_now()
    updated["planned_parameters"] = planned
    updated["actual_parameters"] = actual
    updated["planned_parameter_sources"] = planned_sources
    updated["actual_parameter_sources"] = actual_sources
    updated["parameter_differences"] = differences
    updated["difference_classification"] = highest
    updated["difference_impact"] = impact
    updated["user_confirmation"] = confirmation
    append_entry(owned(root, f"provenance/{REGISTRY_FILES['CALC']}"), updated)
    return {"calculation_id": args.calculation_id, "new_version": updated["version"], "difference_count": len(differences), "highest_classification": highest, "explicit_review_required": highest in {"SCIENTIFICALLY_RELEVANT", "MODEL_CHANGING"} and not args.user_confirmed, "differences": differences}


def record_files_valid(records: Any, gaps: list[str], label: str) -> bool:
    if not isinstance(records, list) or not records:
        gaps.append(f"missing {label} file records")
        return False
    valid = True
    for record in records:
        if not isinstance(record, dict):
            gaps.append(f"invalid {label} file record")
            valid = False
            continue
        path = Path(record.get("path", ""))
        if not path.is_file():
            gaps.append(f"missing {label} file: {record.get('path')}")
            valid = False
        elif sha256_file(path) != record.get("sha256"):
            gaps.append(f"changed {label} file: {record.get('path')}")
            valid = False
    return valid


def traceability_for_conclusion(conclusion: dict[str, Any], latest: dict[str, dict[str, dict[str, Any]]]) -> dict[str, Any]:
    gaps: list[str] = []
    evidence_ids = conclusion.get("evidence_ids") or []
    result_ids: set[str] = set()
    calculation_ids: set[str] = set()
    model_ids: set[str] = set()
    task_ids: set[str] = set(conclusion.get("stage1_task_ids") or [])
    processed_present = False
    if not evidence_ids:
        gaps.append("conclusion has no evidence IDs")
    for evidence_id in evidence_ids:
        evidence = latest["EVIDENCE"].get(evidence_id)
        if not evidence:
            gaps.append(f"missing evidence registry entry: {evidence_id}")
            continue
        if evidence.get("validation_status") not in {"VALIDATED", "APPROVED", "EVIDENCE_NODE_APPROVED", "accepted"}:
            gaps.append(f"evidence not validated: {evidence_id}")
        result_ids.update(evidence.get("result_ids") or [])
        if evidence.get("processed_data_files"):
            processed_present = record_files_valid(evidence.get("processed_data_files"), gaps, f"evidence {evidence_id} processed data") or processed_present
    for result_id in sorted(result_ids):
        result = latest["RESULT"].get(result_id)
        if not result:
            gaps.append(f"missing result registry entry: {result_id}")
            continue
        calculation_ids.update(result.get("calculation_ids") or [])
        if result.get("processed_data_files"):
            processed_present = record_files_valid(result.get("processed_data_files"), gaps, f"result {result_id} processed data") or processed_present
        record_files_valid(result.get("real_result_files"), gaps, f"result {result_id} real result")
    if not processed_present:
        gaps.append("no traceable processed data file")
    for calculation_id in sorted(calculation_ids):
        calculation = latest["CALC"].get(calculation_id)
        if not calculation:
            gaps.append(f"missing calculation registry entry: {calculation_id}")
            continue
        model_ids.update(calculation.get("model_ids") or [])
        task_ids.update(calculation.get("stage1_task_ids") or [])
        record_files_valid(calculation.get("actual_input_files") or calculation.get("actual_parameter_sources"), gaps, f"calculation {calculation_id} actual input")
        record_files_valid(calculation.get("actual_output_files"), gaps, f"calculation {calculation_id} actual output")
        if calculation.get("actual_parameters") is None:
            gaps.append(f"calculation lacks actual parameters: {calculation_id}")
    for model_id in sorted(model_ids):
        model = latest["MODEL"].get(model_id)
        if not model:
            gaps.append(f"missing model registry entry: {model_id}")
            continue
        task_ids.update(model.get("stage1_task_ids") or [])
        record_files_valid(model.get("source_files"), gaps, f"model {model_id}")
    if not task_ids:
        gaps.append("no approved stage-1 task ID")
    status = "TRACEABILITY_COMPLETE" if not gaps else "TRACEABILITY_INCOMPLETE"
    return {
        "conclusion_id": conclusion["id"],
        "conclusion_version": conclusion.get("version"),
        "checked_at": utc_now(),
        "status": status,
        "manuscript_eligible": status == "TRACEABILITY_COMPLETE",
        "chain": {"evidence_ids": sorted(evidence_ids), "result_ids": sorted(result_ids), "calculation_ids": sorted(calculation_ids), "model_ids": sorted(model_ids), "stage1_task_ids": sorted(task_ids)},
        "gaps": sorted(set(gaps)),
    }


def command_check_traceability(root: Path, args: argparse.Namespace | None = None) -> dict[str, Any]:
    registries = load_registries(root)
    latest = {kind: latest_entries(registry) for kind, registry in registries.items()}
    wanted = getattr(args, "conclusion_id", None) if args else None
    conclusions = [latest["CONCLUSION"][wanted]] if wanted else list(latest["CONCLUSION"].values())
    if wanted and wanted not in latest["CONCLUSION"]:
        raise ControlError(f"Unknown conclusion ID: {wanted}")
    entries = [traceability_for_conclusion(item, latest) for item in sorted(conclusions, key=lambda item: item["id"])]
    summary = {"complete": sum(item["status"] == "TRACEABILITY_COMPLETE" for item in entries), "incomplete": sum(item["status"] == "TRACEABILITY_INCOMPLETE" for item in entries), "total": len(entries)}
    data = {"schema_version": SCHEMA_VERSION, "checked_at": utc_now(), "entries": entries, "summary": summary}
    write_json(owned(root, "provenance/conclusion_traceability.json"), data)
    return data


def command_pause(root: Path, args: argparse.Namespace) -> dict[str, Any]:
    control = owned(root, "project_control")
    workflow = read_json(control / "workflow_state.json")
    manifest = read_json(control / "project_manifest.json")
    record = {
        "schema_version": SCHEMA_VERSION,
        "project_id": manifest.get("project_id"),
        "source_state_revision": workflow.get("revision"),
        "current_stage": args.stage,
        "current_task": args.task,
        "current_model_version": args.model_version or manifest.get("current_model_id"),
        "current_input_version": args.input_version or manifest.get("current_parameter_version"),
        "current_result_version": args.result_version or manifest.get("current_result_id"),
        "completed_steps": args.completed_step,
        "incomplete_steps": args.incomplete_step,
        "last_decision": args.last_decision,
        "allowed_next_operations": args.allowed_operation,
        "next_user_action": args.next_action,
        "required_return_files": args.required_file,
        "updated_at": utc_now(),
    }
    version, history_path = next_version(control / "resume_history", "resume")
    record["resume_version"] = version
    write_new_json(history_path, record)
    write_json(control / "resume_context.json", record)
    atomic_write_text(control / "next_user_action.md", f"# 下一步操作\n\n{args.next_action.strip()}\n")
    required_lines = "\n".join(f"- {item}" for item in args.required_file) if args.required_file else "当前没有指定必须回传的文件。"
    atomic_write_text(control / "required_return_files.md", f"# 需要回传的文件\n\n{required_lines}\n")
    render_dashboard(root)
    return {"status": "paused", "resume_version": version, "history": str(history_path), "next_user_action": args.next_action, "required_return_files": args.required_file}


def command_resume(root: Path, args: argparse.Namespace) -> dict[str, Any]:
    audit = command_audit(root, write_report=True)
    resume = read_json(owned(root, "project_control/resume_context.json"))
    return {"status": "resume_ready" if audit["audit_passed"] else "resume_blocked_by_audit", "audit_passed": audit["audit_passed"], "conflicts": audit["conflicts"], "resume_context": resume, "instruction": "Continue only the recorded allowed operation; do not repeat completed approvals." if audit["audit_passed"] else "Resolve the state/hash conflict without overwriting local history."}


def command_classify_error(root: Path, args: argparse.Namespace) -> dict[str, Any]:
    control = owned(root, "project_control")
    evidence = [file_record(Path(item), "error_evidence", root) for item in args.evidence_file]
    version, path = next_version(control / "error_reports", "error")
    report = {
        "schema_version": SCHEMA_VERSION,
        "error_version": version,
        "error_type": args.error_type,
        "summary": args.summary,
        "evidence_files": evidence,
        "affected_ids": args.affected_id,
        "owning_route": ERROR_ROUTES[args.error_type],
        "recommended_action": args.recommended_action or ERROR_ROUTES[args.error_type],
        "user_action_required": True,
        "recorded_at": utc_now(),
        **FALSE_EXECUTION_FLAGS,
    }
    write_new_json(path, report)
    render_dashboard(root)
    return report


def command_add_citation(root: Path, args: argparse.Namespace) -> dict[str, Any]:
    record = parse_json_argument(args.record)
    if not isinstance(record, dict):
        raise ControlError("Citation record must be a JSON object")
    required = ["type", "software_or_method", "status"]
    missing = [field for field in required if not record.get(field)]
    if missing:
        raise ControlError(f"Missing citation fields: {', '.join(missing)}")
    allowed = {"VERIFIED", "PENDING_VERSION", "PENDING_METHOD_DETAIL", "PENDING_OFFICIAL_SOURCE", "NOT_APPLICABLE"}
    if record["status"] not in allowed:
        raise ControlError(f"Unsupported citation status: {record['status']}")
    if record["status"] == "VERIFIED" and not record.get("source_url_or_doi"):
        raise ControlError("A VERIFIED citation requires source_url_or_doi")
    path = owned(root, "project_control/citation_registry.json")
    registry = read_json(path)
    citation_id = f"CITATION-{len(registry.get('entries', [])) + 1:04d}"
    entry = {"citation_id": citation_id, "recorded_at": utc_now(), **record}
    registry["entries"].append(entry)
    write_json(path, registry)
    return {"status": "citation_recorded", **entry}


def delivery_registry(root: Path) -> tuple[Path, dict[str, Any]]:
    path = owned(root, "project_delivery/delivery_registry.json")
    if not path.exists():
        write_new_json(path, {"schema_version": SCHEMA_VERSION, "entries": []})
    return path, read_json(path)


def command_delivery_add(root: Path, args: argparse.Namespace) -> dict[str, Any]:
    entry_gate = gate_report(root, "manuscript_approved")
    if not entry_gate["passed"]:
        raise ControlError(f"Delivery intake is blocked: {', '.join(entry_gate['missing'])}")
    audit = command_audit(root, write_report=True)
    if not audit["audit_passed"]:
        raise ControlError("Delivery intake is blocked by a global/local state or locked-source conflict")
    workflow = read_json(owned(root, "project_control/workflow_state.json"))
    if workflow.get("state") == "MANUSCRIPT_CONTENT_APPROVED":
        command_transition(root, argparse.Namespace(to_state="DELIVERY_VALIDATION_IN_PROGRESS", actor="skill", task="delivery file intake", user_confirmed=False, confirmation_note=None, allow_reopen=False))
    source = Path(args.source).expanduser().resolve()
    if not source.is_file():
        raise ControlError(f"Delivery source must be a file: {source}")
    delivery = owned(root, "project_delivery")
    category = args.category
    category_dir = owned(root, f"project_delivery/{category}")
    category_dir.mkdir(parents=True, exist_ok=True)
    relative_name = Path(args.destination or source.name)
    if relative_name.is_absolute() or ".." in relative_name.parts:
        raise ControlError("Delivery destination must be a safe relative path")
    destination = (category_dir / relative_name).resolve()
    try:
        destination.relative_to(category_dir.resolve())
    except ValueError as exc:
        raise ControlError("Delivery destination escapes its category") from exc
    source_hash = sha256_file(source)
    included = args.sharing_status != "RESTRICTED_REFERENCE_ONLY"
    if included:
        destination.parent.mkdir(parents=True, exist_ok=True)
        if destination.exists() and sha256_file(destination) != source_hash:
            raise ControlError(f"Refusing to overwrite different delivery file: {destination}")
        if not destination.exists():
            shutil.copy2(source, destination)
        if sha256_file(source) != source_hash or sha256_file(destination) != source_hash:
            raise ControlError("Hash mismatch after delivery copy")
    registry_path, registry = delivery_registry(root)
    file_id = f"DELIVERY-FILE-{len(registry.get('entries', [])) + 1:05d}"
    entry = {
        "file_id": file_id,
        "file_name": source.name,
        "source_path": str(source),
        "delivery_path": destination.relative_to(delivery).as_posix() if included else None,
        "category": category,
        "file_type": args.file_type or source.suffix.lstrip(".") or "file",
        "stage": args.stage,
        "task": args.task,
        "model_version": args.model_version,
        "parameter_version": args.parameter_version,
        "result_version": args.result_version,
        "is_original": args.original,
        "is_approved": args.approved,
        "provenance_source": args.provenance_source,
        "source_sha256": source_hash,
        "delivery_sha256": source_hash if included else None,
        "sharing_status": args.sharing_status,
        "included": included,
        "notes": args.notes,
        "added_at": utc_now(),
    }
    registry["entries"].append(entry)
    write_json(registry_path, registry)
    return {"status": "recorded", **entry}


def markdown_value(value: Any) -> str:
    if value is None or value == "":
        return "未确认"
    if isinstance(value, list):
        return ", ".join(str(item) for item in value) if value else "无"
    return str(value)


def write_delivery_manifest(delivery: Path, entries: list[dict[str, Any]]) -> None:
    fields = ["file_id", "file_name", "delivery_path", "file_type", "stage", "task", "model_version", "parameter_version", "result_version", "is_original", "is_approved", "provenance_source", "delivery_sha256", "sharing_status", "included", "notes"]
    path = delivery / "FILE_MANIFEST.csv"
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    with temporary.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(entries)
    temporary.replace(path)


def verified_delivery_entries(root: Path, entries: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    valid = []
    problems = []
    delivery = owned(root, "project_delivery")
    for entry in entries:
        source = Path(entry.get("source_path", ""))
        if not source.is_file():
            problems.append({"severity": "BLOCKING_DELIVERY", "item": entry.get("file_id"), "issue": "source file missing", "path": str(source)})
            continue
        actual_source_hash = sha256_file(source)
        if actual_source_hash != entry.get("source_sha256"):
            problems.append({"severity": "BLOCKING_CORE", "item": entry.get("file_id"), "issue": "source file changed after intake", "path": str(source)})
            continue
        if entry.get("included"):
            destination = (delivery / entry.get("delivery_path", "")).resolve()
            try:
                destination.relative_to(delivery.resolve())
            except ValueError:
                problems.append({"severity": "BLOCKING_DELIVERY", "item": entry.get("file_id"), "issue": "delivery path traversal"})
                continue
            if not destination.is_file() or sha256_file(destination) != entry.get("delivery_sha256"):
                problems.append({"severity": "BLOCKING_DELIVERY", "item": entry.get("file_id"), "issue": "delivery copy missing or changed", "path": str(destination)})
                continue
        valid.append(entry)
    return valid, problems


def delivery_missing_items(root: Path, trace: dict[str, Any], entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for gate in ("stage1_approved", "results_approved", "manuscript_approved"):
        report = gate_report(root, gate)
        for missing in report["missing"]:
            items.append({"severity": "BLOCKING_CORE", "missing_file_or_record": missing, "task": gate, "reproduction_impact": "breaks approved workflow trace", "manuscript_impact": "blocks validated final delivery", "suggested_remedy": "restore or regenerate through the owning stage without overwriting history", "absence_acceptable": False})
    for trace_entry in trace.get("entries", []):
        for gap in trace_entry.get("gaps", []):
            items.append({"severity": "BLOCKING_CORE", "missing_file_or_record": gap, "task": trace_entry["conclusion_id"], "reproduction_impact": "conclusion source chain incomplete", "manuscript_impact": "conclusion is not eligible for final approved prose", "suggested_remedy": "complete the exact provenance node or remove the unsupported conclusion", "absence_acceptable": False})
    included_categories = {entry.get("category") for entry in entries if entry.get("included")}
    for category in ("01_planning", "02_models", "03_calculation_inputs", "04_hpc_scripts", "05_user_results", "06_processed_data", "07_analysis", "08_manuscript", "10_provenance"):
        if category not in included_categories:
            items.append({"severity": "BLOCKING_DELIVERY", "missing_file_or_record": f"no reviewed delivery file in {category}", "task": "delivery package", "reproduction_impact": "required deliverable category absent", "manuscript_impact": "package inspection incomplete", "suggested_remedy": "add only the reviewed required files with delivery-add", "absence_acceptable": False})
    if "09_open_source_reproduction" not in included_categories:
        items.append({"severity": "REPRODUCTION_LIMITATION", "missing_file_or_record": "no packaged open-source reproduction note", "task": "open-source reproduction", "reproduction_impact": "prospective alternative is not packaged", "manuscript_impact": "does not alter actual calculation provenance", "suggested_remedy": "add the approved separate reproduction note if available", "absence_acceptable": True})
    manifest = read_json(owned(root, "project_control/project_manifest.json"))
    if not manifest.get("specified_software"):
        items.append({"severity": "BLOCKING_CORE", "missing_file_or_record": "actual calculation software identity", "task": "actual method provenance", "reproduction_impact": "calculation implementation cannot be reconstructed", "manuscript_impact": "actual method cannot be verified", "suggested_remedy": "record the real software from actual input/output evidence; do not substitute an alternative", "absence_acceptable": False})
    citations = read_json(owned(root, "project_control/citation_registry.json"), required=False) or {"entries": []}
    if not any(item.get("status") == "VERIFIED" for item in citations.get("entries", [])):
        items.append({"severity": "BLOCKING_DELIVERY", "missing_file_or_record": "verified software or method citation record", "task": "software and method citation", "reproduction_impact": "software/method identity lacks a checked reference", "manuscript_impact": "citation checklist is incomplete", "suggested_remedy": "verify the exact actual version/method against an official or primary source", "absence_acceptable": False})
    return items


def command_delivery_check(root: Path, args: argparse.Namespace) -> dict[str, Any]:
    entry_gate = gate_report(root, "manuscript_approved")
    if not entry_gate["passed"]:
        return {"state": "DELIVERY_ENTRY_BLOCKED", "entry_gate": entry_gate, "instruction": "Complete only the listed stage-4 or upstream requirements before creating a delivery package.", **FALSE_EXECUTION_FLAGS}
    audit = command_audit(root, write_report=True)
    if not audit["audit_passed"]:
        return {"state": "DELIVERY_ENTRY_BLOCKED", "entry_gate": entry_gate, "audit": audit, "instruction": "Reconcile the recorded global/local state or locked-source conflict before delivery; do not overwrite history.", **FALSE_EXECUTION_FLAGS}
    workflow = read_json(owned(root, "project_control/workflow_state.json"))
    if workflow.get("state") != "DELIVERY_VALIDATION_IN_PROGRESS":
        command_transition(root, argparse.Namespace(to_state="DELIVERY_VALIDATION_IN_PROGRESS", actor="skill", task="delivery validation", user_confirmed=False, confirmation_note=None, allow_reopen=False))
    delivery = owned(root, "project_delivery")
    delivery.mkdir(parents=True, exist_ok=True)
    for category in sorted(DELIVERY_CATEGORIES):
        (delivery / category).mkdir(parents=True, exist_ok=True)
    registry_path, registry = delivery_registry(root)
    entries = registry.get("entries", [])
    valid_entries, integrity_problems = verified_delivery_entries(root, entries)
    trace = command_check_traceability(root)
    missing = delivery_missing_items(root, trace, valid_entries)
    if trace.get("summary", {}).get("total", 0) == 0:
        missing.append({"severity": "BLOCKING_CORE", "missing_file_or_record": "no registered approved conclusion trace", "task": "conclusion provenance", "reproduction_impact": "no conclusion-to-result chain can be inspected", "manuscript_impact": "approved manuscript conclusions lack global provenance", "suggested_remedy": "register approved conclusions and their evidence/result/calculation/model links", "absence_acceptable": False})
    for problem in integrity_problems:
        missing.append({"severity": problem["severity"], "missing_file_or_record": problem.get("path") or problem.get("item"), "task": "delivery integrity", "reproduction_impact": problem["issue"], "manuscript_impact": "package hash integrity failed", "suggested_remedy": "restore the recorded source/copy or add a new reviewed delivery version", "absence_acceptable": False})
    blocking = [item for item in missing if item["severity"].startswith("BLOCKING")]
    manifest = read_json(owned(root, "project_control/project_manifest.json"))
    workflow = read_json(owned(root, "project_control/workflow_state.json"))
    state = "DELIVERY_ITEMS_MISSING" if blocking else "DELIVERY_USER_REVIEW_REQUIRED"
    write_delivery_manifest(delivery, entries)
    actual_software = manifest.get("specified_software") or "未确认"
    readme = f"""# 项目交付说明

## 项目目标

{markdown_value(manifest.get('research_goal'))}

## 整体工作流

本项目按经审批的计划、模型、计算文件、用户真实结果、数据处理、证据验证和论文内容顺序组织。全局状态：`{workflow.get('state')}`。

## 主要材料模型

当前模型编号：{markdown_value(manifest.get('current_model_id'))}。详细模型记录见 `02_models/` 与 `10_provenance/`。

## 实际计算软件

{actual_software}。未确认的软件版本和参数不得由本 README 补写。

## 文件夹与任务顺序

目录 `01` 至 `10` 依次存放方案、模型、计算输入、运行脚本、用户结果、处理后数据、分析、论文、独立开源复现建议和来源追踪。正式任务顺序以批准的阶段一方案和来源登记为准。

## 数据处理与核心结论

处理方式见 `06_processed_data/` 和 `07_analysis/`；核心结论和论文内容见 `08_manuscript/`。所有最终结论必须通过 `10_provenance/` 追溯。

## 开源复现建议

若存在，位于 `09_open_source_reproduction/`。它不代表现有结果已经由替代软件重新计算。

## 已知缺失内容

见 `MISSING_ITEMS.md`。

## 恢复项目

读取项目根目录 `project_control/resume_context.json`、`next_user_action.md` 和本交付包的来源清单；恢复前先运行全局审计，不要重做已批准步骤。
"""
    atomic_write_text(delivery / "README.md", readme)
    repro = ["# 可复现性记录", "", f"- 完整追踪结论：{trace['summary']['complete']}", f"- 追踪不完整结论：{trace['summary']['incomplete']}", f"- 实际计算软件：{actual_software}", "- 非开源或受限软件仍按真实来源记录；受许可限制的文件不应打包。", "- 开源替代参数映射仅为复现建议，除非有真实重算结果，否则不得写成复现成功。", "- 跨程序差异可能来自数值实现、赝势/基组、网格、默认收敛和后处理定义。", "", "## 限制", ""]
    repro.extend(f"- [{item['severity']}] {item['missing_file_or_record']}" for item in missing if item["severity"] in {"REPRODUCTION_LIMITATION", "DISCLOSURE_ONLY"})
    atomic_write_text(delivery / "REPRODUCIBILITY_RECORD.md", "\n".join(repro) + "\n")
    citation_registry = read_json(owned(root, "project_control/citation_registry.json"), required=False) or {"entries": []}
    software_lines = ["# 软件与许可", "", f"- 实际软件：{actual_software}", f"- 版本：{markdown_value(manifest.get('software_version'))}", "- 许可、引用和共享权利必须按实际版本与模块核验。", "- 开源替代项属于独立的未来复现建议。", "", "## 引用登记", ""]
    if citation_registry.get("entries"):
        software_lines.extend(f"- {item.get('citation_id', '未编号')}: {item.get('software_or_method', '未确认')} — {item.get('status', 'UNVERIFIED')}" for item in citation_registry["entries"])
    else:
        software_lines.append("- 尚无已核验引用登记。")
    atomic_write_text(delivery / "SOFTWARE_AND_LICENSES.md", "\n".join(software_lines) + "\n")
    missing_lines = ["# 缺失项目", ""]
    if missing:
        for index, item in enumerate(missing, 1):
            missing_lines.extend([f"## {index}. {item['missing_file_or_record']}", "", f"- 严重性：`{item['severity']}`", f"- 对应任务：{item['task']}", f"- 是否影响复现：{item['reproduction_impact']}", f"- 是否影响论文：{item['manuscript_impact']}", f"- 建议补充方式：{item['suggested_remedy']}", f"- 是否可以接受缺失：{'是' if item['absence_acceptable'] else '否'}", ""])
    else:
        missing_lines.append("未发现缺失项。")
    atomic_write_text(delivery / "MISSING_ITEMS.md", "\n".join(missing_lines) + "\n")
    checks = [
        ("第一阶段批准方案存在", gate_report(root, "stage1_approved")["passed"]),
        ("结果分析已批准", gate_report(root, "results_approved")["passed"]),
        ("论文内容已批准", gate_report(root, "manuscript_approved")["passed"]),
        ("结论来源完整", trace["summary"]["incomplete"] == 0),
        ("交付复制哈希一致", not integrity_problems),
        ("无阻断缺失项", not blocking),
    ]
    atomic_write_text(delivery / "DELIVERY_CHECKLIST.md", "# 交付核对\n\n" + "\n".join(f"- [{'x' if passed else ' '}] {label}" for label, passed in checks) + "\n")
    approved_models = len(latest_entries(load_registries(root)["MODEL"]))
    report_lines = ["# 最终交付报告", "", f"- 已完成全局状态：{workflow.get('state')}", f"- 批准/登记模型数：{approved_models}", f"- 正式计算任务数：{len(latest_entries(load_registries(root)['CALC']))}", f"- 用户结果数：{len(latest_entries(load_registries(root)['RESULT']))}", f"- 处理后与分析条目：{len(latest_entries(load_registries(root)['EVIDENCE']))}", f"- 通过追踪的证据结论：{trace['summary']['complete']}", f"- 论文内容状态：{local_snapshot(root)['manuscript'].get('state')}", "- 软件与许可状态：见 SOFTWARE_AND_LICENSES.md", "- 开源复现状态：建议与实际计算分离", f"- 缺失项目数：{len(missing)}", f"- 交付登记文件数：{len(entries)}", "- 待用户保留事项：原始输入、输出、结构、数据和所有批准历史版本。"]
    atomic_write_text(delivery / "DELIVERY_REPORT.md", "\n".join(report_lines) + "\n")
    atomic_write_text(delivery / "files_recommended_for_cleanup.md", "# 建议清理清单\n\n本次检查不自动删除或移动任何文件。未发现可在无用户逐项确认下安全清理的文件。不得删除用户原始输入、输出、结构或数据。\n")
    check_version, check_path = next_version(delivery / "validation_history", "delivery_check")
    status = {"schema_version": SCHEMA_VERSION, "project_version": manifest.get("project_version"), "check_version": check_version, "state": state, "checked_at": utc_now(), "file_count": len(entries), "valid_file_count": len(valid_entries), "blocking_missing_items": blocking, "all_missing_items": missing, "traceability_summary": trace["summary"], "user_review_required": not blocking, **FALSE_EXECUTION_FLAGS}
    write_new_json(check_path, status)
    write_json(delivery / "delivery_status.json", status)
    command_transition(root, argparse.Namespace(to_state=state, actor="skill", task="delivery validation result", user_confirmed=False, confirmation_note=None, allow_reopen=False))
    return status


def command_delivery_accept(root: Path, args: argparse.Namespace) -> dict[str, Any]:
    if not getattr(args, "review_verified", False):
        raise ControlError("Delivery acceptance must be submitted through the hash-bound browser review command")
    status_path = owned(root, "project_delivery/delivery_status.json")
    status = read_json(status_path)
    if status.get("state") != "DELIVERY_USER_REVIEW_REQUIRED" or status.get("blocking_missing_items"):
        raise ControlError("Delivery can be accepted only after a clean check and user review")
    if not args.user_confirmed or not (args.confirmation_note or "").strip():
        raise ControlError("Delivery acceptance requires --user-confirmed and --confirmation-note")
    version, path = next_version(owned(root, "project_delivery/approval_history"), "delivery_approval")
    approval = {"schema_version": SCHEMA_VERSION, "approval_version": version, "actor": args.actor, "confirmation_note": args.confirmation_note, "approved_at": utc_now(), "delivery_check_version": status.get("check_version"), "file_manifest": file_record(owned(root, "project_delivery/FILE_MANIFEST.csv"), "delivery_manifest", root)}
    write_new_json(path, approval)
    status["state"] = "DELIVERY_PACKAGE_READY"
    status["user_approval"] = approval
    write_json(status_path, status)
    command_transition(root, argparse.Namespace(to_state="DELIVERY_PACKAGE_READY", actor=args.actor, task="delivery package approved", user_confirmed=True, confirmation_note=args.confirmation_note, allow_reopen=False))
    return status


def append_delivery_review_log(root: Path, entry: dict[str, Any]) -> None:
    path = owned(root, "project_delivery/review_change_log.json")
    records = read_json(path, required=False) or []
    if not isinstance(records, list):
        raise ControlError("project_delivery/review_change_log.json must contain a list")
    records.append({**entry, "recorded_at": utc_now()})
    write_json(path, records)


def delivery_review_bundle(root: Path, archive_review: bool) -> Path:
    delivery = owned(root, "project_delivery")
    status = read_json(delivery / "delivery_status.json")
    report_path = delivery / "DELIVERY_REPORT.md"
    manifest_path = delivery / "FILE_MANIFEST.csv"
    if not report_path.is_file() or not manifest_path.is_file():
        raise ControlError("Delivery report and file manifest are required for browser review")
    bundle = {
        "schema_version": SCHEMA_VERSION,
        "review_kind": "archive" if archive_review else "delivery_package",
        "delivery_status": status,
        "delivery_report_file": str(report_path.relative_to(root)),
        "delivery_report": report_path.read_text(encoding="utf-8"),
        "file_manifest_file": str(manifest_path.relative_to(root)),
        "file_manifest": manifest_path.read_text(encoding="utf-8"),
        "generated_at": utc_now(),
    }
    path = delivery / ("archive_review_bundle.json" if archive_review else "delivery_review_bundle.json")
    write_json(path, bundle)
    return path


def command_delivery_browser_review(root: Path, args: argparse.Namespace, archive_review: bool) -> dict[str, Any]:
    delivery_dir = owned(root, "project_delivery")
    delivery_status_path = delivery_dir / "delivery_status.json"
    status = read_json(delivery_status_path)
    expected = "DELIVERY_PACKAGE_READY" if archive_review else "DELIVERY_USER_REVIEW_REQUIRED"
    if status.get("state") != expected:
        raise ControlError(f"Browser review requires {expected}")
    if status.get("blocking_missing_items"):
        raise ControlError("Blocking delivery items must be resolved before browser review")
    content_file = delivery_review_bundle(root, archive_review)
    stage = "stage5_archive" if archive_review else "stage5_delivery"
    title = args.title or ("第五阶段：项目归档最终审查" if archive_review else "第五阶段：交付包审查")

    def approve_browser(comment: str) -> dict[str, Any]:
        confirmation = comment.strip() or "Approved through hash-bound browser review."
        approval_args = argparse.Namespace(
            actor="browser_user",
            user_confirmed=True,
            confirmation_note=confirmation,
            review_verified=True,
        )
        return command_archive(root, approval_args) if archive_review else command_delivery_accept(root, approval_args)

    result = execute_stage_review(
        project_dir=root,
        stage_dir=delivery_dir,
        stage=stage,
        title=title,
        content_file=content_file,
        allowed_statuses={expected},
        revision_status=expected,
        rejected_status="DELIVERY_REVIEW_REJECTED",
        load_status=lambda: read_json(delivery_status_path),
        save_status=lambda value: write_json(delivery_status_path, value),
        append_log=lambda value: append_delivery_review_log(root, value),
        approve=approve_browser,
        error_type=ControlError,
        blocked_access_updates={"user_review_required": True},
        revision_updates={"user_review_required": True},
        rejected_updates={"user_review_required": False},
        status_field="state",
        start_port=args.start_port,
        timeout_seconds=args.timeout,
    )
    resulting_status = result.get("status") if isinstance(result, dict) else None
    if isinstance(resulting_status, dict) and resulting_status.get("state") == "DELIVERY_REVIEW_REJECTED":
        command_transition(
            root,
            argparse.Namespace(
                to_state="DELIVERY_REVIEW_REJECTED",
                actor="browser_user",
                task="delivery review rejected",
                user_confirmed=False,
                confirmation_note=resulting_status.get("review_comment"),
                allow_reopen=False,
            ),
        )
    return result


def command_archive(root: Path, args: argparse.Namespace) -> dict[str, Any]:
    if not getattr(args, "review_verified", False):
        raise ControlError("Project archival must be submitted through the hash-bound browser review command")
    delivery = read_json(owned(root, "project_delivery/delivery_status.json"))
    if delivery.get("state") != "DELIVERY_PACKAGE_READY" or delivery.get("blocking_missing_items"):
        raise ControlError("Archive requires DELIVERY_PACKAGE_READY with no blocking missing items")
    if not args.user_confirmed or not (args.confirmation_note or "").strip():
        raise ControlError("Archive requires explicit --user-confirmed and --confirmation-note")
    control = owned(root, "project_control")
    workflow = read_json(control / "workflow_state.json")
    manifest = read_json(control / "project_manifest.json")
    version, path = next_version(control / "archive_records", "archive")
    metadata_dir = control / "archive_records" / f"archive_v{version:03d}_metadata"
    if metadata_dir.exists():
        raise ControlError(f"Refusing to overwrite archive metadata directory: {metadata_dir}")
    metadata_dir.mkdir(parents=True)
    metadata_names = ["README.md", "FILE_MANIFEST.csv", "REPRODUCIBILITY_RECORD.md", "SOFTWARE_AND_LICENSES.md", "MISSING_ITEMS.md", "DELIVERY_CHECKLIST.md", "DELIVERY_REPORT.md", "files_recommended_for_cleanup.md", "delivery_status.json", "delivery_registry.json"]
    metadata_records = []
    for name in metadata_names:
        source = owned(root, f"project_delivery/{name}")
        if source.is_file():
            destination = metadata_dir / name
            shutil.copy2(source, destination)
            metadata_records.append(file_record(destination, "archived_delivery_metadata", root))
    record = {
        "schema_version": SCHEMA_VERSION,
        "archive_version": version,
        "project_id": manifest.get("project_id"),
        "project_version": manifest.get("project_version"),
        "global_revision": workflow.get("revision"),
        "file_manifest": file_record(owned(root, "project_delivery/FILE_MANIFEST.csv"), "delivery_manifest", root),
        "delivery_report": file_record(owned(root, "project_delivery/DELIVERY_REPORT.md"), "delivery_report", root),
        "traceability_summary": delivery.get("traceability_summary"),
        "missing_item_summary": {"blocking": len(delivery.get("blocking_missing_items", [])), "total": len(delivery.get("all_missing_items", []))},
        "metadata_snapshot": metadata_records,
        "actor": args.actor,
        "confirmation_note": args.confirmation_note,
        "archived_at": utc_now(),
    }
    write_new_json(path, record)
    transition_args = argparse.Namespace(to_state="PROJECT_ARCHIVED", actor=args.actor, task="project archived", user_confirmed=True, confirmation_note=args.confirmation_note, allow_reopen=False)
    result = command_transition(root, transition_args)
    return {**result, "archive_record": str(path), "archive_version": version}


def command_reopen(root: Path, args: argparse.Namespace) -> dict[str, Any]:
    if args.return_state not in GLOBAL_STATES or args.return_state == "PROJECT_ARCHIVED":
        raise ControlError("Reopen requires a valid non-archived return state")
    control = owned(root, "project_control")
    workflow = read_json(control / "workflow_state.json")
    if workflow.get("state") != "PROJECT_ARCHIVED":
        raise ControlError("Only an archived project can be reopened")
    if not args.user_confirmed or not args.reason.strip():
        raise ControlError("Reopen requires --user-confirmed and a reason")
    gate = gate_report(root, state_gate(args.return_state))
    if not gate["passed"]:
        raise ControlError(f"Return state gate is not satisfied: {', '.join(gate['missing'])}")
    manifest = read_json(control / "project_manifest.json")
    old_version = int(manifest.get("project_version", 1))
    manifest["project_version"] = old_version + 1
    manifest["last_user_action"] = args.reason
    write_json(control / "project_manifest.json", manifest)
    version, path = next_version(control / "reopen_records", "reopen")
    record = {"schema_version": SCHEMA_VERSION, "reopen_version": version, "from_project_version": old_version, "to_project_version": old_version + 1, "return_state": args.return_state, "reason": args.reason, "affected_ids": args.affected_id, "actor": args.actor, "reopened_at": utc_now()}
    write_new_json(path, record)
    transition_args = argparse.Namespace(to_state=args.return_state, actor=args.actor, task="reopened project", user_confirmed=True, confirmation_note=args.reason, allow_reopen=True)
    result = command_transition(root, transition_args)
    return {**result, "reopen_record": str(path), "project_version": old_version + 1}


def add_common_delivery_metadata(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--stage", required=True)
    parser.add_argument("--task", required=True)
    parser.add_argument("--model-version")
    parser.add_argument("--parameter-version")
    parser.add_argument("--result-version")
    parser.add_argument("--file-type")
    parser.add_argument("--provenance-source", required=True)
    parser.add_argument("--notes")
    parser.add_argument("--original", action="store_true")
    parser.add_argument("--approved", action="store_true")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Global project control, provenance, recovery, and delivery without calculation execution")
    parser.add_argument("--project-root", required=True, help="Computational chemistry project root")
    sub = parser.add_subparsers(dest="command", required=True)

    init = sub.add_parser("init", help="Initialize global control and provenance stores without overwriting")
    init.add_argument("--project-name")
    init.add_argument("--research-object")
    init.add_argument("--material-system")
    init.add_argument("--research-goal")
    init.add_argument("--software")
    init.add_argument("--software-version")
    init.add_argument("--compute-platform")

    sub.add_parser("audit", help="Audit global/local state and locked hashes")

    transition = sub.add_parser("transition", help="Change only the verified global state")
    transition.add_argument("--to-state", required=True, choices=GLOBAL_STATES)
    transition.add_argument("--actor", required=True)
    transition.add_argument("--task")
    transition.add_argument("--user-confirmed", action="store_true")
    transition.add_argument("--confirmation-note")

    route = sub.add_parser("route", help="Classify a request and report the nearest dependency")
    route.add_argument("--request", required=True)

    register = sub.add_parser("register", help="Allocate a unique provenance ID and append version 1")
    register.add_argument("--kind", required=True, choices=sorted(REGISTRY_FILES))
    register.add_argument("--subtype", required=True)
    register.add_argument("--record", required=True, help="JSON file path or JSON object")
    register.add_argument("--status", default="DRAFT")
    register.add_argument("--notes")

    compare = sub.add_parser("compare-parameters", help="Keep planned and actual parameters separate and append a calculation version")
    compare.add_argument("--calculation-id", required=True)
    compare.add_argument("--planned", required=True)
    compare.add_argument("--actual", required=True)
    compare.add_argument("--planned-source", action="append", required=True)
    compare.add_argument("--actual-source", action="append", required=True)
    compare.add_argument("--user-confirmed", action="store_true")
    compare.add_argument("--confirmation-note")

    trace = sub.add_parser("check-traceability", help="Resolve conclusion-to-plan chains and block incomplete conclusions")
    trace.add_argument("--conclusion-id")

    pause = sub.add_parser("pause", help="Write versioned recovery context and exact next-user guidance")
    pause.add_argument("--stage", required=True)
    pause.add_argument("--task", required=True)
    pause.add_argument("--next-action", required=True)
    pause.add_argument("--required-file", action="append", default=[])
    pause.add_argument("--completed-step", action="append", default=[])
    pause.add_argument("--incomplete-step", action="append", default=[])
    pause.add_argument("--allowed-operation", action="append", default=[])
    pause.add_argument("--last-decision", required=True)
    pause.add_argument("--model-version")
    pause.add_argument("--input-version")
    pause.add_argument("--result-version")

    sub.add_parser("resume", help="Audit and read recovery context without replaying completed work")

    error = sub.add_parser("classify-error", help="Record one controlled error class and route")
    error.add_argument("--error-type", required=True, choices=sorted(ERROR_ROUTES))
    error.add_argument("--summary", required=True)
    error.add_argument("--evidence-file", action="append", default=[])
    error.add_argument("--affected-id", action="append", default=[])
    error.add_argument("--recommended-action")

    citation = sub.add_parser("citation-add", help="Append a verified or explicitly pending software/method citation record")
    citation.add_argument("--record", required=True, help="JSON file path or JSON object")

    delivery_add = sub.add_parser("delivery-add", help="Copy or externally record one reviewed deliverable without moving its source")
    delivery_add.add_argument("--source", required=True)
    delivery_add.add_argument("--category", required=True, choices=sorted(DELIVERY_CATEGORIES))
    delivery_add.add_argument("--destination")
    delivery_add.add_argument("--sharing-status", choices=["SHAREABLE", "RESTRICTED_REFERENCE_ONLY", "UNVERIFIED"], default="UNVERIFIED")
    add_common_delivery_metadata(delivery_add)

    sub.add_parser("delivery-check", help="Generate stage-5 manifests and reports without deleting files")

    delivery_accept = sub.add_parser("delivery-accept", help="Record explicit user review of a clean delivery package")
    delivery_accept.add_argument("--actor", required=True)
    delivery_accept.add_argument("--user-confirmed", action="store_true")
    delivery_accept.add_argument("--confirmation-note")

    delivery_review = sub.add_parser("delivery-review", help="Open the hash-bound delivery review gate and wait")
    delivery_review.add_argument("--title")
    delivery_review.add_argument("--start-port", type=int, default=5050)
    delivery_review.add_argument("--timeout", type=float, default=0.0)

    archive = sub.add_parser("archive", help="Archive only a user-approved ready package")
    archive.add_argument("--actor", required=True)
    archive.add_argument("--user-confirmed", action="store_true")
    archive.add_argument("--confirmation-note")

    archive_review = sub.add_parser("archive-review", help="Open the hash-bound archive review gate and wait")
    archive_review.add_argument("--title")
    archive_review.add_argument("--start-port", type=int, default=5050)
    archive_review.add_argument("--timeout", type=float, default=0.0)

    reopen = sub.add_parser("reopen", help="Create a new project version from an archived package")
    reopen.add_argument("--return-state", required=True, choices=GLOBAL_STATES)
    reopen.add_argument("--reason", required=True)
    reopen.add_argument("--affected-id", action="append", default=[])
    reopen.add_argument("--actor", required=True)
    reopen.add_argument("--user-confirmed", action="store_true")
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    try:
        root = ensure_root(args.project_root)
        commands = {
            "init": lambda: command_init(root, args),
            "audit": lambda: command_audit(root),
            "transition": lambda: command_transition(root, args),
            "route": lambda: command_route(root, args),
            "register": lambda: command_register(root, args),
            "compare-parameters": lambda: command_compare_parameters(root, args),
            "check-traceability": lambda: command_check_traceability(root, args),
            "pause": lambda: command_pause(root, args),
            "resume": lambda: command_resume(root, args),
            "classify-error": lambda: command_classify_error(root, args),
            "citation-add": lambda: command_add_citation(root, args),
            "delivery-add": lambda: command_delivery_add(root, args),
            "delivery-check": lambda: command_delivery_check(root, args),
            "delivery-accept": lambda: command_delivery_accept(root, args),
            "delivery-review": lambda: command_delivery_browser_review(root, args, False),
            "archive": lambda: command_archive(root, args),
            "archive-review": lambda: command_delivery_browser_review(root, args, True),
            "reopen": lambda: command_reopen(root, args),
        }
        result = commands[args.command]()
        print(json_dump(result), end="")
        return 0
    except ControlError as exc:
        print(json_dump({"error": str(exc), **FALSE_EXECUTION_FLAGS}), end="", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
