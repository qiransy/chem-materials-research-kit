# Stage 2 Step 3 Formal Calculation Data Contract

## Contents

1. Directory and state contract
2. Frozen entry gate
3. Formal plan and task graph
4. Batch version contract
5. File and static-validation contract
6. Approval contract
7. Result batch and analysis contract
8. Exact decision map
9. Evidence completion contract
10. Protected and prohibited values

## Directory and state contract

Write only within:

```text
formal_calculations/
├── versions/vNNN/
│   ├── calculation_inputs/
│   ├── postprocess_inputs/
│   ├── reference_systems/
│   ├── hpc_scripts/
│   ├── local_run_scripts/
│   ├── dependencies/
│   └── validation/
├── approved_batches/<batch_id>/
├── user_results/<batch_id>_result_vNNN/
├── parsed_results/
├── accepted_results/
├── rejected_results/
├── regenerated_inputs/
├── result_analysis/
├── formal_calculation_plan_vNNN.json
├── formal_calculation_plan_vNNN.md
├── formal_task_graph.json
├── formal_change_log.json
├── formal_review.html
├── formal_status.json
├── formal_result_status.json
├── formal_result_analysis_vNNN.json
├── formal_result_analysis_vNNN.md
└── parameter_difference_report_vNNN.md
```

Permit only:

```text
WAITING_FOR_FORMAL_TASK_SELECTION
FORMAL_TASK_GRAPH_GENERATED
FORMAL_INPUTS_GENERATED
REFERENCE_INPUTS_GENERATED
HPC_SCRIPTS_GENERATED
FORMAL_STATIC_VALIDATION_COMPLETED
WAITING_FOR_FORMAL_FILE_APPROVAL
FORMAL_CALCULATION_FILES_APPROVED
WAITING_FOR_FORMAL_CALCULATION_RESULT
FORMAL_CALCULATION_RESULT_RECEIVED
FORMAL_RESULT_VALIDATED
FORMAL_RESULT_REJECTED
FORMAL_FILES_REGENERATION_REQUIRED
NEXT_FORMAL_BATCH_READY
FORMAL_EVIDENCE_NODE_COMPLETED
FORMAL_CALCULATION_WORKFLOW_COMPLETED
```

Never use a status implying that the Skill ran a calculation.

## Frozen entry gate

`formal_status.json.entry_gate` contains absolute file records with path, SHA-256, and size for stage-1 approval/status/plan/Markdown; supplied surface/interface approvals; the accepted optimization result status/analysis; accepted structure files; actual optimization inputs; and parameter-difference evidence. Recheck these records before every mutation.

Require `OPTIMIZED_STRUCTURE_ACCEPTED`, a valid current analysis hash, and at least one accepted structure record. Store `calculation_executed_by_skill: false`, `job_submitted_by_skill: false`, `queue_queried_by_skill: false`, `remote_result_retrieval: false`, and `background_monitoring: false` in state, approvals, batches, and analyses.

## Formal plan and task graph

`formal_task_graph.json` requires:

```json
{
  "project_id": "",
  "source_stage1_plan": {},
  "nodes": [
    {
      "task_id": "T01",
      "task_name": "",
      "task_type": "high_precision_scf",
      "scientific_question_id": "",
      "software": "",
      "module": "",
      "method": {},
      "systems": [],
      "controls": [],
      "target_parameters": [],
      "target_data_forms": [],
      "scientific_meaning": "",
      "supported_conclusions": [],
      "evidence_role": "",
      "prerequisites": [],
      "downstream_dependencies": [],
      "priority": "",
      "necessity": "",
      "status": "pending"
    }
  ],
  "edges": [],
  "evidence_nodes": [],
  "deleted_task_ids": [],
  "topological_order": [],
  "completed_task_ids": [],
  "completed_evidence_node_ids": []
}
```

Task IDs must be unique; all dependency IDs must exist among retained nodes; the graph must be acyclic. Deleted/rejected/replaced tasks stay only in `deleted_task_ids` and cannot be selected. Infer task type only to select a file/result contract; do not change stage-1 scientific meaning.

`formal_calculation_plan_vNNN.json` requires project ID, plan version, batch ID, selected task IDs, prerequisite snapshot, accepted structure record, actual optimization parameter audit, software/method snapshot, batch purpose, dependencies, reference definitions, projection selections, output requests, scheduler/local configuration, generated artifacts, static validation, pending fields, reconfirmation items, known risks, and version record.

