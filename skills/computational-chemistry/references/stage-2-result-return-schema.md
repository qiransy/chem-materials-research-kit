# Calculation Result Return Data Contract

## Contents

1. Directory and immutable versions
2. Delivery gate and status
3. Result batch manifest
4. Analysis object
5. Decision rules
6. Follow-up file packages
7. Optimized-structure acceptance
8. Next-task package
9. Protected and prohibited data

## Directory and immutable versions

Write only under:

```text
calculation_results/
├── user_uploaded/
│   └── batch_v001/
├── parsed_outputs/
├── accepted_structures/
├── rejected_structures/
├── restart_files/
├── regenerated_optimization_files/
├── next_step_files/
├── calculation_result_handoff.md
├── result_batch_v001.json
├── result_analysis_v001.json
├── result_analysis_v001.md
├── parameter_difference_report_v001.md
├── parameter_difference_report.md
├── result_change_log.json
└── result_status.json
```

Create new batch and analysis versions without overwriting earlier records. `parameter_difference_report.md` may be a current readable pointer, but retain every numbered report. Never modify files in `planning/`, `surface_design/`, or `interface_design/`.

## Delivery gate and status

Require the six interface approval targets, `interface_status.json` with `INTERFACE_FILES_APPROVED`, and a consistent `interface_file_approval_record.json`. Recheck approved JSON/parameter/Markdown hashes, approved calculation/HPC manifests, and frozen stage-1/surface links.

Store an engine-owned `delivery_gate` snapshot in `result_status.json`. Include `calculation_executed_by_skill: false`, `job_submitted_by_skill: false`, `background_monitoring: false`, and `automatic_result_retrieval: false` in every state.

Permit these result states:

```text
WAITING_FOR_USER_CALCULATION_RESULT
CALCULATION_RESULT_RECEIVED
RETURN_TO_SURFACE_REDESIGN
RETURN_TO_INTERFACE_REDESIGN
REGENERATE_OPTIMIZATION_FILES
OPTIMIZATION_RESTART_FILES_REQUIRED
OPTIMIZED_STRUCTURE_ACCEPTED
```

For the decision `补充必要文件后重新判断`, remain `CALCULATION_RESULT_RECEIVED` and set `awaiting_additional_files: true`.

## Result batch manifest

Require:

| Field | Meaning |
| --- | --- |
| `software` | Must match the approved optimization software |
| `result_kind` | `geometry_optimization` |
| `files` | Actual user paths and semantic roles |
| `user_description` | User statement preserved without upgrading it to evidence |
| `description_only` | True only when no file is available |
| `described_facts` | Termination, SCF, geometry, forces, energy trend, structure behavior, and errors when description-only |
| `actual_execution_context` | Local/HPC, scheduler, script, and user-reported changes when known |

Allowed file roles include:

```text
actual_input
main_output
final_structure
trajectory
restart
checkpoint
wavefunction
stderr
job_script
topology
parameters
energy_file
other
```

Copy files to `user_uploaded/batch_vNNN/` and add `stored_path`, SHA-256, size, original path, and ingestion time. Do not infer a role solely from an extension when the content contradicts it.

Recommended minimum evidence for acceptance:

- Quantum ESPRESSO: `actual_input`, `main_output`, `final_structure`;
- CP2K: `actual_input`, `main_output`, `final_structure`, preferably trajectory/restart;
- Gaussian: `actual_input`, `main_output`, final structure, preferably checkpoint;
- ORCA: `actual_input`, `main_output`, `final_structure`, preferably `.gbw`;
- GROMACS: actual parameters, main log, final structure, topology, preferably energy file.

Description-only, screenshot-only, or single-energy evidence cannot satisfy optimized-structure acceptance.

## Analysis object

Require top-level fields:

| Field | Required content |
| --- | --- |
| `result_batch_version` | Existing immutable batch |
| `software` | Approved/actual software |
| `actual_input_check` | Approved-versus-run version and parameter differences |
| `program_termination` | `normal`, `abnormal`, `interrupted`, or `unknown` plus evidence |
| `electronic_scf` | `converged`, `not_converged`, `unstable`, or `unknown` plus evidence |
| `geometry_optimization` | `converged`, `not_converged`, `near_converged`, `interrupted`, or `unknown` |
| `structure_assessment` | `reasonable`, `surface_failure`, `interface_failure`, `nonphysical`, or `unknown` |
| `comparison_integrity` | Cell/strain/composition/parameter comparability checks |
| `file_completeness` | `sufficient` or `insufficient`, missing roles, and limitations |
| `problem_attribution` | Primary category and concrete issue codes |
| `source_evidence` | Ingested file path/checksum, evidence type, and observation |
| `decision_code`, `decision_label` | Exactly one permitted conclusion |
| `decision_reasons` | Nonempty, evidence-linked reasons |
| `affected_downstream_parameters` | Results/files invalidated by the issue |
| `recommended_action` | Concrete corrective or next action |
| `reusable_artifacts` | Files/decisions that remain valid |
| `final_structure_files` | Ingested final/last-valid structures used for judgment |
| `followup_file_specs` | Required only for regeneration/restart decisions |
| `followup_static_validation` | Static checks for generated follow-up files |

Each status object must contain a concrete `evidence` list. Evidence items reference an ingested `stored_path` and SHA-256, except an explicitly unknown/missing finding. Preserve excerpts/observations without inventing absent numeric values.

`actual_input_check` requires:

