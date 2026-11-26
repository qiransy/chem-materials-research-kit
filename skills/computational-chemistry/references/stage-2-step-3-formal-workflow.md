# Stage 2 Step 3: Formal Calculation Evidence Workflow

## Contents

1. Scope and entry gate
2. Restore the approved evidence chain
3. Minimal batch sequencing
4. Task-specific generation rules
5. Static validation and review
6. Approval and external execution handoff
7. Result return and judgment
8. Evidence-node progression
9. Stopping and isolation rules

## Scope and entry gate

Use this workflow only to convert retained stage-1 evidence tasks into versioned formal calculation batches after geometry optimization has been accepted. It may generate structures, inputs, reference systems, post-processing inputs, extraction/conversion scripts, local-run instructions, and scheduler scripts. It may read user-returned outputs and data files. It must never run a scientific/post-processing program, generated script, MPI launcher, scheduler command, queue command, remote download, or background monitor.

Require and checksum:

- `planning/stage1_plan_approved.json`, its Markdown, approval record, and `stage1_status.json` with `APPROVED`;
- the applicable approved surface and/or interface baseline;
- `calculation_results/result_status.json` with `OPTIMIZED_STRUCTURE_ACCEPTED`;
- the immutable accepted result analysis and at least one accepted final-structure record;
- the user-returned actual optimization input and its approved-versus-run difference analysis.

Write only under `formal_calculations/`. Do not modify `planning/`, `surface_design/`, `interface_design/`, or `calculation_results/`.

## Restore the approved evidence chain

Restore every retained, nondeleted stage-1 task with its scientific question, systems, controls, software, module, method, targets, output forms, meaning, conclusions, evidence role, prerequisites, downstream dependencies, priority, necessity, and status. Preserve stage-1 IDs. Never restore a deleted/replaced duplicate or add a task merely because installed software supports it.

Build an acyclic formal task graph and link stage-1 evidence nodes to task IDs. Classify each task without changing its approved meaning, using types such as `high_precision_scf`, `binding_or_formation_energy`, `charge_density_difference`, `quantitative_charge`, `dos_pdos`, `cohp_coop_bonding`, `qtaim`, `adsorption_configuration_design`, `classical_md`, or `approved_other`.

Record actual optimization differences before formal generation. Resource/script-only differences may be retained. Numerical changes require comparability analysis. Changes to functional, pseudopotential/basis, dispersion, Hubbard U, spin method, primary boundary conditions, charge model, or core model require stage-1 reconfirmation and block file approval.

## Minimal batch sequencing

Generate only the smallest prerequisite-ready batch. A normal dependency pattern is:

```text
accepted optimized structure
└── high-precision static SCF
    ├── comparable energy/reference systems
    ├── comparable density/reference systems
    ├── NSCF
    │   ├── DOS
    │   └── selected PDOS
    └── compatible wavefunction/projection output
        ├── selected COHP/COOP
        └── approved QTAIM route
```

Do not materialize all expensive downstream tasks in one batch. A later batch may be generated only after every prerequisite result has passed its task-specific acceptance rule. Adsorption tasks must route to an adsorption-configuration design step before formal adsorption input generation.

## Task-specific generation rules

### High-precision static calculation

Use the accepted lattice and coordinates without ionic optimization. Preserve the approved method, spin, boundary, charge, and fixed-region interpretation. Tighten numerical settings only when the approved plan permits it and record the relationship to optimization settings. Generate only outputs required by downstream approved tasks.

### Binding, adsorption, or formation energy

Generate the composite and every mathematical reference term together. For an interface binding energy use:

```text
E_bind = E_interface - E_A - E_B
```

Keep the same in-plane cell, strained geometry convention, supercell, vacuum, core numerical settings, and method. Derive same-strain component references by deleting the other component while preserving remaining atomic positions unless an approved strain-decomposition task explicitly requires separately relaxed references. Never compute the energy inside the Skill.

For adsorption energy, require an approved adsorption configuration and generate the combined system, surface, and isolated adsorbate references with a documented comparable convention.

### Charge-density difference and charge partitioning

For `Δρ = ρ_composite - ρ_A - ρ_B`, use identical lattice, FFT/grid logic, positions inherited from the composite, pseudopotentials/basis, cutoffs, k points, spin, and occupations. Do not reoptimize isolated components. Generate Bader, Hirshfeld, NPA, or another partition only when explicitly approved and keep its quantitative role distinct from the spatial CDD role.

### DOS and selected PDOS

Require an accepted SCF dependency. Generate the approved SCF/NSCF/post-processing chain for the chosen program. Use compatible k points, energy window, smearing, and Fermi reference. Select elements, atoms, and orbitals from the scientific question; do not mechanically project every orbital on every atom.

### COHP/COOP/bond order/QTAIM

Require compatible wavefunction/density output, pseudopotential/basis/projection support, sufficient bands, energy range, and explicitly selected atom pairs. Never generate all atom pairs. For QTAIM, document required density/wavefunction conversions and limitations; do not claim compatibility without readable output requirements.

### Software-specific constraints

