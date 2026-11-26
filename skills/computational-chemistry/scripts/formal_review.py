#!/usr/bin/env python3
"""Version, review, approve, and judge formal calculation evidence batches.

This program only reads/writes workflow artifacts. It never invokes scientific or
post-processing software, generated scripts, MPI, schedulers, queues, remote
downloads, or background monitors.
"""

from __future__ import annotations

import argparse
import base64
import copy
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

WAITING_FOR_FORMAL_TASK_SELECTION = "WAITING_FOR_FORMAL_TASK_SELECTION"
FORMAL_TASK_GRAPH_GENERATED = "FORMAL_TASK_GRAPH_GENERATED"
FORMAL_INPUTS_GENERATED = "FORMAL_INPUTS_GENERATED"
REFERENCE_INPUTS_GENERATED = "REFERENCE_INPUTS_GENERATED"
HPC_SCRIPTS_GENERATED = "HPC_SCRIPTS_GENERATED"
FORMAL_STATIC_VALIDATION_COMPLETED = "FORMAL_STATIC_VALIDATION_COMPLETED"
WAITING_FOR_FORMAL_FILE_APPROVAL = "WAITING_FOR_FORMAL_FILE_APPROVAL"
FORMAL_CALCULATION_FILES_APPROVED = "FORMAL_CALCULATION_FILES_APPROVED"
WAITING_FOR_FORMAL_CALCULATION_RESULT = "WAITING_FOR_FORMAL_CALCULATION_RESULT"
FORMAL_CALCULATION_RESULT_RECEIVED = "FORMAL_CALCULATION_RESULT_RECEIVED"
FORMAL_RESULT_VALIDATED = "FORMAL_RESULT_VALIDATED"
FORMAL_RESULT_REJECTED = "FORMAL_RESULT_REJECTED"
FORMAL_FILES_REGENERATION_REQUIRED = "FORMAL_FILES_REGENERATION_REQUIRED"
NEXT_FORMAL_BATCH_READY = "NEXT_FORMAL_BATCH_READY"
FORMAL_EVIDENCE_NODE_COMPLETED = "FORMAL_EVIDENCE_NODE_COMPLETED"
FORMAL_CALCULATION_WORKFLOW_COMPLETED = "FORMAL_CALCULATION_WORKFLOW_COMPLETED"
FORMAL_REVIEW_REJECTED = "FORMAL_REVIEW_REJECTED"

VALID_STATES = {
    WAITING_FOR_FORMAL_TASK_SELECTION,
    FORMAL_TASK_GRAPH_GENERATED,
    FORMAL_INPUTS_GENERATED,
    REFERENCE_INPUTS_GENERATED,
    HPC_SCRIPTS_GENERATED,
    FORMAL_STATIC_VALIDATION_COMPLETED,
    WAITING_FOR_FORMAL_FILE_APPROVAL,
    WAITING_FOR_REVIEW_DECISION,
    FORMAL_REVIEW_REJECTED,
    FORMAL_CALCULATION_FILES_APPROVED,
    WAITING_FOR_FORMAL_CALCULATION_RESULT,
    FORMAL_CALCULATION_RESULT_RECEIVED,
    FORMAL_RESULT_VALIDATED,
    FORMAL_RESULT_REJECTED,
    FORMAL_FILES_REGENERATION_REQUIRED,
    NEXT_FORMAL_BATCH_READY,
    FORMAL_EVIDENCE_NODE_COMPLETED,
    FORMAL_CALCULATION_WORKFLOW_COMPLETED,
}

DECISIONS = {
    "FORMAL_RESULT_VALID_NEXT_BATCH": ("当前正式计算结果有效，可以生成下一批文件", NEXT_FORMAL_BATCH_READY),
    "FORMAL_RESULT_FILES_MISSING": ("当前结果缺少必要文件，需要补充文件后重新判断", FORMAL_CALCULATION_RESULT_RECEIVED),
    "FORMAL_REGENERATE_PARAMETERS": ("当前计算参数存在问题，需要重新生成正式计算文件", FORMAL_FILES_REGENERATION_REQUIRED),
    "FORMAL_REGENERATE_REFERENCES": ("参考体系设置不一致，需要重新生成并计算对照组", FORMAL_FILES_REGENERATION_REQUIRED),
    "FORMAL_ELECTRONIC_UNSTABLE": ("当前电子结构结果不稳定，需要调整数值参数", FORMAL_FILES_REGENERATION_REQUIRED),
    "FORMAL_RETURN_OPTIMIZATION_REVIEW": ("优化结构存在问题，需要返回几何优化结果审查", FORMAL_RESULT_REJECTED),
    "FORMAL_RETURN_INTERFACE_DESIGN": ("界面模型存在问题，需要返回材料界面设计阶段", FORMAL_RESULT_REJECTED),
    "FORMAL_RETURN_SURFACE_DESIGN": ("表面模型存在问题，需要返回材料表面设计阶段", FORMAL_RESULT_REJECTED),
    "FORMAL_EVIDENCE_NODE_COMPLETE": ("当前证据节点已经完成，可以进入下一证据节点", FORMAL_EVIDENCE_NODE_COMPLETED),
}

FORMAL_HANDOFF_PROMPT = """当前正式计算批次所需的结构文件、计算输入文件、参考体系文件、后处理文件和运行脚本已经生成，并完成静态检查。

请按照任务依赖和运行说明，在本地工作站或超算平台上自行执行计算。你不需要保持当前页面持续打开，但请保留本次对话。当前批次完成后，请返回本对话并上传实际使用的输入文件、主输出文件、错误日志及后续分析所需的电子密度、波函数或其他结果文件。

收到真实计算结果后，我会检查计算参数、程序结束状态、电子收敛、文件完整性、参考体系可比性和数据是否满足当前科学任务，并判断是否需要重新生成文件，还是可以进入下一批正式计算。"""

EXECUTION_FLAGS = {
    "calculation_executed_by_skill",
    "job_submitted_by_skill",
    "queue_queried_by_skill",
    "remote_result_retrieval",
    "background_monitoring",
}

PROHIBITED_ESTIMATE_KEYS = {
    "estimated_runtime",
    "runtime_hours",
    "estimated_memory",
    "memory_gb",
    "estimated_storage",
    "storage_gb",
}

FILE_ROOTS = {
    "calculation_inputs",
    "postprocess_inputs",
    "reference_systems",
    "hpc_scripts",
    "local_run_scripts",
    "dependencies",
    "validation",
}

SCRIPT_ROLES = {"hpc_script", "local_run_script"}
INPUT_ROLES = {"calculation_input", "reference_calculation_input"}
ALLOWED_FILE_ROLES = INPUT_ROLES | {
    "structure",
    "reference_structure",
    "postprocess_input",
    "hpc_script",
    "local_run_script",
    "dependency",
    "conversion_script",
    "extraction_script",
    "validation_record",
}

RESULT_FILE_ROLES = {
    "actual_input",
    "main_output",
    "stderr",
    "energy",
    "density",
    "wavefunction",
    "checkpoint",
    "restart",
    "dos",
    "pdos",
    "charge_partition",
    "cohp",
    "coop",
    "bond_order",
    "qtaim",
    "structure",
    "job_script",
    "postprocess_output",
    "other",
}

TASK_TYPES = {
    "geometry_optimization",
    "high_precision_scf",
    "binding_or_formation_energy",
    "charge_density_difference",
    "quantitative_charge",
    "dos_pdos",
    "cohp_coop_bonding",
    "qtaim",
    "adsorption_configuration_design",
    "classical_md",
    "approved_other",
}

OPTIMIZATION_PARAMETER_FIELDS = (
    "software",
    "software_version",
    "functional",
    "basis",
    "pseudopotential",
    "dispersion",
    "hubbard_u",
    "cutoffs",
    "k_points",
    "spin",
    "occupations",
    "fixed_atoms",
    "lattice",
    "total_charge",
    "boundary_conditions",
)

CORE_OPTIMIZATION_PARAMETER_FIELDS = {
    "software",
    "functional",
    "basis",
    "pseudopotential",
    "dispersion",
    "hubbard_u",
    "spin",
    "fixed_atoms",
    "lattice",
    "total_charge",
    "boundary_conditions",
}

TASK_SEMANTIC_REQUIREMENTS = {
    "high_precision_scf": {"primary_static_input"},
    "binding_or_formation_energy": {"composite_energy_input", "reference_energy_input"},
    "charge_density_difference": {"composite_density_input", "component_density_input", "cdd_postprocess_input"},
    "quantitative_charge": {"charge_density_input", "charge_analysis_input"},
    "dos_pdos": {"nscf_input", "dos_or_selected_pdos_input"},
    "cohp_coop_bonding": {"compatible_wavefunction_input", "selected_bonding_analysis_input"},
    "qtaim": {"qtaim_density_or_wavefunction_input", "qtaim_analysis_or_conversion_input"},
    "classical_md": {"md_stage_input"},
    "approved_other": {"approved_task_input"},
}

RETURN_ROUTES = {
    "FORMAL_RETURN_OPTIMIZATION_REVIEW": "RETURN_TO_OPTIMIZATION_RESULT_REVIEW",
    "FORMAL_RETURN_INTERFACE_DESIGN": "RETURN_TO_INTERFACE_REDESIGN",
    "FORMAL_RETURN_SURFACE_DESIGN": "RETURN_TO_SURFACE_REDESIGN",
}


