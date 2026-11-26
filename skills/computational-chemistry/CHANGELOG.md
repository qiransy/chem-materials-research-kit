# Changelog

All notable changes to Computational Chemistry Skill are documented in this file.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project uses [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added

- Reserved section for changes after version 1.1.0.

## [1.1.0] - 2026-07-20

### Added

- Controlled PowerShell 7 execution rules using `pwsh -NoLogo -NoProfile -NonInteractive`, finite timeouts, output validation, and at most one justified retry.
- Progressive stage-1 intake that confirms the calculation goal, structure/files, software/version, execution environment, requested deliverables, returned-result requirements, and key parameters before generating artifacts.
- A deterministic `scripts/staged_review.py` checker/renderer and executable regression tests for the default intake and fixed review-page contract.

### Changed

- The default browser review is generated only after stage-1 completeness and consistency checks, at the fixed path `.review/review.html`; revisions overwrite the same page.
- `.review/review_response.json` is optional and is created only when a real browser-return mechanism requires it.
- Formal calculation directories now default to the target program's minimum runnable file set plus one `README.md`; scheduler scripts and `.ps1` launchers are generated only when requested and applicable.
- WSL and Linux routes use Bash or target-software commands, while the existing hash-bound Flask review and provenance workflow remains an explicit advanced-project compatibility mode.

### Fixed

- PowerShell failures no longer block scientific analysis, review preparation, or calculation-file generation; failed Windows automation enters a continuing fallback or manual-execution state.
- Documentation no longer presents unexecuted validation, generated approval/manifest/status files, or unsupported hardware estimates as default behavior.

## [1.0.0] - 2026-07-19

### Added

- Staged computational-chemistry workflow covering scientific planning, model design, formal input preparation, result analysis, manuscript drafting, and project delivery.
- Human-in-the-loop browser review with independent pages for each blocking stage.
- Review decisions bound to `request_id`, `stage`, and SHA-256 `content_hash`.
- Structured plan editor for ordinary users and an advanced JSON mode for technical users.
- Version history and natural-language comparison of scientific scope, workload, evidence chain, result impact, and risk.
- Guidance for bulk, surface, defect, adsorption, interface, electronic-structure, charge, bonding, molecular-dynamics, and related computational tasks.
- Separation between planned parameters and parameters extracted from actual user-run calculations.
- Numbered data-processing tutorials and evidence-oriented analysis of user-provided processed data.
- Manuscript method drafting from actual input, output, log, structure, software, and version records.
- Open-source reproduction and migration suggestions while preserving the truthful provenance of non-open-source calculations.
- Repository documentation, dependency declarations, citation metadata, contribution guidance, and issue templates.

### Safety and scientific boundaries

- Production calculations and remote scheduler jobs remain user-executed.
- Static validation is not treated as proof of numerical convergence or scientific correctness.
- Browser closure, timeout, server exit, stale decisions, and hash mismatches are never interpreted as approval.
- Credentials, private keys, license files, and sensitive cluster configuration are excluded from normal project inputs.

[Unreleased]: https://github.com/jianzushen/Computational-chemistry-skill/compare/v1.1.0...HEAD
[1.1.0]: https://github.com/jianzushen/Computational-chemistry-skill/compare/v1.0.0...v1.1.0
[1.0.0]: https://github.com/jianzushen/Computational-chemistry-skill/releases/tag/v1.0.0
