#!/usr/bin/env python3
"""Manage stage-2-step-2 interface selection, file generation, review, and approval.

This program only reads/writes structures and text artifacts. It never launches a
scientific executable, MPI process, scheduler command, queue query, or generated script.
"""

from __future__ import annotations

import argparse
import base64
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
from contextlib import suppress
from datetime import datetime, timezone
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse

from review_ui.stage_gate import WAITING_FOR_REVIEW_DECISION, execute_stage_review

WAITING_FOR_INTERFACE_SELECTION = "WAITING_FOR_INTERFACE_SELECTION"
INTERFACE_SURFACES_SELECTED = "INTERFACE_SURFACES_SELECTED"
LATTICE_MATCHING_COMPLETED = "LATTICE_MATCHING_COMPLETED"
INTERFACE_CANDIDATES_GENERATED = "INTERFACE_CANDIDATES_GENERATED"
INTERFACE_MODELS_VALIDATED = "INTERFACE_MODELS_VALIDATED"
CALCULATION_INPUTS_GENERATED = "CALCULATION_INPUTS_GENERATED"
HPC_SCRIPTS_GENERATED = "HPC_SCRIPTS_GENERATED"
STATIC_VALIDATION_COMPLETED = "STATIC_VALIDATION_COMPLETED"
WAITING_FOR_INTERFACE_FILE_APPROVAL = "WAITING_FOR_INTERFACE_FILE_APPROVAL"
INTERFACE_FILES_APPROVED = "INTERFACE_FILES_APPROVED"
INTERFACE_REVIEW_REJECTED = "INTERFACE_REVIEW_REJECTED"

VALID_STATUSES = {
    WAITING_FOR_INTERFACE_SELECTION,
    INTERFACE_SURFACES_SELECTED,
    LATTICE_MATCHING_COMPLETED,
    INTERFACE_CANDIDATES_GENERATED,
    INTERFACE_MODELS_VALIDATED,
    CALCULATION_INPUTS_GENERATED,
    HPC_SCRIPTS_GENERATED,
    STATIC_VALIDATION_COMPLETED,
    WAITING_FOR_INTERFACE_FILE_APPROVAL,
    WAITING_FOR_REVIEW_DECISION,
    INTERFACE_REVIEW_REJECTED,
    INTERFACE_FILES_APPROVED,
}

COMPLETION_CHECKS = (
    "stage1_gate_passed",
    "surface_gate_passed",
    "user_selection_confirmed",
    "interface_type_identified",
    "software_compatible",
    "lattice_matching_completed_or_not_applicable",
    "candidates_generated",
    "duplicates_resolved",
    "geometry_static_checks_passed",
    "calculation_inputs_generated",
    "component_references_generated_or_not_required",
    "hpc_or_local_scripts_generated",
    "static_validation_completed",
    "browser_review_generated",
)

GEOMETRY_CHECKS = (
    "component_identity",
    "atom_overlap",
    "short_bonds",
    "component_penetration",
    "ligand_integrity",
    "vacuum_direction",
    "strain",
    "charge",
    "spin",
    "fixed_region",
    "provenance",
)

FILE_GROUP_ROOTS = {
    "calculation_inputs": "calculation_inputs_{version}",
    "reference_components": "reference_components_{version}",
    "hpc_scripts": "hpc_scripts_{version}",
    "local_run_scripts": "local_run_scripts_{version}",
    "dependencies": "dependencies_{version}",
    "generation_scripts": "scripts/generated_{version}",
}

FORBIDDEN_RESOURCE_KEYS = {
    "estimated_runtime",
    "runtime_hours",
    "estimated_memory",
    "memory_gb_estimate",
    "estimated_storage",
    "storage_gb",
    "optimal_resources",
    "predicted_queue_time",
}

FORBIDDEN_RESULT_KEYS = {
    "optimized_structure",
    "optimized_geometry",
    "total_energy_result",
    "interface_energy_result",
    "binding_energy_result",
    "equilibrium_distance_result",
    "convergence_result",
    "charge_transfer_result",
    "dos_result",
    "pdos_result",
    "cohp_result",
    "bader_result",
    "qtaim_result",
    "reaction_barrier_result",
}

FORBIDDEN_STATUS_VALUES = {
    "INTERFACE_OPTIMIZATION_RUNNING",
    "INTERFACE_OPTIMIZATION_COMPLETED",
    "CALCULATION_RUNNING",
    "CALCULATION_COMPLETED",
    "JOB_SUBMITTED",
}

PERIODIC_TYPES = {
    "crystal_crystal",
    "2d_2d",
    "mof_inorganic",
    "mof_polymer_periodic",
    "polymer_inorganic_periodic",
}
CLUSTER_TYPES = {"finite_cluster", "cluster_cluster", "mof_polymer_cluster", "polymer_inorganic_cluster"}
ADSORPTION_TYPES = {"molecule_surface", "adsorption"}

SOFTWARE_ALIASES = {
    "quantumespresso": "quantum_espresso",
    "qe": "quantum_espresso",
    "pwx": "quantum_espresso",
    "cp2k": "cp2k",
    "gaussian": "gaussian",
    "g16": "gaussian",
    "g09": "gaussian",
    "orca": "orca",
    "gromacs": "gromacs",
    "vasp": "vasp",
    "lammps": "lammps",
    "multiwfn": "multiwfn",
    "lobster": "lobster",
}