class FormalError(RuntimeError):
    """Raise for user-correctable formal-workflow errors."""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_bytes(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_bytes(data)
    temporary.replace(path)


def write_text(path: Path, value: str) -> None:
    write_bytes(path, value.replace("\r\n", "\n").encode("utf-8"))


def write_json(path: Path, value: Any) -> None:
    write_text(path, json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def file_record(path: Path) -> dict[str, Any]:
    return {"path": str(path.resolve()), "sha256": sha256(path), "size_bytes": path.stat().st_size}


def verify_absolute_record(record: Any, label: str) -> Path:
    if not isinstance(record, dict):
        raise FormalError(f"{label} is not a file record.")
    path = Path(str(record.get("path", "")))
    if not path.is_file() or sha256(path) != str(record.get("sha256", "")):
        raise FormalError(f"Frozen file changed or disappeared: {label}")
    return path


def safe_relative_path(root: Path, raw_path: str) -> Path:
    if not raw_path or Path(raw_path).is_absolute():
        raise FormalError(f"Expected a non-empty relative path under {root}: {raw_path!r}")
    resolved = (root / raw_path).resolve()
    try:
        resolved.relative_to(root.resolve())
    except ValueError as exc:
        raise FormalError(f"Path escapes the formal workflow directory: {raw_path}") from exc
    return resolved


def safe_name(value: str) -> str:
    name = re.sub(r"[^A-Za-z0-9._-]+", "_", value.strip())
    return name.strip("._") or "artifact"


def flatten_text(value: Any) -> str:
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False, sort_keys=True) if value is not None else ""


def compact(value: Any, limit: int = 500) -> str:
    text = flatten_text(value).replace("\n", " ")
    return text if len(text) <= limit else text[: limit - 1] + "…"


def false_execution_flags() -> dict[str, bool]:
    return {name: False for name in sorted(EXECUTION_FLAGS)}


def reject_prohibited_fields(value: Any, label: str = "payload") -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            lowered = str(key).lower()
            if lowered in EXECUTION_FLAGS and item is not False:
                raise FormalError(f"{label}.{key} must be false when supplied.")
            if lowered in PROHIBITED_ESTIMATE_KEYS:
                raise FormalError(f"{label}.{key} is prohibited; do not estimate runtime, memory, or storage.")
            reject_prohibited_fields(item, f"{label}.{key}")
    elif isinstance(value, list):
        for index, item in enumerate(value):
            reject_prohibited_fields(item, f"{label}[{index}]")


def detect_structure_tools() -> dict[str, dict[str, Any]]:
    tools: dict[str, dict[str, Any]] = {}
    for module, distribution in (("ase", "ase"), ("pymatgen", "pymatgen"), ("spglib", "spglib"), ("numpy", "numpy")):
        available = importlib.util.find_spec(module) is not None
        version = None
        if available:
            try:
                version = importlib.metadata.version(distribution)
            except importlib.metadata.PackageNotFoundError:
                version = "available-version-unresolved"
        tools[module] = {"available": available, "version": version}
    return tools


def manifest_tree(root: Path, base: Path) -> list[dict[str, Any]]:
    return [
        {"path": path.relative_to(base).as_posix(), "sha256": sha256(path), "size_bytes": path.stat().st_size}
        for path in sorted(root.rglob("*"))
        if path.is_file()
    ]


def validate_manifest(base: Path, records: Any, label: str) -> list[dict[str, Any]]:
    if not isinstance(records, list):
        raise FormalError(f"{label} manifest is missing.")
    validated: list[dict[str, Any]] = []
    for index, record in enumerate(records):
        if not isinstance(record, dict):
            raise FormalError(f"{label}[{index}] is invalid.")
        path = safe_relative_path(base, str(record.get("path", "")))
        if not path.is_file() or sha256(path) != str(record.get("sha256", "")):
            raise FormalError(f"Manifest file changed or disappeared: {record.get('path')}")
        validated.append(copy.deepcopy(record))
    return validated


def status_path(formal_dir: Path) -> Path:
    return formal_dir / "formal_status.json"


def log_path(formal_dir: Path) -> Path:
    return formal_dir / "formal_change_log.json"


def load_status(formal_dir: Path) -> dict[str, Any]:
    path = status_path(formal_dir)
    if not path.is_file():
        raise FormalError("formal_status.json is missing; start the formal workflow first.")
    status = read_json(path)
    if not isinstance(status, dict) or status.get("status") not in VALID_STATES:
        raise FormalError(f"Unknown formal state: {status.get('status')!r}")
    return status


def append_log(formal_dir: Path, entry: dict[str, Any]) -> None:
    path = log_path(formal_dir)
    entries = read_json(path) if path.exists() else []
    if not isinstance(entries, list):
        raise FormalError("formal_change_log.json must contain a list.")
    entries.append(entry)
    write_json(path, entries)


def write_result_status_projection(formal_dir: Path, status: dict[str, Any]) -> None:
    """Write a non-authoritative current result-state projection for user inspection."""
    write_json(
        formal_dir / "formal_result_status.json",
        {
            "project_id": status.get("project_id"),
            "workflow_step": "stage2_step3_formal_result_projection",
            "status": status.get("status"),
            "active_batch_id": status.get("active_batch_id"),
            "latest_result_version": status.get("latest_result_version"),
            "latest_analysis_version": status.get("latest_analysis_version"),
            "decision_code": status.get("decision_code"),
            "decision_label": status.get("decision_label"),
            "awaiting_additional_files": status.get("awaiting_additional_files", False),
            "return_route": status.get("return_route"),
            "authoritative_state_file": str(status_path(formal_dir).resolve()),
            **false_execution_flags(),
            "updated_at": status.get("updated_at") or utc_now(),
        },
    )


def version_number(paths: list[Path], prefix: str) -> int:
    values: list[int] = []
    for path in paths:
        match = re.search(re.escape(prefix) + r"v(\d{3,})", path.stem)
        if match:
            values.append(int(match.group(1)))
    return max(values, default=0) + 1


def next_plan_version(formal_dir: Path) -> str:
    return f"v{version_number(list(formal_dir.glob('formal_calculation_plan_v*.json')), 'formal_calculation_plan_'):03d}"


def next_graph_version(formal_dir: Path) -> str:
    return f"v{version_number(list(formal_dir.glob('formal_task_graph_v*.json')), 'formal_task_graph_'):03d}"


def next_selection_version(formal_dir: Path) -> str:
    return f"v{version_number(list(formal_dir.glob('formal_batch_selection_v*.json')), 'formal_batch_selection_'):03d}"


def next_result_version(formal_dir: Path) -> str:
    return f"v{version_number(list(formal_dir.glob('formal_result_batch_v*.json')), 'formal_result_batch_'):03d}"


def next_analysis_version(formal_dir: Path) -> str:
    return f"v{version_number(list(formal_dir.glob('formal_result_analysis_v*.json')), 'formal_result_analysis_'):03d}"


def verify_stage1(planning_dir: Path) -> dict[str, Any]:
    paths = {
        "status": planning_dir / "stage1_status.json",
        "plan": planning_dir / "stage1_plan_approved.json",
        "markdown": planning_dir / "stage1_plan_approved.md",
        "approval": planning_dir / "stage1_approval_record.json",
    }
    missing = [name for name, path in paths.items() if not path.is_file()]
    if missing:
        raise FormalError("Stage-1 approved baseline is incomplete: " + ", ".join(missing))
    status = read_json(paths["status"])
    plan = read_json(paths["plan"])
    approval = read_json(paths["approval"])
    if status.get("status") != "APPROVED" or status.get("stage2_access") is not True:
        raise FormalError("Stage 1 is not APPROVED with stage2 access.")
    if str(status.get("project_id")) != str(plan.get("project_id")):
        raise FormalError("Stage-1 status and plan project IDs differ.")
    if approval.get("approved_plan_sha256") and approval.get("approved_plan_sha256") != sha256(paths["plan"]):
        raise FormalError("Stage-1 approved plan checksum differs from the approval record.")
    return {
        "project_id": plan.get("project_id"),
        "approved_version": status.get("approved_version") or approval.get("approved_plan_version"),
        "files": {name: file_record(path) for name, path in paths.items()},
        "plan": plan,
    }


def verify_surface(surface_dir: Path | None, project_id: Any) -> dict[str, Any] | None:
    if surface_dir is None:
        return None
    paths = {
        "status": surface_dir / "surface_status.json",
        "design": surface_dir / "surface_design_approved.json",
        "markdown": surface_dir / "surface_design_approved.md",
        "approval": surface_dir / "surface_approval_record.json",
    }
    missing = [name for name, path in paths.items() if not path.is_file()]
    if missing:
        raise FormalError("Approved surface baseline is incomplete: " + ", ".join(missing))
    status = read_json(paths["status"])
    design = read_json(paths["design"])
    approval = read_json(paths["approval"])
    reject_prohibited_fields(status, "surface_status")
    reject_prohibited_fields(approval, "surface_approval")
    if status.get("status") != "SURFACE_DESIGN_APPROVED":
        raise FormalError("Surface baseline is not SURFACE_DESIGN_APPROVED.")
    if str(status.get("project_id")) != str(project_id) or str(design.get("project_id")) != str(project_id):
        raise FormalError("Surface baseline project ID differs from stage 1.")
    if approval.get("approved_design_sha256") and approval.get("approved_design_sha256") != sha256(paths["design"]):
        raise FormalError("Approved surface checksum differs from the approval record.")
    records = {name: file_record(path) for name, path in paths.items()}
    for model in design.get("models", []) if isinstance(design.get("models"), list) else []:
        if not isinstance(model, dict) or model.get("classification") == "rejected":
            continue
        for index, record in enumerate(model.get("structure_files", []) if isinstance(model.get("structure_files"), list) else []):
            relative = str(record.get("path", "")) if isinstance(record, dict) else ""
            path = safe_relative_path(surface_dir, relative)
            if not path.is_file() or sha256(path) != str(record.get("sha256", "")):
                raise FormalError(f"Approved surface structure changed: model {model.get('id')} record {index}")
            records[f"structure_{model.get('id')}_{index}"] = file_record(path)
    return {"approved_version": status.get("approved_version") or approval.get("approved_version"), "files": records}


def verify_interface(interface_dir: Path | None, project_id: Any) -> dict[str, Any] | None:
    if interface_dir is None:
        return None
    paths = {
        "status": interface_dir / "interface_status.json",
        "design": interface_dir / "interface_design_approved.json",
        "parameters": interface_dir / "optimization_parameters_approved.json",
        "markdown": interface_dir / "interface_design_approved.md",
        "approval": interface_dir / "interface_file_approval_record.json",
    }
    missing = [name for name, path in paths.items() if not path.is_file()]
    if missing:
        raise FormalError("Approved interface baseline is incomplete: " + ", ".join(missing))
    status = read_json(paths["status"])
    design = read_json(paths["design"])
    approval = read_json(paths["approval"])
    reject_prohibited_fields(status, "interface_status")
    reject_prohibited_fields(approval, "interface_approval")
    if status.get("status") != "INTERFACE_FILES_APPROVED":
        raise FormalError("Interface baseline is not INTERFACE_FILES_APPROVED.")
    if str(status.get("project_id")) != str(project_id) or str(design.get("project_id")) != str(project_id):
        raise FormalError("Interface baseline project ID differs from stage 1.")
    expected = {
        "design": approval.get("approved_design_sha256"),
        "parameters": approval.get("approved_parameters_sha256"),
        "markdown": approval.get("approved_markdown_sha256"),
    }
    for name, checksum in expected.items():
        if checksum and sha256(paths[name]) != str(checksum):
            raise FormalError(f"Approved interface {name} checksum differs from the approval record.")
    records = {name: file_record(path) for name, path in paths.items()}
    manifests = approval.get("approved_file_manifests", {})
    if not isinstance(manifests, dict):
        raise FormalError("Approved interface manifests are missing.")
    for key in ("calculation_inputs_approved", "hpc_scripts_approved", "approved_interfaces"):
        validated = validate_manifest(interface_dir, manifests.get(key), key)
        actual_root = interface_dir / key
        if not actual_root.is_dir():
            raise FormalError(f"Approved interface directory is missing: {key}")
        actual = manifest_tree(actual_root, interface_dir)
        if {(item["path"], item["sha256"]) for item in validated} != {(item["path"], item["sha256"]) for item in actual}:
            raise FormalError(f"Approved interface directory differs from its frozen manifest: {key}")
        for index, record in enumerate(validated):
            records[f"{key}_{index}"] = file_record(safe_relative_path(interface_dir, str(record["path"])))
    return {"approved_version": approval.get("approved_version") or status.get("approved_version"), "files": records}


def verify_accepted_result(results_dir: Path, project_id: Any) -> dict[str, Any]:
    status_file = results_dir / "result_status.json"
    if not status_file.is_file():
        raise FormalError("Accepted optimization result status is missing.")
    status = read_json(status_file)
    reject_prohibited_fields(status, "optimization_result_status")
    if status.get("status") != "OPTIMIZED_STRUCTURE_ACCEPTED" or status.get("next_task_access") is not True:
        raise FormalError("Optimization result is not OPTIMIZED_STRUCTURE_ACCEPTED.")
    if str(status.get("project_id")) != str(project_id):
        raise FormalError("Accepted optimization result project ID differs from stage 1.")
    version = str(status.get("latest_analysis_version", ""))
    analysis_path = results_dir / f"result_analysis_{version}.json"
    if not analysis_path.is_file() or sha256(analysis_path) != str(status.get("latest_analysis_sha256", "")):
        raise FormalError("Accepted optimization analysis changed or disappeared.")
    analysis = read_json(analysis_path)
    accepted: list[dict[str, Any]] = []
    for index, record in enumerate(analysis.get("judged_structure_records", [])):
        if not isinstance(record, dict):
            raise FormalError(f"Accepted structure record {index} is invalid.")
        path = safe_relative_path(results_dir, str(record.get("path", "")))
        if not path.is_file() or sha256(path) != str(record.get("sha256", "")):
            raise FormalError(f"Accepted structure changed or disappeared: {record.get('path')}")
        accepted.append({**copy.deepcopy(record), "absolute_path": str(path.resolve())})
    if not accepted:
        raise FormalError("Accepted optimization analysis contains no final structure.")
    batch_version = str(analysis.get("result_batch_version", ""))
    batch_record = next((item for item in status.get("result_batches", []) if isinstance(item, dict) and item.get("version") == batch_version), None)
    if not batch_record:
        raise FormalError("Accepted optimization result batch is not recorded.")
    batch_path = results_dir / str(batch_record.get("path", ""))
    if not batch_path.is_file() or sha256(batch_path) != str(batch_record.get("sha256", "")):
        raise FormalError("Accepted optimization result batch changed or disappeared.")
    batch = read_json(batch_path)
    actual_inputs: list[dict[str, Any]] = []
    for item in batch.get("files", []) if isinstance(batch.get("files"), list) else []:
        if not isinstance(item, dict) or item.get("role") not in {"actual_input", "parameters"}:
            continue
        path = safe_relative_path(results_dir, str(item.get("stored_path", "")))
        if not path.is_file() or sha256(path) != str(item.get("sha256", "")):
            raise FormalError("Actual optimization input changed or disappeared.")
        actual_inputs.append({**copy.deepcopy(item), "absolute_path": str(path.resolve())})
    if not actual_inputs:
        raise FormalError("Accepted optimization has no preserved actual input/parameter file.")
    frozen = [file_record(status_file), file_record(analysis_path), file_record(batch_path)]
    frozen.extend(file_record(Path(item["absolute_path"])) for item in accepted + actual_inputs)
    gate = status.get("delivery_gate", {})
    if not isinstance(gate, dict):
        raise FormalError("Optimization result delivery gate is missing.")
    for index, record in enumerate(gate.get("frozen_files", [])):
        path = verify_absolute_record(record, f"optimization delivery frozen file {index}")
        frozen.append(file_record(path))
    return {
        "results_dir": str(results_dir.resolve()),
        "status": "OPTIMIZED_STRUCTURE_ACCEPTED",
        "analysis_version": version,
        "analysis_sha256": sha256(analysis_path),
        "accepted_structures": accepted,
        "actual_optimization_inputs": actual_inputs,
        "actual_input_check": copy.deepcopy(analysis.get("actual_input_check")),
        "acceptance_conditions": copy.deepcopy(analysis.get("acceptance_conditions")),
        "completed_task_ids": [str(value) for value in analysis.get("completed_task_ids", [])] if isinstance(analysis.get("completed_task_ids"), list) else [],
        "software": analysis.get("software"),
        "frozen_files": frozen,
    }


def collect_frozen_files(*gates: Any) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for gate in gates:
        if not isinstance(gate, dict):
            continue
        candidates: list[dict[str, Any]] = []
        if isinstance(gate.get("files"), dict):
            candidates.extend(record for record in gate["files"].values() if isinstance(record, dict))
        if isinstance(gate.get("frozen_files"), list):
            candidates.extend(record for record in gate["frozen_files"] if isinstance(record, dict))
        for record in candidates:
            key = (str(record.get("path")), str(record.get("sha256")))
            if key not in seen:
                records.append(copy.deepcopy(record))
                seen.add(key)
    return records


def verify_frozen_gate(status: dict[str, Any]) -> None:
    gate = status.get("entry_gate")
    if not isinstance(gate, dict):
        raise FormalError("Formal entry gate is missing.")
    for index, record in enumerate(gate.get("frozen_files", [])):
        verify_absolute_record(record, f"entry_gate.frozen_files[{index}]")
    if read_json(Path(gate["stage1"]["files"]["status"]["path"])).get("status") != "APPROVED":
        raise FormalError("Stage-1 approval gate is no longer valid.")
    result_status = read_json(Path(gate["optimization_result"]["results_dir"]) / "result_status.json")
    if result_status.get("status") != "OPTIMIZED_STRUCTURE_ACCEPTED":
        raise FormalError("Accepted optimization result gate is no longer valid.")


def infer_task_type(task: dict[str, Any]) -> str:
    text = " ".join(
        flatten_text(task.get(key)).lower()
        for key in ("name", "module", "method", "target_parameters", "target_data_forms", "scientific_meaning", "evidence_role")
    )
    if any(token in text for token in ("geometry optimization", "结构优化", "几何优化", "relax", "vc-relax")):
        return "geometry_optimization"
    if any(token in text for token in ("adsorption configuration", "吸附构型", "吸附位点", "构型筛选")):
        return "adsorption_configuration_design"
    if any(token in text for token in ("cohp", "coop", "bond order", "键级", "成键分析")):
        return "cohp_coop_bonding"
    if any(token in text for token in ("qtaim", "atoms in molecules", "拓扑分析")):
        return "qtaim"
    if any(token in text for token in ("pdos", "density of states", "dos", "态密度")):
        return "dos_pdos"
    if any(token in text for token in ("charge density difference", "cdd", "电荷密度差", "差分电荷")):
        return "charge_density_difference"
    if any(token in text for token in ("bader", "hirshfeld", "npa", "charge partition", "定量电荷")):
        return "quantitative_charge"
    if any(token in text for token in ("binding energy", "formation energy", "adsorption energy", "结合能", "形成能", "吸附能")):
        return "binding_or_formation_energy"
    if any(token in text for token in ("molecular dynamics", "gromacs", "lammps", "分子动力学", "nvt", "npt")):
        return "classical_md"
    if any(token in text for token in ("single point", "static scf", "高精度", "静态单点", "scf")):
        return "high_precision_scf"
    return "approved_other"


def task_is_deleted(task: dict[str, Any]) -> bool:
    text = " ".join((flatten_text(task.get("status")), flatten_text(task.get("necessity")), flatten_text(task.get("redundancy")))).lower()
    return any(token in text for token in ("deleted", "rejected", "delete", "删除", "拒绝"))


def task_is_necessary(node: dict[str, Any]) -> bool:
    text = f"{flatten_text(node.get('necessity'))} {flatten_text(node.get('priority'))}".lower()
    return any(token in text for token in ("necessary", "required", "core", "foundation", "必要", "核心", "基础"))


def route_task_ids(value: Any, valid_ids: set[str], ordered: list[str]) -> None:
    if isinstance(value, str):
        if value in valid_ids and value not in ordered:
            ordered.append(value)
    elif isinstance(value, list):
        for item in value:
            route_task_ids(item, valid_ids, ordered)
    elif isinstance(value, dict):
        for key in ("task_id", "task_ids", "tasks", "steps", "route", "sequence", "parallel", "branches"):
            if key in value:
                route_task_ids(value[key], valid_ids, ordered)
        for key, item in value.items():
            if key not in {"task_id", "task_ids", "tasks", "steps", "route", "sequence", "parallel", "branches"}:
                route_task_ids(item, valid_ids, ordered)


def topological_order(nodes: list[dict[str, Any]], preferred_order: list[str] | None = None) -> list[str]:
    ids: set[str] = {str(node.get("task_id")) for node in nodes}
    rank = {task_id: index for index, task_id in enumerate(preferred_order or [])}

    def order_key(task_id: str) -> tuple[int, str]:
        return rank.get(task_id, len(rank)), task_id

    incoming: dict[str, set[str]] = {task_id: set() for task_id in ids}
    outgoing: dict[str, set[str]] = {task_id: set() for task_id in ids}
    for node in nodes:
        task_id = str(node.get("task_id"))
        for dependency in node.get("prerequisites", []):
            dep = str(dependency)
            if dep not in ids:
                raise FormalError(f"Retained task {task_id} references missing/deleted prerequisite {dep}.")
            incoming[task_id].add(dep)
            outgoing[dep].add(task_id)
    ready = sorted((task_id for task_id, deps in incoming.items() if not deps), key=order_key)
    ordered: list[str] = []
    while ready:
        current = ready.pop(0)
        ordered.append(current)
        for downstream in sorted(outgoing[current], key=order_key):
            incoming[downstream].discard(current)
            if not incoming[downstream] and downstream not in ordered and downstream not in ready:
                ready.append(downstream)
                ready.sort(key=order_key)
    if len(ordered) != len(ids):
        raise FormalError("The approved retained task graph contains a dependency cycle.")
    return ordered


def build_task_graph(stage1_gate: dict[str, Any], optimization_gate: dict[str, Any]) -> dict[str, Any]:
    plan = stage1_gate["plan"]
    all_tasks = [task for task in plan.get("tasks", []) if isinstance(task, dict)]
    retained = [task for task in all_tasks if not task_is_deleted(task)]
    ids = [str(task.get("id", "")) for task in retained]
    if any(not task_id for task_id in ids) or len(set(ids)) != len(ids):
        raise FormalError("Every retained stage-1 task requires a unique nonempty ID.")
    inferred_types = {str(task.get("id")): infer_task_type(task) for task in retained}
    geometry_ids = [task_id for task_id, task_type in inferred_types.items() if task_type == "geometry_optimization"]
    accepted_from_result = {str(value) for value in optimization_gate.get("completed_task_ids", [])}
    if not accepted_from_result and len(geometry_ids) == 1:
        accepted_from_result.add(geometry_ids[0])
    elif not accepted_from_result and len(geometry_ids) > 1:
        raise FormalError("Multiple retained geometry-optimization tasks exist; the accepted result must identify completed_task_ids explicitly.")
    unknown_completed = accepted_from_result - set(ids)
    if unknown_completed:
        raise FormalError("Accepted optimization result names tasks absent from the retained stage-1 graph: " + ", ".join(sorted(unknown_completed)))
    nodes: list[dict[str, Any]] = []
    for task in retained:
        task_type = inferred_types[str(task.get("id"))]
        node = {
            "task_id": str(task.get("id")),
            "task_name": task.get("name"),
            "task_type": task_type,
            "scientific_question_id": task.get("scientific_question_id"),
            "software": task.get("software"),
            "module": task.get("module"),
            "method": copy.deepcopy(task.get("method")),
            "systems": copy.deepcopy(task.get("systems", [])),
            "controls": copy.deepcopy(task.get("controls", [])),
            "target_parameters": copy.deepcopy(task.get("target_parameters")),
            "target_data_forms": copy.deepcopy(task.get("target_data_forms")),
            "scientific_meaning": task.get("scientific_meaning"),
            "supported_conclusions": copy.deepcopy(task.get("supported_conclusions")),
            "evidence_role": task.get("evidence_role"),
            "prerequisites": [str(value) for value in task.get("prerequisites", [])] if isinstance(task.get("prerequisites"), list) else [],
            "downstream_dependencies": [str(value) for value in task.get("downstream_dependencies", [])] if isinstance(task.get("downstream_dependencies"), list) else [],
            "priority": copy.deepcopy(task.get("priority")),
            "necessity": copy.deepcopy(task.get("necessity")),
            "stage1_status": task.get("status"),
            "status": "accepted" if str(task.get("id")) in accepted_from_result else "pending",
            "attempts": [],
        }
        nodes.append(node)
    preferred: list[str] = []
    route_task_ids(plan.get("execution_route"), set(ids), preferred)
    preferred.extend(task_id for task_id in ids if task_id not in preferred)
    ordered = topological_order(nodes, preferred)
    node_ids = set(ids)
    edges = [{"from": dep, "to": node["task_id"]} for node in nodes for dep in node["prerequisites"]]
    evidence_nodes: list[dict[str, Any]] = []
    for item in plan.get("evidence_chain", []) if isinstance(plan.get("evidence_chain"), list) else []:
        if not isinstance(item, dict) or not item.get("id"):
            continue
        task_ids = [str(task_id) for task_id in item.get("task_ids", []) if str(task_id) in node_ids]
        evidence_nodes.append({
            "id": str(item.get("id")),
            "role": item.get("role"),
            "task_ids": task_ids,
            "supports": item.get("supports"),
            "required": item.get("required") is True,
            "completion_rule": item.get("completion_rule", "all"),
            "status": "pending",
        })
    completed = sorted(node["task_id"] for node in nodes if node["status"] == "accepted")
    graph = {
        "project_id": plan.get("project_id"),
        "source_stage1_plan": stage1_gate["files"]["plan"],
        "nodes": nodes,
        "edges": edges,
        "evidence_nodes": evidence_nodes,
        "deleted_task_ids": [str(task.get("id")) for task in all_tasks if task_is_deleted(task) and task.get("id")],
        "source_execution_route": copy.deepcopy(plan.get("execution_route")),
        "source_execution_order": preferred,
        "topological_order": ordered,
        "completed_task_ids": completed,
        "completed_evidence_node_ids": [],
        "generated_at": utc_now(),
    }
    refresh_evidence_nodes(graph)
    return graph


def refresh_evidence_nodes(graph: dict[str, Any]) -> list[str]:
    accepted = {str(node.get("task_id")) for node in graph.get("nodes", []) if isinstance(node, dict) and node.get("status") == "accepted"}
    completed: list[str] = []
    for item in graph.get("evidence_nodes", []):
        if not isinstance(item, dict):
            continue
        tasks = {str(value) for value in item.get("task_ids", [])}
        done = bool(tasks) and (bool(tasks & accepted) if item.get("completion_rule") == "any" else tasks.issubset(accepted))
        item["status"] = "completed" if done else "pending"
        if done:
            completed.append(str(item.get("id")))
    graph["completed_task_ids"] = sorted(accepted)
    graph["completed_evidence_node_ids"] = sorted(completed)
    return completed


def write_graph_snapshot(formal_dir: Path, graph: dict[str, Any], event: str) -> str:
    version = next_graph_version(formal_dir)
    snapshot = copy.deepcopy(graph)
    snapshot["graph_version"] = version
    snapshot["snapshot_event"] = event
    snapshot["updated_at"] = utc_now()
    write_json(formal_dir / f"formal_task_graph_{version}.json", snapshot)
    write_json(formal_dir / "formal_task_graph.json", snapshot)
    return version


def load_graph(formal_dir: Path) -> dict[str, Any]:
    path = formal_dir / "formal_task_graph.json"
    if not path.is_file():
        raise FormalError("formal_task_graph.json is missing.")
    graph = read_json(path)
    if not isinstance(graph, dict):
        raise FormalError("Formal task graph is invalid.")
    derived = topological_order([node for node in graph.get("nodes", []) if isinstance(node, dict)], [str(value) for value in graph.get("source_execution_order", [])])
    if derived != [str(value) for value in graph.get("topological_order", [])]:
        raise FormalError("Formal task graph topological order changed or is inconsistent.")
    return graph


def review_asset_path() -> Path:
    return Path(__file__).resolve().parent.parent / "assets" / "formal_review.html"


def ensure_review_html(formal_dir: Path) -> None:
    source = review_asset_path()
    if not source.is_file():
        raise FormalError(f"Formal review asset is missing: {source}")
    shutil.copyfile(source, formal_dir / "formal_review.html")


def start(
    formal_dir: Path,
    planning_dir: Path,
    results_dir: Path,
    surface_dir: Path | None = None,
    interface_dir: Path | None = None,
) -> dict[str, Any]:
    if status_path(formal_dir).exists():
        raise FormalError("Formal workflow already exists; start will not overwrite it.")
    stage1 = verify_stage1(planning_dir.resolve())
    surface = verify_surface(surface_dir.resolve() if surface_dir else None, stage1["project_id"])
    interface = verify_interface(interface_dir.resolve() if interface_dir else None, stage1["project_id"])
    if surface is None and interface is None:
        # Molecule/cluster workflows may legitimately have neither material-model gate.
        systems_text = flatten_text(stage1["plan"].get("systems", [])).lower()
        if any(token in systems_text for token in ("surface", "interface", "slab", "表面", "界面")):
            raise FormalError("The approved plan contains a material surface/interface but no corresponding approved baseline was supplied.")
    result = verify_accepted_result(results_dir.resolve(), stage1["project_id"])
    graph = build_task_graph(stage1, result)
    pending_formal = [node for node in graph["nodes"] if node["status"] == "pending"]
    if not pending_formal:
        raise FormalError("The stage-1 plan contains no retained formal task after accepted optimization.")
    formal_dir.mkdir(parents=True, exist_ok=True)
    for name in (
        "versions",
        "approved_batches",
        "approved_alias_history",
        "user_results",
        "parsed_results",
        "accepted_results",
        "rejected_results",
        "regenerated_inputs",
        "result_analysis",
    ):
        (formal_dir / name).mkdir(parents=True, exist_ok=True)
    ensure_review_html(formal_dir)
    stage1_snapshot = {key: value for key, value in stage1.items() if key != "plan"}
    frozen = collect_frozen_files(stage1_snapshot, surface, interface, result)
    entry_gate = {
        "stage1": stage1_snapshot,
        "surface": surface,
        "interface": interface,
        "optimization_result": result,
        "frozen_files": frozen,
    }
    graph_version = write_graph_snapshot(formal_dir, graph, "FORMAL_WORKFLOW_STARTED")
    status = {
        "project_id": stage1["project_id"],
        "workflow_step": "stage2_step3_formal_calculations",
        "status": WAITING_FOR_FORMAL_TASK_SELECTION,
        "entry_gate": entry_gate,
        "current_graph_version": graph_version,
        "current_selection_version": None,
        "current_candidate_version": None,
        "previous_version": None,
        "previous_valid_version": None,
        "active_batch_id": None,
        "active_approval": None,
        "latest_result_version": None,
        "latest_analysis_version": None,
        "awaiting_additional_files": False,
        "return_route": None,
        "validation_errors": [],
        "validation_warnings": [],
        "last_impact_level": None,
        "detected_structure_tools": detect_structure_tools(),
        **false_execution_flags(),
        "updated_at": utc_now(),
    }
    write_json(status_path(formal_dir), status)
    write_result_status_projection(formal_dir, status)
    write_json(log_path(formal_dir), [{"event": "FORMAL_WORKFLOW_STARTED", "timestamp": utc_now(), "status_before": None, "status_after": WAITING_FOR_FORMAL_TASK_SELECTION, "graph_version": graph_version, **false_execution_flags()}])
    return {"status": status, "task_graph": graph}


def graph_node_map(graph: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {str(node.get("task_id")): node for node in graph.get("nodes", []) if isinstance(node, dict) and node.get("task_id")}


def ready_task_ids(graph: dict[str, Any], include_regeneration: bool = False) -> list[str]:
    nodes = graph_node_map(graph)
    accepted = {task_id for task_id, node in nodes.items() if node.get("status") == "accepted"}
    allowed_statuses = {"pending"} | ({"regeneration_required"} if include_regeneration else set())
    return [
        task_id
        for task_id in graph.get("topological_order", [])
        if task_id in nodes
        and nodes[task_id].get("status") in allowed_statuses
        and set(str(value) for value in nodes[task_id].get("prerequisites", [])).issubset(accepted)
    ]


def load_selection(formal_dir: Path, status: dict[str, Any]) -> dict[str, Any]:
    record = status.get("current_selection_record")
    path = verify_absolute_record(record, "current formal batch selection")
    selection = read_json(path)
    if not isinstance(selection, dict):
        raise FormalError("Current formal batch selection is invalid.")
    return selection


def select_batch(formal_dir: Path, source_path: Path | None = None, source_value: dict[str, Any] | None = None) -> dict[str, Any]:
    status = load_status(formal_dir)
    verify_frozen_gate(status)
    allowed = {
        WAITING_FOR_FORMAL_TASK_SELECTION,
        NEXT_FORMAL_BATCH_READY,
        FORMAL_EVIDENCE_NODE_COMPLETED,
        FORMAL_FILES_REGENERATION_REQUIRED,
    }
    if status["status"] not in allowed:
        raise FormalError(f"Batch selection is not allowed from {status['status']}.")
    source = copy.deepcopy(source_value) if source_value is not None else read_json(source_path) if source_path else None
    if not isinstance(source, dict):
        raise FormalError("Batch selection must be a JSON object.")
    reject_prohibited_fields(source, "batch_selection")
    if source.get("user_selected") is not True or not str(source.get("reason", "")).strip():
        raise FormalError("Batch selection requires user_selected: true and a nonempty reason.")
    selected = [str(value) for value in source.get("selected_task_ids", [])] if isinstance(source.get("selected_task_ids"), list) else []
    if not selected or len(set(selected)) != len(selected):
        raise FormalError("selected_task_ids must be a nonempty unique list.")
    graph = load_graph(formal_dir)
    nodes = graph_node_map(graph)
    ready = ready_task_ids(graph, include_regeneration=status["status"] == FORMAL_FILES_REGENERATION_REQUIRED)
    invalid = sorted(set(selected) - set(ready))
    if invalid:
        raise FormalError("Selected tasks are not prerequisite-ready retained tasks: " + ", ".join(invalid))
    selected_nodes = [nodes[task_id] for task_id in selected]
    task_types = {str(node.get("task_type")) for node in selected_nodes}
    if "adsorption_configuration_design" in task_types and len(task_types) > 1:
        raise FormalError("Adsorption configuration design must be routed as its own batch.")
    optional = [node["task_id"] for node in selected_nodes if not task_is_necessary(node)]
    if optional and source.get("include_supplemental_tasks") is not True:
        raise FormalError("Selecting optional/conditional tasks requires include_supplemental_tasks: true.")
    version = next_selection_version(formal_dir)
    ordinal = int(version[1:])
    primary = safe_name(sorted(task_types)[0])[:36]
    batch_id = f"batch_{ordinal:02d}_{primary}"
    selection = {
        "project_id": status["project_id"],
        "workflow_step": "stage2_step3_formal_batch_selection",
        "selection_version": version,
        "batch_id": batch_id,
        "selected_task_ids": selected,
        "selected_tasks": copy.deepcopy(selected_nodes),
        "ready_task_ids_at_selection": ready,
        "origin_task_statuses": {task_id: nodes[task_id].get("status") for task_id in selected},
        "selection_origin_state": status["status"],
        "user_selected": True,
        "reason": str(source["reason"]),
        "include_supplemental_tasks": source.get("include_supplemental_tasks") is True,
        "user_notes": source.get("user_notes", ""),
        "route": "ADSORPTION_CONFIGURATION_DESIGN_REQUIRED" if task_types == {"adsorption_configuration_design"} else "FORMAL_FILES_REQUIRED",
        **false_execution_flags(),
        "selected_at": utc_now(),
    }
    path = formal_dir / f"formal_batch_selection_{version}.json"
    write_json(path, selection)
    old = status["status"]
    status.update(
        {
            "status": FORMAL_TASK_GRAPH_GENERATED,
            "current_selection_version": version,
            "current_selection_record": file_record(path),
            "selection_review_confirmed": False,
            "active_batch_id": batch_id,
            "current_candidate_version": None,
            "previous_version": None,
            "previous_valid_version": None,
            "current_result_record": None,
            "validation_errors": [],
            "validation_warnings": [],
            "awaiting_additional_files": False,
            "return_route": None,
            **false_execution_flags(),
            "updated_at": utc_now(),
        }
    )
    write_json(status_path(formal_dir), status)
    write_result_status_projection(formal_dir, status)
    append_log(formal_dir, {"event": "FORMAL_BATCH_SELECTED", "timestamp": utc_now(), "batch_id": batch_id, "selection_version": version, "task_ids": selected, "reason": source["reason"], "status_before": old, "status_after": FORMAL_TASK_GRAPH_GENERATED, **false_execution_flags()})
    return {"status": status, "selection": selection}


def inspect_structure(path: Path) -> dict[str, Any]:
    errors: list[str] = []
    if importlib.util.find_spec("ase") is not None:
        try:
            from ase.io import read as ase_read

            atoms_result = ase_read(str(path), index=-1)
            if isinstance(atoms_result, list):
                if not atoms_result:
                    raise FormalError("ASE returned no structures.")
                atoms = atoms_result[-1]
            else:
                atoms = atoms_result
            symbols = atoms.get_chemical_symbols()
            cell = atoms.cell.array.tolist()
            periodic = [bool(value) for value in atoms.pbc]
            result: dict[str, Any] = {
                "reader": "ase",
                "atom_count": len(symbols),
                "elements": sorted(set(symbols)),
                "formula": atoms.get_chemical_formula(),
                "periodic": periodic,
                "cell": cell,
            }
            if any(periodic) and importlib.util.find_spec("spglib") is not None:
                try:
                    import spglib

                    numbers = atoms.get_atomic_numbers().tolist()
                    dataset = spglib.get_symmetry_dataset((atoms.cell.array, atoms.get_scaled_positions(), numbers))
                    if dataset is not None:
                        result["space_group"] = str(dataset.international)
                        result["space_group_number"] = int(dataset.number)
                except Exception as exc:  # static optional enrichment only
                    result["symmetry_note"] = f"spglib static inspection unavailable: {exc}"
            return result
        except Exception as exc:
            errors.append(f"ASE: {exc}")
    if importlib.util.find_spec("pymatgen") is not None:
        try:
            from pymatgen.core import Molecule, Structure

            try:
                structure = Structure.from_file(str(path))
                return {
                    "reader": "pymatgen.Structure",
                    "atom_count": len(structure),
                    "elements": sorted(str(element) for element in structure.composition.elements),
                    "formula": structure.composition.reduced_formula,
                    "periodic": [True, True, True],
                    "cell": structure.lattice.matrix.tolist(),
                }
            except Exception:
                molecule = Molecule.from_file(str(path))
                return {
                    "reader": "pymatgen.Molecule",
                    "atom_count": len(molecule),
                    "elements": sorted(str(element) for element in molecule.composition.elements),
                    "formula": molecule.composition.reduced_formula,
                    "periodic": [False, False, False],
                    "cell": None,
                }
        except Exception as exc:
            errors.append(f"pymatgen: {exc}")
    raise FormalError("Accepted structure is not readable by available structure tools: " + "; ".join(errors or ["ASE/pymatgen unavailable"]))


def replace_version_token(raw_path: str, version: str) -> str:
    return raw_path.replace("{version}", version).replace("__VERSION__", version)


def validate_scheduler_configuration(value: Any) -> list[str]:
    errors: list[str] = []
    if value in (None, {}, []):
        return errors
    if not isinstance(value, dict):
        return ["scheduler_configuration must be an object."]
    scheduler = str(value.get("scheduler", "")).lower()
    if scheduler not in {"slurm", "pbs", "lsf", "none", "not_applicable"}:
        errors.append("scheduler_configuration.scheduler must be slurm, pbs, lsf, none, or not_applicable.")
    fields = value.get("fields", {})
    if scheduler in {"slurm", "pbs", "lsf"} and not isinstance(fields, dict):
        errors.append("scheduler_configuration.fields must be an object for a scheduler.")
    elif isinstance(fields, dict):
        for name, record in fields.items():
            if not isinstance(record, dict) or "value" not in record or record.get("source") not in {"user", "existing_script", "approved_record", "placeholder"}:
                errors.append(f"scheduler field {name} requires value and source=user/existing_script/approved_record/placeholder.")
    return errors


def validate_optimization_parameter_matrix(source: dict[str, Any], status: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    matrix = copy.deepcopy(source.get("optimization_parameter_matrix"))
    blockers: list[str] = []
    if not isinstance(matrix, dict):
        return {}, ["optimization_parameter_matrix is required before formal file approval."]
    actual_inputs = status["entry_gate"]["optimization_result"].get("actual_optimization_inputs", [])
    actual_hashes = {str(item.get("sha256")) for item in actual_inputs if isinstance(item, dict)}
    source_record = source.get("optimization_parameter_source")
    if not isinstance(source_record, dict) or str(source_record.get("sha256", "")) not in actual_hashes:
        blockers.append("optimization_parameter_source must cite a preserved actual optimization input checksum.")
    allowed = {"match", "difference_reapproved", "difference_numerical", "not_applicable", "unknown"}
    for field in OPTIMIZATION_PARAMETER_FIELDS:
        item = matrix.get(field)
        if not isinstance(item, dict):
            blockers.append(f"optimization_parameter_matrix.{field} is required.")
            continue
        for key in ("approved_value", "actual_value", "status", "scientific_impact", "source"):
            if key not in item:
                blockers.append(f"optimization_parameter_matrix.{field}.{key} is required.")
        comparison_status = item.get("status")
        if comparison_status not in allowed:
            blockers.append(f"optimization_parameter_matrix.{field}.status is invalid.")
            continue
        if comparison_status == "unknown":
            blockers.append(f"Actual optimization parameter remains unknown: {field}.")
        if field in CORE_OPTIMIZATION_PARAMETER_FIELDS and comparison_status == "difference_numerical":
            blockers.append(f"Core optimization setting {field} cannot be treated as an ordinary numerical difference.")
        if comparison_status == "difference_reapproved":
            try:
                verify_absolute_record(item.get("reapproval_record"), f"optimization_parameter_matrix.{field}.reapproval_record")
            except FormalError as exc:
                blockers.append(str(exc))
        if comparison_status in {"difference_reapproved", "difference_numerical"} and not str(item.get("scientific_impact", "")).strip():
            blockers.append(f"Optimization parameter difference {field} requires a scientific-impact statement.")
    return matrix, blockers


def expected_defaults(task_type: str, reference_ids: list[str], has_projections: bool) -> list[dict[str, Any]]:
    defaults = [{"role": "actual_input", "required": True}, {"role": "main_output", "required": True}]
    if task_type == "high_precision_scf":
        defaults.append({"role": "energy", "required": True})
    elif task_type == "binding_or_formation_energy":
        defaults.append({"role": "energy", "system_id": "composite", "required": True})
        defaults.extend({"role": "energy", "system_id": reference_id, "required": True} for reference_id in reference_ids)
    elif task_type == "charge_density_difference":
        defaults.append({"role": "density", "system_id": "composite", "required": True})
        defaults.extend({"role": "density", "system_id": reference_id, "required": True} for reference_id in reference_ids)
        defaults.append({"role": "postprocess_output", "required": True})
    elif task_type == "quantitative_charge":
        defaults.append({"role": "charge_partition", "required": True})
    elif task_type == "dos_pdos":
        defaults.append({"role": "dos", "required": True})
        if has_projections:
            defaults.append({"role": "pdos", "required": True})
    elif task_type == "cohp_coop_bonding":
        defaults.extend(({"role": "wavefunction", "required": True}, {"role": "cohp", "required": True}))
    elif task_type == "qtaim":
        defaults.extend(({"role": "density", "required": True}, {"role": "qtaim", "required": True}))
    elif task_type == "classical_md":
        defaults.append({"role": "structure", "required": True})
    return defaults


def merge_expected_roles(source: Any, selected_nodes: list[dict[str, Any]], references: list[dict[str, Any]], projections: Any) -> dict[str, list[dict[str, Any]]]:
    supplied = source if isinstance(source, dict) else {}
    reference_ids = [str(item.get("id")) for item in references if isinstance(item, dict) and item.get("id")]
    merged: dict[str, list[dict[str, Any]]] = {}
    for node in selected_nodes:
        task_id = str(node["task_id"])
        values = copy.deepcopy(supplied.get(task_id, [])) if isinstance(supplied.get(task_id), list) else []
        defaults = expected_defaults(str(node["task_type"]), reference_ids, bool(projections))
        keys = {(str(item.get("role")), str(item.get("system_id", ""))) for item in values if isinstance(item, dict)}
        for item in defaults:
            key = (str(item.get("role")), str(item.get("system_id", "")))
            if key not in keys:
                values.append(item)
                keys.add(key)
        for index, item in enumerate(values):
            if not isinstance(item, dict) or item.get("role") not in RESULT_FILE_ROLES or item.get("required") is not True:
                raise FormalError(f"expected_result_roles.{task_id}[{index}] must define an allowed required role.")
        merged[task_id] = values
    return merged


def validate_task_contracts(plan: dict[str, Any], selected_nodes: list[dict[str, Any]], specs: list[dict[str, Any]]) -> list[str]:
    errors: list[str] = []
    by_task: dict[str, list[dict[str, Any]]] = {}
    for spec in specs:
        by_task.setdefault(str(spec.get("task_id")), []).append(spec)
    references = plan.get("reference_definitions", []) if isinstance(plan.get("reference_definitions"), list) else []
    reference_ids = {str(item.get("id")) for item in references if isinstance(item, dict) and item.get("id")}
    comparisons = plan.get("comparability_checks", {}) if isinstance(plan.get("comparability_checks"), dict) else {}
    for node in selected_nodes:
        task_id = str(node["task_id"])
        task_type = str(node["task_type"])
        semantic = {str(item.get("semantic_role")) for item in by_task.get(task_id, [])}
        missing = TASK_SEMANTIC_REQUIREMENTS.get(task_type, set()) - semantic
        if missing:
            errors.append(f"Task {task_id} ({task_type}) is missing semantic file roles: {', '.join(sorted(missing))}.")
        if task_type in {"binding_or_formation_energy", "charge_density_difference"}:
            if len(reference_ids) < 2:
                errors.append(f"Task {task_id} requires at least two explicit reference definitions.")
            expected_semantic = "reference_energy_input" if task_type == "binding_or_formation_energy" else "component_density_input"
            supplied_refs = {str(item.get("reference_id")) for item in by_task.get(task_id, []) if item.get("semantic_role") == expected_semantic}
            if not reference_ids.issubset(supplied_refs):
                errors.append(f"Task {task_id} does not generate every defined reference system: {', '.join(sorted(reference_ids - supplied_refs))}.")
        if task_type == "binding_or_formation_energy":
            for key in ("same_in_plane_cell", "same_strain", "same_supercell", "same_vacuum", "same_method", "same_numerical_parameters", "reference_positions_preserved"):
                if comparisons.get(key) is not True:
                    errors.append(f"Binding/formation task requires comparability_checks.{key}: true.")
        if task_type == "charge_density_difference":
            for key in ("same_lattice", "same_atomic_positions", "same_grid", "same_pseudopotential_or_basis", "same_cutoffs", "same_kpoints", "same_spin", "same_occupations"):
                if comparisons.get(key) is not True:
                    errors.append(f"CDD task requires comparability_checks.{key}: true.")
        if task_type == "dos_pdos":
            prereq_types = {str(item.get("task_type")) for item in selected_nodes if item.get("task_id") in node.get("prerequisites", [])}
            # Accepted prerequisites are checked from the graph separately; require an explicit SCF dependency declaration here.
            dependency_types = set(str(value) for value in plan.get("dependency_task_types", {}).get(task_id, [])) if isinstance(plan.get("dependency_task_types"), dict) else set()
            if "high_precision_scf" not in prereq_types | dependency_types:
                errors.append(f"DOS/PDOS task {task_id} must declare an accepted high_precision_scf dependency.")
        if task_type == "cohp_coop_bonding":
            for key in ("wavefunction_compatible", "projection_basis_defined", "bands_sufficient", "atom_indices_verified"):
                if comparisons.get(key) is not True:
                    errors.append(f"Bonding task requires comparability_checks.{key}: true.")
    return errors


def prepare_file_specs(
    formal_dir: Path,
    plan: dict[str, Any],
    selected_nodes: list[dict[str, Any]],
    version: str,
    accepted_structure: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[tuple[dict[str, Any], Path, bytes]], list[str]]:
    raw_specs = plan.get("file_specs")
    task_types = {str(node.get("task_type")) for node in selected_nodes}
    if task_types == {"adsorption_configuration_design"}:
        if raw_specs not in (None, []):
            raise FormalError("Adsorption configuration design cannot materialize arbitrary formal calculation files.")
        return [], [], []
    if not isinstance(raw_specs, list) or not raw_specs:
        raise FormalError("A formal calculation candidate requires file_specs.")
    selected_ids = {str(node["task_id"]) for node in selected_nodes}
    prepared: list[dict[str, Any]] = []
    payloads: list[tuple[dict[str, Any], Path, bytes]] = []
    warnings: list[str] = []
    checked_names = set()
    static = plan.get("static_validation", {})
    if isinstance(static, dict) and isinstance(static.get("files_checked"), list):
        checked_names = {replace_version_token(str(value), version) for value in static["files_checked"]}
    for index, item in enumerate(raw_specs):
        if not isinstance(item, dict):
            raise FormalError(f"file_specs[{index}] must be an object.")
        for key in ("path", "role", "task_id", "software", "source", "semantic_role"):
            if not str(item.get(key, "")).strip():
                raise FormalError(f"file_specs[{index}].{key} is required.")
        role = str(item["role"])
        task_id = str(item["task_id"])
        if role not in ALLOWED_FILE_ROLES:
            raise FormalError(f"file_specs[{index}].role is invalid: {role}")
        if task_id not in selected_ids and task_id != "BATCH":
            raise FormalError(f"file_specs[{index}] references an unselected task: {task_id}")
        path_template = str(item.get("path_template") or item["path"])
        relative = replace_version_token(path_template, version).replace("\\", "/")
        parts = Path(relative).parts
        if not parts or parts[0] not in FILE_ROOTS:
            raise FormalError(f"file_specs[{index}].path must start with an allowed formal directory.")
        if re.search(r"(?:^|[_-])(calc1|test_new|final2)(?:[_.-]|$)", Path(relative).stem, re.I):
            raise FormalError(f"Ambiguous formal filename is prohibited: {relative}")
        if version.lower() not in Path(relative).stem.lower():
            warnings.append(f"Generated filename does not contain {version}: {relative}")
        target = safe_relative_path(formal_dir / "versions" / version, relative)
        if "content" in item:
            if not isinstance(item["content"], str):
                raise FormalError(f"file_specs[{index}].content must be text.")
            data = item["content"].replace("{version}", version).replace("__VERSION__", version).encode("utf-8")
        elif "content_base64" in item:
            try:
                data = base64.b64decode(str(item["content_base64"]), validate=True)
            except ValueError as exc:
                raise FormalError(f"file_specs[{index}] has invalid base64 content.") from exc
        else:
            raise FormalError(f"file_specs[{index}] requires content or content_base64.")
        if not data:
            raise FormalError(f"file_specs[{index}] cannot be empty.")
        if checked_names and relative not in checked_names and Path(relative).name not in checked_names:
            raise FormalError(f"static_validation.files_checked omits {relative}.")
        if role in INPUT_ROLES | {"postprocess_input"}:
            structure_source = item.get("structure_source")
            if not isinstance(structure_source, dict) or structure_source.get("path") != accepted_structure.get("path") or structure_source.get("sha256") != accepted_structure.get("sha256"):
                raise FormalError(f"file_specs[{index}] must bind to the accepted structure path/checksum.")
        copied = copy.deepcopy(item)
        copied["path"] = relative
        copied["path_template"] = path_template
        copied["content_sha256"] = hashlib.sha256(data).hexdigest()
        prepared.append(copied)
        payloads.append((copied, target, data))
    roles = {str(item.get("role")) for item in prepared}
    if not roles.intersection(SCRIPT_ROLES):
        raise FormalError("Every formal batch requires an HPC or local external-run instruction script.")
    errors = validate_task_contracts(plan, selected_nodes, prepared)
    if errors:
        raise FormalError("Formal task contract validation failed:\n- " + "\n- ".join(errors))
    return prepared, payloads, warnings


def recursive_differences(before: Any, after: Any, path: str = "") -> list[dict[str, Any]]:
    changes: list[dict[str, Any]] = []
    if isinstance(before, dict) and isinstance(after, dict):
        for key in sorted(set(before) | set(after)):
            child = f"{path}.{key}" if path else str(key)
            if key not in before:
                changes.append({"path": child, "before": None, "after": copy.deepcopy(after[key])})
            elif key not in after:
                changes.append({"path": child, "before": copy.deepcopy(before[key]), "after": None})
            else:
                changes.extend(recursive_differences(before[key], after[key], child))
    elif isinstance(before, list) and isinstance(after, list):
        if before != after:
            changes.append({"path": path, "before": copy.deepcopy(before), "after": copy.deepcopy(after)})
    elif before != after:
        changes.append({"path": path, "before": copy.deepcopy(before), "after": copy.deepcopy(after)})
    return changes


def impact_for_path(path: str) -> tuple[str, str, str]:
    lowered = path.lower()
    high = ("accepted_structure", "lattice", "functional", "pseudopotential", "basis", "dispersion", "hubbard", "spin", "charge", "boundary", "reference_definitions", "selected_task_ids")
    medium = ("kpoint", "k_point", "cutoff", "grid", "projection", "output_requests", "energy_window", "smearing", "mixing", "electron", "file_specs")
    low = ("scheduler_configuration", "local_configuration", "user_notes", "name", "label", "path")
    if any(token in lowered for token in high):
        return "HIGH", "May change the scientific model, reference definition, or cross-system comparability.", "Return to the owning approval gate or explicitly reconfirm before approval."
    if any(token in lowered for token in medium):
        return "MEDIUM", "May change numerical convergence, output scope, or evidence interpretation.", "Regenerate all affected files and reassess dependent comparisons."
    if any(token in lowered for token in low):
        return "LOW", "Usually affects execution instructions, labels, or file organization.", "Static-check paths and user-supplied scheduler fields."
    return "MEDIUM", "The formal batch changed and its downstream impact requires review.", "Review affected task dependencies and result comparability."


def analyze_impact(before: dict[str, Any] | None, after: dict[str, Any], reason: str) -> dict[str, Any]:
    changes = recursive_differences(before or {}, after)
    levels = {"LOW": 1, "MEDIUM": 2, "HIGH": 3}
    overall = "LOW"
    for item in changes:
        level, impact, recommendation = impact_for_path(str(item.get("path", "")))
        item.update({"impact_level": level, "impact_reason": impact, "recommendation": recommendation})
        if levels[level] > levels[overall]:
            overall = level
    return {"modification_reason": reason, "overall_impact_level": overall, "changes": changes, "generated_at": utc_now()}


def validate_candidate_source(
    formal_dir: Path,
    status: dict[str, Any],
    source: dict[str, Any],
    selection: dict[str, Any],
    version: str,
) -> tuple[dict[str, Any], list[tuple[dict[str, Any], Path, bytes]], list[str], list[str]]:
    reject_prohibited_fields(source, "formal_candidate")
    graph = load_graph(formal_dir)
    nodes = graph_node_map(graph)
    selected_ids = [str(value) for value in selection["selected_task_ids"]]
    supplied_ids = [str(value) for value in source.get("selected_task_ids", selected_ids)] if isinstance(source.get("selected_task_ids", selected_ids), list) else []
    if supplied_ids != selected_ids:
        raise FormalError("Candidate selected_task_ids cannot differ from the user-confirmed batch selection.")
    selected_nodes = [copy.deepcopy(nodes[task_id]) for task_id in selected_ids]
    priority_overrides = copy.deepcopy(source.get("task_priority_overrides", {}))
    if not isinstance(priority_overrides, dict) or any(str(task_id) not in set(selected_ids) for task_id in priority_overrides):
        raise FormalError("task_priority_overrides must be an object keyed only by selected task IDs.")
    current = load_plan(formal_dir, status["current_candidate_version"]) if status.get("current_candidate_version") else None
    if current:
        protected_keys: tuple[str, ...] = (
            "project_id",
            "batch_id",
            "selected_task_ids",
            "selected_tasks",
            "prerequisite_snapshot",
            "accepted_structure",
            "accepted_structure_metadata",
            "actual_optimization_parameter_audit",
            "actual_optimization_inputs",
            "stage1_method_snapshot",
            "dependency_task_types",
            "route",
        )
        if source.get("version_source") == "RESTORE":
            protected_keys = ("project_id", "batch_id", "selected_task_ids", "accepted_structure")
        for key in protected_keys:
            if key in source and source.get(key) != current.get(key):
                raise FormalError(f"Protected candidate field cannot be edited: {key}")
        if source.get("version_source") != "RESTORE" and source.get("plan_version") != current.get("plan_version"):
            raise FormalError("Protected candidate field cannot be edited: plan_version")
    for key in ("completed_task_ids", "completed_evidence_node_ids", "workflow_completed", "result_state", "decision_code", "decision_label"):
        if key in source:
            raise FormalError(f"Engine-owned completion/decision field is prohibited in a formal candidate: {key}")
    purpose = str(source.get("batch_purpose", "")).strip()
    if not purpose:
        raise FormalError("batch_purpose is required.")
    references = copy.deepcopy(source.get("reference_definitions", []))
    if not isinstance(references, list):
        raise FormalError("reference_definitions must be a list.")
    reference_ids: set[str] = set()
    for index, item in enumerate(references):
        if not isinstance(item, dict) or any(not str(item.get(key, "")).strip() for key in ("id", "name", "system_id", "definition", "structure_origin")):
            raise FormalError(f"reference_definitions[{index}] requires id, name, system_id, definition, and structure_origin.")
        if str(item["id"]) in reference_ids:
            raise FormalError("Reference definition IDs must be unique.")
        reference_ids.add(str(item["id"]))
    accepted = copy.deepcopy(status["entry_gate"]["optimization_result"]["accepted_structures"][0])
    structure_path = Path(str(accepted["absolute_path"]))
    if not structure_path.is_file() or sha256(structure_path) != str(accepted["sha256"]):
        raise FormalError("Accepted structure changed or disappeared.")
    structure_metadata = inspect_structure(structure_path)
    static = copy.deepcopy(source.get("static_validation", {}))
    if not isinstance(static, dict):
        raise FormalError("static_validation must be an object.")
    blockers: list[str] = []
    for key in ("file_format", "parameter_logic", "task_dependencies"):
        if static.get(key) != "passed":
            blockers.append(f"static_validation.{key} must be passed before approval.")
    if static.get("reference_comparability") not in {"passed", "not_applicable"}:
        blockers.append("static_validation.reference_comparability must be passed or not_applicable before approval.")
    for key in ("files_checked", "pending_user_fields", "scientific_reconfirmation", "not_determinable"):
        if not isinstance(static.get(key), list):
            raise FormalError(f"static_validation.{key} must be a list.")
    pending_fields = copy.deepcopy(source.get("pending_fields", static.get("pending_user_fields", [])))
    if not isinstance(pending_fields, list):
        raise FormalError("pending_fields must be a list.")
    for item in pending_fields:
        if isinstance(item, dict) and item.get("required") is True and not str(item.get("value", "")).strip():
            blockers.append(f"Required pending field is unresolved: {item.get('field') or item.get('name')}")
    reconfirmation = copy.deepcopy(source.get("scientific_reconfirmation", static.get("scientific_reconfirmation", [])))
    if not isinstance(reconfirmation, list):
        raise FormalError("scientific_reconfirmation must be a list.")
    if reconfirmation:
        blockers.append("Scientific parameters require upstream reconfirmation before approval.")
    blockers.extend(validate_scheduler_configuration(source.get("scheduler_configuration", {})))
    parameter_matrix, parameter_blockers = validate_optimization_parameter_matrix(source, status)
    blockers.extend(parameter_blockers)
    plan = copy.deepcopy(source)
    plan.update(
        {
            "project_id": status["project_id"],
            "workflow_step": "stage2_step3_formal_calculations",
            "plan_version": version,
            "batch_id": selection["batch_id"],
            "selected_task_ids": selected_ids,
            "selected_tasks": selected_nodes,
            "task_priority_overrides": priority_overrides,
            "prerequisite_snapshot": {task_id: copy.deepcopy(nodes[task_id].get("prerequisites", [])) for task_id in selected_ids},
            "dependency_task_types": {
                task_id: [str(nodes[dependency].get("task_type")) for dependency in nodes[task_id].get("prerequisites", []) if dependency in nodes]
                for task_id in selected_ids
            },
            "accepted_structure": accepted,
            "accepted_structure_metadata": structure_metadata,
            "actual_optimization_parameter_audit": copy.deepcopy(status["entry_gate"]["optimization_result"]["actual_input_check"]),
            "actual_optimization_inputs": copy.deepcopy(status["entry_gate"]["optimization_result"]["actual_optimization_inputs"]),
            "optimization_parameter_matrix": parameter_matrix,
            "optimization_parameter_source": copy.deepcopy(source.get("optimization_parameter_source")),
            "stage1_method_snapshot": [{key: copy.deepcopy(node.get(key)) for key in ("task_id", "software", "module", "method", "target_parameters", "evidence_role")} for node in selected_nodes],
            "reference_definitions": references,
            "pending_fields": pending_fields,
            "scientific_reconfirmation": reconfirmation,
            "route": selection["route"],
            **false_execution_flags(),
            "version_record": {
                "version": version,
                "previous_version": status.get("current_candidate_version"),
                "modification_reason": str(source.get("modification_reason", "Initial formal batch generation" if not current else "Formal batch revision")),
                "source": str(source.get("version_source", "USER_REVIEW" if current else "INITIAL_GENERATION")),
                "generated_at": utc_now(),
            },
        }
    )
    prepared, payloads, warnings = prepare_file_specs(formal_dir, plan, selected_nodes, version, accepted)
    plan["file_specs"] = prepared
    plan["expected_result_roles"] = merge_expected_roles(source.get("expected_result_roles"), selected_nodes, references, source.get("projection_selections"))
    plan["engine_static_validation"] = {
        "accepted_structure_readable": True,
        "accepted_structure_metadata": structure_metadata,
        "task_ids_and_prerequisites_valid": True,
        "safe_paths": True,
        "file_roles_valid": True,
        "reference_definitions": len(references),
        "external_execution_only": True,
        "runtime_convergence_not_determinable": True,
        "blockers": blockers,
        "warnings": warnings,
    }
    return plan, payloads, blockers, warnings


def materialize_candidate(formal_dir: Path, plan: dict[str, Any], payloads: list[tuple[dict[str, Any], Path, bytes]]) -> list[dict[str, Any]]:
    version = str(plan["plan_version"])
    root = formal_dir / "versions" / version
    if root.exists():
        raise FormalError(f"Formal version directory already exists: {root}")
    for name in FILE_ROOTS:
        (root / name).mkdir(parents=True, exist_ok=True)
    artifacts: list[dict[str, Any]] = []
    for spec, target, data in payloads:
        write_bytes(target, data)
        artifacts.append(
            {
                "path": target.relative_to(formal_dir).as_posix(),
                "sha256": sha256(target),
                "size_bytes": target.stat().st_size,
                "role": spec.get("role"),
                "semantic_role": spec.get("semantic_role"),
                "task_id": spec.get("task_id"),
                "system_id": spec.get("system_id"),
                "reference_id": spec.get("reference_id"),
                "software": spec.get("software"),
                "source": spec.get("source"),
            }
        )
    return artifacts


def render_plan_markdown(plan: dict[str, Any]) -> str:
    lines = [
        f"# Formal Calculation Batch {plan.get('batch_id')} · {plan.get('plan_version')}",
        "",
        f"- Purpose: {plan.get('batch_purpose')}",
        f"- Tasks: {', '.join(plan.get('selected_task_ids', []))}",
        f"- Accepted structure: `{plan.get('accepted_structure', {}).get('path')}`",
        f"- Route: {plan.get('route')}",
        "- Calculation executed by Skill: false",
        "- Job submitted by Skill: false",
        "- Queue queried by Skill: false",
        "",
        "## Selected approved tasks",
        "",
    ]
    for task in plan.get("selected_tasks", []):
        lines.append(f"- `{task.get('task_id')}` · {task.get('task_name')} · {task.get('task_type')} · {task.get('evidence_role')}")
    lines.extend(["", "## References and comparability", "", "```json", json.dumps({"reference_definitions": plan.get("reference_definitions"), "comparability_checks": plan.get("comparability_checks")}, ensure_ascii=False, indent=2), "```", "", "## Static validation", "", "```json", json.dumps({"declared": plan.get("static_validation"), "engine": plan.get("engine_static_validation")}, ensure_ascii=False, indent=2), "```", "", "## Generated files", ""])
    lines.extend(f"- `{item.get('path')}` · {item.get('role')} · {item.get('semantic_role')} · `{item.get('sha256')}`" for item in plan.get("generated_artifacts", []))
    lines.extend(["", "Static validation does not prove runtime convergence or scientific validity.", ""])
    return "\n".join(lines)


def render_impact_markdown(impact: dict[str, Any], version: str) -> str:
    lines = [f"# Formal Batch Modification Impact {version}", "", f"- Overall impact: {impact.get('overall_impact_level')}", f"- Reason: {impact.get('modification_reason')}", "", "| Path | Before | After | Impact | Reason | Recommendation |", "| --- | --- | --- | --- | --- | --- |"]
    for item in impact.get("changes", []):
        row = [item.get("path"), compact(item.get("before")), compact(item.get("after")), item.get("impact_level"), item.get("impact_reason"), item.get("recommendation")]
        lines.append("| " + " | ".join(str(value).replace("|", "\\|") for value in row) + " |")
    lines.append("")
    return "\n".join(lines)


def load_plan(formal_dir: Path, version: str | None) -> dict[str, Any]:
    if not version:
        raise FormalError("Formal candidate version is missing.")
    path = formal_dir / f"formal_calculation_plan_{version}.json"
    if not path.is_file():
        raise FormalError(f"Formal candidate version does not exist: {version}")
    value = read_json(path)
    if not isinstance(value, dict):
        raise FormalError(f"Formal candidate {version} is invalid.")
    return value


def submit_plan(formal_dir: Path, source_path: Path | None = None, source_value: dict[str, Any] | None = None, reason: str = "") -> dict[str, Any]:
    status = load_status(formal_dir)
    verify_frozen_gate(status)
    if status["status"] not in {FORMAL_TASK_GRAPH_GENERATED, WAITING_FOR_FORMAL_FILE_APPROVAL}:
        raise FormalError("Formal candidate submission requires a selected batch or an active file review.")
    if status["status"] == FORMAL_TASK_GRAPH_GENERATED and status.get("selection_review_confirmed") is not True:
        raise FormalError("The selected formal batch requires hash-bound browser confirmation before file generation.")
    selection = load_selection(formal_dir, status)
    source = copy.deepcopy(source_value) if source_value is not None else read_json(source_path) if source_path else None
    if not isinstance(source, dict):
        raise FormalError("Formal candidate source must be a JSON object.")
    if reason:
        source["modification_reason"] = reason
    version = next_plan_version(formal_dir)
    plan, payloads, blockers, warnings = validate_candidate_source(formal_dir, status, source, selection, version)
    previous = load_plan(formal_dir, status["current_candidate_version"]) if status.get("current_candidate_version") else None
    artifacts = materialize_candidate(formal_dir, plan, payloads)
    plan["generated_artifacts"] = artifacts
    plan_path = formal_dir / f"formal_calculation_plan_{version}.json"
    write_json(plan_path, plan)
    write_text(formal_dir / f"formal_calculation_plan_{version}.md", render_plan_markdown(plan))
    impact = analyze_impact(previous, plan, str(plan["version_record"]["modification_reason"]))
    write_json(formal_dir / f"formal_impact_analysis_{version}.json", impact)
    write_text(formal_dir / f"formal_impact_analysis_{version}.md", render_impact_markdown(impact, version))
    graph = load_graph(formal_dir)
    nodes = graph_node_map(graph)
    for task_id in selection["selected_task_ids"]:
        node = nodes[str(task_id)]
        if node.get("status") in {"pending", "regeneration_required"}:
            node["status"] = "batched"
        raw_attempts = node.get("attempts")
        attempts: list[Any] = raw_attempts if isinstance(raw_attempts, list) else []
        attempts.append({"batch_id": selection["batch_id"], "candidate_version": version, "status": "candidate_generated"})
        node["attempts"] = attempts
    graph_version = write_graph_snapshot(formal_dir, graph, "FORMAL_CANDIDATE_GENERATED")
    old = status["status"]
    previous_version = status.get("current_candidate_version")
    status.update(
        {
            "status": WAITING_FOR_FORMAL_FILE_APPROVAL,
            "current_candidate_version": version,
            "previous_version": previous_version,
            "previous_valid_version": previous_version if previous and not status.get("validation_errors") else status.get("previous_valid_version"),
            "current_candidate_record": file_record(plan_path),
            "current_graph_version": graph_version,
            "validation_errors": blockers,
            "validation_warnings": warnings,
            "last_impact_level": impact["overall_impact_level"],
            **false_execution_flags(),
            "updated_at": utc_now(),
        }
    )
    write_json(status_path(formal_dir), status)
    write_result_status_projection(formal_dir, status)
    for event, intermediate in (
        ("FORMAL_INPUT_FILES_MATERIALIZED", FORMAL_INPUTS_GENERATED),
        ("FORMAL_REFERENCE_FILES_MATERIALIZED", REFERENCE_INPUTS_GENERATED),
        ("FORMAL_RUN_INSTRUCTIONS_MATERIALIZED", HPC_SCRIPTS_GENERATED),
        ("FORMAL_STATIC_VALIDATION_RECORDED", FORMAL_STATIC_VALIDATION_COMPLETED),
    ):
        append_log(formal_dir, {"event": event, "timestamp": utc_now(), "batch_id": selection["batch_id"], "version": version, "recorded_state": intermediate, **false_execution_flags()})
    append_log(formal_dir, {"event": "FORMAL_CANDIDATE_SUBMITTED_FOR_REVIEW", "timestamp": utc_now(), "batch_id": selection["batch_id"], "version": version, "previous_version": previous_version, "reason": plan["version_record"]["modification_reason"], "impact": impact["overall_impact_level"], "status_before": old, "status_after": WAITING_FOR_FORMAL_FILE_APPROVAL, **false_execution_flags()})
    return {"status": status, "plan": plan, "impact": impact}


APPROVED_ALIAS_NAMES = (
    "formal_calculation_plan_approved.json",
    "formal_calculation_plan_approved.md",
    "formal_calculation_approval_record.json",
    "calculation_inputs_approved",
    "postprocess_inputs_approved",
    "reference_systems_approved",
    "hpc_scripts_approved",
    "local_run_scripts_approved",
    "dependencies_approved",
)


def verify_candidate_files(formal_dir: Path, plan: dict[str, Any]) -> None:
    for index, record in enumerate(plan.get("generated_artifacts", [])):
        if not isinstance(record, dict):
            raise FormalError(f"generated_artifacts[{index}] is invalid.")
        path = safe_relative_path(formal_dir, str(record.get("path", "")))
        if not path.is_file() or sha256(path) != str(record.get("sha256", "")):
            raise FormalError(f"Generated candidate file changed or disappeared: {record.get('path')}")


def archive_current_aliases(formal_dir: Path, status: dict[str, Any]) -> None:
    existing = [formal_dir / name for name in APPROVED_ALIAS_NAMES if (formal_dir / name).exists()]
    if not existing:
        return
    prior = status.get("active_approval")
    if not isinstance(prior, dict):
        raise FormalError("Approved root aliases exist without an active approval record.")
    verify_absolute_record(prior.get("record"), "active formal approval before alias archival")
    stamp = re.sub(r"[^0-9]", "", utc_now())
    archive = formal_dir / "approved_alias_history" / f"{safe_name(str(prior.get('batch_id')))}_{stamp}"
    if archive.exists():
        raise FormalError(f"Approved alias archive already exists: {archive}")
    archive.mkdir(parents=True)
    for path in existing:
        shutil.move(str(path), str(archive / path.name))


def approve(formal_dir: Path, confirmed_by: str, reason: str) -> dict[str, Any]:
    status = load_status(formal_dir)
    verify_frozen_gate(status)
    if status["status"] != WAITING_FOR_FORMAL_FILE_APPROVAL:
        raise FormalError("Formal approval requires WAITING_FOR_FORMAL_FILE_APPROVAL.")
    if status.get("validation_errors"):
        raise FormalError("Formal candidate has approval blockers:\n- " + "\n- ".join(status["validation_errors"]))
    if not str(reason).strip():
        raise FormalError("Formal approval requires an explicit confirmation reason.")
    version = str(status.get("current_candidate_version", ""))
    plan = load_plan(formal_dir, version)
    verify_candidate_files(formal_dir, plan)
    if plan.get("scientific_reconfirmation"):
        raise FormalError("Scientific reconfirmation items remain; return to the owning approval stage.")
    required_pending = [item for item in plan.get("pending_fields", []) if isinstance(item, dict) and item.get("required") is True and not str(item.get("value", "")).strip()]
    if required_pending:
        raise FormalError("Required user fields remain unresolved.")
    selection = load_selection(formal_dir, status)
    batch_id = str(selection["batch_id"])
    batch_root = formal_dir / "approved_batches" / batch_id
    if batch_root.exists():
        raise FormalError(f"Approved batch directory already exists: {batch_root}")
    batch_root.mkdir(parents=True)
    source_root = formal_dir / "versions" / version
    directory_map = {
        "calculation_inputs": "calculation_inputs_approved",
        "postprocess_inputs": "postprocess_inputs_approved",
        "reference_systems": "reference_systems_approved",
        "hpc_scripts": "hpc_scripts_approved",
        "local_run_scripts": "local_run_scripts_approved",
        "dependencies": "dependencies_approved",
    }
    for source_name, target_name in directory_map.items():
        shutil.copytree(source_root / source_name, batch_root / target_name)
    approved_plan = batch_root / "formal_calculation_plan_approved.json"
    approved_md = batch_root / "formal_calculation_plan_approved.md"
    write_json(approved_plan, plan)
    write_text(approved_md, render_plan_markdown(plan))
    manifests = {target: manifest_tree(batch_root / target, batch_root) for target in directory_map.values()}
    record = {
        "project_id": status["project_id"],
        "workflow_step": "stage2_step3_formal_calculations",
        "status": FORMAL_CALCULATION_FILES_APPROVED,
        "batch_id": batch_id,
        "approved_candidate_version": version,
        "approved_candidate_sha256": sha256(formal_dir / f"formal_calculation_plan_{version}.json"),
        "approved_plan_sha256": sha256(approved_plan),
        "approved_markdown_sha256": sha256(approved_md),
        "selected_task_ids": copy.deepcopy(plan.get("selected_task_ids")),
        "accepted_structure": copy.deepcopy(plan.get("accepted_structure")),
        "actual_optimization_parameter_audit": copy.deepcopy(plan.get("actual_optimization_parameter_audit")),
        "approved_file_manifests": manifests,
        "static_validation": copy.deepcopy(plan.get("static_validation")),
        "engine_static_validation": copy.deepcopy(plan.get("engine_static_validation")),
        "pending_optional_fields": [item for item in plan.get("pending_fields", []) if not (isinstance(item, dict) and item.get("required") is True)],
        "confirmed_by": confirmed_by or "user",
        "confirmation_reason": reason,
        "confirmed_at": utc_now(),
        **false_execution_flags(),
    }
    record_path = batch_root / "formal_calculation_approval_record.json"
    write_json(record_path, record)
    archive_current_aliases(formal_dir, status)
    shutil.copyfile(approved_plan, formal_dir / "formal_calculation_plan_approved.json")
    shutil.copyfile(approved_md, formal_dir / "formal_calculation_plan_approved.md")
    shutil.copyfile(record_path, formal_dir / "formal_calculation_approval_record.json")
    for target_name in directory_map.values():
        shutil.copytree(batch_root / target_name, formal_dir / target_name)
    graph = load_graph(formal_dir)
    nodes = graph_node_map(graph)
    for task_id in plan["selected_task_ids"]:
        node = nodes[str(task_id)]
        node["status"] = "awaiting_result"
        if node.get("attempts"):
            node["attempts"][-1]["status"] = "approved_awaiting_external_result"
            node["attempts"][-1]["approval_record"] = file_record(record_path)
    graph_version = write_graph_snapshot(formal_dir, graph, "FORMAL_BATCH_APPROVED_AND_DELIVERED")
    old = status["status"]
    active_approval = {"batch_id": batch_id, "batch_dir": str(batch_root.resolve()), "record": file_record(record_path), "plan": file_record(approved_plan), "manifests": manifests}
    status.update(
        {
            "status": WAITING_FOR_FORMAL_CALCULATION_RESULT,
            "active_batch_id": batch_id,
            "active_approval": active_approval,
            "current_graph_version": graph_version,
            "validation_errors": [],
            "awaiting_additional_files": False,
            "return_route": None,
            **false_execution_flags(),
            "updated_at": utc_now(),
        }
    )
    write_json(status_path(formal_dir), status)
    write_result_status_projection(formal_dir, status)
    append_log(formal_dir, {"event": "FORMAL_CALCULATION_FILES_APPROVED", "timestamp": record["confirmed_at"], "batch_id": batch_id, "version": version, "status_before": old, "status_after": FORMAL_CALCULATION_FILES_APPROVED, **false_execution_flags()})
    append_log(formal_dir, {"event": "FORMAL_FILES_DELIVERED_FOR_EXTERNAL_EXECUTION", "timestamp": utc_now(), "batch_id": batch_id, "status_before": FORMAL_CALCULATION_FILES_APPROVED, "status_after": WAITING_FOR_FORMAL_CALCULATION_RESULT, **false_execution_flags()})
    return {"status": status, "approval_record": record, "user_prompt": FORMAL_HANDOFF_PROMPT}


def transition(formal_dir: Path, action: str, reason: str = "", version: str | None = None, confirmed_by: str = "user") -> dict[str, Any]:
    status = load_status(formal_dir)
    verify_frozen_gate(status)
    if action in {"accept", "approve"}:
        raise FormalError("Formal-file approval must be submitted through the hash-bound browser review command.")
    if status["status"] != WAITING_FOR_FORMAL_FILE_APPROVAL:
        raise FormalError("Review actions require WAITING_FOR_FORMAL_FILE_APPROVAL.")
    if action == "reselect":
        selection = load_selection(formal_dir, status)
        graph = load_graph(formal_dir)
        nodes = graph_node_map(graph)
        origins = selection.get("origin_task_statuses", {}) if isinstance(selection.get("origin_task_statuses"), dict) else {}
        for task_id in selection.get("selected_task_ids", []):
            if str(task_id) in nodes:
                nodes[str(task_id)]["status"] = origins.get(str(task_id), "pending")
                if nodes[str(task_id)].get("attempts"):
                    nodes[str(task_id)]["attempts"][-1]["status"] = "candidate_abandoned_for_reselection"
        graph_version = write_graph_snapshot(formal_dir, graph, "FORMAL_BATCH_RESELECTION_REQUESTED")
        target = str(selection.get("selection_origin_state", WAITING_FOR_FORMAL_TASK_SELECTION))
        if target not in {WAITING_FOR_FORMAL_TASK_SELECTION, NEXT_FORMAL_BATCH_READY, FORMAL_EVIDENCE_NODE_COMPLETED, FORMAL_FILES_REGENERATION_REQUIRED}:
            target = WAITING_FOR_FORMAL_TASK_SELECTION
        old = status["status"]
        status.update({"status": target, "active_batch_id": None, "current_selection_version": None, "current_selection_record": None, "current_candidate_version": None, "current_candidate_record": None, "previous_version": None, "previous_valid_version": None, "current_graph_version": graph_version, "validation_errors": [], "validation_warnings": [], "updated_at": utc_now()})
        write_json(status_path(formal_dir), status)
        write_result_status_projection(formal_dir, status)
        append_log(formal_dir, {"event": "FORMAL_BATCH_RESELECTION_REQUESTED", "timestamp": utc_now(), "abandoned_batch_id": selection.get("batch_id"), "reason": reason, "status_before": old, "status_after": target, **false_execution_flags()})
        return {"status": status}
    if action == "continue":
        append_log(formal_dir, {"event": "FORMAL_CONTINUE_EDITING", "timestamp": utc_now(), "batch_id": status.get("active_batch_id"), "version": status.get("current_candidate_version"), "reason": reason, "status_before": status["status"], "status_after": status["status"], **false_execution_flags()})
        return {"status": status}
    if action == "restore":
        if not version:
            raise FormalError("Restore requires a historical candidate version.")
        source = load_plan(formal_dir, version)
        if source.get("batch_id") != status.get("active_batch_id"):
            raise FormalError("Restore is limited to versions of the active batch.")
        source["version_source"] = "RESTORE"
        return submit_plan(formal_dir, source_value=source, reason=reason or f"Restore {version} as a new immutable version")
    if action == "reject":
        fallback = status.get("previous_valid_version") or status.get("previous_version")
        if not fallback:
            raise FormalError("No previous formal candidate version is available.")
        rejected = status.get("current_candidate_version")
        fallback_plan = load_plan(formal_dir, str(fallback))
        if fallback_plan.get("batch_id") != status.get("active_batch_id"):
            raise FormalError("Previous candidate belongs to another batch and cannot become the current pointer.")
        status.update({"current_candidate_version": fallback, "current_candidate_record": file_record(formal_dir / f"formal_calculation_plan_{fallback}.json"), "rejected_version": rejected, "validation_errors": [], "validation_warnings": [], "updated_at": utc_now()})
        write_json(status_path(formal_dir), status)
        write_result_status_projection(formal_dir, status)
        append_log(formal_dir, {"event": "FORMAL_CANDIDATE_REJECTED", "timestamp": utc_now(), "batch_id": status.get("active_batch_id"), "version": rejected, "restored_current_version": fallback, "reason": reason, "status_before": WAITING_FOR_FORMAL_FILE_APPROVAL, "status_after": WAITING_FOR_FORMAL_FILE_APPROVAL, **false_execution_flags()})
        return {"status": status}
    raise FormalError(f"Unknown formal review action: {action}")


def browser_review(
    formal_dir: Path,
    project_dir: Path,
    title: str,
    start_port: int,
    timeout_seconds: float | None,
) -> dict[str, Any]:
    status = load_status(formal_dir)
    version = status.get("current_candidate_version")
    if not version:
        raise FormalError("No formal calculation candidate is available for browser review.")
    return execute_stage_review(
        project_dir=project_dir,
        stage_dir=formal_dir,
        stage="stage2_step3_formal",
        title=title,
        content_file=formal_dir / f"formal_calculation_plan_{version}.json",
        allowed_statuses={WAITING_FOR_FORMAL_FILE_APPROVAL},
        revision_status=WAITING_FOR_FORMAL_FILE_APPROVAL,
        rejected_status=FORMAL_REVIEW_REJECTED,
        load_status=lambda: load_status(formal_dir),
        save_status=lambda value: write_json(status_path(formal_dir), value),
        append_log=lambda value: append_log(formal_dir, value),
        approve=lambda comment: approve(
            formal_dir,
            "browser_user",
            comment.strip() or "Approved through hash-bound browser review.",
        ),
        error_type=FormalError,
        blocked_access_updates=false_execution_flags(),
        revision_updates=false_execution_flags(),
        rejected_updates=false_execution_flags(),
        start_port=start_port,
        timeout_seconds=timeout_seconds,
    )


def browser_review_selection(
    formal_dir: Path,
    project_dir: Path,
    title: str,
    start_port: int,
    timeout_seconds: float | None,
) -> dict[str, Any]:
    status = load_status(formal_dir)
    selection = load_selection(formal_dir, status)
    origin = str(selection.get("selection_origin_state", WAITING_FOR_FORMAL_TASK_SELECTION))
    allowed_origins = {WAITING_FOR_FORMAL_TASK_SELECTION, NEXT_FORMAL_BATCH_READY, FORMAL_EVIDENCE_NODE_COMPLETED, FORMAL_FILES_REGENERATION_REQUIRED}
    if origin not in allowed_origins:
        origin = WAITING_FOR_FORMAL_TASK_SELECTION
    selection_path = verify_absolute_record(status.get("current_selection_record"), "current formal batch selection")

    def confirm_selection(comment: str) -> dict[str, Any]:
        current = load_status(formal_dir)
        current.update({"selection_review_confirmed": True, "selection_review_comment": comment, "updated_at": utc_now()})
        write_json(status_path(formal_dir), current)
        write_result_status_projection(formal_dir, current)
        append_log(formal_dir, {"event": "FORMAL_BATCH_SELECTION_BROWSER_CONFIRMED", "timestamp": utc_now(), "comment": comment, "status_after": current["status"], **false_execution_flags()})
        return {"status": current}

    return execute_stage_review(
        project_dir=project_dir,
        stage_dir=formal_dir,
        stage="stage2_step3_formal_selection",
        title=title,
        content_file=selection_path,
        allowed_statuses={FORMAL_TASK_GRAPH_GENERATED},
        revision_status=origin,
        rejected_status=FORMAL_REVIEW_REJECTED,
        load_status=lambda: load_status(formal_dir),
        save_status=lambda value: write_json(status_path(formal_dir), value),
        append_log=lambda value: append_log(formal_dir, value),
        approve=confirm_selection,
        error_type=FormalError,
        blocked_access_updates={"selection_review_confirmed": False, **false_execution_flags()},
        revision_updates={"selection_review_confirmed": False, **false_execution_flags()},
        rejected_updates={"selection_review_confirmed": False, **false_execution_flags()},
        start_port=start_port,
        timeout_seconds=timeout_seconds,
    )


def verify_active_approval(formal_dir: Path, status: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any], Path]:
    active = status.get("active_approval")
    if not isinstance(active, dict):
        raise FormalError("Active formal approval record is missing.")
    record_path = verify_absolute_record(active.get("record"), "active formal approval record")
    plan_path = verify_absolute_record(active.get("plan"), "active approved formal plan")
    record = read_json(record_path)
    plan = read_json(plan_path)
    if not isinstance(record, dict) or not isinstance(plan, dict):
        raise FormalError("Active formal approval/plan is invalid.")
    if record.get("status") != FORMAL_CALCULATION_FILES_APPROVED or record.get("batch_id") != status.get("active_batch_id"):
        raise FormalError("Active formal approval batch/status is inconsistent.")
    if sha256(plan_path) != str(record.get("approved_plan_sha256", "")):
        raise FormalError("Active approved formal plan checksum is inconsistent.")
    batch_root = Path(str(active.get("batch_dir", "")))
    if not batch_root.is_dir():
        raise FormalError("Active approved batch directory is missing.")
    manifests = record.get("approved_file_manifests")
    if not isinstance(manifests, dict):
        raise FormalError("Active approved batch manifests are missing.")
    for directory, records in manifests.items():
        validated = validate_manifest(batch_root, records, f"active approval {directory}")
        actual_root = batch_root / str(directory)
        actual = manifest_tree(actual_root, batch_root) if actual_root.is_dir() else []
        if {(item["path"], item["sha256"]) for item in validated} != {(item["path"], item["sha256"]) for item in actual}:
            raise FormalError(f"Active approved directory differs from its manifest: {directory}")
    return record, plan, batch_root


def normalize_software(value: Any) -> str:
    compact_value = re.sub(r"[^a-z0-9]+", "", str(value).lower())
    aliases = {
        "qe": "quantumespresso",
        "pwx": "quantumespresso",
        "quantumespresso": "quantumespresso",
        "cp2k": "cp2k",
        "gaussian": "gaussian",
        "g16": "gaussian",
        "g09": "gaussian",
        "orca": "orca",
        "gromacs": "gromacs",
        "vasp": "vasp",
        "lammps": "lammps",
        "lobster": "lobster",
        "multiwfn": "multiwfn",
    }
    return aliases.get(compact_value, compact_value)


def ingest_results(formal_dir: Path, manifest_path: Path) -> dict[str, Any]:
    status = load_status(formal_dir)
    verify_frozen_gate(status)
    if status["status"] not in {WAITING_FOR_FORMAL_CALCULATION_RESULT, FORMAL_CALCULATION_RESULT_RECEIVED}:
        raise FormalError("Formal result intake requires the active external-result wait/additional-files state.")
    approval, plan, _ = verify_active_approval(formal_dir, status)
    manifest = read_json(manifest_path)
    if not isinstance(manifest, dict):
        raise FormalError("Formal result manifest must be a JSON object.")
    reject_prohibited_fields(manifest, "formal_result_manifest")
    if manifest.get("batch_id") != status.get("active_batch_id"):
        raise FormalError("Formal result batch_id differs from the active approved batch.")
    if manifest.get("approved_batch_sha256") != status["active_approval"]["record"]["sha256"]:
        raise FormalError("Formal result manifest must bind to the active approval-record checksum.")
    if manifest.get("result_kind") != "formal_calculation":
        raise FormalError("result_kind must be formal_calculation.")
    approved_software = {normalize_software(task.get("software")) for task in plan.get("selected_tasks", []) if isinstance(task, dict) and normalize_software(task.get("software"))}
    supplied_software = manifest.get("software")
    software_values = supplied_software if isinstance(supplied_software, list) else [supplied_software]
    normalized_supplied = {normalize_software(value) for value in software_values if normalize_software(value)}
    if approved_software and (not normalized_supplied or not normalized_supplied.issubset(approved_software)):
        raise FormalError("Formal result software differs from the selected approved task software.")
    files = manifest.get("files")
    if not isinstance(files, list):
        raise FormalError("Formal result files must be a list.")
    description_only = manifest.get("description_only") is True
    if files and description_only:
        raise FormalError("description_only must be false when result files are supplied.")
    if not files and not description_only:
        raise FormalError("Provide real formal result files or explicitly record a detailed description-only return.")
    if description_only:
        facts = manifest.get("described_facts")
        required = ("program_termination", "electronic_status", "file_status", "reference_status", "errors")
        if not isinstance(facts, dict) or any(key not in facts for key in required):
            raise FormalError("Description-only formal intake requires termination, electronic, file, reference, and error facts.")
    version = next_result_version(formal_dir)
    result_root = formal_dir / "user_results" / f"{safe_name(str(status['active_batch_id']))}_result_{version}"
    if result_root.exists():
        raise FormalError(f"Formal result directory already exists: {result_root}")
    result_root.mkdir(parents=True)
    selected_ids = {str(value) for value in plan.get("selected_task_ids", [])}
    stored: list[dict[str, Any]] = []
    for index, item in enumerate(files, start=1):
        if not isinstance(item, dict) or not str(item.get("path", "")).strip():
            raise FormalError(f"files[{index - 1}] requires an actual path.")
        role = str(item.get("role", ""))
        task_id = str(item.get("task_id", ""))
        if role not in RESULT_FILE_ROLES:
            raise FormalError(f"files[{index - 1}].role is invalid: {role}")
        if task_id not in selected_ids and task_id != "BATCH":
            raise FormalError(f"files[{index - 1}] references an unselected task: {task_id}")
        source = Path(str(item["path"])).expanduser().resolve()
        if not source.is_file():
            raise FormalError(f"Returned formal result path is not a file: {source}")
        target = result_root / f"{index:03d}_{safe_name(str(item.get('name') or source.name))}"
        shutil.copyfile(source, target)
        stored.append(
            {
                "role": role,
                "task_id": task_id,
                "system_id": item.get("system_id"),
                "label": item.get("label"),
                "original_path": str(source),
                "stored_path": target.relative_to(formal_dir).as_posix(),
                "sha256": sha256(target),
                "size_bytes": target.stat().st_size,
                "ingested_at": utc_now(),
            }
        )
    batch = {
        "project_id": status["project_id"],
        "workflow_step": "stage2_step3_formal_result_intake",
        "result_version": version,
        "batch_id": status["active_batch_id"],
        "approved_batch_record": copy.deepcopy(status["active_approval"]["record"]),
        "software": supplied_software,
        "normalized_software": sorted(normalized_supplied),
        "result_kind": "formal_calculation",
        "description_only": description_only,
        "user_description": manifest.get("user_description", ""),
        "described_facts": copy.deepcopy(manifest.get("described_facts", {})),
        "actual_execution_context": copy.deepcopy(manifest.get("actual_execution_context", {})),
        "files": stored,
        **false_execution_flags(),
        "ingested_at": utc_now(),
    }
    batch_path = formal_dir / f"formal_result_batch_{version}.json"
    write_json(batch_path, batch)
    old = status["status"]
    raw_result_versions = status.get("result_versions")
    result_versions: list[Any] = raw_result_versions if isinstance(raw_result_versions, list) else []
    result_versions.append({"version": version, "batch_id": status["active_batch_id"], "record": file_record(batch_path)})
    status.update(
        {
            "status": FORMAL_CALCULATION_RESULT_RECEIVED,
            "latest_result_version": version,
            "current_result_record": file_record(batch_path),
            "result_versions": result_versions,
            "awaiting_additional_files": False,
            **false_execution_flags(),
            "updated_at": utc_now(),
        }
    )
    write_json(status_path(formal_dir), status)
    write_result_status_projection(formal_dir, status)
    append_log(formal_dir, {"event": "FORMAL_CALCULATION_RESULT_RECEIVED", "timestamp": utc_now(), "batch_id": status["active_batch_id"], "result_version": version, "file_count": len(stored), "description_only": description_only, "status_before": old, "status_after": FORMAL_CALCULATION_RESULT_RECEIVED, **false_execution_flags()})
    return {"status": status, "result_batch": batch}


def load_result_batch(formal_dir: Path, status: dict[str, Any]) -> dict[str, Any]:
    path = verify_absolute_record(status.get("current_result_record"), "current formal result batch")
    batch = read_json(path)
    if not isinstance(batch, dict) or batch.get("result_version") != status.get("latest_result_version"):
        raise FormalError("Current formal result batch is invalid or inconsistent.")
    return batch


def result_file_map(batch: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {str(item.get("stored_path")): item for item in batch.get("files", []) if isinstance(item, dict) and item.get("stored_path")}


def validate_result_file(formal_dir: Path, files: dict[str, dict[str, Any]], record: Any, label: str, roles: set[str] | None = None) -> dict[str, Any]:
    if not isinstance(record, dict):
        raise FormalError(f"{label} must be a formal result-file reference.")
    stored_path = str(record.get("stored_path", ""))
    canonical = files.get(stored_path)
    if not canonical or canonical.get("sha256") != record.get("sha256"):
        raise FormalError(f"{label} does not match the immutable result batch.")
    if roles and canonical.get("role") not in roles:
        raise FormalError(f"{label} has role {canonical.get('role')}, expected {sorted(roles)}.")
    path = safe_relative_path(formal_dir, stored_path)
    if not path.is_file() or sha256(path) != str(canonical.get("sha256", "")):
        raise FormalError(f"{label} file changed or disappeared.")
    return canonical


def validate_evidence(formal_dir: Path, batch: dict[str, Any], files: dict[str, dict[str, Any]], item: Any, label: str) -> None:
    if not isinstance(item, dict) or not str(item.get("observation", "")).strip():
        raise FormalError(f"{label} requires a concrete observation.")
    if item.get("source") == "user_description":
        if batch.get("description_only") is not True:
            raise FormalError(f"{label} may cite user_description only for a description-only result.")
        return
    validate_result_file(formal_dir, files, item, label)


TASK_ACCEPTANCE_CHECKS = {
    "high_precision_scf": {"energy_stable", "occupations_reasonable", "magnetization_reasonable", "required_outputs_present"},
    "binding_or_formation_energy": {"energy_terms_complete", "same_cell", "same_strain", "same_parameters"},
    "charge_density_difference": {"density_terms_complete", "same_grid", "same_lattice", "positions_preserved"},
    "quantitative_charge": {"density_compatible", "partition_complete"},
    "dos_pdos": {"scf_dependency_valid", "nscf_complete", "fermi_reference_consistent", "projection_scope_matches"},
    "cohp_coop_bonding": {"wavefunction_complete", "projection_basis_valid", "bands_sufficient", "selected_pairs_complete"},
    "qtaim": {"density_or_wavefunction_compatible", "topology_output_complete"},
    "classical_md": {"required_stage_complete", "trajectory_and_state_complete"},
    "approved_other": {"approved_acceptance_criteria_met"},
}


def missing_expected_results(plan: dict[str, Any], batch: dict[str, Any]) -> list[str]:
    files = [item for item in batch.get("files", []) if isinstance(item, dict)]
    missing: list[str] = []
    expected = plan.get("expected_result_roles", {})
    for task_id, requirements in expected.items() if isinstance(expected, dict) else []:
        if not isinstance(requirements, list):
            continue
        for requirement in requirements:
            if not isinstance(requirement, dict) or requirement.get("required") is not True:
                continue
            role = str(requirement.get("role"))
            system_id = str(requirement.get("system_id", ""))
            found = any(str(item.get("task_id")) == str(task_id) and str(item.get("role")) == role and (not system_id or str(item.get("system_id", "")) == system_id) for item in files)
            if not found:
                missing.append(f"{task_id}:{role}" + (f":{system_id}" if system_id else ""))
    return sorted(missing)


def validate_input_comparison(formal_dir: Path, plan: dict[str, Any], batch: dict[str, Any], check: Any) -> tuple[list[str], bool]:
    errors: list[str] = []
    if not isinstance(check, dict):
        return ["actual_input_check must be an object."], False
    match = check.get("match_status")
    if match not in {"exact_match", "modified_reapproved", "modified_unapproved", "unknown"}:
        errors.append("actual_input_check.match_status is invalid.")
    differences = check.get("differences")
    if not isinstance(differences, list):
        errors.append("actual_input_check.differences must be a list.")
        differences = []
    approved_hashes = {str(item.get("sha256")) for item in plan.get("generated_artifacts", []) if isinstance(item, dict) and item.get("role") in INPUT_ROLES}
    actual_hashes = {str(item.get("sha256")) for item in batch.get("files", []) if isinstance(item, dict) and item.get("role") == "actual_input"}
    if match == "exact_match" and (not approved_hashes or not approved_hashes.issubset(actual_hashes)):
        errors.append("exact_match requires every approved calculation/reference input to be returned with matching checksums.")
    if match == "exact_match" and differences:
        errors.append("exact_match cannot contain differences.")
    if str(match).startswith("modified") and not differences:
        errors.append("Modified actual inputs require explicit differences.")
    core: list[dict[str, Any]] = []
    for index, item in enumerate(differences):
        if not isinstance(item, dict):
            errors.append(f"actual_input_check.differences[{index}] must be an object.")
            continue
        for key in ("parameter", "approved_value", "actual_value", "category", "scientific_impact", "reapproval_status"):
            if key not in item:
                errors.append(f"actual_input_check.differences[{index}].{key} is required.")
        if item.get("category") not in {"core_method", "numerical", "reference", "resource", "path_dependency", "postprocess"}:
            errors.append(f"actual_input_check.differences[{index}].category is invalid.")
        if item.get("reapproval_status") not in {"not_required", "approved", "required"}:
            errors.append(f"actual_input_check.differences[{index}].reapproval_status is invalid.")
        if item.get("category") == "core_method":
            core.append(item)
    core_approved = not core
    if core:
        core_approved = match == "modified_reapproved" and all(item.get("reapproval_status") == "approved" for item in core)
        if core_approved:
            try:
                verify_absolute_record(check.get("stage1_reapproval_record"), "formal actual-input stage-1 reapproval record")
            except FormalError as exc:
                errors.append(str(exc))
                core_approved = False
    return errors, core_approved


def validate_task_checks(
    formal_dir: Path,
    plan: dict[str, Any],
    batch: dict[str, Any],
    source: dict[str, Any],
) -> tuple[list[str], dict[str, dict[str, Any]]]:
    errors: list[str] = []
    files = result_file_map(batch)
    raw = source.get("task_checks")
    if not isinstance(raw, list):
        return ["task_checks must be a list."], {}
    selected = {str(task.get("task_id")): task for task in plan.get("selected_tasks", []) if isinstance(task, dict)}
    checks: dict[str, dict[str, Any]] = {}
    for index, item in enumerate(raw):
        if not isinstance(item, dict):
            errors.append(f"task_checks[{index}] must be an object.")
            continue
        task_id = str(item.get("task_id", ""))
        if task_id not in selected or task_id in checks:
            errors.append(f"task_checks[{index}] has an unselected or duplicate task ID: {task_id}")
            continue
        allowed = {
            "program_termination": {"normal", "abnormal", "interrupted", "unknown"},
            "electronic_convergence": {"stable", "unstable", "not_converged", "not_applicable", "unknown"},
            "file_completeness": {"complete", "incomplete", "unknown"},
            "reference_comparability": {"passed", "failed", "not_applicable", "unknown"},
            "scientific_validity": {"valid", "invalid", "unknown"},
        }
        for field, values in allowed.items():
            if item.get(field) not in values:
                errors.append(f"task_checks[{index}].{field} is invalid.")
        evidence = item.get("evidence")
        if not isinstance(evidence, list) or (item.get("scientific_validity") != "unknown" and not evidence):
            errors.append(f"task_checks[{index}].evidence must be nonempty unless validity is unknown.")
        else:
            for evidence_index, evidence_item in enumerate(evidence):
                try:
                    validate_evidence(formal_dir, batch, files, evidence_item, f"task_checks[{index}].evidence[{evidence_index}]")
                except FormalError as exc:
                    errors.append(str(exc))
        detailed = item.get("checks")
        if not isinstance(detailed, dict):
            errors.append(f"task_checks[{index}].checks must be an object.")
            detailed = {}
        if item.get("scientific_validity") == "valid":
            required = TASK_ACCEPTANCE_CHECKS.get(str(selected[task_id].get("task_type")), set())
            for key in required:
                if detailed.get(key) is not True:
                    errors.append(f"Valid task {task_id} requires checks.{key}: true.")
        checks[task_id] = copy.deepcopy(item)
    missing = sorted(set(selected) - set(checks))
    if missing:
        errors.append("task_checks omit selected tasks: " + ", ".join(missing))
    return errors, checks


def task_checks_all_valid(checks: dict[str, dict[str, Any]]) -> bool:
    return bool(checks) and all(
        item.get("program_termination") == "normal"
        and item.get("electronic_convergence") in {"stable", "not_applicable"}
        and item.get("file_completeness") == "complete"
        and item.get("reference_comparability") in {"passed", "not_applicable"}
        and item.get("scientific_validity") == "valid"
        for item in checks.values()
    )


def projected_graph_after_acceptance(graph: dict[str, Any], task_ids: list[str]) -> dict[str, Any]:
    projected = copy.deepcopy(graph)
    nodes = graph_node_map(projected)
    for task_id in task_ids:
        if task_id not in nodes:
            raise FormalError(f"Accepted task is absent from the formal task graph: {task_id}")
        nodes[task_id]["status"] = "accepted"
        if nodes[task_id].get("attempts"):
            nodes[task_id]["attempts"][-1]["status"] = "accepted"
    refresh_evidence_nodes(projected)
    return projected


def workflow_is_complete(graph: dict[str, Any]) -> bool:
    nodes = [node for node in graph.get("nodes", []) if isinstance(node, dict)]
    necessary = {str(node.get("task_id")) for node in nodes if task_is_necessary(node)}
    accepted = {str(node.get("task_id")) for node in nodes if node.get("status") == "accepted"}
    required_evidence = {str(item.get("id")) for item in graph.get("evidence_nodes", []) if isinstance(item, dict) and item.get("required") is True}
    completed_evidence = set(str(value) for value in graph.get("completed_evidence_node_ids", []))
    return necessary.issubset(accepted) and required_evidence.issubset(completed_evidence)


def render_parameter_report(analysis: dict[str, Any]) -> str:
    check = analysis.get("actual_input_check", {})
    lines = [f"# Formal Parameter Difference Report {analysis.get('analysis_version')}", "", f"- Match status: {check.get('match_status')}", f"- Core method approved/consistent: {analysis.get('core_method_approved')}", "", "| Parameter | Approved | Actual | Category | Scientific impact | Reapproval |", "| --- | --- | --- | --- | --- | --- |"]
    for item in check.get("differences", []) if isinstance(check, dict) else []:
        if isinstance(item, dict):
            values = [item.get(key) for key in ("parameter", "approved_value", "actual_value", "category", "scientific_impact", "reapproval_status")]
            lines.append("| " + " | ".join(compact(value).replace("|", "\\|") for value in values) + " |")
    lines.append("")
    return "\n".join(lines)


def render_result_analysis(analysis: dict[str, Any]) -> str:
    lines = [
        f"# Formal Result Judgment {analysis.get('analysis_version')}",
        "",
        f"- Batch: {analysis.get('batch_id')}",
        f"- Result version: {analysis.get('result_version')}",
        f"- Conclusion: **{analysis.get('decision_label')}**",
        f"- Decision code: `{analysis.get('decision_code')}`",
        f"- Result state: `{analysis.get('result_state')}`",
        f"- Return route: {analysis.get('return_route') or 'none'}",
        "- Calculation executed by Skill: false",
        "- Job submitted by Skill: false",
        "",
        "## Actual input comparison",
        "",
        "```json",
        json.dumps(analysis.get("actual_input_check", {}), ensure_ascii=False, indent=2),
        "```",
        "",
        "## Task checks",
        "",
        "```json",
        json.dumps(analysis.get("task_checks", []), ensure_ascii=False, indent=2),
        "```",
        "",
        "## Evidence and action",
        "",
    ]
    for item in analysis.get("source_evidence", []):
        lines.append(f"- `{item.get('stored_path') or item.get('source')}` · {item.get('observation')}")
    lines.extend(["", f"Recommended action: {analysis.get('recommended_action')}", "", "## Evidence-chain update", "", "```json", json.dumps({"accepted_task_ids": analysis.get("accepted_task_ids"), "new_completed_evidence_node_ids": analysis.get("new_completed_evidence_node_ids"), "ready_task_ids": analysis.get("ready_task_ids"), "workflow_completed": analysis.get("workflow_completed")}, ensure_ascii=False, indent=2), "```", ""])
    return "\n".join(lines)


def copy_result_set(formal_dir: Path, batch: dict[str, Any], accepted: bool, version: str) -> list[dict[str, Any]]:
    root_name = "accepted_results" if accepted else "rejected_results"
    root = formal_dir / root_name / f"{safe_name(str(batch.get('batch_id')))}_{version}"
    if root.exists():
        raise FormalError(f"Formal judged-result directory already exists: {root}")
    root.mkdir(parents=True)
    copied: list[dict[str, Any]] = []
    for index, item in enumerate(batch.get("files", []), start=1):
        if not isinstance(item, dict):
            continue
        source = safe_relative_path(formal_dir, str(item.get("stored_path", "")))
        target = root / f"{index:03d}_{safe_name(source.name)}"
        shutil.copyfile(source, target)
        copied.append({"path": target.relative_to(formal_dir).as_posix(), "sha256": sha256(target), "source_stored_path": item.get("stored_path"), "source_sha256": item.get("sha256"), "role": item.get("role"), "task_id": item.get("task_id")})
    return copied


def analyze_results(formal_dir: Path, source_path: Path) -> dict[str, Any]:
    status = load_status(formal_dir)
    verify_frozen_gate(status)
    if status["status"] != FORMAL_CALCULATION_RESULT_RECEIVED:
        raise FormalError("Formal result analysis requires FORMAL_CALCULATION_RESULT_RECEIVED.")
    approval, plan, _ = verify_active_approval(formal_dir, status)
    batch = load_result_batch(formal_dir, status)
    source = read_json(source_path)
    if not isinstance(source, dict):
        raise FormalError("Formal result analysis source must be a JSON object.")
    reject_prohibited_fields(source, "formal_result_analysis")
    errors: list[str] = []
    files = result_file_map(batch)
    source_evidence = source.get("source_evidence")
    if not isinstance(source_evidence, list) or not source_evidence:
        errors.append("source_evidence must be a nonempty list.")
        source_evidence = []
    for index, item in enumerate(source_evidence):
        try:
            validate_evidence(formal_dir, batch, files, item, f"source_evidence[{index}]")
        except FormalError as exc:
            errors.append(str(exc))
    input_errors, core_approved = validate_input_comparison(formal_dir, plan, batch, source.get("actual_input_check"))
    errors.extend(input_errors)
    check_errors, task_checks = validate_task_checks(formal_dir, plan, batch, source)
    errors.extend(check_errors)
    missing = missing_expected_results(plan, batch)
    raw_completeness = source.get("file_completeness")
    completeness: dict[str, Any] = raw_completeness if isinstance(raw_completeness, dict) else {}
    if not isinstance(raw_completeness, dict) or completeness.get("status") not in {"complete", "incomplete"} or not isinstance(completeness.get("missing"), list) or not str(completeness.get("limitations", "")).strip():
        errors.append("file_completeness requires status, missing, and limitations.")
    elif completeness.get("status") == "complete" and missing:
        errors.append("file_completeness cannot be complete; required returned roles are missing: " + ", ".join(missing))
    attribution = source.get("problem_attribution")
    allowed_categories = {"accepted", "missing_files", "input_or_execution_parameters", "reference_systems", "electronic_numerics", "optimization_structure", "interface_model", "surface_model"}
    if not isinstance(attribution, dict) or attribution.get("primary_category") not in allowed_categories or not isinstance(attribution.get("issue_codes"), list) or not str(attribution.get("reasoning", "")).strip():
        errors.append("problem_attribution requires an allowed category, issue_codes, and reasoning.")
        category = ""
    else:
        category = str(attribution["primary_category"])
    decision = str(source.get("decision_code", ""))
    if decision not in DECISIONS:
        errors.append("decision_code must be one of the nine permitted formal conclusions.")
    elif source.get("decision_label") != DECISIONS[decision][0]:
        errors.append(f"decision_label must be exactly {DECISIONS[decision][0]}.")
    for key in ("decision_reasons", "affected_task_ids", "reusable_artifacts"):
        if not isinstance(source.get(key), list) or (key == "decision_reasons" and not source.get(key)):
            errors.append(f"{key} must be {'nonempty ' if key == 'decision_reasons' else ''}a list.")
    if not str(source.get("recommended_action", "")).strip():
        errors.append("recommended_action is required.")
    selected_ids = [str(value) for value in plan.get("selected_task_ids", [])]
    accepted_ids = [str(value) for value in source.get("accepted_task_ids", [])] if isinstance(source.get("accepted_task_ids"), list) else []
    all_valid = task_checks_all_valid(task_checks)
    graph = load_graph(formal_dir)
    projected = projected_graph_after_acceptance(graph, selected_ids) if all_valid else None
    old_evidence = set(str(value) for value in graph.get("completed_evidence_node_ids", []))
    new_evidence = sorted(set(str(value) for value in projected.get("completed_evidence_node_ids", [])) - old_evidence) if projected else []
    projected_ready = ready_task_ids(projected) if projected else []
    projected_complete = workflow_is_complete(projected) if projected else False
    raw_actual_input_check = source.get("actual_input_check")
    actual_input_check: dict[str, Any] = raw_actual_input_check if isinstance(raw_actual_input_check, dict) else {}
    actual_differences = actual_input_check.get("differences")
    actual_difference_items = actual_differences if isinstance(actual_differences, list) else []
    unapproved_core = not core_approved and any(
        isinstance(item, dict) and item.get("category") == "core_method"
        for item in actual_difference_items
    )
    reference_failed = any(item.get("reference_comparability") == "failed" for item in task_checks.values())
    electronic_unstable = any(item.get("electronic_convergence") in {"unstable", "not_converged"} for item in task_checks.values())
    if batch.get("description_only") is True and decision != "FORMAL_RESULT_FILES_MISSING":
        errors.append("Description-only formal results can conclude only that necessary files are missing.")
    if unapproved_core and decision != "FORMAL_RESULT_FILES_MISSING":
        errors.append("An unapproved core-method change requires stage-1 reconfirmation before any formal acceptance/regeneration decision.")
    if decision == "FORMAL_RESULT_FILES_MISSING":
        if not (batch.get("description_only") is True or missing or completeness.get("status") == "incomplete" or actual_input_check.get("match_status") in {"unknown", "modified_unapproved"}):
            errors.append("Missing-files conclusion requires missing/description-only/unknown/unapproved evidence.")
        if category != "missing_files":
            errors.append("Missing-files conclusion requires problem_attribution.primary_category=missing_files.")
    elif decision == "FORMAL_REGENERATE_PARAMETERS":
        if category != "input_or_execution_parameters" or reference_failed or source.get("model_valid") is not True:
            errors.append("Parameter regeneration requires a valid model, comparable references, and input/execution parameter attribution.")
    elif decision == "FORMAL_REGENERATE_REFERENCES":
        if category != "reference_systems" or not reference_failed:
            errors.append("Reference regeneration requires failed reference comparability and reference_systems attribution.")
    elif decision == "FORMAL_ELECTRONIC_UNSTABLE":
        if category != "electronic_numerics" or not electronic_unstable or source.get("model_valid") is not True:
            errors.append("Electronic-instability conclusion requires unstable/nonconverged electronic evidence and a valid model.")
    elif decision in RETURN_ROUTES:
        expected_category = {"FORMAL_RETURN_OPTIMIZATION_REVIEW": "optimization_structure", "FORMAL_RETURN_INTERFACE_DESIGN": "interface_model", "FORMAL_RETURN_SURFACE_DESIGN": "surface_model"}[decision]
        if category != expected_category or source.get("upstream_failure_evidence") is not True:
            errors.append(f"{decision} requires {expected_category} attribution and explicit upstream failure evidence.")
    elif decision in {"FORMAL_RESULT_VALID_NEXT_BATCH", "FORMAL_EVIDENCE_NODE_COMPLETE"}:
        if not all_valid or missing or completeness.get("status") != "complete" or accepted_ids != selected_ids or category != "accepted":
            errors.append("Formal acceptance requires every selected task valid, complete files, exact accepted task IDs, and accepted attribution.")
        if actual_input_check.get("match_status") not in {"exact_match", "modified_reapproved"} or not core_approved:
            errors.append("Formal acceptance requires confirmed actual inputs and no unapproved core-method change.")
        if decision == "FORMAL_RESULT_VALID_NEXT_BATCH" and not projected_ready:
            errors.append("Valid-next-batch conclusion requires at least one projected prerequisite-ready task.")
        if decision == "FORMAL_EVIDENCE_NODE_COMPLETE" and not (new_evidence or projected_complete):
            errors.append("Evidence-node completion requires a newly completed evidence node or full workflow completion.")
    if errors:
        raise FormalError("Formal result analysis validation failed:\n- " + "\n- ".join(errors))
    version = next_analysis_version(formal_dir)
    target_state = DECISIONS[decision][1]
    if decision == "FORMAL_EVIDENCE_NODE_COMPLETE" and projected_complete:
        target_state = FORMAL_CALCULATION_WORKFLOW_COMPLETED
    accepted_result = decision in {"FORMAL_RESULT_VALID_NEXT_BATCH", "FORMAL_EVIDENCE_NODE_COMPLETE"}
    judged = copy_result_set(formal_dir, batch, accepted_result, version)
    analysis = copy.deepcopy(source)
    analysis.update(
        {
            "project_id": status["project_id"],
            "workflow_step": "stage2_step3_formal_result_analysis",
            "analysis_version": version,
            "batch_id": status["active_batch_id"],
            "result_version": batch["result_version"],
            "approved_batch_record": copy.deepcopy(status["active_approval"]["record"]),
            "decision_label": DECISIONS[decision][0],
            "result_state": target_state,
            "core_method_approved": core_approved,
            "engine_missing_expected_results": missing,
            "accepted_task_ids": selected_ids if accepted_result else [],
            "new_completed_evidence_node_ids": new_evidence if accepted_result else [],
            "ready_task_ids": projected_ready if accepted_result else [],
            "workflow_completed": projected_complete if accepted_result else False,
            "return_route": RETURN_ROUTES.get(decision),
            "judged_result_records": judged,
            **false_execution_flags(),
            "generated_at": utc_now(),
        }
    )
    analysis_path = formal_dir / f"formal_result_analysis_{version}.json"
    write_json(analysis_path, analysis)
    write_json(formal_dir / "result_analysis" / f"formal_result_analysis_{version}.json", analysis)
    write_json(formal_dir / "parsed_results" / f"formal_result_analysis_{version}_normalized.json", analysis)
    write_text(formal_dir / f"formal_result_analysis_{version}.md", render_result_analysis(analysis))
    write_text(formal_dir / f"parameter_difference_report_{version}.md", render_parameter_report(analysis))
    if accepted_result and projected is not None:
        graph = projected
    elif decision in {"FORMAL_REGENERATE_PARAMETERS", "FORMAL_REGENERATE_REFERENCES", "FORMAL_ELECTRONIC_UNSTABLE"}:
        nodes = graph_node_map(graph)
        for task_id in selected_ids:
            nodes[task_id]["status"] = "regeneration_required"
            if nodes[task_id].get("attempts"):
                nodes[task_id]["attempts"][-1]["status"] = "regeneration_required"
    elif decision in RETURN_ROUTES:
        nodes = graph_node_map(graph)
        for task_id in selected_ids:
            nodes[task_id]["status"] = "rejected"
            if nodes[task_id].get("attempts"):
                nodes[task_id]["attempts"][-1]["status"] = "rejected_upstream_return"
    graph_version = write_graph_snapshot(formal_dir, graph, f"FORMAL_RESULT_DECISION_{decision}")
    old = status["status"]
    status.update(
        {
            "status": target_state,
            "latest_analysis_version": version,
            "latest_analysis_record": file_record(analysis_path),
            "current_graph_version": graph_version,
            "decision_code": decision,
            "decision_label": DECISIONS[decision][0],
            "awaiting_additional_files": decision == "FORMAL_RESULT_FILES_MISSING",
            "return_route": RETURN_ROUTES.get(decision),
            "next_ready_task_ids": projected_ready if accepted_result else [],
            **false_execution_flags(),
            "updated_at": utc_now(),
        }
    )
    write_json(status_path(formal_dir), status)
    write_result_status_projection(formal_dir, status)
    append_log(formal_dir, {"event": "FORMAL_RESULT_JUDGED", "timestamp": utc_now(), "batch_id": status["active_batch_id"], "result_version": batch["result_version"], "analysis_version": version, "decision_code": decision, "decision_label": DECISIONS[decision][0], "status_before": old, "status_after": target_state, "accepted_task_ids": analysis["accepted_task_ids"], "completed_evidence_nodes": analysis["new_completed_evidence_node_ids"], **false_execution_flags()})
    return {"status": status, "analysis": analysis}


def candidate_versions_for_batch(formal_dir: Path, batch_id: str | None) -> list[str]:
    versions: list[str] = []
    for path in sorted(formal_dir.glob("formal_calculation_plan_v*.json")):
        try:
            plan = read_json(path)
        except (OSError, ValueError, json.JSONDecodeError):
            continue
        if isinstance(plan, dict) and plan.get("batch_id") == batch_id:
            versions.append(str(plan.get("plan_version")))
    return versions


def current_data(formal_dir: Path) -> dict[str, Any]:
    status = load_status(formal_dir)
    graph = load_graph(formal_dir)
    selection = None
    if status.get("current_selection_record"):
        selection = load_selection(formal_dir, status)
    plan = load_plan(formal_dir, status.get("current_candidate_version")) if status.get("current_candidate_version") else None
    impact = None
    if status.get("current_candidate_version"):
        impact_path = formal_dir / f"formal_impact_analysis_{status['current_candidate_version']}.json"
        impact = read_json(impact_path) if impact_path.is_file() else None
    result = load_result_batch(formal_dir, status) if status.get("current_result_record") else None
    analysis = None
    if status.get("latest_analysis_record"):
        analysis_path = verify_absolute_record(status["latest_analysis_record"], "latest formal result analysis")
        analysis = read_json(analysis_path)
    include_regeneration = status.get("status") == FORMAL_FILES_REGENERATION_REQUIRED
    return {
        "status": status,
        "task_graph": graph,
        "ready_task_ids": ready_task_ids(graph, include_regeneration=include_regeneration),
        "selection": selection,
        "plan": plan,
        "versions": candidate_versions_for_batch(formal_dir, status.get("active_batch_id")),
        "change_log": read_json(log_path(formal_dir)),
        "impact": impact,
        "latest_result": result,
        "latest_analysis": analysis,
    }


class FormalHandler(BaseHTTPRequestHandler):
    formal_dir: Path

    def log_message(self, format_string: str, *args: Any) -> None:
        sys.stderr.write("[formal-review] " + format_string % args + "\n")

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
        if length <= 0 or length > 24 * 1024 * 1024:
            raise FormalError("Request body must be between 1 byte and 24 MiB.")
        value = json.loads(self.rfile.read(length).decode("utf-8"))
        if not isinstance(value, dict):
            raise FormalError("Request body must be a JSON object.")
        return value

    def do_GET(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
        try:
            if path in {"/", "/formal_review.html"}:
                self.send_file(self.formal_dir / "formal_review.html", "text/html; charset=utf-8")
            elif path == "/api/state":
                self.send_json(current_data(self.formal_dir))
            elif path.startswith("/files/"):
                target = safe_relative_path(self.formal_dir, unquote(path[len("/files/") :]))
                if not target.is_file():
                    self.send_json({"error": "File not found"}, HTTPStatus.NOT_FOUND)
                else:
                    self.send_file(target)
            else:
                self.send_json({"error": "Not found"}, HTTPStatus.NOT_FOUND)
        except (FormalError, OSError, ValueError, json.JSONDecodeError) as exc:
            self.send_json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)

    def do_POST(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
        try:
            payload = self.body()
            if path == "/api/select-batch":
                result = select_batch(self.formal_dir, source_value=payload)
            elif path == "/api/submit":
                plan = payload.get("plan")
                if not isinstance(plan, dict):
                    raise FormalError("plan must be a JSON object.")
                result = submit_plan(self.formal_dir, source_value=plan, reason=str(payload.get("reason", "")))
            elif path == "/api/action":
                result = transition(
                    self.formal_dir,
                    str(payload.get("action", "")),
                    str(payload.get("reason", "")),
                    str(payload["version"]) if payload.get("version") else None,
                    str(payload.get("confirmed_by", "user")),
                )
            else:
                self.send_json({"error": "Not found"}, HTTPStatus.NOT_FOUND)
                return
            self.send_json({"ok": True, "result": result})
        except (FormalError, OSError, ValueError, json.JSONDecodeError) as exc:
            self.send_json({"ok": False, "error": str(exc)}, HTTPStatus.BAD_REQUEST)


def serve(formal_dir: Path, host: str, port: int, open_page: bool) -> None:
    ensure_review_html(formal_dir)
    handler = type("BoundFormalHandler", (FormalHandler,), {"formal_dir": formal_dir})
    server = ThreadingHTTPServer((host, port), handler)
    address = f"http://{host}:{server.server_address[1]}/"
    print(f"Formal calculation review page: {address}", flush=True)
    print("Press Ctrl+C to stop the local review service. This service never waits for or retrieves calculation results.", flush=True)
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

    start_parser = subparsers.add_parser("start", help="Verify approved gates and restore the formal task graph.")
    start_parser.add_argument("--planning-dir", type=Path, required=True)
    start_parser.add_argument("--results-dir", type=Path, required=True)
    start_parser.add_argument("--surface-dir", type=Path)
    start_parser.add_argument("--interface-dir", type=Path)
    start_parser.add_argument("--formal-dir", type=Path, default=Path("formal_calculations"))

    select_parser = subparsers.add_parser("select-batch", help="Record a user-confirmed prerequisite-ready minimum batch.")
    select_parser.add_argument("--formal-dir", type=Path, default=Path("formal_calculations"))
    select_parser.add_argument("--selection", type=Path, required=True)

    submit_parser = subparsers.add_parser("submit", help="Materialize a new immutable formal candidate version.")
    submit_parser.add_argument("--formal-dir", type=Path, default=Path("formal_calculations"))
    submit_parser.add_argument("--candidate", type=Path, required=True)
    submit_parser.add_argument("--reason", default="")

    action_parser = subparsers.add_parser("action", help="Approve, continue, restore, or reject a formal candidate.")
    action_parser.add_argument("--formal-dir", type=Path, default=Path("formal_calculations"))
    action_parser.add_argument("--action", choices=("approve", "accept", "continue", "restore", "reject", "reselect"), required=True)
    action_parser.add_argument("--reason", default="")
    action_parser.add_argument("--version")
    action_parser.add_argument("--confirmed-by", default="user")

    ingest_parser = subparsers.add_parser("ingest-results", help="Copy an immutable user-returned formal result batch.")
    ingest_parser.add_argument("--formal-dir", type=Path, default=Path("formal_calculations"))
    ingest_parser.add_argument("--manifest", type=Path, required=True)

    analysis_parser = subparsers.add_parser("analyze-results", help="Validate one evidence-linked exact formal result decision.")
    analysis_parser.add_argument("--formal-dir", type=Path, default=Path("formal_calculations"))
    analysis_parser.add_argument("--analysis", type=Path, required=True)

    serve_parser = subparsers.add_parser("serve", help="Serve and optionally open the formal review page.")
    serve_parser.add_argument("--formal-dir", type=Path, default=Path("formal_calculations"))
    serve_parser.add_argument("--host", default="127.0.0.1")
    serve_parser.add_argument("--port", type=int, default=0)
    serve_parser.add_argument("--open", action="store_true", dest="open_page")

    review_parser = subparsers.add_parser("review", help="Open the hash-bound Flask review gate and wait for a decision.")
    review_parser.add_argument("--formal-dir", type=Path, default=Path("formal_calculations"))
    review_parser.add_argument("--project-dir", type=Path)
    review_parser.add_argument("--title", default="第二阶段第三步：正式计算文件审查")
    review_parser.add_argument("--start-port", type=int, default=5050)
    review_parser.add_argument("--timeout", type=float, default=0.0)

    selection_review_parser = subparsers.add_parser("review-selection", help="Review the selected formal batch in an isolated browser gate.")
    selection_review_parser.add_argument("--formal-dir", type=Path, default=Path("formal_calculations"))
    selection_review_parser.add_argument("--project-dir", type=Path)
    selection_review_parser.add_argument("--title", default="Stage 2 step 3: formal batch selection review")
    selection_review_parser.add_argument("--start-port", type=int, default=5050)
    selection_review_parser.add_argument("--timeout", type=float, default=0.0)

    status_parser = subparsers.add_parser("status", help="Show formal state without waiting or monitoring.")
    status_parser.add_argument("--formal-dir", type=Path, default=Path("formal_calculations"))
    subparsers.add_parser("environment", help="Report optional static structure-library availability.")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        if args.command == "start":
            result = start(
                args.formal_dir.resolve(),
                args.planning_dir.resolve(),
                args.results_dir.resolve(),
                args.surface_dir.resolve() if args.surface_dir else None,
                args.interface_dir.resolve() if args.interface_dir else None,
            )
        elif args.command == "select-batch":
            result = select_batch(args.formal_dir.resolve(), source_path=args.selection.resolve())
        elif args.command == "submit":
            result = submit_plan(args.formal_dir.resolve(), source_path=args.candidate.resolve(), reason=args.reason)
        elif args.command == "action":
            result = transition(args.formal_dir.resolve(), args.action, args.reason, args.version, args.confirmed_by)
        elif args.command == "ingest-results":
            result = ingest_results(args.formal_dir.resolve(), args.manifest.resolve())
        elif args.command == "analyze-results":
            result = analyze_results(args.formal_dir.resolve(), args.analysis.resolve())
        elif args.command == "serve":
            serve(args.formal_dir.resolve(), args.host, args.port, args.open_page)
            return 0
        elif args.command == "review":
            formal_dir = args.formal_dir.resolve()
            project_dir = args.project_dir.resolve() if args.project_dir else formal_dir.parent
            result = browser_review(formal_dir, project_dir, args.title, args.start_port, args.timeout)
        elif args.command == "review-selection":
            formal_dir = args.formal_dir.resolve()
            project_dir = args.project_dir.resolve() if args.project_dir else formal_dir.parent
            result = browser_review_selection(formal_dir, project_dir, args.title, args.start_port, args.timeout)
        elif args.command == "status":
            result = current_data(args.formal_dir.resolve())
        elif args.command == "environment":
            result = detect_structure_tools()
        else:
            raise FormalError(f"Unsupported command: {args.command}")
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (FormalError, OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