```json
{
  "match_status": "exact_match | modified_reapproved | modified_unapproved | unknown",
  "approved_input_files": [],
  "actual_input_files": [],
  "differences": [
    {
      "parameter": "",
      "approved_value": null,
      "actual_value": null,
      "category": "core_method | numerical | structure_constraint | boundary | resource | path_dependency",
      "scientific_impact": "",
      "reapproval_status": "not_required | approved | required"
    }
  ],
  "core_method_consistent": true,
  "comparability_impact": "",
  "actual_version_label": ""
}
```

Core-method changes include functional, pseudopotential/basis family, dispersion, or spin method. Do not treat them as ordinary convergence tuning.

Structure checks require booleans or explicit unknowns for composition preserved, component identity, interface separation, overlaps, bonds/coordination, surface termination, bulk-like slab center, defects/dopants/functional groups, fixed regions, vacuum/periodicity, and magnetic state.

## Decision rules

Map exactly:

| Code | Label | Result state |
| --- | --- | --- |
| `RETURN_TO_SURFACE_REDESIGN` | `重新设计材料表面` | `RETURN_TO_SURFACE_REDESIGN` |
| `RETURN_TO_INTERFACE_REDESIGN` | `重新设计材料界面` | `RETURN_TO_INTERFACE_REDESIGN` |
| `REGENERATE_OPTIMIZATION_FILES` | `重新生成几何优化参数` | `REGENERATE_OPTIMIZATION_FILES` |
| `OPTIMIZATION_RESTART_FILES_REQUIRED` | `生成优化重启文件` | `OPTIMIZATION_RESTART_FILES_REQUIRED` |
| `ADDITIONAL_FILES_REQUIRED` | `补充必要文件后重新判断` | remain `CALCULATION_RESULT_RECEIVED` |
| `OPTIMIZED_STRUCTURE_ACCEPTED` | `优化结构通过，可以进入下一步` | `OPTIMIZED_STRUCTURE_ACCEPTED` |

Require attribution issue codes. Surface codes may include `surface_collapse`, `non_target_reconstruction`, `termination_lost`, `ligand_detached`, `no_bulk_like_center`, `slab_too_thin`, `vacuum_insufficient`, `uncompensated_polarity`, `surface_constraints_invalid`, `defect_or_dopant_lost`, or `functionalization_environment_mismatch`.

Interface codes may include `components_separated`, `atom_overlap`, `component_penetration`, `implausible_contact`, `strain_distortion`, `wrong_order`, `initial_distance_invalid`, or `non_target_reaction`.

Numerical codes may include `scf_oscillation`, `electronic_steps_exhausted`, `mixing_invalid`, `smearing_invalid`, `initial_magnetization_invalid`, `ionic_step_unstable`, `optimizer_unstable`, `parallel_error`, or `dependency_path_error`.

Restart codes may include `walltime_interruption`, `scheduler_interruption`, or `ionic_step_limit` and require near-converged/reasonable structure plus a readable last-valid structure.

Reject a decision inconsistent with its evidence category. `OPTIMIZED_STRUCTURE_ACCEPTED` requires every acceptance condition from the workflow and no unapproved core-method difference.

## Follow-up file packages

For `REGENERATE_OPTIMIZATION_FILES`, require `parameter_changes` with before/after, reason, and effect class `numerical_stability` or `scientific_method`. A `scientific_method` change requires an actual stage-1 reapproval record before materialization.

For `OPTIMIZATION_RESTART_FILES_REQUIRED`, require a referenced last-valid structure, continuation metadata, unchanged method/boundary/constraints/spin booleans, and restart input plus HPC/local-run script.

Represent `followup_file_specs` as text/base64 records with safe relative path, role, software, source, and content. Materialize only into a new versioned directory. Require at least one input and one execution-instruction script. Store checksums and static validation. Never execute them.

## Optimized-structure acceptance

Copy accepted structures to `accepted_structures/vNNN/`; copy structures supporting rejected redesign decisions to `rejected_structures/vNNN/`. Preserve the uploaded original and record source path/checksum. An accepted structure must be readable, have a final-structure role, and be cited by the analysis.

Set:

```json
{
  "program_normal": true,
  "scf_converged": true,
  "geometry_converged": true,
  "structure_reasonable": true,
  "composition_preserved": true,
  "constraints_and_boundaries_correct": true,
  "comparability_preserved": true,
  "final_structure_complete": true,
  "actual_parameters_confirmed": true
}
```

All must be true for acceptance.

## Next-task package

Permit next-task materialization only from `OPTIMIZED_STRUCTURE_ACCEPTED`. Require an accepted structure record, a retained stage-1 task ID, satisfied prerequisites, task type, scientific purpose, comparison rules, `file_specs`, dependency records, and static validation.

Task-specific required roles:

```text
interface_binding_energy:
  interface_single_point, component_a_single_point, component_b_single_point
charge_density_difference:
  interface_density, component_a_density, component_b_density
dos_pdos:
  scf, nscf, dos_or_pdos_postprocess
cohp:
  compatible_scf_or_nscf, wavefunction_projection, bonding_analysis_dependency
adsorption_configuration_design:
  no formal calculation files; route to adsorption-model design
```

For binding/CDD, require explicit equality checks for cell, strain, positions where required, grids, and numerical settings. Write `next_task_vNNN.json`, `next_task_vNNN.md`, and `next_step_files/vNNN/`. Do not run or submit the package.

## Protected and prohibited data

Protect the delivery gate, upstream paths/checksums, approved files, original uploads, batch versions, analysis versions, accepted/rejected structure provenance, and generated-file hashes. No editor may rewrite them.

Reject claimed automatic monitoring/retrieval, background execution, Skill-executed calculation, fabricated convergence/energy/force/structure values, or statuses implying the Skill ran a job. Do not overwrite upstream or history. Do not call calculation, MPI, scheduler, queue, remote-download, or generated-script commands.
