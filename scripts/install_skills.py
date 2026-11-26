#!/usr/bin/env python3
"""Copy the kit's skills into a project's agent skill directory."""

import argparse
from filecmp import cmp
import os
from pathlib import Path
from shutil import copytree
from tempfile import TemporaryDirectory


def filesystem_path(path):
    # Some vendored templates and fixtures exceed Windows' legacy path limit.
    path_text = str(path)
    if os.name != "nt" or path_text.startswith("\\\\?\\"):
        return path
    if path_text.startswith("\\\\"):
        return Path("\\\\?\\UNC\\" + path_text[2:])
    return Path("\\\\?\\" + path_text)


SOURCE = filesystem_path(Path(__file__).resolve().parent.parent / "skills")
SHARED = ".agents/skills"
TARGETS = {
    "agents": SHARED,
    "antigravity": SHARED,
    "codex": SHARED,
    "cursor": SHARED,
    "devin": SHARED,
    "gemini": SHARED,
    "openclaw": SHARED,
    "opencode": SHARED,
    "claude": ".claude/skills",
    "copilot": ".github/skills",
    "kiro": ".kiro/skills",
    "qwen": ".qwen/skills",
    "roo": ".roo/skills",
}

DEPENDENCIES = {
    "citation-verification": ("managing-zotero", "nature-ref-verifier", "scientific-writing"),
    "literature-review": ("nature-paper-card", "nature-ref-verifier", "paper-lookup"),
    "nature-figure": ("nature-shared",),
    "nature-paper2ppt": ("nature-shared",),
    "nature-polishing": ("nature-shared",),
    "nature-reader": ("nature-shared",),
    "nature-response": ("nature-shared",),
    "nature-reviewer": ("nature-shared",),
    "nature-writing": ("nature-shared",),
    "results-analysis": ("research-ideation",),
    "review-response": ("nature-response",),
}


def matches_source(name, target):
    source = SOURCE / name
    return target.is_dir() and not target.is_symlink() and all(
        (target / path.relative_to(source)).is_file()
        and cmp(path, target / path.relative_to(source), shallow=False)
        for path in source.rglob("*") if path.is_file()
    )


def install(project, skill_dir, names, dry_run):
    if not project.is_dir():
        raise ValueError(f"Project directory does not exist: {project}")
    project = project.resolve()
    destination = (project / skill_dir).resolve()
    if not destination.is_relative_to(project):
        raise ValueError(f"Skill directory resolves outside the project: {destination}")
    display_destination = destination
    destination = filesystem_path(destination)

    present = [name for name in names
               if (destination / name).exists() or (destination / name).is_symlink()]
    conflicts = [name for name in present if not matches_source(name, destination / name)]
    if conflicts:
        raise ValueError(f"Already present in {display_destination}: {', '.join(conflicts)}. "
                         "Keep your existing versions or choose a different project.")
    names = [name for name in names if name not in present]
    if present:
        print(f"Already installed: {', '.join(present)}")
    if not names:
        return

    print(f"{'Would install' if dry_run else 'Installing'} {len(names)} skill folders in {display_destination}")
    for name in names:
        print(f"  {name}")
    if dry_run:
        return

    destination.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(prefix=".chem-kit-", dir=destination.parent) as temporary:
        staging = Path(temporary)
        for name in names:
            copytree(SOURCE / name, staging / name)
        for name in names:
            # Recheck after staging so an existing installation is never intentionally replaced.
            target_path = destination / name
            if target_path.exists() or target_path.is_symlink():
                raise ValueError(f"Skill folder appeared during installation: {target_path}")
            (staging / name).rename(target_path)


def main():
    available = {entry.parent.name for entry in SOURCE.glob("*/SKILL.md")}
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("target", nargs="?", default="agents", choices=TARGETS)
    parser.add_argument("--project", type=Path, default=Path.cwd(),
                        help="Existing project or workspace directory (default: current directory)")
    parser.add_argument("--skills-dir", type=Path,
                        help="Override the target with a skill directory inside the project")
    parser.add_argument("--skill", action="append", choices=sorted(available),
                        help="Skill to install (repeatable, default: all 27)")
    parser.add_argument("--list", action="store_true", help="List available skill names")
    parser.add_argument("--dry-run", action="store_true", help="Show the plan without writing files")
    args = parser.parse_args()

    if not available:
        parser.error(f"No skill folders found in {SOURCE}")
    if args.list:
        print("\n".join(sorted(available)))
        return

    names = set(args.skill or available)
    pending = list(names)
    while pending:
        name = pending.pop()
        dependencies = set(DEPENDENCIES.get(name, ()))
        pending.extend(dependencies - names)
        names.update(dependencies)
    if missing := names - available:
        parser.error(f"Missing required skill folders: {', '.join(sorted(missing))}")
    try:
        install(args.project, args.skills_dir or TARGETS[args.target], sorted(names), args.dry_run)
    except (OSError, ValueError) as error:
        parser.exit(1, f"Installation failed: {error}\n")


if __name__ == "__main__":
    main()
