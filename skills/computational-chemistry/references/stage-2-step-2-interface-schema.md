# Stage 2 Step 2 Interface and File Data Contract

## Contents

1. Directory contract
2. Upstream gates and selection
3. Design object
4. Lattice-match and candidate records
5. Calculation packages and dependencies
6. Static validation
7. Protected and forbidden data
8. Approval baseline

## Directory contract

Write only under the stage-specific namespace:

```text
interface_design/
├── selected_surfaces/
├── user_interface_proposal/
├── lattice_matching/
├── candidate_interfaces/
├── approved_interfaces/
├── reference_components/
├── calculation_inputs/
│   ├── prescreen/
│   └── formal_optimization/
├── hpc_scripts/
│   ├── slurm/
│   ├── pbs/
│   └── lsf/
├── local_run_scripts/
├── dependencies/
├── previews/
├── validation/
├── scripts/
├── interface_selection.json
├── interface_type.json
├── lattice_matching_report.json
├── interface_candidates_v001.json
├── interface_matrix_v001.csv
├── optimization_parameters_v001.json
├── input_generation_report_v001.md
├── static_validation_report_v001.md
├── interface_change_log.json
├── interface_impact_analysis.md
├── interface_review.html
└── interface_status.json
```

Create immutable `vNNN` records and package directories:

```text
calculation_inputs_vNNN/
reference_components_vNNN/
hpc_scripts_vNNN/
local_run_scripts_vNNN/
dependencies_vNNN/
```

Do not write to `planning/` or `surface_design/`. Do not overwrite upstream structures, numbered versions, or approved baselines.

## Upstream gates and selection

Store read-only `stage1_link` and `surface_link` snapshots containing resolved approved-file paths, approved versions, project ID, checksums, goal/software summaries, and surface-model summaries. Revalidate the files from their checksums before every version or approval operation.

Require `interface_selection.json` to contain:

- `lower_surface_id` and `upper_surface_id` from retained approved surface IDs;
- `user_selected: true` and `order_confirmed: true`;
- the non-equivalence rationale when order matters;
- optional user proposal/experiment notes and actual copied file records;
- copied lower/upper component records under `selected_surfaces/`;
- no edited facet, termination, defect, dopant, functionalization, or spin values that diverge from the upstream snapshots.

Allow selection of the same approved surface twice only for a justified homo-interface, grain-boundary, symmetric stack, or equivalent construction with `allow_same_surface: true` and a nonempty rationale.

## Design object

Require top-level fields:

| Field | Meaning |
| --- | --- |
| `project_id` | Stable upstream project ID |
| `workflow_step` | `stage2_step2_interface_files` |
| `stage1_link`, `surface_link` | Engine-owned frozen upstream snapshots |
| `selection` | Final user-authorized lower/upper IDs and copied component records |
| `interface_type` | Category, periodicity, model form, interface count, vacuum rule, rationale |
| `software_compatibility` | Approved software/module, task links, compatibility decision, limits |
| `lattice_matches` | Periodic match records or an explicit justified nonperiodic record |
| `candidates` | Interface structures, contacts, checks, provenance, and dispositions |
| `optimization_parameters` | Inherited and adjusted numerical/method settings with reasons |
| `calculation_packages` | Prescreen, formal optimization, and component-reference package definitions |
| `file_specs` | Text artifacts to materialize into version-specific directories |
| `generated_artifacts` | Engine-owned paths/checksums for materialized files |
| `dependencies` | Required file/module/parameter manifest and status |
| `hpc_configuration` | User/template/placeholder scheduler and environment values |
| `static_validation` | Explicit format, logic, dependency, pending, and unknown results |
| `duplicate_review` | Matcher, tolerances, groups, representatives, and rationale |
| `comparison_policy` | Consistent cell, strain, settings, and component-reference rules |
| `known_risks` | Structural, scientific, software, dependency, or execution risks |
| `workflow_checks` | Required completion booleans and evidence references |

The engine adds `interface_version`, timestamps, and `version_record`. Historical versions are immutable.

## Lattice-match and candidate records

For every lattice match require:

| Field | Required content |
| --- | --- |
| `id`, `status`, `rationale` | Stable identity and retain/reject decision |
| `surface_a_supercell`, `surface_b_supercell` | Two 2×2 integer transforms or explicit replication matrices |
| `rotation_deg` | Relative angle and source |
| `matched_lattice` | Two full in-plane vectors and units |
| `strain_a`, `strain_b` | Direction-1, direction-2, angle change, and tensor/matrix summary |
| `interface_area`, `atom_count` | Size controls with units where applicable |
| `strain_distribution` | A-only, B-only, shared, substrate-fixed, or weighted plus rationale |

For a nonperiodic cluster interface, use one `not_applicable` match record with the boundary/cut rationale rather than inventing 2D strain.

For every candidate require:

- `id`, traceable `name`, `match_id`, lower/upper IDs, and explicit order;
- fractional in-plane translation and relative rotation;
- initial interface distance, minimum intercomponent distance, their units and bases;
- target contact atom pairs and interaction types;
- fixed and relaxed regions;
- vacuum, interface normal, periodic boundary, dipole handling, charge, and spin;
- preservation statements for defects, doping, functionalization, ligands, and component atom counts;
- structure files with actual paths/checksums under `candidate_interfaces/`;
- generator script/checksum, library/version, exact parameters, manual edits, `generated_for_version`, and reproducibility;
- overlap, short-bond, penetration, ligand-integrity, vacuum, strain, charge, spin, constraint, provenance, and component-identity checks;
- duplicate/fingerprint result, classification, retention/rejection reason, scientific use, downstream tasks, and optional preview.

