---
name: computational-chemistry
description: Plan computational chemistry and materials calculations, prepare or review calculation inputs (e.g., DFT, Gaussian, ORCA, VASP, xTB/CREST), and interpret requested outputs. Load materials, surface, interface, or advanced project procedures when relevant.
---

# Computational Chemistry Workflow

<!-- local-mw-profile-v1 -->

## Molecular spectroscopy fast route

For an ordinary gas-phase molecule or cluster task, first read the shared domain
workflow above. Use the user's established CREST/Gaussian/ORCA and HPC settings;
ask only for missing information needed for the requested files or analysis.
Do not apply surface/interface stage intake or mandatory browser review to
routine molecular input preparation or result organization. Load only relevant
software references. Existing explicitly initialized project protections remain
binding. Preserve user control of candidates; do not impose energy cutoffs or
assignment priorities. A frozen-geometry single-point calculation alone does
not provide centrifugal-distortion constants.

## Default intake, review, and execution route

For a new or underspecified request, read and follow all of:

- `references/execution-and-file-generation-rules.md`
- `references/powershell-nonblocking-rules.md`
- `references/stage-1-review-and-approval.md`
- `references/browser_review_enforcement.md`

Collect stage-1 information progressively. A request such as “help me optimize this structure with CP2K” is not authorization to create files. Ask only the next relevant questions until the calculation goal, structure or existing files, software and version, run location, environment-loading command, requested deliverables, required return files, and key scientific parameters are complete and mutually consistent. Ask scheduler resource questions only when the user requests a submission script.

Before intake is complete, do not create `.review/`, calculation input files, review records, manifests, or approval files. After consistency checks pass, generate or overwrite exactly `.review/review.html`. Create `.review/review_response.json` only when an automated browser-return mechanism actually needs it. User revisions overwrite the same page; never create numbered or “final” review copies.

Use `scripts/staged_review.py check` and `scripts/staged_review.py render` when a machine-checkable default intake/review path is available. Browser auto-open is only a convenience: failure to open a browser does not block scientific analysis, and the local page path or verified URL must be returned instead.

PowerShell is an optional bounded Windows adapter, not an analysis engine or workflow gate. When it is genuinely useful, use PowerShell 7 only as `pwsh -NoLogo -NoProfile -NonInteractive`, with a finite timeout and captured output. Do not use Windows PowerShell 5.1, background jobs, interactive prompts, or unbounded waits. WSL and Linux routes use Bash or the target program's native command. A failed PowerShell action must enter a continuing fallback state and must not prevent analysis or file generation.

The existing hash-bound Flask review service and immutable project-control records remain available only for an explicitly initialized advanced project or when the user requests that mode. Those internal records stay outside the formal calculation delivery directory and do not change the default single-page/minimal-file contract.

## Route the request

Determine the requested workflow stage before acting.

For every request associated with an explicitly initialized advanced project, first read all of:

- `references/global-project-control-workflow.md`
- `references/global-project-control-schema.md`

Use `scripts/project_control.py audit` to read the global state, local stage-status projection, locked hashes, resume context, dependencies, approvals, and provenance before routing. A conflict pauses the downstream action; reconcile it through verified local gates and an explicit global transition, never by modification time. Do not initialize `project_control/` or `provenance/` for the default simple route. If the user explicitly selects the advanced project workflow, initialize those independent stores without claiming any scientific-stage approval. The global layer may read stage files but must never write them.

When the active request depends on software compatibility, parameter translation, returned-file sufficiency, citations/licenses, or an open-source alternative, load only the applicable central records among `references/software_capability_matrix.yaml`, `references/software_parameter_mapping.yaml`, `references/software_output_requirements.yaml`, `references/software_citation_rules.yaml`, `references/citation_registry.json`, `references/method_citation_templates.md`, and `references/open_source_alternatives.yaml`. Treat all capability/version/license fields marked `UNVERIFIED` or `VERIFY_*` as requiring official confirmation; similarity never establishes equivalence.

For stage 1 requests involving research-goal definition, scientific-question decomposition, model/control design, evidence-chain planning, software or parameter selection, redundancy review, resource prioritization, or readiness decisions, read all of:

- `references/stage-1-workflow.md`
- `references/stage-1-evidence-and-methods.md`
- `references/stage-1-output-contract.md`
- `references/stage-1-plan-schema.md`
- `references/stage-1-review-and-approval.md`

Treat stage 1 as the default only when the user asks for a plan or has not authorized input generation or computation.

For stage 2 step 1 requests involving material-surface design, facet or termination selection, slab/vacuum/supercell/constraint design, defects, doping, functionalization, spin, surface candidate generation, surface screening, or surface-model approval, read all of:

