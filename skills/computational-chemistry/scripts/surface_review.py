#!/usr/bin/env python3
"""Gate, version, review, compare, and approve stage-2 step-1 surface designs."""

from __future__ import annotations

import argparse
import copy
import csv
import hashlib
import importlib.metadata
import importlib.util
import json
import mimetypes
import re
import shutil
import sys
import threading
import webbrowser
from datetime import datetime, timezone
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse

from review_ui.stage_gate import WAITING_FOR_REVIEW_DECISION, execute_stage_review

WAITING_FOR_SURFACE_INPUT = "WAITING_FOR_SURFACE_INPUT"
SURFACE_INPUT_RECEIVED = "SURFACE_INPUT_RECEIVED"
SURFACE_INPUT_VALIDATED = "SURFACE_INPUT_VALIDATED"
SURFACE_INPUT_NOT_AVAILABLE = "SURFACE_INPUT_NOT_AVAILABLE"
SURFACE_CANDIDATES_GENERATED = "SURFACE_CANDIDATES_GENERATED"
SURFACE_MODELS_VALIDATED = "SURFACE_MODELS_VALIDATED"
SURFACE_MODELS_SCREENED = "SURFACE_MODELS_SCREENED"
WAITING_FOR_SURFACE_REVIEW = "WAITING_FOR_SURFACE_REVIEW"
SURFACE_USER_EDITED = "SURFACE_USER_EDITED"
WAITING_FOR_SURFACE_APPROVAL = "WAITING_FOR_SURFACE_APPROVAL"
SURFACE_DESIGN_APPROVED = "SURFACE_DESIGN_APPROVED"
SURFACE_REVIEW_REJECTED = "SURFACE_REVIEW_REJECTED"

VALID_STATUSES = {
    WAITING_FOR_SURFACE_INPUT,
    SURFACE_INPUT_RECEIVED,
    SURFACE_INPUT_VALIDATED,
    SURFACE_INPUT_NOT_AVAILABLE,
    SURFACE_CANDIDATES_GENERATED,
    SURFACE_MODELS_VALIDATED,
    SURFACE_MODELS_SCREENED,
    WAITING_FOR_SURFACE_REVIEW,
    SURFACE_USER_EDITED,
    WAITING_FOR_SURFACE_APPROVAL,
    WAITING_FOR_REVIEW_DECISION,
    SURFACE_REVIEW_REJECTED,
    SURFACE_DESIGN_APPROVED,
}

MODEL_FIELDS = (
    "id",
    "name",
    "material",
    "miller_index",
    "termination",
    "stoichiometry",
    "polarity",
    "dipole_handling",
    "slab_layers",
    "slab_thickness",
    "thickness_test",
    "vacuum",
    "in_plane_supercell",
    "fixed_layers",
    "relaxed_layers",
    "defect",
    "doping",
    "functionalization",
    "spin_setting",
    "target_sites",
    "experimental_support",
    "evidence_function",
    "comparison_group",
    "downstream_uses",
    "classification",
    "retention_reason",
    "rejection_reason",
    "structure_files",
    "preview_file",
    "generation_record",
    "reasonability_checks",
    "screening",
    "scientific_weight",
    "workload_weight",
    "status",
    "user_notes",
)

SCI_COMPONENTS = ("E", "R", "U", "S", "N")
WORK_COMPONENTS = ("A", "C", "K", "D", "S", "H")
DEFAULT_SCI_COEFFICIENTS = {key: 1 / len(SCI_COMPONENTS) for key in SCI_COMPONENTS}
DEFAULT_WORK_COEFFICIENTS = {key: 1 / len(WORK_COMPONENTS) for key in WORK_COMPONENTS}
REASONABILITY_KEYS = (
    "atom_overlap",
    "short_bonds",
    "intact_fragments",
    "coordination",
    "net_charge",
    "stoichiometry",
    "polarity",
    "periodic_images",
    "vacuum",
    "bulk_like_center",
    "constraints",
    "spin",
)
COMPLETION_CHECKS = (
    "stage1_gate_passed",
    "mandatory_user_question_answered",
    "bulk_validated",
    "candidates_generated",
    "reasonability_checked",
    "duplicates_resolved",
    "screening_completed_or_not_required",
    "browser_review_generated",
)
CLASSIFICATIONS = {"core", "stability_control", "functional", "screening", "rejected"}
FORBIDDEN_RESOURCE_KEYS = {
    "estimated_runtime",
    "runtime_hours",
    "estimated_memory",
    "memory_gb",
    "estimated_storage",
    "storage_gb",
}
FORBIDDEN_RESULT_KEYS = {
    "adsorption_energy_result",
    "binding_energy_result",
    "dos_result",
    "pdos_result",
    "cohp_result",
    "bader_result",
    "qtaim_result",
    "reaction_barrier_result",
    "production_md_result",
}


class SurfaceError(RuntimeError):
    """Raise for user-correctable surface-workflow errors."""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(text, encoding="utf-8", newline="\n")
    temporary.replace(path)


