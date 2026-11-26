# Stage 2 Step 2 Interface Review and Approval

## Contents

1. State machine
2. Selection capture
3. Initial file-bearing design
4. Browser review
5. Versioning and impact analysis
6. Static validation and user decisions
7. Approval baseline
8. Failure and stage boundary

## State machine

Use only these stage-specific states:

```text
WAITING_FOR_INTERFACE_SELECTION
└─ explicit lower/upper selection and order → INTERFACE_SURFACES_SELECTED
     └─ matching or justified N/A → LATTICE_MATCHING_COMPLETED
          └─ real candidates generated → INTERFACE_CANDIDATES_GENERATED
               └─ static geometry/provenance pass → INTERFACE_MODELS_VALIDATED
                    └─ input packages written → CALCULATION_INPUTS_GENERATED
                         └─ scheduler/local templates written → HPC_SCRIPTS_GENERATED
                              └─ file checks complete → STATIC_VALIDATION_COMPLETED
                                   └─ browser ready → WAITING_FOR_INTERFACE_FILE_APPROVAL
                                        ├─ user edit → new version + impact analysis
                                        │    └─ WAITING_FOR_INTERFACE_FILE_APPROVAL
                                        ├─ explicit acceptance → INTERFACE_FILES_APPROVED
                                        ├─ continue → WAITING_FOR_INTERFACE_FILE_APPROVAL
                                        ├─ restore → new version → WAITING_FOR_INTERFACE_FILE_APPROVAL
                                        └─ reject edit → previous valid version → WAITING_FOR_INTERFACE_FILE_APPROVAL
```

Never create or accept states implying that an optimization or scientific calculation is running or completed. Browser generation and static validation are not approval.

## Selection capture

After `start`, serve the browser immediately:

```text
python <skill>/scripts/interface_review.py serve \
  --interface-dir <project>/interface_design --open
```

The page must display all approved surface metadata and let the user choose lower and upper components, swap their order, upload an optional proposal, and confirm that the order is intentional. Before this action, remain `WAITING_FOR_INTERFACE_SELECTION` and do not create candidate/interface input versions.

For nonbrowser use, prepare a selection JSON following `stage-2-step-2-interface-schema.md` and call `select`. The engine copies selected approved surface files and verifies the upstream hashes. Selection creates `interface_selection.json` and state `INTERFACE_SURFACES_SELECTED`; it does not construct or calculate the interface.

## Initial file-bearing design

After real interface structures, generator records, file contents, and static checks are prepared, create the source design JSON and run:

```text
python <skill>/scripts/interface_review.py init-design \
  --interface-dir <project>/interface_design \
  --design <interface-design-source.json>
```

The engine must:

1. revalidate both upstream baselines;
2. bind the project, stage-1, surface, and user-selection snapshots;
3. materialize `file_specs` only into new `v001` package directories;
4. create `interface_type.json`, `lattice_matching_report.json`, `interface_candidates_v001.json`, `interface_matrix_v001.csv`, `optimization_parameters_v001.json`, input/static reports, and file manifests;
5. validate real structure/generator files, matching, component preservation, software compatibility, input/reference/script files, dependency status, scheduler origins, and static-check claims;
6. record every required state transition through `WAITING_FOR_INTERFACE_FILE_APPROVAL`.

Fail without promoting the state if selection, software, structure provenance, file content, or logical checks are incomplete. A failed version directory may be retained for diagnosis but must not become the current valid version.

## Browser review

Display at least:

- stage-1 goal, evidence tasks, approved software/method snapshot;
- lower/upper approved surfaces, order, facet, termination, cell, layers, state, constraints, and spin;
- interface type and model form;
- lattice transforms, rotation, both components' two-direction strain, angle change, area, atom count, and strain distribution;
- candidate contacts, translation, distance, minimum distance, interaction, fixed/relaxed regions, vacuum/boundary/dipole, spin, structure preview, and scientific use;
- prescreen and formal input files;
- independent component references;
- scheduler and local-run scripts, environment commands, dependency manifest, placeholders, and pending fields;
- static format/logic/dependency results and items that cannot be decided statically;
- version history, before/after differences, scientific/file impacts, validation errors, and risks.

Do not display predicted runtime, memory, storage, or an allegedly optimal resource allocation. File links may display or download text and structures but must never execute them.