- `references/stage-2-step-1-surface-workflow.md`
- `references/stage-2-step-1-surface-schema.md`
- `references/stage-2-step-1-surface-review.md`

Enter stage 2 step 1 only through the approved stage-1 gate. If the isolated surface workflow has not recorded the user's answer to the mandatory proposal/experiment question, ask it and pause before generating formal surface structures.

For stage 2 step 2 requests involving user selection of two approved surfaces, upper/lower ordering, interface typing, two-dimensional lattice matching, rotation or strain allocation, interface contact construction, candidate deduplication, interface optimization input generation, independent-component references, dependency manifests, HPC/local-run scripts, static file checks, browser editing, or interface-file approval, read all of:

- `references/stage-2-step-2-interface-workflow.md`
- `references/stage-2-step-2-interface-schema.md`
- `references/stage-2-step-2-interface-review.md`

Enter stage 2 step 2 only after both stage 1 and stage 2 step 1 approved baselines pass their status and checksum gates. Start at `WAITING_FOR_INTERFACE_SELECTION`; show all retained approved surfaces in the browser and require the user to choose the lower and upper surfaces and confirm their order. Do not automatically choose the pair or generate a formal interface/file version before that selection.

For requests involving calculation-file delivery handoff, returned output/error/final-structure files, program/SCF/geometry/structure validation, parameter-difference review, surface/interface redesign decisions, optimization input regeneration, restart files, optimized-structure acceptance, or files for the next approved task, read both:

- `references/stage-2-result-return-workflow.md`
- `references/stage-2-result-return-schema.md`

After approved geometry-optimization files are delivered, keep `interface_design/interface_status.json` unchanged and start the isolated result store at `WAITING_FOR_USER_CALCULATION_RESULT`. Display the exact handoff prompt from the result workflow, then stop. Do not wait, monitor, query, retrieve, or promise automatic continuation. When the user later returns, ingest the real files or detailed description before making any judgment.

For stage 2 step 3 requests involving recovery of the approved formal evidence chain, minimum prerequisite-ready batches, high-precision SCF, comparable binding/formation-energy references, charge-density difference, quantitative charge, DOS/PDOS, selected COHP/COOP/QTAIM, formal input/post-processing/reference files, scheduler/local scripts, formal browser approval, formal-result return, or evidence-node progression, read all of:

- `references/stage-2-step-3-formal-workflow.md`
- `references/stage-2-step-3-formal-schema.md`
- `references/stage-2-step-3-formal-review.md`

Enter stage 2 step 3 only after the stage-1 approved plan and applicable surface/interface baselines pass checksum gates and the geometry result state is `OPTIMIZED_STRUCTURE_ACCEPTED`. Start an isolated `formal_calculations/` store, restore only retained approved tasks, and generate one minimum prerequisite-ready batch at a time. Require browser approval before delivery and real returned results before accepting a task or generating its dependent batch.

For stage 3 requests involving help processing real calculation outputs, resuming from a stated processing step, extracting target observables, unit/reference/energy-zero/atom-mapping alignment, processed CSV/Excel/TXT/value review, binding or adsorption energy, CDD/Bader, DOS/PDOS, COHP/QTAIM data interpretation, result consistency, experimental correspondence, conclusion strength, evidence gaps, or evidence-chain validation, read all of:

- `references/stage-3-analysis-workflow.md`
- `references/stage-3-analysis-schema.md`
- `references/stage-3-analysis-review.md`

Enter stage 3 only when the approved stage-1 evidence chain exists and the current formal task has a real returned or accepted result. Start an isolated `results_analysis/` store. If the user already states whether data are raw, partial, processed, tutorial-needed, or at a numbered step, continue from there without repeating the initial question. Do not assume unsupplied formal tasks are complete, and do not make figure generation part of this stage.

For stage 4 requests involving scientific-conclusion generation, manuscript computational methods, concise/full method variants, results and discussion, evidence-node conclusions, theory–experiment correspondence, actual-software provenance, citation/license/file-sharing review, commercial-software disclosure, open-source alternatives, reproduction parameter mapping, manuscript style edits, conclusion-strength edits, or final manuscript-content approval, read all of:

- `references/stage-4-manuscript-workflow.md`
- `references/stage-4-manuscript-schema.md`
- `references/stage-4-manuscript-review.md`

Enter stage 4 only after stage 3 is `RESULTS_APPROVED` with overall completion. Freeze all approved stage-1/2/3 records, actual inputs/outputs/models, and every stage-3 analysis approval. Write only within `manuscript_generation/`. Keep actual methods, scientific interpretation, and future open-source reproduction mappings visibly and structurally separate.