def write_json(path: Path, value: Any) -> None:
    write_text(path, json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def safe_relative_path(root: Path, raw_path: str) -> Path:
    if not raw_path or Path(raw_path).is_absolute():
        raise SurfaceError(f"Expected a non-empty relative path under {root}: {raw_path!r}")
    resolved = (root / raw_path).resolve()
    try:
        resolved.relative_to(root.resolve())
    except ValueError as exc:
        raise SurfaceError(f"Path escapes the surface directory: {raw_path}") from exc
    return resolved


def asset_html_path() -> Path:
    return Path(__file__).resolve().parent.parent / "assets" / "surface_review.html"


def ensure_review_html(surface_dir: Path) -> None:
    source = asset_html_path()
    if not source.exists():
        raise SurfaceError(f"Surface review asset is missing: {source}")
    shutil.copyfile(source, surface_dir / "surface_review.html")


def status_path(surface_dir: Path) -> Path:
    return surface_dir / "surface_status.json"


def log_path(surface_dir: Path) -> Path:
    return surface_dir / "surface_change_log.json"


def version_json_path(surface_dir: Path, version: str) -> Path:
    return surface_dir / f"surface_design_{version}.json"


def version_csv_path(surface_dir: Path, version: str) -> Path:
    return surface_dir / f"surface_matrix_{version}.csv"


def version_md_path(surface_dir: Path, version: str) -> Path:
    return surface_dir / f"surface_screening_report_{version}.md"


def parse_version(version: str) -> int:
    match = re.fullmatch(r"v(\d{3,})", version or "")
    if not match:
        raise SurfaceError(f"Invalid surface-design version: {version!r}")
    return int(match.group(1))


def next_version(status: dict[str, Any]) -> str:
    return f"v{parse_version(status['latest_version']) + 1:03d}"


def load_status(surface_dir: Path) -> dict[str, Any]:
    path = status_path(surface_dir)
    if not path.exists():
        raise SurfaceError("surface_status.json is missing; run start first.")
    status = read_json(path)
    if status.get("status") not in VALID_STATUSES:
        raise SurfaceError(f"Unknown surface status: {status.get('status')!r}")
    return status


def load_design(surface_dir: Path, version: str) -> dict[str, Any]:
    path = version_json_path(surface_dir, version)
    if not path.exists():
        raise SurfaceError(f"Surface-design version does not exist: {version}")
    value = read_json(path)
    if not isinstance(value, dict):
        raise SurfaceError(f"Surface-design version {version} is not a JSON object.")
    return value


def append_log(surface_dir: Path, entry: dict[str, Any]) -> None:
    path = log_path(surface_dir)
    entries = read_json(path) if path.exists() else []
    if not isinstance(entries, list):
        raise SurfaceError("surface_change_log.json must contain a JSON list.")
    entries.append(entry)
    write_json(path, entries)


def verify_stage1(stage1_dir: Path) -> dict[str, Any]:
    required = {
        "status": stage1_dir / "stage1_status.json",
        "plan": stage1_dir / "stage1_plan_approved.json",
        "markdown": stage1_dir / "stage1_plan_approved.md",
        "approval": stage1_dir / "stage1_approval_record.json",
    }
    missing = [name for name, path in required.items() if not path.exists()]
    if missing:
        raise SurfaceError("Stage-1 approved baseline is incomplete: " + ", ".join(missing))
    status = read_json(required["status"])
    plan = read_json(required["plan"])
    approval = read_json(required["approval"])
    if status.get("status") != "APPROVED" or status.get("stage2_access") is not True:
        raise SurfaceError("Stage 1 is not APPROVED with stage2_access enabled.")
    plan_hash = sha256(required["plan"])
    recorded_hash = approval.get("approved_plan_sha256")
    if recorded_hash and recorded_hash != plan_hash:
        raise SurfaceError("Stage-1 approved-plan checksum does not match the approval record.")
    if str(status.get("project_id")) != str(plan.get("project_id")):
        raise SurfaceError("Stage-1 status and approved plan use different project IDs.")
    return {
        "project_id": plan.get("project_id"),
        "approved_version": status.get("approved_version") or approval.get("approved_plan_version"),
        "approved_plan_path": str(required["plan"].resolve()),
        "approved_plan_sha256": plan_hash,
        "approval_record_path": str(required["approval"].resolve()),
        "approval_record_sha256": sha256(required["approval"]),
        "research_goal": plan.get("research_goal"),
        "target_tasks": [
            {
                "id": task.get("id"),
                "name": task.get("name"),
                "target_parameters": task.get("target_parameters"),
                "evidence_role": task.get("evidence_role"),
            }
            for task in plan.get("tasks", [])
            if isinstance(task, dict)
        ],
    }


def detect_structure_tools() -> dict[str, dict[str, Any]]:
    tools: dict[str, dict[str, Any]] = {}
    for module_name, distribution_name in (
        ("ase", "ase"),
        ("pymatgen", "pymatgen"),
        ("spglib", "spglib"),
        ("numpy", "numpy"),
    ):
        available = importlib.util.find_spec(module_name) is not None
        version = None
        if available:
            try:
                version = importlib.metadata.version(distribution_name)
            except importlib.metadata.PackageNotFoundError:
                version = "available-version-unresolved"
        tools[module_name] = {"available": available, "version": version}
    return tools


def start(surface_dir: Path, stage1_dir: Path) -> dict[str, Any]:
    if status_path(surface_dir).exists():
        raise SurfaceError("Surface workflow already exists; start will not overwrite it.")
    gate = verify_stage1(stage1_dir.resolve())
    surface_dir.mkdir(parents=True, exist_ok=True)
    for name in (
        "bulk_reference",
        "candidate_surfaces",
        "screened_surfaces",
        "rejected_surfaces",
        "scripts",
        "previews",
    ):
        (surface_dir / name).mkdir(exist_ok=True)
    ensure_review_html(surface_dir)
    status = {
        "project_id": gate["project_id"],
        "workflow_step": "stage2_step1_surface_design",
        "status": WAITING_FOR_SURFACE_INPUT,
        "stage1_gate": gate,
        "detected_structure_tools": detect_structure_tools(),
        "current_candidate_version": None,
        "latest_version": None,
        "previous_version": None,
        "previous_valid_version": None,
        "approved_version": None,
        "validation_errors": [],
        "validation_warnings": [],
        "next_step_access": False,
        "updated_at": utc_now(),
    }
    write_json(status_path(surface_dir), status)
    write_json(
        log_path(surface_dir),
        [
            {
                "event": "SURFACE_WORKFLOW_STARTED",
                "timestamp": utc_now(),
                "status_before": None,
                "status_after": WAITING_FOR_SURFACE_INPUT,
                "stage1_approved_version": gate["approved_version"],
                "stage1_plan_sha256": gate["approved_plan_sha256"],
            }
        ],
    )
    return status


def render_proposal(summary: dict[str, Any]) -> str:
    lines = [
        "# User Surface Proposal",
        "",
        f"- Has proposal: {summary.get('user_has_surface_proposal')}",
        f"- Validation status: {summary.get('validation_status')}",
        "",
        "## User response",
        "",
        str(summary.get("user_response", "")),
        "",
        "## Proposed surface design",
        "",
        "```json",
        json.dumps(summary.get("surface_proposal", {}), ensure_ascii=False, indent=2),
        "```",
        "",
        "## Review decisions",
        "",
    ]
    for category in ("retain", "adjust", "convergence_test", "not_recommended"):
        lines.append(f"### {category}")
        lines.append("")
        values = summary.get("proposal_review", {}).get(category, []) if isinstance(summary.get("proposal_review"), dict) else []
        lines.extend([f"- {item}" for item in values] or ["- None recorded."])
        lines.append("")
    return "\n".join(lines)


def render_constraints(summary: dict[str, Any]) -> str:
    lines = [
        "# Experimental Constraints",
        "",
        f"- Has experimental constraints: {summary.get('user_has_experimental_constraints')}",
        "",
    ]
    constraints = summary.get("experimental_constraints", [])
    if isinstance(constraints, list) and constraints:
        for item in constraints:
            lines.extend(
                [
                    f"## {item.get('id', 'constraint')} — {item.get('technique', '')}",
                    "",
                    f"- Observation: {item.get('observation', '')}",
                    f"- Model implication: {item.get('model_implication', '')}",
                    f"- Confidence: {item.get('confidence', '')}",
                    f"- Conflict/uncertainty: {item.get('conflict', '')}",
                    "",
                ]
            )
    else:
        lines.append("No experimental constraints were provided.")
    conflicts = summary.get("conflicts", [])
    lines.extend(["", "## Conflicts requiring attention", ""])
    lines.extend([f"- {item}" for item in conflicts] or ["- None recorded."])
    return "\n".join(lines)


def record_input(surface_dir: Path, summary_path: Path) -> dict[str, Any]:
    status = load_status(surface_dir)
    if status["status"] not in {WAITING_FOR_SURFACE_INPUT, SURFACE_INPUT_RECEIVED}:
        raise SurfaceError("Surface input can only be recorded before candidate design.")
    summary = read_json(summary_path)
    if not isinstance(summary, dict):
        raise SurfaceError("Input summary must be a JSON object.")
    required = ("user_has_surface_proposal", "user_has_experimental_constraints", "explicitly_no_input", "validation_status")
    missing = [key for key in required if key not in summary]
    if missing:
        raise SurfaceError("Input summary is missing: " + ", ".join(missing))
    has_proposal = summary.get("user_has_surface_proposal") is True
    has_experiment = summary.get("user_has_experimental_constraints") is True
    explicit_none = summary.get("explicitly_no_input") is True
    validation = str(summary.get("validation_status"))
    if not has_proposal and not has_experiment and not explicit_none:
        raise SurfaceError("Missing input is not explicit absence; record the user's answer first.")
    if explicit_none and (has_proposal or has_experiment):
        raise SurfaceError("explicitly_no_input conflicts with supplied proposal or experiment flags.")
    if explicit_none and validation != "not_available":
        raise SurfaceError("Explicit absence requires validation_status 'not_available'.")
    if not explicit_none and validation not in {"validated", "conflict_requires_confirmation"}:
        raise SurfaceError("Provided input requires 'validated' or 'conflict_requires_confirmation'.")

    summary = copy.deepcopy(summary)
    summary["recorded_at"] = utc_now()
    summary["project_id"] = status["project_id"]
    for item in summary.get("files_read", []) if isinstance(summary.get("files_read"), list) else []:
        if not isinstance(item, dict) or not str(item.get("path", "")).strip() or not str(item.get("sha256", "")).strip():
            raise SurfaceError("Each files_read entry requires path and sha256 from an actually read file.")
    write_json(surface_dir / "user_input_summary.json", summary)
    write_text(surface_dir / "user_surface_proposal.md", render_proposal(summary))
    write_text(surface_dir / "experimental_constraints.md", render_constraints(summary))

    old = status["status"]
    if explicit_none:
        new_status = SURFACE_INPUT_NOT_AVAILABLE
    elif validation == "validated":
        append_log(
            surface_dir,
            {
                "event": "SURFACE_INPUT_RECEIVED",
                "timestamp": utc_now(),
                "status_before": old,
                "status_after": SURFACE_INPUT_RECEIVED,
            },
        )
        new_status = SURFACE_INPUT_VALIDATED
    else:
        new_status = SURFACE_INPUT_RECEIVED
    status.update({"status": new_status, "updated_at": utc_now(), "input_summary_sha256": sha256(surface_dir / "user_input_summary.json")})
    write_json(status_path(surface_dir), status)
    append_log(
        surface_dir,
        {
            "event": "SURFACE_INPUT_REVIEWED" if new_status != SURFACE_INPUT_RECEIVED else "SURFACE_INPUT_CONFLICT",
            "timestamp": utc_now(),
            "status_before": SURFACE_INPUT_RECEIVED if new_status == SURFACE_INPUT_VALIDATED else old,
            "status_after": new_status,
            "validation_status": validation,
        },
    )
    return status


def scan_forbidden_keys(value: Any, prefix: str = "") -> list[str]:
    found: list[str] = []
    if isinstance(value, dict):
        for key, child in value.items():
            path = f"{prefix}.{key}" if prefix else str(key)
            if str(key).lower() in FORBIDDEN_RESOURCE_KEYS | FORBIDDEN_RESULT_KEYS:
                found.append(path)
            found.extend(scan_forbidden_keys(child, path))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            found.extend(scan_forbidden_keys(child, f"{prefix}[{index}]"))
    return found


def coefficients(settings: dict[str, Any], key: str, components: tuple[str, ...], defaults: dict[str, float], errors: list[str]) -> dict[str, float]:
    raw = settings.get(key)
    if raw is None:
        raw = defaults.copy()
        settings[key] = raw
    if not isinstance(raw, dict):
        errors.append(f"weight_settings.{key} must be an object.")
        return defaults.copy()
    result: dict[str, float] = {}
    for component in components:
        value = raw.get(component)
        if not isinstance(value, (int, float)) or isinstance(value, bool) or value < 0:
            errors.append(f"weight_settings.{key}.{component} must be a non-negative number.")
            result[component] = defaults[component]
        else:
            result[component] = float(value)
    if abs(sum(result.values()) - 1.0) > 1e-6:
        errors.append(f"weight_settings.{key} coefficients must sum to 1.0.")
    return result


def score_weight(weight: Any, components: tuple[str, ...], coeffs: dict[str, float], path: str, errors: list[str]) -> float | None:
    if not isinstance(weight, dict):
        errors.append(f"{path} must be an object.")
        return None
    rationale = weight.get("rationale")
    values: dict[str, float] = {}
    for component in components:
        value = weight.get(component)
        if not isinstance(value, (int, float)) or isinstance(value, bool) or not 0 <= float(value) <= 100:
            errors.append(f"{path}.{component} must be between 0 and 100.")
        else:
            values[component] = float(value)
    if not isinstance(rationale, dict) or any(not str(rationale.get(component, "")).strip() for component in components):
        errors.append(f"{path}.rationale must explain {', '.join(components)} separately.")
    if len(values) == len(components):
        value = round(sum(coeffs[key] * values[key] for key in components), 2)
        weight["value"] = value
        return value
    return None


def check_record_status(value: Any) -> str:
    if isinstance(value, dict):
        return str(value.get("status", "")).strip().lower()
    return str(value).strip().lower()


def validate_file_record(surface_dir: Path, item: Any, path: str, errors: list[str], required_prefix: str | None = None) -> None:
    if not isinstance(item, dict):
        errors.append(f"{path} must be an object with path and sha256.")
        return
    relative = str(item.get("path", ""))
    if required_prefix and not relative.replace("\\", "/").startswith(required_prefix.rstrip("/") + "/"):
        errors.append(f"{path}.path must be under {required_prefix}/.")
    try:
        actual = safe_relative_path(surface_dir, relative)
    except SurfaceError as exc:
        errors.append(str(exc))
        return
    if not actual.is_file():
        errors.append(f"{path}.path does not exist: {relative}.")
        return
    recorded = str(item.get("sha256", ""))
    if not recorded:
        errors.append(f"{path}.sha256 is required.")
    elif recorded != sha256(actual):
        errors.append(f"{path}.sha256 does not match {relative}.")


def model_signature(model: dict[str, Any]) -> str:
    signature = {
        "material": model.get("material"),
        "miller": model.get("miller_index"),
        "termination": model.get("termination"),
        "supercell": model.get("in_plane_supercell"),
        "layers": model.get("slab_layers"),
        "vacuum": model.get("vacuum"),
        "defect": model.get("defect"),
        "doping": model.get("doping"),
        "functionalization": model.get("functionalization"),
        "spin": model.get("spin_setting"),
    }
    return json.dumps(signature, ensure_ascii=False, sort_keys=True)


def validate_design(surface_dir: Path, design: dict[str, Any], for_approval: bool = False) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    status = load_status(surface_dir)
    if str(design.get("project_id")) != str(status.get("project_id")):
        errors.append("project_id must match the approved stage-1 project.")
    if design.get("workflow_step") not in (None, "stage2_step1_surface_design"):
        errors.append("workflow_step must be stage2_step1_surface_design.")
    design["workflow_step"] = "stage2_step1_surface_design"
    stage1_link = design.get("stage1_link")
    if not isinstance(stage1_link, dict) or stage1_link.get("approved_plan_sha256") != status["stage1_gate"]["approved_plan_sha256"]:
        errors.append("stage1_link must match the verified approved stage-1 baseline.")
    input_ref = design.get("input_summary_ref")
    if not isinstance(input_ref, dict) or input_ref.get("sha256") != status.get("input_summary_sha256"):
        errors.append("input_summary_ref must match the recorded user input summary.")

    bulk = design.get("bulk_reference")
    if not isinstance(bulk, dict):
        errors.append("bulk_reference must be an object.")
    else:
        required_bulk = ("source_type", "source_path", "source_copy", "sha256", "composition", "space_group", "lattice_parameters", "validation_status", "validation_notes")
        missing = [key for key in required_bulk if key not in bulk]
        if missing:
            errors.append("bulk_reference is missing: " + ", ".join(missing))
        if str(bulk.get("validation_status", "")).lower() != "validated":
            errors.append("bulk_reference.validation_status must be validated.")
        if bulk.get("source_copy"):
            validate_file_record(surface_dir, {"path": bulk.get("source_copy"), "sha256": bulk.get("sha256")}, "bulk_reference", errors, "bulk_reference")

    settings = design.get("weight_settings")
    if not isinstance(settings, dict):
        settings = {}
        design["weight_settings"] = settings
    sci_coeffs = coefficients(settings, "scientific_coefficients", SCI_COMPONENTS, DEFAULT_SCI_COEFFICIENTS, errors)
    work_coeffs = coefficients(settings, "workload_coefficients", WORK_COMPONENTS, DEFAULT_WORK_COEFFICIENTS, errors)
    settings.setdefault("coefficient_reason", "Equal component weights are used only as a neutral default for within-plan comparison.")
    settings["workload_note"] = "Relative plan complexity only; never convert to runtime, memory, or storage."

    models = design.get("models")
    if not isinstance(models, list) or not models:
        errors.append("models must contain at least one candidate surface.")
        models = []
    identifiers: list[str] = []
    signatures: dict[str, list[str]] = {}
    retained_classifications: list[str] = []
    for index, model in enumerate(models):
        path = f"models[{index}]"
        if not isinstance(model, dict):
            errors.append(f"{path} must be an object.")
            continue
        missing = [key for key in MODEL_FIELDS if key not in model]
        if missing:
            errors.append(f"{path} is missing fields: {', '.join(missing)}.")
        model_id = str(model.get("id", "")).strip()
        if not model_id:
            errors.append(f"{path}.id is required.")
        identifiers.append(model_id)
        classification = str(model.get("classification", ""))
        if classification not in CLASSIFICATIONS:
            errors.append(f"{path}.classification must be one of {', '.join(sorted(CLASSIFICATIONS))}.")
        if classification != "rejected":
            retained_classifications.append(classification)
        miller = model.get("miller_index")
        if not isinstance(miller, list) or len(miller) not in {3, 4} or any(not isinstance(value, int) for value in miller):
            errors.append(f"{path}.miller_index must be a three- or four-integer list.")
        for scalar in ("name", "material", "termination", "stoichiometry", "evidence_function", "comparison_group", "status"):
            if scalar in model and not str(model.get(scalar, "")).strip():
                errors.append(f"{path}.{scalar} must not be empty.")
        for list_field in ("target_sites", "experimental_support", "downstream_uses", "structure_files"):
            if list_field in model and not isinstance(model.get(list_field), list):
                errors.append(f"{path}.{list_field} must be a list.")

        sci = score_weight(model.get("scientific_weight"), SCI_COMPONENTS, sci_coeffs, f"{path}.scientific_weight", errors)
        work = score_weight(model.get("workload_weight"), WORK_COMPONENTS, work_coeffs, f"{path}.workload_weight", errors)
        if sci is not None and work is not None:
            model["selection_priority_index"] = round(sci / (1 + 0.01 * work), 4)
            model["selection_priority_note"] = "Ordering aid only; not an automatic deletion rule."

        checks = model.get("reasonability_checks")
        if not isinstance(checks, dict):
            errors.append(f"{path}.reasonability_checks must be an object.")
        else:
            for key in REASONABILITY_KEYS:
                if key not in checks:
                    errors.append(f"{path}.reasonability_checks.{key} is required.")
                elif classification != "rejected" and check_record_status(checks[key]) not in {"passed", "not_applicable"}:
                    errors.append(f"{path}.reasonability_checks.{key} must pass or be justified not_applicable for retained models.")

        screening = model.get("screening")
        screen_status = check_record_status(screening)
        if classification != "rejected" and screen_status not in {"passed", "not_required"}:
            errors.append(f"{path}.screening must be passed or not_required for retained models.")
        if classification == "rejected" and not str(model.get("rejection_reason", "")).strip():
            errors.append(f"{path}.rejection_reason is required for rejected models.")
        if classification != "rejected" and not str(model.get("retention_reason", "")).strip():
            errors.append(f"{path}.retention_reason is required for retained models.")

        raw_files = model.get("structure_files")
        files: list[Any] = raw_files if isinstance(raw_files, list) else []
        if classification != "rejected" and not files:
            errors.append(f"{path}.structure_files must contain a generated retained structure.")
        for file_index, item in enumerate(files):
            prefix = "screened_surfaces" if classification != "rejected" else None
            validate_file_record(surface_dir, item, f"{path}.structure_files[{file_index}]", errors, prefix)

        generation = model.get("generation_record")
        if not isinstance(generation, dict):
            errors.append(f"{path}.generation_record must be an object.")
        elif classification != "rejected":
            for key in ("script_path", "script_sha256", "library", "library_version", "parameters", "manual_edits", "reproducible"):
                if key not in generation:
                    errors.append(f"{path}.generation_record.{key} is required.")
            expected_parameters = {
                "miller_index": model.get("miller_index"),
                "termination": model.get("termination"),
                "slab_layers": model.get("slab_layers"),
                "vacuum": model.get("vacuum"),
                "in_plane_supercell": model.get("in_plane_supercell"),
                "fixed_layers": model.get("fixed_layers"),
                "defect": model.get("defect"),
                "doping": model.get("doping"),
                "functionalization": model.get("functionalization"),
                "spin_setting": model.get("spin_setting"),
            }
            if generation.get("parameters") != expected_parameters:
                errors.append(f"{path}.generation_record.parameters must exactly match the current structural design fields.")
            if generation.get("script_path"):
                validate_file_record(
                    surface_dir,
                    {"path": generation.get("script_path"), "sha256": generation.get("script_sha256")},
                    f"{path}.generation_record",
                    errors,
                    "scripts",
                )
            if generation.get("reproducible") is not True:
                errors.append(f"{path}.generation_record.reproducible must be true for retained models.")

        if classification != "rejected":
            signatures.setdefault(model_signature(model), []).append(model_id)

    duplicate_ids = sorted({identifier for identifier in identifiers if identifier and identifiers.count(identifier) > 1})
    if duplicate_ids:
        errors.append("Model IDs must be unique; duplicates: " + ", ".join(duplicate_ids))
    for ids in signatures.values():
        if len(ids) > 1:
            errors.append("Retained models have duplicate design signatures: " + ", ".join(ids))
    if "functional" in retained_classifications and "stability_control" not in retained_classifications:
        warnings.append("A functional surface is retained without an explicit stability-control surface.")
    if "core" not in retained_classifications:
        errors.append("At least one retained model must be classified as core.")

    checks = design.get("workflow_checks")
    if not isinstance(checks, dict):
        errors.append("workflow_checks must be an object.")
    else:
        for key in COMPLETION_CHECKS:
            if checks.get(key) is not True:
                errors.append(f"workflow_checks.{key} must be true before review/approval.")
    duplicate_review = design.get("duplicate_review")
    if not isinstance(duplicate_review, (dict, list)):
        errors.append("duplicate_review must record matcher/results and retained representatives.")
    for path in scan_forbidden_keys(design):
        errors.append(f"Forbidden result or unsupported hardware-estimate field: {path}.")

    if for_approval:
        if errors:
            return errors, warnings
        for model in models:
            if isinstance(model, dict) and model.get("classification") != "rejected":
                preview = model.get("preview_file")
                if preview:
                    try:
                        preview_path = safe_relative_path(surface_dir, str(preview))
                        if not preview_path.is_file():
                            warnings.append(f"Preview file is missing for {model.get('id')}: {preview}")
                    except SurfaceError as exc:
                        warnings.append(str(exc))
    return errors, warnings


def design_for_version(
    source: dict[str, Any],
    version: str,
    modification_source: str,
    reason: str,
    status_before: str,
    status_after: str,
    stage1_link: dict[str, Any],
    input_summary_sha256: str,
) -> dict[str, Any]:
    design = copy.deepcopy(source)
    design["workflow_step"] = "stage2_step1_surface_design"
    design["stage1_link"] = copy.deepcopy(stage1_link)
    design["input_summary_ref"] = {"path": "user_input_summary.json", "sha256": input_summary_sha256}
    design["design_version"] = version
    design["generated_at"] = utc_now()
    design["version_record"] = {
        "version": version,
        "generated_at": design["generated_at"],
        "modification_source": modification_source,
        "modification_reason": reason,
        "modification_content": reason,
        "status_before": status_before,
        "status_after": status_after,
    }
    return design


def compact(value: Any, limit: int = 280) -> str:
    if value is None:
        return ""
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, sort_keys=True)
    text = text.replace("\n", " ")
    return text if len(text) <= limit else text[: limit - 1] + "…"