Every retained candidate must have real structure and generator files and all required static geometry checks equal to `passed` or justified `not_applicable`. A design placeholder may be discussed but blocks `INTERFACE_FILES_APPROVED`.

When selection, lattice match, rotation, translation, initial distance, target contacts, vacuum/cell, or another coordinate-affecting field changes, require a new structure filename containing the new `vNNN`, a new checksum/record rather than the previous structure record, and `generation_record.generated_for_version` equal to that version. Scheduler-only or other nonstructural edits may retain the prior structure provenance.

## Calculation packages and dependencies

Require package records for each intended use:

```text
prescreen
formal_optimization
component_reference_a
component_reference_b
```

Permit `not_required` only with a project-specific reason. When later binding energy is planned, both component references are mandatory and must record identical interface cell, strain, vacuum/reference convention, and numerical settings.

Require at least one generated `formal_optimization` package. Every retained candidate must link its package IDs, and every generated package must link at least one materialized artifact. `static_validation.files_checked` must name every calculation, reference, scheduler, and local-run artifact that was statically inspected.

Represent generated text through `file_specs` groups:

```text
calculation_inputs
reference_components
hpc_scripts
local_run_scripts
dependencies
generation_scripts
```

Each file spec requires a safe relative path, content, role, and source/rationale. The engine writes it only to a new version-specific directory and records its SHA-256. Never place a path outside `interface_design/` and never overwrite an earlier version.

Input-file records require software, module, candidate/package ID, purpose, inherited parameters, interface-specific adjustments, and limitations. The structure referenced by an input must have the same atom count, cell, fixed region, charge, and spin recorded in the candidate.

Dependency records require logical name, expected filename, role, software, source, path/checksum when provided, and one status:

```text
provided
missing
user_confirmation_required
not_applicable
```

Missing dependencies may remain only as explicit pending items; they must never be reported as present. Missing GROMACS component or cross-interaction force-field parameters block formal GROMACS inputs.

HPC fields must record `value` and `origin`. Permit origins only `user`, `cluster_template`, or `placeholder`. Placeholder values must be visibly bracketed, for example `<PARTITION>`. Do not infer partitions, accounts, module names, executable paths, nodes, cores, memory, or walltime. Resource fields are execution requests, not performance predictions.

## Static validation

Require:

```json
{
  "format_check": {"status": "passed", "details": []},
  "logic_check": {"status": "passed", "details": []},
  "dependency_check": {"status": "complete_or_explicitly_pending", "details": []},
  "user_parameter_check": {"status": "complete_or_explicitly_pending", "details": []},
  "not_determinable_statically": [],
  "files_checked": []
}
```

Static checking covers required sections/tokens, file paths and checksums, element mapping, atom/cell consistency, coordinate and fixed-index logic, charge, spin, pseudopotential/basis mapping, scheduler placeholders, dependency state, and cross-reference completeness. It cannot determine convergence, stable geometry, equilibrium distance, final energy, charge transfer, or electronic structure.

Require these workflow checks before review and approval:

```json
{
  "stage1_gate_passed": true,
  "surface_gate_passed": true,
  "user_selection_confirmed": true,
  "interface_type_identified": true,
  "software_compatible": true,
  "lattice_matching_completed_or_not_applicable": true,
  "candidates_generated": true,
  "duplicates_resolved": true,
  "geometry_static_checks_passed": true,
  "calculation_inputs_generated": true,
  "component_references_generated_or_not_required": true,
  "hpc_or_local_scripts_generated": true,
  "static_validation_completed": true,
  "browser_review_generated": true
}
```

## Protected and forbidden data

Treat `project_id`, `stage1_link`, `surface_link`, upstream model snapshots/checksums, detected tool versions, historical files, and generated checksums as immutable. Change the lower/upper selection only by selecting other approved model IDs; never edit an approved model's facet, termination, cell, defect, doping, functionalization, or spin in this step.

Reject unsupported performance-prediction fields such as `estimated_runtime`, `runtime_hours`, `estimated_memory`, `memory_gb`, `estimated_storage`, `storage_gb`, or `optimal_resources`.

Reject claimed result fields or statuses such as optimized geometry, total/binding/interface energy, converged result, equilibrium distance, charge transfer, DOS/PDOS, COHP, Bader/QTAIM, reaction barrier, `INTERFACE_OPTIMIZATION_RUNNING`, or `INTERFACE_OPTIMIZATION_COMPLETED`. A generated input, static pass, or scheduler template is never a computed result.

## Approval baseline

On explicit acceptance, create without overwriting:

```text
interface_design_approved.json
optimization_parameters_approved.json
calculation_inputs_approved/
hpc_scripts_approved/
interface_design_approved.md
interface_file_approval_record.json
```

Also copy retained approved structures to `approved_interfaces/` with checksums. The approval record must include the upstream versions/checksums, final interface version, selection/order, interface type, match, rotation, strain, translations, distances, constraints, vacuum/boundary, spin, software/module, generated inputs, references, scripts, dependencies, pending user fields, static-check result, confirmation identity/time, and approved-file hashes. Set `INTERFACE_FILES_APPROVED` only after every required baseline exists.