For stage 5 requests involving final file validation, delivery manifests, reproducibility records, missing-item classification, software/license summaries, cleanup recommendations, delivery review, project archive, or reopening an archived project, additionally read:

- `references/global-delivery-review.md`

Enter stage 5 only after the local manuscript state is `MANUSCRIPT_CONTENT_APPROVED`. Write only within `project_delivery/` and global history stores. Add files through an explicit reviewed list, copy rather than move them, preserve source hashes, exclude restricted dependencies from the package, and never delete anything. Set `PROJECT_ARCHIVED` only after a clean delivery check and explicit user approval; reopening creates a new project version and preserves the prior archive.

## Preserve stage isolation in advanced projects

- Execute only the requested stage.
- Use the global controller as a read-only observer of stage-owned directories. Write global state, audit, recovery, provenance, and delivery artifacts only under `project_control/`, `provenance/`, and `project_delivery/`; do not let recovery or routing mutate a local stage state.
- Allocate globally unique model, calculation, result, evidence, and conclusion IDs without reuse. Keep conclusion chains resolvable through real results, actual inputs, model versions, and approved stage-1 tasks; incomplete chains are not manuscript-eligible.
- Keep planned and actual parameters in separate records. Extract actual values only from user-run inputs/outputs, classify every difference, and require explicit review for scientifically relevant or model-changing differences.
- On every pause, version the resume context and state exactly one next user action plus the specific return files. On “continue” or a cross-dialog return, audit and resume from the stored task without replaying approved stages.
- Classify file, syntax, environment, numerical, model, reference-system, processing, interpretation, and provenance failures separately and route them to their owning step. Never conceal a model failure with numerical tuning or demand recalculation for a pure processing error.
- Do not generate production input files, run calculations, submit jobs, extract results, or perform post-processing during stage 1.
- Do not infer authorization to enter a later stage from a request to make the plan more detailed.
- Keep stage 1 limited to decisions, dependencies, evidence roles, parameter-selection criteria, execution logic, plan versioning, user review, modification-impact analysis, and approval records.
- Do not treat the initial plan as stage completion. Complete stage 1 only after browser review, explicit final user confirmation, approved baseline generation, and status `APPROVED`.
- Stop after stage-1 approval artifacts are generated. State the readiness conditions for a later stage without performing it.
- During stage 2 step 1, treat all `planning/stage1_*approved*` files as read-only and write only within `surface_design/`.
- Permit candidate surface structures, deterministic model checks, and clearly labeled low-cost prescreening during stage 2 step 1; do not run formal adsorption, binding, DOS/PDOS, COHP, charge, QTAIM, reaction, or production-MD calculations.
- Complete stage 2 step 1 only after explicit user confirmation, all four surface approved baseline files, and status `SURFACE_DESIGN_APPROVED`; do not automatically start the next step.
- During stage 2 step 2, treat every `planning/` and `surface_design/` approved/status file as read-only and write only within `interface_design/`.
- Permit structure transformation, two-dimensional matching, duplicate/static geometry checks, and generation of software inputs, dependencies, scheduler templates, and local-run instructions in stage 2 step 2. Never execute a generated file, scientific code, MPI launcher, scheduler command, queue query, or post-processing command.
- Preserve the exact approved surface facet, termination, cell, defect, doping, functionalization, constraint, and spin snapshots. Change the interface components only by a new user selection among approved surface IDs; return to the owning stage for any upstream model/method change.
- Complete stage 2 step 2 only after explicit user confirmation, the six interface/file approved targets, and status `INTERFACE_FILES_APPROVED`. State that calculations and job submission remain unexecuted, then stop without entering optimization or result analysis.
- During result return, treat `planning/`, `surface_design/`, and `interface_design/` as read-only and write only within `calculation_results/`. Preserve original uploads and create immutable result batches and analysis versions.
- Separate program termination, electronic SCF convergence, geometry convergence, and scientific structure reasonableness. Never infer one from another or accept screenshots/single energies as sufficient proof.
- Emit exactly one permitted result conclusion and enforce its evidence rule: surface redesign, interface redesign, optimization-file regeneration, restart-file generation, additional files required, or optimized structure accepted.
- Generate restart/regenerated/next-task files only when their result state allows it. Never run or submit them. Generate electronic/bonding/adsorption follow-up files only after `OPTIMIZED_STRUCTURE_ACCEPTED`; route adsorption to configuration design rather than arbitrary placement.
- During stage 2 step 3, treat `planning/`, `surface_design/`, `interface_design/`, and `calculation_results/` as read-only and write only within `formal_calculations/`. Freeze all entry files by absolute path and checksum.
- Restore only retained stage-1 tasks and preserve their IDs, scientific purpose, controls, priority, necessity, and dependencies. Never restore deleted duplicates or add unapproved calculations.
- Generate only the current minimum prerequisite-ready formal batch. Enforce composite/reference completeness for energy and density differences, accepted SCF/NSCF dependencies for DOS/PDOS, and compatible wavefunction/projection requirements for bonding/QTAIM analyses.
- Require immutable candidate versions, static checks, browser review, explicit user approval, and `WAITING_FOR_FORMAL_CALCULATION_RESULT` before external execution. Do not wait for, monitor, or retrieve results.
- Ingest actual formal inputs/outputs/data before judgment. Emit exactly one of the nine formal conclusions, calculate task/evidence completion from validated files, and record upstream return routes without changing the owning stage's status.
- Set `FORMAL_CALCULATION_WORKFLOW_COMPLETED` only when all retained necessary formal tasks and required evidence nodes have accepted user-run results.
- During stage 3, treat `planning/`, `surface_design/`, `interface_design/`, `calculation_results/`, and `formal_calculations/` as read-only and write only within `results_analysis/`. Freeze source paths and checksums; explicitly sync a legitimately advanced formal graph/result projection without changing upstream state.
- Record data-processing progress separately per dataset/task/type. Give the eight-step overview before detailed commands when the user does not know the workflow; when the user names a step, expand only that step and direct dependencies and preserve all unaffected completed steps.
- Copy every raw, partial, or processed upload into a new immutable version. Treat screenshots, pictures, single energies, or unreferenced values as insufficient for quantitative/comparative acceptance; require only the specific missing metadata that affects the current judgment.
- Separate processing gaps from source-calculation failures. Prefer supplementary extraction, alignment, mapping, integration, sign checking, or table organization when raw results are adequate. Return to stage 2 step 3 only for missing raw calculations, wrong core parameters, irreparable references, or insufficient source precision.
- Analyze completeness, comparability, trend, anomaly, physical meaning, evidence role, corroboration, experimental link, conclusion boundary, and next action in that order. Assign only `STRONGLY_SUPPORTED`, `SUPPORTED`, `PARTIALLY_SUPPORTED`, `INCONCLUSIVE`, or `CONTRADICTED`; strong support requires independent physical dimensions.
- Accept individual evidence nodes without claiming all stage-3 work is complete. Set `RESULTS_APPROVED` only after required nodes, all completion checks, and explicit user confirmation pass. Never require or automatically generate a paper, presentation, or data-visualization figure.
- During stage 4, treat every stage-1/2/3 directory as read-only and write only within `manuscript_generation/`. Require actual input and real output/data provenance; do not draft methods from the stage-1 plan alone or infer software from an extension.
- Preserve actual software/version/module/model/parameter/formula records. Use actual parameters when they differ from the plan, identify unknown version with the required pending statement, and block final approval when a result-relevant actual parameter remains unknown.
- Inherit stage-3 conclusion strengths and limitations. Permit lower but never higher draft strength; require independent evidence roles for mechanism claims and reject proof/causal wording beyond the approved evidence.
- Review official software/method citations, license category, input sharing, and restricted dependencies without copying long manual text or packaging restricted files. A non-open program remains named as the actual program.
- Put open-source alternatives and parameter mappings in a separate future-reproduction section with the exact non-recalculation disclaimer. Never put an unexecuted alternative into the actual method or treat a mapped template as provenance for existing results.
- Version every manuscript edit and analyze its impact. Protect source IDs/hashes/facts/strength ceilings, freeze the six approved Markdown files plus approval record only after explicit user confirmation, and never submit a paper or publish a repository.
- During stage 5, treat all stage-1/2/3/4 directories as read-only. Build the delivery package from explicit source records and hashes, distinguish blocking scientific gaps from reproduction-only limitations, keep actual and alternative software records separate, and recommend cleanup without moving or deleting files.
- Load only the references routed to the active stage. Preserve every completed stage's terminology, files, states, and prohibitions unless the user explicitly revises that stage.

## Use available context

Inspect the current request, earlier project context, accessible project files, existing results, experimental observations, software environment, and compute constraints before asking for information. Do not ask the user to repeat information already available.

When information is missing, produce the most complete defensible work allowed by the active stage, mark assumptions as provisional, identify only the unresolved decisions that materially affect the route, and respect any mandatory pause or approval gate.

## Maintain scientific integrity

- Start from the scientific conclusion that needs support, then select observables and methods.
- Give each proposed calculation one distinct evidence role.
- Prefer the smallest complete, interpretable, and resource-aware evidence chain.
- Distinguish method requirements from examples and provisional recommendations.
- Never invent software capabilities, module names, parameter justifications, literature findings, numerical results, or convergence status.
