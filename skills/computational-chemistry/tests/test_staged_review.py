from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

SCRIPT = Path(__file__).parents[1] / "scripts" / "staged_review.py"
SPEC = importlib.util.spec_from_file_location("staged_review", SCRIPT)
assert SPEC and SPEC.loader
staged_review = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(staged_review)


def complete_payload() -> dict[str, object]:
    return {
        "calculation_goal": "Optimize bulk silicon atomic positions",
        "structure": "Two-atom primitive cell",
        "software": "Quantum ESPRESSO",
        "software_version": "7.5",
        "run_location": "school Linux cluster",
        "environment": "module load qe/7.5; pw.x",
        "server_environment": "Linux cluster",
        "scheduler": "Slurm",
        "requested_files": ["calculation.in", "README.md"],
        "return_files": ["calculation.out", "optimized structure"],
        "key_parameters": {"calculation": "relax", "ecutwfc": "50 Ry"},
        "generate_submit_script": False,
    }


def test_incomplete_intake_creates_no_review(tmp_path: Path) -> None:
    payload = {"calculation_goal": "Optimize a structure"}
    with pytest.raises(staged_review.IntakeIncompleteError):
        staged_review.render_review(payload, tmp_path)
    assert not (tmp_path / ".review").exists()


def test_complete_intake_generates_only_fixed_review_name(tmp_path: Path) -> None:
    target = staged_review.render_review(complete_payload(), tmp_path)
    assert target == tmp_path / ".review" / "review.html"
    assert target.is_file()
    assert [path.name for path in target.parent.iterdir()] == ["review.html"]


def test_revision_overwrites_review_without_version_copy(tmp_path: Path) -> None:
    payload = complete_payload()
    target = staged_review.render_review(payload, tmp_path)
    first = target.read_text(encoding="utf-8")
    payload["calculation_goal"] = "Optimize and verify bulk silicon"
    staged_review.render_review(payload, tmp_path)
    second = target.read_text(encoding="utf-8")
    assert first != second
    assert "Optimize and verify bulk silicon" in second
    assert not list(target.parent.glob("review_v*.html"))
    assert not (target.parent / "review_final.html").exists()


def test_submit_resources_are_conditional() -> None:
    payload = complete_payload()
    assert "scheduler_resources" not in staged_review.missing_fields(payload)
    payload["generate_submit_script"] = True
    assert "scheduler_resources" in staged_review.missing_fields(payload)


def test_questions_are_progressive_and_ordered() -> None:
    assert staged_review.next_question_fields({}) == ["calculation_goal", "structure"]


def test_wsl_uses_bash_route_without_powershell() -> None:
    payload = complete_payload()
    payload.update(
        {
            "run_location": "Windows 11 WSL Ubuntu 22.04",
            "environment": "use_cp2k",
            "local_environment": "Ubuntu 22.04; cp2k.psmp",
        }
    )
    payload.pop("server_environment")
    payload.pop("scheduler")
    assert staged_review.execution_route(payload) == "bash_or_native"
    assert not staged_review.missing_fields(payload)


def test_input_only_cluster_request_does_not_need_slurm_resources() -> None:
    payload = complete_payload()
    payload["generate_submit_script"] = False
    assert staged_review.execution_route(payload) == "bash_or_native"
    assert "scheduler_resources" not in staged_review.missing_fields(payload)


def test_review_uses_friendly_controls() -> None:
    payload = complete_payload()
    payload["key_parameters"] = {"ecutwfc": 50, "spin_polarized": True}
    page = staged_review.review_html(payload)
    assert "<select" in page
    assert 'type="number"' in page
    assert 'type="checkbox"' in page