def model_rows(design: dict[str, Any]) -> list[dict[str, str]]:
    fields = [field for field in MODEL_FIELDS if field not in {"scientific_weight", "workload_weight"}]
    rows: list[dict[str, str]] = []
    for model in design.get("models", []):
        if not isinstance(model, dict):
            continue
        row = {field: compact(model.get(field), 2000) for field in fields}
        row["scientific_weight"] = compact(model.get("scientific_weight"), 2000)
        row["scientific_weight_value"] = str(model.get("scientific_weight", {}).get("value", "")) if isinstance(model.get("scientific_weight"), dict) else ""
        row["workload_weight"] = compact(model.get("workload_weight"), 2000)
        row["workload_weight_value"] = str(model.get("workload_weight", {}).get("value", "")) if isinstance(model.get("workload_weight"), dict) else ""
        row["selection_priority_index"] = str(model.get("selection_priority_index", ""))
        rows.append(row)
    return rows


def write_matrix_csv(path: Path, design: dict[str, Any]) -> None:
    rows = model_rows(design)
    headers = list(rows[0]) if rows else ["id"]
    temporary = path.with_name(path.name + ".tmp")
    temporary.parent.mkdir(parents=True, exist_ok=True)
    with temporary.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=headers)
        writer.writeheader()
        writer.writerows(rows)
    temporary.replace(path)


