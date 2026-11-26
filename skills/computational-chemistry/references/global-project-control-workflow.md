# Global Project Control Workflow

## Contents

1. Scope and authority
2. Request entry protocol
3. Initialization
4. State synchronization
5. Routing and dependencies
6. Pause and recovery
7. Provenance and parameter truth
8. Error diversion
9. Stage 5 delivery
10. Archive and reopen
11. Prohibitions

## Scope and authority

Use the global layer before every stage-specific action when a project root is available. It is a controller and auditor, not a replacement for a stage engine. Read local stage state and approved artifacts; never write into `planning/`, `surface_design/`, `interface_design/`, `calculation_results/`, `formal_calculations/`, `results_analysis/`, or `manuscript_generation/` through the global controller.

The global controller may write only to:

```text
project_control/
provenance/
project_delivery/
```

It never executes scientific software, generated inputs, MPI commands, scheduler commands, queue queries, remote downloads, result monitors, or post-processing calculations.

## Request entry protocol

For each new request:

1. Locate the project root.
2. Read `project_control/project_manifest.json`, `workflow_state.json`, `resume_context.json`, `stage_dependencies.json`, `user_approvals.json`, and all provenance registries.
3. Read existing local stage status files and verify any frozen file hashes already recorded by the global layer.
4. Run the global audit. If a state conflict or changed locked source exists, stop stage execution and report the conflict. Do not choose the newest file by time.
5. Classify the request and check only the necessary dependencies.
6. Route to the closest executable stage. Do not restart completed stages unless their approved baseline is absent, invalid, or explicitly revised.
7. After the stage action, update only global snapshots, resume guidance, and provenance links. The owning stage remains responsible for its own local state.

If no `project_control/` exists, initialize it before creating new stage artifacts. Initialization does not assert that any scientific stage is approved.

## Initialization

Run:

```text
python scripts/project_control.py --project-root <project> init [metadata options]
```

Create without overwriting:

```text
project_control/project_manifest.json
project_control/workflow_state.json
project_control/stage_dependencies.json
project_control/decision_log.json
project_control/user_approvals.json
project_control/resume_context.json
project_control/next_user_action.md
project_control/required_return_files.md
project_control/project_dashboard.html
provenance/model_registry.json
provenance/calculation_registry.json
provenance/result_registry.json
provenance/evidence_registry.json
provenance/conclusion_registry.json
provenance/conclusion_traceability.json
```

Use a temporary project ID if a formal project name is missing. Never invent a paper title, software version, compute platform, material identity, or scientific goal.

## State synchronization

Global states are projections of local evidence, not substitutes for local states. Use `transition` only after the target state's gate passes. Approval-like states require the corresponding local approved status and artifacts. In-progress global states authorize routing only; they do not grant approval.

Use:

```text
python scripts/project_control.py --project-root <project> audit
python scripts/project_control.py --project-root <project> transition --to-state <STATE> --actor <actor>
```

For user-confirmed states, add `--user-confirmed`. `PROJECT_ARCHIVED` also requires an explicit, non-empty `--confirmation-note` and a ready delivery package.

When local and global state conflict, generate a versioned report under `project_control/state_conflicts/`, leave all states unchanged, and stop the requested downstream action. A missing optional later-stage directory is not a conflict when the global state has not reached it.

When an explicit return or reopen moves the global project backward, record later local status snapshots as superseded historical states instead of editing them. A superseded approval cannot satisfy a new downstream gate; that gate reopens only after the owning stage creates a new status hash and approval version. Preserve the prior approved artifacts as locked history.

## Routing and dependencies

Use `route --request <text>` to identify the stage and nearest unmet dependency. Routes include:

- planning and evidence-chain design → stage 1;
- surface, facet, termination, slab, defect, doping, or functionalization → stage 2 step 1;
- interface construction, matching, ordering, geometry inputs, or optimization files → stage 2 step 2;
- returned geometry result, convergence, or restart → geometry-result return;
- SCF, energy references, CDD, charge, PDOS, COHP, QTAIM, or formal batches → stage 2 step 3;
- processing, units, alignment, interpretation, or result evidence → stage 3;
- methods, discussion, conclusions, citations, licenses, or reproduction prose → stage 4;
- manifest, reproducibility package, delivery, or archive → stage 5.

