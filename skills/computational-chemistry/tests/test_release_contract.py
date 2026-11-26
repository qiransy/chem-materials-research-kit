from __future__ import annotations

import re
from pathlib import Path

import yaml

ROOT = Path(__file__).parents[1]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_version_is_consistent() -> None:
    version = read("VERSION").strip()
    citation = yaml.safe_load(read("CITATION.cff"))
    assert version == "1.1.0"
    assert citation["version"] == version
    assert f"version-{version}-" in read("README.md")
    assert f"[{version}]" in read("CHANGELOG.md")
    assert version in read("RELEASE.md")


def test_controlled_powershell_contract() -> None:
    rules = read("references/powershell-nonblocking-rules.md")
    assert "pwsh -NoLogo -NoProfile -NonInteractive" in rules
    assert "Never fall back to `powershell.exe`" in rules
    assert "Start-Job" in rules and "Prohibit" in rules
    assert "exit code alone" in rules
    assert "manual_execution_required" in rules


def test_default_review_and_delivery_contract() -> None:
    skill = read("SKILL.md")
    browser = read("docs/BROWSER_REVIEW.md")
    generation = read("references/execution-and-file-generation-rules.md")
    assert ".review/review.html" in skill
    assert ".review/review.html" in browser
    assert "review_v1.html" in browser
    assert "overwrite" in browser.lower() or "覆盖" in browser
    for forbidden in (
        "approval_record.json",
        "parameter_manifest.json",
        "RETURN_FILES_REQUIRED.md",
        "execution_status.json",
    ):
        assert forbidden in generation
    assert "Do not generate these by default" in generation


def test_no_ephemeral_review_or_result_artifacts_are_tracked() -> None:
    tracked_names = {path.name for path in ROOT.rglob("*") if path.is_file()}
    assert "review.html" not in tracked_names
    assert "review_response.json" not in tracked_names
    assert not any(re.search(r"\.(out|err)$", name) for name in tracked_names)


def test_relative_markdown_links_resolve() -> None:
    pattern = re.compile(r"\[[^]]*\]\(([^)]+)\)")
    missing: list[str] = []
    for document in ROOT.rglob("*.md"):
        for raw_target in pattern.findall(document.read_text(encoding="utf-8")):
            target = raw_target.split("#", 1)[0].strip().strip("<>")
            if not target or "://" in target or target.startswith(("#", "mailto:")):
                continue
            if not (document.parent / target).resolve().exists():
                missing.append(f"{document.relative_to(ROOT)} -> {target}")
    assert not missing, "Missing relative links:\n" + "\n".join(missing)
