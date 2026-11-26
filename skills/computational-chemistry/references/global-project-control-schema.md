# Global Control and Provenance Schema

## Contents

1. Owned paths
2. Manifest and workflow state
3. Local stage projection
4. Dependencies and approvals
5. Resume records
6. Registries and identifiers
7. Traceability
8. Parameter differences
9. Error reports
10. Dashboard contract
11. Immutability

## Owned paths

The global controller owns only `project_control/`, `provenance/`, and `project_delivery/`. Every command rejects a project root that would cause an owned path to escape the root.

## Manifest and workflow state

`project_manifest.json` records:

```json
{
  "schema_version": 1,
  "project_id": "PROJECT-...",
  "project_version": 1,
  "project_name": null,
  "research_object": null,
  "material_system": null,
  "research_goal": null,
  "specified_software": null,
  "software_version": null,
  "compute_platform": null,
  "created_at": "RFC3339 UTC",
  "current_stage": "global_control",
  "current_task": "project initialization",
  "current_model_id": null,
  "current_parameter_version": null,
  "current_result_id": null,
  "last_user_action": null
}
```

Unknown values remain `null`. `workflow_state.json` records the global state, monotonic revision, last transition, local-state snapshot, locked-source snapshot, and execution flags. All execution/submission/query/retrieval/monitoring flags are always false.

A backward transition records `superseded_local_states` by path, state, hash, global revision, and reason. Supersession deactivates only that mutable status snapshot; it does not remove the historical lock on approved artifacts. A later approval with a new status hash creates a new active lock.

Allowed global states:

```text
PROJECT_INITIALIZED
PLANNING_IN_PROGRESS
PLANNING_APPROVED
SURFACE_DESIGN_IN_PROGRESS
SURFACE_DESIGN_APPROVED
INTERFACE_DESIGN_IN_PROGRESS
INTERFACE_FILES_APPROVED
WAITING_FOR_USER_CALCULATION
USER_CALCULATION_RESULT_RECEIVED
FORMAL_CALCULATION_FILES_IN_PROGRESS
FORMAL_CALCULATION_FILES_APPROVED
DATA_PROCESSING_IN_PROGRESS
RESULT_ANALYSIS_IN_PROGRESS
RESULTS_APPROVED
MANUSCRIPT_GENERATION_IN_PROGRESS
MANUSCRIPT_CONTENT_APPROVED
DELIVERY_VALIDATION_IN_PROGRESS
DELIVERY_ITEMS_MISSING
DELIVERY_USER_REVIEW_REQUIRED
DELIVERY_PACKAGE_READY
PROJECT_ARCHIVED
```

## Local stage projection

Read, when present:

```text
planning/stage1_status.json
surface_design/surface_status.json
interface_design/interface_status.json
calculation_results/result_status.json
formal_calculations/formal_status.json
formal_calculations/formal_result_status.json
results_analysis/processing_status.json
manuscript_generation/manuscript_status.json
```

Extract local state only from a controlled field such as `state`, `status`, or `current_state`. Never infer it from a filename or timestamp. Record file path, size, SHA-256, parsed state, and parse result in the snapshot.

Approved gates require both local state and required immutable artifacts. A global transition must not change the local file.

## Dependencies and approvals

`stage_dependencies.json` contains stable dependency IDs, owning routes, prerequisite gates, required records, and whether a missing item blocks entry or final approval. Do not silently edit dependency definitions after initialization; create a new global revision and decision record.

`user_approvals.json` contains append-only entries with approval ID, level, subject, subject version/hash, actor, timestamp, confirmation text, and source approval files. Levels are:

```text
INFORMATIONAL
REVIEW_REQUIRED
EXPLICIT_APPROVAL_REQUIRED
LOCKED_AFTER_APPROVAL
```

Locked entries may be superseded by a new version but never overwritten.

## Resume records

`resume_context.json` records current stage/task, model/input/result versions, completed and incomplete steps, last decision, allowed next operations, and its source state revision. Each pause also writes `project_control/resume_history/resume_vNNN.json`.