Do not require a full restart when only the nearest prerequisite is missing. A supplemental calculation requested from stage 3 may return directly to stage 2 step 3 when its existing model and scientific method remain approved.

## Pause and recovery

Whenever work pauses, run `pause` to create an immutable resume history entry and update the three current recovery files. `next_user_action.md` contains only the next user action. `required_return_files.md` contains only the specifically needed files.

On “continue”, “calculation finished”, or “at step N”, run `resume` and continue from the recorded task after an audit. Do not repeat approved work or ask again for known information. Recovery never rolls back, rewrites, or reconstructs a local stage state.

## Provenance and parameter truth

Allocate IDs with `register`. IDs are never reused, including after an entry is retired. Every entry must contain explicit source records. Use the category prefixes defined in the schema.

For calculations, maintain separate `planned_parameters`, `actual_parameters`, differences, impact, and confirmation. Actual parameters require actual input/output source records; never copy the plan into the actual field as a fallback. Use `compare-parameters` for a deterministic key-level comparison.

Use `check-traceability` before stage 4 approval and delivery. Every approved conclusion must resolve through evidence, processed data/real result, actual calculation files, model version, and an approved stage-1 task. Mark an incomplete chain `TRACEABILITY_INCOMPLETE` and exclude it from final approved prose.

Record exact software/method citations with `citation-add`. `VERIFIED` requires a supplied official or primary source identifier; missing version or method detail remains explicitly pending and is never guessed.

## Error diversion

Run `classify-error` with one of the controlled error classes. The command records a versioned report and returns the owning route. It does not modify a stage status.

Never mask `MODEL_ERROR` with numerical tuning. Never order recalculation for a pure `DATA_PROCESSING_ERROR`. Core-method changes go to stage 1 reapproval; model geometry changes go to the owning surface/interface stage.

## Stage 5 delivery

Enter stage 5 only after local stage 4 is `MANUSCRIPT_CONTENT_APPROVED`. Set the global state to `DELIVERY_VALIDATION_IN_PROGRESS`.

Add deliverable copies explicitly with `delivery-add`. The command copies without changing the source, records both hashes, rejects path traversal, and keeps license/share restrictions in metadata. Do not bulk-copy an unknown directory or a restricted dependency.

Run `delivery-check` to create the folder structure and regenerate:

```text
README.md
FILE_MANIFEST.csv
REPRODUCIBILITY_RECORD.md
SOFTWARE_AND_LICENSES.md
MISSING_ITEMS.md
DELIVERY_CHECKLIST.md
DELIVERY_REPORT.md
files_recommended_for_cleanup.md
```

Missing core traceability or manuscript evidence produces `DELIVERY_ITEMS_MISSING`. A reproduction-only limitation may be disclosed without blocking the otherwise valid package. The check never deletes or moves source files.

## Archive and reopen

Use `archive` only after the package is ready and the user explicitly approves it. Archive creates a versioned snapshot and changes only the global state. `PROJECT_ARCHIVED` does not make files immutable forever.

If the user later adds calculations, use `reopen` with a reason and explicit return state. Increment the project version, preserve the archive record, and route only to the affected stage. Do not erase previous delivery or approval history.

## Prohibitions

- Never overwrite original uploads or locked approved versions.
- Never delete historical versions or reuse IDs.
- Never infer source from folder name, extension, or modification time alone.
- Never mix results from different model or parameter versions.
- Never describe planned settings as actual settings.
- Never describe an open-source mapping as an executed method or successful reproduction.
- Never accept a conclusion with missing critical traceability into the final manuscript.
- Never display or invent runtime, memory, or storage estimates in the dashboard.
- Never use global recovery to bypass a local approval gate.
