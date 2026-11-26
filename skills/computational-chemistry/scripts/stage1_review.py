#!/usr/bin/env python3
"""Version, review, compare, and approve a stage-1 computational chemistry plan."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
import webbrowser
from datetime import datetime, timezone
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from review_ui.server import content_sha256
from review_ui.workflow import (
    ReviewWorkflowError,
    prepare_review_request,
    run_review_session,
)

WAITING_FOR_USER_APPROVAL = "WAITING_FOR_USER_APPROVAL"
USER_EDITED_PENDING_ANALYSIS = "USER_EDITED_PENDING_ANALYSIS"
IMPACT_ANALYSIS_READY = "IMPACT_ANALYSIS_READY"
WAITING_FOR_FINAL_APPROVAL = "WAITING_FOR_FINAL_APPROVAL"
WAITING_FOR_REVIEW_DECISION = "WAITING_FOR_REVIEW_DECISION"
STAGE1_REVIEW_REJECTED = "STAGE1_REVIEW_REJECTED"
APPROVED = "APPROVED"

VALID_STATUSES = {
    WAITING_FOR_USER_APPROVAL,
    USER_EDITED_PENDING_ANALYSIS,
    IMPACT_ANALYSIS_READY,
    WAITING_FOR_FINAL_APPROVAL,
    WAITING_FOR_REVIEW_DECISION,
    STAGE1_REVIEW_REJECTED,
    APPROVED,
}

TASK_REQUIRED_FIELDS = (
    "id",
    "name",
    "scientific_question_id",
    "systems",
    "controls",
    "software",
    "module",
    "method",
    "target_parameters",
    "target_data_forms",
    "scientific_meaning",
    "supported_conclusions",
    "experimental_correspondence",
    "corroborates_with",
    "prerequisites",
    "downstream_dependencies",
    "evidence_role",
    "scientific_weight",
    "workload_weight",
    "result_sensitivity",
    "irreplaceability",
    "priority",
    "necessity",
    "alternatives",
    "redundancy",
    "status",
    "user_notes",
)

SCI_COMPONENTS = ("I", "U", "S", "N")
WORK_COMPONENTS = ("M", "C", "K", "P", "H")
FORBIDDEN_RESOURCE_KEYS = {
    "estimated_runtime",
    "runtime_hours",
    "estimated_memory",
    "memory_gb",
    "estimated_storage",
    "storage_gb",
}
PROTECTED_TOP_LEVEL = {"project_id", "protected_records"}
ENTITY_LISTS = ("scientific_questions", "systems", "controls", "tasks", "evidence_chain")


class Stage1Error(RuntimeError):
    """Raise for user-correctable workflow errors."""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: Any) -> None:
    write_text(path, json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def write_text(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(value, encoding="utf-8", newline="\n")
    temporary.replace(path)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def asset_html_path() -> Path:
    return Path(__file__).resolve().parent.parent / "assets" / "stage1_review.html"


def ensure_review_html(planning_dir: Path) -> None:
    assets_dir = asset_html_path().parent
    for name in ("stage1_review.html", "stage1_review.css", "stage1_review.js"):
        source = assets_dir / name
        if not source.exists():
            raise Stage1Error(f"Review-page asset is missing: {source}")
        shutil.copyfile(source, planning_dir / name)


def status_path(planning_dir: Path) -> Path:
    return planning_dir / "stage1_status.json"


def log_path(planning_dir: Path) -> Path:
    return planning_dir / "stage1_change_log.json"


def version_json_path(planning_dir: Path, version: str) -> Path:
    return planning_dir / f"stage1_plan_{version}.json"


def version_md_path(planning_dir: Path, version: str) -> Path:
    return planning_dir / f"stage1_plan_{version}.md"


def parse_version(version: str) -> int:
    match = re.fullmatch(r"v(\d{3,})", version or "")
    if not match:
        raise Stage1Error(f"Invalid plan version: {version!r}")
    return int(match.group(1))


def next_version(status: dict[str, Any]) -> str:
    return f"v{parse_version(status['latest_version']) + 1:03d}"


def load_status(planning_dir: Path) -> dict[str, Any]:
    path = status_path(planning_dir)
    if not path.exists():
        raise Stage1Error("stage1_status.json is missing; initialize the review first.")
    status = read_json(path)
    if status.get("status") not in VALID_STATUSES:
        raise Stage1Error(f"Unknown stage-1 status: {status.get('status')!r}")
    return status


def load_plan(planning_dir: Path, version: str) -> dict[str, Any]:
    path = version_json_path(planning_dir, version)
    if not path.exists():
        raise Stage1Error(f"Plan version does not exist: {version}")
    plan = read_json(path)
    if not isinstance(plan, dict):
        raise Stage1Error(f"Plan version {version} is not a JSON object.")
    return plan


def append_log(planning_dir: Path, entry: dict[str, Any]) -> None:
    path = log_path(planning_dir)
    entries = read_json(path) if path.exists() else []
    if not isinstance(entries, list):
        raise Stage1Error("stage1_change_log.json must contain a JSON list.")
    entries.append(entry)
    write_json(path, entries)


def score_component(weight: dict[str, Any], key: str, errors: list[str], path: str) -> float | None:
    value = weight.get(key)
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        errors.append(f"{path}.{key} must be a number from 0 to 100.")
        return None
    if not 0 <= float(value) <= 100:
        errors.append(f"{path}.{key} must be between 0 and 100.")
        return None
    return float(value)


def calculate_task_weights(task: dict[str, Any], coefficient: float, errors: list[str], index: int) -> None:
    scientific = task.get("scientific_weight")
    workload = task.get("workload_weight")
    task_path = f"tasks[{index}]"
    if not isinstance(scientific, dict):
        errors.append(f"{task_path}.scientific_weight must be an object.")
    else:
        values = {key: score_component(scientific, key, errors, f"{task_path}.scientific_weight") for key in SCI_COMPONENTS}
        rationale = scientific.get("rationale")
        if not isinstance(rationale, dict) or any(not str(rationale.get(key, "")).strip() for key in SCI_COMPONENTS):
            errors.append(f"{task_path}.scientific_weight.rationale must explain I, U, S, and N separately.")
        i_value = values["I"]
        u_value = values["U"]
        s_value = values["S"]
        n_value = values["N"]
        if all(value is not None for value in (i_value, u_value, s_value, n_value)):
            assert i_value is not None and u_value is not None and s_value is not None and n_value is not None
            scientific["value"] = round(
                0.35 * i_value + 0.25 * u_value + 0.20 * s_value + 0.20 * n_value,
                2,
            )

    if not isinstance(workload, dict):
        errors.append(f"{task_path}.workload_weight must be an object.")
    else:
        values = {key: score_component(workload, key, errors, f"{task_path}.workload_weight") for key in WORK_COMPONENTS}
        rationale = workload.get("rationale")
        if not isinstance(rationale, dict) or any(not str(rationale.get(key, "")).strip() for key in WORK_COMPONENTS):
            errors.append(f"{task_path}.workload_weight.rationale must explain M, C, K, P, and H separately.")
        m_value = values["M"]
        c_value = values["C"]
        k_value = values["K"]
        p_value = values["P"]
        h_value = values["H"]
        if all(value is not None for value in (m_value, c_value, k_value, p_value, h_value)):
            assert m_value is not None and c_value is not None and k_value is not None and p_value is not None and h_value is not None
            workload["value"] = round(
                0.25 * m_value
                + 0.25 * c_value
                + 0.20 * k_value
                + 0.15 * p_value
                + 0.15 * h_value,
                2,
            )

    sci_value = scientific.get("value") if isinstance(scientific, dict) else None
    work_value = workload.get("value") if isinstance(workload, dict) else None
    if isinstance(sci_value, (int, float)) and isinstance(work_value, (int, float)):
        task["execution_priority_index"] = round(float(sci_value) / (1 + coefficient * float(work_value)), 4)


def find_forbidden_resource_keys(value: Any, prefix: str = "") -> list[str]:
    found: list[str] = []
    if isinstance(value, dict):
        for key, child in value.items():
            path = f"{prefix}.{key}" if prefix else str(key)
            if str(key).lower() in FORBIDDEN_RESOURCE_KEYS:
                found.append(path)
            found.extend(find_forbidden_resource_keys(child, path))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            found.extend(find_forbidden_resource_keys(child, f"{prefix}[{index}]"))
    return found


def detect_cycle(tasks: list[dict[str, Any]]) -> list[str] | None:
    graph = {str(task.get("id")): [str(item) for item in task.get("prerequisites", [])] for task in tasks}
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(node: str, chain: list[str]) -> list[str] | None:
        if node in visiting:
            start = chain.index(node) if node in chain else 0
            return chain[start:] + [node]
        if node in visited:
            return None
        visiting.add(node)
        chain.append(node)
        for parent in graph.get(node, []):
            cycle = visit(parent, chain)
            if cycle:
                return cycle
        chain.pop()
        visiting.remove(node)
        visited.add(node)
        return None

    for task_id in graph:
        cycle = visit(task_id, [])
        if cycle:
            return cycle
    return None


def validate_and_score_plan(plan: dict[str, Any]) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    if not str(plan.get("project_id", "")).strip():
        errors.append("project_id is required.")
    if plan.get("stage") not in (1, "1", None):
        errors.append("stage must be 1.")
    plan["stage"] = 1

    goal = plan.get("research_goal")
    if not isinstance(goal, dict):
        errors.append("research_goal must be an object.")
    else:
        for key in ("research_object", "core_question", "target_conclusion"):
            if not str(goal.get(key, "")).strip():
                errors.append(f"research_goal.{key} is required.")

    for key in ("scientific_questions", "systems", "controls", "evidence_chain", "tasks"):
        if not isinstance(plan.get(key), list):
            errors.append(f"{key} must be a list.")
        elif not plan.get(key):
            errors.append(f"{key} must contain at least one entry for a complete stage-1 plan.")

    raw_tasks = plan.get("tasks")
    tasks: list[Any] = raw_tasks if isinstance(raw_tasks, list) else []
    identifiers: list[str] = []
    settings = plan.get("weight_settings")
    if not isinstance(settings, dict):
        errors.append("weight_settings must be an object.")
        settings = {}
        plan["weight_settings"] = settings
    coefficient = settings.get("lambda", 0.01)
    if not isinstance(coefficient, (int, float)) or isinstance(coefficient, bool) or coefficient < 0:
        errors.append("weight_settings.lambda must be a non-negative number.")
        coefficient = 0.01
    settings["lambda"] = coefficient
    settings["priority_index_note"] = "Internal ranking aid only; never convert to runtime or use to delete a necessary task automatically."

    for index, task in enumerate(tasks):
        if not isinstance(task, dict):
            errors.append(f"tasks[{index}] must be an object.")
            continue
        missing = [field for field in TASK_REQUIRED_FIELDS if field not in task]
        if missing:
            errors.append(f"tasks[{index}] is missing fields: {', '.join(missing)}.")
        task_id = str(task.get("id", "")).strip()
        if not task_id:
            errors.append(f"tasks[{index}].id is required.")
        for scalar_field in (
            "name",
            "scientific_question_id",
            "software",
            "module",
            "method",
            "scientific_meaning",
            "evidence_role",
            "result_sensitivity",
            "irreplaceability",
            "priority",
            "necessity",
            "redundancy",
            "status",
        ):
            if scalar_field in task and not str(task.get(scalar_field, "")).strip():
                errors.append(f"tasks[{index}].{scalar_field} must not be empty; use a justified 'not_applicable' value when needed.")
        identifiers.append(task_id)
        for list_field in (
            "systems",
            "controls",
            "target_parameters",
            "target_data_forms",
            "supported_conclusions",
            "experimental_correspondence",
            "corroborates_with",
            "prerequisites",
            "downstream_dependencies",
            "alternatives",
        ):
            if list_field in task and not isinstance(task[list_field], list):
                errors.append(f"tasks[{index}].{list_field} must be a list.")
        calculate_task_weights(task, float(coefficient), errors, index)

    duplicates = sorted({item for item in identifiers if item and identifiers.count(item) > 1})
    if duplicates:
        errors.append(f"Task IDs must be unique; duplicates: {', '.join(duplicates)}.")
    task_ids = set(identifiers)
    entity_ids: dict[str, set[str]] = {}
    for field in ("scientific_questions", "systems", "controls"):
        values: list[Any] = plan.get(field, []) if isinstance(plan.get(field), list) else []
        ids = [str(item.get("id", "")).strip() for item in values if isinstance(item, dict)]
        missing_id_indexes = [str(index) for index, item in enumerate(values) if not isinstance(item, dict) or not str(item.get("id", "")).strip()]
        if missing_id_indexes:
            errors.append(f"{field} entries require IDs; invalid indexes: {', '.join(missing_id_indexes)}.")
        duplicate_ids = sorted({item for item in ids if item and ids.count(item) > 1})
        if duplicate_ids:
            errors.append(f"{field} IDs must be unique; duplicates: {', '.join(duplicate_ids)}.")
        entity_ids[field] = set(ids)
    for index, task in enumerate(tasks):
        if not isinstance(task, dict):
            continue
        for relation in ("prerequisites", "downstream_dependencies"):
            related_values = task.get(relation)
            for related in related_values if isinstance(related_values, list) else []:
                if str(related) not in task_ids:
                    errors.append(f"tasks[{index}].{relation} refers to missing task {related!r}.")
                if str(related) == str(task.get("id")):
                    errors.append(f"tasks[{index}].{relation} cannot refer to itself.")
        question_id = str(task.get("scientific_question_id", "")).strip()
        if question_id and question_id not in entity_ids.get("scientific_questions", set()):
            errors.append(f"tasks[{index}].scientific_question_id refers to missing question {question_id!r}.")
        for task_field, entity_field in (("systems", "systems"), ("controls", "controls")):
            for related in task.get(task_field, []) if isinstance(task.get(task_field), list) else []:
                if str(related) not in entity_ids.get(entity_field, set()):
                    errors.append(f"tasks[{index}].{task_field} refers to missing {entity_field[:-1]} {related!r}.")

    cycle = detect_cycle([task for task in tasks if isinstance(task, dict)])
    if cycle:
        errors.append("Task prerequisite cycle detected: " + " -> ".join(cycle) + ".")

    for index, link in enumerate(plan.get("evidence_chain", []) if isinstance(plan.get("evidence_chain"), list) else []):
        if not isinstance(link, dict):
            errors.append(f"evidence_chain[{index}] must be an object.")
            continue
        if "id" not in link or "role" not in link or not isinstance(link.get("task_ids"), list):
            errors.append(f"evidence_chain[{index}] requires id, role, and task_ids.")
            continue
        missing_ids = [str(item) for item in link["task_ids"] if str(item) not in task_ids]
        if missing_ids:
            errors.append(f"evidence_chain[{index}] refers to missing tasks: {', '.join(missing_ids)}.")

    for forbidden in find_forbidden_resource_keys(plan):
        errors.append(f"Unsupported hardware estimate field is forbidden: {forbidden}.")

    signatures: dict[tuple[str, str, str], list[str]] = {}
    for task in tasks:
        if not isinstance(task, dict):
            continue
        supported = task.get("supported_conclusions")
        supported_values = supported if isinstance(supported, list) else []
        signature = (
            str(task.get("scientific_question_id", "")).strip().lower(),
            str(task.get("evidence_role", "")).strip().lower(),
            "|".join(sorted(str(item).strip().lower() for item in supported_values)),
        )
        signatures.setdefault(signature, []).append(str(task.get("id", "")))
    for signature, ids in signatures.items():
        if signature != ("", "", "") and len(ids) > 1:
            warnings.append(
                f"Potential evidence duplication among tasks {', '.join(ids)}; verify that each has a distinct evidence function."
            )

    return errors, warnings


def manual_override_paths(plan: dict[str, Any]) -> dict[str, str]:
    overrides: dict[str, str] = {}
    for item in plan.get("manual_overrides", []) if isinstance(plan.get("manual_overrides"), list) else []:
        if isinstance(item, dict) and str(item.get("path", "")).strip() and str(item.get("reason", "")).strip():
            item["manual_override"] = True
            overrides[str(item["path"])] = str(item["reason"])
    return overrides


def validate_protected_changes(before: dict[str, Any], after: dict[str, Any]) -> list[str]:
    overrides = manual_override_paths(after)
    errors: list[str] = []
    if before.get("project_id") != after.get("project_id") and "project_id" not in overrides:
        errors.append("Protected field 'project_id' changed without a manual_overrides reason.")

    def changed_paths(old: Any, new: Any, prefix: str) -> list[str]:
        if old == new:
            return []
        if isinstance(old, dict) and isinstance(new, dict):
            paths: list[str] = []
            for key in sorted(set(old) | set(new)):
                paths.extend(changed_paths(old.get(key), new.get(key), f"{prefix}.{key}"))
            return paths
        return [prefix]

    for path in changed_paths(before.get("protected_records"), after.get("protected_records"), "protected_records"):
        authorized = any(path == override or path.startswith(override + ".") for override in overrides)
        if not authorized:
            errors.append(f"Protected field {path!r} changed without a manual_overrides reason.")
    return errors


def entity_map(value: Any) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    if isinstance(value, list):
        for item in value:
            if isinstance(item, dict) and str(item.get("id", "")):
                result[str(item["id"])] = item
    return result


def compact(value: Any, limit: int = 240) -> str:
    if value is None:
        return "—"
    if isinstance(value, str):
        text = value
    else:
        text = json.dumps(value, ensure_ascii=False, sort_keys=True)
    text = text.replace("\n", " ")
    return text if len(text) <= limit else text[: limit - 1] + "…"


def classify_change(path: str, kind: str, before: Any, after: Any) -> tuple[str, str, str]:
    lower = path.lower()
    if kind == "merged":
        return "MEDIUM", "Merges tasks and may remove either redundant work or an independent evidence role.", "Verify that the retained task preserves every required observable and dependency."
    if kind == "split":
        return "MEDIUM", "Splits a task into distinct evidence or execution units and increases workflow complexity.", "Confirm that the split clarifies evidence ownership without duplicating work."
    if kind == "replaced":
        return "HIGH", "Replaces a task or method and can change comparability, compatibility, or evidence meaning.", "Verify output equivalence, parameter consistency, and evidence coverage before acceptance."
    if lower.endswith("user_notes") or lower.endswith("modification_reason"):
        return "LOW", "Changes notes or explanation without changing scientific content.", "Keep the rationale with the version record."
    if lower.startswith("research_goal.core_question") or lower.startswith("research_goal.target_conclusion"):
        return "HIGH", "Changes the scientific question or target conclusion and may require redesigning the evidence chain.", "Re-audit every core task and control against the revised goal."
    if lower.startswith("research_goal.research_object"):
        return "CRITICAL", "Changes the principal research object and can invalidate the entire model and comparison design.", "Rebuild the model, control, parameter, and evidence assumptions before approval."
    if lower.startswith("controls") and kind == "deleted":
        return "HIGH", "Removes a comparison basis required by one or more difference quantities.", "Restore the control or remove/redefine dependent observables explicitly."
    if lower.startswith("tasks") and kind in {"deleted", "merged"}:
        task = before if isinstance(before, dict) else {}
        sci = task.get("scientific_weight", {}).get("value", 0) if isinstance(task.get("scientific_weight"), dict) else 0
        necessity = str(task.get("necessity", "")).lower()
        if sci >= 80 or "core" in necessity or "necessary" in necessity or "核心" in necessity or "必要" in necessity:
            return "HIGH", "Deletes a high-value or necessary task and may remove direct evidence.", "Check for an explicit substitute and an intact evidence-chain path."
        return "MEDIUM", "Deletes a task and reduces evidence depth or implementation work.", "Confirm that the task is redundant or nonessential before acceptance."
    if lower.startswith("tasks") and kind in {"added", "split"}:
        return "MEDIUM", "Adds evidence and implementation work; scientific value depends on independence from existing tasks.", "Run redundancy and necessity checks before retaining it."
    if any(token in lower for token in (".software", ".module", ".method")):
        return "MEDIUM", "May change implementation defaults, numerical behavior, compatibility, and post-processing.", "Verify capability, version, parameter equivalence, and data interoperability."
    if any(token in lower for token in ("target_parameters", "controls", "prerequisites", "downstream_dependencies", "evidence_role", "execution_route")):
        return "HIGH", "Changes the observable, comparison basis, dependency, or evidence function.", "Re-run comparability, dependency, and evidence-integrity checks."
    if any(token in lower for token in ("scientific_weight", "workload_weight", "priority")):
        return "MEDIUM", "Changes task evaluation or ordering but not necessarily its scientific definition.", "Confirm the component rationales and recalculate the derived indices."
    if kind in {"added", "deleted"}:
        return "MEDIUM", "Changes the plan scope or comparison structure.", "Check downstream dependencies and evidence coverage."
    return "LOW", "Changes implementation detail or presentation with limited direct effect on the central conclusion.", "Retain the change if consistency checks pass."


def make_change(
    path: str,
    kind: str,
    before: Any,
    after: Any,
    reason: str,
) -> dict[str, Any]:
    level, rationale, recommendation = classify_change(path, kind, before, after)
    return {
        "path": path,
        "kind": kind,
        "before": before,
        "after": after,
        "user_reason": reason,
        "impact_level": level,
        "impact_reason": rationale,
        "recommendation": recommendation,
    }


def recursive_diff(before: Any, after: Any, path: str, reason: str, changes: list[dict[str, Any]]) -> None:
    if before == after:
        return
    if isinstance(before, dict) and isinstance(after, dict):
        for key in sorted(set(before) | set(after)):
            child_path = f"{path}.{key}" if path else key
            if key not in before:
                changes.append(make_change(child_path, "added", None, after[key], reason))
            elif key not in after:
                changes.append(make_change(child_path, "deleted", before[key], None, reason))
            else:
                recursive_diff(before[key], after[key], child_path, reason, changes)
        return
    changes.append(make_change(path, "changed", before, after, reason))


def compare_entity_list(field: str, before: Any, after: Any, reason: str) -> list[dict[str, Any]]:
    changes: list[dict[str, Any]] = []
    old = entity_map(before)
    new = entity_map(after)
    if len(old) != len(before or []) or len(new) != len(after or []):
        recursive_diff(before, after, field, reason, changes)
        return changes
    for identifier in sorted(set(old) | set(new)):
        path = f"{field}[{identifier}]"
        if identifier not in old:
            changes.append(make_change(path, "added", None, new[identifier], reason))
        elif identifier not in new:
            changes.append(make_change(path, "deleted", old[identifier], None, reason))
        else:
            recursive_diff(old[identifier], new[identifier], path, reason, changes)
    return changes


def compare_plans(before: dict[str, Any], after: dict[str, Any], reason: str) -> list[dict[str, Any]]:
    changes: list[dict[str, Any]] = []
    ignored = {"version_record", "plan_version", "generated_at", "change_intents"}
    for key in sorted((set(before) | set(after)) - ignored):
        if key in ENTITY_LISTS:
            changes.extend(compare_entity_list(key, before.get(key, []), after.get(key, []), reason))
        elif key not in before:
            changes.append(make_change(key, "added", None, after[key], reason))
        elif key not in after:
            changes.append(make_change(key, "deleted", before[key], None, reason))
        else:
            recursive_diff(before[key], after[key], key, reason, changes)
    intents = after.get("change_intents", []) if isinstance(after.get("change_intents"), list) else []
    for index, intent in enumerate(intents):
        if not isinstance(intent, dict):
            continue
        kind = str(intent.get("type", "changed")).lower()
        if kind not in {"merged", "split", "replaced"}:
            continue
        changes.append(
            make_change(
                f"change_intents[{index}]",
                kind,
                intent.get("source_task_ids"),
                intent.get("target_task_ids"),
                str(intent.get("reason") or reason),
            )
        )
    return changes


def task_weights(plan: dict[str, Any]) -> dict[str, dict[str, float]]:
    result: dict[str, dict[str, float]] = {}
    for task in plan.get("tasks", []):
        if not isinstance(task, dict):
            continue
        sci = task.get("scientific_weight", {})
        work = task.get("workload_weight", {})
        result[str(task.get("id", ""))] = {
            "scientific": float(sci.get("value", 0)) if isinstance(sci, dict) else 0,
            "workload": float(work.get("value", 0)) if isinstance(work, dict) else 0,
        }
    return result


def evidence_gaps(plan: dict[str, Any]) -> list[dict[str, Any]]:
    tasks = {
        task_id: task
        for task_id, task in entity_map(plan.get("tasks", [])).items()
        if str(task.get("status", "")).strip().lower() not in {"deleted", "delete", "cancelled", "canceled"}
    }
    gaps: list[dict[str, Any]] = []
    for link in plan.get("evidence_chain", []):
        if not isinstance(link, dict):
            continue
        active = [task_id for task_id in link.get("task_ids", []) if str(task_id) in tasks]
        if link.get("required", False) and not active:
            gaps.append(
                {
                    "id": link.get("id"),
                    "role": link.get("role"),
                    "supports": link.get("supports"),
                    "reason": "A required evidence-chain node has no remaining task.",
                }
            )
    return gaps


def keyword_result_impacts(before: dict[str, Any], after: dict[str, Any], changes: list[dict[str, Any]]) -> list[str]:
    impacts: list[str] = []
    deleted_tasks = [change.get("before", {}) for change in changes if change["kind"] == "deleted" and change["path"].startswith("tasks[")]
    remaining_text = json.dumps(after.get("tasks", []), ensure_ascii=False).lower()
    for task in deleted_tasks:
        text = json.dumps(task, ensure_ascii=False).lower()
        if (
            "charge density difference" in text or "电荷密度差" in text
        ) and any(token in remaining_text for token in ("bader", "hirshfeld", "cm5", "npa", "定量电荷")):
            impacts.append("删除电荷密度差后仍可定量判断电荷转移方向和数量，但失去电荷重排位置的空间证据。")
        if any(token in text for token in ("bader", "hirshfeld", "cm5", "npa", "定量电荷")) and (
            "charge density difference" in remaining_text or "电荷密度差" in remaining_text
        ):
            impacts.append("删除定量电荷分析后仍可观察电子积累与耗尽区域，但无法可靠给出电子转移数量。")
        if "pdos" in text and "dos" in remaining_text:
            impacts.append("删除 PDOS 后仍可判断整体电子态变化，但难以识别具体元素、原子或轨道贡献。")
        if "cohp" in text:
            impacts.append("删除 COHP 对稳定性结论的直接影响通常有限，但削弱具体成键与反键贡献的解释。")
        if any(token in text for token in ("adsorption energy", "binding energy", "reaction energy", "吸附能", "结合能", "反应能")):
            impacts.append("删除核心能量参数会使相应热力学稳定性或发生倾向失去直接依据。")
    if any(change["kind"] == "deleted" and change["path"].startswith("controls[") for change in changes):
        impacts.append("删除对照体系可能使差值参数无法计算，并使相关结果失去统一比较基础。")
    if any(change["kind"] == "added" and change["path"].startswith("tasks[") for change in changes):
        impacts.append("新增任务增加潜在证据和工作量；只有其证据功能独立且不可由现有任务替代时才具有合理科学价值。")
    if any(any(token in change["path"].lower() for token in (".software", ".module", ".method")) for change in changes):
        impacts.append("软件或方法变化可能影响默认设置、数值精度、文件兼容性和后处理流程；直接比较前需证明计算条件等价。")
    return list(dict.fromkeys(impacts))


def workload_summary(before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
    old_tasks = before.get("tasks", []) if isinstance(before.get("tasks"), list) else []
    new_tasks = after.get("tasks", []) if isinstance(after.get("tasks"), list) else []
    old_weights = task_weights(before)
    new_weights = task_weights(after)
    old_total = sum(item["workload"] for item in old_weights.values())
    new_total = sum(item["workload"] for item in new_weights.values())
    delta = new_total - old_total
    if abs(delta) < 5 and len(old_tasks) == len(new_tasks):
        label = "基本不变"
    elif delta <= -20 or len(new_tasks) <= len(old_tasks) - 2:
        label = "明显降低"
    elif delta < 0:
        label = "降低"
    elif delta >= 20 or len(new_tasks) >= len(old_tasks) + 2:
        label = "明显增加"
    else:
        label = "增加"
    return {
        "label": label,
        "relative_weight_before": round(old_total, 2),
        "relative_weight_after": round(new_total, 2),
        "relative_weight_delta": round(delta, 2),
        "task_count_before": len(old_tasks),
        "task_count_after": len(new_tasks),
        "model_count_before": len(before.get("systems", []) or []),
        "model_count_after": len(after.get("systems", []) or []),
        "control_count_before": len(before.get("controls", []) or []),
        "control_count_after": len(after.get("controls", []) or []),
        "note": "Weights are relative within this plan and are not runtime, memory, or storage estimates.",
    }


def overall_impact(changes: list[dict[str, Any]], gaps: list[dict[str, Any]], errors: list[str]) -> tuple[str, str]:
    if errors:
        return "CRITICAL", "导致方案无法继续执行的变化"
    if gaps or any(change["impact_level"] == "CRITICAL" for change in changes):
        return "CRITICAL", "导致方案无法继续执行的变化"
    if any(change["impact_level"] == "HIGH" for change in changes):
        if any(change["kind"] == "deleted" for change in changes):
            return "HIGH", "明显削弱证据链的变化"
        return "HIGH", "可能改变最终结论的变化"
    if any(change["impact_level"] == "MEDIUM" for change in changes):
        if any(any(token in change["path"].lower() for token in (".method", ".software", "target_parameters")) for change in changes):
            return "MEDIUM", "影响数值精度但通常不改变趋势的变化"
        return "MEDIUM", "影响部分机理解释完整性的变化"
    return "LOW", "不影响核心结论的变化"


def analyze_comparison(
    before: dict[str, Any],
    after: dict[str, Any],
    reason: str,
    validation_errors: list[str],
    validation_warnings: list[str],
) -> dict[str, Any]:
    changes = compare_plans(before, after, reason)
    gaps = evidence_gaps(after)
    level, category = overall_impact(changes, gaps, validation_errors)
    return {
        "generated_at": utc_now(),
        "from_version": before.get("plan_version"),
        "to_version": after.get("plan_version"),
        "user_modification_summary": reason,
        "changes": changes,
        "weight_changes": {
            "before": task_weights(before),
            "after": task_weights(after),
        },
        "workload_change": workload_summary(before, after),
        "evidence_gaps": gaps,
        "result_impacts": keyword_result_impacts(before, after, changes),
        "validation_errors": validation_errors,
        "validation_warnings": validation_warnings,
        "overall_impact_level": level,
        "impact_category": category,
        "final_conclusion_impact": (
            "The plan cannot be approved until validation errors and required evidence gaps are resolved."
            if validation_errors or gaps
            else "See the per-change impact reasons; approval remains a user decision."
        ),
    }


def markdown_table(rows: list[list[Any]], headers: list[str]) -> str:
    def cell(value: Any) -> str:
        return compact(value).replace("|", "\\|")

    lines = ["| " + " | ".join(headers) + " |", "| " + " | ".join("---" for _ in headers) + " |"]
    lines.extend("| " + " | ".join(cell(value) for value in row) + " |" for row in rows)
    return "\n".join(lines)


def render_plan_markdown(plan: dict[str, Any]) -> str:
    goal = plan.get("research_goal", {}) if isinstance(plan.get("research_goal"), dict) else {}
    lines = [
        f"# Stage 1 Plan {plan.get('plan_version', '')}",
        "",
        f"- Project: `{plan.get('project_id', '')}`",
        f"- Generated: {plan.get('generated_at', '')}",
        f"- Modification source: {plan.get('version_record', {}).get('modification_source', '')}",
        "",
        "## 研究目标",
        "",
        f"- 研究对象：{goal.get('research_object', '')}",
        f"- 比较对象：{goal.get('comparison_object', '')}",
        f"- 实验现象：{goal.get('experimental_phenomenon', '')}",
        f"- 核心问题：{goal.get('core_question', '')}",
        f"- 目标结论：{goal.get('target_conclusion', '')}",
        "",
        "## 科学问题拆分",
        "",
        markdown_table(
            [[item.get("id"), item.get("question"), item.get("evidence_target"), item.get("depends_on")] for item in plan.get("scientific_questions", []) if isinstance(item, dict)],
            ["ID", "问题", "证据目标", "依赖"],
        ),
        "",
        "## 计算体系与对照组",
        "",
        "### 研究体系",
        "",
        markdown_table(
            [[item.get("id"), item.get("name"), item.get("role"), item.get("description")] for item in plan.get("systems", []) if isinstance(item, dict)],
            ["ID", "名称", "角色", "说明"],
        ),
        "",
        "### 对照体系",
        "",
        markdown_table(
            [[item.get("id"), item.get("name"), item.get("isolates"), item.get("consistency_requirements")] for item in plan.get("controls", []) if isinstance(item, dict)],
            ["ID", "名称", "隔离变量", "一致性条件"],
        ),
        "",
        "## 总体证据链",
        "",
        markdown_table(
            [[item.get("id"), item.get("role"), item.get("task_ids"), item.get("supports"), item.get("required")] for item in plan.get("evidence_chain", []) if isinstance(item, dict)],
            ["ID", "证据功能", "任务", "支持结论", "必需"],
        ),
        "",
        "## 具体计算方案",
        "",
    ]
    for task in plan.get("tasks", []):
        if not isinstance(task, dict):
            continue
        raw_scientific = task.get("scientific_weight")
        raw_workload = task.get("workload_weight")
        scientific: dict[str, Any] = raw_scientific if isinstance(raw_scientific, dict) else {}
        workload: dict[str, Any] = raw_workload if isinstance(raw_workload, dict) else {}
        lines.extend(
            [
                f"### {task.get('id', '')} — {task.get('name', '')}",
                "",
                f"- 科学子问题：{task.get('scientific_question_id', '')}",
                f"- 体系/对照：{compact(task.get('systems'))} / {compact(task.get('controls'))}",
                f"- 软件/模块/方法：{task.get('software', '')} / {task.get('module', '')} / {task.get('method', '')}",
                f"- 目标参数：{compact(task.get('target_parameters'))}",
                f"- 目标数据形式：{compact(task.get('target_data_forms'))}",
                f"- 科学含义：{task.get('scientific_meaning', '')}",
                f"- 支持结论：{compact(task.get('supported_conclusions'))}",
                f"- 实验对应：{compact(task.get('experimental_correspondence'))}",
                f"- 佐证关系：{compact(task.get('corroborates_with'))}",
                f"- 前置/后续：{compact(task.get('prerequisites'))} / {compact(task.get('downstream_dependencies'))}",
                f"- 证据功能：{task.get('evidence_role', '')}",
                f"- 科学权重：{scientific.get('value', '')}",
                f"- 工作量权重：{workload.get('value', '')}",
                f"- 执行优先指数：{task.get('execution_priority_index', '')}",
                f"- 结果敏感性/不可替代性：{task.get('result_sensitivity', '')} / {task.get('irreplaceability', '')}",
                f"- 优先级/必要性：{task.get('priority', '')} / {task.get('necessity', '')}",
                f"- 替代方法：{compact(task.get('alternatives'))}",
                f"- 重复性判断：{task.get('redundancy', '')}",
                f"- 状态/用户备注：{task.get('status', '')} / {task.get('user_notes', '')}",
                "",
            ]
        )
    lines.extend(
        [
            "## 重复性审查",
            "",
            compact(plan.get("redundancy_review")),
            "",
            "## 最终执行路线",
            "",
            compact(plan.get("execution_route"), 4000),
            "",
            "> 本文件仅记录第一阶段方案，不是正式计算输入文件，也不授权运行或提交计算。",
            "",
        ]
    )
    return "\n".join(lines)


def render_impact_markdown(analysis: dict[str, Any]) -> str:
    changes = analysis.get("changes", [])
    rows = [
        [
            change.get("kind"),
            change.get("path"),
            change.get("before"),
            change.get("after"),
            change.get("user_reason"),
            change.get("impact_level"),
            change.get("impact_reason"),
            change.get("recommendation"),
        ]
        for change in changes
    ]
    weight_rows: list[list[Any]] = []
    before_weights = analysis.get("weight_changes", {}).get("before", {})
    after_weights = analysis.get("weight_changes", {}).get("after", {})
    for task_id in sorted(set(before_weights) | set(after_weights)):
        old = before_weights.get(task_id, {})
        new = after_weights.get(task_id, {})
        weight_rows.append(
            [
                task_id,
                old.get("scientific"),
                new.get("scientific"),
                round(new.get("scientific", 0) - old.get("scientific", 0), 2),
                old.get("workload"),
                new.get("workload"),
                round(new.get("workload", 0) - old.get("workload", 0), 2),
            ]
        )
    workload = analysis.get("workload_change", {})
    lines = [
        "# Stage 1 修改影响分析",
        "",
        f"- 方案版本：{analysis.get('from_version')} → {analysis.get('to_version')}",
        f"- 生成时间：{analysis.get('generated_at')}",
        f"- 用户修改摘要：{analysis.get('user_modification_summary')}",
        f"- 总体风险等级：**{analysis.get('overall_impact_level')}**",
        f"- 影响类型：{analysis.get('impact_category')}",
        "",
        "## 任务与参数差异",
        "",
        markdown_table(
            rows,
            ["类型", "路径", "修改前", "修改后", "修改理由", "影响等级", "影响原因", "系统建议"],
        ) if rows else "未检测到内容变化。",
        "",
        "## 软件、方法与目标参数差异",
        "",
        "参见上表中 `.software`、`.module`、`.method` 与 `target_parameters` 路径；每项变化均保留前后值与兼容性建议。",
        "",
        "## 科学权重与工作量权重变化",
        "",
        markdown_table(weight_rows, ["任务", "科学前", "科学后", "科学Δ", "工作前", "工作后", "工作Δ"]),
        "",
        f"总体工作量变化：**{workload.get('label')}**；任务数 {workload.get('task_count_before')} → {workload.get('task_count_after')}，体系数 {workload.get('model_count_before')} → {workload.get('model_count_after')}，对照数 {workload.get('control_count_before')} → {workload.get('control_count_after')}。",
        "",
        f"> {workload.get('note', '')}",
        "",
        "## 证据链变化",
        "",
    ]
    gaps = analysis.get("evidence_gaps", [])
    if gaps:
        lines.extend([f"- **缺口 {gap.get('id')}**：{gap.get('role')} — {gap.get('reason')}" for gap in gaps])
    else:
        lines.append("- 未检测到显式标记为必需的证据节点完全失去任务支撑；仍需结合每项修改的证据功能复核解释深度。")
    lines.extend(["", "## 预期结果影响", ""])
    impacts = analysis.get("result_impacts", [])
    lines.extend([f"- {item}" for item in impacts] or ["- 未检测到预设规则覆盖的特定结果影响；按逐项影响原因解释。"])
    lines.extend(
        [
            "",
            "## 最终结论影响",
            "",
            analysis.get("final_conclusion_impact", ""),
            "",
            "## 格式、逻辑与风险检查",
            "",
        ]
    )
    lines.extend([f"- **错误：** {item}" for item in analysis.get("validation_errors", [])])
    lines.extend([f"- **警告：** {item}" for item in analysis.get("validation_warnings", [])])
    if not analysis.get("validation_errors") and not analysis.get("validation_warnings"):
        lines.append("- 格式、依赖、对照引用、证据链引用与权重结构检查通过。")
    lines.extend(
        [
            "",
            "## 系统建议",
            "",
            "系统仅提供保留、删除、替换、合并、降级或延后的建议，不自动删除用户任务。最终是否接受修改由用户决定。",
            "",
        ]
    )
    return "\n".join(lines)


def plan_for_version(
    source: dict[str, Any],
    version: str,
    modification_source: str,
    reason: str,
    before_status: str | None,
    after_status: str,
) -> dict[str, Any]:
    plan = copy.deepcopy(source)
    plan["stage"] = 1
    plan["plan_version"] = version
    plan["generated_at"] = utc_now()
    plan["version_record"] = {
        "version": version,
        "generated_at": plan["generated_at"],
        "modification_source": modification_source,
        "modification_content": reason,
        "modification_reason": reason,
        "status_before": before_status,
        "status_after": after_status,
    }
    return plan


def initialize(planning_dir: Path, source_plan_path: Path) -> dict[str, Any]:
    planning_dir.mkdir(parents=True, exist_ok=True)
    if version_json_path(planning_dir, "v001").exists() or status_path(planning_dir).exists():
        raise Stage1Error("Stage-1 review already exists; initialization will not overwrite history.")
    source = read_json(source_plan_path)
    if not isinstance(source, dict):
        raise Stage1Error("Initial plan must be a JSON object.")
    plan = plan_for_version(source, "v001", "SYSTEM_INITIAL_PLAN", "Initial stage-1 plan", None, WAITING_FOR_USER_APPROVAL)
    errors, warnings = validate_and_score_plan(plan)
    if errors:
        raise Stage1Error("Initial plan validation failed:\n- " + "\n- ".join(errors))
    write_json(version_json_path(planning_dir, "v001"), plan)
    write_text(version_md_path(planning_dir, "v001"), render_plan_markdown(plan))
    status = {
        "project_id": plan["project_id"],
        "stage": 1,
        "status": WAITING_FOR_USER_APPROVAL,
        "current_candidate_version": "v001",
        "latest_version": "v001",
        "previous_version": None,
        "previous_valid_version": "v001",
        "approved_version": None,
        "updated_at": utc_now(),
        "validation_errors": [],
        "validation_warnings": warnings,
        "review_page_generated": True,
        "stage2_access": False,
    }
    write_json(status_path(planning_dir), status)
    write_json(
        log_path(planning_dir),
        [
            {
                "event": "INITIALIZED",
                "timestamp": utc_now(),
                "version": "v001",
                "source": "SYSTEM_INITIAL_PLAN",
                "reason": "Initial stage-1 plan",
                "status_before": None,
                "status_after": WAITING_FOR_USER_APPROVAL,
            }
        ],
    )
    write_text(
        planning_dir / "stage1_impact_analysis.md",
        "# Stage 1 修改影响分析\n\n初始方案尚未发生用户修改。提交修改后生成版本间影响分析。\n",
    )
    ensure_review_html(planning_dir)
    return status


def submit_plan(
    planning_dir: Path,
    edited_plan: dict[str, Any],
    reason: str,
    modification_source: str = "USER_EDIT",
) -> dict[str, Any]:
    if not reason.strip():
        raise Stage1Error("A modification reason is required.")
    status = load_status(planning_dir)
    if status["status"] == APPROVED:
        raise Stage1Error("The approved baseline is immutable; start a separately authorized revision workflow.")
    before_status = status["status"]
    before_version = status["current_candidate_version"]
    before = load_plan(planning_dir, before_version)
    new_version = next_version(status)
    after = plan_for_version(
        edited_plan,
        new_version,
        modification_source,
        reason,
        before_status,
        IMPACT_ANALYSIS_READY,
    )

    status["status"] = USER_EDITED_PENDING_ANALYSIS
    status["updated_at"] = utc_now()
    status["stage2_access"] = False
    write_json(status_path(planning_dir), status)

    errors, warnings = validate_and_score_plan(after)
    errors.extend(validate_protected_changes(before, after))
    modification_changes = compare_plans(before, after, reason)
    after["version_record"]["modification_content"] = [
        {"kind": item["kind"], "path": item["path"]} for item in modification_changes
    ]
    write_json(version_json_path(planning_dir, new_version), after)
    write_text(version_md_path(planning_dir, new_version), render_plan_markdown(after))
    analysis = analyze_comparison(before, after, reason, errors, warnings)
    report_name = f"stage1_impact_analysis_{before_version}_to_{new_version}.md"
    report_text = render_impact_markdown(analysis)
    write_text(planning_dir / report_name, report_text)
    write_text(planning_dir / "stage1_impact_analysis.md", report_text)

    status.update(
        {
            "status": IMPACT_ANALYSIS_READY,
            "current_candidate_version": new_version,
            "latest_version": new_version,
            "previous_version": before_version,
            "previous_valid_version": before_version if not status.get("validation_errors") else status.get("previous_valid_version", before_version),
            "updated_at": utc_now(),
            "validation_errors": errors,
            "validation_warnings": warnings,
            "last_impact_report": report_name,
            "last_impact_level": analysis["overall_impact_level"],
            "stage2_access": False,
        }
    )
    write_json(status_path(planning_dir), status)
    append_log(
        planning_dir,
        {
            "event": "MODIFICATION_ANALYZED",
            "timestamp": utc_now(),
            "version": new_version,
            "previous_version": before_version,
            "source": modification_source,
            "reason": reason,
            "changes": [
                {"kind": item["kind"], "path": item["path"], "impact_level": item["impact_level"]}
                for item in analysis["changes"]
            ],
            "status_before": USER_EDITED_PENDING_ANALYSIS,
            "status_after": IMPACT_ANALYSIS_READY,
        },
    )
    return {"status": status, "analysis": analysis}


def transition(planning_dir: Path, action: str, reason: str = "", version: str | None = None, confirmed_by: str = "user") -> dict[str, Any]:
    status = load_status(planning_dir)
    current_status = status["status"]
    if current_status == APPROVED:
        raise Stage1Error("Stage 1 is already approved and its baseline is immutable.")

    if action == "accept":
        if current_status not in {IMPACT_ANALYSIS_READY, WAITING_FOR_USER_APPROVAL}:
            raise Stage1Error("Accept is allowed after impact analysis or after reviewing an unchanged initial candidate.")
        if status.get("validation_errors"):
            raise Stage1Error("Resolve validation errors before accepting the modified plan.")
        status["status"] = WAITING_FOR_FINAL_APPROVAL
        status["previous_valid_version"] = status["current_candidate_version"]
        status["project_id"] = load_plan(planning_dir, status["current_candidate_version"]).get("project_id")
        event = "MODIFICATION_ACCEPTED"
    elif action == "continue":
        if current_status not in {IMPACT_ANALYSIS_READY, WAITING_FOR_FINAL_APPROVAL, WAITING_FOR_USER_APPROVAL}:
            raise Stage1Error("Continue editing is unavailable in the current state.")
        status["status"] = WAITING_FOR_USER_APPROVAL
        event = "CONTINUE_EDITING"
    elif action == "reject":
        if current_status != IMPACT_ANALYSIS_READY:
            raise Stage1Error("Reject is allowed only after impact analysis is ready.")
        rejected = status["current_candidate_version"]
        fallback = status.get("previous_valid_version") or status.get("previous_version")
        if not fallback:
            raise Stage1Error("No previous version is available.")
        status["rejected_version"] = rejected
        status["current_candidate_version"] = fallback
        status["status"] = WAITING_FOR_FINAL_APPROVAL
        status["validation_errors"] = []
        event = "MODIFICATION_REJECTED"
    elif action == "restore":
        target = version or status.get("previous_version")
        if not target:
            raise Stage1Error("No version was supplied for restoration.")
        source_plan = load_plan(planning_dir, target)
        result = submit_plan(planning_dir, source_plan, reason or f"Restore {target}", "RESTORE")
        append_log(
            planning_dir,
            {
                "event": "VERSION_RESTORED_AS_NEW_VERSION",
                "timestamp": utc_now(),
                "source_version": target,
                "new_version": result["status"]["current_candidate_version"],
                "reason": reason or f"Restore {target}",
                "status_after": IMPACT_ANALYSIS_READY,
            },
        )
        return result
    elif action == "approve":
        raise Stage1Error("Final approval must be submitted through the hash-bound browser review command.")
    else:
        raise Stage1Error(f"Unknown action: {action}")

    old_status = current_status
    status["updated_at"] = utc_now()
    status["stage2_access"] = False
    write_json(status_path(planning_dir), status)
    append_log(
        planning_dir,
        {
            "event": event,
            "timestamp": utc_now(),
            "version": status["current_candidate_version"],
            "reason": reason,
            "status_before": old_status,
            "status_after": status["status"],
        },
    )
    return {"status": status}


def approve(planning_dir: Path, confirmed_by: str, reason: str) -> dict[str, Any]:
    targets = [
        planning_dir / "stage1_plan_approved.json",
        planning_dir / "stage1_plan_approved.md",
        planning_dir / "stage1_approval_record.json",
    ]
    if any(path.exists() for path in targets):
        raise Stage1Error("Approved baseline files already exist and will not be overwritten.")
    status = load_status(planning_dir)
    version = status["current_candidate_version"]
    plan = load_plan(planning_dir, version)
    errors, warnings = validate_and_score_plan(plan)
    missing_review_artifacts = [
        name
        for name in ("stage1_review.html", "stage1_status.json", "stage1_change_log.json", "stage1_impact_analysis.md", f"stage1_plan_{version}.md")
        if not (planning_dir / name).exists()
    ]
    if missing_review_artifacts:
        errors.append("Missing review artifacts: " + ", ".join(missing_review_artifacts) + ".")
    gaps = evidence_gaps(plan)
    if gaps:
        errors.append("Required evidence-chain gaps remain: " + ", ".join(str(item.get("id")) for item in gaps) + ".")
    if errors:
        raise Stage1Error("Final plan validation failed:\n- " + "\n- ".join(errors))
    write_json(targets[0], plan)
    write_text(targets[1], render_plan_markdown(plan))
    tasks = [task for task in plan.get("tasks", []) if isinstance(task, dict)]
    log = read_json(log_path(planning_dir))
    record = {
        "project_id": plan.get("project_id"),
        "stage": 1,
        "approved_plan_version": version,
        "confirmed_at": utc_now(),
        "confirmed_by": confirmed_by or "user",
        "confirmation_reason": reason,
        "user_confirmation_status": "CONFIRMED",
        "core_research_goal": plan.get("research_goal"),
        "retained_core_tasks": [
            {"id": task.get("id"), "name": task.get("name")}
            for task in tasks
            if str(task.get("necessity", "")).lower() in {"core", "necessary", "核心", "必要"}
            or (task.get("scientific_weight", {}) if isinstance(task.get("scientific_weight"), dict) else {}).get("value", 0) >= 70
        ],
        "deleted_or_replaced_tasks": [
            item
            for entry in log
            for item in entry.get("changes", [])
            if item.get("kind") == "deleted" or "method" in item.get("path", "") or "software" in item.get("path", "")
        ],
        "major_scientific_weights": {
            str(task.get("id")): (task.get("scientific_weight", {}) if isinstance(task.get("scientific_weight"), dict) else {}).get("value") for task in tasks
        },
        "major_workload_weights": {
            str(task.get("id")): (task.get("workload_weight", {}) if isinstance(task.get("workload_weight"), dict) else {}).get("value") for task in tasks
        },
        "key_risks": plan.get("risks", []),
        "evidence_chain_integrity": "complete" if not evidence_gaps(plan) else "gaps_detected",
        "validation_warnings": warnings,
        "approved_plan_sha256": sha256(targets[0]),
    }
    write_json(targets[2], record)
    old_status = status["status"]
    status.update(
        {
            "status": APPROVED,
            "approved_version": version,
            "approved_at": record["confirmed_at"],
            "updated_at": record["confirmed_at"],
            "stage2_access": True,
            "validation_errors": [],
        }
    )
    write_json(status_path(planning_dir), status)
    append_log(
        planning_dir,
        {
            "event": "FINAL_APPROVAL",
            "timestamp": record["confirmed_at"],
            "version": version,
            "confirmed_by": confirmed_by or "user",
            "reason": reason,
            "status_before": old_status,
            "status_after": APPROVED,
        },
    )
    return {"status": status, "approval_record": record}


def browser_review(
    planning_dir: Path,
    project_dir: Path,
    title: str,
    start_port: int,
    timeout_seconds: float | None,
) -> dict[str, Any]:
    """Block on a hash-bound browser decision and route the stage-1 result."""

    status = load_status(planning_dir)
    if status["status"] != WAITING_FOR_FINAL_APPROVAL:
        raise Stage1Error("Browser review is allowed only after the candidate is ready for final approval.")
    if status.get("validation_errors"):
        raise Stage1Error("Resolve validation errors before starting browser review.")
    version = status["current_candidate_version"]
    content_file = version_json_path(planning_dir, version)
    request_payload = prepare_review_request(project_dir, "stage1", title, content_file)
    resume_status = status["status"]
    status.update(
        {
            "status": WAITING_FOR_REVIEW_DECISION,
            "updated_at": utc_now(),
            "stage2_access": False,
            "review_request_id": request_payload["request_id"],
            "review_content_hash": request_payload["content_hash"],
            "review_resume_status": resume_status,
            "review_comment": None,
        }
    )
    write_json(status_path(planning_dir), status)
    append_log(
        planning_dir,
        {
            "event": "BROWSER_REVIEW_REQUESTED",
            "timestamp": utc_now(),
            "version": version,
            "request_id": request_payload["request_id"],
            "content_hash": request_payload["content_hash"],
            "status_before": resume_status,
            "status_after": WAITING_FOR_REVIEW_DECISION,
        },
    )
    try:
        decision = run_review_session(
            project_dir,
            request_payload,
            start_port=start_port,
            decision_timeout_seconds=timeout_seconds,
        )
    except ReviewWorkflowError as exc:
        status = load_status(planning_dir)
        status.update({"status": WAITING_FOR_REVIEW_DECISION, "updated_at": utc_now(), "last_review_error": str(exc)})
        write_json(status_path(planning_dir), status)
        raise Stage1Error(str(exc)) from exc

    status = load_status(planning_dir)
    status.update(
        {
            "review_decision": decision["decision"],
            "review_comment": decision.get("comment", ""),
            "review_confirmed_at": decision["confirmed_at"],
            "updated_at": utc_now(),
        }
    )
    if decision["decision"] == "approved":
        status["status"] = resume_status
        write_json(status_path(planning_dir), status)
        return approve(planning_dir, "browser_user", decision.get("comment", ""))
    if decision["decision"] == "revision_required":
        status.update({"status": WAITING_FOR_USER_APPROVAL, "stage2_access": False})
        event = "BROWSER_REVISION_REQUIRED"
    else:
        status.update({"status": STAGE1_REVIEW_REJECTED, "stage2_access": False})
        event = "BROWSER_REVIEW_REJECTED"
    write_json(status_path(planning_dir), status)
    append_log(
        planning_dir,
        {
            "event": event,
            "timestamp": utc_now(),
            "version": version,
            "request_id": decision["request_id"],
            "content_hash": decision["content_hash"],
            "comment": decision.get("comment", ""),
            "status_before": WAITING_FOR_REVIEW_DECISION,
            "status_after": status["status"],
        },
    )
    return {"status": status, "review_decision": decision}


def draft_path(planning_dir: Path) -> Path:
    return planning_dir / "stage1_plan_draft.json"


def check_edited_plan(planning_dir: Path, edited_plan: dict[str, Any]) -> dict[str, Any]:
    """Validate an editor payload without creating a version or changing workflow state."""

    status = load_status(planning_dir)
    candidate = load_plan(planning_dir, status["current_candidate_version"])
    checked = copy.deepcopy(edited_plan)
    errors, warnings = validate_and_score_plan(checked)
    protected_errors = validate_protected_changes(candidate, checked)
    errors.extend(protected_errors)
    return {
        "valid": not errors,
        "errors": errors,
        "warnings": warnings,
        "protected_errors": protected_errors,
        "checked_plan": checked,
        "base_version": status["current_candidate_version"],
        "status": status["status"],
    }


def save_draft(planning_dir: Path, edited_plan: dict[str, Any]) -> dict[str, Any]:
    """Persist an editable draft without creating a plan version or advancing state."""

    status = load_status(planning_dir)
    if status["status"] == APPROVED:
        raise Stage1Error("The approved baseline is immutable; a draft cannot overwrite it.")
    checked = check_edited_plan(planning_dir, edited_plan)
    record = {
        "schema_version": "1.0",
        "draft_status": "SAVED_NOT_SUBMITTED",
        "saved_at": utc_now(),
        "base_version": status["current_candidate_version"],
        "workflow_status": status["status"],
        "plan": edited_plan,
        "validation_errors": checked["errors"],
        "validation_warnings": checked["warnings"],
    }
    write_json(draft_path(planning_dir), record)
    return {
        "draft_status": record["draft_status"],
        "saved_at": record["saved_at"],
        "base_version": record["base_version"],
        "workflow_status": record["workflow_status"],
        "validation_errors": record["validation_errors"],
        "validation_warnings": record["validation_warnings"],
    }


def start_browser_review_process(planning_dir: Path) -> dict[str, Any]:
    """Start the existing hash-bound final-review command in an isolated process."""

    status = load_status(planning_dir)
    if status["status"] != WAITING_FOR_FINAL_APPROVAL:
        raise Stage1Error("Submit the candidate and accept its impact analysis before opening final review.")
    if status.get("validation_errors"):
        raise Stage1Error("Resolve validation errors before opening final review.")

    project_dir = planning_dir.parent.resolve()
    review_dir = project_dir / "review"
    lock_file = review_dir / "lock.json"
    if lock_file.exists():
        try:
            lock = read_json(lock_file)
        except (OSError, json.JSONDecodeError):
            lock = {}
        if lock.get("request_id") == status.get("review_request_id"):
            session_file = review_dir / "session.json"
            session = read_json(session_file) if session_file.exists() else {}
            return {
                "started": False,
                "already_running": True,
                "request_id": lock.get("request_id"),
                "stage": lock.get("stage"),
                "server_url": session.get("server_url"),
            }

    log_file = planning_dir / "stage1_review_gate.log"
    creation_flags = int(getattr(subprocess, "CREATE_NO_WINDOW", 0)) if os.name == "nt" else 0
    command = [
        sys.executable,
        str(Path(__file__).resolve()),
        "review",
        "--planning-dir",
        str(planning_dir.resolve()),
        "--project-dir",
        str(project_dir),
    ]
    with log_file.open("a", encoding="utf-8") as log_handle:
        process = subprocess.Popen(
            command,
            cwd=str(project_dir),
            stdin=subprocess.DEVNULL,
            stdout=log_handle,
            stderr=subprocess.STDOUT,
            creationflags=creation_flags,
        )

    deadline = time.monotonic() + 15.0
    last_status: dict[str, Any] = status
    while time.monotonic() < deadline:
        if process.poll() is not None:
            tail = log_file.read_text(encoding="utf-8", errors="replace")[-2000:] if log_file.exists() else ""
            raise Stage1Error(
                f"The browser review process exited before creating a request (exit {process.returncode}).\n{tail}"
            )
        last_status = load_status(planning_dir)
        request_id = last_status.get("review_request_id")
        if last_status.get("status") == WAITING_FOR_REVIEW_DECISION and request_id:
            request_file = review_dir / "review_request.json"
            session_file = review_dir / "session.json"
            request = read_json(request_file) if request_file.exists() else {}
            session = read_json(session_file) if session_file.exists() else {}
            return {
                "started": True,
                "already_running": False,
                "pid": process.pid,
                "request_id": request_id,
                "stage": request.get("stage", "stage1"),
                "content_hash": last_status.get("review_content_hash"),
                "server_url": session.get("server_url"),
                "state": WAITING_FOR_REVIEW_DECISION,
                "log_file": str(log_file),
            }
        time.sleep(0.1)
    raise Stage1Error("Timed out while waiting for the hash-bound browser review request to start.")


def current_review_data(planning_dir: Path) -> dict[str, Any]:
    status = load_status(planning_dir)
    plan = load_plan(planning_dir, status["current_candidate_version"])
    candidate_file = version_json_path(planning_dir, status["current_candidate_version"])
    previous = load_plan(planning_dir, status["previous_version"]) if status.get("previous_version") else None
    reason = plan.get("version_record", {}).get("modification_reason", "")
    errors = status.get("validation_errors", [])
    warnings = status.get("validation_warnings", [])
    analysis = analyze_comparison(previous, plan, reason, errors, warnings) if previous else None
    draft = read_json(draft_path(planning_dir)) if draft_path(planning_dir).exists() else None
    review_session_path = planning_dir.parent / "review" / "session.json"
    review_session = read_json(review_session_path) if review_session_path.exists() else None
    return {
        "status": status,
        "plan": plan,
        "candidate_content_hash": content_sha256(candidate_file.read_text(encoding="utf-8")),
        "draft": draft,
        "review_session": review_session,
        "versions": sorted(path.stem.replace("stage1_plan_", "") for path in planning_dir.glob("stage1_plan_v*.json")),
        "change_log": read_json(log_path(planning_dir)),
        "analysis": analysis,
    }


class ReviewHandler(BaseHTTPRequestHandler):
    planning_dir: Path

    def log_message(self, format_string: str, *args: Any) -> None:
        sys.stderr.write("[stage1-review] " + format_string % args + "\n")

    def send_json(self, payload: Any, status: HTTPStatus = HTTPStatus.OK) -> None:
        encoded = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status.value)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(encoded)

    def send_file(self, path: Path, content_type: str) -> None:
        encoded = path.read_bytes()
        self.send_response(HTTPStatus.OK.value)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(encoded)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(encoded)

    def read_body(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0"))
        if length <= 0 or length > 5 * 1024 * 1024:
            raise Stage1Error("Request body must be between 1 byte and 5 MiB.")
        payload = json.loads(self.rfile.read(length).decode("utf-8"))
        if not isinstance(payload, dict):
            raise Stage1Error("Request body must be a JSON object.")
        return payload

    def do_GET(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
        try:
            if path in {"/", "/stage1_review.html"}:
                self.send_file(self.planning_dir / "stage1_review.html", "text/html; charset=utf-8")
            elif path == "/stage1_review.css":
                self.send_file(self.planning_dir / "stage1_review.css", "text/css; charset=utf-8")
            elif path == "/stage1_review.js":
                self.send_file(self.planning_dir / "stage1_review.js", "text/javascript; charset=utf-8")
            elif path == "/api/state":
                self.send_json(current_review_data(self.planning_dir))
            elif path == "/api/impact":
                self.send_file(self.planning_dir / "stage1_impact_analysis.md", "text/markdown; charset=utf-8")
            else:
                self.send_json({"error": "Not found"}, HTTPStatus.NOT_FOUND)
        except (Stage1Error, OSError, json.JSONDecodeError) as exc:
            self.send_json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)

    def do_POST(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
        try:
            payload = self.read_body()
            if path == "/api/submit":
                plan = payload.get("plan")
                if not isinstance(plan, dict):
                    raise Stage1Error("plan must be a JSON object.")
                result = submit_plan(self.planning_dir, plan, str(payload.get("reason", "")))
            elif path == "/api/draft":
                plan = payload.get("plan")
                if not isinstance(plan, dict):
                    raise Stage1Error("plan must be a JSON object.")
                result = save_draft(self.planning_dir, plan)
            elif path == "/api/check":
                plan = payload.get("plan")
                if not isinstance(plan, dict):
                    raise Stage1Error("plan must be a JSON object.")
                result = check_edited_plan(self.planning_dir, plan)
            elif path == "/api/start-review":
                result = start_browser_review_process(self.planning_dir)
            elif path == "/api/action":
                result = transition(
                    self.planning_dir,
                    str(payload.get("action", "")),
                    str(payload.get("reason", "")),
                    str(payload["version"]) if payload.get("version") else None,
                    str(payload.get("confirmed_by", "user")),
                )
            else:
                self.send_json({"error": "Not found"}, HTTPStatus.NOT_FOUND)
                return
            self.send_json({"ok": True, "result": result})
        except (Stage1Error, OSError, ValueError, json.JSONDecodeError) as exc:
            self.send_json({"ok": False, "error": str(exc)}, HTTPStatus.BAD_REQUEST)


def serve(planning_dir: Path, host: str, port: int, open_page: bool) -> None:
    ensure_review_html(planning_dir)
    handler = type("BoundReviewHandler", (ReviewHandler,), {"planning_dir": planning_dir})
    server = ThreadingHTTPServer((host, port), handler)
    address = f"http://{host}:{server.server_address[1]}/"
    print(f"Stage-1 review page: {address}", flush=True)
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

    init_parser = subparsers.add_parser("init", help="Create immutable v001 and review artifacts.")
    init_parser.add_argument("--plan", type=Path, required=True, help="Source stage-1 plan JSON.")
    init_parser.add_argument("--planning-dir", type=Path, default=Path("planning"))

    validate_parser = subparsers.add_parser("validate", help="Validate and score a plan JSON.")
    validate_parser.add_argument("--plan", type=Path, required=True)

    submit_parser = subparsers.add_parser("submit", help="Create a new immutable version and analyze impact.")
    submit_parser.add_argument("--planning-dir", type=Path, default=Path("planning"))
    submit_parser.add_argument("--edited-plan", type=Path, required=True)
    submit_parser.add_argument("--reason", required=True)

    action_parser = subparsers.add_parser("action", help="Accept, continue, restore, reject, or approve.")
    action_parser.add_argument("--planning-dir", type=Path, default=Path("planning"))
    action_parser.add_argument("--name", choices=("accept", "continue", "restore", "reject", "approve"), required=True)
    action_parser.add_argument("--reason", default="")
    action_parser.add_argument("--version")
    action_parser.add_argument("--confirmed-by", default="user")

    serve_parser = subparsers.add_parser("serve", help="Serve and optionally open the review page.")
    serve_parser.add_argument("--planning-dir", type=Path, default=Path("planning"))
    serve_parser.add_argument("--host", default="127.0.0.1")
    serve_parser.add_argument("--port", type=int, default=8765)
    serve_parser.add_argument("--open", action="store_true", dest="open_page")

    review_parser = subparsers.add_parser("review", help="Open the hash-bound Flask review gate and wait for a decision.")
    review_parser.add_argument("--planning-dir", type=Path, default=Path("planning"))
    review_parser.add_argument("--project-dir", type=Path)
    review_parser.add_argument("--title", default="第一阶段：研究目标与计算方案最终审查")
    review_parser.add_argument("--start-port", type=int, default=5050)
    review_parser.add_argument("--timeout", type=float, default=0.0, help="Seconds; 0 waits without a deadline.")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        if args.command == "init":
            result = initialize(args.planning_dir.resolve(), args.plan.resolve())
        elif args.command == "validate":
            plan = read_json(args.plan.resolve())
            if not isinstance(plan, dict):
                raise Stage1Error("Plan must be a JSON object.")
            errors, warnings = validate_and_score_plan(plan)
            result = {"valid": not errors, "errors": errors, "warnings": warnings}
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return 0 if not errors else 1
        elif args.command == "submit":
            edited = read_json(args.edited_plan.resolve())
            if not isinstance(edited, dict):
                raise Stage1Error("Edited plan must be a JSON object.")
            result = submit_plan(args.planning_dir.resolve(), edited, args.reason)
        elif args.command == "action":
            result = transition(
                args.planning_dir.resolve(),
                args.name,
                args.reason,
                args.version,
                args.confirmed_by,
            )
        elif args.command == "serve":
            serve(args.planning_dir.resolve(), args.host, args.port, args.open_page)
            return 0
        elif args.command == "review":
            planning_dir = args.planning_dir.resolve()
            project_dir = args.project_dir.resolve() if args.project_dir else planning_dir.parent
            result = browser_review(
                planning_dir,
                project_dir,
                args.title,
                args.start_port,
                args.timeout,
            )
        else:
            raise Stage1Error(f"Unsupported command: {args.command}")
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (Stage1Error, OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