def markdown_table(headers: list[str], rows: list[list[Any]]) -> str:
    def cell(value: Any) -> str:
        return compact(value).replace("|", "\\|")
    lines = ["| " + " | ".join(headers) + " |", "| " + " | ".join("---" for _ in headers) + " |"]
    lines.extend("| " + " | ".join(cell(item) for item in row) + " |" for row in rows)
    return "\n".join(lines)


def render_screening_report(design: dict[str, Any]) -> str:
    bulk = design.get("bulk_reference", {}) if isinstance(design.get("bulk_reference"), dict) else {}
    lines = [
        f"# Surface Design {design.get('design_version', '')}",
        "",
        f"- Project: `{design.get('project_id', '')}`",
        f"- Stage-1 approved version: {design.get('stage1_link', {}).get('approved_version', '')}",
        f"- Generated: {design.get('generated_at', '')}",
        "",
        "## Stage-1 goal",
        "",
        "```json",
        json.dumps(design.get("stage1_link", {}).get("research_goal"), ensure_ascii=False, indent=2),
        "```",
        "",
        "## Bulk reference",
        "",
        f"- Source: {bulk.get('source_type', '')} — {bulk.get('source_path', '')}",
        f"- Copy/checksum: {bulk.get('source_copy', '')} / {bulk.get('sha256', '')}",
        f"- Composition/space group: {bulk.get('composition', '')} / {bulk.get('space_group', '')}",
        f"- Validation: {bulk.get('validation_status', '')} — {compact(bulk.get('validation_notes'))}",
        "",
        "## Candidate matrix",
        "",
        markdown_table(
            ["ID", "Name", "Facet", "Termination", "Layers", "Vacuum", "Cell", "Defect/doping/functionalization", "Spin", "Class", "Sci", "Work", "Status"],
            [
                [
                    model.get("id"), model.get("name"), model.get("miller_index"), model.get("termination"),
                    model.get("slab_layers"), model.get("vacuum"), model.get("in_plane_supercell"),
                    {"defect": model.get("defect"), "doping": model.get("doping"), "functionalization": model.get("functionalization")},
                    model.get("spin_setting"), model.get("classification"),
                    model.get("scientific_weight", {}).get("value") if isinstance(model.get("scientific_weight"), dict) else None,
                    model.get("workload_weight", {}).get("value") if isinstance(model.get("workload_weight"), dict) else None,
                    model.get("status"),
                ]
                for model in design.get("models", []) if isinstance(model, dict)
            ],
        ),
        "",
        "## Duplicate review",
        "",
        "```json",
        json.dumps(design.get("duplicate_review"), ensure_ascii=False, indent=2),
        "```",
        "",
        "## Screening summary",
        "",
        "```json",
        json.dumps(design.get("screening_summary"), ensure_ascii=False, indent=2),
        "```",
        "",
        "## Known risks",
        "",
    ]
    lines.extend([f"- {compact(item)}" for item in design.get("known_risks", [])] or ["- None recorded."])
    lines.extend(
        [
            "",
            "> This is a stage-2 step-1 surface-design record. It is not a formal adsorption, electronic-structure, bonding, reaction, or production-MD result.",
            "",
        ]
    )
    return "\n".join(lines)


def entity_map(value: Any) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    if isinstance(value, list):
        for item in value:
            if isinstance(item, dict) and str(item.get("id", "")):
                result[str(item["id"])] = item
    return result


