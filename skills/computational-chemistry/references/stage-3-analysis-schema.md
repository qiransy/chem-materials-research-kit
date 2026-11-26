# Stage 3 Data and State Contract

## Contents

1. Directory contract
2. State and source-snapshot contract
3. Data-status and progress contract
4. Processing-guide contract
5. Dataset manifest contract
6. Completeness and comparability contract
7. Result-analysis contract
8. Evidence and conclusion-strength contract
9. Approval and completion contract
10. Protected and prohibited values

## Directory contract

Write only within:

```text
results_analysis/
├── user_raw_results/
├── user_processed_data/
├── processing_guides/
├── processing_progress/
├── validated_data/
├── rejected_data/
├── evidence_analysis/
├── experiment_comparison/
├── source_snapshots/
├── result_analysis_vNNN.json
├── result_analysis_vNNN.md
├── evidence_matrix_vNNN.csv
├── processing_status.json
├── analysis_change_log.json
└── result_review.html
```

Do not create an automatic plotting directory. Never use a plot as a completion target.

## State and source-snapshot contract

Permit only:

```text
WAITING_FOR_USER_DATA_STATUS
RAW_DATA_RECEIVED
PROCESSING_GUIDE_REQUIRED
PROCESSING_GUIDE_PROVIDED
USER_PROCESSING_IN_PROGRESS
PROCESSED_DATA_RECEIVED
DATA_COMPLETENESS_CHECKED
DATA_COMPARABILITY_VALIDATED
RESULT_ANALYSIS_COMPLETED
EVIDENCE_CHAIN_VALIDATED
SUPPLEMENTARY_PROCESSING_REQUIRED
RETURN_TO_FORMAL_CALCULATION
WAITING_FOR_RESULT_APPROVAL
RESULTS_APPROVED
```

`processing_status.json` is authoritative. It records project ID, current state, immutable source snapshot, dataset/progress/guide/validation/analysis records, validated evidence-node IDs, pending information, and all execution flags set to false.

The source snapshot contains absolute paths, SHA-256, and sizes for the approved stage-1 JSON/Markdown and the current formal task graph/result-status projection. Recheck it before mutation. If formal sources legitimately advance, `sync-sources` creates a new snapshot version and history entry; it cannot alter stage-1 project/approval or delete prior validated nodes.

## Data-status and progress contract

The optional starting `user_data_status` is one of:

```text
raw
partial
processed
tutorial
resume
```

When absent, enter `WAITING_FOR_USER_DATA_STATUS` and return the exact initial question in the workflow. When present, do not return that question again.

Each progress record requires:

```json
{
  "dataset_id": "D001",
  "task_id": "T02",
  "data_type": "binding_energy",
  "progress_state": "USER_PROCESSING_STEP_4",
  "current_step": 4,
  "completed_steps": [1, 2, 3],
  "reopened_steps": [],
  "user_marker": "正在进行第几步",
  "notes": "",
  "version": "v001"
}
```

Steps must be integers 1–8. A later record cannot remove completed steps. A failed prior step is added to `reopened_steps` while unaffected completion remains. Store each version in `processing_progress/<dataset_id>_progress_vNNN.json`.

## Processing-guide contract

Supported built-in guide types are:

```text
binding_energy
adsorption_energy
charge_density_difference
bader_charge
dos_pdos
cohp
qtaim
approved_other
```

A guide request requires dataset ID, task ID, data type, and `mode: full | step`. `step` mode requires step 1–8. A full guide contains eight ordered items with purpose, input, output, and pass standard plus the exact follow-up invitation. A step guide expands only the requested item and provides concise direct-prerequisite and next-step summaries.

Store guides as `processing_guides/<dataset_id>_<data_type>_guide_vNNN.json` and Markdown. A guide may contain user-specific commands or paths as instructions, but they are never invoked by the engine.

## Dataset manifest contract

An ingestion manifest requires:

```json
{
  "dataset_id": "D001",
  "task_id": "T02",
  "evidence_node_ids": ["E01"],
  "data_type": "binding_energy",
  "data_stage": "raw | partial | processed",
  "files": [
    {
      "path": "absolute/or/manifest-relative/path.csv",
      "role": "table",
      "system_id": "S01",
      "description": ""
    }
  ],
  "key_values": [],
  "metadata": {
    "system_name": "",
    "model_version": "",
    "calculation_task": "",
    "parameter_name": "",
    "unit": "",
    "reference_definition": "",
    "software": "",
    "method": "",
    "atom_or_orbital_assignment": "",
    "image_isovalue": "only when a rendered density image is supplied",
    "color_definition": "only when a rendered density image is supplied",
    "quantitative_support": "numeric dataset/key-value IDs supporting the image",
    "completed_steps": []
  },
  "current_step": null,
  "user_notes": ""
}
```

Require at least one actual file or key value. Task and evidence IDs must exist in the frozen formal graph. Copy files into a new `<dataset_id>_vNNN/`, calculate checksums, and perform only format-level inspection. Accept roles such as actual input/output, stderr, table, CSV, Excel, text, integration, peak positions, processed result, density, charge partition, DOS, PDOS, COHP, QTAIM, image, metadata, or other.

