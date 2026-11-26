#!/usr/bin/env python3
"""Guide data processing and validate evidence without calculations or plots.

This workflow engine only copies, inspects, versions, and reviews user data. It
does not invoke scientific/post-processing software, generated commands, MPI,
schedulers, remote services, monitors, or figure-generation pipelines.
"""

from __future__ import annotations

import argparse
import copy
import csv
import hashlib
import json
import mimetypes
import re
import shutil
import sys
import threading
import webbrowser
import zipfile
from datetime import datetime, timezone
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse
from xml.etree import ElementTree

from review_ui.stage_gate import WAITING_FOR_REVIEW_DECISION, execute_stage_review

WAITING_FOR_USER_DATA_STATUS = "WAITING_FOR_USER_DATA_STATUS"
RAW_DATA_RECEIVED = "RAW_DATA_RECEIVED"
PROCESSING_GUIDE_REQUIRED = "PROCESSING_GUIDE_REQUIRED"
PROCESSING_GUIDE_PROVIDED = "PROCESSING_GUIDE_PROVIDED"
USER_PROCESSING_IN_PROGRESS = "USER_PROCESSING_IN_PROGRESS"
PROCESSED_DATA_RECEIVED = "PROCESSED_DATA_RECEIVED"
DATA_COMPLETENESS_CHECKED = "DATA_COMPLETENESS_CHECKED"
DATA_COMPARABILITY_VALIDATED = "DATA_COMPARABILITY_VALIDATED"
RESULT_ANALYSIS_COMPLETED = "RESULT_ANALYSIS_COMPLETED"
EVIDENCE_CHAIN_VALIDATED = "EVIDENCE_CHAIN_VALIDATED"
SUPPLEMENTARY_PROCESSING_REQUIRED = "SUPPLEMENTARY_PROCESSING_REQUIRED"
RETURN_TO_FORMAL_CALCULATION = "RETURN_TO_FORMAL_CALCULATION"
WAITING_FOR_RESULT_APPROVAL = "WAITING_FOR_RESULT_APPROVAL"
RESULTS_APPROVED = "RESULTS_APPROVED"
STAGE3_REVIEW_REJECTED = "STAGE3_REVIEW_REJECTED"

VALID_STATES = {
    WAITING_FOR_USER_DATA_STATUS,
    RAW_DATA_RECEIVED,
    PROCESSING_GUIDE_REQUIRED,
    PROCESSING_GUIDE_PROVIDED,
    USER_PROCESSING_IN_PROGRESS,
    PROCESSED_DATA_RECEIVED,
    DATA_COMPLETENESS_CHECKED,
    DATA_COMPARABILITY_VALIDATED,
    RESULT_ANALYSIS_COMPLETED,
    EVIDENCE_CHAIN_VALIDATED,
    SUPPLEMENTARY_PROCESSING_REQUIRED,
    RETURN_TO_FORMAL_CALCULATION,
    WAITING_FOR_RESULT_APPROVAL,
    WAITING_FOR_REVIEW_DECISION,
    STAGE3_REVIEW_REJECTED,
    RESULTS_APPROVED,
}

INITIAL_QUESTION = """请说明当前数据属于以下哪种情况：

1. 只有计算软件的原始输出文件；
2. 已经提取部分数据，但尚未完成处理；
3. 已经完成数据处理，需要分析结果和结论；
4. 不清楚如何处理，希望先获得完整教程；
5. 已经进行到某一步，需要从当前步骤继续。

可以直接上传文件，并说明当前做到第几步。"""

FOLLOWUP_INVITATION = "你可以直接说“第 3 步不会”“我进行到第 5 步”或“第 6 步检查没有通过”，我会从对应位置继续。"

EXECUTION_FLAG_NAMES = {
    "calculation_executed_by_skill",
    "postprocessing_executed_by_skill",
    "job_submitted_by_skill",
    "queue_queried_by_skill",
    "remote_result_retrieval",
    "background_monitoring",
    "research_figures_generated_by_skill",
}

DATA_STATUS_MAP = {
    "raw": RAW_DATA_RECEIVED,
    "partial": USER_PROCESSING_IN_PROGRESS,
    "processed": PROCESSED_DATA_RECEIVED,
    "tutorial": PROCESSING_GUIDE_REQUIRED,
    "resume": USER_PROCESSING_IN_PROGRESS,
}

DATA_STAGES = {"raw", "partial", "processed"}
DATA_TYPES = {
    "binding_energy",
    "adsorption_energy",
    "charge_density_difference",
    "bader_charge",
    "dos_pdos",
    "cohp",
    "qtaim",
    "geometry",
    "molecular_dynamics",
    "approved_other",
}

FILE_ROLES = {
    "actual_input",
    "raw_output",
    "main_output",
    "stderr",
    "table",
    "csv",
    "excel",
    "text",
    "integration",
    "peak_positions",
    "processed_result",
    "density",
    "charge_partition",
    "dos",
    "pdos",
    "cohp",
    "qtaim",
    "image",
    "metadata",
    "other",
}

PROGRESS_MARKERS = {
    "该数据尚未处理",
    "正在进行第几步",
    "处理已完成",
    "需要步骤指导",
    "数据存在疑问",
}

CHECK_RESULTS = {"passed", "failed", "unknown", "not_applicable"}
COMMON_CHECK_KEYS = (
    "calculation_completed",
    "actual_parameters_checked",
    "target_data_extracted",
    "reference_basis_unified",
    "target_processing_completed",
    "comparability_checked",
    "upload_format_complete",
)
COMPARABILITY_KEYS = (
    "method",
    "model_version",
    "unit",
    "reference_definition",
    "structure_state",
    "numerical_parameters",
    "coordinate_atom_mapping",
    "grid_or_energy_zero",
)
METADATA_FIELDS = {
    "system_name",
    "model_version",
    "calculation_task",
    "parameter_name",
    "unit",
    "reference_definition",
    "software",
    "method",
    "atom_or_orbital_assignment",
    "image_isovalue",
    "color_definition",
    "quantitative_support",
    "completed_steps",
}
CORE_METADATA_FIELDS = {
    "system_name",
    "model_version",
    "calculation_task",
    "parameter_name",
    "unit",
    "reference_definition",
    "software",
    "method",
    "atom_or_orbital_assignment",
}

FORMAL_RETURN_REASONS = {
    "missing_raw_calculation",
    "wrong_core_parameter",
    "irreparable_reference_incomparability",
    "insufficient_source_precision",
}
RESOLUTION_SCOPES = {"none", "processing_only", "formal_recalculation"}
OUTCOME_STATES = {
    "CURRENT_ANALYSIS_READY_FOR_APPROVAL": WAITING_FOR_RESULT_APPROVAL,
    "SUPPLEMENTARY_PROCESSING_REQUIRED": SUPPLEMENTARY_PROCESSING_REQUIRED,
    "RETURN_TO_FORMAL_CALCULATION": RETURN_TO_FORMAL_CALCULATION,
}
CONCLUSION_STRENGTHS = {
    "STRONGLY_SUPPORTED",
    "SUPPORTED",
    "PARTIALLY_SUPPORTED",
    "INCONCLUSIVE",
    "CONTRADICTED",
}
CONTRADICTION_CHECK_KEYS = (
    "reference_system",
    "energy_zero",
    "atom_mapping",
    "model_version",
    "calculation_parameters",
    "unit_conversion",
    "sign_convention",
    "result_convergence_validity",
)

FORMAL_REAL_RESULT_STATES = {
    "FORMAL_CALCULATION_RESULT_RECEIVED",
    "FORMAL_RESULT_VALIDATED",
    "FORMAL_RESULT_REJECTED",
    "FORMAL_FILES_REGENERATION_REQUIRED",
    "NEXT_FORMAL_BATCH_READY",
    "FORMAL_EVIDENCE_NODE_COMPLETED",
    "FORMAL_CALCULATION_WORKFLOW_COMPLETED",
}

STEP_TITLES = (
    "确认计算完成状态",
    "核对实际计算参数",
    "提取目标数据",
    "统一数据基准",
    "完成目标参数处理",
    "检查可比性",
    "整理上传格式",
    "上传并进行结论分析",
)

TASK_STEP_SUMMARIES: dict[str, tuple[str, ...]] = {
    "binding_energy": (
        "确认界面、组分 A 和组分 B 的单点计算均真实完成。",
        "核对三者晶格、应变状态和计算参数。",
        "提取三套体系最终总能量。",
        "将能量统一为批准单位。",
        "按批准的结合能公式计算。",
        "检查符号、参照体系及等价界面数量。",
        "整理不同模型的结合能对比表。",
        "上传表格，分析稳定性和模型差异。",
    ),
    "adsorption_energy": (
        "确认吸附体系、洁净表面和孤立吸附物均真实完成。",
        "核对理论方法、总电荷、自旋和参数。",
        "提取三套体系总能量。",
        "统一能量单位。",
        "按批准的吸附能定义计算。",
        "检查孤立盒、自旋和周期镜像影响。",
        "整理不同位点和构型的吸附能表。",
        "上传表格，分析吸附倾向和位点选择性。",
    ),
    "charge_density_difference": (
        "确认复合体系及两个组分的密度计算完成。",
        "核对晶格、坐标、网格和方法完全一致。",
        "导出三套电子密度数据。",
        "统一坐标、网格、单位和原子映射。",
        "按批准定义完成密度相减。",
        "检查差分网格、单位和积分一致性。",
        "整理积累/耗尽区域及定量佐证表。",
        "上传数值结果，分析转移方向和空间分布。",
    ),
    "bader_charge": (
        "确认密度文件的精度适合 Bader 分区。",
        "准备总密度和批准的参考密度。",
        "确认分区输出完整且来源明确。",
        "检查电荷积分完整性和单位。",
        "将原子编号映射到材料、元素和界面区域。",
        "计算原子或组分的电荷变化。",
        "整理获得/失去电子量表格。",
        "上传表格，分析净转移及其与 CDD 的一致性。",
    ),
    "dos_pdos": (
        "确认 SCF、NSCF 及 DOS/PDOS 后处理均完成。",
        "核对 k 点、展宽、能量范围和投影选择。",
        "提取总 DOS 及目标元素、原子或轨道 PDOS。",
        "统一费米能级或批准的能量零点。",
        "确认自旋上下数据的符号约定。",
        "提取带隙、近费米态密度、峰位和轨道贡献。",
        "整理不同体系关键参数对比表。",
        "上传能量—态密度数据或参数表，分析态变化来源。",
    ),
    "cohp": (
        "确认主电子结构和投影分析均完成。",
        "检查投影质量、电荷泄漏和能带数量。",
        "确认目标原子对及编号。",
        "提取 COHP、ICOHP、费米能级和键长。",
        "统一成键/反键符号约定。",
        "比较关键原子对的积分值和能量分布。",
        "整理原子对、键长、ICOHP 和成键区间。",
        "上传表格和必要数据，分析界面成键性质。",
    ),
    "qtaim": (
        "确认波函数或电子密度适用于 QTAIM。",
        "确认拓扑搜索完成且输出完整。",
        "核对键路径连接目标原子。",
        "提取密度、拉普拉斯、能量密度等批准参数。",
        "检查临界点类型和拓扑关系。",
        "比较不同体系或原子对的拓扑参数。",
        "整理键临界点参数表。",
        "上传表格，分析相互作用性质和证据边界。",
    ),
    "approved_other": (
        "确认目标计算及依赖任务真实完成。",
        "核对实际参数与批准方案。",
        "提取科学问题所需的目标数据。",
        "统一单位、参照、映射和坐标基准。",
        "按批准定义完成必要处理。",
        "检查方法、模型和数值可比性。",
        "整理可追溯的标准数据表。",
        "上传处理结果，进行定向结论分析。",
    ),
}


class AnalysisError(RuntimeError):
    """Raise for user-correctable stage-3 workflow errors."""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def false_execution_flags() -> dict[str, bool]:
    return {key: False for key in sorted(EXECUTION_FLAG_NAMES)}


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


def file_record(path: Path, **extra: Any) -> dict[str, Any]:
    return {
        "path": str(path.resolve()),
        "sha256": sha256(path),
        "size_bytes": path.stat().st_size,
        **extra,
    }


def safe_name(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", value.strip())
    return cleaned.strip("._") or "item"


def stable_id(value: Any, label: str) -> str:
    raw = str(value or "").strip()
    if not raw or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}", raw):
        raise AnalysisError(f"{label} must be a nonempty safe identifier.")
    return raw