def classify_change(path: str, kind: str, before: Any, after: Any) -> tuple[str, str, str]:
    lower = path.lower()
    if kind == "deleted" and path.startswith("models["):
        model = before if isinstance(before, dict) else {}
        classification = model.get("classification")
        support = json.dumps(model.get("experimental_support"), ensure_ascii=False).lower()
        if classification == "core" and support not in {"", "[]", "null"}:
            return "HIGH", "Deletes a primary experimentally supported surface and reduces experiment-model consistency.", "Restore it or retain an experimentally supported core alternative."
        if classification == "stability_control":
            return "HIGH", "Deletes the stability control and removes the comparison needed to test a functional high-energy surface.", "Retain a stability-control surface or explicitly abandon that comparison."
        return "MEDIUM", "Deletes a surface candidate and its distinct sites or comparison role.", "Confirm that no unique evidence or downstream model depends on it."
    if kind == "added" and path.startswith("models["):
        return "MEDIUM", "Adds a surface model, evidence opportunity, and relative workload.", "Keep it only if aligned with stage 1 and non-duplicate."
    if ".miller_index" in lower:
        return "HIGH", "Changes exposed crystallography and may alter experiment relevance and accessible sites.", "Recheck diffraction/microscopy constraints and all comparison roles."
    if ".termination" in lower:
        return "CRITICAL", "Changes coordination, charge, polarity, sites, and electronic structure at the surface.", "Rebuild and revalidate the model and all direct comparisons."
    if ".in_plane_supercell" in lower:
        return "HIGH", "Changes periodic-image separation, defect/dopant concentration, and later adsorption coverage.", "Recalculate concentrations and repeat image-interaction checks."
    if ".slab_layers" in lower or ".slab_thickness" in lower:
        return "HIGH", "Changes whether the slab center can recover bulk-like structure and electronic character.", "Repeat thickness convergence using predefined observables."
    if ".vacuum" in lower:
        return "HIGH", "Changes possible artificial interaction between periodic slabs or later adsorbates.", "Repeat vacuum convergence with energy, potential, work function, or target observables."
    if ".fixed_layers" in lower or ".relaxed_layers" in lower:
        return "MEDIUM", "Changes reconstruction freedom and preservation of the bulk-like interior.", "Recheck layer response and structural drift."
    if any(token in lower for token in (".defect", ".doping", ".functionalization")):
        return "HIGH", "Changes composition, local coordination, charge/spin, concentration, and available active sites.", "Confirm stage-1 alignment, retain a pristine control, and regenerate the structure."
    if ".spin_setting" in lower:
        return "HIGH", "Changes the accessible electronic state and energy ordering for magnetic or open-shell surfaces.", "Recheck physically meaningful magnetic alternatives and cross-model consistency."
    if any(token in lower for token in ("scientific_weight", "workload_weight", "classification", "comparison_group")):
        return "MEDIUM", "Changes model importance, relative work, or comparison role.", "Re-evaluate component rationales and retained controls."
    if path.startswith("bulk_reference"):
        return "CRITICAL", "Changes the source from which every surface is generated.", "Revalidate the bulk and regenerate all dependent structures."
    if path.startswith("stage1_link"):
        return "CRITICAL", "Attempts to alter the approved scientific baseline.", "Return to stage 1 for explicit re-approval."
    if lower.endswith("user_notes"):
        return "LOW", "Changes notes without changing model physics.", "Retain the rationale in history."
    return "LOW", "Changes a descriptive or implementation detail with limited direct scientific effect.", "Retain if validation and comparison checks pass."


def make_change(path: str, kind: str, before: Any, after: Any, reason: str) -> dict[str, Any]:
    level, impact, recommendation = classify_change(path, kind, before, after)
    return {
        "path": path,
        "kind": kind,
        "before": before,
        "after": after,
        "user_reason": reason,
        "impact_level": level,
        "impact_reason": impact,
        "recommendation": recommendation,
    }


def recursive_diff(before: Any, after: Any, path: str, reason: str, changes: list[dict[str, Any]]) -> None:
    if before == after:
        return
    if isinstance(before, dict) and isinstance(after, dict):
        for key in sorted(set(before) | set(after)):
            child = f"{path}.{key}" if path else key
            if key not in before:
                changes.append(make_change(child, "added", None, after[key], reason))
            elif key not in after:
                changes.append(make_change(child, "deleted", before[key], None, reason))
            else:
                recursive_diff(before[key], after[key], child, reason, changes)
        return
    changes.append(make_change(path, "changed", before, after, reason))


def compare_designs(before: dict[str, Any], after: dict[str, Any], reason: str) -> list[dict[str, Any]]:
    changes: list[dict[str, Any]] = []
    ignored = {"design_version", "generated_at", "version_record"}
    for key in sorted((set(before) | set(after)) - ignored):
        if key == "models":
            old = entity_map(before.get("models"))
            new = entity_map(after.get("models"))
            for model_id in sorted(set(old) | set(new)):
                path = f"models[{model_id}]"
                if model_id not in old:
                    changes.append(make_change(path, "added", None, new[model_id], reason))
                elif model_id not in new:
                    changes.append(make_change(path, "deleted", old[model_id], None, reason))
                else:
                    recursive_diff(old[model_id], new[model_id], path, reason, changes)
        elif key not in before:
            changes.append(make_change(key, "added", None, after[key], reason))
        elif key not in after:
            changes.append(make_change(key, "deleted", before[key], None, reason))
        else:
            recursive_diff(before[key], after[key], key, reason, changes)
    return changes


def weights(design: dict[str, Any]) -> dict[str, dict[str, float]]:
    result: dict[str, dict[str, float]] = {}
    for model in design.get("models", []):
        if not isinstance(model, dict):
            continue
        raw_sci = model.get("scientific_weight")
        raw_work = model.get("workload_weight")
        sci: dict[str, Any] = raw_sci if isinstance(raw_sci, dict) else {}
        work: dict[str, Any] = raw_work if isinstance(raw_work, dict) else {}
        result[str(model.get("id"))] = {"scientific": float(sci.get("value", 0)), "workload": float(work.get("value", 0))}
    return result


def overall_level(changes: list[dict[str, Any]], errors: list[str]) -> str:
    if errors or any(item["impact_level"] == "CRITICAL" for item in changes):
        return "CRITICAL"
    if any(item["impact_level"] == "HIGH" for item in changes):
        return "HIGH"
    if any(item["impact_level"] == "MEDIUM" for item in changes):
        return "MEDIUM"
    return "LOW"


def impact_messages(changes: list[dict[str, Any]]) -> list[str]:
    messages: list[str] = []
    paths = [item["path"].lower() for item in changes]
    if any("miller_index" in path for path in paths):
        messages.append("晶面变化会改变实验相关性、活性位点类型和后续吸附位点集合。")
    if any("termination" in path for path in paths):
        messages.append("终止变化会同时影响局域配位、表面电荷、极性、吸附位点和电子结构，原结果不可直接沿用。")
    if any("in_plane_supercell" in path for path in paths):
        messages.append("超胞变化会改变周期镜像距离、缺陷或掺杂浓度以及后续吸附覆盖度，从而影响吸附能可比性。")
    if any("slab_layers" in path or "slab_thickness" in path for path in paths):
        messages.append("slab 变薄可能使中心区域无法恢复体相性质，影响表面能、电荷和电子结构分析。")
    if any("vacuum" in path for path in paths):
        messages.append("真空层减小可能引入相邻周期表面或吸附物之间的非物理相互作用。")
    if any(any(token in path for token in (".defect", ".doping", ".functionalization")) for path in paths):
        messages.append("缺陷、掺杂或官能化变化会改变局域电荷、自旋、成键环境和后续机理解释，必须保留可比的基准表面。")
    if any(item["kind"] == "deleted" and isinstance(item.get("before"), dict) and item["before"].get("classification") == "stability_control" for item in changes):
        messages.append("删除稳定性对照后，无法判断功能性表面是否仅为高能特殊构型。")
    if not messages:
        messages.append("未检测到预设高影响表面参数变化；仍应依据逐项影响原因检查后续可比性。")
    return list(dict.fromkeys(messages))


def analyze(before: dict[str, Any], after: dict[str, Any], reason: str, errors: list[str], warnings: list[str]) -> dict[str, Any]:
    changes = compare_designs(before, after, reason)
    old_weights = weights(before)
    new_weights = weights(after)
    old_work = sum(item["workload"] for item in old_weights.values())
    new_work = sum(item["workload"] for item in new_weights.values())
    return {
        "generated_at": utc_now(),
        "from_version": before.get("design_version"),
        "to_version": after.get("design_version"),
        "user_modification_summary": reason,
        "changes": changes,
        "weight_changes": {"before": old_weights, "after": new_weights},
        "workload_change": {
            "model_count_before": len(before.get("models", [])),
            "model_count_after": len(after.get("models", [])),
            "relative_weight_before": round(old_work, 2),
            "relative_weight_after": round(new_work, 2),
            "relative_weight_delta": round(new_work - old_work, 2),
            "note": "Relative within-design workload only; not runtime, memory, or storage.",
        },
        "result_impacts": impact_messages(changes),
        "validation_errors": errors,
        "validation_warnings": warnings,
        "overall_impact_level": overall_level(changes, errors),
        "final_conclusion_impact": "Approval is blocked until structural errors are resolved." if errors else "User confirmation remains required after reviewing all model and downstream effects.",
    }