Permit editing of lower/upper selection among approved IDs, order, match cells, rotation, strain allocation, distance, translation, contact sites, constraints, vacuum, candidate count/disposition, interface-adjusted input parameters, scheduler, environment, and resource request fields. Keep upstream model definitions and historical versions read-only.

## Versioning and impact analysis

Every submitted edit requires a reason and creates the next immutable JSON, CSV, optimization-parameter record, reports, calculation package directories, and script directories. Never edit an older directory in place.

Compare stable IDs and classify concrete impacts:

- selected surface, order, interface type/model form, software, functional, basis/pseudopotential, dispersion, or spin-method changes: `CRITICAL`; require upstream consistency review and possibly return to stage 1 or surface design;
- surface-cell transforms, rotation, matched lattice, strain values/distribution, vacuum/boundary, or component-reference convention: `HIGH`; rebuild structures and inputs and reassess comparability;
- translation, target contacts, initial distance, fixed/relaxed region, or local conformation: `MEDIUM` or `HIGH` according to contact changes;
- candidate inclusion/exclusion and prescreen/formal parameter changes: at least `MEDIUM`, with evidence-chain and screening consequences;
- scheduler partition/account/module/path/nodes/cores/memory/walltime edits: `LOW` for scientific conclusions, but regenerate scripts and warn that invalid resources can prevent execution;
- dependency completion or corrected file path: `LOW` or `MEDIUM` for science, but may change execution readiness.

Explain effects on local chemistry, interface reconstruction, mismatch/strain, model size, periodicity, independent-reference comparability, later binding energy, charge transfer, electronic/bonding analyses, and final interpretation. Never emit only a severity label.

If a user edits an upstream-approved surface attribute instead of selecting another approved ID, reject the edit. If the software or method no longer matches stage 1, keep the version invalid until the owning stage is reapproved.

## Static validation and user decisions

Static validation distinguishes:

```text
format passed
logic passed
dependencies complete or explicitly pending
user parameters complete or explicitly pending
not determinable statically
```

It checks files and cross-references but never invokes the target program. Do not infer convergence or correctness of future results.

Offer:

- 接受当前界面与文件
- 继续修改
- 恢复历史版本（另存为新版本）
- 拒绝当前修改

Rejecting an edit retains the rejected history and returns to the previous valid candidate. Restoring copies the historical design into a new version and regenerates new package directories. Continuing preserves history. Acceptance always requires explicit user confirmation.

## Approval baseline

From `WAITING_FOR_INTERFACE_FILE_APPROVAL`, run `interface_review.py review`. Only a matching confirmed browser `approved` decision may revalidate upstream hashes, structures, version files, static checks, and package manifests and create the immutable files/directories defined by the schema. Do not overwrite any pre-existing approved target.

Copy the exact current calculation package to `calculation_inputs_approved/`, including prescreen/formal/reference subdirectories. Copy current scheduler/local templates to `hpc_scripts_approved/`. Copy retained structures to `approved_interfaces/`. Calculate hashes after copying and store them in `interface_file_approval_record.json`.

The approval record must explicitly state:

- file generation and static checks completed;
- `calculation_executed: false` and `job_submitted: false`;
- whether dependencies or user/cluster placeholders remain;
- no convergence or result claim was made;
- the commands shown in scripts are user-execution instructions only.

Set `INTERFACE_FILES_APPROVED` only after the complete baseline exists. Do not run or submit the approved files.

## Failure and stage boundary

- If stage 1 or surface approval/checksum fails, do not create the interface state store.
- If the user has not selected both surfaces and order, remain `WAITING_FOR_INTERFACE_SELECTION`.
- If a selected surface is not retained in the approved baseline, reject it.
- If matching is physically unacceptable, pause file generation and recommend an explicit surface/cell revision; do not silently alter an upstream surface.
- If software is incompatible, stop formal files; do not switch programs automatically.
- If structure tools are absent, do not invent an interface structure.
- If GROMACS cross parameters are absent, do not generate formal GROMACS files.
- If cluster details are absent, use marked placeholders and list them as pending.
- If static checks fail, retain diagnostics but block approval.
- Never overwrite upstream, historical, or approved data.
- Never execute a calculation, scheduler command, queue operation, or post-processing command.
- Stop after `INTERFACE_FILES_APPROVED`; do not start interface optimization or result analysis.
