#!/usr/bin/env python3
"""Receive external calculation results, judge them, and generate follow-up files.

This program never runs scientific software, generated scripts, MPI, schedulers,
queue commands, remote downloads, background monitors, or automatic result retrieval.
"""

from __future__ import annotations

import argparse
import base64
import copy
import hashlib
import json
import re
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

WAITING_FOR_USER_CALCULATION_RESULT = "WAITING_FOR_USER_CALCULATION_RESULT"
CALCULATION_RESULT_RECEIVED = "CALCULATION_RESULT_RECEIVED"
RETURN_TO_SURFACE_REDESIGN = "RETURN_TO_SURFACE_REDESIGN"
RETURN_TO_INTERFACE_REDESIGN = "RETURN_TO_INTERFACE_REDESIGN"
REGENERATE_OPTIMIZATION_FILES = "REGENERATE_OPTIMIZATION_FILES"
OPTIMIZATION_RESTART_FILES_REQUIRED = "OPTIMIZATION_RESTART_FILES_REQUIRED"
OPTIMIZED_STRUCTURE_ACCEPTED = "OPTIMIZED_STRUCTURE_ACCEPTED"

VALID_STATES = {
    WAITING_FOR_USER_CALCULATION_RESULT,
    CALCULATION_RESULT_RECEIVED,
    RETURN_TO_SURFACE_REDESIGN,
    RETURN_TO_INTERFACE_REDESIGN,
    REGENERATE_OPTIMIZATION_FILES,
    OPTIMIZATION_RESTART_FILES_REQUIRED,
    OPTIMIZED_STRUCTURE_ACCEPTED,
}

DECISIONS = {
    RETURN_TO_SURFACE_REDESIGN: ("重新设计材料表面", RETURN_TO_SURFACE_REDESIGN),
    RETURN_TO_INTERFACE_REDESIGN: ("重新设计材料界面", RETURN_TO_INTERFACE_REDESIGN),
    REGENERATE_OPTIMIZATION_FILES: ("重新生成几何优化参数", REGENERATE_OPTIMIZATION_FILES),
    OPTIMIZATION_RESTART_FILES_REQUIRED: ("生成优化重启文件", OPTIMIZATION_RESTART_FILES_REQUIRED),
    "ADDITIONAL_FILES_REQUIRED": ("补充必要文件后重新判断", CALCULATION_RESULT_RECEIVED),
    OPTIMIZED_STRUCTURE_ACCEPTED: ("优化结构通过，可以进入下一步", OPTIMIZED_STRUCTURE_ACCEPTED),
}

USER_HANDOFF_PROMPT = """几何优化所需的结构文件、计算输入文件和运行脚本已经生成，并已完成静态检查。

请根据提供的运行说明，在本地工作站或超算平台上自行执行计算。你不需要保持当前页面持续打开，也不要退出或删除本次对话。计算结束后，请返回本对话，上传输出文件、优化后的结构文件和错误日志，或者直接描述计算状态与关键现象。

收到真实计算结果后，我会检查计算是否正常结束、几何优化是否收敛、结构是否合理，并判断需要重新设计材料表面、修改界面模型、调整计算参数，还是可以进入下一计算步骤。"""

ALLOWED_FILE_ROLES = {
    "actual_input",
    "main_output",
    "final_structure",
    "trajectory",
    "restart",
    "checkpoint",
    "wavefunction",
    "stderr",
    "job_script",
    "topology",
    "parameters",
    "energy_file",
    "other",
}

MINIMUM_ACCEPTANCE_ROLES = {
    "quantum_espresso": {"actual_input", "main_output", "final_structure"},
    "cp2k": {"actual_input", "main_output", "final_structure"},
    "gaussian": {"actual_input", "main_output", "final_structure"},
    "orca": {"actual_input", "main_output", "final_structure"},
    "gromacs": {"parameters", "main_output", "final_structure", "topology"},
}

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
}

SURFACE_ISSUES = {
    "surface_collapse",
    "non_target_reconstruction",
    "termination_lost",
    "ligand_detached",
    "no_bulk_like_center",
    "slab_too_thin",
    "vacuum_insufficient",
    "uncompensated_polarity",
    "surface_constraints_invalid",
    "defect_or_dopant_lost",
    "functionalization_environment_mismatch",
}

INTERFACE_ISSUES = {
    "components_separated",
    "atom_overlap",
    "component_penetration",
    "implausible_contact",
    "strain_distortion",
    "wrong_order",
    "initial_distance_invalid",
    "non_target_reaction",
}

NUMERICAL_ISSUES = {
    "scf_oscillation",
    "electronic_steps_exhausted",
    "mixing_invalid",
    "smearing_invalid",
    "initial_magnetization_invalid",
    "ionic_step_unstable",
    "optimizer_unstable",
    "parallel_error",
    "dependency_path_error",
}

RESTART_ISSUES = {"walltime_interruption", "scheduler_interruption", "ionic_step_limit"}

ACCEPTANCE_KEYS = (
    "program_normal",
    "scf_converged",
    "geometry_converged",
    "structure_reasonable",
    "composition_preserved",
    "constraints_and_boundaries_correct",
    "comparability_preserved",
    "final_structure_complete",
    "actual_parameters_confirmed",
)

NEXT_TASK_ROLES = {
    "interface_binding_energy": {"interface_single_point", "component_a_single_point", "component_b_single_point"},
    "charge_density_difference": {"interface_density", "component_a_density", "component_b_density"},
    "dos_pdos": {"scf", "nscf", "dos_or_pdos_postprocess"},
    "cohp": {"compatible_scf_or_nscf", "wavefunction_projection", "bonding_analysis_dependency"},
}