class InterfaceError(RuntimeError):
    """Raise for user-correctable interface-workflow errors."""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_bytes(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_bytes(content)
    temporary.replace(path)


def write_text(path: Path, content: str) -> None:
    write_bytes(path, content.replace("\r\n", "\n").encode("utf-8"))


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
        raise InterfaceError(f"Expected a non-empty relative path under {root}: {raw_path!r}")
    resolved = (root / raw_path).resolve()
    try:
        resolved.relative_to(root.resolve())
    except ValueError as exc:
        raise InterfaceError(f"Path escapes the interface directory: {raw_path}") from exc
    return resolved


def safe_upstream_path(root: Path, raw_path: str) -> Path:
    if not raw_path or Path(raw_path).is_absolute():
        raise InterfaceError(f"Expected a relative upstream path under {root}: {raw_path!r}")
    resolved = (root / raw_path).resolve()
    try:
        resolved.relative_to(root.resolve())
    except ValueError as exc:
        raise InterfaceError(f"Upstream path escapes its approved directory: {raw_path}") from exc
    return resolved


def safe_name(value: str) -> str:
    name = re.sub(r"[^A-Za-z0-9._-]+", "_", value.strip())
    return name.strip("._") or "artifact"


def normalize_software(value: Any) -> str:
    compact = re.sub(r"[^a-z0-9]+", "", str(value).lower())
    return SOFTWARE_ALIASES.get(compact, compact)


def status_path(interface_dir: Path) -> Path:
    return interface_dir / "interface_status.json"


def log_path(interface_dir: Path) -> Path:
    return interface_dir / "interface_change_log.json"


def version_json_path(interface_dir: Path, version: str) -> Path:
    return interface_dir / f"interface_candidates_{version}.json"


def version_csv_path(interface_dir: Path, version: str) -> Path:
    return interface_dir / f"interface_matrix_{version}.csv"


def version_parameters_path(interface_dir: Path, version: str) -> Path:
    return interface_dir / f"optimization_parameters_{version}.json"


def version_input_report_path(interface_dir: Path, version: str) -> Path:
    return interface_dir / f"input_generation_report_{version}.md"


def version_static_report_path(interface_dir: Path, version: str) -> Path:
    return interface_dir / f"static_validation_report_{version}.md"


def parse_version(version: str) -> int:
    match = re.fullmatch(r"v(\d{3,})", version or "")
    if not match:
        raise InterfaceError(f"Invalid interface version: {version!r}")
    return int(match.group(1))


def next_version(interface_dir: Path, status: dict[str, Any]) -> str:
    numbers: list[int] = []
    for path in interface_dir.glob("interface_candidates_v*.json"):
        with suppress(InterfaceError):
            numbers.append(parse_version(path.stem.replace("interface_candidates_", "")))
    if status.get("latest_version"):
        numbers.append(parse_version(str(status["latest_version"])))
    return f"v{max(numbers, default=0) + 1:03d}"


def load_status(interface_dir: Path) -> dict[str, Any]:
    path = status_path(interface_dir)
    if not path.exists():
        raise InterfaceError("interface_status.json is missing; run start first.")
    status = read_json(path)
    if not isinstance(status, dict) or status.get("status") not in VALID_STATUSES:
        raise InterfaceError(f"Unknown interface status: {status.get('status')!r}")
    return status


def load_design(interface_dir: Path, version: str) -> dict[str, Any]:
    path = version_json_path(interface_dir, version)
    if not path.exists():
        raise InterfaceError(f"Interface version does not exist: {version}")
    design = read_json(path)
    if not isinstance(design, dict):
        raise InterfaceError(f"Interface version {version} is not an object.")
    return design


def append_log(interface_dir: Path, entry: dict[str, Any]) -> None:
    path = log_path(interface_dir)
    entries = read_json(path) if path.exists() else []
    if not isinstance(entries, list):
        raise InterfaceError("interface_change_log.json must contain a list.")
    entries.append(entry)
    write_json(path, entries)


def detect_structure_tools() -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for module, distribution in (("ase", "ase"), ("pymatgen", "pymatgen"), ("spglib", "spglib"), ("numpy", "numpy")):
        available = importlib.util.find_spec(module) is not None
        version = None
        if available:
            try:
                version = importlib.metadata.version(distribution)
            except importlib.metadata.PackageNotFoundError:
                version = "available-version-unresolved"
        result[module] = {"available": available, "version": version}
    return result


def approved_software_records(plan: dict[str, Any]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for task in plan.get("tasks", []) if isinstance(plan.get("tasks"), list) else []:
        if not isinstance(task, dict) or str(task.get("status", "")).lower() in {"deleted", "rejected"}:
            continue
        software = task.get("software")
        if str(software or "").strip():
            records.append(
                {
                    "task_id": task.get("id"),
                    "task_name": task.get("name"),
                    "software": software,
                    "normalized_software": normalize_software(software),
                    "module": task.get("module"),
                    "method": task.get("method"),
                    "target_parameters": task.get("target_parameters"),
                    "evidence_role": task.get("evidence_role"),
                }
            )
    return records


def frozen_file_record(path: Path) -> dict[str, str]:
    return {"path": str(path.resolve()), "sha256": sha256(path)}


def verify_stage1(stage1_dir: Path) -> dict[str, Any]:
    paths = {
        "status": stage1_dir / "stage1_status.json",
        "plan": stage1_dir / "stage1_plan_approved.json",
        "markdown": stage1_dir / "stage1_plan_approved.md",
        "approval": stage1_dir / "stage1_approval_record.json",
    }
    missing = [name for name, path in paths.items() if not path.is_file()]
    if missing:
        raise InterfaceError("Stage-1 approved baseline is incomplete: " + ", ".join(missing))
    status = read_json(paths["status"])
    plan = read_json(paths["plan"])
    approval = read_json(paths["approval"])
    if status.get("status") != "APPROVED" or status.get("stage2_access") is not True:
        raise InterfaceError("Stage 1 is not APPROVED with stage2_access enabled.")
    plan_hash = sha256(paths["plan"])
    if approval.get("approved_plan_sha256") and approval.get("approved_plan_sha256") != plan_hash:
        raise InterfaceError("Stage-1 approved plan checksum does not match its approval record.")
    if str(status.get("project_id")) != str(plan.get("project_id")):
        raise InterfaceError("Stage-1 status and approved plan use different project IDs.")
    software = approved_software_records(plan)
    if not software:
        raise InterfaceError("Stage-1 approved plan contains no retained task with an explicit software choice.")
    return {
        "project_id": plan.get("project_id"),
        "approved_version": status.get("approved_version") or approval.get("approved_plan_version"),
        "files": {name: frozen_file_record(path) for name, path in paths.items()},
        "research_goal": plan.get("research_goal"),
        "approved_software_records": software,
        "method_snapshot": [
            {
                "id": task.get("id"),
                "software": task.get("software"),
                "module": task.get("module"),
                "method": task.get("method"),
                "target_parameters": task.get("target_parameters"),
                "evidence_role": task.get("evidence_role"),
            }
            for task in plan.get("tasks", [])
            if isinstance(task, dict) and str(task.get("status", "")).lower() not in {"deleted", "rejected"}
        ],
    }


def verify_surface(surface_dir: Path, project_id: Any) -> dict[str, Any]:
    paths = {
        "status": surface_dir / "surface_status.json",
        "design": surface_dir / "surface_design_approved.json",
        "markdown": surface_dir / "surface_design_approved.md",
        "approval": surface_dir / "surface_approval_record.json",
    }
    missing = [name for name, path in paths.items() if not path.is_file()]
    if missing:
        raise InterfaceError("Approved surface baseline is incomplete: " + ", ".join(missing))
    status = read_json(paths["status"])
    design = read_json(paths["design"])
    approval = read_json(paths["approval"])
    if status.get("status") != "SURFACE_DESIGN_APPROVED" or status.get("next_step_access") is not True:
        raise InterfaceError("Surface design is not SURFACE_DESIGN_APPROVED with next-step access enabled.")
    if str(status.get("project_id")) != str(project_id) or str(design.get("project_id")) != str(project_id):
        raise InterfaceError("Stage-1 and surface baselines use different project IDs.")
    design_hash = sha256(paths["design"])
    if approval.get("approved_design_sha256") and approval.get("approved_design_sha256") != design_hash:
        raise InterfaceError("Approved surface checksum does not match its approval record.")
    models: list[dict[str, Any]] = []
    for model in design.get("models", []) if isinstance(design.get("models"), list) else []:
        if not isinstance(model, dict) or model.get("classification") == "rejected":
            continue
        structure_records = []
        for record in model.get("structure_files", []) if isinstance(model.get("structure_files"), list) else []:
            if not isinstance(record, dict):
                raise InterfaceError(f"Approved surface {model.get('id')} has an invalid structure record.")
            actual = safe_upstream_path(surface_dir, str(record.get("path", "")))
            if not actual.is_file() or sha256(actual) != str(record.get("sha256", "")):
                raise InterfaceError(f"Approved surface structure is missing or changed: {record.get('path')}")
            structure_records.append(copy.deepcopy(record))
        if not structure_records:
            raise InterfaceError(f"Approved surface {model.get('id')} has no real structure file.")
        snapshot = copy.deepcopy(model)
        snapshot["structure_files"] = structure_records
        models.append(snapshot)
    if len(models) < 2:
        raise InterfaceError("At least two retained approved surface records are required for interface selection.")
    return {
        "project_id": project_id,
        "approved_version": status.get("approved_version") or approval.get("approved_version"),
        "surface_dir": str(surface_dir.resolve()),
        "files": {name: frozen_file_record(path) for name, path in paths.items()},
        "models": models,
    }


def verify_frozen_gates(status: dict[str, Any]) -> None:
    for gate_name in ("stage1_gate", "surface_gate"):
        gate = status.get(gate_name)
        if not isinstance(gate, dict):
            raise InterfaceError(f"Frozen {gate_name} record is missing.")
        for label, record in gate.get("files", {}).items():
            path = Path(str(record.get("path", "")))
            if not path.is_file() or sha256(path) != str(record.get("sha256", "")):
                raise InterfaceError(f"Frozen upstream file changed or disappeared: {gate_name}.{label}")
    stage1_status = read_json(Path(status["stage1_gate"]["files"]["status"]["path"]))
    surface_status = read_json(Path(status["surface_gate"]["files"]["status"]["path"]))
    if stage1_status.get("status") != "APPROVED" or stage1_status.get("stage2_access") is not True:
        raise InterfaceError("Stage-1 approval gate is no longer valid.")
    if surface_status.get("status") != "SURFACE_DESIGN_APPROVED" or surface_status.get("next_step_access") is not True:
        raise InterfaceError("Surface approval gate is no longer valid.")


def review_asset_path() -> Path:
    return Path(__file__).resolve().parent.parent / "assets" / "interface_review.html"


def ensure_review_html(interface_dir: Path) -> None:
    source = review_asset_path()
    if not source.is_file():
        raise InterfaceError(f"Interface review asset is missing: {source}")
    shutil.copyfile(source, interface_dir / "interface_review.html")


def start(interface_dir: Path, stage1_dir: Path, surface_dir: Path) -> dict[str, Any]:
    if status_path(interface_dir).exists():
        raise InterfaceError("Interface workflow already exists; start will not overwrite it.")
    stage1_gate = verify_stage1(stage1_dir.resolve())
    surface_gate = verify_surface(surface_dir.resolve(), stage1_gate["project_id"])
    interface_dir.mkdir(parents=True, exist_ok=True)
    for name in (
        "selected_surfaces",
        "user_interface_proposal",
        "lattice_matching",
        "candidate_interfaces",
        "approved_interfaces",
        "reference_components",
        "calculation_inputs/prescreen",
        "calculation_inputs/formal_optimization",
        "hpc_scripts/slurm",
        "hpc_scripts/pbs",
        "hpc_scripts/lsf",
        "local_run_scripts",
        "dependencies",
        "previews",
        "validation",
        "scripts",
    ):
        (interface_dir / name).mkdir(parents=True, exist_ok=True)
    ensure_review_html(interface_dir)
    status = {
        "project_id": stage1_gate["project_id"],
        "workflow_step": "stage2_step2_interface_files",
        "status": WAITING_FOR_INTERFACE_SELECTION,
        "stage1_gate": stage1_gate,
        "surface_gate": surface_gate,
        "detected_structure_tools": detect_structure_tools(),
        "current_candidate_version": None,
        "latest_version": None,
        "previous_version": None,
        "previous_valid_version": None,
        "approved_version": None,
        "validation_errors": [],
        "validation_warnings": [],
        "calculation_executed": False,
        "job_submitted": False,
        "user_execution_files_ready": False,
        "updated_at": utc_now(),
    }
    write_json(status_path(interface_dir), status)
    write_json(
        log_path(interface_dir),
        [{
            "event": "INTERFACE_FILE_WORKFLOW_STARTED",
            "timestamp": utc_now(),
            "status_before": None,
            "status_after": WAITING_FOR_INTERFACE_SELECTION,
            "stage1_version": stage1_gate["approved_version"],
            "surface_version": surface_gate["approved_version"],
        }],
    )
    return status


def model_by_id(status: dict[str, Any], model_id: str) -> dict[str, Any]:
    for model in status["surface_gate"].get("models", []):
        if str(model.get("id")) == model_id:
            return model
    raise InterfaceError(f"Surface ID is not retained in the approved baseline: {model_id}")


def copy_selected_model(interface_dir: Path, status: dict[str, Any], role: str, model: dict[str, Any]) -> list[dict[str, Any]]:
    surface_root = Path(status["surface_gate"]["surface_dir"])
    copied: list[dict[str, Any]] = []
    for index, record in enumerate(model.get("structure_files", []), start=1):
        source = safe_upstream_path(surface_root, str(record.get("path", "")))
        if sha256(source) != str(record.get("sha256", "")):
            raise InterfaceError(f"Selected surface checksum changed: {record.get('path')}")
        destination = interface_dir / "selected_surfaces" / f"{role}_{safe_name(str(model.get('id')))}_{index}_{safe_name(source.name)}"
        if destination.exists():
            if sha256(destination) != sha256(source):
                raise InterfaceError(f"Selected-surface copy conflicts with existing file: {destination.name}")
        else:
            shutil.copyfile(source, destination)
        copied.append({"path": destination.relative_to(interface_dir).as_posix(), "sha256": sha256(destination), "upstream_path": record.get("path")})
    return copied


def surface_snapshot(interface_dir: Path, status: dict[str, Any], role: str, model_id: str) -> dict[str, Any]:
    model = model_by_id(status, model_id)
    return {
        "id": model.get("id"),
        "name": model.get("name"),
        "material": model.get("material"),
        "miller_index": model.get("miller_index"),
        "termination": model.get("termination"),
        "in_plane_supercell": model.get("in_plane_supercell"),
        "slab_layers": model.get("slab_layers"),
        "fixed_layers": model.get("fixed_layers"),
        "defect": model.get("defect"),
        "doping": model.get("doping"),
        "functionalization": model.get("functionalization"),
        "spin_setting": model.get("spin_setting"),
        "surface_design_version": status["surface_gate"].get("approved_version"),
        "approved_structure_files": copy.deepcopy(model.get("structure_files")),
        "copied_structure_files": copy_selected_model(interface_dir, status, role, model),
    }


def ingest_proposal_files(interface_dir: Path, selection: dict[str, Any]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for item in selection.get("user_proposal_files", []) if isinstance(selection.get("user_proposal_files"), list) else []:
        if not isinstance(item, dict) or not str(item.get("source_path", "")).strip():
            raise InterfaceError("Each user_proposal_files item requires source_path.")
        source = Path(str(item["source_path"])).expanduser().resolve()
        if not source.is_file():
            raise InterfaceError(f"User proposal file does not exist: {source}")
        destination = interface_dir / "user_interface_proposal" / safe_name(str(item.get("name") or source.name))
        if destination.exists():
            raise InterfaceError(f"User proposal destination already exists: {destination.name}")
        shutil.copyfile(source, destination)
        records.append({"path": destination.relative_to(interface_dir).as_posix(), "sha256": sha256(destination), "source_path": str(source), "label": item.get("label")})
    for item in selection.get("uploaded_files", []) if isinstance(selection.get("uploaded_files"), list) else []:
        if not isinstance(item, dict) or not str(item.get("name", "")).strip() or not str(item.get("content_base64", "")).strip():
            raise InterfaceError("Each uploaded file requires name and content_base64.")
        try:
            content = base64.b64decode(str(item["content_base64"]), validate=True)
        except ValueError as exc:
            raise InterfaceError(f"Invalid base64 upload: {item.get('name')}") from exc
        destination = interface_dir / "user_interface_proposal" / safe_name(str(item["name"]))
        if destination.exists():
            raise InterfaceError(f"Uploaded proposal destination already exists: {destination.name}")
        write_bytes(destination, content)
        records.append({"path": destination.relative_to(interface_dir).as_posix(), "sha256": sha256(destination), "source": "browser_upload"})
    return records


def normalize_selection(interface_dir: Path, status: dict[str, Any], raw: dict[str, Any], include_proposals: bool = False) -> dict[str, Any]:
    lower_id = str(raw.get("lower_surface_id", "")).strip()
    upper_id = str(raw.get("upper_surface_id", "")).strip()
    if not lower_id or not upper_id:
        raise InterfaceError("The user must select both lower_surface_id and upper_surface_id.")
    if raw.get("user_selected") is not True or raw.get("order_confirmed") is not True:
        raise InterfaceError("Selection requires user_selected: true and order_confirmed: true.")
    if lower_id == upper_id and (
        raw.get("allow_same_surface") is not True
        or not str(raw.get("same_surface_rationale", "")).strip()
    ):
        raise InterfaceError("Selecting the same surface twice requires allow_same_surface and a rationale.")
    selection = {
        "lower_surface_id": lower_id,
        "upper_surface_id": upper_id,
        "user_selected": True,
        "order_confirmed": True,
        "order_rationale": str(raw.get("order_rationale", "")).strip(),
        "allow_same_surface": bool(raw.get("allow_same_surface", False)),
        "same_surface_rationale": str(raw.get("same_surface_rationale", "")).strip(),
        "user_notes": raw.get("user_notes", ""),
        "lower_surface": surface_snapshot(interface_dir, status, "lower", lower_id),
        "upper_surface": surface_snapshot(interface_dir, status, "upper", upper_id),
        "recorded_at": utc_now(),
    }
    selection["user_proposal_files"] = ingest_proposal_files(interface_dir, raw) if include_proposals else copy.deepcopy(raw.get("user_proposal_files", []))
    return selection


def record_selection(interface_dir: Path, selection_path: Path | None = None, selection_value: dict[str, Any] | None = None) -> dict[str, Any]:
    status = load_status(interface_dir)
    verify_frozen_gates(status)
    if status["status"] != WAITING_FOR_INTERFACE_SELECTION:
        raise InterfaceError("Initial selection is allowed only in WAITING_FOR_INTERFACE_SELECTION.")
    target = interface_dir / "interface_selection.json"
    if target.exists():
        raise InterfaceError("interface_selection.json already exists and will not be overwritten.")
    raw = selection_value if selection_value is not None else read_json(selection_path.resolve()) if selection_path else None
    if not isinstance(raw, dict):
        raise InterfaceError("Selection must be a JSON object.")
    selection = normalize_selection(interface_dir, status, raw, include_proposals=True)
    write_json(target, selection)
    old = status["status"]
    status.update({"status": INTERFACE_SURFACES_SELECTED, "selection_sha256": sha256(target), "selection_review_confirmed": False, "updated_at": utc_now()})
    write_json(status_path(interface_dir), status)
    append_log(interface_dir, {"event": "INTERFACE_SURFACES_SELECTED", "timestamp": utc_now(), "status_before": old, "status_after": INTERFACE_SURFACES_SELECTED, "lower_surface_id": selection["lower_surface_id"], "upper_surface_id": selection["upper_surface_id"]})
    return {"status": status, "selection": selection}


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


def scan_forbidden_statuses(value: Any, prefix: str = "") -> list[str]:
    found: list[str] = []
    if isinstance(value, dict):
        for key, child in value.items():
            path = f"{prefix}.{key}" if prefix else str(key)
            found.extend(scan_forbidden_statuses(child, path))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            found.extend(scan_forbidden_statuses(child, f"{prefix}[{index}]"))
    elif isinstance(value, str) and value.upper() in FORBIDDEN_STATUS_VALUES:
        found.append(prefix)
    return found


def check_status(value: Any) -> str:
    if isinstance(value, dict):
        return str(value.get("status", "")).strip().lower()
    return str(value).strip().lower()


def validate_file_record(interface_dir: Path, record: Any, path: str, errors: list[str], required_prefix: str | None = None) -> None:
    if not isinstance(record, dict):
        errors.append(f"{path} must be an object with path and sha256.")
        return
    relative = str(record.get("path", ""))
    if required_prefix and not relative.replace("\\", "/").startswith(required_prefix.rstrip("/") + "/"):
        errors.append(f"{path}.path must be under {required_prefix}/.")
    try:
        actual = safe_relative_path(interface_dir, relative)
    except InterfaceError as exc:
        errors.append(str(exc))
        return
    if not actual.is_file():
        errors.append(f"{path}.path does not exist: {relative}.")
        return
    if not str(record.get("sha256", "")):
        errors.append(f"{path}.sha256 is required.")
    elif sha256(actual) != str(record["sha256"]):
        errors.append(f"{path}.sha256 does not match {relative}.")


def numeric(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def matrix_2x2(value: Any, integers: bool = False) -> bool:
    if not isinstance(value, list) or len(value) != 2:
        return False
    for row in value:
        if not isinstance(row, list) or len(row) != 2:
            return False
        for item in row:
            if integers:
                if not isinstance(item, int) or isinstance(item, bool):
                    return False
            elif not numeric(item):
                return False
    return True


def group_root(interface_dir: Path, group: str, version: str) -> Path:
    if group not in FILE_GROUP_ROOTS:
        raise InterfaceError(f"Unknown file-spec group: {group}")
    return interface_dir / FILE_GROUP_ROOTS[group].format(version=version)


def materialize_file_specs(interface_dir: Path, design: dict[str, Any], version: str) -> dict[str, list[dict[str, Any]]]:
    specs = design.get("file_specs")
    if not isinstance(specs, dict):
        raise InterfaceError("file_specs must be an object grouped by artifact type.")
    artifacts: dict[str, list[dict[str, Any]]] = {}
    planned_roots = [group_root(interface_dir, group, version) for group, items in specs.items() if isinstance(items, list) and items]
    conflict = next((path for path in planned_roots if path.exists()), None)
    if conflict:
        raise InterfaceError(f"Versioned artifact directory already exists and will not be overwritten: {conflict}")
    for group, items in specs.items():
        if group not in FILE_GROUP_ROOTS:
            raise InterfaceError(f"Unsupported file_specs group: {group}")
        if not isinstance(items, list):
            raise InterfaceError(f"file_specs.{group} must be a list.")
        records: list[dict[str, Any]] = []
        root = group_root(interface_dir, group, version)
        for index, item in enumerate(items):
            if not isinstance(item, dict):
                raise InterfaceError(f"file_specs.{group}[{index}] must be an object.")
            relative = str(item.get("path", ""))
            target = safe_relative_path(root, relative)
            if target.exists():
                raise InterfaceError(f"Generated artifact already exists and will not be overwritten: {target}")
            if "content" in item:
                if not isinstance(item["content"], str):
                    raise InterfaceError(f"file_specs.{group}[{index}].content must be text.")
                write_text(target, item["content"])
            elif "content_base64" in item:
                try:
                    write_bytes(target, base64.b64decode(str(item["content_base64"]), validate=True))
                except ValueError as exc:
                    raise InterfaceError(f"Invalid base64 content in file_specs.{group}[{index}].") from exc
            else:
                raise InterfaceError(f"file_specs.{group}[{index}] requires content or content_base64.")
            record = {
                "path": target.relative_to(interface_dir).as_posix(),
                "sha256": sha256(target),
                "size_bytes": target.stat().st_size,
                "role": item.get("role"),
                "source": item.get("source"),
                "software": item.get("software"),
                "module": item.get("module"),
                "package_id": item.get("package_id"),
                "candidate_id": item.get("candidate_id"),
                "logical_name": item.get("logical_name"),
            }
            records.append(record)
        artifacts[group] = records
    for group in FILE_GROUP_ROOTS:
        artifacts.setdefault(group, [])
    return artifacts


def input_token_errors(path: Path, software: str, role: str) -> list[str]:
    if path.suffix.lower() in {".cif", ".xyz", ".pdb", ".poscar", ".vasp", ".gro", ".top", ".itp", ".ndx"}:
        return []
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return []
    upper = text.upper()
    errors: list[str] = []
    if software == "quantum_espresso" and path.suffix.lower() in {".in", ".pwi"}:
        for token in ("&CONTROL", "&SYSTEM", "&ELECTRONS", "ATOMIC_SPECIES", "ATOMIC_POSITIONS", "CELL_PARAMETERS", "K_POINTS"):
            if token not in upper:
                errors.append(f"{path.name} is missing Quantum ESPRESSO token {token}.")
        if "CALCULATION" not in upper or ("'RELAX'" not in upper and '"RELAX"' not in upper and "'VC-RELAX'" not in upper and '"VC-RELAX"' not in upper):
            errors.append(f"{path.name} must explicitly select relax or a justified vc-relax.")
    elif software == "cp2k" and path.suffix.lower() in {".inp", ".in"}:
        for token in ("&GLOBAL", "&FORCE_EVAL", "&DFT", "&SUBSYS", "&SCF", "&MGRID", "&XC", "&MOTION"):
            if token not in upper:
                errors.append(f"{path.name} is missing CP2K section {token}.")
    elif software == "gaussian" and path.suffix.lower() in {".gjf", ".com"}:
        if not any(line.lstrip().startswith("#") for line in text.splitlines()):
            errors.append(f"{path.name} is missing a Gaussian route line.")
        if not re.search(r"(?m)^\s*-?\d+\s+\d+\s*$", text):
            errors.append(f"{path.name} is missing a charge/multiplicity line.")
    elif software == "orca" and path.suffix.lower() == ".inp":
        if "!" not in text or not re.search(r"(?im)^\s*\*\s+XYZ\s+-?\d+\s+\d+", text):
            errors.append(f"{path.name} is missing ORCA method or xyz charge/multiplicity syntax.")
    elif software == "gromacs" and path.suffix.lower() == ".mdp":
        if not re.search(r"(?im)^\s*integrator\s*=", text):
            errors.append(f"{path.name} is missing a GROMACS integrator setting.")
    if not text.strip():
        errors.append(f"{path.name} is empty ({role}).")
    return errors


def expected_generation_parameters(candidate: dict[str, Any]) -> dict[str, Any]:
    return {
        "lower_surface_id": candidate.get("lower_surface_id"),
        "upper_surface_id": candidate.get("upper_surface_id"),
        "match_id": candidate.get("match_id"),
        "translation_fractional": candidate.get("translation_fractional"),
        "rotation_deg": candidate.get("rotation_deg"),
        "initial_interface_distance": candidate.get("initial_interface_distance"),
        "fixed_region": candidate.get("fixed_region"),
        "relaxed_region": candidate.get("relaxed_region"),
        "vacuum": candidate.get("vacuum"),
        "boundary_conditions": candidate.get("boundary_conditions"),
        "spin_setting": candidate.get("spin_setting"),
    }


def candidate_signature(candidate: dict[str, Any]) -> str:
    value = {
        "lower": candidate.get("lower_surface_id"),
        "upper": candidate.get("upper_surface_id"),
        "match": candidate.get("match_id"),
        "translation": candidate.get("translation_fractional"),
        "rotation": candidate.get("rotation_deg"),
        "distance": candidate.get("initial_interface_distance"),
        "contacts": candidate.get("target_contact_pairs"),
        "spin": candidate.get("spin_setting"),
    }
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def coordinate_design_fingerprint(design: dict[str, Any]) -> str:
    candidates = []
    for candidate in design.get("candidates", []) if isinstance(design.get("candidates"), list) else []:
        if not isinstance(candidate, dict):
            continue
        candidates.append(
            {
                "id": candidate.get("id"),
                "match_id": candidate.get("match_id"),
                "lower_surface_id": candidate.get("lower_surface_id"),
                "upper_surface_id": candidate.get("upper_surface_id"),
                "translation_fractional": candidate.get("translation_fractional"),
                "rotation_deg": candidate.get("rotation_deg"),
                "initial_interface_distance": candidate.get("initial_interface_distance"),
                "target_contact_pairs": candidate.get("target_contact_pairs"),
                "vacuum": candidate.get("vacuum"),
                "boundary_conditions": candidate.get("boundary_conditions"),
            }
        )
    value = {
        "selection": {key: design.get("selection", {}).get(key) for key in ("lower_surface_id", "upper_surface_id")},
        "interface_type": design.get("interface_type"),
        "lattice_matches": design.get("lattice_matches"),
        "candidates": candidates,
    }
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def structural_regeneration_errors(before: dict[str, Any] | None, after: dict[str, Any], version: str) -> list[str]:
    if before is not None and coordinate_design_fingerprint(before) == coordinate_design_fingerprint(after):
        return []
    errors: list[str] = []
    before_candidates = {str(item.get("id")): item for item in before.get("candidates", []) if isinstance(item, dict)} if before else {}
    for candidate in after.get("candidates", []) if isinstance(after.get("candidates"), list) else []:
        if not isinstance(candidate, dict) or candidate.get("classification") == "rejected":
            continue
        candidate_id = str(candidate.get("id"))
        raw_generation = candidate.get("generation_record")
        generation: dict[str, Any] = raw_generation if isinstance(raw_generation, dict) else {}
        if generation.get("generated_for_version") != version:
            errors.append(f"Structural candidate {candidate_id} must record generation_record.generated_for_version = {version} after a coordinate-affecting change.")
        raw_files = candidate.get("structure_files")
        files: list[Any] = raw_files if isinstance(raw_files, list) else []
        if files and any(version.lower() not in Path(str(item.get("path", ""))).stem.lower() for item in files if isinstance(item, dict)):
            errors.append(f"Structural candidate {candidate_id} must use a traceable {version} structure filename after a coordinate-affecting change.")
        previous = before_candidates.get(candidate_id)
        if previous is not None and previous.get("structure_files") == files:
            errors.append(f"Structural candidate {candidate_id} changed construction fields but reused the previous structure record.")
    return errors


def clone_restored_structures(interface_dir: Path, design: dict[str, Any], version: str) -> None:
    for candidate in design.get("candidates", []) if isinstance(design.get("candidates"), list) else []:
        if not isinstance(candidate, dict) or candidate.get("classification") == "rejected":
            continue
        restored: list[dict[str, Any]] = []
        for index, record in enumerate(candidate.get("structure_files", []) if isinstance(candidate.get("structure_files"), list) else [], start=1):
            source = safe_relative_path(interface_dir, str(record.get("path", "")))
            if not source.is_file() or sha256(source) != str(record.get("sha256", "")):
                raise InterfaceError(f"Historical structure cannot be restored because it is missing or changed: {record.get('path')}")
            stem = re.sub(r"_v\d{3,}$", "", source.stem, flags=re.IGNORECASE)
            destination = interface_dir / "candidate_interfaces" / f"{safe_name(str(candidate.get('id')))}_{index}_{safe_name(stem)}_{version}{source.suffix}"
            if destination.exists():
                raise InterfaceError(f"Restored structure target already exists: {destination}")
            shutil.copyfile(source, destination)
            restored.append({"path": destination.relative_to(interface_dir).as_posix(), "sha256": sha256(destination), "restored_from": record.get("path")})
        candidate["structure_files"] = restored
        name = str(candidate.get("name", ""))
        candidate["name"] = re.sub(r"_v\d{3,}$", "", name, flags=re.IGNORECASE) + f"_{version}"
        generation = candidate.get("generation_record")
        if isinstance(generation, dict):
            generation["generated_for_version"] = version
            generation["restored_from_version"] = design.get("interface_version")


def validate_design(interface_dir: Path, design: dict[str, Any], for_approval: bool = False) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    status = load_status(interface_dir)
    try:
        verify_frozen_gates(status)
    except InterfaceError as exc:
        errors.append(str(exc))
    if str(design.get("project_id")) != str(status.get("project_id")):
        errors.append("project_id must match both approved upstream baselines.")
    if design.get("workflow_step") != "stage2_step2_interface_files":
        errors.append("workflow_step must be stage2_step2_interface_files.")
    if design.get("stage1_link") != status.get("stage1_gate"):
        errors.append("stage1_link must equal the engine-owned frozen stage-1 gate.")
    if design.get("surface_link") != status.get("surface_gate"):
        errors.append("surface_link must equal the engine-owned frozen surface gate.")

    selection = design.get("selection")
    if not isinstance(selection, dict):
        errors.append("selection must be an engine-normalized object.")
        selection = {}
    lower_id = str(selection.get("lower_surface_id", ""))
    upper_id = str(selection.get("upper_surface_id", ""))
    if selection.get("user_selected") is not True or selection.get("order_confirmed") is not True:
        errors.append("selection must record explicit user selection and order confirmation.")
    try:
        lower_model = model_by_id(status, lower_id)
        upper_model = model_by_id(status, upper_id)
    except InterfaceError as exc:
        errors.append(str(exc))
        lower_model = {}
        upper_model = {}
    for role, snapshot, approved in (("lower", selection.get("lower_surface"), lower_model), ("upper", selection.get("upper_surface"), upper_model)):
        if not isinstance(snapshot, dict):
            errors.append(f"selection.{role}_surface must be an approved-model snapshot.")
            continue
        for key in ("id", "material", "miller_index", "termination", "in_plane_supercell", "slab_layers", "fixed_layers", "defect", "doping", "functionalization", "spin_setting"):
            if snapshot.get(key) != approved.get(key):
                errors.append(f"selection.{role}_surface.{key} differs from the approved surface baseline.")
        for index, record in enumerate(snapshot.get("copied_structure_files", []) if isinstance(snapshot.get("copied_structure_files"), list) else []):
            validate_file_record(interface_dir, record, f"selection.{role}_surface.copied_structure_files[{index}]", errors, "selected_surfaces")

    interface_type = design.get("interface_type")
    if not isinstance(interface_type, dict):
        errors.append("interface_type must be an object.")
        interface_type = {}
    for key in ("category", "periodicity", "model_form", "interface_count", "vacuum_required", "rationale"):
        if key not in interface_type:
            errors.append(f"interface_type.{key} is required.")
    category = str(interface_type.get("category", "")).lower()
    if category in ADSORPTION_TYPES:
        errors.append("A molecule-surface system must be routed to the adsorption workflow, not this interface-matching step.")
    model_form = str(interface_type.get("model_form", ""))
    if model_form not in {"single_interface_vacuum", "symmetric_double_interface", "periodic_superlattice", "finite_cluster_interface"}:
        errors.append("interface_type.model_form is not a supported explicit interface form.")

    compatibility = design.get("software_compatibility")
    if not isinstance(compatibility, dict):
        errors.append("software_compatibility must be an object.")
        compatibility = {}
    software = normalize_software(compatibility.get("software"))
    approved_records = status["stage1_gate"].get("approved_software_records", [])
    approved_for_software = [item for item in approved_records if item.get("normalized_software") == software]
    if not software or not approved_for_software:
        errors.append("software_compatibility.software must match an explicit retained stage-1 software choice.")
    approved_task_ids = compatibility.get("approved_task_ids")
    if not isinstance(approved_task_ids, list) or not approved_task_ids:
        errors.append("software_compatibility.approved_task_ids must link the relevant stage-1 tasks.")
    elif any(task_id not in {item.get("task_id") for item in approved_for_software} for task_id in approved_task_ids):
        errors.append("software_compatibility.approved_task_ids contains a task not approved for the selected software.")
    if compatibility.get("interface_supported") is not True or not str(compatibility.get("rationale", "")).strip():
        errors.append("software compatibility requires interface_supported: true and a rationale.")
    if software in {"multiwfn", "lobster"}:
        errors.append(f"{software} is an analysis tool and cannot be the interface optimizer.")
    if category in PERIODIC_TYPES and software in {"gaussian", "orca"}:
        errors.append("Gaussian/ORCA cannot be used for a complete periodic interface in this workflow.")
    if category in CLUSTER_TYPES and software in {"quantum_espresso", "vasp"}:
        errors.append("The selected periodic-only input route is incompatible with the declared finite cluster.")
    if software in {"gromacs", "lammps"} and compatibility.get("force_field_parameters_complete") is not True:
        errors.append(f"Formal {software} interface files require complete component and cross-interaction parameters.")

    matches = design.get("lattice_matches")
    if not isinstance(matches, list) or not matches:
        errors.append("lattice_matches must contain a retained match or a justified nonperiodic record.")
        matches = []
    match_ids: list[str] = []
    retained_matches: set[str] = set()
    for index, match in enumerate(matches):
        path = f"lattice_matches[{index}]"
        if not isinstance(match, dict):
            errors.append(f"{path} must be an object.")
            continue
        match_id = str(match.get("id", "")).strip()
        if not match_id:
            errors.append(f"{path}.id is required.")
        match_ids.append(match_id)
        match_status = str(match.get("status", "")).lower()
        if match_status in {"retained", "selected", "passed"}:
            retained_matches.add(match_id)
        if category in PERIODIC_TYPES:
            if not matrix_2x2(match.get("surface_a_supercell"), integers=True) or not matrix_2x2(match.get("surface_b_supercell"), integers=True):
                errors.append(f"{path} requires two 2x2 integer surface supercell matrices.")
            lattice = match.get("matched_lattice")
            if not isinstance(lattice, list) or len(lattice) != 2 or any(not isinstance(v, list) or len(v) not in {2, 3} or any(not numeric(x) for x in v) for v in lattice):
                errors.append(f"{path}.matched_lattice must contain two numeric in-plane vectors.")
            for side in ("strain_a", "strain_b"):
                strain = match.get(side)
                if not isinstance(strain, dict) or any(not numeric(strain.get(key)) for key in ("direction_1_pct", "direction_2_pct", "angle_change_deg")):
                    errors.append(f"{path}.{side} requires two directional strains and angle change.")
            if not numeric(match.get("rotation_deg")) or not numeric(match.get("interface_area")) or not isinstance(match.get("atom_count"), int):
                errors.append(f"{path} requires numeric rotation, area, and integer atom count.")
            distribution = match.get("strain_distribution")
            if not isinstance(distribution, dict) or distribution.get("mode") not in {"a_only", "b_only", "shared", "substrate_fixed", "weighted"} or not str(distribution.get("rationale", "")).strip():
                errors.append(f"{path}.strain_distribution requires an explicit mode and rationale.")
        elif check_status(match) not in {"not_applicable", "retained", "selected", "passed"}:
            errors.append(f"{path} must justify a nonperiodic not_applicable match.")
    duplicate_match_ids = sorted({item for item in match_ids if item and match_ids.count(item) > 1})
    if duplicate_match_ids:
        errors.append("Lattice-match IDs must be unique: " + ", ".join(duplicate_match_ids))
    if not retained_matches and category in PERIODIC_TYPES:
        errors.append("At least one periodic lattice match must be retained.")

    candidates = design.get("candidates")
    if not isinstance(candidates, list) or not candidates:
        errors.append("candidates must contain at least one real interface candidate.")
        candidates = []
    candidate_ids: list[str] = []
    retained_candidates: list[dict[str, Any]] = []
    signatures: dict[str, list[str]] = {}
    for index, candidate in enumerate(candidates):
        path = f"candidates[{index}]"
        if not isinstance(candidate, dict):
            errors.append(f"{path} must be an object.")
            continue
        required = (
            "id", "name", "match_id", "lower_surface_id", "upper_surface_id", "order",
            "translation_fractional", "rotation_deg", "initial_interface_distance", "minimum_intercomponent_distance",
            "target_contact_pairs", "interaction_types", "fixed_region", "relaxed_region", "vacuum",
            "boundary_conditions", "dipole_handling", "charge", "spin_setting", "defects_preserved",
            "doping_preserved", "functionalization_preserved", "structure_files", "generation_record",
            "geometry_checks", "duplicate_check", "classification", "retention_reason", "rejection_reason",
            "scientific_use", "downstream_tasks", "input_package_ids",
        )
        missing = [key for key in required if key not in candidate]
        if missing:
            errors.append(f"{path} is missing fields: {', '.join(missing)}.")
        candidate_id = str(candidate.get("id", "")).strip()
        candidate_ids.append(candidate_id)
        classification = str(candidate.get("classification", "")).lower()
        retained = classification != "rejected"
        if classification not in {"core", "comparison", "screening", "functional", "rejected"}:
            errors.append(f"{path}.classification is invalid.")
        if candidate.get("lower_surface_id") != lower_id or candidate.get("upper_surface_id") != upper_id:
            errors.append(f"{path} must preserve the selected lower/upper surface order.")
        if category in PERIODIC_TYPES and candidate.get("match_id") not in retained_matches:
            errors.append(f"{path}.match_id must reference a retained lattice match.")
        translation = candidate.get("translation_fractional")
        if not isinstance(translation, list) or len(translation) != 2 or any(not numeric(value) for value in translation):
            errors.append(f"{path}.translation_fractional must contain two numbers.")
        if not numeric(candidate.get("rotation_deg")):
            errors.append(f"{path}.rotation_deg must be numeric.")
        for distance_key in ("initial_interface_distance", "minimum_intercomponent_distance"):
            distance = candidate.get(distance_key)
            if not isinstance(distance, dict) or not numeric(distance.get("value")) or not str(distance.get("unit", "")).strip() or not str(distance.get("basis", "")).strip():
                errors.append(f"{path}.{distance_key} requires value, unit, and basis.")
        for preservation in ("defects_preserved", "doping_preserved", "functionalization_preserved"):
            if candidate.get(preservation) not in {True, "not_applicable"}:
                errors.append(f"{path}.{preservation} must be true or not_applicable.")
        checks = candidate.get("geometry_checks")
        if not isinstance(checks, dict):
            errors.append(f"{path}.geometry_checks must be an object.")
        else:
            for key in GEOMETRY_CHECKS:
                if retained and check_status(checks.get(key)) not in {"passed", "not_applicable"}:
                    errors.append(f"{path}.geometry_checks.{key} must pass or be justified not_applicable.")
        if retained and check_status(candidate.get("duplicate_check")) not in {"passed", "unique", "representative"}:
            errors.append(f"{path}.duplicate_check must identify a unique/representative retained structure.")
        if retained and not str(candidate.get("retention_reason", "")).strip():
            errors.append(f"{path}.retention_reason is required.")
        if not retained and not str(candidate.get("rejection_reason", "")).strip():
            errors.append(f"{path}.rejection_reason is required for rejected candidates.")
        raw_files = candidate.get("structure_files")
        files: list[Any] = raw_files if isinstance(raw_files, list) else []
        if retained and not files:
            errors.append(f"{path}.structure_files must contain a real candidate structure.")
        for file_index, record in enumerate(files):
            validate_file_record(interface_dir, record, f"{path}.structure_files[{file_index}]", errors, "candidate_interfaces")
        generation = candidate.get("generation_record")
        if not isinstance(generation, dict):
            errors.append(f"{path}.generation_record must be an object.")
        elif retained:
            for key in ("script_path", "script_sha256", "library", "library_version", "parameters", "manual_edits", "reproducible", "generated_for_version"):
                if key not in generation:
                    errors.append(f"{path}.generation_record.{key} is required.")
            if generation.get("parameters") != expected_generation_parameters(candidate):
                errors.append(f"{path}.generation_record.parameters must exactly match current construction fields.")
            validate_file_record(interface_dir, {"path": generation.get("script_path"), "sha256": generation.get("script_sha256")}, f"{path}.generation_record", errors, "scripts")
            if generation.get("reproducible") is not True:
                errors.append(f"{path}.generation_record.reproducible must be true.")
        if retained:
            retained_candidates.append(candidate)
            signatures.setdefault(candidate_signature(candidate), []).append(candidate_id)
    duplicate_candidate_ids = sorted({item for item in candidate_ids if item and candidate_ids.count(item) > 1})
    if duplicate_candidate_ids:
        errors.append("Candidate IDs must be unique: " + ", ".join(duplicate_candidate_ids))
    for ids in signatures.values():
        if len(ids) > 1:
            errors.append("Retained candidates have duplicate construction signatures: " + ", ".join(ids))
    if not retained_candidates:
        errors.append("At least one interface candidate must be retained.")

    duplicate_review = design.get("duplicate_review")
    if not isinstance(duplicate_review, dict) or duplicate_review.get("resolved") is not True:
        errors.append("duplicate_review must record a completed, resolved comparison.")
    comparison_policy = design.get("comparison_policy")
    if not isinstance(comparison_policy, dict) or not all(key in comparison_policy for key in ("cell_rule", "strain_rule", "parameter_rule", "component_reference_rule")):
        errors.append("comparison_policy must define consistent cell, strain, parameter, and component-reference rules.")

    parameters = design.get("optimization_parameters")
    if not isinstance(parameters, dict):
        errors.append("optimization_parameters must be an object.")
    else:
        for key in ("software", "module", "functional", "basis_or_pseudopotential", "dispersion", "spin", "calculation_type", "k_points", "convergence", "constraints", "boundary_conditions", "inherited_from_stage1", "interface_adjustments", "stage1_consistency"):
            if key not in parameters:
                errors.append(f"optimization_parameters.{key} is required.")
        if normalize_software(parameters.get("software")) != software:
            errors.append("optimization_parameters.software must match software_compatibility.software.")
        if parameters.get("stage1_consistency") is not True:
            errors.append("optimization_parameters.stage1_consistency must be true; revise stage 1 for method changes.")
        if not isinstance(parameters.get("interface_adjustments"), list):
            errors.append("optimization_parameters.interface_adjustments must list every model-specific adjustment and reason.")

    artifacts = design.get("generated_artifacts")
    if not isinstance(artifacts, dict):
        errors.append("generated_artifacts must be created by the engine.")
        artifacts = {}
    all_artifacts: list[dict[str, Any]] = []
    for group in FILE_GROUP_ROOTS:
        records = artifacts.get(group)
        if not isinstance(records, list):
            errors.append(f"generated_artifacts.{group} must be a list.")
            continue
        for index, record in enumerate(records):
            validate_file_record(interface_dir, record, f"generated_artifacts.{group}[{index}]", errors, FILE_GROUP_ROOTS[group].format(version=design.get("interface_version", "")))
            if isinstance(record, dict):
                all_artifacts.append(record)
                actual = safe_relative_path(interface_dir, str(record.get("path", "")))
                if actual.is_file() and group in {"calculation_inputs", "reference_components"}:
                    errors.extend(input_token_errors(actual, normalize_software(record.get("software") or software), str(record.get("role", ""))))
    if not artifacts.get("calculation_inputs"):
        errors.append("At least one calculation input file must be generated.")
    if not artifacts.get("hpc_scripts") and not artifacts.get("local_run_scripts"):
        errors.append("At least one HPC or local-run script/template must be generated.")

    packages = design.get("calculation_packages")
    if not isinstance(packages, list) or not packages:
        errors.append("calculation_packages must define generated input uses.")
        packages = []
    package_ids: list[str] = []
    package_modes: set[str] = set()
    artifact_package_ids = {str(item.get("package_id")) for item in all_artifacts if item.get("package_id")}
    for index, package in enumerate(packages):
        path = f"calculation_packages[{index}]"
        if not isinstance(package, dict):
            errors.append(f"{path} must be an object.")
            continue
        for key in ("id", "candidate_id", "mode", "software", "status", "purpose", "limitations"):
            if key not in package:
                errors.append(f"{path}.{key} is required.")
        package_id = str(package.get("id", ""))
        package_ids.append(package_id)
        mode = str(package.get("mode", ""))
        package_modes.add(mode)
        if mode not in {"prescreen", "formal_optimization", "component_reference_a", "component_reference_b"}:
            errors.append(f"{path}.mode is invalid.")
        if package.get("status") not in {"generated", "not_required"}:
            errors.append(f"{path}.status must be generated or not_required.")
        if package.get("status") == "generated" and package_id not in artifact_package_ids:
            errors.append(f"{path} has no generated artifact linked by package_id.")
        if normalize_software(package.get("software")) != software:
            errors.append(f"{path}.software must match the approved interface software.")
        if package.get("candidate_id") not in candidate_ids and mode not in {"component_reference_a", "component_reference_b"}:
            errors.append(f"{path}.candidate_id must reference an interface candidate.")
    duplicate_package_ids = sorted({item for item in package_ids if item and package_ids.count(item) > 1})
    if duplicate_package_ids:
        errors.append("Calculation package IDs must be unique: " + ", ".join(duplicate_package_ids))
    if "formal_optimization" not in package_modes:
        errors.append("A formal_optimization input package is required before file approval.")
    package_id_set = set(package_ids)
    for candidate in retained_candidates:
        linked = candidate.get("input_package_ids")
        if not isinstance(linked, list) or not linked:
            errors.append(f"Retained candidate {candidate.get('id')} must link at least one calculation package.")
        elif any(str(package_id) not in package_id_set for package_id in linked):
            errors.append(f"Retained candidate {candidate.get('id')} links an unknown calculation package.")
    binding_planned = bool(isinstance(comparison_policy, dict) and comparison_policy.get("binding_energy_planned"))
    if binding_planned and not {"component_reference_a", "component_reference_b"}.issubset(package_modes):
        errors.append("Binding-energy planning requires both strained component-reference packages.")
    if binding_planned and not artifacts.get("reference_components"):
        errors.append("Binding-energy planning requires generated independent-component reference files.")

    dependencies = design.get("dependencies")
    if not isinstance(dependencies, list):
        errors.append("dependencies must be a list.")
        dependencies = []
    generated_dependency_names = {str(item.get("logical_name")) for item in artifacts.get("dependencies", []) if item.get("logical_name")}
    for index, dependency in enumerate(dependencies):
        path = f"dependencies[{index}]"
        if not isinstance(dependency, dict):
            errors.append(f"{path} must be an object.")
            continue
        for key in ("logical_name", "expected_filename", "role", "software", "source", "status"):
            if key not in dependency:
                errors.append(f"{path}.{key} is required.")
        dep_status = dependency.get("status")
        if dep_status not in {"provided", "missing", "user_confirmation_required", "not_applicable"}:
            errors.append(f"{path}.status is invalid.")
        if dep_status == "provided" and str(dependency.get("logical_name")) not in generated_dependency_names:
            errors.append(f"{path} is marked provided but has no generated dependency artifact.")
        if dep_status in {"missing", "user_confirmation_required"}:
            warnings.append(f"Dependency remains pending: {dependency.get('logical_name')} ({dep_status}).")
    if software in {"gromacs", "lammps"} and any(item.get("status") != "provided" for item in dependencies if isinstance(item, dict)):
        errors.append(f"All declared {software} force-field dependencies must be provided before formal files.")

    hpc = design.get("hpc_configuration")
    if not isinstance(hpc, dict):
        errors.append("hpc_configuration must be an object.")
    else:
        fields = hpc.get("fields")
        if not isinstance(fields, dict):
            errors.append("hpc_configuration.fields must be an object.")
        else:
            for name, record in fields.items():
                if not isinstance(record, dict) or record.get("origin") not in {"user", "cluster_template", "placeholder"}:
                    errors.append(f"hpc_configuration.fields.{name} requires value and an allowed origin.")
                    continue
                value = str(record.get("value", ""))
                if record.get("origin") == "placeholder" and not re.search(r"<[^>]+>", value):
                    errors.append(f"hpc_configuration.fields.{name} placeholder must be visibly bracketed.")
        if not isinstance(hpc.get("pending_fields"), list):
            errors.append("hpc_configuration.pending_fields must be a list.")

    static_validation = design.get("static_validation")
    if not isinstance(static_validation, dict):
        errors.append("static_validation must be an object.")
    else:
        for key, allowed in (
            ("format_check", {"passed"}),
            ("logic_check", {"passed"}),
            ("dependency_check", {"complete", "complete_or_explicitly_pending"}),
            ("user_parameter_check", {"complete", "complete_or_explicitly_pending"}),
        ):
            record = static_validation.get(key)
            if not isinstance(record, dict) or record.get("status") not in allowed or not isinstance(record.get("details"), list):
                errors.append(f"static_validation.{key} has an invalid status/details record.")
        if not isinstance(static_validation.get("not_determinable_statically"), list) or not static_validation.get("not_determinable_statically"):
            errors.append("static_validation.not_determinable_statically must state unresolved convergence/result limits.")
        if not isinstance(static_validation.get("files_checked"), list):
            errors.append("static_validation.files_checked must be a list.")
        else:
            checked = {str(item.get("path")) if isinstance(item, dict) else str(item) for item in static_validation["files_checked"]}
            for artifact in [item for group in ("calculation_inputs", "reference_components", "hpc_scripts", "local_run_scripts") for item in artifacts.get(group, []) if isinstance(item, dict)]:
                artifact_path = str(artifact.get("path", ""))
                if artifact_path not in checked and Path(artifact_path).name not in checked:
                    errors.append(f"static_validation.files_checked does not include generated artifact {artifact_path}.")

    workflow_checks = design.get("workflow_checks")
    if not isinstance(workflow_checks, dict):
        errors.append("workflow_checks must be an object.")
    else:
        for key in COMPLETION_CHECKS:
            if workflow_checks.get(key) is not True:
                errors.append(f"workflow_checks.{key} must be true before review/approval.")
    for path in scan_forbidden_keys(design):
        errors.append(f"Forbidden result or unsupported performance-prediction field: {path}.")
    for path in scan_forbidden_statuses(design):
        errors.append(f"Forbidden calculation-execution status at {path}.")

    if for_approval:
        if not design.get("file_specs"):
            errors.append("file_specs must remain available for reproducible restoration/regeneration.")
        for candidate in retained_candidates:
            preview = candidate.get("preview_file")
            if preview:
                try:
                    if not safe_relative_path(interface_dir, str(preview)).is_file():
                        warnings.append(f"Preview is missing for {candidate.get('id')}: {preview}")
                except InterfaceError as exc:
                    warnings.append(str(exc))
    return errors, warnings


def prepare_design(
    interface_dir: Path,
    status: dict[str, Any],
    source: dict[str, Any],
    version: str,
    modification_source: str,
    reason: str,
    status_before: str,
) -> dict[str, Any]:
    design = copy.deepcopy(source)
    raw_selection = design.get("selection")
    if not isinstance(raw_selection, dict):
        raise InterfaceError("Design selection must be an object.")
    design["project_id"] = status["project_id"]
    design["workflow_step"] = "stage2_step2_interface_files"
    design["stage1_link"] = copy.deepcopy(status["stage1_gate"])
    design["surface_link"] = copy.deepcopy(status["surface_gate"])
    design["selection"] = normalize_selection(interface_dir, status, raw_selection, include_proposals=False)
    design["interface_version"] = version
    design["generated_at"] = utc_now()
    design["version_record"] = {
        "version": version,
        "generated_at": design["generated_at"],
        "modification_source": modification_source,
        "modification_reason": reason,
        "status_before": status_before,
        "status_after": WAITING_FOR_INTERFACE_FILE_APPROVAL,
        "calculation_executed": False,
        "job_submitted": False,
    }
    design["generated_artifacts"] = materialize_file_specs(interface_dir, design, version)
    return design


def compact(value: Any, limit: int = 260) -> str:
    if value is None:
        return ""
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, sort_keys=True)
    text = text.replace("\n", " ")
    return text if len(text) <= limit else text[: limit - 1] + "…"


def markdown_table(headers: list[str], rows: list[list[Any]]) -> str:
    lines = ["| " + " | ".join(headers) + " |", "| " + " | ".join("---" for _ in headers) + " |"]
    for row in rows:
        lines.append("| " + " | ".join(compact(value).replace("|", "\\|") for value in row) + " |")
    return "\n".join(lines)


def write_matrix_csv(path: Path, design: dict[str, Any]) -> None:
    fields = [
        "id", "name", "lower_surface_id", "upper_surface_id", "match_id", "translation_fractional",
        "rotation_deg", "initial_interface_distance", "minimum_intercomponent_distance", "target_contact_pairs",
        "interaction_types", "fixed_region", "relaxed_region", "vacuum", "boundary_conditions", "spin_setting",
        "classification", "scientific_use", "retention_reason", "rejection_reason", "structure_files", "input_package_ids",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for candidate in design.get("candidates", []):
            if isinstance(candidate, dict):
                writer.writerow({field: compact(candidate.get(field), 800) for field in fields})


def render_design_report(design: dict[str, Any]) -> str:
    selection = design.get("selection", {})
    interface_type = design.get("interface_type", {})
    compatibility = design.get("software_compatibility", {})
    lines = [
        f"# Interface Design and File Package {design.get('interface_version', '')}",
        "",
        "This report documents generated files only. No optimization, scientific calculation, job submission, or result analysis was executed.",
        "",
        "## Approved upstream context",
        "",
        f"- Project: {design.get('project_id')}",
        f"- Stage-1 version: {design.get('stage1_link', {}).get('approved_version')}",
        f"- Surface version: {design.get('surface_link', {}).get('approved_version')}",
        f"- Research goal: {compact(design.get('stage1_link', {}).get('research_goal'), 1200)}",
        "",
        "## User-selected surfaces and order",
        "",
        f"- Lower: {selection.get('lower_surface_id')} / {compact(selection.get('lower_surface'))}",
        f"- Upper: {selection.get('upper_surface_id')} / {compact(selection.get('upper_surface'))}",
        f"- Order rationale: {selection.get('order_rationale', '')}",
        "",
        "## Interface type and software",
        "",
        f"- Type: {interface_type.get('category')} / {interface_type.get('model_form')}",
        f"- Periodicity/interfaces/vacuum: {interface_type.get('periodicity')} / {interface_type.get('interface_count')} / {interface_type.get('vacuum_required')}",
        f"- Rationale: {interface_type.get('rationale', '')}",
        f"- Software/module: {compatibility.get('software')} / {compatibility.get('module')}",
        f"- Compatibility: {compatibility.get('rationale', '')}",
        "",
        "## Lattice matching",
        "",
        markdown_table(
            ["ID", "A cell", "B cell", "Rotation", "A strain", "B strain", "Area", "Atoms", "Distribution", "Status"],
            [[m.get("id"), m.get("surface_a_supercell"), m.get("surface_b_supercell"), m.get("rotation_deg"), m.get("strain_a"), m.get("strain_b"), m.get("interface_area"), m.get("atom_count"), m.get("strain_distribution"), m.get("status")] for m in design.get("lattice_matches", []) if isinstance(m, dict)],
        ),
        "",
        "## Interface candidates",
        "",
        markdown_table(
            ["ID", "Match", "Translation", "Distance", "Contacts", "Constraints", "Boundary", "Spin", "Class", "Use"],
            [[c.get("id"), c.get("match_id"), c.get("translation_fractional"), c.get("initial_interface_distance"), c.get("target_contact_pairs"), {"fixed": c.get("fixed_region"), "relaxed": c.get("relaxed_region")}, c.get("boundary_conditions"), c.get("spin_setting"), c.get("classification"), c.get("scientific_use")] for c in design.get("candidates", []) if isinstance(c, dict)],
        ),
        "",
        "## Optimization parameters",
        "",
        "```json",
        json.dumps(design.get("optimization_parameters", {}), ensure_ascii=False, indent=2),
        "```",
        "",
        "## Generated artifacts",
        "",
    ]
    for group, records in design.get("generated_artifacts", {}).items():
        lines.extend([f"### {group}", ""])
        if records:
            lines.extend([f"- `{item.get('path')}` — {item.get('role')} — SHA-256 `{item.get('sha256')}`" for item in records if isinstance(item, dict)])
        else:
            lines.append("- None / not required")
        lines.append("")
    lines.extend(
        [
            "## Dependencies and pending fields",
            "",
            "```json",
            json.dumps({"dependencies": design.get("dependencies"), "hpc": design.get("hpc_configuration")}, ensure_ascii=False, indent=2),
            "```",
            "",
            "## Static validation limitation",
            "",
            "Static checks cannot establish convergence, equilibrium geometry, binding energy, charge transfer, or electronic/bonding results.",
            "",
        ]
    )
    return "\n".join(lines)


def render_input_report(design: dict[str, Any]) -> str:
    lines = [
        f"# Input Generation Report {design.get('interface_version')}",
        "",
        "Files were rendered but not executed or submitted.",
        "",
        "## Packages",
        "",
        markdown_table(["ID", "Candidate", "Mode", "Software", "Status", "Purpose", "Limitations"], [[p.get("id"), p.get("candidate_id"), p.get("mode"), p.get("software"), p.get("status"), p.get("purpose"), p.get("limitations")] for p in design.get("calculation_packages", []) if isinstance(p, dict)]),
        "",
        "## Inherited and adjusted parameters",
        "",
        "```json",
        json.dumps(design.get("optimization_parameters", {}), ensure_ascii=False, indent=2),
        "```",
        "",
        "## File manifest",
        "",
    ]
    for group, records in design.get("generated_artifacts", {}).items():
        for item in records:
            lines.append(f"- {group}: `{item.get('path')}` ({item.get('role')}, `{item.get('sha256')}`)")
    lines.append("")
    return "\n".join(lines)


def render_static_report(design: dict[str, Any], errors: list[str], warnings: list[str]) -> str:
    static = design.get("static_validation", {})
    lines = [
        f"# Static Validation Report {design.get('interface_version')}",
        "",
        f"- Engine contract result: {'PASSED' if not errors else 'FAILED'}",
        f"- User-declared format check: {check_status(static.get('format_check'))}",
        f"- User-declared logic check: {check_status(static.get('logic_check'))}",
        f"- Dependency state: {check_status(static.get('dependency_check'))}",
        f"- User-parameter state: {check_status(static.get('user_parameter_check'))}",
        "- Calculation executed: false",
        "- Job submitted: false",
        "",
        "## Errors",
        "",
    ]
    lines.extend([f"- {item}" for item in errors] or ["- None"])
    lines.extend(["", "## Warnings and pending fields", ""])
    lines.extend([f"- {item}" for item in warnings] or ["- None"])
    lines.extend(["", "## Cannot be determined statically", ""])
    lines.extend([f"- {item}" for item in static.get("not_determinable_statically", [])] or ["- Optimization convergence, equilibrium geometry, and scientific results."])
    lines.extend(["", "A static pass does not guarantee that a future calculation will converge or be scientifically correct.", ""])
    return "\n".join(lines)


def write_version(interface_dir: Path, design: dict[str, Any], errors: list[str], warnings: list[str], analysis: dict[str, Any] | None = None) -> None:
    version = design["interface_version"]
    design["engine_static_validation"] = {
        "status": "passed" if not errors else "failed",
        "errors": errors,
        "warnings": warnings,
        "checked_at": utc_now(),
        "calculation_executed": False,
        "job_submitted": False,
    }
    write_json(version_json_path(interface_dir, version), design)
    write_matrix_csv(version_csv_path(interface_dir, version), design)
    write_json(version_parameters_path(interface_dir, version), design.get("optimization_parameters", {}))
    write_text(version_input_report_path(interface_dir, version), render_input_report(design))
    write_text(version_static_report_path(interface_dir, version), render_static_report(design, errors, warnings))
    write_json(interface_dir / "interface_type.json", design.get("interface_type", {}))
    write_json(interface_dir / "lattice_matching_report.json", {"version": version, "matches": design.get("lattice_matches", []), "comparison_policy": design.get("comparison_policy")})
    if analysis:
        report = render_impact(analysis)
        name = f"interface_impact_analysis_{analysis['from_version']}_to_{analysis['to_version']}.md"
        write_text(interface_dir / name, report)
        write_text(interface_dir / "interface_impact_analysis.md", report)
    elif not (interface_dir / "interface_impact_analysis.md").exists():
        write_text(interface_dir / "interface_impact_analysis.md", "# Interface Modification Impact\n\nNo user modification has been submitted.\n")


def attempted_protected_edits(before: dict[str, Any], edited: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    for key in ("project_id", "stage1_link", "surface_link"):
        if key in edited and edited.get(key) != before.get(key):
            errors.append(f"Immutable upstream field {key!r} changed; return to its owning stage.")
    before_selection = before.get("selection", {})
    edited_selection = edited.get("selection", {})
    if isinstance(before_selection, dict) and isinstance(edited_selection, dict):
        same_ids = all(before_selection.get(key) == edited_selection.get(key) for key in ("lower_surface_id", "upper_surface_id"))
        if same_ids:
            for key in ("lower_surface", "upper_surface"):
                if key in edited_selection and edited_selection.get(key) != before_selection.get(key):
                    errors.append(f"Approved component snapshot selection.{key} cannot be edited; select another approved ID instead.")
    return errors


def classify_change(path: str) -> tuple[str, str, str]:
    lowered = path.lower()
    if any(token in lowered for token in ("stage1_link", "surface_link", "lower_surface_id", "upper_surface_id", "interface_type", "software_compatibility", "functional", "basis_or_pseudopotential", "dispersion", "spin_method")):
        return "CRITICAL", "Changes the approved components, model form, software, or scientific method and can redefine the physical system or evidence chain.", "Revalidate the owning approved stage and regenerate every dependent structure and file."
    if any(token in lowered for token in ("lattice_matches", "supercell", "rotation_deg", "strain", "matched_lattice", "vacuum", "boundary_conditions", "dipole", "component_reference", "k_points")):
        return "HIGH", "Changes mismatch, periodicity, strain/reference state, or reciprocal/boundary settings, affecting comparability and downstream energies/electronic analyses.", "Rebuild structures, inputs, and strained component references; repeat static checks."
    if any(token in lowered for token in ("translation_fractional", "initial_interface_distance", "minimum_intercomponent_distance", "target_contact_pairs", "interaction_types", "fixed_region", "relaxed_region", "candidate")):
        return "MEDIUM", "Changes local contacts or the allowed reconstruction space and may alter later bonding, charge transfer, and configuration ranking.", "Regenerate the affected candidate and inspect contact/constraint geometry."
    if any(token in lowered for token in ("hpc_configuration", "hpc_scripts", "local_run_scripts", "partition", "account", "nodes", "cores", "walltime", "memory", "module", "executable")):
        return "LOW", "Changes execution packaging rather than the intended scientific model; invalid values may still prevent a future job from starting.", "Regenerate scripts and verify the values against the actual platform without claiming performance impact."
    if "dependencies" in lowered:
        return "LOW", "Changes file readiness or provenance but does not by itself change a scientific result.", "Recheck mappings and hashes before user execution."
    return "MEDIUM", "Changes the interface/file package and may affect reproducibility or interpretation.", "Review the changed artifact and regenerate dependent records."


def recursive_diff(before: Any, after: Any, path: str, reason: str, changes: list[dict[str, Any]]) -> None:
    if isinstance(before, dict) and isinstance(after, dict):
        for key in sorted(set(before) | set(after)):
            if key in {"generated_at", "interface_version", "version_record", "engine_static_validation", "generated_artifacts"}:
                continue
            child_path = f"{path}.{key}" if path else key
            if key not in before:
                level, effect, recommendation = classify_change(child_path)
                changes.append({"kind": "added", "path": child_path, "before": None, "after": after[key], "user_reason": reason, "impact_level": level, "impact_reason": effect, "recommendation": recommendation})
            elif key not in after:
                level, effect, recommendation = classify_change(child_path)
                changes.append({"kind": "removed", "path": child_path, "before": before[key], "after": None, "user_reason": reason, "impact_level": level, "impact_reason": effect, "recommendation": recommendation})
            else:
                recursive_diff(before[key], after[key], child_path, reason, changes)
    elif isinstance(before, list) and isinstance(after, list):
        if before != after:
            level, effect, recommendation = classify_change(path)
            changes.append({"kind": "changed", "path": path, "before": before, "after": after, "user_reason": reason, "impact_level": level, "impact_reason": effect, "recommendation": recommendation})
    elif before != after:
        level, effect, recommendation = classify_change(path)
        changes.append({"kind": "changed", "path": path, "before": before, "after": after, "user_reason": reason, "impact_level": level, "impact_reason": effect, "recommendation": recommendation})


def analyze(before: dict[str, Any], after: dict[str, Any], reason: str, errors: list[str], warnings: list[str]) -> dict[str, Any]:
    changes: list[dict[str, Any]] = []
    recursive_diff(before, after, "", reason, changes)
    levels = {"LOW": 1, "MEDIUM": 2, "HIGH": 3, "CRITICAL": 4}
    overall = "CRITICAL" if errors else max((item["impact_level"] for item in changes), key=lambda value: levels[value], default="LOW")
    impacts: list[str] = []
    if any(item["impact_level"] == "CRITICAL" for item in changes):
        impacts.append("The physical system or approved method may have changed; upstream consistency and the complete evidence chain require review.")
    if any("strain" in item["path"].lower() or "lattice" in item["path"].lower() for item in changes):
        impacts.append("Strained independent-component references and future binding-energy comparability must be regenerated and rechecked.")
    if any(any(token in item["path"].lower() for token in ("translation", "distance", "contact", "fixed_region")) for item in changes):
        impacts.append("Local coordination, hydrogen bonding, charge-transfer pathways, and allowed interface reconstruction may differ.")
    if any("hpc" in item["path"].lower() or "local_run" in item["path"].lower() for item in changes):
        impacts.append("Scheduler/resource changes do not directly change the scientific model, but invalid settings can prevent execution.")
    if not impacts:
        impacts.append("The change is confined to recorded packaging or metadata; reproducibility records still require regeneration.")
    return {
        "from_version": before.get("interface_version"),
        "to_version": after.get("interface_version"),
        "generated_at": utc_now(),
        "reason": reason,
        "overall_impact_level": overall,
        "changes": changes,
        "result_impacts": impacts,
        "validation_errors": errors,
        "validation_warnings": warnings,
        "final_conclusion_impact": "No scientific result has been generated. These changes affect the design or readiness of future calculations only.",
    }


def render_impact(analysis: dict[str, Any]) -> str:
    lines = [
        f"# Interface/File Impact: {analysis.get('from_version')} → {analysis.get('to_version')}",
        "",
        f"- Overall impact: **{analysis.get('overall_impact_level')}**",
        f"- Reason: {analysis.get('reason')}",
        "",
        "## Changes",
        "",
        markdown_table(["Path", "Kind", "Before", "After", "Level", "Impact", "Recommendation"], [[c.get("path"), c.get("kind"), c.get("before"), c.get("after"), c.get("impact_level"), c.get("impact_reason"), c.get("recommendation")] for c in analysis.get("changes", [])]),
        "",
        "## Downstream effects",
        "",
    ]
    lines.extend([f"- {item}" for item in analysis.get("result_impacts", [])])
    lines.extend(["", "## Validation", ""])
    lines.extend([f"- ERROR: {item}" for item in analysis.get("validation_errors", [])])
    lines.extend([f"- WARNING: {item}" for item in analysis.get("validation_warnings", [])])
    if not analysis.get("validation_errors") and not analysis.get("validation_warnings"):
        lines.append("- Version data, generated-file hashes, and logical/static checks passed.")
    lines.extend(["", analysis.get("final_conclusion_impact", ""), ""])
    return "\n".join(lines)


def initialize_design(interface_dir: Path, source_path: Path) -> dict[str, Any]:
    status = load_status(interface_dir)
    verify_frozen_gates(status)
    if status["status"] != INTERFACE_SURFACES_SELECTED or status.get("current_candidate_version"):
        raise InterfaceError("Initial design requires an explicit selection and no existing valid interface version.")
    if status.get("selection_review_confirmed") is not True:
        raise InterfaceError("The selected lower/upper surfaces require hash-bound browser confirmation before design initialization.")
    source = read_json(source_path)
    if not isinstance(source, dict):
        raise InterfaceError("Interface design source must be a JSON object.")
    selection = read_json(interface_dir / "interface_selection.json")
    source["selection"] = selection
    version = next_version(interface_dir, status)
    design = prepare_design(interface_dir, status, source, version, "SYSTEM_INITIAL_INTERFACE_FILES", "Initial interface candidate and generated file package", status["status"])
    errors, warnings = validate_design(interface_dir, design)
    errors.extend(structural_regeneration_errors(None, design, version))
    write_version(interface_dir, design, errors, warnings)
    status["latest_version"] = version
    status["updated_at"] = utc_now()
    status["validation_errors"] = errors
    status["validation_warnings"] = warnings
    if errors:
        write_json(status_path(interface_dir), status)
        append_log(interface_dir, {"event": "INTERFACE_INITIAL_VERSION_REJECTED", "timestamp": utc_now(), "version": version, "status_before": INTERFACE_SURFACES_SELECTED, "status_after": INTERFACE_SURFACES_SELECTED, "errors": errors})
        raise InterfaceError("Initial interface/file validation failed:\n- " + "\n- ".join(errors))
    transitions = (
        (LATTICE_MATCHING_COMPLETED, "LATTICE_MATCHING_COMPLETED"),
        (INTERFACE_CANDIDATES_GENERATED, "INTERFACE_CANDIDATES_GENERATED"),
        (INTERFACE_MODELS_VALIDATED, "INTERFACE_MODELS_VALIDATED"),
        (CALCULATION_INPUTS_GENERATED, "CALCULATION_INPUTS_GENERATED"),
        (HPC_SCRIPTS_GENERATED, "HPC_OR_LOCAL_SCRIPTS_GENERATED"),
        (STATIC_VALIDATION_COMPLETED, "STATIC_VALIDATION_COMPLETED"),
        (WAITING_FOR_INTERFACE_FILE_APPROVAL, "INTERFACE_FILE_REVIEW_READY"),
    )
    old = status["status"]
    for new_status, event in transitions:
        append_log(interface_dir, {"event": event, "timestamp": utc_now(), "version": version, "status_before": old, "status_after": new_status})
        old = new_status
    status.update(
        {
            "status": WAITING_FOR_INTERFACE_FILE_APPROVAL,
            "current_candidate_version": version,
            "latest_version": version,
            "previous_version": None,
            "previous_valid_version": version,
            "validation_errors": [],
            "validation_warnings": warnings,
            "updated_at": utc_now(),
            "user_execution_files_ready": False,
        }
    )
    write_json(status_path(interface_dir), status)
    return status


def submit_design(interface_dir: Path, edited: dict[str, Any], reason: str, source: str = "USER_EDIT") -> dict[str, Any]:
    if not reason.strip():
        raise InterfaceError("A modification reason is required.")
    status = load_status(interface_dir)
    verify_frozen_gates(status)
    if status["status"] == INTERFACE_FILES_APPROVED:
        raise InterfaceError("The approved interface/file baseline is immutable.")
    if status["status"] != WAITING_FOR_INTERFACE_FILE_APPROVAL or not status.get("current_candidate_version"):
        raise InterfaceError("Submit edits only after an initial interface/file version is ready for review.")
    before_version = status["current_candidate_version"]
    before = load_design(interface_dir, before_version)
    attempted_errors = attempted_protected_edits(before, edited)
    version = next_version(interface_dir, status)
    if source == "RESTORE" and coordinate_design_fingerprint(before) != coordinate_design_fingerprint(edited):
        edited = copy.deepcopy(edited)
        clone_restored_structures(interface_dir, edited, version)
    after = prepare_design(interface_dir, status, edited, version, source, reason, status["status"])
    errors, warnings = validate_design(interface_dir, after)
    errors.extend(attempted_errors)
    errors.extend(structural_regeneration_errors(before, after, version))
    analysis = analyze(before, after, reason, errors, warnings)
    after["version_record"]["modification_content"] = [{"kind": item["kind"], "path": item["path"]} for item in analysis["changes"]]
    after["version_record"]["impact_summary"] = {"overall_impact_level": analysis["overall_impact_level"], "validation_errors": errors, "result_impacts": analysis["result_impacts"]}
    write_version(interface_dir, after, errors, warnings, analysis)
    status.update(
        {
            "status": WAITING_FOR_INTERFACE_FILE_APPROVAL,
            "current_candidate_version": version,
            "latest_version": version,
            "previous_version": before_version,
            "previous_valid_version": before_version if not before.get("engine_static_validation", {}).get("errors") else status.get("previous_valid_version"),
            "validation_errors": errors,
            "validation_warnings": warnings,
            "last_impact_level": analysis["overall_impact_level"],
            "last_impact_report": f"interface_impact_analysis_{before_version}_to_{version}.md",
            "updated_at": utc_now(),
            "user_execution_files_ready": False,
        }
    )
    write_json(status_path(interface_dir), status)
    append_log(interface_dir, {"event": "INTERFACE_FILE_MODIFICATION_ANALYZED", "timestamp": utc_now(), "version": version, "previous_version": before_version, "source": source, "reason": reason, "changes": [{"path": item["path"], "impact_level": item["impact_level"]} for item in analysis["changes"]], "status_before": WAITING_FOR_INTERFACE_FILE_APPROVAL, "status_after": WAITING_FOR_INTERFACE_FILE_APPROVAL})
    return {"status": status, "analysis": analysis}


def manifest_tree(root: Path, base: Path) -> list[dict[str, Any]]:
    if not root.exists():
        return []
    return [{"path": path.relative_to(base).as_posix(), "sha256": sha256(path), "size_bytes": path.stat().st_size} for path in sorted(root.rglob("*")) if path.is_file()]


def copytree_required(source: Path, target: Path) -> None:
    if not source.is_dir():
        raise InterfaceError(f"Required versioned directory is missing: {source}")
    if target.exists():
        raise InterfaceError(f"Approved directory already exists and will not be overwritten: {target}")
    shutil.copytree(source, target)


def approve(interface_dir: Path, confirmed_by: str, reason: str) -> dict[str, Any]:
    status = load_status(interface_dir)
    verify_frozen_gates(status)
    if status["status"] != WAITING_FOR_INTERFACE_FILE_APPROVAL:
        raise InterfaceError("Interface-file approval requires a reviewed current candidate.")
    if status.get("validation_errors"):
        raise InterfaceError("Resolve validation errors before interface-file approval.")
    version = str(status.get("current_candidate_version", ""))
    design = load_design(interface_dir, version)
    errors, warnings = validate_design(interface_dir, design, for_approval=True)
    required_files = [
        "interface_selection.json",
        "interface_type.json",
        "lattice_matching_report.json",
        f"interface_matrix_{version}.csv",
        f"optimization_parameters_{version}.json",
        f"input_generation_report_{version}.md",
        f"static_validation_report_{version}.md",
        "interface_change_log.json",
        "interface_impact_analysis.md",
        "interface_review.html",
    ]
    missing = [name for name in required_files if not (interface_dir / name).exists()]
    if missing:
        errors.append("Missing interface review/generation artifacts: " + ", ".join(missing))
    approved_json = interface_dir / "interface_design_approved.json"
    approved_parameters = interface_dir / "optimization_parameters_approved.json"
    approved_calculation_dir = interface_dir / "calculation_inputs_approved"
    approved_hpc_dir = interface_dir / "hpc_scripts_approved"
    approved_md = interface_dir / "interface_design_approved.md"
    approval_record_path = interface_dir / "interface_file_approval_record.json"
    targets = [approved_json, approved_parameters, approved_calculation_dir, approved_hpc_dir, approved_md, approval_record_path]
    if any(path.exists() for path in targets):
        errors.append("One or more approved interface/file targets already exist and will not be overwritten.")
    approved_structure_dir = interface_dir / "approved_interfaces" / version
    if approved_structure_dir.exists():
        errors.append(f"Approved interface structure directory already exists: {approved_structure_dir}")
    if errors:
        raise InterfaceError("Interface-file approval validation failed:\n- " + "\n- ".join(errors))

    write_json(approved_json, design)
    write_json(approved_parameters, design.get("optimization_parameters", {}))
    write_text(approved_md, render_design_report(design))
    copytree_required(group_root(interface_dir, "calculation_inputs", version), approved_calculation_dir)
    reference_source = group_root(interface_dir, "reference_components", version)
    if reference_source.is_dir():
        shutil.copytree(reference_source, approved_calculation_dir / "reference_components")
    hpc_source = group_root(interface_dir, "hpc_scripts", version)
    local_source = group_root(interface_dir, "local_run_scripts", version)
    approved_hpc_dir.mkdir(parents=True)
    if hpc_source.is_dir():
        shutil.copytree(hpc_source, approved_hpc_dir / "scheduler")
    if local_source.is_dir():
        shutil.copytree(local_source, approved_hpc_dir / "local_run_scripts")
    approved_structure_dir.mkdir(parents=True)
    copied_structures: list[dict[str, Any]] = []
    for candidate in design.get("candidates", []):
        if not isinstance(candidate, dict) or candidate.get("classification") == "rejected":
            continue
        for index, record in enumerate(candidate.get("structure_files", []), start=1):
            source = safe_relative_path(interface_dir, str(record.get("path", "")))
            destination = approved_structure_dir / f"{safe_name(str(candidate.get('id')))}_{index}_{safe_name(source.name)}"
            shutil.copyfile(source, destination)
            copied_structures.append({"candidate_id": candidate.get("id"), "path": destination.relative_to(interface_dir).as_posix(), "sha256": sha256(destination)})

    selection = design.get("selection", {})
    selected_match_ids = {candidate.get("match_id") for candidate in design.get("candidates", []) if isinstance(candidate, dict) and candidate.get("classification") != "rejected"}
    selected_matches = [match for match in design.get("lattice_matches", []) if isinstance(match, dict) and match.get("id") in selected_match_ids]
    pending_fields = copy.deepcopy(design.get("hpc_configuration", {}).get("pending_fields", []))
    pending_dependencies = [item for item in design.get("dependencies", []) if isinstance(item, dict) and item.get("status") in {"missing", "user_confirmation_required"}]
    record = {
        "project_id": design.get("project_id"),
        "workflow_step": "stage2_step2_interface_files",
        "approved_version": version,
        "confirmed_at": utc_now(),
        "confirmed_by": confirmed_by or "user",
        "confirmation_reason": reason,
        "user_confirmation_status": "CONFIRMED",
        "stage1_version": design.get("stage1_link", {}).get("approved_version"),
        "stage1_files": design.get("stage1_link", {}).get("files"),
        "surface_version": design.get("surface_link", {}).get("approved_version"),
        "surface_files": design.get("surface_link", {}).get("files"),
        "lower_surface_id": selection.get("lower_surface_id"),
        "upper_surface_id": selection.get("upper_surface_id"),
        "order": "lower__upper",
        "interface_type": design.get("interface_type"),
        "selected_lattice_matches": selected_matches,
        "retained_candidates": [{"id": candidate.get("id"), "name": candidate.get("name"), "match_id": candidate.get("match_id"), "translation": candidate.get("translation_fractional"), "rotation_deg": candidate.get("rotation_deg"), "initial_distance": candidate.get("initial_interface_distance"), "fixed_region": candidate.get("fixed_region"), "vacuum": candidate.get("vacuum"), "boundary_conditions": candidate.get("boundary_conditions"), "spin": candidate.get("spin_setting")} for candidate in design.get("candidates", []) if isinstance(candidate, dict) and candidate.get("classification") != "rejected"],
        "software_compatibility": design.get("software_compatibility"),
        "optimization_parameters": design.get("optimization_parameters"),
        "calculation_packages": design.get("calculation_packages"),
        "generated_artifacts": design.get("generated_artifacts"),
        "approved_interface_structures": copied_structures,
        "dependencies": design.get("dependencies"),
        "pending_dependencies": pending_dependencies,
        "pending_user_fields": pending_fields,
        "static_validation": design.get("static_validation"),
        "engine_static_validation": design.get("engine_static_validation"),
        "known_risks": design.get("known_risks"),
        "validation_warnings": warnings,
        "approved_file_manifests": {
            "calculation_inputs_approved": manifest_tree(approved_calculation_dir, interface_dir),
            "hpc_scripts_approved": manifest_tree(approved_hpc_dir, interface_dir),
            "approved_interfaces": manifest_tree(approved_structure_dir, interface_dir),
        },
        "approved_design_sha256": sha256(approved_json),
        "approved_parameters_sha256": sha256(approved_parameters),
        "approved_markdown_sha256": sha256(approved_md),
        "calculation_executed": False,
        "job_submitted": False,
        "static_validation_is_not_convergence_proof": True,
        "commands_are_user_instructions_only": True,
    }
    write_json(approval_record_path, record)
    old = status["status"]
    status.update(
        {
            "status": INTERFACE_FILES_APPROVED,
            "approved_version": version,
            "approved_at": record["confirmed_at"],
            "updated_at": record["confirmed_at"],
            "validation_errors": [],
            "calculation_executed": False,
            "job_submitted": False,
            "user_execution_files_ready": True,
        }
    )
    write_json(status_path(interface_dir), status)
    append_log(interface_dir, {"event": "INTERFACE_FILES_APPROVED", "timestamp": record["confirmed_at"], "version": version, "confirmed_by": confirmed_by or "user", "reason": reason, "status_before": old, "status_after": INTERFACE_FILES_APPROVED, "calculation_executed": False, "job_submitted": False})
    return {"status": status, "approval_record": record}


def transition(interface_dir: Path, action: str, reason: str = "", version: str | None = None, confirmed_by: str = "user") -> dict[str, Any]:
    status = load_status(interface_dir)
    verify_frozen_gates(status)
    if status["status"] == INTERFACE_FILES_APPROVED:
        raise InterfaceError("The approved interface/file baseline is immutable.")
    if action in {"accept", "approve"}:
        raise InterfaceError("Interface approval must be submitted through the hash-bound browser review command.")
    if status["status"] != WAITING_FOR_INTERFACE_FILE_APPROVAL:
        raise InterfaceError("Review actions require WAITING_FOR_INTERFACE_FILE_APPROVAL.")
    if action == "continue":
        append_log(interface_dir, {"event": "INTERFACE_CONTINUE_EDITING", "timestamp": utc_now(), "version": status.get("current_candidate_version"), "reason": reason, "status_before": status["status"], "status_after": status["status"]})
        return {"status": status}
    if action == "reject":
        fallback = status.get("previous_valid_version") or status.get("previous_version")
        if not fallback:
            raise InterfaceError("No previous valid interface version is available.")
        rejected = status.get("current_candidate_version")
        status.update({"current_candidate_version": fallback, "rejected_version": rejected, "validation_errors": [], "updated_at": utc_now()})
        write_json(status_path(interface_dir), status)
        append_log(interface_dir, {"event": "INTERFACE_FILE_MODIFICATION_REJECTED", "timestamp": utc_now(), "version": rejected, "restored_current_version": fallback, "reason": reason, "status_before": WAITING_FOR_INTERFACE_FILE_APPROVAL, "status_after": WAITING_FOR_INTERFACE_FILE_APPROVAL})
        return {"status": status}
    if action == "restore":
        target = version or status.get("previous_version")
        if not target:
            raise InterfaceError("No historical version was supplied for restoration.")
        source_design = load_design(interface_dir, target)
        result = submit_design(interface_dir, source_design, reason or f"Restore {target}", "RESTORE")
        append_log(interface_dir, {"event": "INTERFACE_VERSION_RESTORED_AS_NEW", "timestamp": utc_now(), "source_version": target, "new_version": result["status"]["current_candidate_version"], "reason": reason or f"Restore {target}"})
        return result
    raise InterfaceError(f"Unknown action: {action}")


def browser_review(
    interface_dir: Path,
    project_dir: Path,
    title: str,
    start_port: int,
    timeout_seconds: float | None,
) -> dict[str, Any]:
    status = load_status(interface_dir)
    version = status.get("current_candidate_version")
    if not version:
        raise InterfaceError("No interface candidate is available for browser review.")
    return execute_stage_review(
        project_dir=project_dir,
        stage_dir=interface_dir,
        stage="stage2_step2_interface",
        title=title,
        content_file=version_json_path(interface_dir, str(version)),
        allowed_statuses={WAITING_FOR_INTERFACE_FILE_APPROVAL},
        revision_status=WAITING_FOR_INTERFACE_FILE_APPROVAL,
        rejected_status=INTERFACE_REVIEW_REJECTED,
        load_status=lambda: load_status(interface_dir),
        save_status=lambda value: write_json(status_path(interface_dir), value),
        append_log=lambda value: append_log(interface_dir, value),
        approve=lambda comment: approve(interface_dir, "browser_user", comment),
        error_type=InterfaceError,
        blocked_access_updates={"user_execution_files_ready": False},
        revision_updates={"user_execution_files_ready": False},
        rejected_updates={"user_execution_files_ready": False},
        start_port=start_port,
        timeout_seconds=timeout_seconds,
    )


def browser_review_selection(
    interface_dir: Path,
    project_dir: Path,
    title: str,
    start_port: int,
    timeout_seconds: float | None,
) -> dict[str, Any]:
    def confirm_selection(comment: str) -> dict[str, Any]:
        status = load_status(interface_dir)
        status.update({"selection_review_confirmed": True, "selection_review_comment": comment, "updated_at": utc_now()})
        write_json(status_path(interface_dir), status)
        append_log(interface_dir, {"event": "INTERFACE_SELECTION_BROWSER_CONFIRMED", "timestamp": utc_now(), "comment": comment, "status_after": status["status"]})
        return {"status": status}

    return execute_stage_review(
        project_dir=project_dir,
        stage_dir=interface_dir,
        stage="stage2_step2_interface_selection",
        title=title,
        content_file=interface_dir / "interface_selection.json",
        allowed_statuses={INTERFACE_SURFACES_SELECTED},
        revision_status=WAITING_FOR_INTERFACE_SELECTION,
        rejected_status=INTERFACE_REVIEW_REJECTED,
        load_status=lambda: load_status(interface_dir),
        save_status=lambda value: write_json(status_path(interface_dir), value),
        append_log=lambda value: append_log(interface_dir, value),
        approve=confirm_selection,
        error_type=InterfaceError,
        blocked_access_updates={"selection_review_confirmed": False},
        revision_updates={"selection_review_confirmed": False},
        rejected_updates={"selection_review_confirmed": False},
        start_port=start_port,
        timeout_seconds=timeout_seconds,
    )


def current_data(interface_dir: Path) -> dict[str, Any]:
    status = load_status(interface_dir)
    current = load_design(interface_dir, status["current_candidate_version"]) if status.get("current_candidate_version") else None
    previous = load_design(interface_dir, status["previous_version"]) if status.get("previous_version") else None
    analysis = None
    if current and previous:
        analysis = analyze(previous, current, current.get("version_record", {}).get("modification_reason", ""), status.get("validation_errors", []), status.get("validation_warnings", []))
    selection = read_json(interface_dir / "interface_selection.json") if (interface_dir / "interface_selection.json").exists() else None
    return {
        "status": status,
        "available_surfaces": status.get("surface_gate", {}).get("models", []),
        "selection": selection,
        "design": current,
        "versions": sorted(path.stem.replace("interface_candidates_", "") for path in interface_dir.glob("interface_candidates_v*.json")),
        "change_log": read_json(log_path(interface_dir)),
        "analysis": analysis,
    }


class InterfaceHandler(BaseHTTPRequestHandler):
    interface_dir: Path

    def log_message(self, format_string: str, *args: Any) -> None:
        sys.stderr.write("[interface-review] " + format_string % args + "\n")

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
        self.send_header("Content-Disposition", f'inline; filename="{safe_name(path.name)}"')
        self.end_headers()
        self.wfile.write(encoded)

    def body(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0"))
        if length <= 0 or length > 16 * 1024 * 1024:
            raise InterfaceError("Request body must be between 1 byte and 16 MiB.")
        value = json.loads(self.rfile.read(length).decode("utf-8"))
        if not isinstance(value, dict):
            raise InterfaceError("Request body must be a JSON object.")
        return value

    def do_GET(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
        try:
            if path in {"/", "/interface_review.html"}:
                self.send_file(self.interface_dir / "interface_review.html", "text/html; charset=utf-8")
            elif path == "/api/state":
                self.send_json(current_data(self.interface_dir))
            elif path.startswith("/files/"):
                artifact = safe_relative_path(self.interface_dir, unquote(path[len("/files/"):]))
                if not artifact.is_file():
                    self.send_json({"error": "File not found"}, HTTPStatus.NOT_FOUND)
                else:
                    self.send_file(artifact)
            else:
                self.send_json({"error": "Not found"}, HTTPStatus.NOT_FOUND)
        except (InterfaceError, OSError, ValueError, json.JSONDecodeError) as exc:
            self.send_json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)

    def do_POST(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
        try:
            payload = self.body()
            if path == "/api/select":
                result = record_selection(self.interface_dir, selection_value=payload)
            elif path == "/api/submit":
                design = payload.get("design")
                if not isinstance(design, dict):
                    raise InterfaceError("design must be a JSON object.")
                result = submit_design(self.interface_dir, design, str(payload.get("reason", "")))
            elif path == "/api/action":
                result = transition(self.interface_dir, str(payload.get("action", "")), str(payload.get("reason", "")), str(payload["version"]) if payload.get("version") else None, str(payload.get("confirmed_by", "user")))
            else:
                self.send_json({"error": "Not found"}, HTTPStatus.NOT_FOUND)
                return
            self.send_json({"ok": True, "result": result})
        except (InterfaceError, OSError, ValueError, json.JSONDecodeError) as exc:
            self.send_json({"ok": False, "error": str(exc)}, HTTPStatus.BAD_REQUEST)


def serve(interface_dir: Path, host: str, port: int, open_page: bool) -> None:
    ensure_review_html(interface_dir)
    handler = type("BoundInterfaceHandler", (InterfaceHandler,), {"interface_dir": interface_dir})
    server = ThreadingHTTPServer((host, port), handler)
    address = f"http://{host}:{server.server_address[1]}/"
    print(f"Interface review page: {address}", flush=True)
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

    start_parser = subparsers.add_parser("start", help="Verify both approved baselines and initialize interface selection.")
    start_parser.add_argument("--stage1-planning-dir", type=Path, required=True)
    start_parser.add_argument("--surface-dir", type=Path, required=True)
    start_parser.add_argument("--interface-dir", type=Path, default=Path("interface_design"))

    select_parser = subparsers.add_parser("select", help="Record the user's lower/upper approved surface selection.")
    select_parser.add_argument("--interface-dir", type=Path, default=Path("interface_design"))
    select_parser.add_argument("--selection", type=Path, required=True)

    init_parser = subparsers.add_parser("init-design", help="Create a file-bearing immutable interface version.")
    init_parser.add_argument("--interface-dir", type=Path, default=Path("interface_design"))
    init_parser.add_argument("--design", type=Path, required=True)

    validate_parser = subparsers.add_parser("validate", help="Validate an interface design against files and frozen gates.")
    validate_parser.add_argument("--interface-dir", type=Path, default=Path("interface_design"))
    validate_parser.add_argument("--design", type=Path, required=True)
    validate_parser.add_argument("--for-approval", action="store_true")

    submit_parser = subparsers.add_parser("submit", help="Create the next immutable file/design version and impact report.")
    submit_parser.add_argument("--interface-dir", type=Path, default=Path("interface_design"))
    submit_parser.add_argument("--edited-design", type=Path, required=True)
    submit_parser.add_argument("--reason", required=True)

    action_parser = subparsers.add_parser("action", help="Accept, continue, restore, or reject a version.")
    action_parser.add_argument("--interface-dir", type=Path, default=Path("interface_design"))
    action_parser.add_argument("--name", choices=("accept", "approve", "continue", "restore", "reject"), required=True)
    action_parser.add_argument("--reason", default="")
    action_parser.add_argument("--version")
    action_parser.add_argument("--confirmed-by", default="user")

    serve_parser = subparsers.add_parser("serve", help="Serve and optionally open the browser interface/file review page.")
    serve_parser.add_argument("--interface-dir", type=Path, default=Path("interface_design"))
    serve_parser.add_argument("--host", default="127.0.0.1")
    serve_parser.add_argument("--port", type=int, default=8767)
    serve_parser.add_argument("--open", action="store_true", dest="open_page")

    review_parser = subparsers.add_parser("review", help="Open the hash-bound Flask review gate and wait for a decision.")
    review_parser.add_argument("--interface-dir", type=Path, default=Path("interface_design"))
    review_parser.add_argument("--project-dir", type=Path)
    review_parser.add_argument("--title", default="第二阶段第二步：材料界面与计算文件审查")
    review_parser.add_argument("--start-port", type=int, default=5050)
    review_parser.add_argument("--timeout", type=float, default=0.0)

    selection_review_parser = subparsers.add_parser("review-selection", help="Review the selected lower/upper surfaces in an isolated browser gate.")
    selection_review_parser.add_argument("--interface-dir", type=Path, default=Path("interface_design"))
    selection_review_parser.add_argument("--project-dir", type=Path)
    selection_review_parser.add_argument("--title", default="Stage 2 step 2: interface surface selection review")
    selection_review_parser.add_argument("--start-port", type=int, default=5050)
    selection_review_parser.add_argument("--timeout", type=float, default=0.0)

    subparsers.add_parser("environment", help="Report structure-library availability without running scientific software.")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    result: dict[str, Any]
    try:
        if args.command == "environment":
            result = detect_structure_tools()
        elif args.command == "start":
            result = start(args.interface_dir.resolve(), args.stage1_planning_dir.resolve(), args.surface_dir.resolve())
        elif args.command == "select":
            result = record_selection(args.interface_dir.resolve(), selection_path=args.selection.resolve())
        elif args.command == "init-design":
            result = initialize_design(args.interface_dir.resolve(), args.design.resolve())
        elif args.command == "validate":
            design = read_json(args.design.resolve())
            if not isinstance(design, dict):
                raise InterfaceError("Design must be a JSON object.")
            errors, warnings = validate_design(args.interface_dir.resolve(), design, args.for_approval)
            result = {"valid": not errors, "errors": errors, "warnings": warnings}
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return 0 if not errors else 1
        elif args.command == "submit":
            design = read_json(args.edited_design.resolve())
            if not isinstance(design, dict):
                raise InterfaceError("Edited design must be a JSON object.")
            result = submit_design(args.interface_dir.resolve(), design, args.reason)
        elif args.command == "action":
            result = transition(args.interface_dir.resolve(), args.name, args.reason, args.version, args.confirmed_by)
        elif args.command == "serve":
            serve(args.interface_dir.resolve(), args.host, args.port, args.open_page)
            return 0
        elif args.command == "review":
            interface_dir = args.interface_dir.resolve()
            project_dir = args.project_dir.resolve() if args.project_dir else interface_dir.parent
            result = browser_review(interface_dir, project_dir, args.title, args.start_port, args.timeout)
        elif args.command == "review-selection":
            interface_dir = args.interface_dir.resolve()
            project_dir = args.project_dir.resolve() if args.project_dir else interface_dir.parent
            result = browser_review_selection(interface_dir, project_dir, args.title, args.start_port, args.timeout)
        else:
            raise InterfaceError(f"Unsupported command: {args.command}")
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (InterfaceError, OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