- Quantum ESPRESSO: use traceable `prefix`/`outdir`; `scf` for static and `nscf` for non-self-consistent work; keep pseudo paths and grid/cell logic consistent; remove ionic optimization sections from static inputs.
- CP2K: inherit approved functional, basis, pseudopotential, dispersion, MGRID, periodicity, charge, and spin; remove geometry-motion sections from static tasks.
- Gaussian: use only the approved finite-cluster boundary, charge, multiplicity, method, constraints, and reference fragments; generate checkpoint and `formchk` instructions when approved, but never execute them.
- ORCA: preserve charge, multiplicity, method, dispersion, SCF criteria, and required GBW/Molden output; limit high-level methods to their approved evidence role.
- GROMACS: enforce minimization → equilibration → production dependencies and approved force field/topology/protonation. Treat it as sampling only when downstream electronic evidence requires quantum calculations.

## Static validation and review

Perform only non-scientific-program static checks:

- accepted-structure source/checksum and readable structure metadata;
- atom count/elements and lattice consistency;
- task IDs, prerequisites, prefix/path dependencies, and no cycles;
- method/spin/charge/boundary inheritance;
- basis/pseudopotential/dependency manifests;
- required reference terms and reference comparability;
- CDD cell/coordinates/grid settings;
- SCF → NSCF → DOS/PDOS dependencies;
- wavefunction/projection/band requirements for bonding analysis;
- scheduler fields derived from user data or explicit placeholders.

Record independently: format passed, parameter logic passed, task dependency passed, reference comparability passed/not applicable, pending user fields, scientific parameters requiring reconfirmation, and runtime facts that static checks cannot determine. Never describe static validation as convergence proof.

Generate `formal_review.html`, serve it locally, and show tasks, purpose, software/module, accepted structure, targets, references, dependency graph, generated files, scripts, static validation, pending fields, history, and impact. Do not display predicted runtime, memory, or storage.

Allow the user to modify supplemental inclusion, priority, reference naming, selected projection atoms/pairs, post-processing outputs/windows, script fields, and directories. Treat structure, lattice, method, functional, pseudopotential/basis, dispersion, spin, Hubbard U, charge, or primary boundary changes as high-impact and require the owning approval gate. Every edit or restoration creates a new immutable version with new materialized files.

## Approval and external execution handoff

Approve only a valid current version with explicit user confirmation. Freeze:

```text
formal_calculation_plan_approved.json
formal_calculation_plan_approved.md
formal_calculation_approval_record.json
calculation_inputs_approved/
postprocess_inputs_approved/
reference_systems_approved/
hpc_scripts_approved/
local_run_scripts_approved/
dependencies_approved/
```

Record `FORMAL_CALCULATION_FILES_APPROVED`, then set the active result wait state to `WAITING_FOR_FORMAL_CALCULATION_RESULT` and display exactly:

> 当前正式计算批次所需的结构文件、计算输入文件、参考体系文件、后处理文件和运行脚本已经生成，并完成静态检查。
>
> 请按照任务依赖和运行说明，在本地工作站或超算平台上自行执行计算。你不需要保持当前页面持续打开，但请保留本次对话。当前批次完成后，请返回本对话并上传实际使用的输入文件、主输出文件、错误日志及后续分析所需的电子密度、波函数或其他结果文件。
>
> 收到真实计算结果后，我会检查计算参数、程序结束状态、电子收敛、文件完整性、参考体系可比性和数据是否满足当前科学任务，并判断是否需要重新生成文件，还是可以进入下一批正式计算。

Stop. Do not wait in place or promise automatic continuation.

## Result return and judgment

Copy every returned file into a new immutable `user_results/<batch>_result_vNNN/` directory and set `FORMAL_CALCULATION_RESULT_RECEIVED`. Prefer actual inputs, main outputs, stderr, density, wavefunction/checkpoint/restart, post-processing data, and reference-system outputs. A description-only return cannot validate an evidence node.

Check in order:

1. actual input and script versus the approved batch;
2. termination, missing files, syntax/dependency/path/scheduler failures;
3. electronic convergence, stability, occupations, charge, and magnetization;
4. task-specific output completeness;
5. reference comparability or grid/coordinate identity;
6. scientific usability for the current target, without inventing missing values.

Choose exactly one conclusion from the schema. Normal termination alone never establishes evidence validity. Store evidence-linked findings, actual parameter differences, affected tasks, reusable files, correction, return route, and next-batch eligibility.

## Evidence-node progression

Mark a task complete only after its returned result satisfies its task-specific acceptance contract. Mark an evidence node complete only when all required task alternatives chosen for that node have passed. Generate the next prerequisite-ready minimum batch only from `NEXT_FORMAL_BATCH_READY` or `FORMAL_EVIDENCE_NODE_COMPLETED`.

Set `FORMAL_CALCULATION_WORKFLOW_COMPLETED` only when every retained necessary stage-1 task and required evidence node is accepted. Supplemental/conditional tasks do not block completion unless their approved activation condition is met.

## Stopping and isolation rules

- Never execute, submit, query, terminate, restart, monitor, or download a calculation.
- Never infer completion without user-returned evidence.
- Never accept difference quantities with incomparable references or CDD with mismatched grids.
- Never accept DOS/PDOS without valid SCF/NSCF dependencies or COHP without compatible wavefunction/projection output.
- Never generate a downstream batch before current prerequisites pass.
- Never overwrite upstream approvals, formal versions, user results, or analyses.
- Preserve all old workflow states; formal-step return routes are recommendations and do not mutate the owning stage.