def render_impact(analysis: dict[str, Any]) -> str:
    rows = [
        [item.get("kind"), item.get("path"), item.get("before"), item.get("after"), item.get("user_reason"), item.get("impact_level"), item.get("impact_reason"), item.get("recommendation")]
        for item in analysis.get("changes", [])
    ]
    lines = [
        "# Surface Design Modification Impact",
        "",
        f"- Version: {analysis.get('from_version')} → {analysis.get('to_version')}",
        f"- Generated: {analysis.get('generated_at')}",
        f"- Reason: {analysis.get('user_modification_summary')}",
        f"- Overall impact: **{analysis.get('overall_impact_level')}**",
        "",
        "## Differences",
        "",
        markdown_table(["Kind", "Path", "Before", "After", "Reason", "Level", "Impact", "Recommendation"], rows) if rows else "No content difference detected.",
        "",
        "## Experimental, structural, and downstream-result effects",
        "",
    ]
    lines.extend([f"- {item}" for item in analysis.get("result_impacts", [])])
    work = analysis.get("workload_change", {})
    lines.extend(
        [
            "",
            "## Scientific and workload weights",
            "",
            f"- Models: {work.get('model_count_before')} → {work.get('model_count_after')}",
            f"- Relative workload weight: {work.get('relative_weight_before')} → {work.get('relative_weight_after')} (Δ {work.get('relative_weight_delta')})",
            f"- {work.get('note')}",
            "",
            "## Validation and risk",
            "",
        ]
    )
    lines.extend([f"- **ERROR:** {item}" for item in analysis.get("validation_errors", [])])
    lines.extend([f"- **WARNING:** {item}" for item in analysis.get("validation_warnings", [])])
    if not analysis.get("validation_errors") and not analysis.get("validation_warnings"):
        lines.append("- Structural data contract, provenance, checks, weights, and duplicate rules passed.")
    lines.extend(["", "## Final conclusion effect", "", analysis.get("final_conclusion_impact", ""), ""])
    return "\n".join(lines)


def write_version(surface_dir: Path, design: dict[str, Any], analysis: dict[str, Any] | None = None) -> None:
    version = design["design_version"]
    write_json(version_json_path(surface_dir, version), design)
    write_matrix_csv(version_csv_path(surface_dir, version), design)
    write_text(version_md_path(surface_dir, version), render_screening_report(design))
    if analysis:
        report_name = f"surface_impact_analysis_{analysis['from_version']}_to_{analysis['to_version']}.md"
        report = render_impact(analysis)
        write_text(surface_dir / report_name, report)
        write_text(surface_dir / "surface_impact_analysis.md", report)


def initialize_design(surface_dir: Path, source_path: Path) -> dict[str, Any]:
    status = load_status(surface_dir)
    if status["status"] not in {SURFACE_INPUT_VALIDATED, SURFACE_INPUT_NOT_AVAILABLE}:
        raise SurfaceError("Candidate design requires validated input or explicit input unavailability.")
    if status.get("latest_version"):
        raise SurfaceError("Surface design is already initialized; history will not be overwritten.")
    source = read_json(source_path)
    if not isinstance(source, dict):
        raise SurfaceError("Surface design source must be a JSON object.")
    source["project_id"] = status["project_id"]
    source.setdefault("workflow_checks", {})["browser_review_generated"] = True
    design = design_for_version(
        source,
        "v001",
        "SYSTEM_INITIAL_SURFACE_DESIGN",
        "Initial screened candidate surface design",
        status["status"],
        WAITING_FOR_SURFACE_REVIEW,
        status["stage1_gate"],
        status["input_summary_sha256"],
    )
    errors, warnings = validate_design(surface_dir, design)
    if errors:
        raise SurfaceError("Initial surface design validation failed:\n- " + "\n- ".join(errors))
    write_version(surface_dir, design)
    write_text(surface_dir / "surface_impact_analysis.md", "# Surface Design Modification Impact\n\nNo user modification has been submitted.\n")
    transitions = (
        (SURFACE_CANDIDATES_GENERATED, "SURFACE_CANDIDATES_GENERATED"),
        (SURFACE_MODELS_VALIDATED, "SURFACE_MODELS_VALIDATED"),
        (SURFACE_MODELS_SCREENED, "SURFACE_MODELS_SCREENED"),
        (WAITING_FOR_SURFACE_REVIEW, "SURFACE_REVIEW_READY"),
    )
    old = status["status"]
    for new_status, event in transitions:
        append_log(surface_dir, {"event": event, "timestamp": utc_now(), "version": "v001", "status_before": old, "status_after": new_status})
        old = new_status
    status.update(
        {
            "status": WAITING_FOR_SURFACE_REVIEW,
            "current_candidate_version": "v001",
            "latest_version": "v001",
            "previous_version": None,
            "previous_valid_version": "v001",
            "validation_errors": [],
            "validation_warnings": warnings,
            "updated_at": utc_now(),
            "next_step_access": False,
        }
    )
    write_json(status_path(surface_dir), status)
    return status


def manual_overrides(design: dict[str, Any]) -> dict[str, str]:
    result: dict[str, str] = {}
    for item in design.get("manual_overrides", []) if isinstance(design.get("manual_overrides"), list) else []:
        if isinstance(item, dict) and str(item.get("path", "")).strip() and str(item.get("reason", "")).strip():
            item["manual_override"] = True
            result[str(item["path"])] = str(item["reason"])
    return result


def protected_errors(before: dict[str, Any], after: dict[str, Any]) -> list[str]:
    overrides = manual_overrides(after)
    errors: list[str] = []
    immutable = ("project_id", "stage1_link", "input_summary_ref")
    correctable = ("bulk_reference.source_path", "bulk_reference.source_copy", "bulk_reference.sha256")

    def get_path(value: dict[str, Any], path: str) -> Any:
        current: Any = value
        for part in path.split("."):
            current = current.get(part) if isinstance(current, dict) else None
        return current

    for path in immutable:
        if get_path(before, path) != get_path(after, path):
            errors.append(f"Immutable upstream field {path!r} changed; return to its owning workflow instead of overriding it here.")
    for path in correctable:
        if get_path(before, path) != get_path(after, path) and path not in overrides:
            errors.append(f"Protected field {path!r} changed without a manual override reason.")
    return errors


def submit_design(surface_dir: Path, edited: dict[str, Any], reason: str, source: str = "USER_EDIT") -> dict[str, Any]:
    if not reason.strip():
        raise SurfaceError("A modification reason is required.")
    status = load_status(surface_dir)
    if status["status"] == SURFACE_DESIGN_APPROVED:
        raise SurfaceError("The approved surface baseline is immutable.")
    if not status.get("current_candidate_version"):
        raise SurfaceError("Initialize the surface design before submitting edits.")
    before_status = status["status"]
    before_version = status["current_candidate_version"]
    before = load_design(surface_dir, before_version)
    attempted_protected_errors = protected_errors(before, edited)
    version = next_version(status)
    after = design_for_version(
        edited,
        version,
        source,
        reason,
        before_status,
        WAITING_FOR_SURFACE_APPROVAL,
        status["stage1_gate"],
        status["input_summary_sha256"],
    )
    status.update({"status": SURFACE_USER_EDITED, "updated_at": utc_now(), "next_step_access": False})
    write_json(status_path(surface_dir), status)
    errors, warnings = validate_design(surface_dir, after)
    errors.extend(attempted_protected_errors)
    errors.extend(protected_errors(before, after))
    analysis = analyze(before, after, reason, errors, warnings)
    after["version_record"]["modification_content"] = [{"kind": item["kind"], "path": item["path"]} for item in analysis["changes"]]
    after["version_record"]["impact_summary"] = {
        "overall_impact_level": analysis["overall_impact_level"],
        "result_impacts": analysis["result_impacts"],
        "validation_errors": errors,
    }
    write_version(surface_dir, after, analysis)
    status.update(
        {
            "status": WAITING_FOR_SURFACE_APPROVAL,
            "current_candidate_version": version,
            "latest_version": version,
            "previous_version": before_version,
            "previous_valid_version": before_version if not status.get("validation_errors") else status.get("previous_valid_version", before_version),
            "validation_errors": errors,
            "validation_warnings": warnings,
            "last_impact_level": analysis["overall_impact_level"],
            "last_impact_report": f"surface_impact_analysis_{before_version}_to_{version}.md",
            "updated_at": utc_now(),
            "next_step_access": False,
        }
    )
    write_json(status_path(surface_dir), status)
    append_log(
        surface_dir,
        {
            "event": "SURFACE_MODIFICATION_ANALYZED",
            "timestamp": utc_now(),
            "version": version,
            "previous_version": before_version,
            "source": source,
            "reason": reason,
            "changes": [{"kind": item["kind"], "path": item["path"], "impact_level": item["impact_level"]} for item in analysis["changes"]],
            "status_before": SURFACE_USER_EDITED,
            "status_after": WAITING_FOR_SURFACE_APPROVAL,
        },
    )
    return {"status": status, "analysis": analysis}