def source_reference_id(value: Any, label: str) -> str:
    raw = str(value or "").strip()
    if not raw or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,191}", raw):
        raise AnalysisError(f"{label} must be a nonempty safe source identifier.")
    return raw


def safe_relative_path(root: Path, raw_path: str) -> Path:
    candidate = Path(unquote(raw_path.replace("\\", "/")))
    if candidate.is_absolute() or any(part in {"", ".", ".."} for part in candidate.parts):
        raise AnalysisError("Unsafe relative path.")
    root_resolved = root.resolve()
    target = (root_resolved / candidate).resolve()
    if target != root_resolved and root_resolved not in target.parents:
        raise AnalysisError("Path escapes results_analysis.")
    return target


def version_number(paths: list[Path], prefix: str) -> int:
    values: list[int] = []
    for path in paths:
        match = re.search(re.escape(prefix) + r"v(\d{3,})", path.stem)
        if match:
            values.append(int(match.group(1)))
    return max(values, default=0) + 1


def next_root_version(root: Path, prefix: str) -> str:
    return f"v{version_number(list(root.glob(prefix + 'v*.json')), prefix):03d}"


def next_named_version(directory: Path, identifier: str, suffix: str) -> str:
    prefix = f"{safe_name(identifier)}_{suffix}_"
    return f"v{version_number(list(directory.glob(prefix + 'v*.json')), prefix):03d}"


def status_path(analysis_dir: Path) -> Path:
    return analysis_dir / "processing_status.json"


def change_log_path(analysis_dir: Path) -> Path:
    return analysis_dir / "analysis_change_log.json"


def append_log(analysis_dir: Path, entry: dict[str, Any]) -> None:
    path = change_log_path(analysis_dir)
    records = read_json(path) if path.is_file() else []
    if not isinstance(records, list):
        raise AnalysisError("analysis_change_log.json must contain a list.")
    records.append({**entry, "recorded_at": utc_now()})
    write_json(path, records)


def ensure_false_flags(value: Any, label: str = "payload") -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            if key in EXECUTION_FLAG_NAMES and item is not False:
                raise AnalysisError(f"{label}.{key} must remain false.")
            lower = str(key).lower()
            if any(token in lower for token in ("plot", "figure", "chart", "visualization")) and item not in (False, None, "", []):
                raise AnalysisError(f"{label}.{key} requests a plot or figure, outside stage 3.")
            ensure_false_flags(item, f"{label}.{key}")
    elif isinstance(value, list):
        for index, item in enumerate(value):
            ensure_false_flags(item, f"{label}[{index}]")


def verify_file_record(record: Any, label: str) -> Path:
    if not isinstance(record, dict):
        raise AnalysisError(f"{label} is not a file record.")
    path = Path(str(record.get("path", "")))
    if not path.is_file() or sha256(path) != str(record.get("sha256", "")):
        raise AnalysisError(f"Frozen file changed or disappeared: {label}")
    return path


def analysis_asset_path() -> Path:
    return Path(__file__).resolve().parent.parent / "assets" / "result_review.html"


def ensure_review_html(analysis_dir: Path) -> None:
    asset = analysis_asset_path()
    if not asset.is_file():
        raise AnalysisError("The stage-3 result-review asset is missing.")
    target = analysis_dir / "result_review.html"
    if not target.exists() or sha256(target) != sha256(asset):
        write_bytes(target, asset.read_bytes())