Before approval, require an `optimization_parameter_matrix` with entries for software, software version, functional, basis, pseudopotential, dispersion, Hubbard U, cutoffs, k points, spin, occupations, fixed atoms, lattice, total charge, and boundary conditions. Each entry records approved value, actual value, `match | difference_reapproved | difference_numerical | not_applicable | unknown`, scientific impact, and source. Bind `optimization_parameter_source.sha256` to a preserved actual optimization input. Unknown values block approval. A core-setting difference cannot be classified as ordinary numerical tuning; `difference_reapproved` requires an immutable stage-1 reapproval file record.

## Batch version contract

A candidate batch must contain only prerequisite-ready tasks. Selection records require `user_selected: true`, a nonempty reason, and `include_supplemental_tasks` explicitly recorded. Adsorption task types must set `route: ADSORPTION_CONFIGURATION_DESIGN_REQUIRED` and contain no formal calculation file specs.

Every edit or restoration creates a new `vNNN`; never overwrite `versions/vNNN` or plan files. Compare changes by JSON path. Classify high impact for structure/lattice/functional/pseudopotential/basis/dispersion/Hubbard U/spin/core method/charge/boundary/reference definition; medium for k points, cutoffs, grid, projection scope, output window, numerical SCF, or scheduler logic; low for labels and user-provided resource fields. A conflict with stage-1 approval adds a reconfirmation item and blocks approval.

## File and static-validation contract

Each `file_specs` item requires:

```json
{
  "path": "calculation_inputs/system__task__method__v001.in",
  "role": "calculation_input",
  "task_id": "T01",
  "system_id": "S01",
  "software": "Quantum ESPRESSO",
  "source": "approved method and accepted structure",
  "content": "...",
  "structure_source": {"path": "", "sha256": ""},
  "parameters": {},
  "dependencies": []
}
```

Allow text or base64 content and safe relative paths only. First path component must be one of `calculation_inputs`, `postprocess_inputs`, `reference_systems`, `hpc_scripts`, `local_run_scripts`, `dependencies`, or `validation`. Reject ambiguous names such as `calc1`, `test_new`, or `final2` unless the approved upstream system actually has that identifier.

Require file roles needed by the selected task type. Examples:

```text
high_precision_scf: calculation_input + structure/reference record + run instruction
binding_or_formation_energy: composite calculation + every reference-energy term + run instruction
charge_density_difference: composite density + every component density + postprocess input + run instruction
dos_pdos: SCF dependency + NSCF + DOS/selected-PDOS postprocess + run instruction
cohp_coop_bonding: compatible electronic input + wavefunction/projection settings + selected-pair configuration + run instruction
qtaim: compatible density/wavefunction output request + conversion/instruction when needed
```

`static_validation` requires:

```json
{
  "file_format": "passed | failed",
  "parameter_logic": "passed | failed",
  "task_dependencies": "passed | failed",
  "reference_comparability": "passed | failed | not_applicable",
  "files_checked": [],
  "pending_user_fields": [],
  "scientific_reconfirmation": [],
  "not_determinable": []
}
```

The engine independently verifies safe paths, declared roles/tasks, file checksums, prerequisite readiness, accepted-structure linkage, explicit placeholders, and applicable comparability booleans. Runtime convergence remains not determinable.

## Approval contract

Run `formal_review.py review` only from `WAITING_FOR_FORMAL_FILE_APPROVAL` with no validation errors, pending required fields, or scientific reconfirmation. Create a batch-specific immutable `approved_batches/<batch_id>/` and the required root approved aliases only after a matching confirmed browser `approved` decision. If a root alias already exists for a previous batch, archive it by batch and replace only the aliases after verifying their recorded hashes; never change an earlier approved batch directory.

`formal_calculation_approval_record.json` records user confirmation, candidate version/hash, batch ID, task IDs, accepted structure, actual optimization audit, approved manifests for every directory, static validation, pending optional fields, and all five false execution flags.

After recording `FORMAL_CALCULATION_FILES_APPROVED`, transition to `WAITING_FOR_FORMAL_CALCULATION_RESULT` and return the exact handoff prompt from the workflow.

## Result batch and analysis contract

Result manifest fields:

- `batch_id` and `approved_batch_sha256` matching the active approval;
- `software` and `result_kind: formal_calculation`;
- `files` with actual paths, semantic roles, `task_id`, and `system_id` where applicable;
- `description_only`, `user_description`, and actual execution context.

