# Release 1.1.0

Computational Chemistry Skill 1.1.0 adds a tested default route for simple calculation requests while preserving the version 1.0 advanced project workflow as an explicit compatibility mode.

## Upgrade highlights

- PowerShell 7 is now an allowed controlled executor.
- All PowerShell calls use `pwsh -NoLogo -NoProfile -NonInteractive`, finite timeouts, captured output, and at most one retry backed by a concrete correction.
- Windows PowerShell 5.1 (`powershell.exe`) is no longer a default executor.
- Simple calculation requests enter progressive stage-1 intake instead of immediately generating a browser review page.
- Browser review uses the fixed `.review/review.html` path and overwrites it after revisions. `.review/review_response.json` is optional and only used by a required return channel.
- Formal calculation directories contain only necessary calculation files and one `README.md` by default.
- WSL and Linux use Bash or native program commands. A `.ps1` file or scheduler submission script is created only when explicitly requested and applicable.

## Compatibility

The existing Flask review service, hash-bound `review_request.json`/`review_decision.json`, immutable stage versions, provenance, and project-control records remain available for initialized version 1.0 projects or users who explicitly select advanced mode. They are no longer the default response to a new simple request.

Existing advanced project data is not migrated, overwritten, or copied into the default `.review/` layout. Advanced internal records remain outside the formal calculation delivery directory.

The new default flow changes generated-artifact expectations: automation that assumed immediate review generation or default approval/manifest/status files should instead wait for intake completeness and read instructions from the single calculation `README.md`.

## Usage notes

- “帮我用 CP2K 优化这个结构” should trigger questions about the goal and structure, followed by software version, run location/environment, requested files, returned results, and key parameters. It must not create files immediately.
- A Windows 11 + WSL Ubuntu 22.04 + CP2K 2024.3 + `use_cp2k` + `cp2k.psmp` route uses Bash, not PowerShell.
- A Quantum ESPRESSO input-only request on a Slurm cluster does not require scheduler resource questions. Ask for them only when `submit.slurm` is requested.
- Browser auto-open failure returns the local page path or verified address and does not block analysis.
- Long calculations are never waited on in a PowerShell foreground process; continue later from logs, results, or job identifiers.

## Default artifacts

Before stage-1 completion: no review or calculation files.

After completion and before approval:

```text
.review/review.html
```

Optionally, only for a real automated return channel:

```text
.review/review_response.json
```

After approval: target-software inputs/structures/parameters and one `README.md`. The default route does not generate approval records, parameter manifests, provenance records, review-content Markdown, return-file Markdown, execution-status JSON, run-instruction Markdown, or validation records.

## Verification for this release

The repository includes executable tests for incomplete intake, fixed review filenames, overwrite behavior, conditional scheduler questions, version consistency, controlled PowerShell wording, minimal-file rules, and exclusion of runtime review/output artifacts. Static checks prove the implementation contract only; they do not prove scientific convergence or successful execution of external chemistry software.

Release tags and GitHub Releases are created only after the release pull request is merged and the merged commit passes the repository checks.

## Maintainer release checklist

- [ ] `VERSION`, README badge, `CITATION.cff`, and `CHANGELOG.md` all report 1.1.0.
- [ ] `pyproject.toml` remains configuration-only unless the project later adds package metadata; do not invent a duplicate version field.
- [ ] `python -m pytest` passes.
- [ ] `ruff check .` passes.
- [ ] `python -m mypy scripts` is run and its actual result is recorded.
- [ ] Relative documentation paths resolve.
- [ ] No `.review/`, `*.out`, `*.err`, calculation results, credentials, local paths, caches, or temporary state are committed.
- [ ] No new default rule uses `powershell.exe`, PowerShell background jobs, unbounded waits, or versioned review page names.
- [ ] The tag is created only on the merged default-branch commit; never move an existing published tag.