def verify_stage1_sources(planning_dir: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    paths = {
        "stage1_status": planning_dir / "stage1_status.json",
        "stage1_plan": planning_dir / "stage1_plan_approved.json",
        "stage1_markdown": planning_dir / "stage1_plan_approved.md",
    }
    missing = [name for name, path in paths.items() if not path.is_file()]
    if missing:
        raise AnalysisError("Stage-1 approved baseline is incomplete: " + ", ".join(missing))
    status = read_json(paths["stage1_status"])
    plan = read_json(paths["stage1_plan"])
    if not isinstance(status, dict) or status.get("status") != "APPROVED":
        raise AnalysisError("Stage 1 must be APPROVED before stage 3.")
    if not isinstance(plan, dict) or str(plan.get("project_id", "")) != str(status.get("project_id", "")):
        raise AnalysisError("Stage-1 status and approved plan project IDs differ.")
    if not isinstance(plan.get("evidence_chain"), list) or not plan.get("evidence_chain"):
        raise AnalysisError("The approved stage-1 evidence chain must exist before stage 3.")
    records = [
        file_record(path, source_name=name, source_kind="stage1_immutable")
        for name, path in paths.items()
    ]
    return plan, records


def graph_task_map(graph: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        str(item.get("task_id")): item
        for item in graph.get("nodes", [])
        if isinstance(item, dict) and item.get("task_id")
    }


def graph_evidence_map(graph: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        str(item.get("id")): item
        for item in graph.get("evidence_nodes", [])
        if isinstance(item, dict) and item.get("id")
    }


def accepted_task_ids(graph: dict[str, Any]) -> list[str]:
    accepted = {
        str(item.get("task_id"))
        for item in graph.get("nodes", [])
        if isinstance(item, dict) and item.get("status") == "accepted"
    }
    accepted.update(str(item) for item in graph.get("completed_task_ids", []))
    return sorted(item for item in accepted if item)


def verify_formal_sources(formal_dir: Path, project_id: Any) -> tuple[dict[str, Any], dict[str, Any], list[dict[str, Any]]]:
    graph_path = formal_dir / "formal_task_graph.json"
    projection_path = formal_dir / "formal_result_status.json"
    missing = [path.name for path in (graph_path, projection_path) if not path.is_file()]
    if missing:
        raise AnalysisError("Formal result sources are incomplete: " + ", ".join(missing))
    graph = read_json(graph_path)
    projection = read_json(projection_path)
    if not isinstance(graph, dict) or not isinstance(projection, dict):
        raise AnalysisError("Formal graph and result projection must be JSON objects.")
    if str(graph.get("project_id", "")) != str(project_id) or str(projection.get("project_id", "")) != str(project_id):
        raise AnalysisError("Formal sources and stage-1 project IDs differ.")
    if not isinstance(graph.get("evidence_nodes"), list) or not graph.get("evidence_nodes"):
        raise AnalysisError("The formal task graph does not contain the approved evidence chain.")
    accepted = accepted_task_ids(graph)
    returned_current = (
        projection.get("status") in FORMAL_REAL_RESULT_STATES
        and bool(projection.get("latest_result_version"))
    )
    if not accepted and not returned_current:
        raise AnalysisError("No formal task currently has a real returned or accepted result for stage-3 analysis.")
    records = [
        file_record(graph_path, source_name="formal_task_graph", source_kind="formal_current"),
        file_record(projection_path, source_name="formal_result_status", source_kind="formal_current"),
    ]
    return graph, projection, records


def source_snapshot(
    planning_dir: Path,
    formal_dir: Path,
    version: str,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    plan, stage1_records = verify_stage1_sources(planning_dir)
    graph, projection, formal_records = verify_formal_sources(formal_dir, plan.get("project_id"))
    snapshot = {
        "snapshot_version": version,
        "project_id": plan.get("project_id"),
        "planning_dir": str(planning_dir.resolve()),
        "formal_dir": str(formal_dir.resolve()),
        "records": stage1_records + formal_records,
        "accepted_task_ids": accepted_task_ids(graph),
        "formal_completed_evidence_node_ids": sorted(str(item) for item in graph.get("completed_evidence_node_ids", [])),
        "formal_result_status": projection.get("status"),
        "formal_latest_result_version": projection.get("latest_result_version"),
        "captured_at": utc_now(),
    }
    return plan, graph, snapshot


def save_source_snapshot(analysis_dir: Path, snapshot: dict[str, Any], plan: dict[str, Any], graph: dict[str, Any]) -> dict[str, Any]:
    version = str(snapshot["snapshot_version"])
    path = analysis_dir / "source_snapshots" / f"source_snapshot_{version}.json"
    payload = {
        **snapshot,
        "stage1_evidence_chain": copy.deepcopy(plan.get("evidence_chain", [])),
        "formal_nodes": copy.deepcopy(graph.get("nodes", [])),
        "formal_evidence_nodes": copy.deepcopy(graph.get("evidence_nodes", [])),
    }
    write_json(path, payload)
    return file_record(path, source_name="stage3_source_snapshot", source_kind="stage3_history")


def verify_source_snapshot(status: dict[str, Any], stage1_only: bool = False) -> None:
    snapshot = status.get("source_snapshot")
    if not isinstance(snapshot, dict):
        raise AnalysisError("Source snapshot is missing from processing state.")
    for index, record in enumerate(snapshot.get("records", [])):
        if not isinstance(record, dict):
            raise AnalysisError(f"source_snapshot.records[{index}] is invalid.")
        if stage1_only and record.get("source_kind") != "stage1_immutable":
            continue
        verify_file_record(record, f"source snapshot record {record.get('source_name', index)}")
    if status.get("source_snapshot_record"):
        verify_file_record(status["source_snapshot_record"], "stage-3 source snapshot history")


def load_status(analysis_dir: Path, verify_sources: bool = True, stage1_only: bool = False) -> dict[str, Any]:
    path = status_path(analysis_dir)
    if not path.is_file():
        raise AnalysisError("processing_status.json is missing; start stage 3 first.")
    status = read_json(path)
    if not isinstance(status, dict) or status.get("status") not in VALID_STATES:
        raise AnalysisError(f"Unknown stage-3 state: {status.get('status')!r}")
    for key in EXECUTION_FLAG_NAMES:
        if status.get(key) is not False:
            raise AnalysisError(f"Protected execution flag changed: {key}")
    if verify_sources:
        verify_source_snapshot(status, stage1_only=stage1_only)
    return status


def write_status(analysis_dir: Path, status: dict[str, Any]) -> None:
    status.update(false_execution_flags())
    status["updated_at"] = utc_now()
    write_json(status_path(analysis_dir), status)


def required_evidence_node_ids(status: dict[str, Any]) -> list[str]:
    source_path = verify_file_record(status["source_snapshot_record"], "stage-3 source snapshot history")
    snapshot = read_json(source_path)
    return sorted(
        str(item.get("id"))
        for item in snapshot.get("formal_evidence_nodes", [])
        if isinstance(item, dict) and item.get("required") is True and item.get("id")
    )


def start(
    analysis_dir: Path,
    planning_dir: Path,
    formal_dir: Path,
    user_data_status: str | None,
) -> dict[str, Any]:
    if status_path(analysis_dir).exists():
        raise AnalysisError("Stage 3 is already initialized; use status or sync-sources.")
    if user_data_status is not None and user_data_status not in DATA_STATUS_MAP:
        raise AnalysisError("user_data_status must be raw, partial, processed, tutorial, or resume.")
    analysis_dir.mkdir(parents=True, exist_ok=True)
    for name in (
        "user_raw_results",
        "user_processed_data",
        "processing_guides",
        "processing_progress",
        "validated_data",
        "rejected_data",
        "evidence_analysis",
        "experiment_comparison",
        "source_snapshots",
    ):
        (analysis_dir / name).mkdir(exist_ok=True)
    plan, graph, snapshot = source_snapshot(planning_dir, formal_dir, "v001")
    snapshot_record = save_source_snapshot(analysis_dir, snapshot, plan, graph)
    state = WAITING_FOR_USER_DATA_STATUS if user_data_status is None else DATA_STATUS_MAP[user_data_status]
    status = {
        "project_id": plan.get("project_id"),
        "workflow_step": "stage3_data_processing_and_evidence_validation",
        "status": state,
        "user_data_status": user_data_status,
        "source_snapshot": snapshot,
        "source_snapshot_record": snapshot_record,
        "source_snapshot_history": [snapshot_record],
        "dataset_records": [],
        "latest_dataset_by_id": {},
        "progress_records": {},
        "guide_records": [],
        "validation_records": [],
        "analysis_records": [],
        "approval_records": [],
        "validated_evidence_node_ids": [],
        "overall_stage_complete": False,
        "pending_information": [],
        "initial_question_required": user_data_status is None,
        **false_execution_flags(),
        "created_at": utc_now(),
    }
    write_status(analysis_dir, status)
    write_json(change_log_path(analysis_dir), [])
    ensure_review_html(analysis_dir)
    append_log(analysis_dir, {"event": "stage3_started", "state": state, "user_data_status": user_data_status})
    return {
        "status": state,
        "message": INITIAL_QUESTION if user_data_status is None else "用户数据状态已记录，不重复询问初始分类。",
        "accepted_formal_task_ids": snapshot["accepted_task_ids"],
        "formal_completed_evidence_node_ids": snapshot["formal_completed_evidence_node_ids"],
        "overall_stage_complete": False,
        **false_execution_flags(),
    }


def sync_sources(analysis_dir: Path) -> dict[str, Any]:
    status = load_status(analysis_dir, verify_sources=True, stage1_only=True)
    if status.get("status") == RESULTS_APPROVED:
        raise AnalysisError("The approved stage-3 baseline is immutable; start a separately authorized revision.")
    old = status["source_snapshot"]
    version = f"v{int(str(old.get('snapshot_version', 'v000'))[1:]) + 1:03d}"
    planning_dir = Path(str(old.get("planning_dir", "")))
    formal_dir = Path(str(old.get("formal_dir", "")))
    plan, graph, snapshot = source_snapshot(planning_dir, formal_dir, version)
    if str(plan.get("project_id")) != str(status.get("project_id")):
        raise AnalysisError("Cannot sync sources from a different project.")
    new_accepted = set(snapshot["accepted_task_ids"])
    prior_nodes = set(status.get("validated_evidence_node_ids", []))
    evidence_map = graph_evidence_map(graph)
    for node_id in prior_nodes:
        node = evidence_map.get(str(node_id))
        if not node or not set(str(item) for item in node.get("task_ids", [])) & new_accepted:
            raise AnalysisError(f"Source sync would invalidate previously accepted evidence node {node_id}.")
    snapshot_record = save_source_snapshot(analysis_dir, snapshot, plan, graph)
    status["source_snapshot"] = snapshot
    status["source_snapshot_record"] = snapshot_record
    status.setdefault("source_snapshot_history", []).append(snapshot_record)
    write_status(analysis_dir, status)
    append_log(
        analysis_dir,
        {
            "event": "formal_sources_synced",
            "from": old.get("snapshot_version"),
            "to": version,
            "accepted_task_ids": snapshot["accepted_task_ids"],
        },
    )
    return snapshot


def current_source_payload(status: dict[str, Any]) -> dict[str, Any]:
    path = verify_file_record(status["source_snapshot_record"], "stage-3 source snapshot history")
    value = read_json(path)
    if not isinstance(value, dict):
        raise AnalysisError("Source snapshot payload is invalid.")
    return value


def require_task_and_type(status: dict[str, Any], task_id: Any, data_type: Any) -> tuple[str, str]:
    task = stable_id(task_id, "task_id")
    kind = str(data_type or "").strip()
    if kind not in DATA_TYPES:
        raise AnalysisError("Unsupported data_type.")
    source = current_source_payload(status)
    tasks = graph_task_map({"nodes": source.get("formal_nodes", [])})
    if task not in tasks:
        raise AnalysisError(f"Unknown formal task ID: {task}")
    return task, kind


def normalize_steps(value: Any, label: str) -> list[int]:
    if not isinstance(value, list):
        raise AnalysisError(f"{label} must be a list.")
    steps: list[int] = []
    for item in value:
        if isinstance(item, bool) or not isinstance(item, int) or item < 1 or item > 8:
            raise AnalysisError(f"{label} may contain only integers 1 through 8.")
        steps.append(item)
    return sorted(set(steps))


def update_progress_value(analysis_dir: Path, status: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
    if status.get("status") == RESULTS_APPROVED:
        raise AnalysisError("Stage-3 results are approved and immutable.")
    ensure_false_flags(payload)
    dataset_id = stable_id(payload.get("dataset_id"), "dataset_id")
    task_id, data_type = require_task_and_type(status, payload.get("task_id"), payload.get("data_type"))
    marker = str(payload.get("user_marker", "")).strip()
    if marker not in PROGRESS_MARKERS:
        raise AnalysisError("Unknown user progress marker.")
    current_step = payload.get("current_step")
    if current_step is not None and (isinstance(current_step, bool) or not isinstance(current_step, int) or not 1 <= current_step <= 8):
        raise AnalysisError("current_step must be null or an integer from 1 through 8.")
    completed = normalize_steps(payload.get("completed_steps", []), "completed_steps")
    reopened = normalize_steps(payload.get("reopened_steps", []), "reopened_steps")
    previous_record = status.get("progress_records", {}).get(dataset_id)
    previous: dict[str, Any] = {}
    if previous_record:
        previous_path = verify_file_record(previous_record, f"progress record for {dataset_id}")
        previous = read_json(previous_path)
        old_completed = set(previous.get("completed_steps", []))
        if not old_completed.issubset(completed):
            raise AnalysisError("Completed processing steps are monotonic and cannot be removed.")
        if str(previous.get("task_id")) != task_id or str(previous.get("data_type")) != data_type:
            raise AnalysisError("A dataset's task ID and data type cannot change through progress updates.")
    if set(reopened) - set(completed):
        raise AnalysisError("A reopened step must previously be listed as completed; preserve it while recording the issue.")
    if marker == "正在进行第几步" and current_step is None:
        raise AnalysisError("The current-step marker requires current_step.")
    if marker == "处理已完成" and completed != list(range(1, 9)):
        raise AnalysisError("Processing may be marked complete only after all eight common steps are completed.")
    if current_step and any(step >= current_step for step in completed if step not in reopened):
        raise AnalysisError("Completed steps should precede the current step unless explicitly reopened.")
    progress_state = (
        "PROCESSED_DATA_RECEIVED"
        if marker == "处理已完成"
        else f"USER_PROCESSING_STEP_{current_step}"
        if current_step
        else "RAW_RESULT_RECEIVED"
        if marker == "该数据尚未处理"
        else "PROCESSING_TUTORIAL_PROVIDED"
        if marker == "需要步骤指导"
        else "USER_PROCESSING_IN_PROGRESS"
    )
    directory = analysis_dir / "processing_progress"
    version = next_named_version(directory, dataset_id, "progress")
    record = {
        "project_id": status.get("project_id"),
        "dataset_id": dataset_id,
        "task_id": task_id,
        "data_type": data_type,
        "progress_state": progress_state,
        "current_step": current_step,
        "completed_steps": completed,
        "reopened_steps": reopened,
        "user_marker": marker,
        "notes": str(payload.get("notes", "")).strip(),
        "version": version,
        "previous_version": previous.get("version"),
        "recorded_at": utc_now(),
        **false_execution_flags(),
    }
    path = directory / f"{safe_name(dataset_id)}_progress_{version}.json"
    write_json(path, record)
    record_file = file_record(path, dataset_id=dataset_id, version=version)
    status.setdefault("progress_records", {})[dataset_id] = record_file
    if marker == "需要步骤指导":
        status["status"] = PROCESSING_GUIDE_REQUIRED
    elif marker == "处理已完成":
        status["status"] = PROCESSED_DATA_RECEIVED
    else:
        status["status"] = USER_PROCESSING_IN_PROGRESS
    write_status(analysis_dir, status)
    append_log(analysis_dir, {"event": "processing_progress_recorded", "dataset_id": dataset_id, "version": version, "marker": marker})
    return record


def update_progress(analysis_dir: Path, source_path: Path) -> dict[str, Any]:
    status = load_status(analysis_dir)
    if status.get("status") == RESULTS_APPROVED:
        raise AnalysisError("Stage-3 results are approved and immutable.")
    payload = read_json(source_path)
    if not isinstance(payload, dict):
        raise AnalysisError("Progress submission must be a JSON object.")
    return update_progress_value(analysis_dir, status, payload)


def generic_step_details(number: int, summary: str) -> dict[str, Any]:
    generic = (
        ("确认任务输出可作为处理起点", "实际输入、主输出、错误日志和依赖输出", "结束/收敛/文件完整性记录", "目标任务与依赖均真实完成；未知项明确标记"),
        ("确认数据与批准方法一致", "实际输入与第一阶段批准方案", "参数差异表", "关键理论设置一致或差异已重新确认"),
        ("提取当前科学问题需要的数据", "已验证的原始输出", "带来源定位的目标数值或数据列", "没有用单一截图或转录值替代完整来源"),
        ("建立可比较的公共基准", "各体系目标数据及元数据", "统一单位、参照、编号/坐标的记录", "每个参与比较的体系使用相同定义"),
        ("按批准定义得到目标参数", "统一后的目标数据和批准公式/积分规则", "可复核的参数值及中间项", "公式项、符号和参照均完整且可追溯"),
        ("排除由方法或处理造成的伪趋势", "参数差异和处理记录", "可比性检查表", "方法、模型、结构状态和数值基准通过或限制已明确"),
        ("形成可直接审查的标准数据", "参数值、单位、来源和备注", "CSV、Excel、TXT 或 Markdown 表", "表中包含体系、模型、任务、参数、单位、参照和方法"),
        ("对证据能力和边界作出定向判断", "处理后数据及可比性记录", "趋势、含义、佐证、强度和下一步判断", "结论不超过当前数据的证据角色"),
    )[number - 1]
    return {
        "step": number,
        "title": STEP_TITLES[number - 1],
        "summary": summary,
        "purpose": generic[0],
        "input": generic[1],
        "output": generic[2],
        "pass_standard": generic[3],
    }


def guide_steps(data_type: str) -> list[dict[str, Any]]:
    selected = data_type if data_type in TASK_STEP_SUMMARIES else "approved_other"
    return [generic_step_details(index, summary) for index, summary in enumerate(TASK_STEP_SUMMARIES[selected], start=1)]


def render_guide_markdown(guide: dict[str, Any]) -> str:
    lines = [
        f"# 数据处理指导：{guide['dataset_id']} / {guide['data_type']}",
        "",
        f"- 任务：`{guide['task_id']}`",
        f"- 模式：`{guide['mode']}`",
        f"- 版本：`{guide['version']}`",
        "",
    ]
    for item in guide["steps"]:
        lines.extend(
            [
                f"## 第 {item['step']} 步：{item['title']}",
                "",
                item["summary"],
                "",
                f"- 目的：{item['purpose']}",
                f"- 输入：{item['input']}",
                f"- 输出：{item['output']}",
                f"- 通过标准：{item['pass_standard']}",
                "",
            ]
        )
    if guide.get("direct_dependencies"):
        lines.extend(["## 直接前后依赖", "", json.dumps(guide["direct_dependencies"], ensure_ascii=False, indent=2), ""])
    if guide.get("followup_invitation"):
        lines.extend([guide["followup_invitation"], ""])
    lines.append("本指导不会由 Skill 自动执行，也不包含科研作图。")
    return "\n".join(lines) + "\n"


def provide_guide_value(analysis_dir: Path, status: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
    if status.get("status") == RESULTS_APPROVED:
        raise AnalysisError("Stage-3 results are approved and immutable.")
    ensure_false_flags(payload)
    dataset_id = stable_id(payload.get("dataset_id"), "dataset_id")
    task_id, data_type = require_task_and_type(status, payload.get("task_id"), payload.get("data_type"))
    if data_type in {"geometry", "molecular_dynamics"}:
        data_type = "approved_other"
    mode = str(payload.get("mode", "")).strip()
    if mode not in {"full", "step"}:
        raise AnalysisError("Guide mode must be full or step.")
    all_steps = guide_steps(data_type)
    requested_step = payload.get("step")
    dependencies: dict[str, Any] = {}
    if mode == "step":
        if isinstance(requested_step, bool) or not isinstance(requested_step, int) or not 1 <= requested_step <= 8:
            raise AnalysisError("Step guide requires an integer step from 1 through 8.")
        steps = [all_steps[requested_step - 1]]
        if requested_step > 1:
            dependencies["previous"] = {key: all_steps[requested_step - 2][key] for key in ("step", "title", "pass_standard")}
        if requested_step < 8:
            dependencies["next"] = {key: all_steps[requested_step][key] for key in ("step", "title", "purpose")}
    else:
        requested_step = None
        steps = all_steps
    directory = analysis_dir / "processing_guides"
    version = next_named_version(directory, f"{dataset_id}_{data_type}", "guide")
    guide = {
        "project_id": status.get("project_id"),
        "dataset_id": dataset_id,
        "task_id": task_id,
        "data_type": data_type,
        "mode": mode,
        "requested_step": requested_step,
        "steps": steps,
        "direct_dependencies": dependencies,
        "followup_invitation": FOLLOWUP_INVITATION if mode == "full" else "",
        "user_context": str(payload.get("user_context", "")).strip(),
        "instructions_executed_by_skill": False,
        "figures_required": False,
        "version": version,
        "generated_at": utc_now(),
        **false_execution_flags(),
    }
    stem = f"{safe_name(dataset_id)}_{safe_name(data_type)}_guide_{version}"
    json_path = directory / f"{stem}.json"
    md_path = directory / f"{stem}.md"
    write_json(json_path, guide)
    write_text(md_path, render_guide_markdown(guide))
    record = {
        "dataset_id": dataset_id,
        "task_id": task_id,
        "data_type": data_type,
        "mode": mode,
        "requested_step": requested_step,
        "version": version,
        "json": file_record(json_path),
        "markdown": file_record(md_path),
    }
    status.setdefault("guide_records", []).append(record)
    status["status"] = PROCESSING_GUIDE_PROVIDED
    write_status(analysis_dir, status)
    append_log(analysis_dir, {"event": "processing_guide_provided", "dataset_id": dataset_id, "data_type": data_type, "mode": mode, "step": requested_step, "version": version})
    return guide


def provide_guide(analysis_dir: Path, source_path: Path) -> dict[str, Any]:
    status = load_status(analysis_dir)
    if status.get("status") == RESULTS_APPROVED:
        raise AnalysisError("Stage-3 results are approved and immutable.")
    payload = read_json(source_path)
    if not isinstance(payload, dict):
        raise AnalysisError("Guide request must be a JSON object.")
    return provide_guide_value(analysis_dir, status, payload)


def inspect_csv(path: Path) -> dict[str, Any]:
    sample = path.read_text(encoding="utf-8-sig", errors="replace")[:131072]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",\t;")
        delimiter = dialect.delimiter
    except csv.Error:
        delimiter = "\t" if "\t" in sample else ","
    rows = list(csv.reader(sample.splitlines(), delimiter=delimiter))
    header = rows[0] if rows else []
    return {
        "kind": "delimited_text",
        "delimiter": "tab" if delimiter == "\t" else delimiter,
        "header": header[:100],
        "sample_row_count": max(0, len(rows) - 1),
        "truncated_inspection": path.stat().st_size > len(sample.encode("utf-8", errors="ignore")),
    }


def inspect_xlsx(path: Path) -> dict[str, Any]:
    result: dict[str, Any] = {"kind": "xlsx", "worksheets": []}
    try:
        with zipfile.ZipFile(path) as archive:
            workbook = ElementTree.fromstring(archive.read("xl/workbook.xml"))
            namespace = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
            names = [item.attrib.get("name", "") for item in workbook.findall(".//m:sheet", namespace)]
            result["worksheets"] = names
            dimensions: list[str] = []
            for member in sorted(name for name in archive.namelist() if re.fullmatch(r"xl/worksheets/sheet\d+\.xml", name)):
                root = ElementTree.fromstring(archive.read(member))
                dimension = root.find("m:dimension", namespace)
                dimensions.append(dimension.attrib.get("ref", "") if dimension is not None else "")
            result["dimensions"] = dimensions
    except (KeyError, zipfile.BadZipFile, ElementTree.ParseError) as exc:
        result["format_error"] = str(exc)
    return result


def inspect_file(path: Path) -> dict[str, Any]:
    suffix = path.suffix.lower()
    mime = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    base: dict[str, Any] = {"extension": suffix, "mime_type": mime, "size_bytes": path.stat().st_size}
    if suffix in {".csv", ".tsv"}:
        return {**base, **inspect_csv(path)}
    if suffix == ".xlsx":
        return {**base, **inspect_xlsx(path)}
    if suffix == ".json":
        try:
            value = read_json(path)
            return {
                **base,
                "kind": "json",
                "top_level_type": type(value).__name__,
                "top_level_keys": list(value)[:100] if isinstance(value, dict) else [],
                "item_count": len(value) if isinstance(value, (dict, list)) else None,
            }
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            return {**base, "kind": "json", "format_error": str(exc)}
    if suffix in {".txt", ".md", ".dat", ".out", ".log"} or mime.startswith("text/"):
        raw = path.read_bytes()[:262144]
        text_value = raw.decode("utf-8", errors="replace")
        return {
            **base,
            "kind": "text",
            "sample_line_count": len(text_value.splitlines()),
            "preview": text_value[:1000],
            "truncated_inspection": path.stat().st_size > len(raw),
        }
    return {**base, "kind": "binary_or_unparsed"}


def resolve_manifest_source(manifest_path: Path | None, raw_path: Any) -> Path:
    value = str(raw_path or "").strip()
    if not value:
        raise AnalysisError("Every file entry requires path.")
    candidate = Path(value)
    if not candidate.is_absolute():
        if manifest_path is None:
            raise AnalysisError("Browser/API ingestion requires absolute source paths.")
        candidate = manifest_path.parent / candidate
    candidate = candidate.resolve()
    if not candidate.is_file():
        raise AnalysisError(f"Uploaded source file is missing: {candidate}")
    return candidate


def next_dataset_version(analysis_dir: Path, data_stage: str, dataset_id: str) -> str:
    parent = analysis_dir / ("user_raw_results" if data_stage == "raw" else "user_processed_data")
    prefix = safe_name(dataset_id) + "_v"
    values: list[int] = []
    for item in parent.glob(prefix + "*"):
        match = re.fullmatch(re.escape(prefix) + r"(\d{3,})", item.name)
        if match:
            values.append(int(match.group(1)))
    return f"v{max(values, default=0) + 1:03d}"


def validate_evidence_node_links(status: dict[str, Any], task_id: str, raw_ids: Any) -> list[str]:
    if not isinstance(raw_ids, list):
        raise AnalysisError("evidence_node_ids must be a list.")
    source = current_source_payload(status)
    evidence = graph_evidence_map({"evidence_nodes": source.get("formal_evidence_nodes", [])})
    output: list[str] = []
    for value in raw_ids:
        node_id = stable_id(value, "evidence_node_id")
        node = evidence.get(node_id)
        if node is None:
            raise AnalysisError(f"Unknown evidence node ID: {node_id}")
        if task_id not in {str(item) for item in node.get("task_ids", [])}:
            raise AnalysisError(f"Task {task_id} is not linked to evidence node {node_id}.")
        output.append(node_id)
    return sorted(set(output))


def verify_dataset_record(record: Any, label: str) -> dict[str, Any]:
    path = verify_file_record(record, label)
    manifest = read_json(path)
    if not isinstance(manifest, dict):
        raise AnalysisError(f"{label} does not point to a dataset manifest.")
    for index, item in enumerate(manifest.get("files", [])):
        verify_file_record(item, f"{label} file {index + 1}")
    return manifest


def ingest_dataset_value(
    analysis_dir: Path,
    status: dict[str, Any],
    payload: dict[str, Any],
    manifest_path: Path | None,
) -> dict[str, Any]:
    if status.get("status") == RESULTS_APPROVED:
        raise AnalysisError("Stage-3 results are approved and immutable.")
    ensure_false_flags(payload)
    dataset_id = stable_id(payload.get("dataset_id"), "dataset_id")
    task_id, data_type = require_task_and_type(status, payload.get("task_id"), payload.get("data_type"))
    evidence_node_ids = validate_evidence_node_links(status, task_id, payload.get("evidence_node_ids", []))
    data_stage = str(payload.get("data_stage", "")).strip()
    if data_stage not in DATA_STAGES:
        raise AnalysisError("data_stage must be raw, partial, or processed.")
    files = payload.get("files", [])
    key_values = payload.get("key_values", [])
    if not isinstance(files, list) or not isinstance(key_values, list) or (not files and not key_values):
        raise AnalysisError("A dataset requires at least one actual file or key value.")
    metadata = payload.get("metadata", {})
    if not isinstance(metadata, dict):
        raise AnalysisError("metadata must be an object.")
    unknown_metadata = sorted(set(metadata) - METADATA_FIELDS)
    if unknown_metadata:
        raise AnalysisError("Unknown metadata fields: " + ", ".join(unknown_metadata))
    if "completed_steps" in metadata:
        metadata["completed_steps"] = normalize_steps(metadata["completed_steps"], "metadata.completed_steps")
    version = next_dataset_version(analysis_dir, data_stage, dataset_id)
    parent = analysis_dir / ("user_raw_results" if data_stage == "raw" else "user_processed_data")
    target_dir = parent / f"{safe_name(dataset_id)}_{version}"
    if target_dir.exists():
        raise AnalysisError("Dataset target version already exists.")
    target_dir.mkdir(parents=True)
    stored_files: list[dict[str, Any]] = []
    seen_names: set[str] = set()
    try:
        for index, item in enumerate(files, start=1):
            if not isinstance(item, dict):
                raise AnalysisError(f"files[{index - 1}] must be an object.")
            role = str(item.get("role", "")).strip()
            if role not in FILE_ROLES:
                raise AnalysisError(f"Unsupported file role: {role}")
            source_path = resolve_manifest_source(manifest_path, item.get("path"))
            filename = safe_name(source_path.name)
            if filename in seen_names:
                filename = f"{index:03d}_{filename}"
            seen_names.add(filename)
            target = target_dir / filename
            shutil.copy2(source_path, target)
            stored_files.append(
                file_record(
                    target,
                    file_id=f"{dataset_id}:F{index:03d}",
                    role=role,
                    system_id=str(item.get("system_id", "")).strip(),
                    description=str(item.get("description", "")).strip(),
                    original_name=source_path.name,
                    format_inspection=inspect_file(target),
                )
            )
        normalized_values: list[dict[str, Any]] = []
        for index, item in enumerate(key_values, start=1):
            if not isinstance(item, dict) or not str(item.get("parameter", "")).strip():
                raise AnalysisError(f"key_values[{index - 1}] requires parameter.")
            normalized_values.append(
                {
                    "key_value_id": f"{dataset_id}:K{index:03d}",
                    "parameter": str(item.get("parameter", "")).strip(),
                    "value": item.get("value"),
                    "unit": str(item.get("unit", "")).strip(),
                    "system_id": str(item.get("system_id", "")).strip(),
                    "reference_definition": str(item.get("reference_definition", "")).strip(),
                    "source_description": str(item.get("source_description", "")).strip(),
                }
            )
        image_only = bool(stored_files) and all(item.get("role") == "image" for item in stored_files) and not normalized_values
        single_value_only = not stored_files and len(normalized_values) == 1
        dataset = {
            "project_id": status.get("project_id"),
            "dataset_id": dataset_id,
            "dataset_version": version,
            "task_id": task_id,
            "evidence_node_ids": evidence_node_ids,
            "data_type": data_type,
            "data_stage": data_stage,
            "files": stored_files,
            "key_values": normalized_values,
            "metadata": copy.deepcopy(metadata),
            "current_step": payload.get("current_step"),
            "user_notes": str(payload.get("user_notes", "")).strip(),
            "image_only": image_only,
            "single_value_only": single_value_only,
            "quantitative_acceptance_blocked": image_only and data_type in {"charge_density_difference", "dos_pdos"},
            "source_snapshot_version": status["source_snapshot"]["snapshot_version"],
            "ingested_at": utc_now(),
            **false_execution_flags(),
        }
        manifest_target = target_dir / "dataset_manifest.json"
        write_json(manifest_target, dataset)
    except Exception:
        shutil.rmtree(target_dir, ignore_errors=True)
        raise
    record = file_record(
        manifest_target,
        dataset_id=dataset_id,
        dataset_version=version,
        task_id=task_id,
        data_type=data_type,
        data_stage=data_stage,
    )
    status.setdefault("dataset_records", []).append(record)
    status.setdefault("latest_dataset_by_id", {})[dataset_id] = record
    status["status"] = RAW_DATA_RECEIVED if data_stage == "raw" else USER_PROCESSING_IN_PROGRESS if data_stage == "partial" else PROCESSED_DATA_RECEIVED
    status["initial_question_required"] = False
    status["user_data_status"] = data_stage
    write_status(analysis_dir, status)
    append_log(analysis_dir, {"event": "dataset_ingested", "dataset_id": dataset_id, "dataset_version": version, "data_stage": data_stage, "task_id": task_id})
    if payload.get("current_step") is not None or "completed_steps" in metadata:
        current_status = load_status(analysis_dir)
        reported_completed = set(metadata.get("completed_steps", []))
        previous_completed: set[int] = set()
        previous_record = current_status.get("progress_records", {}).get(dataset_id)
        if previous_record:
            previous_progress = read_json(verify_file_record(previous_record, f"progress record for {dataset_id}"))
            previous_completed = set(previous_progress.get("completed_steps", []))
        completed = sorted(previous_completed | reported_completed)
        reopened = sorted(previous_completed - reported_completed)
        requested_current = payload.get("current_step")
        if requested_current is None and completed != list(range(1, 9)):
            requested_current = next((step for step in range(1, 9) if step not in set(completed) or step in set(reopened)), None)
        if completed == list(range(1, 9)) and data_stage == "processed" and not reopened:
            marker = "处理已完成"
            requested_current = None
        elif requested_current is not None:
            marker = "正在进行第几步"
        else:
            marker = "数据存在疑问"
        update_progress_value(
            analysis_dir,
            current_status,
            {
                "dataset_id": dataset_id,
                "task_id": task_id,
                "data_type": data_type,
                "current_step": requested_current,
                "completed_steps": completed,
                "reopened_steps": reopened,
                "user_marker": marker,
                "notes": "由数据接收清单同步。",
            },
        )
    return dataset


def ingest_dataset(analysis_dir: Path, manifest_path: Path) -> dict[str, Any]:
    status = load_status(analysis_dir)
    if status.get("status") == RESULTS_APPROVED:
        raise AnalysisError("Stage-3 results are approved and immutable.")
    payload = read_json(manifest_path)
    if not isinstance(payload, dict):
        raise AnalysisError("Dataset manifest must be a JSON object.")
    return ingest_dataset_value(analysis_dir, status, payload, manifest_path)


def latest_datasets(status: dict[str, Any], dataset_ids: list[str]) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for dataset_id in dataset_ids:
        record = status.get("latest_dataset_by_id", {}).get(dataset_id)
        if not record:
            raise AnalysisError(f"No ingested dataset version exists for {dataset_id}.")
        output.append(verify_dataset_record(record, f"latest dataset {dataset_id}"))
    return output


def all_dataset_source_ids(datasets: list[dict[str, Any]]) -> set[str]:
    identifiers: set[str] = set()
    for dataset in datasets:
        identifiers.update(str(item.get("file_id")) for item in dataset.get("files", []) if item.get("file_id"))
        identifiers.update(str(item.get("key_value_id")) for item in dataset.get("key_values", []) if item.get("key_value_id"))
    return identifiers


def validate_check_group(value: Any, keys: tuple[str, ...], evidence_ids: set[str], label: str) -> dict[str, dict[str, Any]]:
    if not isinstance(value, dict):
        raise AnalysisError(f"{label} must be an object.")
    missing = [key for key in keys if key not in value]
    unknown = sorted(set(value) - set(keys))
    if missing or unknown:
        details = []
        if missing:
            details.append("missing " + ", ".join(missing))
        if unknown:
            details.append("unknown " + ", ".join(unknown))
        raise AnalysisError(f"{label} keys are invalid: " + "; ".join(details))
    output: dict[str, dict[str, Any]] = {}
    for key in keys:
        item = value[key]
        if not isinstance(item, dict) or item.get("status") not in CHECK_RESULTS:
            raise AnalysisError(f"{label}.{key} requires a valid status.")
        observation = str(item.get("observation", "")).strip()
        if not observation:
            raise AnalysisError(f"{label}.{key} requires a concrete observation.")
        refs = item.get("evidence_file_ids", [])
        if not isinstance(refs, list) or any(str(ref) not in evidence_ids for ref in refs):
            raise AnalysisError(f"{label}.{key} contains an unknown evidence file/key-value ID.")
        if item.get("status") in {"passed", "failed"} and not refs:
            raise AnalysisError(f"{label}.{key} passed/failed requires at least one source reference.")
        output[key] = {"status": item["status"], "observation": observation, "evidence_file_ids": sorted(set(str(ref) for ref in refs))}
    return output


def render_validation_markdown(record: dict[str, Any]) -> str:
    lines = [
        f"# 数据完整性与可比性检查 {record['validation_version']}",
        "",
        f"- 数据集：{', '.join(record['dataset_ids'])}",
        f"- 当前目标：{record['analysis_goal']}",
        f"- 处理范围：`{record['resolution_scope']}`",
        f"- 结论状态：`{record['resulting_state']}`",
        "",
        "## 通用处理检查",
        "",
    ]
    for key, item in record["common_checks"].items():
        lines.append(f"- `{key}` — **{item['status']}**：{item['observation']}")
    lines.extend(["", "## 可比性检查", ""])
    for key, item in record["comparability"].items():
        lines.append(f"- `{key}` — **{item['status']}**：{item['observation']}")
    lines.extend(["", "## 缺失与处理", ""])
    lines.append(f"- 阻断字段：{record['blocking_missing_fields'] or '无'}")
    lines.append(f"- 非阻断字段：{record['nonblocking_missing_fields'] or '无'}")
    lines.append(f"- 正式计算返回原因：{record['formal_return_reasons'] or '无'}")
    lines.extend(["", "本记录不包含作图，也不表示 Skill 执行了计算或后处理。", ""])
    return "\n".join(lines)


def validate_data_value(analysis_dir: Path, status: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
    if status.get("status") == RESULTS_APPROVED:
        raise AnalysisError("Stage-3 results are approved and immutable.")
    ensure_false_flags(payload)
    raw_ids = payload.get("dataset_ids")
    if not isinstance(raw_ids, list) or not raw_ids:
        raise AnalysisError("dataset_ids must be a nonempty list.")
    dataset_ids = [stable_id(item, "dataset_id") for item in raw_ids]
    if len(dataset_ids) != len(set(dataset_ids)):
        raise AnalysisError("dataset_ids must be unique.")
    datasets = latest_datasets(status, dataset_ids)
    source_ids = all_dataset_source_ids(datasets)
    analysis_goal = str(payload.get("analysis_goal", "")).strip()
    if not analysis_goal:
        raise AnalysisError("analysis_goal is required.")
    common = validate_check_group(payload.get("common_checks"), COMMON_CHECK_KEYS, source_ids, "common_checks")
    comparability = validate_check_group(payload.get("comparability"), COMPARABILITY_KEYS, source_ids, "comparability")
    required_fields = payload.get("required_for_current_judgment", [])
    if not isinstance(required_fields, list) or any(str(item) not in METADATA_FIELDS for item in required_fields):
        raise AnalysisError("required_for_current_judgment contains an unknown metadata field.")
    required_fields = sorted(set(str(item) for item in required_fields))
    nonblocking = payload.get("nonblocking_missing", {})
    if not isinstance(nonblocking, dict) or any(str(key) not in METADATA_FIELDS for key in nonblocking):
        raise AnalysisError("nonblocking_missing must map known metadata fields to rationales.")
    for key, reason in nonblocking.items():
        if not str(reason).strip():
            raise AnalysisError(f"nonblocking_missing.{key} requires a rationale.")
    missing_by_dataset: dict[str, list[str]] = {}
    checked_metadata_fields = CORE_METADATA_FIELDS | set(required_fields)
    for dataset in datasets:
        metadata = dataset.get("metadata", {})
        missing_by_dataset[str(dataset["dataset_id"])] = [
            field for field in sorted(checked_metadata_fields) if not str(metadata.get(field, "")).strip()
        ]
    all_missing = sorted(set(item for items in missing_by_dataset.values() for item in items))
    blocking_missing = sorted(field for field in required_fields if field in all_missing and field not in nonblocking)
    nonblocking_missing = {field: str(nonblocking[field]).strip() for field in all_missing if field in nonblocking}
    unresolved_checks = [
        f"common_checks.{key}"
        for key, item in common.items()
        if item["status"] in {"failed", "unknown"}
    ] + [
        f"comparability.{key}"
        for key, item in comparability.items()
        if item["status"] in {"failed", "unknown"}
    ]
    image_blocks = [str(item["dataset_id"]) for item in datasets if item.get("quantitative_acceptance_blocked")]
    if image_blocks:
        unresolved_checks.append("quantitative_data_missing_for_image_only_dataset:" + ",".join(image_blocks))
    if any(item.get("data_stage") != "processed" for item in datasets):
        unresolved_checks.append("processed_data_not_yet_received")
    scope = str(payload.get("resolution_scope", "")).strip()
    if scope not in RESOLUTION_SCOPES:
        raise AnalysisError("resolution_scope must be none, processing_only, or formal_recalculation.")
    reasons = payload.get("formal_return_reasons", [])
    if not isinstance(reasons, list) or any(str(item) not in FORMAL_RETURN_REASONS for item in reasons):
        raise AnalysisError("formal_return_reasons contains an unsupported cause.")
    reasons = sorted(set(str(item) for item in reasons))
    issues = payload.get("issues", [])
    if not isinstance(issues, list):
        raise AnalysisError("issues must be a list.")
    for index, item in enumerate(issues):
        if not isinstance(item, dict) or not str(item.get("issue", "")).strip() or not str(item.get("recommended_action", "")).strip():
            raise AnalysisError(f"issues[{index}] requires issue and recommended_action.")
    unresolved = bool(blocking_missing or unresolved_checks)
    if scope == "none" and unresolved:
        raise AnalysisError("Unresolved completeness/comparability issues require processing_only or formal_recalculation.")
    if scope != "none" and not unresolved:
        raise AnalysisError("A resolution scope is unnecessary because no blocking issue remains.")
    if scope == "formal_recalculation":
        if not reasons:
            raise AnalysisError("Formal recalculation requires at least one permitted fundamental cause.")
        issue_classes = {str(item.get("cause_class", "")) for item in issues if isinstance(item, dict)}
        repairable = {"extraction", "format", "unit_alignment", "energy_zero_alignment", "mapping", "sign_interpretation", "integration", "table_organization"}
        if issue_classes and issue_classes.issubset(repairable):
            raise AnalysisError("Repairable processing gaps cannot be routed to formal recalculation.")
        resulting_state = RETURN_TO_FORMAL_CALCULATION
    elif scope == "processing_only":
        if reasons:
            raise AnalysisError("processing_only cannot contain formal_return_reasons.")
        resulting_state = SUPPLEMENTARY_PROCESSING_REQUIRED
    else:
        if reasons:
            raise AnalysisError("resolution_scope none cannot contain formal_return_reasons.")
        resulting_state = DATA_COMPARABILITY_VALIDATED
    version = next_root_version(analysis_dir / "evidence_analysis", "data_validation_")
    record = {
        "project_id": status.get("project_id"),
        "validation_version": version,
        "dataset_ids": dataset_ids,
        "dataset_versions": {str(item["dataset_id"]): str(item["dataset_version"]) for item in datasets},
        "analysis_goal": analysis_goal,
        "required_for_current_judgment": required_fields,
        "missing_by_dataset": missing_by_dataset,
        "blocking_missing_fields": blocking_missing,
        "nonblocking_missing_fields": nonblocking_missing,
        "common_checks": common,
        "comparability": comparability,
        "unresolved_checks": unresolved_checks,
        "issues": copy.deepcopy(issues),
        "resolution_scope": scope,
        "formal_return_reasons": reasons,
        "resulting_state": resulting_state,
        "data_completeness_checked": True,
        "data_comparability_validated": resulting_state == DATA_COMPARABILITY_VALIDATED,
        "source_snapshot_version": status["source_snapshot"]["snapshot_version"],
        "recorded_at": utc_now(),
        **false_execution_flags(),
    }
    directory = analysis_dir / "evidence_analysis"
    json_path = directory / f"data_validation_{version}.json"
    md_path = directory / f"data_validation_{version}.md"
    write_json(json_path, record)
    write_text(md_path, render_validation_markdown(record))
    validation_record = {"version": version, "json": file_record(json_path), "markdown": file_record(md_path), "dataset_ids": dataset_ids, "resulting_state": resulting_state}
    status.setdefault("validation_records", []).append(validation_record)
    status["latest_validation_record"] = validation_record["json"]
    status["status"] = resulting_state
    status["pending_information"] = blocking_missing + unresolved_checks
    write_status(analysis_dir, status)
    append_log(analysis_dir, {"event": "data_completeness_and_comparability_checked", "version": version, "dataset_ids": dataset_ids, "state": resulting_state})
    return record


def validate_data(analysis_dir: Path, source_path: Path) -> dict[str, Any]:
    status = load_status(analysis_dir)
    if status.get("status") == RESULTS_APPROVED:
        raise AnalysisError("Stage-3 results are approved and immutable.")
    payload = read_json(source_path)
    if not isinstance(payload, dict):
        raise AnalysisError("Data validation submission must be a JSON object.")
    return validate_data_value(analysis_dir, status, payload)


def load_latest_validation(status: dict[str, Any]) -> dict[str, Any]:
    record = status.get("latest_validation_record")
    if not record:
        raise AnalysisError("No completeness/comparability validation exists for analysis.")
    path = verify_file_record(record, "latest data validation")
    value = read_json(path)
    if not isinstance(value, dict):
        raise AnalysisError("Latest data validation is invalid.")
    return value


def evidence_source_map(status: dict[str, Any], datasets: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    mapping: dict[str, dict[str, Any]] = {}
    for dataset in datasets:
        manifest_record = status.get("latest_dataset_by_id", {}).get(str(dataset["dataset_id"]))
        manifest_sha = str(manifest_record.get("sha256", "")) if isinstance(manifest_record, dict) else ""
        for item in dataset.get("files", []):
            mapping[str(item["file_id"])] = {
                "kind": "file",
                "dataset_id": dataset["dataset_id"],
                "sha256": item["sha256"],
                "path": item["path"],
                "role": item.get("role"),
            }
        for item in dataset.get("key_values", []):
            mapping[str(item["key_value_id"])] = {
                "kind": "key_value",
                "dataset_id": dataset["dataset_id"],
                "dataset_manifest_sha256": manifest_sha,
                "value": copy.deepcopy(item),
            }
    return mapping


def normalize_text_list(value: Any, label: str, allow_empty: bool = True) -> list[str]:
    if not isinstance(value, list):
        raise AnalysisError(f"{label} must be a list.")
    result = [str(item).strip() for item in value]
    if any(not item for item in result):
        raise AnalysisError(f"{label} cannot contain blank items.")
    if not allow_empty and not result:
        raise AnalysisError(f"{label} cannot be empty.")
    return result


def normalize_evidence_items(value: Any, source_map: dict[str, dict[str, Any]], dataset_ids: set[str]) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
    if not isinstance(value, list) or not value:
        raise AnalysisError("evidence_items must be a nonempty list.")
    records: list[dict[str, Any]] = []
    by_id: dict[str, dict[str, Any]] = {}
    for index, item in enumerate(value):
        if not isinstance(item, dict):
            raise AnalysisError(f"evidence_items[{index}] must be an object.")
        evidence_id = stable_id(item.get("evidence_id"), f"evidence_items[{index}].evidence_id")
        if evidence_id in by_id:
            raise AnalysisError(f"Duplicate evidence item ID: {evidence_id}")
        dataset_id = stable_id(item.get("dataset_id"), f"evidence_items[{index}].dataset_id")
        source_id = source_reference_id(item.get("source_id"), f"evidence_items[{index}].source_id")
        role = str(item.get("evidence_role", "")).strip()
        observation = str(item.get("observation", "")).strip()
        if dataset_id not in dataset_ids or source_id not in source_map or source_map[source_id]["dataset_id"] != dataset_id:
            raise AnalysisError(f"Evidence item {evidence_id} refers to an unknown dataset source.")
        if not role or not observation:
            raise AnalysisError(f"Evidence item {evidence_id} requires evidence_role and observation.")
        record = {
            "evidence_id": evidence_id,
            "evidence_role": role,
            "dataset_id": dataset_id,
            "source_id": source_id,
            "source_record": copy.deepcopy(source_map[source_id]),
            "observation": observation,
            "consistency": str(item.get("consistency", "")).strip(),
        }
        records.append(record)
        by_id[evidence_id] = record
    return records, by_id


def normalize_conclusions(value: Any, evidence_map: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    if not isinstance(value, list) or not value:
        raise AnalysisError("conclusions must be a nonempty list.")
    output: list[dict[str, Any]] = []
    for index, item in enumerate(value):
        if not isinstance(item, dict):
            raise AnalysisError(f"conclusions[{index}] must be an object.")
        claim = str(item.get("claim", "")).strip()
        strength = str(item.get("strength", "")).strip()
        refs = item.get("evidence_item_ids", [])
        limitations = normalize_text_list(item.get("limitations", []), f"conclusions[{index}].limitations")
        if not claim or strength not in CONCLUSION_STRENGTHS:
            raise AnalysisError(f"conclusions[{index}] requires a claim and exact strength.")
        if not isinstance(refs, list) or any(str(ref) not in evidence_map for ref in refs):
            raise AnalysisError(f"conclusions[{index}] refers to an unknown evidence item.")
        refs = sorted(set(str(ref) for ref in refs))
        if strength != "INCONCLUSIVE" and not refs:
            raise AnalysisError(f"Conclusion {index + 1} requires evidence-item references.")
        roles = {evidence_map[ref]["evidence_role"] for ref in refs}
        if strength == "STRONGLY_SUPPORTED" and len(roles) < 2:
            raise AnalysisError("STRONGLY_SUPPORTED requires at least two independent physical evidence roles.")
        output.append({"claim": claim, "strength": strength, "evidence_item_ids": refs, "independent_evidence_roles": sorted(roles), "limitations": limitations})
    return output


def normalize_contradiction_checks(value: Any, evidence_ids: set[str]) -> dict[str, dict[str, Any]]:
    return validate_check_group(value, CONTRADICTION_CHECK_KEYS, evidence_ids, "processing_causes_checked")


def validate_analysis_nodes(
    status: dict[str, Any],
    node_ids: Any,
    task_ids: set[str],
    conclusions: list[dict[str, Any]],
) -> list[str]:
    if not isinstance(node_ids, list):
        raise AnalysisError("validated_evidence_node_ids must be a list.")
    source = current_source_payload(status)
    graph = {
        "nodes": source.get("formal_nodes", []),
        "evidence_nodes": source.get("formal_evidence_nodes", []),
        "completed_evidence_node_ids": status["source_snapshot"].get("formal_completed_evidence_node_ids", []),
    }
    evidence = graph_evidence_map(graph)
    formally_complete = set(str(item) for item in graph.get("completed_evidence_node_ids", []))
    accepted_strength = any(item["strength"] in {"STRONGLY_SUPPORTED", "SUPPORTED"} for item in conclusions)
    output: list[str] = []
    for raw in node_ids:
        node_id = stable_id(raw, "validated_evidence_node_id")
        node = evidence.get(node_id)
        if node is None:
            raise AnalysisError(f"Unknown evidence node ID: {node_id}")
        if node_id not in formally_complete:
            raise AnalysisError(f"Evidence node {node_id} cannot be validated before its formal result is accepted.")
        node_tasks = {str(item) for item in node.get("task_ids", [])}
        if node.get("completion_rule") == "any":
            if not node_tasks.intersection(task_ids):
                raise AnalysisError(f"Analysis does not include a contributing task for evidence node {node_id}.")
        elif not node_tasks.issubset(task_ids):
            raise AnalysisError(f"Analysis does not include every required task for evidence node {node_id}.")
        if not accepted_strength:
            raise AnalysisError("An evidence node requires at least one SUPPORTED or STRONGLY_SUPPORTED conclusion.")
        output.append(node_id)
    return sorted(set(output))


def render_analysis_markdown(analysis: dict[str, Any]) -> str:
    lines = [
        f"# 第三阶段结果分析 {analysis['analysis_version']}",
        "",
        f"- 数据集：{', '.join(analysis['dataset_ids'])}",
        f"- 正式任务：{', '.join(analysis['task_ids'])}",
        f"- 分析范围：{analysis['analysis_scope']}",
        f"- 流程结论：`{analysis['outcome_code']}`",
        "",
        f"## 数据结论\n\n{analysis['data_conclusion']}",
        f"## 物理含义\n\n{analysis['physical_meaning']}",
        f"## 证据作用\n\n{analysis['evidence_role']}",
        "## 相互佐证",
        "",
    ]
    lines.extend(f"- {item}" for item in analysis["corroboration"])
    lines.extend(["", "## 实验对应", ""])
    lines.extend(f"- {item}" for item in analysis["experimental_correspondence"] or ["当前没有可验证的实验对应；不作扩展解释。"])
    lines.extend(["", "## 结论边界", ""])
    lines.extend(f"- {item}" for item in analysis["conclusion_boundary"])
    lines.extend(["", "## 下一步判断", "", analysis["next_step_judgment"], "", "## 核心结论强度", ""])
    for item in analysis["conclusions"]:
        lines.append(f"- **{item['strength']}** — {item['claim']}（证据：{', '.join(item['evidence_item_ids']) or '不足'}）")
    lines.extend(["", "## 证据节点", "", f"本分析验证：{analysis['validated_evidence_node_ids'] or '无'}", "", "## 强制边界", "", "未生成科研图件；未执行计算、正式后处理、作业提交、队列查询、远程获取或后台监控。", ""])
    return "\n".join(lines)


def write_evidence_matrix(path: Path, analysis: dict[str, Any]) -> None:
    rows: list[list[str]] = [["evidence_id", "dataset_id", "task_ids", "evidence_role", "source_id", "source_sha256", "observation", "consistency", "claim_strengths"]]
    strengths_by_evidence: dict[str, list[str]] = {}
    for conclusion in analysis["conclusions"]:
        for evidence_id in conclusion["evidence_item_ids"]:
            strengths_by_evidence.setdefault(evidence_id, []).append(conclusion["strength"])
    for item in analysis["evidence_items"]:
        source = item["source_record"]
        checksum = str(source.get("sha256") or source.get("dataset_manifest_sha256") or "")
        rows.append(
            [
                item["evidence_id"],
                item["dataset_id"],
                ";".join(analysis["task_ids"]),
                item["evidence_role"],
                item["source_id"],
                checksum,
                item["observation"],
                item["consistency"],
                ";".join(sorted(set(strengths_by_evidence.get(item["evidence_id"], [])))),
            ]
        )
    output = []
    for row in rows:
        escaped = [f'"{value.replace(chr(34), chr(34) * 2)}"' for value in row]
        output.append(",".join(escaped))
    write_text(path, "\n".join(output) + "\n")


def analyze_value(analysis_dir: Path, status: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
    if status.get("status") == RESULTS_APPROVED:
        raise AnalysisError("Stage-3 results are approved and immutable.")
    ensure_false_flags(payload)
    validation = load_latest_validation(status)
    dataset_ids = [stable_id(item, "dataset_id") for item in payload.get("dataset_ids", [])] if isinstance(payload.get("dataset_ids"), list) else []
    if not dataset_ids or len(dataset_ids) != len(set(dataset_ids)):
        raise AnalysisError("dataset_ids must be a nonempty unique list.")
    if set(dataset_ids) != set(str(item) for item in validation.get("dataset_ids", [])):
        raise AnalysisError("Analysis datasets must exactly match the latest completeness/comparability validation.")
    datasets = latest_datasets(status, dataset_ids)
    for dataset in datasets:
        if validation.get("dataset_versions", {}).get(str(dataset["dataset_id"])) != str(dataset["dataset_version"]):
            raise AnalysisError("A dataset changed after validation; validate the current version first.")
    task_ids = normalize_text_list(payload.get("task_ids", []), "task_ids", allow_empty=False)
    dataset_task_ids = {str(item["task_id"]) for item in datasets}
    if set(task_ids) != dataset_task_ids:
        raise AnalysisError("task_ids must exactly match the ingested datasets' formal tasks.")
    source = current_source_payload(status)
    task_map = graph_task_map({"nodes": source.get("formal_nodes", [])})
    if any(task_id not in task_map for task_id in task_ids):
        raise AnalysisError("Analysis contains an unknown formal task ID.")
    required_text = (
        "analysis_scope",
        "data_conclusion",
        "physical_meaning",
        "evidence_role",
        "next_step_judgment",
        "cross_evidence_consistency",
    )
    text_values = {key: str(payload.get(key, "")).strip() for key in required_text}
    missing_text = [key for key, value in text_values.items() if not value]
    if missing_text:
        raise AnalysisError("Analysis text fields are missing: " + ", ".join(missing_text))
    corroboration = normalize_text_list(payload.get("corroboration", []), "corroboration", allow_empty=False)
    experimental = normalize_text_list(payload.get("experimental_correspondence", []), "experimental_correspondence")
    boundaries = normalize_text_list(payload.get("conclusion_boundary", []), "conclusion_boundary", allow_empty=False)
    trends = normalize_text_list(payload.get("trends", []), "trends", allow_empty=False)
    anomalies = normalize_text_list(payload.get("anomalies", []), "anomalies")
    source_map = evidence_source_map(status, datasets)
    evidence_items, evidence_by_id = normalize_evidence_items(payload.get("evidence_items"), source_map, set(dataset_ids))
    conclusions = normalize_conclusions(payload.get("conclusions"), evidence_by_id)
    contradictions = payload.get("contradictions", [])
    if not isinstance(contradictions, list):
        raise AnalysisError("contradictions must be a list.")
    for index, item in enumerate(contradictions):
        if not isinstance(item, dict) or not str(item.get("description", "")).strip() or not str(item.get("evidence_item_a", "")).strip() or not str(item.get("evidence_item_b", "")).strip():
            raise AnalysisError(f"contradictions[{index}] requires description and two evidence item IDs.")
        if str(item["evidence_item_a"]) not in evidence_by_id or str(item["evidence_item_b"]) not in evidence_by_id:
            raise AnalysisError(f"contradictions[{index}] refers to unknown evidence items.")
    processing_checks: dict[str, dict[str, Any]] = {}
    unresolved_processing_cause = False
    if contradictions:
        processing_checks = normalize_contradiction_checks(payload.get("processing_causes_checked"), set(source_map))
        unresolved_processing_cause = any(item["status"] in {"failed", "unknown"} for item in processing_checks.values())
    elif payload.get("processing_causes_checked") not in (None, {}):
        processing_checks = normalize_contradiction_checks(payload.get("processing_causes_checked"), set(source_map))
    outcome = str(payload.get("outcome_code", "")).strip()
    if outcome not in OUTCOME_STATES:
        raise AnalysisError("Unknown outcome_code.")
    validation_state = validation.get("resulting_state")
    if outcome == "CURRENT_ANALYSIS_READY_FOR_APPROVAL":
        if validation_state != DATA_COMPARABILITY_VALIDATED:
            raise AnalysisError("A ready analysis requires validated completeness and comparability.")
        if unresolved_processing_cause:
            raise AnalysisError("Unresolved processing causes require SUPPLEMENTARY_PROCESSING_REQUIRED.")
    elif outcome == "RETURN_TO_FORMAL_CALCULATION":
        if validation_state != RETURN_TO_FORMAL_CALCULATION or not validation.get("formal_return_reasons"):
            raise AnalysisError("Return to formal calculation requires a validated fundamental source-data cause.")
    elif validation_state == RETURN_TO_FORMAL_CALCULATION:
        raise AnalysisError("A fundamental formal-calculation cause cannot be downgraded to processing-only.")
    validated_nodes = validate_analysis_nodes(status, payload.get("validated_evidence_node_ids", []), set(task_ids), conclusions)
    if outcome != "CURRENT_ANALYSIS_READY_FOR_APPROVAL" and validated_nodes:
        raise AnalysisError("An unresolved analysis cannot validate an evidence node.")
    completion_checks = {
        "necessary_data_processing_completed": all(item.get("data_stage") == "processed" for item in datasets) and validation["common_checks"]["target_processing_completed"]["status"] == "passed",
        "processed_data_uploaded": all(item.get("data_stage") == "processed" for item in datasets),
        "data_completeness_checked": validation.get("data_completeness_checked") is True,
        "data_comparability_validated": validation.get("data_comparability_validated") is True,
        "directed_result_analysis_completed": all(bool(text_values[key]) for key in required_text),
        "cross_evidence_consistency_addressed": bool(text_values["cross_evidence_consistency"]),
        "conclusion_strengths_assigned": bool(conclusions) and all(item["strength"] in CONCLUSION_STRENGTHS for item in conclusions),
    }
    version = next_root_version(analysis_dir, "result_analysis_")
    analysis = {
        "project_id": status.get("project_id"),
        "analysis_version": version,
        "source_snapshot_version": status["source_snapshot"]["snapshot_version"],
        "validation_version": validation["validation_version"],
        "dataset_ids": dataset_ids,
        "dataset_versions": {str(item["dataset_id"]): str(item["dataset_version"]) for item in datasets},
        "task_ids": task_ids,
        **text_values,
        "corroboration": corroboration,
        "experimental_correspondence": experimental,
        "conclusion_boundary": boundaries,
        "trends": trends,
        "anomalies": anomalies,
        "evidence_items": evidence_items,
        "contradictions": copy.deepcopy(contradictions),
        "processing_causes_checked": processing_checks,
        "conclusions": conclusions,
        "validated_evidence_node_ids": validated_nodes,
        "completion_checks": completion_checks,
        "outcome_code": outcome,
        "resulting_state": OUTCOME_STATES[outcome],
        "formal_return_reasons": copy.deepcopy(validation.get("formal_return_reasons", [])),
        "overall_stage_complete": False,
        "generated_at": utc_now(),
        **false_execution_flags(),
    }
    json_path = analysis_dir / f"result_analysis_{version}.json"
    md_path = analysis_dir / f"result_analysis_{version}.md"
    matrix_path = analysis_dir / f"evidence_matrix_{version}.csv"
    write_json(json_path, analysis)
    write_text(md_path, render_analysis_markdown(analysis))
    write_evidence_matrix(matrix_path, analysis)
    evidence_copy = analysis_dir / "evidence_analysis" / f"result_analysis_{version}.json"
    write_json(evidence_copy, analysis)
    experiment_record = None
    if experimental:
        experiment_path = analysis_dir / "experiment_comparison" / f"experiment_comparison_{version}.json"
        write_json(experiment_path, {"project_id": status.get("project_id"), "analysis_version": version, "items": experimental, "conclusion_boundary": boundaries})
        experiment_record = file_record(experiment_path)
    record = {
        "version": version,
        "json": file_record(json_path),
        "markdown": file_record(md_path),
        "evidence_matrix": file_record(matrix_path),
        "evidence_copy": file_record(evidence_copy),
        "experiment_comparison": experiment_record,
        "dataset_ids": dataset_ids,
        "outcome_code": outcome,
        "resulting_state": OUTCOME_STATES[outcome],
    }
    status.setdefault("analysis_records", []).append(record)
    status["latest_analysis_record"] = record["json"]
    status["status"] = OUTCOME_STATES[outcome]
    status["pending_information"] = validation.get("unresolved_checks", []) if outcome != "CURRENT_ANALYSIS_READY_FOR_APPROVAL" else []
    write_status(analysis_dir, status)
    append_log(analysis_dir, {"event": "directed_result_analysis_completed", "version": version, "outcome_code": outcome, "state": status["status"], "validated_evidence_node_ids": validated_nodes})
    return analysis


def analyze(analysis_dir: Path, source_path: Path) -> dict[str, Any]:
    status = load_status(analysis_dir)
    if status.get("status") == RESULTS_APPROVED:
        raise AnalysisError("Stage-3 results are approved and immutable.")
    payload = read_json(source_path)
    if not isinstance(payload, dict):
        raise AnalysisError("Result analysis must be a JSON object.")
    return analyze_value(analysis_dir, status, payload)


def load_latest_analysis(status: dict[str, Any]) -> dict[str, Any]:
    record = status.get("latest_analysis_record")
    if not record:
        raise AnalysisError("No current result analysis exists.")
    path = verify_file_record(record, "latest result analysis")
    value = read_json(path)
    if not isinstance(value, dict):
        raise AnalysisError("Latest result analysis is invalid.")
    return value


def copy_validated_datasets(analysis_dir: Path, status: dict[str, Any], analysis: dict[str, Any], approval_version: str) -> list[dict[str, Any]]:
    destination_root = analysis_dir / "validated_data" / f"analysis_{analysis['analysis_version']}_approval_{approval_version}"
    if destination_root.exists():
        raise AnalysisError("Validated-data approval directory already exists.")
    destination_root.mkdir(parents=True)
    records: list[dict[str, Any]] = []
    try:
        for dataset_id in analysis["dataset_ids"]:
            record = status.get("latest_dataset_by_id", {}).get(dataset_id)
            dataset = verify_dataset_record(record, f"approved dataset {dataset_id}")
            if str(dataset.get("dataset_version")) != str(analysis["dataset_versions"].get(dataset_id)):
                raise AnalysisError(f"Dataset {dataset_id} changed after analysis.")
            source_dir = Path(str(record["path"])).parent
            target_dir = destination_root / source_dir.name
            shutil.copytree(source_dir, target_dir)
            copied_manifest = target_dir / "dataset_manifest.json"
            copied = read_json(copied_manifest)
            for file_item in copied.get("files", []):
                original_path = Path(str(file_item["path"]))
                new_path = target_dir / original_path.name
                if not new_path.is_file() or sha256(new_path) != file_item["sha256"]:
                    raise AnalysisError(f"Validated copy failed checksum for {dataset_id}/{original_path.name}.")
                file_item["validated_copy_path"] = str(new_path.resolve())
            records.append(file_record(copied_manifest, dataset_id=dataset_id, dataset_version=dataset["dataset_version"]))
    except Exception:
        shutil.rmtree(destination_root, ignore_errors=True)
        raise
    return records


def action(
    analysis_dir: Path,
    action_name: str,
    reason: str,
    confirmed_by: str,
    review_verified: bool = False,
) -> dict[str, Any]:
    status = load_status(analysis_dir)
    if action_name == "accept-analysis":
        if not review_verified:
            raise AnalysisError("Result approval must be submitted through the hash-bound browser review command.")
        if status.get("status") != WAITING_FOR_RESULT_APPROVAL:
            raise AnalysisError("Only an analysis waiting for approval may be accepted.")
        if not str(confirmed_by).strip() or str(confirmed_by).strip().lower() in {"skill", "assistant", "automatic"}:
            raise AnalysisError("Acceptance requires explicit user identity/confirmation.")
        analysis = load_latest_analysis(status)
        if analysis.get("outcome_code") != "CURRENT_ANALYSIS_READY_FOR_APPROVAL":
            raise AnalysisError("Only a ready current analysis may be accepted.")
        validation = load_latest_validation(status)
        if analysis.get("validation_version") != validation.get("validation_version"):
            raise AnalysisError("The analysis no longer matches the latest validation.")
        version = next_root_version(analysis_dir / "evidence_analysis", "analysis_approval_")
        validated_copies = copy_validated_datasets(analysis_dir, status, analysis, version)
        prior_nodes = set(str(item) for item in status.get("validated_evidence_node_ids", []))
        accepted_nodes = sorted(prior_nodes | set(str(item) for item in analysis.get("validated_evidence_node_ids", [])))
        required_nodes = required_evidence_node_ids(status)
        all_checks = all(analysis.get("completion_checks", {}).values())
        overall_complete = bool(accepted_nodes) and set(required_nodes).issubset(accepted_nodes) and all_checks
        resulting_state = RESULTS_APPROVED if overall_complete else EVIDENCE_CHAIN_VALIDATED
        approval = {
            "project_id": status.get("project_id"),
            "approval_version": version,
            "analysis_version": analysis["analysis_version"],
            "analysis_record": copy.deepcopy(status["latest_analysis_record"]),
            "validation_record": copy.deepcopy(status["latest_validation_record"]),
            "dataset_versions": copy.deepcopy(analysis["dataset_versions"]),
            "validated_dataset_copies": validated_copies,
            "source_snapshot_record": copy.deepcopy(status["source_snapshot_record"]),
            "prior_validated_evidence_node_ids": sorted(prior_nodes),
            "newly_validated_evidence_node_ids": copy.deepcopy(analysis["validated_evidence_node_ids"]),
            "all_validated_evidence_node_ids": accepted_nodes,
            "required_evidence_node_ids": required_nodes,
            "completion_checks": copy.deepcopy(analysis["completion_checks"]),
            "overall_stage_complete": overall_complete,
            "resulting_state": resulting_state,
            "confirmed_by": str(confirmed_by).strip(),
            "confirmation": "接受当前分析",
            "reason": str(reason).strip(),
            "confirmed_at": utc_now(),
            **false_execution_flags(),
        }
        approval_path = analysis_dir / "evidence_analysis" / f"analysis_approval_{version}.json"
        write_json(approval_path, approval)
        approval_record = file_record(approval_path, version=version, analysis_version=analysis["analysis_version"])
        status.setdefault("approval_records", []).append(approval_record)
        status["latest_approval_record"] = approval_record
        status["validated_evidence_node_ids"] = accepted_nodes
        status["overall_stage_complete"] = overall_complete
        status["status"] = resulting_state
        status["pending_information"] = [] if overall_complete else sorted(set(required_nodes) - set(accepted_nodes))
        write_status(analysis_dir, status)
        append_log(analysis_dir, {"event": "result_analysis_accepted", "analysis_version": analysis["analysis_version"], "approval_version": version, "state": resulting_state, "overall_stage_complete": overall_complete})
        return approval
    if action_name == "request-reanalysis":
        if status.get("status") not in {WAITING_FOR_RESULT_APPROVAL, EVIDENCE_CHAIN_VALIDATED}:
            raise AnalysisError("Reanalysis may be requested only for a current or partially accepted analysis.")
        if not str(reason).strip():
            raise AnalysisError("Reanalysis requires a specific reason.")
        analysis = load_latest_analysis(status)
        version = next_root_version(analysis_dir / "rejected_data", "reanalysis_request_")
        rejection = {
            "project_id": status.get("project_id"),
            "version": version,
            "analysis_version": analysis["analysis_version"],
            "analysis_record": copy.deepcopy(status["latest_analysis_record"]),
            "reason": str(reason).strip(),
            "requested_by": str(confirmed_by).strip() or "user",
            "requested_at": utc_now(),
        }
        path = analysis_dir / "rejected_data" / f"reanalysis_request_{version}.json"
        write_json(path, rejection)
        if status.get("status") == EVIDENCE_CHAIN_VALIDATED and status.get("latest_approval_record"):
            latest_approval = read_json(verify_file_record(status["latest_approval_record"], "latest analysis approval"))
            if latest_approval.get("analysis_version") == analysis.get("analysis_version"):
                status["validated_evidence_node_ids"] = sorted(
                    str(item) for item in latest_approval.get("prior_validated_evidence_node_ids", [])
                )
        status["status"] = PROCESSED_DATA_RECEIVED
        status["overall_stage_complete"] = False
        status["pending_information"] = sorted(
            set(required_evidence_node_ids(status)) - set(status.get("validated_evidence_node_ids", []))
        )
        status["latest_reanalysis_request"] = file_record(path)
        write_status(analysis_dir, status)
        append_log(analysis_dir, {"event": "result_reanalysis_requested", "analysis_version": analysis["analysis_version"], "version": version, "reason": reason})
        return rejection
    raise AnalysisError("Action must be accept-analysis or request-reanalysis.")


def browser_review(
    analysis_dir: Path,
    project_dir: Path,
    title: str,
    start_port: int,
    timeout_seconds: float | None,
) -> dict[str, Any]:
    status = load_status(analysis_dir)
    record = status.get("latest_analysis_record")
    if not isinstance(record, dict):
        raise AnalysisError("No result-analysis candidate is available for browser review.")
    content_file = verify_file_record(record, "latest result analysis")
    return execute_stage_review(
        project_dir=project_dir,
        stage_dir=analysis_dir,
        stage="stage3_analysis",
        title=title,
        content_file=content_file,
        allowed_statuses={WAITING_FOR_RESULT_APPROVAL},
        revision_status=PROCESSED_DATA_RECEIVED,
        rejected_status=STAGE3_REVIEW_REJECTED,
        load_status=lambda: load_status(analysis_dir),
        save_status=lambda value: write_status(analysis_dir, value),
        append_log=lambda value: append_log(analysis_dir, value),
        approve=lambda comment: action(
            analysis_dir,
            "accept-analysis",
            comment,
            "browser_user",
            review_verified=True,
        ),
        error_type=AnalysisError,
        blocked_access_updates={"overall_stage_complete": False},
        revision_updates={"overall_stage_complete": False},
        rejected_updates={"overall_stage_complete": False},
        start_port=start_port,
        timeout_seconds=timeout_seconds,
    )


def current_data(analysis_dir: Path) -> dict[str, Any]:
    status = load_status(analysis_dir)
    datasets: list[dict[str, Any]] = []
    for dataset_id, record in sorted(status.get("latest_dataset_by_id", {}).items()):
        datasets.append(verify_dataset_record(record, f"latest dataset {dataset_id}"))
    progress: list[dict[str, Any]] = []
    for dataset_id, record in sorted(status.get("progress_records", {}).items()):
        path = verify_file_record(record, f"progress record {dataset_id}")
        progress.append(read_json(path))
    guides: list[dict[str, Any]] = []
    for record in status.get("guide_records", []):
        path = verify_file_record(record.get("json"), "guide record")
        guides.append(read_json(path))
    validation = load_latest_validation(status) if status.get("latest_validation_record") else None
    analysis = load_latest_analysis(status) if status.get("latest_analysis_record") else None
    approval = None
    if status.get("latest_approval_record"):
        approval = read_json(verify_file_record(status["latest_approval_record"], "latest analysis approval"))
    source = current_source_payload(status)
    return {
        "analysis_dir": str(analysis_dir.resolve()),
        "status": status,
        "initial_question": INITIAL_QUESTION if status.get("initial_question_required") else None,
        "datasets": datasets,
        "progress": progress,
        "guides": guides,
        "latest_validation": validation,
        "latest_analysis": analysis,
        "latest_approval": approval,
        "formal_tasks": source.get("formal_nodes", []),
        "formal_evidence_nodes": source.get("formal_evidence_nodes", []),
        "required_evidence_node_ids": required_evidence_node_ids(status),
        "change_log": read_json(change_log_path(analysis_dir)),
    }


class AnalysisHandler(BaseHTTPRequestHandler):
    analysis_dir: Path

    def log_message(self, format_string: str, *args: Any) -> None:
        sys.stderr.write("[stage3-review] " + format_string % args + "\n")

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
        if length <= 0 or length > 8 * 1024 * 1024:
            raise AnalysisError("Request body must be between 1 byte and 8 MiB.")
        value = json.loads(self.rfile.read(length).decode("utf-8"))
        if not isinstance(value, dict):
            raise AnalysisError("Request body must be a JSON object.")
        return value

    def do_GET(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
        try:
            if path in {"/", "/result_review.html"}:
                self.send_file(self.analysis_dir / "result_review.html", "text/html; charset=utf-8")
            elif path == "/api/state":
                self.send_json(current_data(self.analysis_dir))
            elif path.startswith("/files/"):
                target = safe_relative_path(self.analysis_dir, path[len("/files/") :])
                if not target.is_file():
                    self.send_json({"error": "File not found"}, HTTPStatus.NOT_FOUND)
                else:
                    self.send_file(target)
            else:
                self.send_json({"error": "Not found"}, HTTPStatus.NOT_FOUND)
        except (AnalysisError, OSError, ValueError, json.JSONDecodeError) as exc:
            self.send_json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)

    def do_POST(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
        try:
            payload = self.body()
            status = load_status(self.analysis_dir)
            if path == "/api/progress":
                result = update_progress_value(self.analysis_dir, status, payload)
            elif path == "/api/guide":
                result = provide_guide_value(self.analysis_dir, status, payload)
            elif path == "/api/action":
                result = action(
                    self.analysis_dir,
                    str(payload.get("action", "")),
                    str(payload.get("reason", "")),
                    str(payload.get("confirmed_by", "user")),
                )
            else:
                self.send_json({"error": "Not found"}, HTTPStatus.NOT_FOUND)
                return
            self.send_json({"ok": True, "result": result})
        except (AnalysisError, OSError, ValueError, json.JSONDecodeError) as exc:
            self.send_json({"ok": False, "error": str(exc)}, HTTPStatus.BAD_REQUEST)


def serve(analysis_dir: Path, host: str, port: int, open_page: bool) -> None:
    load_status(analysis_dir)
    ensure_review_html(analysis_dir)
    handler = type("BoundAnalysisHandler", (AnalysisHandler,), {"analysis_dir": analysis_dir})
    server = ThreadingHTTPServer((host, port), handler)
    address = f"http://{host}:{server.server_address[1]}/"
    print(f"Stage-3 result review page: {address}", flush=True)
    print("Press Ctrl+C to stop. This page does not run calculations, post-processing, or plotting.", flush=True)
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

    start_parser = subparsers.add_parser("start", help="Freeze stage-1/formal sources and initialize stage 3.")
    start_parser.add_argument("--planning-dir", type=Path, required=True)
    start_parser.add_argument("--formal-dir", type=Path, required=True)
    start_parser.add_argument("--analysis-dir", type=Path, default=Path("results_analysis"))
    start_parser.add_argument("--user-data-status", choices=tuple(DATA_STATUS_MAP))

    sync_parser = subparsers.add_parser("sync-sources", help="Adopt a newer formal graph/result projection without changing it.")
    sync_parser.add_argument("--analysis-dir", type=Path, default=Path("results_analysis"))

    progress_parser = subparsers.add_parser("progress", help="Record a monotonic per-dataset processing progress version.")
    progress_parser.add_argument("--analysis-dir", type=Path, default=Path("results_analysis"))
    progress_parser.add_argument("--record", type=Path, required=True)

    guide_parser = subparsers.add_parser("guide", help="Generate a full overview or one expanded processing step.")
    guide_parser.add_argument("--analysis-dir", type=Path, default=Path("results_analysis"))
    guide_parser.add_argument("--request", type=Path, required=True)

    ingest_parser = subparsers.add_parser("ingest", help="Copy and inspect an immutable raw/partial/processed dataset version.")
    ingest_parser.add_argument("--analysis-dir", type=Path, default=Path("results_analysis"))
    ingest_parser.add_argument("--manifest", type=Path, required=True)

    validate_parser = subparsers.add_parser("validate-data", help="Check data completeness and comparability with evidence.")
    validate_parser.add_argument("--analysis-dir", type=Path, default=Path("results_analysis"))
    validate_parser.add_argument("--validation", type=Path, required=True)

    analyze_parser = subparsers.add_parser("analyze", help="Create an evidence-linked directed result analysis.")
    analyze_parser.add_argument("--analysis-dir", type=Path, default=Path("results_analysis"))
    analyze_parser.add_argument("--analysis", type=Path, required=True)

    action_parser = subparsers.add_parser("action", help="Accept the current analysis or request reanalysis.")
    action_parser.add_argument("--analysis-dir", type=Path, default=Path("results_analysis"))
    action_parser.add_argument("--action", choices=("accept-analysis", "request-reanalysis"), required=True)
    action_parser.add_argument("--reason", default="")
    action_parser.add_argument("--confirmed-by", default="user")

    serve_parser = subparsers.add_parser("serve", help="Serve the local text/table result-review page.")
    serve_parser.add_argument("--analysis-dir", type=Path, default=Path("results_analysis"))
    serve_parser.add_argument("--host", default="127.0.0.1")
    serve_parser.add_argument("--port", type=int, default=0)
    serve_parser.add_argument("--open", action="store_true", dest="open_page")

    review_parser = subparsers.add_parser("review", help="Open the hash-bound Flask review gate and wait for a decision.")
    review_parser.add_argument("--analysis-dir", type=Path, default=Path("results_analysis"))
    review_parser.add_argument("--project-dir", type=Path)
    review_parser.add_argument("--title", default="第三阶段：数据处理与证据链结果审查")
    review_parser.add_argument("--start-port", type=int, default=5050)
    review_parser.add_argument("--timeout", type=float, default=0.0)

    status_parser = subparsers.add_parser("status", help="Show current stage-3 state without monitoring anything.")
    status_parser.add_argument("--analysis-dir", type=Path, default=Path("results_analysis"))
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        if args.command == "start":
            result = start(args.analysis_dir.resolve(), args.planning_dir.resolve(), args.formal_dir.resolve(), args.user_data_status)
        elif args.command == "sync-sources":
            result = sync_sources(args.analysis_dir.resolve())
        elif args.command == "progress":
            result = update_progress(args.analysis_dir.resolve(), args.record.resolve())
        elif args.command == "guide":
            result = provide_guide(args.analysis_dir.resolve(), args.request.resolve())
        elif args.command == "ingest":
            result = ingest_dataset(args.analysis_dir.resolve(), args.manifest.resolve())
        elif args.command == "validate-data":
            result = validate_data(args.analysis_dir.resolve(), args.validation.resolve())
        elif args.command == "analyze":
            result = analyze(args.analysis_dir.resolve(), args.analysis.resolve())
        elif args.command == "action":
            result = action(args.analysis_dir.resolve(), args.action, args.reason, args.confirmed_by)
        elif args.command == "serve":
            serve(args.analysis_dir.resolve(), args.host, args.port, args.open_page)
            return 0
        elif args.command == "review":
            analysis_dir = args.analysis_dir.resolve()
            project_dir = args.project_dir.resolve() if args.project_dir else analysis_dir.parent
            result = browser_review(analysis_dir, project_dir, args.title, args.start_port, args.timeout)
        elif args.command == "status":
            result = current_data(args.analysis_dir.resolve())
        else:
            raise AnalysisError(f"Unsupported command: {args.command}")
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (AnalysisError, OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
