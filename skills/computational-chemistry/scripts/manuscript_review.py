#!/usr/bin/env python3
"""Version evidence-calibrated manuscript text and reproduction guidance.

The engine reads immutable workflow evidence and writes manuscript artifacts. It
never runs calculations, post-processing, plotting, schedulers, remote retrieval,
paper submission, or open-source recomputation.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
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

WAITING_FOR_MANUSCRIPT_INPUT = "WAITING_FOR_MANUSCRIPT_INPUT"
SOURCE_RECORDS_VALIDATED = "SOURCE_RECORDS_VALIDATED"
SOFTWARE_LICENSE_REVIEWED = "SOFTWARE_LICENSE_REVIEWED"
CONCLUSION_DRAFT_GENERATED = "CONCLUSION_DRAFT_GENERATED"
METHOD_STATEMENT_GENERATED = "METHOD_STATEMENT_GENERATED"
OPEN_SOURCE_MAPPING_GENERATED = "OPEN_SOURCE_MAPPING_GENERATED"
WAITING_FOR_MANUSCRIPT_REVIEW = "WAITING_FOR_MANUSCRIPT_REVIEW"
USER_MANUSCRIPT_EDITED = "USER_MANUSCRIPT_EDITED"
MANUSCRIPT_IMPACT_ANALYZED = "MANUSCRIPT_IMPACT_ANALYZED"
WAITING_FOR_MANUSCRIPT_APPROVAL = "WAITING_FOR_MANUSCRIPT_APPROVAL"
MANUSCRIPT_CONTENT_APPROVED = "MANUSCRIPT_CONTENT_APPROVED"
STAGE4_REVIEW_REJECTED = "STAGE4_REVIEW_REJECTED"

VALID_STATES = {
    WAITING_FOR_MANUSCRIPT_INPUT,
    SOURCE_RECORDS_VALIDATED,
    SOFTWARE_LICENSE_REVIEWED,
    CONCLUSION_DRAFT_GENERATED,
    METHOD_STATEMENT_GENERATED,
    OPEN_SOURCE_MAPPING_GENERATED,
    WAITING_FOR_MANUSCRIPT_REVIEW,
    USER_MANUSCRIPT_EDITED,
    MANUSCRIPT_IMPACT_ANALYZED,
    WAITING_FOR_MANUSCRIPT_APPROVAL,
    WAITING_FOR_REVIEW_DECISION,
    STAGE4_REVIEW_REJECTED,
    MANUSCRIPT_CONTENT_APPROVED,
}

FALSE_FLAGS = {
    "calculation_executed_by_skill",
    "postprocessing_executed_by_skill",
    "job_submitted_by_skill",
    "queue_queried_by_skill",
    "remote_result_retrieval",
    "background_monitoring",
    "research_figures_generated_by_skill",
    "open_source_recalculation_performed",
    "existing_results_attributed_to_alternative",
}

LICENSE_CATEGORIES = {
    "open_source",
    "commercial_or_closed",
    "free_non_open",
    "institutional_license",
    "unconfirmed",
}
NONOPEN_LICENSES = LICENSE_CATEGORIES - {"open_source"}
VERSION_STATUSES = {"confirmed", "unconfirmed"}
FILE_ROLES = {"actual_input", "main_output", "result_data", "postprocess_output", "model", "other"}
IDENTIFICATION_TYPES = {"input_syntax", "output_header", "version_string", "user_statement"}
STRONG_IDENTIFICATION_TYPES = {"output_header", "version_string", "user_statement"}
MODEL_SOURCE_ROLES = {
    "approved_model",
    "surface_approval",
    "interface_approval",
    "accepted_structure",
    "actual_parameter_report",
    "model_summary",
}
EXPERIMENT_SOURCE_ROLES = {"experiment_data", "experiment_summary", "theory_experiment_mapping"}

PARAMETER_FIELDS = (
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
    "total_charge",
    "convergence",
    "vacuum",
    "fixed_atoms",
    "lattice_cell",
    "boundary_conditions",
)

DOCUMENT_TYPES = {"research_article", "thesis", "report", "supporting_information"}
LANGUAGES = {"zh", "en", "bilingual"}
METHOD_DETAILS = {"full", "concise", "both"}
CONCLUSION_LEVELS = {"data", "property", "mechanism", "overall"}
STRENGTHS = {
    "STRONGLY_SUPPORTED",
    "SUPPORTED",
    "PARTIALLY_SUPPORTED",
    "INCONCLUSIVE",
    "CONTRADICTED",
}
STRENGTH_ORDER = {
    "INCONCLUSIVE": 0,
    "PARTIALLY_SUPPORTED": 1,
    "SUPPORTED": 2,
    "STRONGLY_SUPPORTED": 3,
}
EXPERIMENT_RELATIONS = {"direct", "interpretive", "none"}
EQUIVALENCE_CLASSES = {"direct", "approximate", "not_transferable"}
CAPABILITY_STATUSES = {"verified", "requires_check", "not_suitable"}

MISSING_VERSION_STATEMENT = "软件版本信息未在现有文件中确认，正式投稿前需由用户补充。"
OPEN_SOURCE_DISCLAIMER = "该开源方案用于提供等效复现路径，尚未用于重新生成本文结果。由于不同程序的数值实现、赝势或基组体系存在差异，复现时可能获得存在合理数值偏差的结果。"

HIGH_CERTAINTY_PHRASES = (
    "完全证明",
    "进一步证明",
    "唯一证明",
    "definitively prove",
    "fully prove",
    "conclusively prove",
    "the sole cause",
)
CAUTIOUS_PHRASES = ("提示", "一定程度", "可能", "suggest", "may", "partially", "indicate a possible")
INCONCLUSIVE_PHRASES = ("尚不足", "无法确定", "不能确定", "证据不足", "inconclusive", "insufficient", "uncertain")
CONTRADICTED_PHRASES = ("不一致", "相反", "矛盾", "contradict", "inconsistent", "opposite")


class ManuscriptError(RuntimeError):
    """Raise for user-correctable stage-4 workflow errors."""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def false_flags() -> dict[str, bool]:
    return {name: False for name in sorted(FALSE_FLAGS)}


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_bytes(path: Path, value: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_bytes(value)
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


def file_record(path: Path, **extra: Any) -> dict[str, Any]:
    return {
        "path": str(path.resolve()),
        "sha256": sha256(path),
        "size_bytes": path.stat().st_size,
        **extra,
    }


def verify_file_record(record: Any, label: str) -> Path:
    if not isinstance(record, dict):
        raise ManuscriptError(f"{label} is not a file record.")
    path = Path(str(record.get("path", "")))
    if not path.is_file() or sha256(path) != str(record.get("sha256", "")):
        raise ManuscriptError(f"Frozen file changed or disappeared: {label}")
    return path


def safe_identifier(value: Any, label: str) -> str:
    raw = str(value or "").strip()
    if not raw or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,191}", raw):
        raise ManuscriptError(f"{label} must be a nonempty safe identifier.")
    return raw


def safe_name(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", value.strip())
    return cleaned.strip("._") or "item"


def safe_relative_path(root: Path, raw_path: str) -> Path:
    candidate = Path(unquote(raw_path.replace("\\", "/")))
    if candidate.is_absolute() or any(part in {"", ".", ".."} for part in candidate.parts):
        raise ManuscriptError("Unsafe relative path.")
    root_resolved = root.resolve()
    target = (root_resolved / candidate).resolve()
    if target != root_resolved and root_resolved not in target.parents:
        raise ManuscriptError("Path escapes manuscript_generation.")
    return target


def ensure_false_flags(value: Any, label: str = "payload") -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            if key in FALSE_FLAGS and item is not False:
                raise ManuscriptError(f"{label}.{key} must remain false.")
            ensure_false_flags(item, f"{label}.{key}")
    elif isinstance(value, list):
        for index, item in enumerate(value):
            ensure_false_flags(item, f"{label}[{index}]")


def word_count(value: str) -> int:
    return len(re.findall(r"[\u3400-\u9fff]|[A-Za-z0-9]+(?:[-'][A-Za-z0-9]+)*", value))


def normalize_text_list(value: Any, label: str, allow_empty: bool = True) -> list[str]:
    if not isinstance(value, list):
        raise ManuscriptError(f"{label} must be a list.")
    output = [str(item).strip() for item in value]
    if any(not item for item in output):
        raise ManuscriptError(f"{label} cannot contain blank items.")
    if not allow_empty and not output:
        raise ManuscriptError(f"{label} cannot be empty.")
    return output


def version_number(paths: list[Path], prefix: str) -> int:
    values: list[int] = []
    for path in paths:
        match = re.search(re.escape(prefix) + r"v(\d{3,})", path.stem)
        if match:
            values.append(int(match.group(1)))
    return max(values, default=0) + 1


def next_version(directory: Path, prefix: str) -> str:
    return f"v{version_number(list(directory.glob(prefix + 'v*.json')), prefix):03d}"


def status_path(manuscript_dir: Path) -> Path:
    return manuscript_dir / "manuscript_status.json"


def change_log_path(manuscript_dir: Path) -> Path:
    return manuscript_dir / "manuscript_change_log.json"


def append_log(manuscript_dir: Path, entry: dict[str, Any]) -> None:
    path = change_log_path(manuscript_dir)
    records = read_json(path) if path.is_file() else []
    if not isinstance(records, list):
        raise ManuscriptError("manuscript_change_log.json must contain a list.")
    records.append({**entry, "recorded_at": utc_now()})
    write_json(path, records)


def review_asset_path() -> Path:
    return Path(__file__).resolve().parent.parent / "assets" / "manuscript_review.html"


def ensure_review_html(manuscript_dir: Path) -> None:
    asset = review_asset_path()
    if not asset.is_file():
        raise ManuscriptError("The stage-4 manuscript review asset is missing.")
    target = manuscript_dir / "manuscript_review.html"
    if not target.is_file() or sha256(target) != sha256(asset):
        write_bytes(target, asset.read_bytes())


def resolve_source_file(manifest_path: Path | None, raw: Any) -> Path:
    value = str(raw or "").strip()
    if not value:
        raise ManuscriptError("A source file path is required.")
    path = Path(value)
    if not path.is_absolute():
        if manifest_path is None:
            raise ManuscriptError("Browser/API source paths must be absolute.")
        path = manifest_path.parent / path
    path = path.resolve()
    if not path.is_file():
        raise ManuscriptError(f"Source file is missing: {path}")
    return path


def verify_stage1(planning_dir: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    paths = {
        "stage1_status": planning_dir / "stage1_status.json",
        "stage1_plan": planning_dir / "stage1_plan_approved.json",
        "stage1_markdown": planning_dir / "stage1_plan_approved.md",
    }
    missing = [name for name, path in paths.items() if not path.is_file()]
    if missing:
        raise ManuscriptError("Stage-1 approved sources are incomplete: " + ", ".join(missing))
    status = read_json(paths["stage1_status"])
    plan = read_json(paths["stage1_plan"])
    if status.get("status") != "APPROVED" or str(status.get("project_id")) != str(plan.get("project_id")):
        raise ManuscriptError("Stage 1 must be APPROVED with a matching project ID.")
    if not plan.get("evidence_chain"):
        raise ManuscriptError("The approved stage-1 evidence chain is missing.")
    return plan, [file_record(path, source_name=name, source_kind="stage1") for name, path in paths.items()]


def verify_formal(formal_dir: Path, project_id: Any) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    paths = {
        "formal_task_graph": formal_dir / "formal_task_graph.json",
        "formal_result_status": formal_dir / "formal_result_status.json",
    }
    missing = [name for name, path in paths.items() if not path.is_file()]
    if missing:
        raise ManuscriptError("Formal sources are incomplete: " + ", ".join(missing))
    graph = read_json(paths["formal_task_graph"])
    projection = read_json(paths["formal_result_status"])
    if str(graph.get("project_id")) != str(project_id) or str(projection.get("project_id")) != str(project_id):
        raise ManuscriptError("Formal sources do not match the stage-1 project.")
    return graph, [file_record(path, source_name=name, source_kind="formal") for name, path in paths.items()]


def collect_stage3_sources(analysis_dir: Path, project_id: Any) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]:
    status_file = analysis_dir / "processing_status.json"
    if not status_file.is_file():
        raise ManuscriptError("Stage-3 processing_status.json is missing.")
    status = read_json(status_file)
    if (
        str(status.get("project_id")) != str(project_id)
        or status.get("status") != "RESULTS_APPROVED"
        or status.get("overall_stage_complete") is not True
    ):
        raise ManuscriptError("Stage 3 must be RESULTS_APPROVED with overall_stage_complete true.")
    records = [file_record(status_file, source_name="stage3_status", source_kind="stage3")]
    conclusions: list[dict[str, Any]] = []
    seen_nodes: set[str] = set()
    approvals = status.get("approval_records", [])
    if not isinstance(approvals, list) or not approvals:
        raise ManuscriptError("Stage-3 analysis approval history is missing.")
    for approval_index, approval_record in enumerate(approvals, start=1):
        approval_path = verify_file_record(approval_record, f"stage-3 approval record {approval_index}")
        records.append(file_record(approval_path, source_name=f"stage3_approval_{approval_index}", source_kind="stage3"))
        approval = read_json(approval_path)
        analysis_path = verify_file_record(approval.get("analysis_record"), f"stage-3 approved analysis {approval_index}")
        validation_path = verify_file_record(approval.get("validation_record"), f"stage-3 validation {approval_index}")
        records.extend(
            [
                file_record(analysis_path, source_name=f"stage3_analysis_{approval_index}", source_kind="stage3"),
                file_record(validation_path, source_name=f"stage3_validation_{approval_index}", source_kind="stage3"),
            ]
        )
        analysis = read_json(analysis_path)
        evidence_by_id = {
            str(item.get("evidence_id")): item
            for item in analysis.get("evidence_items", [])
            if isinstance(item, dict) and item.get("evidence_id")
        }
        for conclusion_index, item in enumerate(analysis.get("conclusions", []), start=1):
            if not isinstance(item, dict) or item.get("strength") not in STRENGTHS:
                raise ManuscriptError("An approved stage-3 conclusion has an invalid strength.")
            evidence_ids = [str(value) for value in item.get("evidence_item_ids", [])]
            roles = sorted({str(evidence_by_id[value].get("evidence_role")) for value in evidence_ids if value in evidence_by_id})
            conclusion_id = f"{analysis.get('analysis_version', f'A{approval_index:03d}')}:C{conclusion_index:03d}"
            conclusions.append(
                {
                    "conclusion_id": conclusion_id,
                    "analysis_version": analysis.get("analysis_version"),
                    "task_ids": copy.deepcopy(analysis.get("task_ids", [])),
                    "dataset_ids": copy.deepcopy(analysis.get("dataset_ids", [])),
                    "evidence_node_ids": copy.deepcopy(analysis.get("validated_evidence_node_ids", [])),
                    "claim": str(item.get("claim", "")),
                    "strength": item.get("strength"),
                    "limitations": copy.deepcopy(item.get("limitations", [])),
                    "evidence_item_ids": evidence_ids,
                    "evidence_roles": roles,
                    "data_conclusion": analysis.get("data_conclusion"),
                    "physical_meaning": analysis.get("physical_meaning"),
                    "corroboration": copy.deepcopy(analysis.get("corroboration", [])),
                    "experimental_correspondence": copy.deepcopy(analysis.get("experimental_correspondence", [])),
                    "conclusion_boundary": copy.deepcopy(analysis.get("conclusion_boundary", [])),
                    "source_analysis_record": file_record(analysis_path),
                }
            )
        seen_nodes.update(str(item) for item in approval.get("all_validated_evidence_node_ids", []))
    if set(str(item) for item in status.get("validated_evidence_node_ids", [])) - seen_nodes:
        raise ManuscriptError("Stage-3 validated-node status is not covered by approval history.")
    if not conclusions:
        raise ManuscriptError("No approved stage-3 conclusion is available.")
    return status, records, conclusions


def verify_model_manifest(path: Path, project_id: Any) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    value = read_json(path)
    if not isinstance(value, dict) or str(value.get("project_id")) != str(project_id):
        raise ManuscriptError("Model/experiment source manifest has the wrong project ID.")
    model_items = value.get("model_records", [])
    experiment_items = value.get("experiment_records", [])
    if not isinstance(model_items, list) or not model_items:
        raise ManuscriptError("At least one approved model source record is required.")
    if not isinstance(experiment_items, list):
        raise ManuscriptError("experiment_records must be a list.")
    records = [file_record(path, source_name="model_experiment_manifest", source_kind="stage2_or_experiment")]
    normalized_models: list[dict[str, Any]] = []
    for index, item in enumerate(model_items):
        if not isinstance(item, dict) or item.get("role") not in MODEL_SOURCE_ROLES:
            raise ManuscriptError(f"model_records[{index}] has an invalid role.")
        source = resolve_source_file(path, item.get("path"))
        record = file_record(source, source_name=f"model_record_{index + 1}", source_kind="stage2_model", role=item["role"])
        records.append(record)
        normalized_models.append({**record, "description": str(item.get("description", "")).strip()})
    normalized_experiments: list[dict[str, Any]] = []
    for index, item in enumerate(experiment_items):
        if not isinstance(item, dict) or item.get("role") not in EXPERIMENT_SOURCE_ROLES:
            raise ManuscriptError(f"experiment_records[{index}] has an invalid role.")
        source = resolve_source_file(path, item.get("path"))
        record = file_record(source, source_name=f"experiment_record_{index + 1}", source_kind="experiment", role=item["role"])
        records.append(record)
        normalized_experiments.append({**record, "description": str(item.get("description", "")).strip()})
    return records, normalized_models + normalized_experiments


def verify_upstream_gate(status: dict[str, Any]) -> None:
    gate = status.get("upstream_gate")
    if not isinstance(gate, dict):
        raise ManuscriptError("The upstream gate is missing.")
    for index, record in enumerate(gate.get("records", [])):
        verify_file_record(record, f"upstream gate record {index + 1}")
    verify_file_record(status.get("upstream_snapshot_record"), "stage-4 upstream snapshot")


def load_status(manuscript_dir: Path, verify_gate: bool = True) -> dict[str, Any]:
    path = status_path(manuscript_dir)
    if not path.is_file():
        raise ManuscriptError("manuscript_status.json is missing; start stage 4 first.")
    status = read_json(path)
    if not isinstance(status, dict) or status.get("status") not in VALID_STATES:
        raise ManuscriptError(f"Unknown stage-4 state: {status.get('status')!r}")
    for key in FALSE_FLAGS:
        if status.get(key) is not False:
            raise ManuscriptError(f"Protected execution flag changed: {key}")
    if verify_gate:
        verify_upstream_gate(status)
    return status


def write_status(manuscript_dir: Path, status: dict[str, Any]) -> None:
    status.update(false_flags())
    status["updated_at"] = utc_now()
    write_json(status_path(manuscript_dir), status)


def start(
    manuscript_dir: Path,
    planning_dir: Path,
    formal_dir: Path,
    analysis_dir: Path,
    model_manifest: Path,
) -> dict[str, Any]:
    if status_path(manuscript_dir).exists():
        raise ManuscriptError("Stage 4 is already initialized.")
    plan, stage1_records = verify_stage1(planning_dir)
    graph, formal_records = verify_formal(formal_dir, plan.get("project_id"))
    stage3_status, stage3_records, conclusions = collect_stage3_sources(analysis_dir, plan.get("project_id"))
    model_records, model_sources = verify_model_manifest(model_manifest, plan.get("project_id"))
    manuscript_dir.mkdir(parents=True, exist_ok=True)
    for name in (
        "source_records",
        "method_drafts",
        "result_discussion",
        "conclusions",
        "software_citations",
        "license_review",
        "open_source_migration",
        "user_edits",
        "source_snapshots",
    ):
        (manuscript_dir / name).mkdir(exist_ok=True)
    gate = {
        "project_id": plan.get("project_id"),
        "records": stage1_records + formal_records + stage3_records + model_records,
        "approved_stage3_conclusions": conclusions,
        "approved_model_and_experiment_sources": model_sources,
        "valid_task_ids": sorted(
            {str(item.get("id")) for item in plan.get("tasks", []) if isinstance(item, dict) and item.get("id")}
            | {str(item.get("task_id")) for item in graph.get("nodes", []) if isinstance(item, dict) and item.get("task_id")}
        ),
        "stage3_validated_evidence_node_ids": copy.deepcopy(stage3_status.get("validated_evidence_node_ids", [])),
        "captured_at": utc_now(),
    }
    snapshot_path = manuscript_dir / "source_snapshots" / "upstream_snapshot_v001.json"
    write_json(snapshot_path, gate)
    snapshot_record = file_record(snapshot_path, source_name="stage4_upstream_snapshot", source_kind="stage4")
    status: dict[str, Any] = {
        "project_id": plan.get("project_id"),
        "workflow_step": "stage4_manuscript_and_reproduction",
        "status": WAITING_FOR_MANUSCRIPT_INPUT,
        "upstream_gate": gate,
        "upstream_snapshot_record": snapshot_record,
        "source_inventory_records": [],
        "license_review_records": [],
        "candidate_records": [],
        "impact_records": [],
        "approval_records": [],
        "current_candidate_version": None,
        "blocking_items": [],
        "manuscript_content_approved": False,
        **false_flags(),
        "created_at": utc_now(),
    }
    write_status(manuscript_dir, status)
    write_json(change_log_path(manuscript_dir), [])
    ensure_review_html(manuscript_dir)
    append_log(manuscript_dir, {"event": "stage4_started", "state": WAITING_FOR_MANUSCRIPT_INPUT, "approved_conclusion_count": len(conclusions)})
    return {
        "status": WAITING_FOR_MANUSCRIPT_INPUT,
        "approved_conclusion_count": len(conclusions),
        "valid_task_ids": gate["valid_task_ids"],
        "stage3_validated_evidence_node_ids": gate["stage3_validated_evidence_node_ids"],
        **false_flags(),
    }


def upstream_snapshot(status: dict[str, Any]) -> dict[str, Any]:
    path = verify_file_record(status.get("upstream_snapshot_record"), "stage-4 upstream snapshot")
    value = read_json(path)
    if not isinstance(value, dict):
        raise ManuscriptError("The stage-4 upstream snapshot is invalid.")
    return value


def source_record_lookup(status: dict[str, Any]) -> dict[tuple[str, str], dict[str, Any]]:
    lookup: dict[tuple[str, str], dict[str, Any]] = {}
    for record in status.get("upstream_gate", {}).get("records", []):
        if isinstance(record, dict):
            lookup[(str(record.get("path", "")), str(record.get("sha256", "")))] = record
    return lookup


def normalize_actual_parameter(
    item: Any,
    field: str,
    file_refs: set[str],
) -> tuple[dict[str, Any], bool]:
    if not isinstance(item, dict):
        raise ManuscriptError(f"actual_parameters.{field} must be an object.")
    status = str(item.get("status", "")).strip()
    if status not in {"confirmed", "not_applicable", "unknown"}:
        raise ManuscriptError(f"actual_parameters.{field}.status is invalid.")
    value = item.get("value")
    rationale = str(item.get("rationale", "")).strip()
    refs = item.get("source_file_refs", [])
    if not isinstance(refs, list) or any(str(ref) not in file_refs for ref in refs):
        raise ManuscriptError(f"actual_parameters.{field} contains an unknown source_file_ref.")
    refs = sorted(set(str(ref) for ref in refs))
    if status == "confirmed" and (value is None or value == "" or not refs):
        raise ManuscriptError(f"Confirmed actual parameter {field} requires a value and source file.")
    if status == "not_applicable" and not rationale:
        raise ManuscriptError(f"Not-applicable actual parameter {field} requires a rationale.")
    if status == "unknown" and not rationale:
        raise ManuscriptError(f"Unknown actual parameter {field} requires a missing-information explanation.")
    return {"value": copy.deepcopy(value), "status": status, "rationale": rationale, "source_file_refs": refs}, status == "unknown"


def copy_inventory_file(
    source: Path,
    target_dir: Path,
    filename: str,
    **metadata: Any,
) -> dict[str, Any]:
    target = target_dir / safe_name(filename)
    if target.exists():
        raise ManuscriptError(f"Duplicate inventory target filename: {target.name}")
    shutil.copy2(source, target)
    return file_record(target, original_path=str(source), **metadata)


def render_source_inventory(inventory: dict[str, Any]) -> str:
    lines = [
        f"# 实际计算软件与来源清单 {inventory['inventory_version']}",
        "",
        "本清单记录真实执行来源；许可分类不改变实际软件名称。",
        "",
        "## 模型",
        "",
    ]
    for model in inventory["models"]:
        lines.extend(
            [
                f"- `{model['model_id']}` · {model['model_type']}：{model['description']}",
                f"  - 批准来源：{model['approved_record']['path']} ({model['approved_record']['sha256']})",
                f"  - 最终结构：{model['final_structure']['path']} ({model['final_structure']['sha256']})",
            ]
        )
    lines.extend(["", "## 实际任务", ""])
    for task in inventory["tasks"]:
        software = task["actual_software"]
        lines.extend(
            [
                f"### {task['task_id']} · {task['task_name']}",
                "",
                f"- 实际软件：{software['name']}",
                f"- 版本：{software['version_display']}",
                f"- 模块：{software['module']}",
                f"- 许可类别：`{software['license_category']}`",
                f"- 文件：{', '.join(item['file_ref'] for item in task['files'])}",
                f"- 计划—实际差异：{task['actual_vs_planned_differences'] or '无记录差异'}",
                "",
            ]
        )
    if inventory["blocking_actual_parameter_items"]:
        lines.extend(["## 阻断性实际参数缺失", ""])
        lines.extend(f"- {item}" for item in inventory["blocking_actual_parameter_items"])
    lines.extend(["", "未执行任何计算、后处理或开源复算。", ""])
    return "\n".join(lines)


def submit_source_inventory_value(
    manuscript_dir: Path,
    status: dict[str, Any],
    payload: dict[str, Any],
    source_path: Path | None,
) -> dict[str, Any]:
    if status.get("status") == MANUSCRIPT_CONTENT_APPROVED:
        raise ManuscriptError("Approved manuscript content is immutable.")
    if status.get("source_inventory_records"):
        raise ManuscriptError("The validated actual-source inventory is immutable; restart stage 4 for a source revision.")
    ensure_false_flags(payload)
    if str(payload.get("project_id")) != str(status.get("project_id")):
        raise ManuscriptError("Source inventory project ID does not match stage 4.")
    models = payload.get("models", [])
    tasks = payload.get("tasks", [])
    if not isinstance(models, list) or not models or not isinstance(tasks, list) or not tasks:
        raise ManuscriptError("Source inventory requires nonempty models and tasks.")
    snapshot = upstream_snapshot(status)
    valid_task_ids = set(str(item) for item in snapshot.get("valid_task_ids", []))
    approved_conclusions = snapshot.get("approved_stage3_conclusions", [])
    required_analysis_task_ids = {
        str(task_id)
        for conclusion in approved_conclusions
        if isinstance(conclusion, dict)
        for task_id in conclusion.get("task_ids", [])
    }
    approved_analysis_versions_by_task: dict[str, set[str]] = {}
    approved_dataset_ids_by_task: dict[str, set[str]] = {}
    for conclusion in approved_conclusions:
        if not isinstance(conclusion, dict):
            continue
        for task_id in conclusion.get("task_ids", []):
            task_key = str(task_id)
            if conclusion.get("analysis_version"):
                approved_analysis_versions_by_task.setdefault(task_key, set()).add(str(conclusion["analysis_version"]))
            approved_dataset_ids_by_task.setdefault(task_key, set()).update(str(item) for item in conclusion.get("dataset_ids", []))
    source_lookup = source_record_lookup(status)
    version = next_version(manuscript_dir / "source_records", "software_source_inventory_")
    target_dir = manuscript_dir / "source_records" / f"inventory_{version}"
    target_dir.mkdir(parents=True)
    normalized_models: list[dict[str, Any]] = []
    normalized_tasks: list[dict[str, Any]] = []
    blockers: list[str] = []
    try:
        seen_model_ids: set[str] = set()
        for index, item in enumerate(models):
            if not isinstance(item, dict):
                raise ManuscriptError(f"models[{index}] must be an object.")
            model_id = safe_identifier(item.get("model_id"), f"models[{index}].model_id")
            if model_id in seen_model_ids:
                raise ManuscriptError(f"Duplicate model ID: {model_id}")
            seen_model_ids.add(model_id)
            model_type = str(item.get("model_type", "")).strip()
            if model_type not in {"surface", "interface", "molecule", "bulk", "other"}:
                raise ManuscriptError(f"models[{index}].model_type is invalid.")
            approved = item.get("approved_record")
            if not isinstance(approved, dict) or (str(approved.get("path", "")), str(approved.get("sha256", ""))) not in source_lookup:
                raise ManuscriptError(f"models[{index}].approved_record is not in the frozen upstream gate.")
            approved_path = verify_file_record(approved, f"model {model_id} approved record")
            final_path = resolve_source_file(source_path, item.get("final_structure"))
            final_record = copy_inventory_file(final_path, target_dir, f"model_{model_id}_{final_path.name}", file_id=f"MODEL:{model_id}:STRUCTURE", role="final_structure")
            normalized_models.append(
                {
                    "model_id": model_id,
                    "model_type": model_type,
                    "approved_record": file_record(approved_path),
                    "final_structure": final_record,
                    "description": str(item.get("description", "")).strip(),
                }
            )
        seen_task_ids: set[str] = set()
        for index, item in enumerate(tasks):
            if not isinstance(item, dict):
                raise ManuscriptError(f"tasks[{index}] must be an object.")
            task_id = safe_identifier(item.get("task_id"), f"tasks[{index}].task_id")
            if task_id not in valid_task_ids or task_id in seen_task_ids:
                raise ManuscriptError(f"Unknown or duplicate source-inventory task ID: {task_id}")
            seen_task_ids.add(task_id)
            task_name = str(item.get("task_name", "")).strip()
            if not task_name:
                raise ManuscriptError(f"Task {task_id} requires task_name.")
            software = item.get("actual_software")
            if not isinstance(software, dict):
                raise ManuscriptError(f"Task {task_id} requires actual_software.")
            software_name = str(software.get("name", "")).strip()
            module_name = str(software.get("module", "")).strip()
            version_status = str(software.get("version_status", "")).strip()
            license_category = str(software.get("license_category", "")).strip()
            if not software_name or not module_name or version_status not in VERSION_STATUSES or license_category not in LICENSE_CATEGORIES:
                raise ManuscriptError(f"Task {task_id} has an incomplete actual-software record.")
            version_value = str(software.get("version", "")).strip()
            if version_status == "confirmed" and not version_value:
                raise ManuscriptError(f"Task {task_id} has confirmed version status but no version.")
            version_display = version_value if version_status == "confirmed" else MISSING_VERSION_STATEMENT
            license_source = str(software.get("license_verification_source", "")).strip()
            if not license_source:
                raise ManuscriptError(f"Task {task_id} requires a license verification source or 'unconfirmed'.")
            raw_files = item.get("files", [])
            if not isinstance(raw_files, list) or not raw_files:
                raise ManuscriptError(f"Task {task_id} requires actual files.")
            stored_files: list[dict[str, Any]] = []
            file_refs: set[str] = set()
            for file_index, file_item in enumerate(raw_files, start=1):
                if not isinstance(file_item, dict) or file_item.get("role") not in FILE_ROLES:
                    raise ManuscriptError(f"Task {task_id} file {file_index} has an invalid role.")
                file_ref = safe_identifier(file_item.get("file_ref"), f"task {task_id} file_ref")
                if file_ref in file_refs:
                    raise ManuscriptError(f"Task {task_id} has duplicate file_ref {file_ref}.")
                file_refs.add(file_ref)
                source = resolve_source_file(source_path, file_item.get("path"))
                stored_files.append(
                    copy_inventory_file(
                        source,
                        target_dir,
                        f"{task_id}_{file_ref}_{source.name}",
                        file_id=f"TASK:{task_id}:{file_ref}",
                        file_ref=file_ref,
                        role=file_item["role"],
                        description=str(file_item.get("description", "")).strip(),
                    )
                )
            roles = {str(record.get("role")) for record in stored_files}
            if "actual_input" not in roles or not roles.intersection({"main_output", "result_data", "postprocess_output"}):
                raise ManuscriptError(f"Task {task_id} requires an actual input and a real output/data file.")
            evidence = item.get("software_identification_evidence", [])
            if not isinstance(evidence, list):
                raise ManuscriptError(f"Task {task_id} software_identification_evidence must be a list.")
            evidence_types: set[str] = set()
            normalized_evidence: list[dict[str, str]] = []
            for evidence_index, evidence_item in enumerate(evidence):
                if not isinstance(evidence_item, dict) or evidence_item.get("type") not in IDENTIFICATION_TYPES:
                    raise ManuscriptError(f"Task {task_id} identification evidence {evidence_index + 1} is invalid.")
                ref = safe_identifier(evidence_item.get("source_file_ref"), f"task {task_id} identification source")
                observation = str(evidence_item.get("observation", "")).strip()
                if ref not in file_refs or not observation:
                    raise ManuscriptError(f"Task {task_id} identification evidence must cite an actual stored file and observation.")
                evidence_types.add(str(evidence_item["type"]))
                normalized_evidence.append({"type": evidence_item["type"], "source_file_ref": ref, "observation": observation})
            if len(evidence_types) < 2 or not evidence_types.intersection(STRONG_IDENTIFICATION_TYPES):
                raise ManuscriptError(f"Task {task_id} software identity needs two evidence types including output/version/user evidence.")
            parameters = item.get("actual_parameters")
            if not isinstance(parameters, dict) or set(parameters) != set(PARAMETER_FIELDS):
                raise ManuscriptError(f"Task {task_id} actual_parameters must contain every required parameter field exactly once.")
            normalized_parameters: dict[str, Any] = {}
            for field in PARAMETER_FIELDS:
                normalized, unknown = normalize_actual_parameter(parameters[field], field, file_refs)
                normalized_parameters[field] = normalized
                if unknown:
                    blockers.append(f"{task_id}.actual_parameters.{field} is unknown")
            if normalized_parameters["software"]["status"] == "confirmed" and str(normalized_parameters["software"]["value"]) != software_name:
                raise ManuscriptError(f"Task {task_id} software parameter differs from actual_software.name.")
            if version_status == "confirmed" and normalized_parameters["software_version"]["status"] == "confirmed" and str(normalized_parameters["software_version"]["value"]) != version_value:
                raise ManuscriptError(f"Task {task_id} software-version parameter differs from actual_software.version.")
            formulas = item.get("actual_formulas", [])
            if not isinstance(formulas, list):
                raise ManuscriptError(f"Task {task_id} actual_formulas must be a list.")
            normalized_formulas: list[dict[str, Any]] = []
            for formula_index, formula in enumerate(formulas):
                if not isinstance(formula, dict):
                    raise ManuscriptError(f"Task {task_id} formula {formula_index + 1} is invalid.")
                formula_id = safe_identifier(formula.get("formula_id"), f"task {task_id} formula ID")
                expression = str(formula.get("expression", "")).strip()
                terms = formula.get("term_definitions")
                conditions = str(formula.get("reference_conditions", "")).strip()
                analysis_versions = normalize_text_list(formula.get("stage3_analysis_versions", []), f"task {task_id} formula analyses", allow_empty=False)
                if not set(analysis_versions).issubset(approved_analysis_versions_by_task.get(task_id, set())):
                    raise ManuscriptError(f"Task {task_id} formula {formula_id} cites an unapproved stage-3 analysis version.")
                if not expression or not isinstance(terms, dict) or not terms or any(not str(key).strip() or not str(value).strip() for key, value in terms.items()) or not conditions:
                    raise ManuscriptError(f"Task {task_id} formula {formula_id} lacks terms or reference conditions.")
                normalized_formulas.append({"formula_id": formula_id, "expression": expression, "term_definitions": copy.deepcopy(terms), "reference_conditions": conditions, "stage3_analysis_versions": analysis_versions})
            postprocessing = item.get("postprocessing_software", [])
            if not isinstance(postprocessing, list):
                raise ManuscriptError(f"Task {task_id} postprocessing_software must be a list.")
            normalized_post: list[dict[str, Any]] = []
            for post_index, post in enumerate(postprocessing):
                if not isinstance(post, dict) or not str(post.get("name", "")).strip() or post.get("license_category") not in LICENSE_CATEGORIES or post.get("version_status") not in VERSION_STATUSES:
                    raise ManuscriptError(f"Task {task_id} post-processing software {post_index + 1} is invalid.")
                post_version = str(post.get("version", "")).strip()
                if post["version_status"] == "confirmed" and not post_version:
                    raise ManuscriptError(f"Task {task_id} post-processing software has no confirmed version.")
                post_evidence_raw = post.get("software_identification_evidence", [])
                if not isinstance(post_evidence_raw, list):
                    raise ManuscriptError(f"Task {task_id} post-processing identity evidence is invalid.")
                post_evidence: list[dict[str, str]] = []
                post_types: set[str] = set()
                for evidence_index, evidence_item in enumerate(post_evidence_raw):
                    if not isinstance(evidence_item, dict) or evidence_item.get("type") not in IDENTIFICATION_TYPES:
                        raise ManuscriptError(f"Task {task_id} post-processing identity evidence {evidence_index + 1} is invalid.")
                    ref = safe_identifier(evidence_item.get("source_file_ref"), f"task {task_id} post-processing identity source")
                    observation = str(evidence_item.get("observation", "")).strip()
                    if ref not in file_refs or not observation:
                        raise ManuscriptError(f"Task {task_id} post-processing identity evidence must cite a stored file.")
                    post_types.add(str(evidence_item["type"]))
                    post_evidence.append({"type": evidence_item["type"], "source_file_ref": ref, "observation": observation})
                if len(post_types) < 2 or not post_types.intersection(STRONG_IDENTIFICATION_TYPES):
                    raise ManuscriptError(f"Task {task_id} post-processing software identity needs two evidence types including output/version/user evidence.")
                normalized_post.append(
                    {
                        "name": str(post["name"]).strip(),
                        "version": post_version,
                        "version_status": post["version_status"],
                        "version_display": post_version if post["version_status"] == "confirmed" else MISSING_VERSION_STATEMENT,
                        "module": str(post.get("module", "")).strip(),
                        "license_category": post["license_category"],
                        "license_verification_source": str(post.get("license_verification_source", "")).strip() or "unconfirmed",
                        "software_identification_evidence": post_evidence,
                    }
                )
            analysis_versions = normalize_text_list(item.get("stage3_analysis_versions", []), f"task {task_id} stage3_analysis_versions", allow_empty=False)
            dataset_ids = normalize_text_list(item.get("stage3_dataset_ids", []), f"task {task_id} stage3_dataset_ids", allow_empty=False)
            if set(analysis_versions) != approved_analysis_versions_by_task.get(task_id, set()):
                raise ManuscriptError(f"Task {task_id} stage-3 analysis versions do not match approved conclusion provenance.")
            if set(dataset_ids) != approved_dataset_ids_by_task.get(task_id, set()):
                raise ManuscriptError(f"Task {task_id} stage-3 dataset IDs do not match approved conclusion provenance.")
            differences = item.get("actual_vs_planned_differences", [])
            if not isinstance(differences, list):
                raise ManuscriptError(f"Task {task_id} actual_vs_planned_differences must be a list.")
            normalized_differences: list[dict[str, Any]] = []
            for difference_index, difference in enumerate(differences):
                if not isinstance(difference, dict) or not str(difference.get("field", "")).strip() or "planned" not in difference or "actual" not in difference or not str(difference.get("effect", "")).strip():
                    raise ManuscriptError(f"Task {task_id} plan/actual difference {difference_index + 1} is incomplete.")
                difference_field = str(difference["field"]).strip()
                if difference_field in normalized_parameters and difference["actual"] != normalized_parameters[difference_field]["value"]:
                    raise ManuscriptError(f"Task {task_id} plan/actual difference for {difference_field} conflicts with the actual parameter source.")
                normalized_differences.append({"field": difference_field, "planned": copy.deepcopy(difference["planned"]), "actual": copy.deepcopy(difference["actual"]), "effect": str(difference["effect"]).strip()})
            normalized_tasks.append(
                {
                    "task_id": task_id,
                    "task_name": task_name,
                    "model_ids": normalize_text_list(item.get("model_ids", []), f"task {task_id} model_ids", allow_empty=False),
                    "actual_software": {
                        "name": software_name,
                        "version": version_value,
                        "version_status": version_status,
                        "version_display": version_display,
                        "module": module_name,
                        "license_category": license_category,
                        "license_verification_source": license_source,
                    },
                    "files": stored_files,
                    "software_identification_evidence": normalized_evidence,
                    "actual_parameters": normalized_parameters,
                    "actual_formulas": normalized_formulas,
                    "actual_vs_planned_differences": normalized_differences,
                    "postprocessing_software": normalized_post,
                    "stage3_analysis_versions": analysis_versions,
                    "stage3_dataset_ids": dataset_ids,
                }
            )
        if not required_analysis_task_ids.issubset(seen_task_ids):
            raise ManuscriptError("Source inventory does not cover every task used by approved stage-3 conclusions: " + ", ".join(sorted(required_analysis_task_ids - seen_task_ids)))
        model_ids = {item["model_id"] for item in normalized_models}
        for task in normalized_tasks:
            missing_models = set(task["model_ids"]) - model_ids
            if missing_models:
                raise ManuscriptError(f"Task {task['task_id']} refers to unknown models: {', '.join(sorted(missing_models))}")
        inventory = {
            "project_id": status.get("project_id"),
            "inventory_version": version,
            "upstream_snapshot_record": copy.deepcopy(status["upstream_snapshot_record"]),
            "models": normalized_models,
            "tasks": normalized_tasks,
            "blocking_actual_parameter_items": sorted(blockers),
            "missing_version_items": [f"{task['task_id']}: {MISSING_VERSION_STATEMENT}" for task in normalized_tasks if task["actual_software"]["version_status"] == "unconfirmed"],
            "generated_at": utc_now(),
            **false_flags(),
        }
        inventory_path = manuscript_dir / "source_records" / f"software_source_inventory_{version}.json"
        markdown_path = manuscript_dir / "source_records" / f"software_source_inventory_{version}.md"
        write_json(inventory_path, inventory)
        write_text(markdown_path, render_source_inventory(inventory))
    except Exception:
        shutil.rmtree(target_dir, ignore_errors=True)
        raise
    record = {"version": version, "json": file_record(inventory_path), "markdown": file_record(markdown_path), "file_manifest": [record for task in normalized_tasks for record in task["files"]] + [item["final_structure"] for item in normalized_models]}
    status.setdefault("source_inventory_records", []).append(record)
    status["current_source_inventory_record"] = record["json"]
    status["blocking_items"] = sorted(blockers)
    status["status"] = SOURCE_RECORDS_VALIDATED
    write_status(manuscript_dir, status)
    append_log(manuscript_dir, {"event": "actual_source_inventory_validated", "version": version, "task_ids": sorted(seen_task_ids), "blocking_items": blockers})
    return inventory


def submit_source_inventory(manuscript_dir: Path, source_path: Path) -> dict[str, Any]:
    status = load_status(manuscript_dir)
    payload = read_json(source_path)
    if not isinstance(payload, dict):
        raise ManuscriptError("Source inventory must be a JSON object.")
    return submit_source_inventory_value(manuscript_dir, status, payload, source_path)


def load_source_inventory(status: dict[str, Any]) -> dict[str, Any]:
    record = status.get("current_source_inventory_record")
    if not record:
        raise ManuscriptError("Actual source inventory has not been validated.")
    path = verify_file_record(record, "current actual source inventory")
    value = read_json(path)
    if not isinstance(value, dict):
        raise ManuscriptError("Current actual source inventory is invalid.")
    for task in value.get("tasks", []):
        for file_item in task.get("files", []):
            verify_file_record(file_item, f"source inventory task {task.get('task_id')} file")
    for model in value.get("models", []):
        verify_file_record(model.get("approved_record"), f"source inventory model {model.get('model_id')} approval")
        verify_file_record(model.get("final_structure"), f"source inventory model {model.get('model_id')} structure")
    return value


def software_inventory(inventory: dict[str, Any]) -> dict[str, dict[str, Any]]:
    output: dict[str, dict[str, Any]] = {}
    for task in inventory.get("tasks", []):
        actual = task["actual_software"]
        key = actual["name"]
        if key in output and output[key]["license_category"] != actual["license_category"]:
            raise ManuscriptError(f"Conflicting license categories in source inventory for {key}.")
        record = output.setdefault(
            key,
            {
                "software_name": key,
                "license_category": actual["license_category"],
                "license_verification_source": actual["license_verification_source"],
                "actual_task_ids": [],
                "roles": ["main_calculation"],
            },
        )
        record["actual_task_ids"].append(task["task_id"])
        for post in task.get("postprocessing_software", []):
            post_key = post["name"]
            post_record = output.setdefault(
                post_key,
                {
                    "software_name": post_key,
                    "license_category": post["license_category"],
                    "license_verification_source": post["license_verification_source"],
                    "actual_task_ids": [],
                    "roles": ["postprocessing"],
                },
            )
            if post_record["license_category"] != post["license_category"]:
                raise ManuscriptError(f"Conflicting license categories in source inventory for {post_key}.")
            post_record["actual_task_ids"].append(task["task_id"])
    for item in output.values():
        item["actual_task_ids"] = sorted(set(item["actual_task_ids"]))
        item["roles"] = sorted(set(item["roles"]))
    return output


def normalize_citation(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ManuscriptError(f"{label} must be an object.")
    title = str(value.get("title", "")).strip()
    authors = str(value.get("authors_or_organization", "")).strip()
    source_type = str(value.get("source_type", "")).strip()
    verification = str(value.get("verification_status", "")).strip()
    if not title or not authors or source_type not in {"official_software", "primary_theory", "primary_algorithm", "license", "other_primary"} or verification not in {"verified", "unconfirmed"}:
        raise ManuscriptError(f"{label} has incomplete citation provenance.")
    return {
        "title": title,
        "authors_or_organization": authors,
        "year": str(value.get("year", "")).strip(),
        "doi_or_url": str(value.get("doi_or_url", "")).strip(),
        "source_type": source_type,
        "verification_status": verification,
        "notes": str(value.get("notes", "")).strip(),
    }


def render_license_review(review: dict[str, Any]) -> tuple[str, str]:
    lines = [f"# 软件许可与文件共享检查 {review['review_version']}", ""]
    citation_lines = [f"# 软件与方法引用清单 {review['review_version']}", ""]
    for item in review["items"]:
        lines.extend(
            [
                f"## {item['software_name']}",
                "",
                f"- 实际任务：{', '.join(item['actual_task_ids'])}",
                f"- 许可类别：`{item['license_category']}`",
                f"- 分类来源：{item['classification_source']}",
                f"- 输入共享：`{item['input_sharing']}`",
                f"- 公开发布措施：{item['public_release_action']}",
                f"- 受限依赖：{item['restricted_dependencies'] or '无已知项'}",
                "",
            ]
        )
        citation_lines.extend([f"## {item['software_name']}", ""])
        for citation in item["recommended_software_citations"] + item["theory_algorithm_citations"]:
            citation_lines.append(f"- {citation['authors_or_organization']} ({citation['year'] or '年份待核'}). {citation['title']}. {citation['doi_or_url'] or '标识待核'} [`{citation['verification_status']}`]")
        if not item["recommended_software_citations"] and not item["theory_algorithm_citations"]:
            citation_lines.append("- 尚无已核实引用；正式投稿前需核对官方推荐引用和实际理论方法原始文献。")
        citation_lines.append("")
    if review["public_release_blockers"]:
        lines.extend(["## 公开发布阻断项", ""])
        lines.extend(f"- {item}" for item in review["public_release_blockers"])
    lines.extend(["", "许可分类只用于引用、共享和复现安排，不改写真实计算来源。", ""])
    return "\n".join(lines), "\n".join(citation_lines)


def submit_license_review_value(manuscript_dir: Path, status: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
    if status.get("status") == MANUSCRIPT_CONTENT_APPROVED:
        raise ManuscriptError("Approved manuscript content is immutable.")
    if status.get("license_review_records"):
        raise ManuscriptError("The license review is immutable; restart stage 4 for a source/license revision.")
    ensure_false_flags(payload)
    inventory = load_source_inventory(status)
    expected = software_inventory(inventory)
    items = payload.get("items", [])
    if not isinstance(items, list) or not items:
        raise ManuscriptError("License review requires one item per actual software.")
    normalized: list[dict[str, Any]] = []
    seen: set[str] = set()
    public_blockers: list[str] = []
    citation_pending: list[str] = []
    for index, item in enumerate(items):
        if not isinstance(item, dict):
            raise ManuscriptError(f"items[{index}] must be an object.")
        software_name = str(item.get("software_name", "")).strip()
        if software_name not in expected or software_name in seen:
            raise ManuscriptError(f"Unknown or duplicate license-review software: {software_name}")
        seen.add(software_name)
        source_license = expected[software_name]["license_category"]
        reviewed_license = str(item.get("license_category", "")).strip()
        if reviewed_license not in LICENSE_CATEGORIES:
            raise ManuscriptError(f"License category is invalid for {software_name}.")
        if source_license != "unconfirmed" and reviewed_license != source_license:
            raise ManuscriptError(f"License review cannot contradict the frozen source category for {software_name}.")
        task_ids = sorted(set(normalize_text_list(item.get("actual_task_ids", []), f"{software_name}.actual_task_ids", allow_empty=False)))
        if task_ids != expected[software_name]["actual_task_ids"]:
            raise ManuscriptError(f"License-review task IDs differ from actual provenance for {software_name}.")
        classification_source = str(item.get("classification_source", "")).strip()
        input_sharing = str(item.get("input_sharing", "")).strip()
        release_action = str(item.get("public_release_action", "")).strip()
        if not classification_source or input_sharing not in {"allowed", "restricted", "unconfirmed"} or not release_action:
            raise ManuscriptError(f"License/share review is incomplete for {software_name}.")
        software_citations_raw = item.get("recommended_software_citations", [])
        theory_citations_raw = item.get("theory_algorithm_citations", [])
        if not isinstance(software_citations_raw, list) or not isinstance(theory_citations_raw, list):
            raise ManuscriptError(f"Citation lists are invalid for {software_name}.")
        software_citations = [normalize_citation(value, f"{software_name}.software citation") for value in software_citations_raw]
        theory_citations = [normalize_citation(value, f"{software_name}.theory citation") for value in theory_citations_raw]
        if not software_citations:
            citation_pending.append(f"{software_name}: official recommended citation not yet verified")
        if any(value["verification_status"] == "unconfirmed" for value in software_citations + theory_citations):
            citation_pending.append(f"{software_name}: one or more citations remain unconfirmed")
        restricted_raw = item.get("restricted_dependencies", [])
        if not isinstance(restricted_raw, list):
            raise ManuscriptError(f"restricted_dependencies is invalid for {software_name}.")
        restricted: list[dict[str, str]] = []
        for dep_index, dependency in enumerate(restricted_raw):
            if not isinstance(dependency, dict):
                raise ManuscriptError(f"{software_name} restricted dependency {dep_index + 1} is invalid.")
            name = str(dependency.get("name", "")).strip()
            provenance = str(dependency.get("provenance", "")).strip()
            acquisition = str(dependency.get("authorized_acquisition", "")).strip()
            sharing = str(dependency.get("sharing_status", "")).strip()
            if not name or not provenance or not acquisition or sharing not in {"allowed", "restricted", "unconfirmed"}:
                raise ManuscriptError(f"{software_name} restricted dependency {dep_index + 1} lacks provenance/acquisition handling.")
            if any(key in dependency for key in ("file_path", "file_content", "base64")):
                raise ManuscriptError("Restricted dependency files cannot be packaged in stage 4.")
            restricted.append({"name": name, "provenance": provenance, "authorized_acquisition": acquisition, "sharing_status": sharing})
            if sharing != "allowed":
                public_blockers.append(f"{software_name}/{name}: restricted dependency must not be packaged")
        quotes_raw = item.get("manual_or_web_quotes", [])
        if not isinstance(quotes_raw, list):
            raise ManuscriptError(f"manual_or_web_quotes is invalid for {software_name}.")
        quotes: list[dict[str, str]] = []
        for quote_index, quote in enumerate(quotes_raw):
            if not isinstance(quote, dict) or not str(quote.get("source", "")).strip() or not str(quote.get("excerpt", "")).strip():
                raise ManuscriptError(f"{software_name} quote {quote_index + 1} is invalid.")
            excerpt = str(quote["excerpt"]).strip()
            if word_count(excerpt) > 25:
                raise ManuscriptError(f"{software_name} quote {quote_index + 1} exceeds 25 words.")
            quotes.append({"source": str(quote["source"]).strip(), "excerpt": excerpt})
        if item.get("review_complete") is not True:
            raise ManuscriptError(f"License review for {software_name} must be explicitly complete.")
        if input_sharing != "allowed":
            public_blockers.append(f"{software_name}: input sharing is {input_sharing}")
        if reviewed_license == "unconfirmed":
            public_blockers.append(f"{software_name}: license category remains unconfirmed")
        normalized.append(
            {
                "software_name": software_name,
                "actual_task_ids": task_ids,
                "roles": expected[software_name]["roles"],
                "license_category": reviewed_license,
                "classification_source": classification_source,
                "recommended_software_citations": software_citations,
                "theory_algorithm_citations": theory_citations,
                "input_sharing": input_sharing,
                "restricted_dependencies": restricted,
                "public_release_action": release_action,
                "manual_or_web_quotes": quotes,
                "review_complete": True,
            }
        )
    if seen != set(expected):
        raise ManuscriptError("License review does not cover every actual/main post-processing software.")
    version = next_version(manuscript_dir / "license_review", "license_review_")
    review = {
        "project_id": status.get("project_id"),
        "review_version": version,
        "source_inventory_record": copy.deepcopy(status["current_source_inventory_record"]),
        "items": normalized,
        "public_release_blockers": sorted(set(public_blockers)),
        "citation_pending_items": sorted(set(citation_pending)),
        "reviewed_at": utc_now(),
        **false_flags(),
    }
    review_path = manuscript_dir / "license_review" / f"license_review_{version}.json"
    review_md_path = manuscript_dir / "license_review" / f"license_review_{version}.md"
    citation_path = manuscript_dir / "software_citations" / f"software_citation_list_{version}.md"
    review_text, citation_text = render_license_review(review)
    write_json(review_path, review)
    write_text(review_md_path, review_text)
    write_text(citation_path, citation_text)
    record = {"version": version, "json": file_record(review_path), "markdown": file_record(review_md_path), "citation_markdown": file_record(citation_path)}
    status.setdefault("license_review_records", []).append(record)
    status["current_license_review_record"] = record["json"]
    status["current_software_citation_record"] = record["citation_markdown"]
    status["status"] = SOFTWARE_LICENSE_REVIEWED
    status["public_release_blockers"] = review["public_release_blockers"]
    write_status(manuscript_dir, status)
    append_log(manuscript_dir, {"event": "software_license_and_sharing_reviewed", "version": version, "software": sorted(seen), "public_release_blockers": review["public_release_blockers"]})
    return review


def submit_license_review(manuscript_dir: Path, source_path: Path) -> dict[str, Any]:
    status = load_status(manuscript_dir)
    payload = read_json(source_path)
    if not isinstance(payload, dict):
        raise ManuscriptError("License review must be a JSON object.")
    return submit_license_review_value(manuscript_dir, status, payload)


def load_license_review(status: dict[str, Any]) -> dict[str, Any]:
    record = status.get("current_license_review_record")
    if not record:
        raise ManuscriptError("Software license/citation review is missing.")
    path = verify_file_record(record, "current license review")
    value = read_json(path)
    if not isinstance(value, dict):
        raise ManuscriptError("Current license review is invalid.")
    return value


def source_conclusion_map(status: dict[str, Any]) -> dict[str, dict[str, Any]]:
    snapshot = upstream_snapshot(status)
    return {
        str(item.get("conclusion_id")): item
        for item in snapshot.get("approved_stage3_conclusions", [])
        if isinstance(item, dict) and item.get("conclusion_id")
    }


def inventory_task_map(inventory: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {str(item["task_id"]): item for item in inventory.get("tasks", [])}


def validate_document_profile(value: Any, nonopen_required: bool) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ManuscriptError("document_profile must be an object.")
    document_type = str(value.get("document_type", "")).strip()
    target_style = str(value.get("target_style", "")).strip()
    language = str(value.get("language", "")).strip()
    detail = str(value.get("method_detail", "")).strip()
    paragraph_order = normalize_text_list(value.get("paragraph_order", []), "document_profile.paragraph_order", allow_empty=False)
    terminology = value.get("terminology", {})
    retain = value.get("retain_open_source_note")
    if document_type not in DOCUMENT_TYPES or not target_style or language not in LANGUAGES or detail not in METHOD_DETAILS:
        raise ManuscriptError("Document type, target style, language, or method detail is invalid.")
    if not isinstance(terminology, dict) or any(not str(key).strip() or not str(item).strip() for key, item in terminology.items()):
        raise ManuscriptError("document_profile.terminology must map nonempty terms.")
    if not isinstance(retain, bool) or (nonopen_required and retain is not True):
        raise ManuscriptError("A separate open-source reproduction note is mandatory for non-open actual software.")
    return {
        "document_type": document_type,
        "target_style": target_style,
        "language": language,
        "method_detail": detail,
        "paragraph_order": paragraph_order,
        "terminology": copy.deepcopy(terminology),
        "retain_open_source_note": retain,
    }


def validate_method_assertions(value: Any, inventory: dict[str, Any]) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        raise ManuscriptError("method_factual_assertions must be a list.")
    tasks = inventory_task_map(inventory)
    models = {str(item["model_id"]) for item in inventory.get("models", [])}
    output: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, item in enumerate(value):
        if not isinstance(item, dict):
            raise ManuscriptError(f"method_factual_assertions[{index}] must be an object.")
        task_id = safe_identifier(item.get("task_id"), f"method assertion {index + 1} task_id")
        if task_id not in tasks or task_id in seen:
            raise ManuscriptError(f"Unknown or duplicate method assertion task: {task_id}")
        seen.add(task_id)
        source_task = tasks[task_id]
        actual = source_task["actual_software"]
        software_name = str(item.get("software_name", "")).strip()
        software_version = str(item.get("software_version", "")).strip()
        module_name = str(item.get("module", "")).strip()
        if software_name != actual["name"] or software_version != actual["version_display"] or module_name != actual["module"]:
            raise ManuscriptError(f"Method assertion for {task_id} conflicts with actual software/version/module provenance.")
        model_ids = sorted(set(normalize_text_list(item.get("model_ids", []), f"method assertion {task_id} model_ids", allow_empty=False)))
        if set(model_ids) - models or set(model_ids) != set(source_task.get("model_ids", [])):
            raise ManuscriptError(f"Method assertion for {task_id} changes the actual model linkage.")
        parameter_fields = sorted(set(normalize_text_list(item.get("parameter_fields", []), f"method assertion {task_id} parameter_fields", allow_empty=False)))
        required_fields = sorted(field for field, record in source_task["actual_parameters"].items() if record["status"] != "not_applicable")
        if parameter_fields != required_fields:
            raise ManuscriptError(f"Method assertion for {task_id} must cover every applicable/unknown result-relevant parameter.")
        snapshot = item.get("parameter_snapshot")
        expected_snapshot = {field: copy.deepcopy(source_task["actual_parameters"][field]) for field in parameter_fields}
        if snapshot != expected_snapshot:
            raise ManuscriptError(f"Method assertion for {task_id} changes actual parameters.")
        file_refs = sorted(set(normalize_text_list(item.get("file_refs", []), f"method assertion {task_id} file_refs", allow_empty=False)))
        valid_refs = {str(file_item["file_ref"]) for file_item in source_task["files"]}
        if set(file_refs) - valid_refs:
            raise ManuscriptError(f"Method assertion for {task_id} cites an unknown actual file.")
        formula_ids = sorted(set(normalize_text_list(item.get("formula_ids", []), f"method assertion {task_id} formula_ids")))
        valid_formula_ids = {str(formula["formula_id"]) for formula in source_task.get("actual_formulas", [])}
        if set(formula_ids) - valid_formula_ids:
            raise ManuscriptError(f"Method assertion for {task_id} adds a formula not recorded as actually used.")
        output.append(
            {
                "task_id": task_id,
                "software_name": software_name,
                "software_version": software_version,
                "module": module_name,
                "model_ids": model_ids,
                "parameter_fields": parameter_fields,
                "parameter_snapshot": expected_snapshot,
                "file_refs": file_refs,
                "formula_ids": formula_ids,
            }
        )
    if seen != set(tasks):
        raise ManuscriptError("Method factual assertions must cover every actual source-inventory task.")
    return sorted(output, key=lambda item: item["task_id"])


def derived_source_strength(source_items: list[dict[str, Any]]) -> str:
    strengths = {str(item["strength"]) for item in source_items}
    if "CONTRADICTED" in strengths:
        if len(strengths) != 1:
            return "INCONCLUSIVE"
        return "CONTRADICTED"
    return min(strengths, key=lambda item: STRENGTH_ORDER[item])


def phrase_present(text: str, phrases: tuple[str, ...]) -> bool:
    lower = text.lower()
    return any(phrase.lower() in lower for phrase in phrases)


def validate_claim_wording(text: str, strength: str, label: str) -> None:
    if phrase_present(text, HIGH_CERTAINTY_PHRASES):
        raise ManuscriptError(f"{label} uses a prohibited certainty/proof phrase.")
    if strength == "PARTIALLY_SUPPORTED" and not phrase_present(text, CAUTIOUS_PHRASES):
        raise ManuscriptError(f"{label} must use cautious partial-support wording.")
    if strength == "INCONCLUSIVE" and not phrase_present(text, INCONCLUSIVE_PHRASES):
        raise ManuscriptError(f"{label} must state that evidence is insufficient or uncertain.")
    if strength == "CONTRADICTED" and not phrase_present(text, CONTRADICTED_PHRASES):
        raise ManuscriptError(f"{label} must explicitly state inconsistency with the hypothesis.")


def validate_conclusion_claims(value: Any, status: dict[str, Any]) -> list[dict[str, Any]]:
    if not isinstance(value, list) or not value:
        raise ManuscriptError("conclusion_claims must be a nonempty list.")
    source_map = source_conclusion_map(status)
    output: list[dict[str, Any]] = []
    covered: set[str] = set()
    seen_claims: set[str] = set()
    overall_count = 0
    levels_seen: set[str] = set()
    for index, item in enumerate(value):
        if not isinstance(item, dict):
            raise ManuscriptError(f"conclusion_claims[{index}] must be an object.")
        claim_id = safe_identifier(item.get("claim_id"), f"conclusion claim {index + 1} ID")
        if claim_id in seen_claims:
            raise ManuscriptError(f"Duplicate conclusion claim ID: {claim_id}")
        seen_claims.add(claim_id)
        level = str(item.get("level", "")).strip()
        if level not in CONCLUSION_LEVELS:
            raise ManuscriptError(f"Conclusion claim {claim_id} has an invalid level.")
        if level == "overall":
            overall_count += 1
        levels_seen.add(level)
        source_ids = sorted(set(normalize_text_list(item.get("source_conclusion_ids", []), f"claim {claim_id} source conclusions", allow_empty=False)))
        if any(source_id not in source_map for source_id in source_ids):
            raise ManuscriptError(f"Conclusion claim {claim_id} refers to an unapproved stage-3 conclusion.")
        source_items = [source_map[source_id] for source_id in source_ids]
        source_strength = derived_source_strength(source_items)
        draft_strength = str(item.get("draft_strength", "")).strip()
        if str(item.get("source_strength", "")).strip() != source_strength or draft_strength not in STRENGTHS:
            raise ManuscriptError(f"Conclusion claim {claim_id} has an invalid source/draft strength.")
        if source_strength == "CONTRADICTED":
            if draft_strength != "CONTRADICTED":
                raise ManuscriptError(f"Contradicted conclusion {claim_id} cannot be rewritten as support.")
        elif draft_strength == "CONTRADICTED" or STRENGTH_ORDER[draft_strength] > STRENGTH_ORDER[source_strength]:
            raise ManuscriptError(f"Conclusion claim {claim_id} exceeds the approved stage-3 strength ceiling.")
        evidence_ids = sorted({str(evidence_id) for source in source_items for evidence_id in source.get("evidence_item_ids", [])})
        evidence_node_ids = sorted({str(node_id) for source in source_items for node_id in source.get("evidence_node_ids", [])})
        roles = sorted({str(role) for source in source_items for role in source.get("evidence_roles", []) if str(role)})
        if sorted(set(normalize_text_list(item.get("source_evidence_item_ids", []), f"claim {claim_id} evidence IDs"))) != evidence_ids:
            raise ManuscriptError(f"Conclusion claim {claim_id} changes its approved evidence-item set.")
        if sorted(set(normalize_text_list(item.get("evidence_roles", []), f"claim {claim_id} evidence roles", allow_empty=False))) != roles:
            raise ManuscriptError(f"Conclusion claim {claim_id} changes its approved evidence roles.")
        if sorted(set(normalize_text_list(item.get("source_evidence_node_ids", []), f"claim {claim_id} evidence node IDs", allow_empty=False))) != evidence_node_ids:
            raise ManuscriptError(f"Conclusion claim {claim_id} changes its approved evidence-node linkage.")
        source_limits = sorted({str(limit) for source in source_items for limit in source.get("limitations", []) + source.get("conclusion_boundary", []) if str(limit).strip()})
        boundaries = sorted(set(normalize_text_list(item.get("boundary", []), f"claim {claim_id} boundary", allow_empty=False)))
        if not set(source_limits).issubset(boundaries):
            raise ManuscriptError(f"Conclusion claim {claim_id} removes an approved limitation/boundary.")
        text = str(item.get("text", "")).strip()
        direct_data = str(item.get("direct_data_basis", "")).strip()
        physical = str(item.get("physical_meaning", "")).strip()
        relation = str(item.get("cross_evidence_relation", "")).strip()
        experiment_relation = str(item.get("experimental_relation", "")).strip()
        experiment_text = str(item.get("experimental_correspondence", "")).strip()
        if not text or not direct_data or not physical or not relation or experiment_relation not in EXPERIMENT_RELATIONS:
            raise ManuscriptError(f"Conclusion claim {claim_id} lacks data/meaning/relation/boundary content.")
        if experiment_relation != "none" and not experiment_text:
            raise ManuscriptError(f"Conclusion claim {claim_id} requires explicit experiment correspondence text.")
        if experiment_relation == "none" and not experiment_text:
            experiment_text = "当前批准证据未建立实验对应。"
        if level == "mechanism" and len(roles) < 2 and draft_strength not in {"PARTIALLY_SUPPORTED", "INCONCLUSIVE"}:
            raise ManuscriptError(f"Mechanism claim {claim_id} needs two independent evidence roles or cautious strength.")
        validate_claim_wording(text, draft_strength, f"Conclusion claim {claim_id}")
        covered.update(source_ids)
        output.append(
            {
                "claim_id": claim_id,
                "level": level,
                "source_conclusion_ids": source_ids,
                "source_evidence_item_ids": evidence_ids,
                "source_evidence_node_ids": evidence_node_ids,
                "evidence_roles": roles,
                "direct_data_basis": direct_data,
                "physical_meaning": physical,
                "cross_evidence_relation": relation,
                "experimental_relation": experiment_relation,
                "experimental_correspondence": experiment_text,
                "boundary": boundaries,
                "source_strength": source_strength,
                "draft_strength": draft_strength,
                "text": text,
            }
        )
    if covered != set(source_map):
        raise ManuscriptError("Conclusion claims must cover every approved stage-3 conclusion.")
    if overall_count != 1:
        raise ManuscriptError("Exactly one overall conclusion claim is required.")
    if levels_seen != CONCLUSION_LEVELS:
        raise ManuscriptError("Conclusion claims must separately cover data, property, mechanism, and overall levels.")
    return output


def review_license_map(review: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {str(item["software_name"]): item for item in review.get("items", [])}


def validate_open_source_mappings(
    value: Any,
    inventory: dict[str, Any],
    license_review: dict[str, Any],
) -> tuple[list[dict[str, Any]], set[str]]:
    if not isinstance(value, list):
        raise ManuscriptError("open_source_mappings must be a list.")
    tasks = inventory_task_map(inventory)
    licenses = review_license_map(license_review)
    required = {
        task_id
        for task_id, task in tasks.items()
        if licenses[task["actual_software"]["name"]]["license_category"] in NONOPEN_LICENSES
    }
    output: list[dict[str, Any]] = []
    seen: set[str] = set()
    alternatives: set[str] = set()
    for index, item in enumerate(value):
        if not isinstance(item, dict):
            raise ManuscriptError(f"open_source_mappings[{index}] must be an object.")
        task_id = safe_identifier(item.get("actual_task_id"), f"open-source mapping {index + 1} task ID")
        if task_id not in tasks or task_id in seen:
            raise ManuscriptError(f"Unknown or duplicate open-source mapping task: {task_id}")
        seen.add(task_id)
        task = tasks[task_id]
        actual_name = str(item.get("actual_software", "")).strip()
        if actual_name != task["actual_software"]["name"]:
            raise ManuscriptError(f"Open-source mapping for {task_id} changes actual software provenance.")
        alternatives_raw = item.get("proposed_alternatives", [])
        if not isinstance(alternatives_raw, list) or not alternatives_raw:
            raise ManuscriptError(f"Open-source mapping for {task_id} requires task-matched alternatives.")
        normalized_alternatives: list[dict[str, str]] = []
        for alt_index, alternative in enumerate(alternatives_raw):
            if not isinstance(alternative, dict):
                raise ManuscriptError(f"Mapping {task_id} alternative {alt_index + 1} is invalid.")
            name = str(alternative.get("name", "")).strip()
            capability = str(alternative.get("capability_status", "")).strip()
            basis = str(alternative.get("capability_basis", "")).strip()
            if not name or name == actual_name or capability not in CAPABILITY_STATUSES or not basis:
                raise ManuscriptError(f"Mapping {task_id} alternative {alt_index + 1} lacks a capability check.")
            alternatives.add(name)
            normalized_alternatives.append({"name": name, "capability_status": capability, "capability_basis": basis})
        mappings_raw = item.get("parameter_mappings", [])
        if not isinstance(mappings_raw, list) or not mappings_raw:
            raise ManuscriptError(f"Open-source mapping for {task_id} requires parameter mappings.")
        parameter_mappings: list[dict[str, Any]] = []
        for mapping_index, mapping in enumerate(mappings_raw):
            if not isinstance(mapping, dict):
                raise ManuscriptError(f"Mapping {task_id} parameter {mapping_index + 1} is invalid.")
            field = str(mapping.get("actual_parameter", "")).strip()
            equivalence = str(mapping.get("equivalence", "")).strip()
            rationale = str(mapping.get("rationale", "")).strip()
            proposed = mapping.get("proposed_setting")
            if field not in PARAMETER_FIELDS or equivalence not in EQUIVALENCE_CLASSES or not rationale:
                raise ManuscriptError(f"Mapping {task_id} parameter {mapping_index + 1} is incomplete.")
            actual_value = task["actual_parameters"][field]["value"]
            if mapping.get("actual_value") != actual_value:
                raise ManuscriptError(f"Mapping {task_id} changes the actual value of {field}.")
            parameter_mappings.append({"actual_parameter": field, "actual_value": copy.deepcopy(actual_value), "proposed_setting": copy.deepcopy(proposed), "equivalence": equivalence, "rationale": rationale})
        limitations = normalize_text_list(item.get("limitations", []), f"mapping {task_id} limitations", allow_empty=False)
        references = normalize_text_list(item.get("references", []), f"mapping {task_id} references")
        template = str(item.get("suggested_input_template", "")).strip()
        if not template:
            raise ManuscriptError(f"Open-source mapping for {task_id} requires a clearly suggested, unexecuted template.")
        if item.get("open_source_recalculation_performed") is not False or item.get("existing_results_attributed_to_alternative") is not False:
            raise ManuscriptError("Open-source mapping execution/provenance flags must remain false.")
        output.append(
            {
                "actual_task_id": task_id,
                "actual_software": actual_name,
                "proposed_alternatives": normalized_alternatives,
                "parameter_mappings": parameter_mappings,
                "non_equivalent_items": normalize_text_list(item.get("non_equivalent_items", []), f"mapping {task_id} non-equivalent items", allow_empty=False),
                "suggested_input_template": template,
                "references": references,
                "limitations": limitations,
                "open_source_recalculation_performed": False,
                "existing_results_attributed_to_alternative": False,
            }
        )
    if not required.issubset(seen):
        raise ManuscriptError("Every non-open actual task requires a separate open-source reproduction mapping: " + ", ".join(sorted(required - seen)))
    return sorted(output, key=lambda item: item["actual_task_id"]), alternatives


def validate_actual_mentions(value: Any, inventory: dict[str, Any]) -> list[dict[str, str]]:
    if not isinstance(value, list):
        raise ManuscriptError("actual_method_software_mentions must be a list.")
    tasks = inventory_task_map(inventory)
    output: list[dict[str, str]] = []
    seen: set[str] = set()
    for index, item in enumerate(value):
        if not isinstance(item, dict):
            raise ManuscriptError(f"actual_method_software_mentions[{index}] must be an object.")
        task_id = safe_identifier(item.get("task_id"), f"actual method mention {index + 1} task ID")
        software_name = str(item.get("software_name", "")).strip()
        if task_id not in tasks or task_id in seen or software_name != tasks[task_id]["actual_software"]["name"]:
            raise ManuscriptError("Actual-method software mentions must exactly match source provenance.")
        seen.add(task_id)
        output.append({"task_id": task_id, "software_name": software_name})
    if seen != set(tasks):
        raise ManuscriptError("Actual-method software mentions must cover every actual task.")
    return sorted(output, key=lambda item: item["task_id"])


def validate_quotes(value: Any) -> list[dict[str, str]]:
    if not isinstance(value, list):
        raise ManuscriptError("manual_source_quotes must be a list.")
    output: list[dict[str, str]] = []
    for index, item in enumerate(value):
        if not isinstance(item, dict) or not str(item.get("source", "")).strip() or not str(item.get("excerpt", "")).strip():
            raise ManuscriptError(f"manual_source_quotes[{index}] is invalid.")
        excerpt = str(item["excerpt"]).strip()
        if word_count(excerpt) > 25:
            raise ManuscriptError(f"manual_source_quotes[{index}] exceeds 25 words.")
        output.append({"source": str(item["source"]).strip(), "excerpt": excerpt})
    return output


def normalize_evidence_node_paragraphs(value: Any, claims: list[dict[str, Any]], status: dict[str, Any]) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        raise ManuscriptError("evidence_node_conclusions must be a list.")
    valid_nodes = set(str(item) for item in upstream_snapshot(status).get("stage3_validated_evidence_node_ids", []))
    claim_map = {str(item["claim_id"]): item for item in claims}
    output: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, item in enumerate(value):
        if not isinstance(item, dict):
            raise ManuscriptError(f"evidence_node_conclusions[{index}] must be an object.")
        node_id = safe_identifier(item.get("evidence_node_id"), f"evidence-node paragraph {index + 1} ID")
        if node_id not in valid_nodes or node_id in seen:
            raise ManuscriptError(f"Unknown or duplicate evidence-node paragraph: {node_id}")
        seen.add(node_id)
        claim_ids = sorted(set(normalize_text_list(item.get("claim_ids", []), f"evidence node {node_id} claim IDs", allow_empty=False)))
        if any(claim_id not in claim_map or node_id not in claim_map[claim_id]["source_evidence_node_ids"] for claim_id in claim_ids):
            raise ManuscriptError(f"Evidence-node paragraph {node_id} contains an unrelated claim.")
        text = str(item.get("text", "")).strip()
        if not text or any(claim_map[claim_id]["text"] not in text for claim_id in claim_ids):
            raise ManuscriptError(f"Evidence-node paragraph {node_id} must preserve each structured claim text.")
        if phrase_present(text, HIGH_CERTAINTY_PHRASES):
            raise ManuscriptError(f"Evidence-node paragraph {node_id} uses prohibited proof wording.")
        output.append({"evidence_node_id": node_id, "claim_ids": claim_ids, "text": text})
    if seen != valid_nodes:
        raise ManuscriptError("Evidence-node conclusions must cover every stage-3 validated evidence node.")
    return sorted(output, key=lambda item: item["evidence_node_id"])


def normalize_experiment_mappings(value: Any, claims: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        raise ManuscriptError("theory_experiment_correspondence must be a list.")
    claim_map = {str(item["claim_id"]): item for item in claims}
    output: list[dict[str, Any]] = []
    for index, item in enumerate(value):
        if not isinstance(item, dict):
            raise ManuscriptError(f"theory_experiment_correspondence[{index}] must be an object.")
        mapping_id = safe_identifier(item.get("mapping_id"), f"experiment mapping {index + 1} ID")
        claim_ids = sorted(set(normalize_text_list(item.get("claim_ids", []), f"experiment mapping {mapping_id} claim IDs", allow_empty=False)))
        relation = str(item.get("relation", "")).strip()
        text = str(item.get("text", "")).strip()
        boundary = str(item.get("boundary", "")).strip()
        if any(claim_id not in claim_map for claim_id in claim_ids) or relation not in EXPERIMENT_RELATIONS or not text or not boundary:
            raise ManuscriptError(f"Theory–experiment mapping {mapping_id} is incomplete.")
        for claim_id in claim_ids:
            source_relation = claim_map[claim_id]["experimental_relation"]
            if source_relation == "none" and relation != "none":
                raise ManuscriptError(f"Theory–experiment mapping {mapping_id} invents an unapproved relation.")
            if source_relation == "interpretive" and relation == "direct":
                raise ManuscriptError(f"Theory–experiment mapping {mapping_id} upgrades an interpretive link to direct.")
        if phrase_present(text, HIGH_CERTAINTY_PHRASES):
            raise ManuscriptError(f"Theory–experiment mapping {mapping_id} uses prohibited proof wording.")
        output.append({"mapping_id": mapping_id, "claim_ids": claim_ids, "relation": relation, "text": text, "boundary": boundary})
    return output


def recursive_differences(before: Any, after: Any, path: str = "") -> list[dict[str, Any]]:
    changes: list[dict[str, Any]] = []
    if type(before) is not type(after):
        return [{"path": path or "$", "before": before, "after": after}]
    if isinstance(before, dict):
        for key in sorted(set(before) | set(after)):
            child = f"{path}.{key}" if path else str(key)
            if key not in before:
                changes.append({"path": child, "before": None, "after": after[key]})
            elif key not in after:
                changes.append({"path": child, "before": before[key], "after": None})
            else:
                changes.extend(recursive_differences(before[key], after[key], child))
    elif isinstance(before, list):
        if before != after:
            changes.append({"path": path or "$", "before": before, "after": after})
    elif before != after:
        changes.append({"path": path or "$", "before": before, "after": after})
    return changes


def impact_for_path(path: str) -> tuple[str, str, str]:
    lower = path.lower()
    if any(token in lower for token in ("source_inventory_record", "license_review_record", "method_factual_assertions", "actual_method_software_mentions", "source_conclusion_ids", "source_evidence_item_ids", "source_evidence_node_ids", "source_strength")):
        return "CRITICAL", "May change actual provenance or approved evidence ownership.", "Reject any conflict and rebuild only from a newly authorized upstream source."
    if any(token in lower for token in ("draft_strength", "boundary", "conclusion_claims", "experimental_relation", "overall_conclusion", "evidence_node_conclusions")):
        return "HIGH", "May change conclusion strength, mechanism scope, or required limitations.", "Revalidate against every cited stage-3 conclusion."
    if any(token in lower for token in ("method_full", "method_concise", "result_discussion", "theory_experiment", "open_source", "software_citation", "license_review", "terminology")):
        return "MEDIUM", "Changes scientific prose, reproduction mapping, citations, or sharing instructions.", "Recheck factual separation and venue/release requirements."
    return "LOW", "Changes style, ordering, or non-scientific presentation.", "Review readability and target style."


def analyze_impact(before: dict[str, Any] | None, after: dict[str, Any], reason: str) -> dict[str, Any]:
    if before is None:
        return {"reason": reason or "initial manuscript generation", "overall_impact": "LOW", "changes": [], "summary": "Initial evidence-bound manuscript version."}
    changes = recursive_differences(before, after)
    ranking = {"LOW": 0, "MEDIUM": 1, "HIGH": 2, "CRITICAL": 3}
    overall = "LOW"
    normalized: list[dict[str, Any]] = []
    for change in changes:
        level, effect, action = impact_for_path(change["path"])
        if ranking[level] > ranking[overall]:
            overall = level
        normalized.append({**change, "impact": level, "scientific_effect": effect, "required_action": action})
    return {"reason": reason, "overall_impact": overall, "changes": normalized, "summary": f"{len(changes)} changed path(s); highest impact {overall}."}


def render_method(candidate: dict[str, Any]) -> str:
    lines = [
        f"# 论文计算方法 {candidate['plan_version']}",
        "",
        "## 论文计算方法完整版",
        "",
        candidate["method_full"],
        "",
        "## 可复现实际参数记录",
        "",
    ]
    for assertion in candidate["method_factual_assertions"]:
        lines.extend([f"### {assertion['task_id']} · {assertion['software_name']} · {assertion['software_version']}", ""])
        for field in assertion["parameter_fields"]:
            item = assertion["parameter_snapshot"][field]
            lines.append(f"- `{field}`：{item['value']}（`{item['status']}`；来源 {item['source_file_refs']}）")
        lines.append("")
    if candidate["formula_records"]:
        lines.extend(["## 实际采用公式与参照定义", ""])
        for formula in candidate["formula_records"]:
            lines.extend([f"### {formula['formula_id']} · 任务 {formula['task_id']}", "", f"`{formula['expression']}`", ""])
            for term, definition in formula["term_definitions"].items():
                lines.append(f"- `{term}`：{definition}")
            lines.extend([f"- 真实参照与计算条件：{formula['reference_conditions']}", ""])
    lines.extend(["## 论文计算方法精简版", "", candidate["method_concise"], "", "本节仅记录实际执行的软件、模型与参数；开源迁移建议见独立文件。", ""])
    return "\n".join(lines)


def render_discussion(candidate: dict[str, Any]) -> str:
    return "\n".join([f"# 结果与讨论 {candidate['plan_version']}", "", candidate["result_discussion"], "", "## 理论与实验对应", ""] + [f"- **{item['relation']}** · {item['text']}（边界：{item['boundary']}）" for item in candidate["theory_experiment_correspondence"]] + [""])


def render_conclusion(candidate: dict[str, Any]) -> str:
    lines = [f"# 科学结论 {candidate['plan_version']}", "", "## 分层结论", ""]
    for claim in candidate["conclusion_claims"]:
        lines.extend([f"### {claim['level']} · {claim['claim_id']} · {claim['draft_strength']}", "", claim["text"], "", f"- 直接数据依据：{claim['direct_data_basis']}", f"- 物理含义：{claim['physical_meaning']}", f"- 证据关系：{claim['cross_evidence_relation']}", f"- 实验关系：{claim['experimental_relation']} · {claim['experimental_correspondence']}", f"- 适用边界：{claim['boundary']}", ""])
    lines.extend(["## 各证据节点结论", ""])
    for item in candidate["evidence_node_conclusions"]:
        lines.extend([f"### {item['evidence_node_id']}", "", item["text"], ""])
    lines.extend(["## 总体科学结论", "", candidate["overall_conclusion"], ""])
    return "\n".join(lines)


def render_open_source_note(candidate: dict[str, Any]) -> str:
    lines = [f"# 开源软件复现建议 {candidate['plan_version']}", "", candidate["open_source_reproduction_note"], ""]
    for mapping in candidate["open_source_mappings"]:
        lines.extend([f"## {mapping['actual_task_id']}：{mapping['actual_software']} 的未来复现映射", "", f"- 建议替代：{mapping['proposed_alternatives']}", f"- 参数映射：{mapping['parameter_mappings']}", f"- 不可直接等效：{mapping['non_equivalent_items']}", f"- 限制：{mapping['limitations']}", "", "### 建议模板（未执行）", "", "```text", mapping["suggested_input_template"], "```", ""])
    return "\n".join(lines)


def render_pending(candidate: dict[str, Any]) -> str:
    items = candidate["pending_user_information"] + candidate["blocking_items"] + candidate["publication_pending_items"]
    return "\n".join([f"# 待用户补充信息 {candidate['plan_version']}", ""] + [f"- {item}" for item in sorted(set(items))] + (["- 无"] if not items else []) + [""])


def load_candidate(manuscript_dir: Path, version: str | None) -> dict[str, Any]:
    if not version:
        raise ManuscriptError("No manuscript candidate version was specified.")
    path = manuscript_dir / f"manuscript_plan_{version}.json"
    if not path.is_file():
        raise ManuscriptError(f"Unknown manuscript candidate version: {version}")
    value = read_json(path)
    if not isinstance(value, dict):
        raise ManuscriptError("Manuscript candidate is invalid.")
    return value


def candidate_versions(manuscript_dir: Path) -> list[str]:
    values: list[tuple[int, str]] = []
    for path in manuscript_dir.glob("manuscript_plan_v*.json"):
        match = re.fullmatch(r"manuscript_plan_v(\d{3,})\.json", path.name)
        if match:
            values.append((int(match.group(1)), f"v{int(match.group(1)):03d}"))
    return [value for _, value in sorted(values)]


def submit_candidate_value(
    manuscript_dir: Path,
    status: dict[str, Any],
    payload: dict[str, Any],
    reason: str,
) -> dict[str, Any]:
    if status.get("status") == MANUSCRIPT_CONTENT_APPROVED:
        raise ManuscriptError("Approved manuscript content is immutable.")
    if status.get("status") not in {SOFTWARE_LICENSE_REVIEWED, WAITING_FOR_MANUSCRIPT_REVIEW, WAITING_FOR_MANUSCRIPT_APPROVAL, MANUSCRIPT_IMPACT_ANALYZED}:
        raise ManuscriptError("Validate actual sources and complete license review before manuscript generation/editing.")
    ensure_false_flags(payload)
    inventory = load_source_inventory(status)
    license_review = load_license_review(status)
    if str(payload.get("project_id")) != str(status.get("project_id")):
        raise ManuscriptError("Manuscript candidate project ID differs from stage 4.")
    if payload.get("source_inventory_record") != status.get("current_source_inventory_record"):
        raise ManuscriptError("Manuscript candidate must bind the current immutable source inventory record.")
    if payload.get("license_review_record") != status.get("current_license_review_record"):
        raise ManuscriptError("Manuscript candidate must bind the current immutable license review record.")
    licenses = review_license_map(license_review)
    actual_software = {task["actual_software"]["name"] for task in inventory["tasks"]}
    nonopen_required = any(licenses[name]["license_category"] in NONOPEN_LICENSES for name in actual_software)
    profile = validate_document_profile(payload.get("document_profile"), nonopen_required)
    assertions = validate_method_assertions(payload.get("method_factual_assertions"), inventory)
    claims = validate_conclusion_claims(payload.get("conclusion_claims"), status)
    mentions = validate_actual_mentions(payload.get("actual_method_software_mentions"), inventory)
    mappings, alternatives = validate_open_source_mappings(payload.get("open_source_mappings"), inventory, license_review)
    method_full = str(payload.get("method_full", "")).strip()
    method_concise = str(payload.get("method_concise", "")).strip()
    result_discussion = str(payload.get("result_discussion", "")).strip()
    overall_conclusion = str(payload.get("overall_conclusion", "")).strip()
    software_citation_text = str(payload.get("software_citation_text", "")).strip()
    license_review_text = str(payload.get("license_review_text", "")).strip()
    reproduction_note = str(payload.get("open_source_reproduction_note", "")).strip()
    if not all((method_full, method_concise, result_discussion, overall_conclusion, software_citation_text, license_review_text)):
        raise ManuscriptError("Full/concise methods, discussion, overall conclusion, citation text, and license text are required.")
    for name in actual_software:
        if name.lower() not in method_full.lower() or name.lower() not in method_concise.lower():
            raise ManuscriptError(f"Both actual-method versions must name the real software {name}.")
    for task in inventory["tasks"]:
        if task["actual_software"]["version_status"] == "unconfirmed" and MISSING_VERSION_STATEMENT not in method_full:
            raise ManuscriptError(f"The full method must retain the exact missing-version statement for {task['task_id']}.")
        for difference in task.get("actual_vs_planned_differences", []):
            if not isinstance(difference, dict):
                continue
            planned = difference.get("planned")
            actual_value = difference.get("actual")
            if not isinstance(planned, (str, int, float)) or not isinstance(actual_value, (str, int, float)) or str(planned) == str(actual_value):
                continue
            planned_pattern = re.compile(r"(?<![A-Za-z0-9])" + re.escape(str(planned)) + r"(?![A-Za-z0-9])", re.IGNORECASE)
            actual_pattern = re.compile(r"(?<![A-Za-z0-9])" + re.escape(str(actual_value)) + r"(?![A-Za-z0-9])", re.IGNORECASE)
            if planned_pattern.search(method_full) and not actual_pattern.search(method_full):
                raise ManuscriptError(f"The full method uses planned {difference.get('field')}={planned} instead of actual {actual_value} for {task['task_id']}.")
    source_task_by_id = inventory_task_map(inventory)
    for assertion in assertions:
        formulas_by_id = {formula["formula_id"]: formula for formula in source_task_by_id[assertion["task_id"]].get("actual_formulas", [])}
        for formula_id in assertion["formula_ids"]:
            expression = str(formulas_by_id[formula_id]["expression"])
            if expression not in method_full:
                raise ManuscriptError(f"The full method omits the actually used formula {formula_id} or changes its recorded expression.")
    alternative_only = {name for name in alternatives if name not in actual_software}
    for name in alternative_only:
        pattern = re.compile(r"(?<![A-Za-z0-9])" + re.escape(name) + r"(?![A-Za-z0-9])", re.IGNORECASE)
        if pattern.search(method_full) or pattern.search(method_concise):
            raise ManuscriptError(f"Unexecuted alternative {name} cannot appear in the actual computational method.")
    if mappings:
        if reproduction_note.count(OPEN_SOURCE_DISCLAIMER) != 1:
            raise ManuscriptError("The separate reproduction note must contain the exact open-source disclaimer once.")
        prohibited_titles = ("本文实际采用的开源计算方法", "本研究使用的开源软件", "本工作由开源软件完成")
        if any(title in reproduction_note for title in prohibited_titles):
            raise ManuscriptError("Open-source reproduction guidance cannot claim it was the actual method.")
    elif profile["retain_open_source_note"] and not reproduction_note:
        raise ManuscriptError("retain_open_source_note requires nonempty reproduction guidance.")
    if phrase_present(result_discussion + "\n" + overall_conclusion, HIGH_CERTAINTY_PHRASES):
        raise ManuscriptError("Discussion or overall conclusion uses prohibited certainty/proof wording.")
    claim_map = {claim["claim_id"]: claim for claim in claims}
    overall_claims = [claim for claim in claims if claim["level"] == "overall"]
    if overall_claims[0]["text"] not in overall_conclusion:
        raise ManuscriptError("Overall conclusion must preserve the structured overall claim text.")
    paragraphs = normalize_evidence_node_paragraphs(payload.get("evidence_node_conclusions"), claims, status)
    paragraph_text = "\n".join(item["text"] for item in paragraphs)
    for claim in claims:
        if claim["level"] != "overall" and claim["text"] not in result_discussion and claim["text"] not in paragraph_text:
            raise ManuscriptError(f"Structured conclusion claim {claim['claim_id']} is absent from discussion/evidence-node paragraphs.")
    experiment_mappings = normalize_experiment_mappings(payload.get("theory_experiment_correspondence"), claims)
    pending = normalize_text_list(payload.get("pending_user_information", []), "pending_user_information")
    quotes = validate_quotes(payload.get("manual_source_quotes", []))
    task_sources = inventory_task_map(inventory)
    formula_records = [
        {"task_id": assertion["task_id"], **copy.deepcopy(formula)}
        for assertion in assertions
        for formula in task_sources[assertion["task_id"]].get("actual_formulas", [])
        if formula["formula_id"] in assertion["formula_ids"]
    ]
    evidence_claim_ids = {claim_id for paragraph in paragraphs for claim_id in paragraph["claim_ids"]}
    if not evidence_claim_ids.issubset(claim_map):
        raise ManuscriptError("Evidence-node paragraphs cite an unknown structured claim.")
    publication_pending = sorted(
        set(inventory.get("missing_version_items", []))
        | set(license_review.get("citation_pending_items", []))
        | set(license_review.get("public_release_blockers", []))
    )
    before = load_candidate(manuscript_dir, status.get("current_candidate_version")) if status.get("current_candidate_version") else None
    version = next_version(manuscript_dir, "manuscript_plan_")
    normalized = {
        "project_id": status.get("project_id"),
        "document_profile": profile,
        "source_inventory_record": copy.deepcopy(status["current_source_inventory_record"]),
        "license_review_record": copy.deepcopy(status["current_license_review_record"]),
        "method_factual_assertions": assertions,
        "actual_method_software_mentions": mentions,
        "formula_records": formula_records,
        "conclusion_claims": claims,
        "method_full": method_full,
        "method_concise": method_concise,
        "result_discussion": result_discussion,
        "overall_conclusion": overall_conclusion,
        "evidence_node_conclusions": paragraphs,
        "theory_experiment_correspondence": experiment_mappings,
        "software_citation_text": software_citation_text,
        "license_review_text": license_review_text,
        "open_source_mappings": mappings,
        "open_source_reproduction_note": reproduction_note,
        "pending_user_information": pending,
        "manual_source_quotes": quotes,
        "blocking_items": copy.deepcopy(inventory.get("blocking_actual_parameter_items", [])),
        "publication_pending_items": publication_pending,
        "submission_ready": not inventory.get("blocking_actual_parameter_items") and not publication_pending,
        **false_flags(),
    }
    impact_before = None
    if before:
        impact_before = {key: value for key, value in before.items() if key not in {"plan_version", "generated_at", "version_record", "impact_record", "current_state"}}
    impact = analyze_impact(impact_before, normalized, reason)
    candidate = {
        **normalized,
        "plan_version": version,
        "generated_at": utc_now(),
        "version_record": {
            "previous_version": before.get("plan_version") if before else None,
            "reason": reason or "initial manuscript generation",
            "restored_from": payload.get("restored_from"),
        },
        "current_state": WAITING_FOR_MANUSCRIPT_REVIEW if before is None else WAITING_FOR_MANUSCRIPT_APPROVAL,
    }
    impact.update({"project_id": status.get("project_id"), "candidate_version": version, "generated_at": utc_now()})
    plan_path = manuscript_dir / f"manuscript_plan_{version}.json"
    method_path = manuscript_dir / f"method_statement_{version}.md"
    discussion_path = manuscript_dir / f"result_discussion_{version}.md"
    conclusion_path = manuscript_dir / f"conclusion_{version}.md"
    open_path = manuscript_dir / f"open_source_reproduction_note_{version}.md"
    citation_path = manuscript_dir / "software_citations" / f"software_citation_list_manuscript_{version}.md"
    license_path = manuscript_dir / "license_review" / f"license_review_manuscript_{version}.md"
    pending_path = manuscript_dir / "user_edits" / f"pending_user_information_{version}.md"
    impact_path = manuscript_dir / f"manuscript_impact_analysis_{version}.json"
    impact_md_path = manuscript_dir / f"manuscript_impact_analysis_{version}.md"
    write_json(plan_path, candidate)
    method_text = render_method(candidate)
    discussion_text = render_discussion(candidate)
    conclusion_text = render_conclusion(candidate)
    open_text = render_open_source_note(candidate)
    write_text(method_path, method_text)
    write_text(discussion_path, discussion_text)
    write_text(conclusion_path, conclusion_text)
    write_text(open_path, open_text)
    method_archive = manuscript_dir / "method_drafts" / f"method_statement_{version}.md"
    discussion_archive = manuscript_dir / "result_discussion" / f"result_discussion_{version}.md"
    conclusion_archive = manuscript_dir / "conclusions" / f"conclusion_{version}.md"
    open_archive = manuscript_dir / "open_source_migration" / f"open_source_reproduction_note_{version}.md"
    write_text(method_archive, method_text)
    write_text(discussion_archive, discussion_text)
    write_text(conclusion_archive, conclusion_text)
    write_text(open_archive, open_text)
    write_text(citation_path, "# 软件与方法引用清单\n\n" + software_citation_text + "\n")
    write_text(license_path, "# 软件许可与文件共享检查\n\n" + license_review_text + "\n")
    write_text(pending_path, render_pending(candidate))
    write_json(impact_path, impact)
    write_text(impact_md_path, "# 用户修改影响分析\n\n" + f"- 版本：`{version}`\n- 最高影响：`{impact['overall_impact']}`\n- 摘要：{impact['summary']}\n\n" + "\n".join(f"- `{item['path']}` · **{item['impact']}** · {item['scientific_effect']}" for item in impact["changes"]) + "\n")
    artifact_records = {
        "plan": file_record(plan_path),
        "method": file_record(method_path),
        "discussion": file_record(discussion_path),
        "conclusion": file_record(conclusion_path),
        "open_source": file_record(open_path),
        "citations": file_record(citation_path),
        "license": file_record(license_path),
        "pending": file_record(pending_path),
        "impact": file_record(impact_path),
        "impact_markdown": file_record(impact_md_path),
        "method_archive": file_record(method_archive),
        "discussion_archive": file_record(discussion_archive),
        "conclusion_archive": file_record(conclusion_archive),
        "open_source_archive": file_record(open_archive),
    }
    record = {"version": version, "artifacts": artifact_records, "state": candidate["current_state"], "overall_impact": impact["overall_impact"]}
    status.setdefault("candidate_records", []).append(record)
    status.setdefault("impact_records", []).append(artifact_records["impact"])
    status["current_candidate_version"] = version
    status["current_candidate_record"] = artifact_records["plan"]
    status["current_artifacts"] = artifact_records
    status["blocking_items"] = candidate["blocking_items"]
    status["status"] = candidate["current_state"]
    write_status(manuscript_dir, status)
    append_log(manuscript_dir, {"event": "conclusion_draft_generated", "version": version, "state": CONCLUSION_DRAFT_GENERATED})
    append_log(manuscript_dir, {"event": "method_statement_generated", "version": version, "state": METHOD_STATEMENT_GENERATED})
    append_log(manuscript_dir, {"event": "open_source_mapping_generated", "version": version, "state": OPEN_SOURCE_MAPPING_GENERATED})
    append_log(manuscript_dir, {"event": "manuscript_candidate_generated" if before is None else "user_manuscript_edit_impact_analyzed", "version": version, "state": status["status"], "overall_impact": impact["overall_impact"], "reason": reason})
    return candidate


def submit_candidate(manuscript_dir: Path, source_path: Path, reason: str) -> dict[str, Any]:
    status = load_status(manuscript_dir)
    payload = read_json(source_path)
    if not isinstance(payload, dict):
        raise ManuscriptError("Manuscript candidate must be a JSON object.")
    return submit_candidate_value(manuscript_dir, status, payload, reason)


def verify_current_artifacts(status: dict[str, Any]) -> dict[str, dict[str, Any]]:
    artifacts = status.get("current_artifacts")
    if not isinstance(artifacts, dict):
        raise ManuscriptError("Current manuscript artifacts are missing.")
    for name, record in artifacts.items():
        verify_file_record(record, f"current manuscript artifact {name}")
    return artifacts


def approve_manuscript(manuscript_dir: Path, status: dict[str, Any], confirmed_by: str, reason: str) -> dict[str, Any]:
    if status.get("status") != WAITING_FOR_MANUSCRIPT_APPROVAL:
        raise ManuscriptError("Only a manuscript waiting for approval may be approved.")
    identity = str(confirmed_by).strip()
    if not identity or identity.lower() in {"skill", "assistant", "automatic"}:
        raise ManuscriptError("Manuscript approval requires explicit user confirmation.")
    candidate = load_candidate(manuscript_dir, status.get("current_candidate_version"))
    if candidate.get("blocking_items"):
        raise ManuscriptError("Unknown result-relevant actual parameters block final manuscript approval: " + ", ".join(candidate["blocking_items"]))
    artifacts = verify_current_artifacts(status)
    aliases = {
        "method_statement_approved.md": artifacts["method"],
        "result_discussion_approved.md": artifacts["discussion"],
        "conclusion_approved.md": artifacts["conclusion"],
        "software_citation_list_approved.md": artifacts["citations"],
        "license_review_approved.md": artifacts["license"],
        "open_source_reproduction_note_approved.md": artifacts["open_source"],
    }
    approved_records: dict[str, dict[str, Any]] = {}
    for filename, source_record in aliases.items():
        source = verify_file_record(source_record, f"approval source {filename}")
        target = manuscript_dir / filename
        if target.exists():
            raise ManuscriptError(f"Approved target already exists: {filename}")
        write_bytes(target, source.read_bytes())
        approved_records[filename] = file_record(target)
    approval = {
        "project_id": status.get("project_id"),
        "approved_candidate_version": candidate["plan_version"],
        "candidate_record": copy.deepcopy(status["current_candidate_record"]),
        "source_inventory_record": copy.deepcopy(status["current_source_inventory_record"]),
        "license_review_record": copy.deepcopy(status["current_license_review_record"]),
        "upstream_snapshot_record": copy.deepcopy(status["upstream_snapshot_record"]),
        "approved_files": approved_records,
        "conclusion_strengths": {item["claim_id"]: {"source": item["source_strength"], "approved": item["draft_strength"]} for item in candidate["conclusion_claims"]},
        "publication_pending_items": copy.deepcopy(candidate["publication_pending_items"]),
        "submission_ready": candidate["submission_ready"],
        "open_source_mapping_is_future_guidance": True,
        "confirmed_by": identity,
        "reason": str(reason).strip(),
        "confirmed_at": utc_now(),
        **false_flags(),
    }
    approval_path = manuscript_dir / "manuscript_approval_record.json"
    write_json(approval_path, approval)
    approval_record = file_record(approval_path)
    status.setdefault("approval_records", []).append(approval_record)
    status["current_approval_record"] = approval_record
    status["status"] = MANUSCRIPT_CONTENT_APPROVED
    status["manuscript_content_approved"] = True
    write_status(manuscript_dir, status)
    append_log(manuscript_dir, {"event": "manuscript_content_approved", "version": candidate["plan_version"], "submission_ready": candidate["submission_ready"], "confirmed_by": identity})
    return approval


def transition(
    manuscript_dir: Path,
    action_name: str,
    reason: str,
    version: str | None,
    confirmed_by: str,
) -> dict[str, Any]:
    status = load_status(manuscript_dir)
    if action_name == "ready-for-approval":
        if status.get("status") != WAITING_FOR_MANUSCRIPT_REVIEW:
            raise ManuscriptError("Only a reviewed initial manuscript can be marked ready for approval.")
        candidate = load_candidate(manuscript_dir, status.get("current_candidate_version"))
        if candidate.get("blocking_items"):
            raise ManuscriptError("Resolve unknown actual parameters before approval review.")
        status["status"] = WAITING_FOR_MANUSCRIPT_APPROVAL
        write_status(manuscript_dir, status)
        append_log(manuscript_dir, {"event": "manuscript_marked_ready_for_approval", "version": candidate["plan_version"], "reason": reason})
        return {"status": status["status"], "version": candidate["plan_version"]}
    if action_name == "continue-editing":
        if status.get("status") != WAITING_FOR_MANUSCRIPT_APPROVAL:
            raise ManuscriptError("continue-editing requires a manuscript waiting for approval.")
        status["status"] = WAITING_FOR_MANUSCRIPT_REVIEW
        write_status(manuscript_dir, status)
        append_log(manuscript_dir, {"event": "manuscript_returned_to_editing", "version": status.get("current_candidate_version"), "reason": reason})
        return {"status": status["status"], "version": status.get("current_candidate_version")}
    if action_name == "restore":
        if status.get("status") not in {WAITING_FOR_MANUSCRIPT_REVIEW, WAITING_FOR_MANUSCRIPT_APPROVAL}:
            raise ManuscriptError("Restore is available only during manuscript review.")
        if not version or version == status.get("current_candidate_version"):
            raise ManuscriptError("Select a noncurrent historical version to restore as a new version.")
        old = load_candidate(manuscript_dir, version)
        payload = {key: copy.deepcopy(value) for key, value in old.items() if key not in {"plan_version", "generated_at", "version_record", "current_state"}}
        payload["restored_from"] = version
        return submit_candidate_value(manuscript_dir, status, payload, reason or f"restore {version}")
    if action_name == "approve":
        raise ManuscriptError("Manuscript approval must be submitted through the hash-bound browser review command.")
    raise ManuscriptError("Action must be ready-for-approval, continue-editing, restore, or approve.")


def browser_review(
    manuscript_dir: Path,
    project_dir: Path,
    title: str,
    start_port: int,
    timeout_seconds: float | None,
) -> dict[str, Any]:
    status = load_status(manuscript_dir)
    version = status.get("current_candidate_version")
    if not version:
        raise ManuscriptError("No manuscript candidate is available for browser review.")
    return execute_stage_review(
        project_dir=project_dir,
        stage_dir=manuscript_dir,
        stage="stage4_manuscript",
        title=title,
        content_file=manuscript_dir / f"manuscript_plan_{version}.json",
        allowed_statuses={WAITING_FOR_MANUSCRIPT_APPROVAL},
        revision_status=WAITING_FOR_MANUSCRIPT_REVIEW,
        rejected_status=STAGE4_REVIEW_REJECTED,
        load_status=lambda: load_status(manuscript_dir),
        save_status=lambda value: write_status(manuscript_dir, value),
        append_log=lambda value: append_log(manuscript_dir, value),
        approve=lambda comment: approve_manuscript(
            manuscript_dir,
            load_status(manuscript_dir),
            "browser_user",
            comment,
        ),
        error_type=ManuscriptError,
        blocked_access_updates={"manuscript_content_approved": False},
        revision_updates={"manuscript_content_approved": False},
        rejected_updates={"manuscript_content_approved": False},
        start_port=start_port,
        timeout_seconds=timeout_seconds,
    )


def current_data(manuscript_dir: Path) -> dict[str, Any]:
    status = load_status(manuscript_dir)
    inventory = load_source_inventory(status) if status.get("current_source_inventory_record") else None
    license_review = load_license_review(status) if status.get("current_license_review_record") else None
    candidate = load_candidate(manuscript_dir, status.get("current_candidate_version")) if status.get("current_candidate_version") else None
    impact = None
    if candidate:
        impact_path = manuscript_dir / f"manuscript_impact_analysis_{candidate['plan_version']}.json"
        impact = read_json(impact_path) if impact_path.is_file() else None
    approval = None
    if status.get("current_approval_record"):
        approval = read_json(verify_file_record(status["current_approval_record"], "current manuscript approval"))
    return {
        "manuscript_dir": str(manuscript_dir.resolve()),
        "status": status,
        "upstream": upstream_snapshot(status),
        "source_inventory": inventory,
        "license_review": license_review,
        "candidate": candidate,
        "impact": impact,
        "approval": approval,
        "versions": candidate_versions(manuscript_dir),
        "change_log": read_json(change_log_path(manuscript_dir)),
    }


class ManuscriptHandler(BaseHTTPRequestHandler):
    manuscript_dir: Path

    def log_message(self, format_string: str, *args: Any) -> None:
        sys.stderr.write("[manuscript-review] " + format_string % args + "\n")

    def send_json(self, payload: Any, status: HTTPStatus = HTTPStatus.OK) -> None:
        encoded = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status.value)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(encoded)

    def send_file(self, path: Path, content_type: str | None = None) -> None:
        data = path.read_bytes()
        self.send_response(HTTPStatus.OK.value)
        self.send_header("Content-Type", content_type or mimetypes.guess_type(path.name)[0] or "application/octet-stream")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Disposition", f'inline; filename="{safe_name(path.name)}"')
        self.end_headers()
        self.wfile.write(data)

    def body(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0"))
        if length <= 0 or length > 16 * 1024 * 1024:
            raise ManuscriptError("Request body must be between 1 byte and 16 MiB.")
        value = json.loads(self.rfile.read(length).decode("utf-8"))
        if not isinstance(value, dict):
            raise ManuscriptError("Request body must be a JSON object.")
        return value

    def do_GET(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
        try:
            if path in {"/", "/manuscript_review.html"}:
                self.send_file(self.manuscript_dir / "manuscript_review.html", "text/html; charset=utf-8")
            elif path == "/api/state":
                self.send_json(current_data(self.manuscript_dir))
            elif path.startswith("/files/"):
                target = safe_relative_path(self.manuscript_dir, path[len("/files/") :])
                if not target.is_file():
                    self.send_json({"error": "File not found"}, HTTPStatus.NOT_FOUND)
                else:
                    self.send_file(target)
            else:
                self.send_json({"error": "Not found"}, HTTPStatus.NOT_FOUND)
        except (ManuscriptError, OSError, ValueError, json.JSONDecodeError) as exc:
            self.send_json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)

    def do_POST(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
        try:
            payload = self.body()
            if path == "/api/submit":
                candidate = payload.get("candidate")
                if not isinstance(candidate, dict):
                    raise ManuscriptError("candidate must be a JSON object.")
                result = submit_candidate_value(self.manuscript_dir, load_status(self.manuscript_dir), candidate, str(payload.get("reason", "")))
            elif path == "/api/action":
                result = transition(
                    self.manuscript_dir,
                    str(payload.get("action", "")),
                    str(payload.get("reason", "")),
                    str(payload["version"]) if payload.get("version") else None,
                    str(payload.get("confirmed_by", "user")),
                )
            else:
                self.send_json({"error": "Not found"}, HTTPStatus.NOT_FOUND)
                return
            self.send_json({"ok": True, "result": result})
        except (ManuscriptError, OSError, ValueError, json.JSONDecodeError) as exc:
            self.send_json({"ok": False, "error": str(exc)}, HTTPStatus.BAD_REQUEST)


def serve(manuscript_dir: Path, host: str, port: int, open_page: bool) -> None:
    load_status(manuscript_dir)
    ensure_review_html(manuscript_dir)
    handler = type("BoundManuscriptHandler", (ManuscriptHandler,), {"manuscript_dir": manuscript_dir})
    server = ThreadingHTTPServer((host, port), handler)
    address = f"http://{host}:{server.server_address[1]}/"
    print(f"Stage-4 manuscript review page: {address}", flush=True)
    print("Press Ctrl+C to stop. This page never calculates, post-processes, plots, submits, or republishes restricted files.", flush=True)
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

    start_parser = subparsers.add_parser("start", help="Freeze approved stage-1/2/3 sources for stage 4.")
    start_parser.add_argument("--planning-dir", type=Path, required=True)
    start_parser.add_argument("--formal-dir", type=Path, required=True)
    start_parser.add_argument("--analysis-dir", type=Path, required=True)
    start_parser.add_argument("--model-manifest", type=Path, required=True)
    start_parser.add_argument("--manuscript-dir", type=Path, default=Path("manuscript_generation"))

    sources_parser = subparsers.add_parser("submit-sources", help="Validate and copy the actual software/input/output/model inventory.")
    sources_parser.add_argument("--manuscript-dir", type=Path, default=Path("manuscript_generation"))
    sources_parser.add_argument("--inventory", type=Path, required=True)

    license_parser = subparsers.add_parser("review-license", help="Record software citations, licenses, and sharing constraints.")
    license_parser.add_argument("--manuscript-dir", type=Path, default=Path("manuscript_generation"))
    license_parser.add_argument("--review", type=Path, required=True)

    submit_parser = subparsers.add_parser("submit", help="Generate or edit an immutable manuscript candidate version.")
    submit_parser.add_argument("--manuscript-dir", type=Path, default=Path("manuscript_generation"))
    submit_parser.add_argument("--candidate", type=Path, required=True)
    submit_parser.add_argument("--reason", default="")

    action_parser = subparsers.add_parser("action", help="Advance review, restore a version, or approve content.")
    action_parser.add_argument("--manuscript-dir", type=Path, default=Path("manuscript_generation"))
    action_parser.add_argument("--action", choices=("ready-for-approval", "continue-editing", "restore", "approve"), required=True)
    action_parser.add_argument("--reason", default="")
    action_parser.add_argument("--version")
    action_parser.add_argument("--confirmed-by", default="user")

    serve_parser = subparsers.add_parser("serve", help="Serve the local stage-4 manuscript review page.")
    serve_parser.add_argument("--manuscript-dir", type=Path, default=Path("manuscript_generation"))
    serve_parser.add_argument("--host", default="127.0.0.1")
    serve_parser.add_argument("--port", type=int, default=0)
    serve_parser.add_argument("--open", action="store_true", dest="open_page")

    review_parser = subparsers.add_parser("review", help="Open the hash-bound Flask review gate and wait for a decision.")
    review_parser.add_argument("--manuscript-dir", type=Path, default=Path("manuscript_generation"))
    review_parser.add_argument("--project-dir", type=Path)
    review_parser.add_argument("--title", default="第四阶段：科学结论与论文内容审查")
    review_parser.add_argument("--start-port", type=int, default=5050)
    review_parser.add_argument("--timeout", type=float, default=0.0)

    status_parser = subparsers.add_parser("status", help="Show stage-4 state without external actions.")
    status_parser.add_argument("--manuscript-dir", type=Path, default=Path("manuscript_generation"))
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        if args.command == "start":
            result = start(args.manuscript_dir.resolve(), args.planning_dir.resolve(), args.formal_dir.resolve(), args.analysis_dir.resolve(), args.model_manifest.resolve())
        elif args.command == "submit-sources":
            result = submit_source_inventory(args.manuscript_dir.resolve(), args.inventory.resolve())
        elif args.command == "review-license":
            result = submit_license_review(args.manuscript_dir.resolve(), args.review.resolve())
        elif args.command == "submit":
            result = submit_candidate(args.manuscript_dir.resolve(), args.candidate.resolve(), args.reason)
        elif args.command == "action":
            result = transition(args.manuscript_dir.resolve(), args.action, args.reason, args.version, args.confirmed_by)
        elif args.command == "serve":
            serve(args.manuscript_dir.resolve(), args.host, args.port, args.open_page)
            return 0
        elif args.command == "review":
            manuscript_dir = args.manuscript_dir.resolve()
            project_dir = args.project_dir.resolve() if args.project_dir else manuscript_dir.parent
            result = browser_review(manuscript_dir, project_dir, args.title, args.start_port, args.timeout)
        elif args.command == "status":
            result = current_data(args.manuscript_dir.resolve())
        else:
            raise ManuscriptError(f"Unsupported command: {args.command}")
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (ManuscriptError, OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