An image-only dataset cannot pass scientific completeness for CDD, DOS/PDOS, or another quantitative result without the associated numeric definition/data. A single energy/value cannot establish a difference quantity unless every approved reference term is present.

## Completeness and comparability contract

A validation submission requires dataset IDs, a current analysis goal, metadata requirements, seven common processing checks, comparability axes, issues, and a resolution scope.

Each check has:

```json
{
  "status": "passed | failed | unknown | not_applicable",
  "observation": "concrete finding",
  "evidence_file_ids": ["D001:F001"]
}
```

The seven common check keys are:

```text
calculation_completed
actual_parameters_checked
target_data_extracted
reference_basis_unified
target_processing_completed
comparability_checked
upload_format_complete
```

Comparability keys are method, model version, unit, reference definition, structure state, numerical parameters, coordinate/atom mapping, and grid or energy zero when applicable. Missing metadata is classified as blocking or nonblocking for the current judgment, with a rationale.

`resolution_scope` is `none`, `processing_only`, or `formal_recalculation`. Formal recalculation requires at least one exact cause:

```text
missing_raw_calculation
wrong_core_parameter
irreparable_reference_incomparability
insufficient_source_precision
```

Format conversion, extraction, unit/zero alignment, mapping, sign interpretation, integration, and table organization are processing-only causes and cannot justify formal recalculation.

## Result-analysis contract

Analyze only datasets whose latest validation has no unresolved blocking completeness/comparability failure. Require:

```json
{
  "dataset_ids": ["D001"],
  "task_ids": ["T02"],
  "analysis_scope": "current task or evidence node",
  "data_conclusion": "",
  "physical_meaning": "",
  "evidence_role": "",
  "corroboration": [],
  "experimental_correspondence": [],
  "conclusion_boundary": [],
  "next_step_judgment": "",
  "trends": [],
  "anomalies": [],
  "evidence_items": [],
  "contradictions": [],
  "processing_causes_checked": {},
  "conclusions": [],
  "validated_evidence_node_ids": [],
  "outcome_code": "CURRENT_ANALYSIS_READY_FOR_APPROVAL"
}
```

Evidence items require ID, evidence role, dataset ID, stored file ID/checksum or key-value reference, and concrete observation. The renderer produces immutable JSON, Markdown, an evidence-matrix CSV, and optional experiment-comparison JSON.

Allowed outcome codes are:

| Code | State | Meaning |
| --- | --- | --- |
| `CURRENT_ANALYSIS_READY_FOR_APPROVAL` | `WAITING_FOR_RESULT_APPROVAL` | Current processed data are usable and the directed analysis is ready for user confirmation |
| `SUPPLEMENTARY_PROCESSING_REQUIRED` | `SUPPLEMENTARY_PROCESSING_REQUIRED` | Existing raw data can fill the gap through additional processing |
| `RETURN_TO_FORMAL_CALCULATION` | `RETURN_TO_FORMAL_CALCULATION` | A permitted fundamental raw-calculation/reference/precision failure requires a narrowly scoped stage-2 step-3 correction |

## Evidence and conclusion-strength contract

Every conclusion uses exactly one of:

```text
STRONGLY_SUPPORTED
SUPPORTED
PARTIALLY_SUPPORTED
INCONCLUSIVE
CONTRADICTED
```

Every non-inconclusive claim cites evidence items. `STRONGLY_SUPPORTED` requires agreement from at least two independent physical evidence roles, not merely two files containing the same observable.

When contradictions are present, `processing_causes_checked` must address reference system, energy zero, atom mapping, model version, calculation parameters, unit conversion, sign convention, and result convergence/validity. Any failed/unknown processing cause prevents a ready-for-approval outcome.

An evidence node can be validated only when its analyzed task set is supported by stored processed data and every contributing formal task has a real accepted result in the current task graph. Record partial node completion without claiming whole-stage completion.

## Approval and completion contract

Only a matching confirmed browser `approved` decision from `analysis_review.py review`, started at `WAITING_FOR_RESULT_APPROVAL`, constitutes user confirmation. Freeze the current analysis, dataset versions, validation versions, source snapshot, conclusion strengths, and node set in an immutable approval record; direct `accept-analysis` calls must not bypass the browser gate.

If every required evidence node is validated and all completion checks pass, set `RESULTS_APPROVED` and `overall_stage_complete: true`. Otherwise set `EVIDENCE_CHAIN_VALIDATED` and `overall_stage_complete: false`; later datasets may continue without erasing the accepted node.

`request-reanalysis` requires a reason, preserves the old analysis, and sets the next state to `PROCESSED_DATA_RECEIVED`. It cannot change a prior approval record.

## Protected and prohibited values

Protect project/evidence/task IDs, stage-1 approval sources, formal source snapshots, original user uploads, dataset/progress/guide/validation/analysis versions, approval records, file checksums, and validated-node history.

Store these values as false in state, manifests, analyses, and approvals:

```text
calculation_executed_by_skill
postprocessing_executed_by_skill
job_submitted_by_skill
queue_queried_by_skill
remote_result_retrieval
background_monitoring
research_figures_generated_by_skill
```

Reject path traversal, overwritten versions, unknown task/evidence IDs, fabricated values, unsupported completion fields, plot/figure-generation requests inside the workflow engine, scientific-program execution, or formal recalculation justified only by a repairable processing gap.