class ResultError(RuntimeError):
    """Raise for user-correctable result-workflow errors."""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_bytes(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_bytes(data)
    temporary.replace(path)


def write_text(path: Path, text: str) -> None:
    write_bytes(path, text.replace("\r\n", "\n").encode("utf-8"))


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
        raise ResultError(f"Expected a non-empty relative path under {root}: {raw_path!r}")
    resolved = (root / raw_path).resolve()
    try:
        resolved.relative_to(root.resolve())
    except ValueError as exc:
        raise ResultError(f"Path escapes the result directory: {raw_path}") from exc
    return resolved


def safe_name(value: str) -> str:
    name = re.sub(r"[^A-Za-z0-9._-]+", "_", value.strip())
    return name.strip("._") or "artifact"


def normalize_software(value: Any) -> str:
    compact = re.sub(r"[^a-z0-9]+", "", str(value).lower())
    return SOFTWARE_ALIASES.get(compact, compact)


def reject_forbidden_execution_claims(value: Any, label: str) -> None:
    """Reject user-supplied claims that this Skill executed or monitored work."""
    forbidden = {
        "calculation_executed_by_skill",
        "job_submitted_by_skill",
        "background_monitoring",
        "automatic_result_retrieval",
    }
    if isinstance(value, dict):
        for key, item in value.items():
            if key in forbidden and item is not False:
                raise ResultError(f"{label}.{key} must be false when supplied.")
            reject_forbidden_execution_claims(item, f"{label}.{key}")
    elif isinstance(value, list):
        for index, item in enumerate(value):
            reject_forbidden_execution_claims(item, f"{label}[{index}]")


def status_path(results_dir: Path) -> Path:
    return results_dir / "result_status.json"


def log_path(results_dir: Path) -> Path:
    return results_dir / "result_change_log.json"


def load_status(results_dir: Path) -> dict[str, Any]:
    path = status_path(results_dir)
    if not path.is_file():
        raise ResultError("result_status.json is missing; start the result-return workflow first.")
    status = read_json(path)
    if not isinstance(status, dict) or status.get("status") not in VALID_STATES:
        raise ResultError(f"Unknown result state: {status.get('status')!r}")
    return status


def append_log(results_dir: Path, entry: dict[str, Any]) -> None:
    path = log_path(results_dir)
    entries = read_json(path) if path.exists() else []
    if not isinstance(entries, list):
        raise ResultError("result_change_log.json must contain a list.")
    entries.append(entry)
    write_json(path, entries)


def file_record(path: Path) -> dict[str, Any]:
    return {"path": str(path.resolve()), "sha256": sha256(path), "size_bytes": path.stat().st_size}


def verify_absolute_record(record: Any, label: str) -> Path:
    if not isinstance(record, dict):
        raise ResultError(f"{label} is not a file record.")
    path = Path(str(record.get("path", "")))
    if not path.is_file() or sha256(path) != str(record.get("sha256", "")):
        raise ResultError(f"Frozen file changed or disappeared: {label}")
    return path


def manifest_for_tree(root: Path, base: Path) -> list[dict[str, Any]]:
    return [{"path": path.relative_to(base).as_posix(), "sha256": sha256(path), "size_bytes": path.stat().st_size} for path in sorted(root.rglob("*")) if path.is_file()]


def validate_relative_manifest(interface_dir: Path, records: Any, label: str) -> list[dict[str, Any]]:
    if not isinstance(records, list):
        raise ResultError(f"{label} manifest is missing.")
    validated: list[dict[str, Any]] = []
    for index, record in enumerate(records):
        if not isinstance(record, dict):
            raise ResultError(f"{label}[{index}] is invalid.")
        relative = str(record.get("path", ""))
        path = (interface_dir / relative).resolve()
        try:
            path.relative_to(interface_dir.resolve())
        except ValueError as exc:
            raise ResultError(f"Approved manifest path escapes interface_design: {relative}") from exc
        if not path.is_file() or sha256(path) != str(record.get("sha256", "")):
            raise ResultError(f"Approved manifest file changed or disappeared: {relative}")
        validated.append(copy.deepcopy(record))
    return validated


def verify_interface_delivery(interface_dir: Path) -> dict[str, Any]:
    paths = {
        "status": interface_dir / "interface_status.json",
        "design": interface_dir / "interface_design_approved.json",
        "parameters": interface_dir / "optimization_parameters_approved.json",
        "markdown": interface_dir / "interface_design_approved.md",
        "approval": interface_dir / "interface_file_approval_record.json",
    }
    required_dirs = {
        "calculation_inputs": interface_dir / "calculation_inputs_approved",
        "hpc_scripts": interface_dir / "hpc_scripts_approved",
        "approved_interfaces": interface_dir / "approved_interfaces",
    }
    missing = [name for name, path in paths.items() if not path.is_file()] + [name for name, path in required_dirs.items() if not path.is_dir()]
    if missing:
        raise ResultError("Approved interface/file delivery is incomplete: " + ", ".join(missing))
    interface_status = read_json(paths["status"])
    design = read_json(paths["design"])
    approval = read_json(paths["approval"])
    if interface_status.get("status") != "INTERFACE_FILES_APPROVED":
        raise ResultError("Interface files are not in INTERFACE_FILES_APPROVED.")
    if interface_status.get("calculation_executed") is not False or interface_status.get("job_submitted") is not False:
        raise ResultError("Interface delivery status contains an invalid execution/submission claim.")
    if approval.get("calculation_executed") is not False or approval.get("job_submitted") is not False:
        raise ResultError("Interface approval record contains an invalid execution/submission claim.")
    expected_hashes = {
        "design": approval.get("approved_design_sha256"),
        "parameters": approval.get("approved_parameters_sha256"),
        "markdown": approval.get("approved_markdown_sha256"),
    }
    for name, expected in expected_hashes.items():
        if not expected or sha256(paths[name]) != str(expected):
            raise ResultError(f"Approved interface {name} checksum does not match the approval record.")
    manifests = approval.get("approved_file_manifests")
    if not isinstance(manifests, dict):
        raise ResultError("Approved interface file manifests are missing.")
    calc_records = validate_relative_manifest(interface_dir, manifests.get("calculation_inputs_approved"), "calculation_inputs_approved")
    hpc_records = validate_relative_manifest(interface_dir, manifests.get("hpc_scripts_approved"), "hpc_scripts_approved")
    interface_records = validate_relative_manifest(interface_dir, manifests.get("approved_interfaces"), "approved_interfaces")
    calc_actual = manifest_for_tree(required_dirs["calculation_inputs"], interface_dir)
    hpc_actual = manifest_for_tree(required_dirs["hpc_scripts"], interface_dir)
    interface_actual = manifest_for_tree(required_dirs["approved_interfaces"], interface_dir)
    if {(r["path"], r["sha256"]) for r in calc_records} != {(r["path"], r["sha256"]) for r in calc_actual}:
        raise ResultError("Approved calculation input directory differs from its frozen manifest.")
    if {(r["path"], r["sha256"]) for r in hpc_records} != {(r["path"], r["sha256"]) for r in hpc_actual}:
        raise ResultError("Approved HPC/local script directory differs from its frozen manifest.")
    if {(r["path"], r["sha256"]) for r in interface_records} != {(r["path"], r["sha256"]) for r in interface_actual}:
        raise ResultError("Approved interface structure directory differs from its frozen manifest.")
    upstream_files: list[dict[str, Any]] = []
    for link_name in ("stage1_link", "surface_link"):
        link = design.get(link_name)
        if not isinstance(link, dict):
            raise ResultError(f"Approved interface design lacks {link_name}.")
        for record_name, record in link.get("files", {}).items():
            verify_absolute_record(record, f"{link_name}.{record_name}")
            upstream_files.append(copy.deepcopy(record))
    software = design.get("software_compatibility", {}).get("software")
    if not normalize_software(software):
        raise ResultError("Approved optimization software is missing.")
    frozen_files = [file_record(path) for path in paths.values()]
    frozen_files.extend({"path": str((interface_dir / item["path"]).resolve()), "sha256": item["sha256"], "size_bytes": item.get("size_bytes")} for item in calc_records + hpc_records + interface_records)
    frozen_files.extend(upstream_files)
    return {
        "project_id": design.get("project_id"),
        "interface_dir": str(interface_dir.resolve()),
        "approved_version": approval.get("approved_version"),
        "software": software,
        "normalized_software": normalize_software(software),
        "approved_design": {
            "selection": design.get("selection"),
            "interface_type": design.get("interface_type"),
            "software_compatibility": design.get("software_compatibility"),
            "optimization_parameters": design.get("optimization_parameters"),
            "comparison_policy": design.get("comparison_policy"),
            "stage1_link": design.get("stage1_link"),
            "surface_link": design.get("surface_link"),
        },
        "approved_calculation_files": calc_records,
        "approved_script_files": hpc_records,
        "approved_interface_structures": interface_records,
        "frozen_files": frozen_files,
    }


def verify_frozen_delivery(status: dict[str, Any]) -> None:
    gate = status.get("delivery_gate")
    if not isinstance(gate, dict):
        raise ResultError("Frozen delivery gate is missing.")
    for index, record in enumerate(gate.get("frozen_files", [])):
        verify_absolute_record(record, f"delivery_gate.frozen_files[{index}]")
    interface_status = read_json(Path(gate["interface_dir"]) / "interface_status.json")
    if interface_status.get("status") != "INTERFACE_FILES_APPROVED":
        raise ResultError("The interface delivery approval is no longer valid.")


def start(results_dir: Path, interface_dir: Path) -> dict[str, Any]:
    if status_path(results_dir).exists():
        raise ResultError("Result-return workflow already exists; start will not overwrite it.")
    gate = verify_interface_delivery(interface_dir.resolve())
    results_dir.mkdir(parents=True, exist_ok=True)
    for name in ("user_uploaded", "parsed_outputs", "accepted_structures", "rejected_structures", "restart_files", "regenerated_optimization_files", "next_step_files"):
        (results_dir / name).mkdir(exist_ok=True)
    handoff = "# Calculation File Delivery Handoff\n\n" + USER_HANDOFF_PROMPT + "\n"
    write_text(results_dir / "calculation_result_handoff.md", handoff)
    status = {
        "project_id": gate["project_id"],
        "workflow_step": "calculation_result_review",
        "status": WAITING_FOR_USER_CALCULATION_RESULT,
        "delivery_gate": gate,
        "current_result_batch": None,
        "latest_result_batch": None,
        "result_batches": [],
        "latest_analysis_version": None,
        "latest_next_task_version": None,
        "decision_code": None,
        "decision_label": None,
        "awaiting_additional_files": False,
        "awaiting_user_rerun": False,
        "next_task_access": False,
        "calculation_executed_by_skill": False,
        "job_submitted_by_skill": False,
        "background_monitoring": False,
        "automatic_result_retrieval": False,
        "updated_at": utc_now(),
    }
    write_json(status_path(results_dir), status)
    write_json(log_path(results_dir), [{"event": "CALCULATION_FILES_DELIVERED", "timestamp": utc_now(), "status_before": None, "status_after": WAITING_FOR_USER_CALCULATION_RESULT, "interface_version": gate["approved_version"], "calculation_executed_by_skill": False, "job_submitted_by_skill": False}])
    return {"status": status, "user_prompt": USER_HANDOFF_PROMPT}


def version_number(paths: list[Path], prefix: str) -> int:
    numbers: list[int] = []
    for path in paths:
        match = re.search(re.escape(prefix) + r"v(\d{3,})", path.stem)
        if match:
            numbers.append(int(match.group(1)))
    return max(numbers, default=0) + 1


def next_batch_version(results_dir: Path) -> str:
    return f"v{version_number(list(results_dir.glob('result_batch_v*.json')), 'result_batch_'):03d}"


def next_analysis_version(results_dir: Path) -> str:
    return f"v{version_number(list(results_dir.glob('result_analysis_v*.json')), 'result_analysis_'):03d}"


def next_task_version(results_dir: Path) -> str:
    return f"v{version_number(list(results_dir.glob('next_task_v*.json')), 'next_task_'):03d}"


def ingest(results_dir: Path, manifest_path: Path) -> dict[str, Any]:
    status = load_status(results_dir)
    verify_frozen_delivery(status)
    if status["status"] in {RETURN_TO_SURFACE_REDESIGN, RETURN_TO_INTERFACE_REDESIGN, OPTIMIZED_STRUCTURE_ACCEPTED}:
        raise ResultError("This result review is terminal; start the appropriate next/redesign workflow instead of overwriting it.")
    manifest = read_json(manifest_path)
    if not isinstance(manifest, dict):
        raise ResultError("Result manifest must be a JSON object.")
    reject_forbidden_execution_claims(manifest, "result_manifest")
    software = normalize_software(manifest.get("software"))
    if software != status["delivery_gate"]["normalized_software"]:
        raise ResultError("Result software does not match the approved optimization delivery.")
    if manifest.get("result_kind") != "geometry_optimization":
        raise ResultError("result_kind must be geometry_optimization.")
    files = manifest.get("files")
    if not isinstance(files, list):
        raise ResultError("files must be a list.")
    description_only = manifest.get("description_only") is True
    if not files and not description_only:
        raise ResultError("Provide real result files or explicitly set description_only with detailed facts.")
    if description_only:
        facts = manifest.get("described_facts")
        required = ("program_termination", "scf_status", "geometry_status", "final_force_or_unknown", "energy_trend_or_unknown", "structure_behavior", "errors")
        if not isinstance(facts, dict) or any(key not in facts for key in required):
            raise ResultError("Description-only intake requires termination, SCF, geometry, force, energy trend, structure behavior, and errors.")
    version = next_batch_version(results_dir)
    batch_dir = results_dir / "user_uploaded" / f"batch_{version}"
    if batch_dir.exists():
        raise ResultError(f"Result batch directory already exists: {batch_dir}")
    batch_dir.mkdir(parents=True)
    stored: list[dict[str, Any]] = []
    for index, item in enumerate(files, start=1):
        if not isinstance(item, dict) or not str(item.get("path", "")).strip():
            raise ResultError(f"files[{index - 1}] requires an actual path.")
        role = str(item.get("role", ""))
        if role not in ALLOWED_FILE_ROLES:
            raise ResultError(f"files[{index - 1}].role is invalid: {role}")
        source = Path(str(item["path"])).expanduser().resolve()
        if not source.is_file():
            raise ResultError(f"Uploaded result path is not a file: {source}")
        destination = batch_dir / f"{index:03d}_{safe_name(str(item.get('name') or source.name))}"
        shutil.copyfile(source, destination)
        stored.append({"role": role, "label": item.get("label"), "original_path": str(source), "stored_path": destination.relative_to(results_dir).as_posix(), "sha256": sha256(destination), "size_bytes": destination.stat().st_size, "ingested_at": utc_now()})
    batch = {
        "project_id": status["project_id"],
        "workflow_step": "calculation_result_review",
        "batch_version": version,
        "software": manifest.get("software"),
        "normalized_software": software,
        "result_kind": "geometry_optimization",
        "description_only": description_only,
        "user_description": manifest.get("user_description", ""),
        "described_facts": manifest.get("described_facts", {}),
        "actual_execution_context": manifest.get("actual_execution_context", {}),
        "files": stored,
        "delivery_interface_version": status["delivery_gate"]["approved_version"],
        "ingested_at": utc_now(),
    }
    write_json(results_dir / f"result_batch_{version}.json", batch)
    old = status["status"]
    batch_path = results_dir / f"result_batch_{version}.json"
    raw_batches = status.get("result_batches")
    batches: list[Any] = raw_batches if isinstance(raw_batches, list) else []
    batches.append({"version": version, "path": batch_path.name, "sha256": sha256(batch_path)})
    status.update({"status": CALCULATION_RESULT_RECEIVED, "current_result_batch": version, "latest_result_batch": version, "result_batches": batches, "awaiting_additional_files": False, "awaiting_user_rerun": False, "updated_at": utc_now()})
    write_json(status_path(results_dir), status)
    append_log(results_dir, {"event": "CALCULATION_RESULT_RECEIVED", "timestamp": utc_now(), "batch_version": version, "file_count": len(stored), "description_only": description_only, "status_before": old, "status_after": CALCULATION_RESULT_RECEIVED})
    return {"status": status, "batch": batch}


def load_batch(results_dir: Path, status: dict[str, Any], version: str) -> dict[str, Any]:
    record = next((item for item in status.get("result_batches", []) if isinstance(item, dict) and item.get("version") == version), None)
    if not record:
        raise ResultError(f"Result batch is not recorded: {version}")
    path = results_dir / str(record.get("path", ""))
    if not path.is_file() or sha256(path) != str(record.get("sha256", "")):
        raise ResultError(f"Result batch {version} changed or disappeared.")
    batch = read_json(path)
    if not isinstance(batch, dict):
        raise ResultError(f"Result batch {version} is invalid.")
    return batch


def batch_file_map(batch: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {str(item.get("stored_path")): item for item in batch.get("files", []) if isinstance(item, dict) and item.get("stored_path")}


def validate_batch_file(results_dir: Path, batch_files: dict[str, dict[str, Any]], record: Any, label: str, required_roles: set[str] | None = None) -> dict[str, Any]:
    if not isinstance(record, dict):
        raise ResultError(f"{label} must be a result-file reference.")
    stored_path = str(record.get("stored_path", ""))
    canonical = batch_files.get(stored_path)
    if not canonical:
        raise ResultError(f"{label} does not reference a file in the current result batch: {stored_path}")
    if record.get("sha256") != canonical.get("sha256"):
        raise ResultError(f"{label} checksum differs from the immutable batch record.")
    if required_roles and canonical.get("role") not in required_roles:
        raise ResultError(f"{label} has role {canonical.get('role')}, expected one of {sorted(required_roles)}.")
    actual = safe_relative_path(results_dir, stored_path)
    if not actual.is_file() or sha256(actual) != canonical.get("sha256"):
        raise ResultError(f"{label} file changed or disappeared: {stored_path}")
    return canonical


def validate_evidence_item(results_dir: Path, batch: dict[str, Any], batch_files: dict[str, dict[str, Any]], item: Any, label: str) -> None:
    if not isinstance(item, dict) or not str(item.get("observation", "")).strip():
        raise ResultError(f"{label} requires a concrete observation.")
    if item.get("source") == "user_description":
        if batch.get("description_only") is not True:
            raise ResultError(f"{label} may cite user_description only for a description-only batch.")
        return
    validate_batch_file(results_dir, batch_files, item, label)


def validate_status_evidence(results_dir: Path, batch: dict[str, Any], batch_files: dict[str, dict[str, Any]], section: Any, label: str, allowed: set[str]) -> str:
    if not isinstance(section, dict):
        raise ResultError(f"{label} must be an object.")
    status = str(section.get("status", ""))
    if status not in allowed:
        raise ResultError(f"{label}.status must be one of {sorted(allowed)}.")
    evidence = section.get("evidence")
    if not isinstance(evidence, list):
        raise ResultError(f"{label}.evidence must be a list.")
    if status != "unknown" and not evidence:
        raise ResultError(f"{label} requires file-linked evidence for status {status}.")
    for index, item in enumerate(evidence):
        validate_evidence_item(results_dir, batch, batch_files, item, f"{label}.evidence[{index}]")
    return status


def prepare_analysis(results_dir: Path, status: dict[str, Any], batch: dict[str, Any], source: dict[str, Any], version: str) -> dict[str, Any]:
    analysis = copy.deepcopy(source)
    analysis["project_id"] = status["project_id"]
    analysis["workflow_step"] = "calculation_result_review"
    analysis["analysis_version"] = version
    analysis["result_batch_version"] = batch["batch_version"]
    analysis["software"] = batch["software"]
    analysis["delivery_interface_version"] = status["delivery_gate"]["approved_version"]
    analysis["generated_at"] = utc_now()
    input_check = analysis.get("actual_input_check")
    if not isinstance(input_check, dict):
        input_check = {}
        analysis["actual_input_check"] = input_check
    input_check["approved_input_files"] = copy.deepcopy(status["delivery_gate"]["approved_calculation_files"])
    input_check["actual_input_files"] = [copy.deepcopy(item) for item in batch.get("files", []) if isinstance(item, dict) and item.get("role") in {"actual_input", "parameters"}]
    analysis["execution_provenance"] = {
        "calculation_executed_by_skill": False,
        "job_submitted_by_skill": False,
        "background_monitoring": False,
        "automatic_result_retrieval": False,
        "result_source": "user_returned_files_or_description",
    }
    return analysis


def validate_analysis_core(results_dir: Path, status: dict[str, Any], batch: dict[str, Any], analysis: dict[str, Any]) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    batch_files = batch_file_map(batch)
    if normalize_software(analysis.get("software")) != status["delivery_gate"]["normalized_software"]:
        errors.append("Analysis software differs from the approved/result software.")
    source_evidence = analysis.get("source_evidence")
    if not isinstance(source_evidence, list):
        errors.append("source_evidence must be a list.")
        source_evidence = []
    elif not source_evidence:
        errors.append("source_evidence must contain at least one concrete file-linked or description-linked observation.")
    for index, item in enumerate(source_evidence):
        try:
            validate_evidence_item(results_dir, batch, batch_files, item, f"source_evidence[{index}]")
        except ResultError as exc:
            errors.append(str(exc))

    input_check = analysis.get("actual_input_check")
    if not isinstance(input_check, dict):
        errors.append("actual_input_check must be an object.")
        input_check = {}
    match_status = input_check.get("match_status")
    if match_status not in {"exact_match", "modified_reapproved", "modified_unapproved", "unknown"}:
        errors.append("actual_input_check.match_status is invalid.")
    differences = input_check.get("differences")
    if not isinstance(differences, list):
        errors.append("actual_input_check.differences must be a list.")
        differences = []
    approved_hashes = {str(item.get("sha256")) for item in status["delivery_gate"]["approved_calculation_files"] if isinstance(item, dict)}
    actual_input_records = [item for item in batch.get("files", []) if isinstance(item, dict) and item.get("role") in {"actual_input", "parameters"}]
    actual_hashes = {str(item.get("sha256")) for item in actual_input_records}
    if match_status == "exact_match" and not approved_hashes.intersection(actual_hashes):
        errors.append("exact_match requires an uploaded actual input whose checksum matches an approved input.")
    if match_status == "exact_match" and differences:
        errors.append("exact_match cannot contain parameter differences.")
    if str(match_status).startswith("modified") and not differences:
        errors.append("A modified actual input requires explicit parameter differences.")
    core_differences = []
    for index, item in enumerate(differences):
        if not isinstance(item, dict):
            errors.append(f"actual_input_check.differences[{index}] must be an object.")
            continue
        for key in ("parameter", "approved_value", "actual_value", "category", "scientific_impact", "reapproval_status"):
            if key not in item:
                errors.append(f"actual_input_check.differences[{index}].{key} is required.")
        if item.get("category") not in {"core_method", "numerical", "structure_constraint", "boundary", "resource", "path_dependency"}:
            errors.append(f"actual_input_check.differences[{index}].category is invalid.")
        if item.get("reapproval_status") not in {"not_required", "approved", "required"}:
            errors.append(f"actual_input_check.differences[{index}].reapproval_status is invalid.")
        if item.get("category") == "core_method":
            core_differences.append(item)
    if not isinstance(input_check.get("core_method_consistent"), bool):
        errors.append("actual_input_check.core_method_consistent must be boolean.")
    if core_differences and match_status == "modified_reapproved":
        record = input_check.get("stage1_reapproval_record")
        try:
            verify_absolute_record(record, "actual_input_check.stage1_reapproval_record")
        except ResultError as exc:
            errors.append(str(exc))
        if any(item.get("reapproval_status") != "approved" for item in core_differences):
            errors.append("Every core-method difference requires explicit approved reapproval status.")
    unapproved_core_method = bool(core_differences) and (
        match_status != "modified_reapproved"
        or any(item.get("reapproval_status") != "approved" for item in core_differences)
    )

    section_statuses: dict[str, str] = {}
    for key, allowed in (
        ("program_termination", {"normal", "abnormal", "interrupted", "unknown"}),
        ("electronic_scf", {"converged", "not_converged", "unstable", "unknown"}),
        ("geometry_optimization", {"converged", "not_converged", "near_converged", "interrupted", "unknown"}),
        ("structure_assessment", {"reasonable", "surface_failure", "interface_failure", "nonphysical", "unknown"}),
    ):
        try:
            section_statuses[key] = validate_status_evidence(results_dir, batch, batch_files, analysis.get(key), key, allowed)
        except ResultError as exc:
            errors.append(str(exc))
            section_statuses[key] = "unknown"

    raw_structure = analysis.get("structure_assessment")
    structure: dict[str, Any] = raw_structure if isinstance(raw_structure, dict) else {}
    checks = structure.get("checks")
    required_structure_checks = ("composition_preserved", "component_identity", "interface_separation", "overlaps", "bonds_and_coordination", "surface_termination", "bulk_like_center", "defects_dopants_functionalization", "fixed_regions", "vacuum_and_periodicity", "magnetic_state")
    if not isinstance(checks, dict):
        errors.append("structure_assessment.checks must be an object.")
    else:
        for key in required_structure_checks:
            if key not in checks:
                errors.append(f"structure_assessment.checks.{key} is required.")

    comparison = analysis.get("comparison_integrity")
    if not isinstance(comparison, dict) or comparison.get("status") not in {"preserved", "broken", "unknown"} or not isinstance(comparison.get("checks"), dict):
        errors.append("comparison_integrity requires status and cell/strain/composition/parameter checks.")

    completeness = analysis.get("file_completeness")
    if not isinstance(completeness, dict) or completeness.get("status") not in {"sufficient", "insufficient"} or not isinstance(completeness.get("missing_roles"), list) or not str(completeness.get("limitations", "")).strip():
        errors.append("file_completeness requires status, missing_roles, and limitations.")
    roles = {str(item.get("role")) for item in batch.get("files", []) if isinstance(item, dict)}
    minimum = MINIMUM_ACCEPTANCE_ROLES.get(status["delivery_gate"]["normalized_software"], {"actual_input", "main_output", "final_structure"})
    missing_minimum = sorted(minimum - roles)
    if isinstance(completeness, dict) and completeness.get("status") == "sufficient" and missing_minimum:
        errors.append("file_completeness cannot be sufficient; missing recommended roles: " + ", ".join(missing_minimum))

    attribution = analysis.get("problem_attribution")
    if not isinstance(attribution, dict) or not str(attribution.get("primary_category", "")).strip() or not isinstance(attribution.get("issue_codes"), list) or not str(attribution.get("reasoning", "")).strip():
        errors.append("problem_attribution requires primary_category, issue_codes, and reasoning.")
        issue_codes: set[str] = set()
        category = ""
    else:
        issue_codes = {str(value) for value in attribution["issue_codes"]}
        category = str(attribution["primary_category"])

    decision = str(analysis.get("decision_code", ""))
    if decision not in DECISIONS:
        errors.append("decision_code must be one of the six permitted conclusions.")
    else:
        expected_label = DECISIONS[decision][0]
        if analysis.get("decision_label") != expected_label:
            errors.append(f"decision_label must be exactly {expected_label}.")
    if not isinstance(analysis.get("decision_reasons"), list) or not analysis.get("decision_reasons"):
        errors.append("decision_reasons must be a nonempty list.")
    for key in ("affected_downstream_parameters", "reusable_artifacts"):
        if not isinstance(analysis.get(key), list):
            errors.append(f"{key} must be a list.")
    if not str(analysis.get("recommended_action", "")).strip():
        errors.append("recommended_action is required.")

    final_structures = analysis.get("final_structure_files")
    if not isinstance(final_structures, list):
        errors.append("final_structure_files must be a list.")
        final_structures = []
    for index, record in enumerate(final_structures):
        try:
            validate_batch_file(results_dir, batch_files, record, f"final_structure_files[{index}]", {"final_structure", "restart", "trajectory"})
        except ResultError as exc:
            errors.append(str(exc))

    if batch.get("description_only") is True and decision != "ADDITIONAL_FILES_REQUIRED":
        errors.append("A description-only batch can conclude only 补充必要文件后重新判断.")
    if unapproved_core_method and decision != "ADDITIONAL_FILES_REQUIRED":
        errors.append("An unapproved core-method change must return for stage-1 reconfirmation via 补充必要文件后重新判断.")
    if decision == RETURN_TO_SURFACE_REDESIGN:
        if section_statuses["structure_assessment"] != "surface_failure" or category != "surface_model" or not issue_codes.intersection(SURFACE_ISSUES):
            errors.append("Surface-redesign decision requires a surface_failure assessment and a recognized surface issue.")
    elif decision == RETURN_TO_INTERFACE_REDESIGN:
        if section_statuses["structure_assessment"] != "interface_failure" or category != "interface_model" or not issue_codes.intersection(INTERFACE_ISSUES):
            errors.append("Interface-redesign decision requires interface_failure evidence and a recognized interface issue.")
    elif decision == REGENERATE_OPTIMIZATION_FILES:
        if section_statuses["structure_assessment"] != "reasonable" or category != "numerical_parameters" or not issue_codes.intersection(NUMERICAL_ISSUES):
            errors.append("Parameter-regeneration decision requires a reasonable model and recognized numerical/file issue.")
    elif decision == OPTIMIZATION_RESTART_FILES_REQUIRED:
        if section_statuses["structure_assessment"] != "reasonable" or section_statuses["geometry_optimization"] not in {"near_converged", "interrupted"} or category != "interrupted_restart" or not issue_codes.intersection(RESTART_ISSUES) or not final_structures:
            errors.append("Restart decision requires a reasonable near-converged/interrupted structure, restart cause, and last-valid structure.")
    elif decision == "ADDITIONAL_FILES_REQUIRED":
        if isinstance(completeness, dict) and completeness.get("status") != "insufficient" and match_status not in {"unknown", "modified_unapproved"} and not core_differences:
            warnings.append("Additional-files decision has no explicit incomplete/unknown/unapproved trigger; review its justification.")
    elif decision == OPTIMIZED_STRUCTURE_ACCEPTED:
        acceptance = analysis.get("acceptance_conditions")
        if not isinstance(acceptance, dict) or any(acceptance.get(key) is not True for key in ACCEPTANCE_KEYS):
            errors.append("Every optimized-structure acceptance condition must be true.")
        if section_statuses != {"program_termination": "normal", "electronic_scf": "converged", "geometry_optimization": "converged", "structure_assessment": "reasonable"}:
            errors.append("Acceptance requires normal termination, converged SCF/geometry, and a reasonable structure.")
        if match_status not in {"exact_match", "modified_reapproved"} or input_check.get("core_method_consistent") is not True:
            errors.append("Acceptance requires confirmed actual parameters and a consistent/reapproved method.")
        if not isinstance(comparison, dict) or comparison.get("status") != "preserved":
            errors.append("Acceptance requires preserved comparison integrity.")
        if not isinstance(completeness, dict) or completeness.get("status") != "sufficient" or missing_minimum:
            errors.append("Acceptance requires complete minimum result files.")
        if category != "accepted" or issue_codes:
            errors.append("Acceptance attribution must be accepted with no unresolved issue codes.")
        if not final_structures or any(batch_files.get(str(item.get("stored_path")), {}).get("role") != "final_structure" for item in final_structures if isinstance(item, dict)):
            errors.append("Acceptance requires at least one cited final_structure file.")

    if decision not in {REGENERATE_OPTIMIZATION_FILES, OPTIMIZATION_RESTART_FILES_REQUIRED} and analysis.get("followup_file_specs"):
        errors.append("followup_file_specs are allowed only for parameter-regeneration or restart decisions.")
    return errors, warnings


def materialize_followup(results_dir: Path, analysis: dict[str, Any], version: str) -> list[dict[str, Any]]:
    decision = analysis["decision_code"]
    if decision == REGENERATE_OPTIMIZATION_FILES:
        root = results_dir / "regenerated_optimization_files" / version
        changes = analysis.get("parameter_changes")
        if not isinstance(changes, list) or not changes:
            raise ResultError("Parameter regeneration requires a nonempty parameter_changes list.")
        for index, item in enumerate(changes):
            if not isinstance(item, dict) or any(key not in item for key in ("parameter", "before", "after", "reason", "effect_class")):
                raise ResultError(f"parameter_changes[{index}] requires parameter, before, after, reason, and effect_class.")
            if item.get("effect_class") not in {"numerical_stability", "scientific_method"}:
                raise ResultError(f"parameter_changes[{index}].effect_class is invalid.")
            if item.get("effect_class") == "scientific_method":
                record = analysis.get("actual_input_check", {}).get("stage1_reapproval_record")
                verify_absolute_record(record, "actual_input_check.stage1_reapproval_record")
    elif decision == OPTIMIZATION_RESTART_FILES_REQUIRED:
        root = results_dir / "restart_files" / version
        continuation = analysis.get("restart_continuation")
        if not isinstance(continuation, dict):
            raise ResultError("Restart decision requires restart_continuation.")
        for key in ("same_optimization", "method_unchanged", "boundary_unchanged", "constraints_unchanged", "spin_unchanged"):
            if continuation.get(key) is not True:
                raise ResultError(f"restart_continuation.{key} must be true.")
        if not str(continuation.get("source_last_valid_structure", "")).strip():
            raise ResultError("restart_continuation.source_last_valid_structure is required.")
    else:
        return []

    specs = analysis.get("followup_file_specs")
    if not isinstance(specs, list) or not specs:
        raise ResultError("The selected follow-up decision requires file specifications.")
    if root.exists():
        raise ResultError(f"Follow-up version directory already exists: {root}")
    roles = {str(item.get("role")) for item in specs if isinstance(item, dict)}
    input_roles = {"geometry_optimization_input", "restart_input"}
    script_roles = {"hpc_script", "local_run_script"}
    if not roles.intersection(input_roles) or not roles.intersection(script_roles):
        raise ResultError("Follow-up files require at least one optimization/restart input and one HPC/local execution-instruction script.")
    static = analysis.get("followup_static_validation")
    if not isinstance(static, dict) or static.get("format_status") != "passed" or static.get("logic_status") != "passed" or not isinstance(static.get("files_checked"), list) or not isinstance(static.get("not_determinable"), list):
        raise ResultError("followup_static_validation requires passed format/logic checks, files_checked, and not_determinable.")
    checked = {str(item) for item in static["files_checked"]}
    for index, item in enumerate(specs):
        if not isinstance(item, dict) or not str(item.get("path", "")).strip() or not str(item.get("role", "")).strip() or not str(item.get("source", "")).strip():
            raise ResultError(f"followup_file_specs[{index}] requires path, role, and source.")
        if Path(str(item["path"])).name not in checked and str(item["path"]) not in checked:
            raise ResultError(f"followup_static_validation.files_checked omits {item['path']}.")
        if "content" not in item and "content_base64" not in item:
            raise ResultError(f"followup_file_specs[{index}] requires content or content_base64.")
    records: list[dict[str, Any]] = []
    for item in specs:
        target = safe_relative_path(root, str(item["path"]))
        if "content" in item:
            if not isinstance(item["content"], str):
                raise ResultError(f"Follow-up content must be text: {item['path']}")
            write_text(target, item["content"])
        else:
            try:
                write_bytes(target, base64.b64decode(str(item["content_base64"]), validate=True))
            except ValueError as exc:
                raise ResultError(f"Invalid base64 follow-up content: {item['path']}") from exc
        records.append({"path": target.relative_to(results_dir).as_posix(), "sha256": sha256(target), "size_bytes": target.stat().st_size, "role": item.get("role"), "software": item.get("software"), "source": item.get("source")})
    return records


def compact(value: Any, limit: int = 500) -> str:
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


def render_parameter_differences(analysis: dict[str, Any]) -> str:
    check = analysis.get("actual_input_check", {})
    rows = [[item.get("parameter"), item.get("approved_value"), item.get("actual_value"), item.get("category"), item.get("scientific_impact"), item.get("reapproval_status")] for item in check.get("differences", []) if isinstance(item, dict)]
    lines = [
        f"# Parameter Difference Report {analysis.get('analysis_version')}",
        "",
        f"- Actual-input match: {check.get('match_status')}",
        f"- Core method consistent: {check.get('core_method_consistent')}",
        f"- Actual version label: {check.get('actual_version_label', '')}",
        f"- Comparability impact: {check.get('comparability_impact', '')}",
        "",
        markdown_table(["Parameter", "Approved", "Actual", "Category", "Impact", "Reapproval"], rows) if rows else "No parameter difference was recorded.",
        "",
    ]
    return "\n".join(lines)


def render_analysis_report(analysis: dict[str, Any]) -> str:
    lines = [
        f"# Calculation Result Judgment {analysis.get('analysis_version')}",
        "",
        f"## 唯一结论：{analysis.get('decision_label')}",
        "",
        "This judgment concerns user-returned results. The Skill did not execute or submit the calculation.",
        "",
        "## Actual files",
        "",
    ]
    for item in analysis.get("source_evidence", []):
        lines.append(f"- `{item.get('stored_path') or item.get('source')}` — {item.get('observation')} — `{item.get('sha256', '')}`")
    lines.extend(["", "## Four independent checks", ""])
    lines.extend(
        [
            f"- Program termination: {compact(analysis.get('program_termination'))}",
            f"- Electronic SCF: {compact(analysis.get('electronic_scf'))}",
            f"- Geometry optimization: {compact(analysis.get('geometry_optimization'))}",
            f"- Structure reasonableness: {compact(analysis.get('structure_assessment'))}",
            f"- Comparison integrity: {compact(analysis.get('comparison_integrity'))}",
            "",
            "## Problem attribution and action",
            "",
            f"- Attribution: {compact(analysis.get('problem_attribution'))}",
            f"- Reasons: {compact(analysis.get('decision_reasons'))}",
            f"- Affected downstream parameters: {compact(analysis.get('affected_downstream_parameters'))}",
            f"- Recommended action: {analysis.get('recommended_action', '')}",
            f"- Reusable artifacts: {compact(analysis.get('reusable_artifacts'))}",
            "",
            "## File completeness and limitations",
            "",
            f"- {compact(analysis.get('file_completeness'))}",
            "- Static/file review cannot replace an actual program run or prove an unobserved result.",
            "",
        ]
    )
    if analysis.get("generated_followup_artifacts"):
        lines.extend(["## Generated follow-up files (not executed)", ""])
        lines.extend([f"- `{item.get('path')}` — {item.get('role')} — `{item.get('sha256')}`" for item in analysis["generated_followup_artifacts"]])
        lines.append("")
    return "\n".join(lines)


def route_task_ids(value: Any, valid_ids: set[str], output: list[str]) -> None:
    if isinstance(value, str) and value in valid_ids and value not in output:
        output.append(value)
    elif isinstance(value, dict):
        for child in value.values():
            route_task_ids(child, valid_ids, output)
    elif isinstance(value, list):
        for child in value:
            route_task_ids(child, valid_ids, output)


def infer_task_type(task: dict[str, Any]) -> str:
    text = json.dumps({"name": task.get("name"), "target_parameters": task.get("target_parameters"), "evidence_role": task.get("evidence_role")}, ensure_ascii=False).lower()
    if "binding" in text or "结合能" in text or "界面能" in text:
        return "interface_binding_energy"
    if "charge density difference" in text or "电荷密度差" in text or "cdd" in text:
        return "charge_density_difference"
    if "cohp" in text or "成键" in text:
        return "cohp"
    if "pdos" in text or re.search(r"\bdos\b", text):
        return "dos_pdos"
    if "adsorption" in text or "吸附" in text:
        return "adsorption_configuration_design"
    return "approved_task_requires_dedicated_generator"


def recommend_next_task(status: dict[str, Any], analysis: dict[str, Any]) -> dict[str, Any] | None:
    plan_record = status["delivery_gate"]["approved_design"]["stage1_link"]["files"].get("plan")
    plan_path = verify_absolute_record(plan_record, "stage1 approved plan")
    plan = read_json(plan_path)
    tasks = [task for task in plan.get("tasks", []) if isinstance(task, dict) and str(task.get("status", "")).lower() not in {"deleted", "rejected"}]
    task_map = {str(task.get("id")): task for task in tasks if task.get("id")}
    completed = set(str(item) for item in analysis.get("completed_task_ids", []) if item)
    completed.update(str(item) for item in status["delivery_gate"]["approved_design"].get("software_compatibility", {}).get("approved_task_ids", []) if item)
    ordered: list[str] = []
    route_task_ids(plan.get("execution_route"), set(task_map), ordered)
    ordered.extend(task_id for task_id in task_map if task_id not in ordered)
    for task_id in ordered:
        if task_id in completed:
            continue
        task = task_map[task_id]
        prerequisites = {str(item) for item in task.get("prerequisites", []) if item} if isinstance(task.get("prerequisites"), list) else set()
        if prerequisites.issubset(completed):
            return {"task_id": task_id, "task_name": task.get("name"), "task_type": infer_task_type(task), "target_parameters": task.get("target_parameters"), "evidence_role": task.get("evidence_role"), "prerequisites": sorted(prerequisites), "basis": "First retained uncompleted task whose approved prerequisites are satisfied."}
    return None


def copy_judged_structures(results_dir: Path, batch: dict[str, Any], analysis: dict[str, Any], version: str) -> list[dict[str, Any]]:
    decision = analysis["decision_code"]
    if decision == OPTIMIZED_STRUCTURE_ACCEPTED:
        root = results_dir / "accepted_structures" / version
    elif decision in {RETURN_TO_SURFACE_REDESIGN, RETURN_TO_INTERFACE_REDESIGN}:
        root = results_dir / "rejected_structures" / version
    else:
        return []
    if root.exists():
        raise ResultError(f"Judged-structure version directory already exists: {root}")
    root.mkdir(parents=True)
    batch_files = batch_file_map(batch)
    records: list[dict[str, Any]] = []
    for index, reference in enumerate(analysis.get("final_structure_files", []), start=1):
        canonical = validate_batch_file(results_dir, batch_files, reference, f"final_structure_files[{index - 1}]")
        source = safe_relative_path(results_dir, str(canonical["stored_path"]))
        target = root / f"{index:03d}_{safe_name(source.name)}"
        shutil.copyfile(source, target)
        records.append({"path": target.relative_to(results_dir).as_posix(), "sha256": sha256(target), "source_stored_path": canonical["stored_path"], "source_sha256": canonical["sha256"], "judgment": decision})
    return records


def analyze_results(results_dir: Path, source_path: Path) -> dict[str, Any]:
    status = load_status(results_dir)
    verify_frozen_delivery(status)
    if status["status"] != CALCULATION_RESULT_RECEIVED or not status.get("current_result_batch"):
        raise ResultError("Analysis requires CALCULATION_RESULT_RECEIVED with a current batch.")
    batch = load_batch(results_dir, status, status["current_result_batch"])
    source = read_json(source_path)
    if not isinstance(source, dict):
        raise ResultError("Analysis source must be a JSON object.")
    reject_forbidden_execution_claims(source, "analysis_source")
    version = next_analysis_version(results_dir)
    analysis = prepare_analysis(results_dir, status, batch, source, version)
    errors, warnings = validate_analysis_core(results_dir, status, batch, analysis)
    if errors:
        raise ResultError("Result analysis validation failed:\n- " + "\n- ".join(errors))
    artifacts = materialize_followup(results_dir, analysis, version)
    analysis["generated_followup_artifacts"] = artifacts
    analysis["judged_structure_records"] = copy_judged_structures(results_dir, batch, analysis, version)
    if analysis["decision_code"] == OPTIMIZED_STRUCTURE_ACCEPTED:
        analysis["next_task_recommendation"] = recommend_next_task(status, analysis)
    analysis["validation_warnings"] = warnings
    analysis["calculation_executed_by_skill"] = False
    analysis["job_submitted_by_skill"] = False
    analysis_path = results_dir / f"result_analysis_{version}.json"
    write_json(analysis_path, analysis)
    write_json(results_dir / "parsed_outputs" / f"analysis_{version}_normalized.json", analysis)
    write_text(results_dir / f"result_analysis_{version}.md", render_analysis_report(analysis))
    difference_report = render_parameter_differences(analysis)
    write_text(results_dir / f"parameter_difference_report_{version}.md", difference_report)
    write_text(results_dir / "parameter_difference_report.md", difference_report)
    decision = analysis["decision_code"]
    old = status["status"]
    new_state = DECISIONS[decision][1]
    status.update(
        {
            "status": new_state,
            "latest_analysis_version": version,
            "latest_analysis_sha256": sha256(analysis_path),
            "decision_code": decision,
            "decision_label": DECISIONS[decision][0],
            "awaiting_additional_files": decision == "ADDITIONAL_FILES_REQUIRED",
            "awaiting_user_rerun": decision in {REGENERATE_OPTIMIZATION_FILES, OPTIMIZATION_RESTART_FILES_REQUIRED},
            "next_task_access": decision == OPTIMIZED_STRUCTURE_ACCEPTED,
            "next_task_recommendation": analysis.get("next_task_recommendation"),
            "calculation_executed_by_skill": False,
            "job_submitted_by_skill": False,
            "background_monitoring": False,
            "automatic_result_retrieval": False,
            "updated_at": utc_now(),
        }
    )
    write_json(status_path(results_dir), status)
    append_log(results_dir, {"event": "CALCULATION_RESULT_JUDGED", "timestamp": utc_now(), "batch_version": batch["batch_version"], "analysis_version": version, "decision_code": decision, "decision_label": DECISIONS[decision][0], "status_before": old, "status_after": new_state, "calculation_executed_by_skill": False, "job_submitted_by_skill": False})
    result: dict[str, Any] = {"status": status, "analysis": analysis}
    if decision in {REGENERATE_OPTIMIZATION_FILES, OPTIMIZATION_RESTART_FILES_REQUIRED}:
        result["user_prompt"] = USER_HANDOFF_PROMPT
    return result


def materialize_next_specs(results_dir: Path, source: dict[str, Any], version: str, required_roles: set[str]) -> list[dict[str, Any]]:
    specs = source.get("file_specs")
    if not isinstance(specs, list) or not specs:
        raise ResultError("Next task requires file_specs.")
    roles = {str(item.get("role")) for item in specs if isinstance(item, dict)}
    missing = sorted(required_roles - roles)
    if missing:
        raise ResultError("Next-task file roles are missing: " + ", ".join(missing))
    if not roles.intersection({"hpc_script", "local_run_script"}):
        raise ResultError("Next-task package requires an HPC or local-run instruction script.")
    static = source.get("static_validation")
    if not isinstance(static, dict) or static.get("format_status") != "passed" or static.get("logic_status") != "passed" or not isinstance(static.get("files_checked"), list) or not isinstance(static.get("not_determinable"), list):
        raise ResultError("Next-task static_validation requires passed format/logic checks, files_checked, and not_determinable.")
    checked = {str(item) for item in static["files_checked"]}
    root = results_dir / "next_step_files" / version
    if root.exists():
        raise ResultError(f"Next-task version directory already exists: {root}")
    for index, item in enumerate(specs):
        if not isinstance(item, dict) or any(not str(item.get(key, "")).strip() for key in ("path", "role", "source")):
            raise ResultError(f"file_specs[{index}] requires path, role, and source.")
        if str(item["path"]) not in checked and Path(str(item["path"])).name not in checked:
            raise ResultError(f"static_validation.files_checked omits {item['path']}.")
        if "content" not in item and "content_base64" not in item:
            raise ResultError(f"file_specs[{index}] requires content or content_base64.")
    records: list[dict[str, Any]] = []
    for item in specs:
        target = safe_relative_path(root, str(item["path"]))
        if "content" in item:
            if not isinstance(item["content"], str):
                raise ResultError(f"Next-task content must be text: {item['path']}")
            write_text(target, item["content"])
        else:
            try:
                write_bytes(target, base64.b64decode(str(item["content_base64"]), validate=True))
            except ValueError as exc:
                raise ResultError(f"Invalid next-task base64 content: {item['path']}") from exc
        records.append({"path": target.relative_to(results_dir).as_posix(), "sha256": sha256(target), "size_bytes": target.stat().st_size, "role": item.get("role"), "software": item.get("software"), "source": item.get("source")})
    return records


def render_next_task(package: dict[str, Any]) -> str:
    lines = [
        f"# Next Approved Task Package {package.get('next_task_version')}",
        "",
        f"- Task: {package.get('task_id')} — {package.get('task_name')}",
        f"- Type: {package.get('task_type')}",
        f"- Purpose: {package.get('scientific_purpose')}",
        f"- Accepted structure: {compact(package.get('accepted_structure'))}",
        f"- Route: {package.get('route')}",
        "- Calculation executed by Skill: false",
        "- Job submitted by Skill: false",
        "",
        "## Comparison rules",
        "",
        "```json",
        json.dumps(package.get("comparison_checks", {}), ensure_ascii=False, indent=2),
        "```",
        "",
        "## Generated files",
        "",
    ]
    lines.extend([f"- `{item.get('path')}` — {item.get('role')} — `{item.get('sha256')}`" for item in package.get("generated_artifacts", [])] or ["- No formal files; route to the required design workflow."])
    lines.extend(["", "These files were generated and statically checked but not run or submitted.", ""])
    return "\n".join(lines)


def next_step(results_dir: Path, source_path: Path) -> dict[str, Any]:
    status = load_status(results_dir)
    verify_frozen_delivery(status)
    if status["status"] != OPTIMIZED_STRUCTURE_ACCEPTED or not status.get("next_task_access"):
        raise ResultError("Next-task generation requires OPTIMIZED_STRUCTURE_ACCEPTED.")
    analysis_version = str(status.get("latest_analysis_version", ""))
    analysis_path = results_dir / f"result_analysis_{analysis_version}.json"
    if not analysis_path.is_file() or sha256(analysis_path) != str(status.get("latest_analysis_sha256", "")):
        raise ResultError("Accepted result analysis changed or disappeared.")
    analysis = read_json(analysis_path)
    source = read_json(source_path)
    if not isinstance(source, dict):
        raise ResultError("Next-task source must be a JSON object.")
    reject_forbidden_execution_claims(source, "next_task_source")
    plan_record = status["delivery_gate"]["approved_design"]["stage1_link"]["files"].get("plan")
    plan = read_json(verify_absolute_record(plan_record, "stage1 approved plan"))
    tasks = [task for task in plan.get("tasks", []) if isinstance(task, dict) and str(task.get("status", "")).lower() not in {"deleted", "rejected"}]
    task_map = {str(task.get("id")): task for task in tasks if task.get("id")}
    task_id = str(source.get("task_id", ""))
    if task_id not in task_map:
        raise ResultError("task_id is not a retained stage-1 approved task.")
    recommendation = status.get("next_task_recommendation")
    if isinstance(recommendation, dict) and recommendation.get("task_id") and task_id != str(recommendation["task_id"]):
        raise ResultError("task_id does not match the next prerequisite-ready stage-1 task.")
    task = task_map[task_id]
    completed = {str(item) for item in source.get("completed_task_ids", []) if item} if isinstance(source.get("completed_task_ids"), list) else set()
    completed.update(str(item) for item in status["delivery_gate"]["approved_design"].get("software_compatibility", {}).get("approved_task_ids", []) if item)
    prerequisites = {str(item) for item in task.get("prerequisites", []) if item} if isinstance(task.get("prerequisites"), list) else set()
    if not prerequisites.issubset(completed):
        raise ResultError("Next-task prerequisites are not all recorded as completed.")
    task_type = str(source.get("task_type", ""))
    inferred = infer_task_type(task)
    if task_type not in set(NEXT_TASK_ROLES) | {"adsorption_configuration_design"}:
        raise ResultError("task_type is not supported by this result handoff.")
    if inferred != "approved_task_requires_dedicated_generator" and task_type != inferred:
        raise ResultError(f"task_type {task_type} conflicts with the approved task content ({inferred}).")
    accepted_records = analysis.get("judged_structure_records")
    if not isinstance(accepted_records, list) or not accepted_records:
        raise ResultError("Accepted analysis contains no accepted structure record.")
    accepted_source = source.get("accepted_structure")
    if not isinstance(accepted_source, dict):
        raise ResultError("accepted_structure must reference the accepted analysis record.")
    accepted = next((item for item in accepted_records if isinstance(item, dict) and item.get("path") == accepted_source.get("path") and item.get("sha256") == accepted_source.get("sha256")), None)
    if not accepted:
        raise ResultError("accepted_structure is not part of the accepted result analysis.")
    accepted_path = safe_relative_path(results_dir, str(accepted["path"]))
    if not accepted_path.is_file() or sha256(accepted_path) != accepted["sha256"]:
        raise ResultError("Accepted structure changed or disappeared.")
    if not str(source.get("scientific_purpose", "")).strip():
        raise ResultError("scientific_purpose is required.")
    comparison = source.get("comparison_checks")
    if not isinstance(comparison, dict):
        raise ResultError("comparison_checks must be an object.")
    if task_type == "interface_binding_energy":
        for key in ("same_in_plane_cell", "same_strain", "same_numerical_parameters"):
            if comparison.get(key) is not True:
                raise ResultError(f"Binding-energy package requires comparison_checks.{key}: true.")
    if task_type == "charge_density_difference":
        for key in ("same_lattice", "same_positions", "same_grid", "same_parameters"):
            if comparison.get(key) is not True:
                raise ResultError(f"CDD package requires comparison_checks.{key}: true.")
    version = next_task_version(results_dir)
    if task_type == "adsorption_configuration_design":
        if source.get("file_specs"):
            raise ResultError("Adsorption must route to configuration design; do not generate arbitrary formal adsorption files here.")
        artifacts: list[dict[str, Any]] = []
        route = "ADSORPTION_CONFIGURATION_DESIGN_REQUIRED"
    else:
        artifacts = materialize_next_specs(results_dir, source, version, NEXT_TASK_ROLES[task_type])
        route = "FILES_GENERATED_FOR_EXTERNAL_EXECUTION"
    package = {
        "project_id": status["project_id"],
        "workflow_step": "calculation_result_review_next_task",
        "next_task_version": version,
        "accepted_analysis_version": analysis_version,
        "accepted_structure": copy.deepcopy(accepted),
        "task_id": task_id,
        "task_name": task.get("name"),
        "task_type": task_type,
        "scientific_purpose": source.get("scientific_purpose"),
        "completed_task_ids": sorted(completed),
        "prerequisites": sorted(prerequisites),
        "comparison_checks": comparison,
        "dependencies": source.get("dependencies", []),
        "static_validation": source.get("static_validation", {}),
        "generated_artifacts": artifacts,
        "route": route,
        "calculation_executed_by_skill": False,
        "job_submitted_by_skill": False,
        "generated_at": utc_now(),
    }
    package_path = results_dir / f"next_task_{version}.json"
    write_json(package_path, package)
    write_text(results_dir / f"next_task_{version}.md", render_next_task(package))
    status.update({"latest_next_task_version": version, "latest_next_task_sha256": sha256(package_path), "next_task_result_status": WAITING_FOR_USER_CALCULATION_RESULT if artifacts else None, "next_task_route": route, "calculation_executed_by_skill": False, "job_submitted_by_skill": False, "background_monitoring": False, "automatic_result_retrieval": False, "updated_at": utc_now()})
    write_json(status_path(results_dir), status)
    append_log(results_dir, {"event": "NEXT_APPROVED_TASK_PREPARED", "timestamp": utc_now(), "next_task_version": version, "task_id": task_id, "task_type": task_type, "route": route, "calculation_executed_by_skill": False, "job_submitted_by_skill": False})
    result: dict[str, Any] = {"status": status, "package": package}
    if artifacts:
        result["user_prompt"] = USER_HANDOFF_PROMPT
    return result


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    start_parser = subparsers.add_parser("start", help="Verify delivered interface files and enter WAITING_FOR_USER_CALCULATION_RESULT.")
    start_parser.add_argument("--interface-dir", type=Path, required=True)
    start_parser.add_argument("--results-dir", type=Path, default=Path("calculation_results"))

    ingest_parser = subparsers.add_parser("ingest", help="Copy a user-returned result batch without interpreting it as success.")
    ingest_parser.add_argument("--results-dir", type=Path, default=Path("calculation_results"))
    ingest_parser.add_argument("--manifest", type=Path, required=True)

    analysis_parser = subparsers.add_parser("analyze", help="Validate and record one evidence-backed result judgment.")
    analysis_parser.add_argument("--results-dir", type=Path, default=Path("calculation_results"))
    analysis_parser.add_argument("--analysis", type=Path, required=True)

    next_parser = subparsers.add_parser("next-step", help="Generate files for the next prerequisite-ready approved task.")
    next_parser.add_argument("--results-dir", type=Path, default=Path("calculation_results"))
    next_parser.add_argument("--task", type=Path, required=True)

    status_parser = subparsers.add_parser("status", help="Show the result state without waiting or monitoring.")
    status_parser.add_argument("--results-dir", type=Path, default=Path("calculation_results"))
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        if args.command == "start":
            result = start(args.results_dir.resolve(), args.interface_dir.resolve())
        elif args.command == "ingest":
            result = ingest(args.results_dir.resolve(), args.manifest.resolve())
        elif args.command == "analyze":
            result = analyze_results(args.results_dir.resolve(), args.analysis.resolve())
        elif args.command == "next-step":
            result = next_step(args.results_dir.resolve(), args.task.resolve())
        elif args.command == "status":
            result = load_status(args.results_dir.resolve())
        else:
            raise ResultError(f"Unsupported command: {args.command}")
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (ResultError, OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