Allowed roles include `actual_input`, `main_output`, `stderr`, `energy`, `density`, `wavefunction`, `checkpoint`, `restart`, `dos`, `pdos`, `charge_partition`, `cohp`, `coop`, `bond_order`, `qtaim`, `structure`, `job_script`, `postprocess_output`, and `other`. Copy before analysis and checksum every stored file.

Formal analysis requires:

- approved-versus-actual input differences;
- program termination and electronic convergence by task/system;
- file completeness by expected output role;
- reference comparability checks;
- task-specific validity checks;
- evidence items tied to stored file/checksum and concrete observations;
- problem attribution, affected task IDs, reusable artifacts, correction, and return route;
- exactly one decision code/label;
- accepted task IDs and completed evidence node IDs only when supported.

Description-only results can conclude only that necessary files are missing. Core-method changes awaiting stage-1 confirmation cannot be accepted or treated as ordinary numerical regeneration.

## Exact decision map

| Code | Exact label | State | Required basis |
| --- | --- | --- | --- |
| `FORMAL_RESULT_VALID_NEXT_BATCH` | `当前正式计算结果有效，可以生成下一批文件` | `NEXT_FORMAL_BATCH_READY` | Current task valid and at least one downstream task is prerequisite-ready |
| `FORMAL_RESULT_FILES_MISSING` | `当前结果缺少必要文件，需要补充文件后重新判断` | `FORMAL_CALCULATION_RESULT_RECEIVED` | Missing/description-only evidence; set `awaiting_additional_files: true` |
| `FORMAL_REGENERATE_PARAMETERS` | `当前计算参数存在问题，需要重新生成正式计算文件` | `FORMAL_FILES_REGENERATION_REQUIRED` | Model/references valid; file or non-electronic parameter issue |
| `FORMAL_REGENERATE_REFERENCES` | `参考体系设置不一致，需要重新生成并计算对照组` | `FORMAL_FILES_REGENERATION_REQUIRED` | Difference/reference definition or comparability failure |
| `FORMAL_ELECTRONIC_UNSTABLE` | `当前电子结构结果不稳定，需要调整数值参数` | `FORMAL_FILES_REGENERATION_REQUIRED` | Model valid; SCF/NSCF instability or electronic numerical issue |
| `FORMAL_RETURN_OPTIMIZATION_REVIEW` | `优化结构存在问题，需要返回几何优化结果审查` | `FORMAL_RESULT_REJECTED` | Accepted optimization structure/input is now contradicted by formal evidence |
| `FORMAL_RETURN_INTERFACE_DESIGN` | `界面模型存在问题，需要返回材料界面设计阶段` | `FORMAL_RESULT_REJECTED` | Interface-model failure evidence |
| `FORMAL_RETURN_SURFACE_DESIGN` | `表面模型存在问题，需要返回材料表面设计阶段` | `FORMAL_RESULT_REJECTED` | Surface-model failure evidence |
| `FORMAL_EVIDENCE_NODE_COMPLETE` | `当前证据节点已经完成，可以进入下一证据节点` | `FORMAL_EVIDENCE_NODE_COMPLETED` or `FORMAL_CALCULATION_WORKFLOW_COMPLETED` | All required tasks for the node accepted |

Do not use ambiguous conclusions. Return routes are recorded in formal state but do not mutate the upstream workflow.

## Evidence completion contract

Maintain task states `pending`, `batched`, `awaiting_result`, `accepted`, `rejected`, or `regeneration_required`. Update the task graph by creating a new immutable graph snapshot and current `formal_task_graph.json`; retain `formal_task_graph_vNNN.json` history.

A downstream task is ready only when all prerequisite task IDs are accepted. An evidence node is complete only when its required selected task set is accepted. Workflow completion requires all retained necessary tasks and all `required: true` evidence nodes. The engine must not let user-edited completion fields bypass this calculation.

## Protected and prohibited values

Protect upstream file records, project/task/evidence IDs, accepted structure provenance, approved candidate manifests, user-result originals, analysis history, and graph history. User edits cannot change engine-owned version, hashes, timestamps, execution flags, completion states, or protected gates.

Reject estimated runtime/memory/storage fields, claimed Skill execution/submission/query/retrieval/monitoring, fabricated outputs, path traversal, overwritten versions, generated commands being invoked, unapproved tasks, missing mathematical reference terms, or downstream tasks with unmet prerequisites.