def approve(surface_dir: Path, confirmed_by: str, reason: str) -> dict[str, Any]:
    status = load_status(surface_dir)
    if status["status"] not in {WAITING_FOR_SURFACE_REVIEW, WAITING_FOR_SURFACE_APPROVAL}:
        raise SurfaceError("Surface approval requires a reviewed initial or impact-analyzed candidate.")
    if status.get("validation_errors"):
        raise SurfaceError("Resolve validation errors before surface approval.")
    targets = [
        surface_dir / "surface_design_approved.json",
        surface_dir / "surface_design_approved.csv",
        surface_dir / "surface_design_approved.md",
        surface_dir / "surface_approval_record.json",
    ]
    if any(path.exists() for path in targets):
        raise SurfaceError("Approved surface baseline files already exist and will not be overwritten.")
    version = status["current_candidate_version"]
    design = load_design(surface_dir, version)
    errors, warnings = validate_design(surface_dir, design, for_approval=True)
    required_artifacts = [
        "user_input_summary.json",
        "user_surface_proposal.md",
        "experimental_constraints.md",
        "surface_review.html",
        "surface_change_log.json",
        "surface_impact_analysis.md",
        f"surface_matrix_{version}.csv",
        f"surface_screening_report_{version}.md",
    ]
    missing = [name for name in required_artifacts if not (surface_dir / name).exists()]
    if missing:
        errors.append("Missing surface-review artifacts: " + ", ".join(missing))
    if errors:
        raise SurfaceError("Surface approval validation failed:\n- " + "\n- ".join(errors))
    write_json(targets[0], design)
    write_matrix_csv(targets[1], design)
    write_text(targets[2], render_screening_report(design))
    retained = [model for model in design.get("models", []) if isinstance(model, dict) and model.get("classification") != "rejected"]
    rejected = [model for model in design.get("models", []) if isinstance(model, dict) and model.get("classification") == "rejected"]
    record = {
        "project_id": design.get("project_id"),
        "workflow_step": "stage2_step1_surface_design",
        "approved_version": version,
        "confirmed_at": utc_now(),
        "confirmed_by": confirmed_by or "user",
        "confirmation_reason": reason,
        "user_confirmation_status": "CONFIRMED",
        "stage1_approved_version": design.get("stage1_link", {}).get("approved_version"),
        "stage1_plan_sha256": design.get("stage1_link", {}).get("approved_plan_sha256"),
        "bulk_structure_source": design.get("bulk_reference"),
        "core_facets": [model.get("miller_index") for model in retained if model.get("classification") == "core"],
        "terminations": {str(model.get("id")): model.get("termination") for model in retained},
        "slab_layers": {str(model.get("id")): model.get("slab_layers") for model in retained},
        "vacuum": {str(model.get("id")): model.get("vacuum") for model in retained},
        "supercells": {str(model.get("id")): model.get("in_plane_supercell") for model in retained},
        "fixed_layers": {str(model.get("id")): model.get("fixed_layers") for model in retained},
        "defects": {str(model.get("id")): model.get("defect") for model in retained},
        "doping": {str(model.get("id")): model.get("doping") for model in retained},
        "functionalization": {str(model.get("id")): model.get("functionalization") for model in retained},
        "spin_settings": {str(model.get("id")): model.get("spin_setting") for model in retained},
        "retained_models": [{"id": model.get("id"), "name": model.get("name"), "classification": model.get("classification")} for model in retained],
        "rejected_models": [{"id": model.get("id"), "name": model.get("name"), "reason": model.get("rejection_reason")} for model in rejected],
        "experimental_basis": design.get("experimental_constraints"),
        "theoretical_assumptions": design.get("design_assumptions"),
        "known_risks": design.get("known_risks"),
        "structure_and_generator_checksums": {
            str(model.get("id")): {
                "structures": model.get("structure_files"),
                "generator": {
                    "path": model.get("generation_record", {}).get("script_path"),
                    "sha256": model.get("generation_record", {}).get("script_sha256"),
                },
            }
            for model in retained
        },
        "validation_warnings": warnings,
        "approved_design_sha256": sha256(targets[0]),
    }
    write_json(targets[3], record)
    old = status["status"]
    status.update(
        {
            "status": SURFACE_DESIGN_APPROVED,
            "approved_version": version,
            "approved_at": record["confirmed_at"],
            "updated_at": record["confirmed_at"],
            "next_step_access": True,
            "validation_errors": [],
        }
    )
    write_json(status_path(surface_dir), status)
    append_log(surface_dir, {"event": "SURFACE_DESIGN_APPROVED", "timestamp": record["confirmed_at"], "version": version, "confirmed_by": confirmed_by or "user", "reason": reason, "status_before": old, "status_after": SURFACE_DESIGN_APPROVED})
    return {"status": status, "approval_record": record}


def transition(surface_dir: Path, action: str, reason: str = "", version: str | None = None, confirmed_by: str = "user") -> dict[str, Any]:
    status = load_status(surface_dir)
    if status["status"] == SURFACE_DESIGN_APPROVED:
        raise SurfaceError("The approved surface baseline is immutable.")
    if action in {"accept", "approve"}:
        raise SurfaceError("Surface approval must be submitted through the hash-bound browser review command.")
    if action == "continue":
        if status["status"] not in {WAITING_FOR_SURFACE_REVIEW, WAITING_FOR_SURFACE_APPROVAL}:
            raise SurfaceError("Continue editing is unavailable in the current state.")
        old = status["status"]
        status.update({"status": WAITING_FOR_SURFACE_REVIEW, "updated_at": utc_now(), "next_step_access": False})
        event = "SURFACE_CONTINUE_EDITING"
    elif action == "reject":
        if status["status"] != WAITING_FOR_SURFACE_APPROVAL:
            raise SurfaceError("Reject is allowed only after modification impact analysis.")
        fallback = status.get("previous_valid_version") or status.get("previous_version")
        if not fallback:
            raise SurfaceError("No previous valid surface version is available.")
        rejected = status["current_candidate_version"]
        old = status["status"]
        status.update({"status": WAITING_FOR_SURFACE_REVIEW, "rejected_version": rejected, "current_candidate_version": fallback, "validation_errors": [], "updated_at": utc_now(), "next_step_access": False})
        event = "SURFACE_MODIFICATION_REJECTED"
    elif action == "restore":
        target = version or status.get("previous_version")
        if not target:
            raise SurfaceError("No surface version was supplied for restoration.")
        source_design = load_design(surface_dir, target)
        result = submit_design(surface_dir, source_design, reason or f"Restore {target}", "RESTORE")
        append_log(surface_dir, {"event": "SURFACE_VERSION_RESTORED_AS_NEW", "timestamp": utc_now(), "source_version": target, "new_version": result["status"]["current_candidate_version"], "reason": reason or f"Restore {target}", "status_after": WAITING_FOR_SURFACE_APPROVAL})
        return result
    else:
        raise SurfaceError(f"Unknown action: {action}")
    write_json(status_path(surface_dir), status)
    append_log(surface_dir, {"event": event, "timestamp": utc_now(), "version": status.get("current_candidate_version"), "reason": reason, "status_before": old, "status_after": status["status"]})
    return {"status": status}


def browser_review(
    surface_dir: Path,
    project_dir: Path,
    title: str,
    start_port: int,
    timeout_seconds: float | None,
) -> dict[str, Any]:
    status = load_status(surface_dir)
    version = status.get("current_candidate_version")
    if not version:
        raise SurfaceError("No surface candidate is available for browser review.")
    return execute_stage_review(
        project_dir=project_dir,
        stage_dir=surface_dir,
        stage="stage2_step1_surface",
        title=title,
        content_file=version_json_path(surface_dir, str(version)),
        allowed_statuses={WAITING_FOR_SURFACE_REVIEW, WAITING_FOR_SURFACE_APPROVAL},
        revision_status=WAITING_FOR_SURFACE_REVIEW,
        rejected_status=SURFACE_REVIEW_REJECTED,
        load_status=lambda: load_status(surface_dir),
        save_status=lambda value: write_json(status_path(surface_dir), value),
        append_log=lambda value: append_log(surface_dir, value),
        approve=lambda comment: approve(surface_dir, "browser_user", comment),
        error_type=SurfaceError,
        blocked_access_updates={"next_step_access": False},
        revision_updates={"next_step_access": False},
        rejected_updates={"next_step_access": False},
        start_port=start_port,
        timeout_seconds=timeout_seconds,
    )