The current recovery files are pointers for convenience. History files are immutable. Recovery must pass the state and hash audit before routing.

## Registries and identifiers

Each registry has:

```json
{
  "schema_version": 1,
  "kind": "MODEL",
  "entries": [],
  "retired_ids": []
}
```

ID prefixes and example subtypes:

```text
MODEL-BULK-001
MODEL-SURFACE-001
MODEL-INTERFACE-001
CALC-OPT-001
CALC-SCF-001
CALC-PDOS-001
RESULT-ENERGY-001
EVIDENCE-CHARGE-001
CONCLUSION-MECHANISM-001
```

Normalize subtype to uppercase ASCII letters, digits, and hyphens. Scan all registries and retired IDs before allocation. Never allocate an existing ID.

All entries record `id`, `kind`, `subtype`, `version`, `status`, `created_at`, `source_files`, and `notes`. Source files record path, SHA-256, size, role, and whether they are original or approved.

Additional required relations:

- MODEL: model version and approved stage-1 task IDs.
- CALC: model IDs, approved stage-1 task IDs, actual input/output records, planned/actual parameters, differences, impact, and user confirmation.
- RESULT: calculation IDs, real result files, processed data files, and the six result-quality/scope fields.
- EVIDENCE: result IDs, processed data files, evidence role, validation state, and limitations.
- CONCLUSION: evidence IDs, approved strength, scope, limitations, and manuscript eligibility.

## Traceability

`conclusion_traceability.json` contains one record per conclusion version. A complete chain resolves:

```text
conclusion ID
→ evidence ID(s)
→ result ID(s) and processed data
→ calculation ID(s) and actual input/output files
→ model ID(s)
→ approved stage-1 task ID(s)
```

Set `TRACEABILITY_COMPLETE` only if every required node exists and every cited file record is readable with the recorded hash. Otherwise set `TRACEABILITY_INCOMPLETE`, list exact gaps, and set `manuscript_eligible: false`.

## Parameter differences

Parameter records contain:

```text
planned_parameters
actual_parameters
parameter_differences
difference_classification
difference_impact
user_confirmation
```

Classify each key as `RUNTIME_ONLY`, `NUMERICAL_STABILITY`, `SCIENTIFICALLY_RELEVANT`, or `MODEL_CHANGING`. When a nested key matches multiple classes, use the most scientifically consequential class and require explicit review for the final two classes.

Actual parameters require at least one hashed source identified as an actual input or output. Missing actual data remains unknown; never copy the planned value.

## Error reports

Controlled types:

```text
FILE_ERROR
SYNTAX_ERROR
ENVIRONMENT_ERROR
NUMERICAL_CONVERGENCE_ERROR
MODEL_ERROR
REFERENCE_SYSTEM_ERROR
DATA_PROCESSING_ERROR
SCIENTIFIC_INTERPRETATION_ERROR
PROVENANCE_ERROR
```

Each report records a version, summary, evidence files, affected IDs, owning route, recommended action, and whether user action is required. It never claims automatic repair or calculation execution.

## Dashboard contract

The generated dashboard displays current stage/task, completed stages, pending tasks, current model/parameter/result versions, next user action, required return files, latest error, latest approval, traceability status, delivery completeness, audit conflicts, and links to existing stage review pages.

Do not display estimated runtime, memory, storage, fabricated progress, or an action that bypasses approval. Embed a read-only snapshot; do not derive state from editable DOM fields.

Bind every `delivery_status.json` to `project_version`. A ready package from an earlier project version cannot satisfy a new archive gate after reopening.

## Immutability

- Version every conflict, resume, error, delivery-check, and archive record.
- Refuse to replace an existing immutable version.
- Preserve original uploads and stage approvals.
- Treat modification time as informational only.
- Recalculate hashes during audit and report changes; never update the recorded hash automatically.
- Delivery copies do not become provenance sources unless explicitly registered.