def current_data(surface_dir: Path) -> dict[str, Any]:
    status = load_status(surface_dir)
    current = load_design(surface_dir, status["current_candidate_version"]) if status.get("current_candidate_version") else None
    previous = load_design(surface_dir, status["previous_version"]) if status.get("previous_version") else None
    analysis = None
    if current and previous:
        reason = current.get("version_record", {}).get("modification_reason", "")
        analysis = analyze(previous, current, reason, status.get("validation_errors", []), status.get("validation_warnings", []))
    input_summary = read_json(surface_dir / "user_input_summary.json") if (surface_dir / "user_input_summary.json").exists() else None
    return {
        "status": status,
        "design": current,
        "input_summary": input_summary,
        "versions": sorted(path.stem.replace("surface_design_", "") for path in surface_dir.glob("surface_design_v*.json")),
        "change_log": read_json(log_path(surface_dir)),
        "analysis": analysis,
    }


class SurfaceHandler(BaseHTTPRequestHandler):
    surface_dir: Path

    def log_message(self, format_string: str, *args: Any) -> None:
        sys.stderr.write("[surface-review] " + format_string % args + "\n")

    def send_json(self, payload: Any, status: HTTPStatus = HTTPStatus.OK) -> None:
        encoded = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status.value)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(encoded)

    def send_file(self, path: Path, content_type: str | None = None) -> None:
        encoded = path.read_bytes()
        self.send_response(HTTPStatus.OK.value)
        self.send_header("Content-Type", content_type or mimetypes.guess_type(path.name)[0] or "application/octet-stream")
        self.send_header("Content-Length", str(len(encoded)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(encoded)

    def body(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0"))
        if length <= 0 or length > 8 * 1024 * 1024:
            raise SurfaceError("Request body must be between 1 byte and 8 MiB.")
        value = json.loads(self.rfile.read(length).decode("utf-8"))
        if not isinstance(value, dict):
            raise SurfaceError("Request body must be a JSON object.")
        return value

    def do_GET(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
        try:
            if path in {"/", "/surface_review.html"}:
                self.send_file(self.surface_dir / "surface_review.html", "text/html; charset=utf-8")
            elif path == "/api/state":
                self.send_json(current_data(self.surface_dir))
            elif path.startswith("/previews/"):
                relative = "previews/" + unquote(path[len("/previews/"):])
                preview = safe_relative_path(self.surface_dir, relative)
                if not preview.is_file():
                    self.send_json({"error": "Preview not found"}, HTTPStatus.NOT_FOUND)
                else:
                    self.send_file(preview)
            else:
                self.send_json({"error": "Not found"}, HTTPStatus.NOT_FOUND)
        except (SurfaceError, OSError, ValueError, json.JSONDecodeError) as exc:
            self.send_json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)

    def do_POST(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
        try:
            payload = self.body()
            if path == "/api/submit":
                design = payload.get("design")
                if not isinstance(design, dict):
                    raise SurfaceError("design must be a JSON object.")
                result = submit_design(self.surface_dir, design, str(payload.get("reason", "")))
            elif path == "/api/action":
                result = transition(
                    self.surface_dir,
                    str(payload.get("action", "")),
                    str(payload.get("reason", "")),
                    str(payload["version"]) if payload.get("version") else None,
                    str(payload.get("confirmed_by", "user")),
                )
            else:
                self.send_json({"error": "Not found"}, HTTPStatus.NOT_FOUND)
                return
            self.send_json({"ok": True, "result": result})
        except (SurfaceError, OSError, ValueError, json.JSONDecodeError) as exc:
            self.send_json({"ok": False, "error": str(exc)}, HTTPStatus.BAD_REQUEST)


def serve(surface_dir: Path, host: str, port: int, open_page: bool) -> None:
    ensure_review_html(surface_dir)
    handler = type("BoundSurfaceHandler", (SurfaceHandler,), {"surface_dir": surface_dir})
    server = ThreadingHTTPServer((host, port), handler)
    address = f"http://{host}:{server.server_address[1]}/"
    print(f"Surface review page: {address}", flush=True)
    print("Press Ctrl+C to stop the local review service.", flush=True)
    if open_page:
        threading.Timer(0.4, lambda: webbrowser.open(address)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    start_parser = subparsers.add_parser("start", help="Verify stage 1 and initialize WAITING_FOR_SURFACE_INPUT.")
    start_parser.add_argument("--stage1-planning-dir", type=Path, required=True)
    start_parser.add_argument("--surface-dir", type=Path, default=Path("surface_design"))

    input_parser = subparsers.add_parser("input", help="Record and validate the user's proposal/experimental input.")
    input_parser.add_argument("--surface-dir", type=Path, default=Path("surface_design"))
    input_parser.add_argument("--summary", type=Path, required=True)

    init_parser = subparsers.add_parser("init-design", help="Create immutable v001 after candidate screening.")
    init_parser.add_argument("--surface-dir", type=Path, default=Path("surface_design"))
    init_parser.add_argument("--design", type=Path, required=True)

    validate_parser = subparsers.add_parser("validate", help="Validate and score a surface-design JSON.")
    validate_parser.add_argument("--surface-dir", type=Path, default=Path("surface_design"))
    validate_parser.add_argument("--design", type=Path, required=True)
    validate_parser.add_argument("--for-approval", action="store_true")

    submit_parser = subparsers.add_parser("submit", help="Create a new immutable version and analyze impact.")
    submit_parser.add_argument("--surface-dir", type=Path, default=Path("surface_design"))
    submit_parser.add_argument("--edited-design", type=Path, required=True)
    submit_parser.add_argument("--reason", required=True)

    action_parser = subparsers.add_parser("action", help="Accept, continue, restore, or reject a design.")
    action_parser.add_argument("--surface-dir", type=Path, default=Path("surface_design"))
    action_parser.add_argument("--name", choices=("accept", "approve", "continue", "restore", "reject"), required=True)
    action_parser.add_argument("--reason", default="")
    action_parser.add_argument("--version")
    action_parser.add_argument("--confirmed-by", default="user")

    serve_parser = subparsers.add_parser("serve", help="Serve and optionally open the browser review page.")
    serve_parser.add_argument("--surface-dir", type=Path, default=Path("surface_design"))
    serve_parser.add_argument("--host", default="127.0.0.1")
    serve_parser.add_argument("--port", type=int, default=8766)
    serve_parser.add_argument("--open", action="store_true", dest="open_page")

    review_parser = subparsers.add_parser("review", help="Open the hash-bound Flask review gate and wait for a decision.")
    review_parser.add_argument("--surface-dir", type=Path, default=Path("surface_design"))
    review_parser.add_argument("--project-dir", type=Path)
    review_parser.add_argument("--title", default="第二阶段第一步：材料表面设计审查")
    review_parser.add_argument("--start-port", type=int, default=5050)
    review_parser.add_argument("--timeout", type=float, default=0.0)

    subparsers.add_parser("environment", help="Report detected structure-tool availability and versions.")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    result: dict[str, Any]
    try:
        if args.command == "environment":
            result = detect_structure_tools()
        elif args.command == "start":
            result = start(args.surface_dir.resolve(), args.stage1_planning_dir.resolve())
        elif args.command == "input":
            result = record_input(args.surface_dir.resolve(), args.summary.resolve())
        elif args.command == "init-design":
            result = initialize_design(args.surface_dir.resolve(), args.design.resolve())
        elif args.command == "validate":
            design = read_json(args.design.resolve())
            if not isinstance(design, dict):
                raise SurfaceError("Design must be a JSON object.")
            errors, warnings = validate_design(args.surface_dir.resolve(), design, args.for_approval)
            result = {"valid": not errors, "errors": errors, "warnings": warnings}
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return 0 if not errors else 1
        elif args.command == "submit":
            edited = read_json(args.edited_design.resolve())
            if not isinstance(edited, dict):
                raise SurfaceError("Edited design must be a JSON object.")
            result = submit_design(args.surface_dir.resolve(), edited, args.reason)
        elif args.command == "action":
            result = transition(args.surface_dir.resolve(), args.name, args.reason, args.version, args.confirmed_by)
        elif args.command == "serve":
            serve(args.surface_dir.resolve(), args.host, args.port, args.open_page)
            return 0
        elif args.command == "review":
            surface_dir = args.surface_dir.resolve()
            project_dir = args.project_dir.resolve() if args.project_dir else surface_dir.parent
            result = browser_review(surface_dir, project_dir, args.title, args.start_port, args.timeout)
        else:
            raise SurfaceError(f"Unsupported command: {args.command}")
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (SurfaceError, OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
