# Calculation Result Return, Acceptance, and Routing

## Contents

1. Scope and delivery handoff
2. Result files to request
3. Immutable result intake
4. Analysis order
5. Surface and interface failure routing
6. Parameter regeneration and restart routing
7. Optimized-structure acceptance
8. Next approved task
9. Output and stopping rules

## Scope and delivery handoff

Use this workflow after geometry-optimization structures, inputs, dependencies, and local/HPC scripts have been approved and delivered. Never execute a scientific program, MPI launcher, generated script, scheduler command, queue query, remote download, or background monitor. Do not ask the user to keep a page open, wait in place, or expect automatic continuation.

Preserve `INTERFACE_FILES_APPROVED` in `interface_design/interface_status.json`. Start an isolated result state store instead:

```text
python <skill>/scripts/result_review.py start \
  --interface-dir <project>/interface_design \
  --results-dir <project>/calculation_results
```

Verify the full interface/file approval baseline and its checksums before creating the store. Set `calculation_results/result_status.json` to `WAITING_FOR_USER_CALCULATION_RESULT`. This means only that files were delivered and real external results are required. It does not mean the Skill is running or watching a calculation.

Display this prompt without changing its meaning:

> 几何优化所需的结构文件、计算输入文件和运行脚本已经生成，并已完成静态检查。
>
> 请根据提供的运行说明，在本地工作站或超算平台上自行执行计算。你不需要保持当前页面持续打开，也不要退出或删除本次对话。计算结束后，请返回本对话，上传输出文件、优化后的结构文件和错误日志，或者直接描述计算状态与关键现象。
>
> 收到真实计算结果后，我会检查计算是否正常结束、几何优化是否收敛、结构是否合理，并判断需要重新设计材料表面、修改界面模型、调整计算参数，还是可以进入下一计算步骤。

Do not promise automatic retrieval or analysis. Stop the active workflow after showing the prompt.

## Result files to request

Prefer complete outputs and final structures over screenshots or a single energy value. Request the actual input and job error log whenever possible.

- Quantum ESPRESSO: main `.out`, actual input, final coordinates/structure, stderr, and necessary restart information.
- CP2K: main output, final coordinate file, trajectory, restart file, actual input, and stderr.
- Gaussian: `.log`/`.out`, actual `.gjf`/`.com`, `.chk`/`.fchk`, and final optimized structure.
- ORCA: `.out`, actual `.inp`, final `.xyz`, `.gbw`, and relevant Hessian/gradient files.
- GROMACS: minimization `.log`, final `.gro`, `.edr`, actual `.mdp`, topology, and stderr.

When only a description is available, request program termination, geometry-convergence message, final residual force, total-energy trend, SCF behavior, separation/collapse/reconstruction observations, and exact error messages. Treat description-only evidence as incomplete unless it contains enough verifiable information and later receives the required files. Never accept a screenshot or single scalar as proof of optimization.

## Immutable result intake

Prepare a result manifest using `stage-2-result-return-schema.md`, then run:

```text
python <skill>/scripts/result_review.py ingest \
  --results-dir <project>/calculation_results \
  --manifest <result-manifest.json>
```

Copy every supplied file to `user_uploaded/batch_vNNN/`, record the source path, role, size, and SHA-256, and create immutable `result_batch_vNNN.json`. Never overwrite approved inputs or earlier uploads. Set `CALCULATION_RESULT_RECEIVED` only after a real file or an explicit detailed result description is recorded.

Do not accept a user's statement such as “finished” or “looks fine” as a reliability judgment. The program ending, electronic SCF convergence, geometry convergence, and scientific structural reasonableness are four separate checks.

## Analysis order

Read the actual files rather than filenames. Create a structured analysis and submit it through the result engine. Follow this order:

1. Compare the actual input with the approved input package. Record every difference in functional, pseudopotential/basis, cutoff, k points, occupation/smearing, dispersion, spin, charge, constraints, lattice, boundary, optimizer, and scheduler-relevant paths. Distinguish numerical, structural, core-method, and resource-only changes.
2. Check program termination and file integrity: normal end, incomplete output, job interruption, syntax, dependency, disk, permission, MPI, scheduler, or path errors.
3. Check electronic iterations: SCF convergence, oscillation, maximum iteration, occupations, charge, and magnetic moments.
4. Check geometry convergence against the approved force, displacement, energy, and step criteria. Normal program exit without geometry convergence is not a completed optimization.
5. Inspect the final structure: interface separation, overlaps, bonds, coordination, surface reconstruction, slab center, component composition, fixed regions, vacuum, periodic boundaries, and spin/magnetic state.
6. Check comparison integrity: interface and controls must still share the required cell, strain, composition conventions, and numerical settings.

Every finding must cite an ingested file/checksum and a concrete observation, or be marked unknown. Do not fabricate missing values.

## Surface and interface failure routing

Choose `重新设计材料表面` and state `RETURN_TO_SURFACE_REDESIGN` when the approved surface itself fails independently of interface registry or numerical convergence. Examples include collapse, non-target severe reconstruction, atom/ligand detachment, loss of termination, no bulk-like center, too-thin slab coupling, insufficient vacuum, uncompensated polarity/dipole, inappropriate fixed layers, lost defect/dopant structure, or environment-inconsistent functionalization.

Report the failed surface evidence, downstream parameters affected, recommended surface changes, and reusable files. Do not hide a surface-model failure by changing SCF settings.

Choose `重新设计材料界面` and state `RETURN_TO_INTERFACE_REDESIGN` when both components remain basically reasonable but their combination fails: complete separation, overlap, penetration, implausible contact, strain-induced distortion, wrong order, poor initial distance, or non-target reaction. Prioritize registry, rotation, match cell, strain distribution, initial distance, order, fixed region, or contact-group changes. Do not proceed to electronic-structure analysis.

## Parameter regeneration and restart routing

Choose `重新生成几何优化参数` and state `REGENERATE_OPTIMIZATION_FILES` when the model remains physically defensible but numerical/file settings fail: SCF oscillation, insufficient electronic iterations, unsuitable mixing/smearing, incorrect initial moments, unstable ionic step/optimizer, parallel setup, or dependency path.

Record before/after values, reason, and whether each change affects numerical stability only or may alter the scientific result. Do not casually replace the functional, pseudopotential, basis, dispersion, or spin method. A core-method change requires a reapproved stage-1 record; until then choose `补充必要文件后重新判断`.

Choose `生成优化重启文件` and state `OPTIMIZATION_RESTART_FILES_REQUIRED` only when a valid final/last structure exists, geometry is near convergence and scientifically reasonable, and termination was caused by walltime, interruption, or ionic-step limit rather than a structural failure. Preserve the approved method, boundary, constraints, and spin. Label restart files as continuation of the same optimization. Generate files and scripts only; do not run them.

For either decision, materialize a new versioned follow-up package under `regenerated_optimization_files/` or `restart_files/`. Require static checks and show the same external-execution handoff. The decision state remains recorded while `awaiting_user_rerun: true`.

If evidence is insufficient or core changes await confirmation, choose `补充必要文件后重新判断`; keep state `CALCULATION_RESULT_RECEIVED` and list exactly what is missing.

## Optimized-structure acceptance

Choose `优化结构通过，可以进入下一步` and set `OPTIMIZED_STRUCTURE_ACCEPTED` only when all are true:

```text
actual inputs match the approved version or every difference is reapproved
program terminated normally
SCF converged stably
geometry met the approved convergence criteria
final structure has no evident nonphysical distortion
target surface/interface composition is preserved
fixed regions and periodic boundaries are correct
comparison systems remain comparable
complete readable final structure exists
```

Copy the accepted structure to `accepted_structures/vNNN/` with its original checksum and provenance. This status says only that user-supplied results passed review. It never says the Skill performed the calculation.

## Next approved task

After `OPTIMIZED_STRUCTURE_ACCEPTED`, read the actual stage-1 approved task order and prerequisites. Do not invent a next calculation or bypass an adsorption-design stage.

Use the `next-step` command and data contract to generate files only for an approved task:

- interface binding energy: optimized interface and same-strain component A/B single-point inputs;
- charge-density difference: interface/A/B inputs with identical lattice, atom positions, grids, and numerical settings;
- DOS/PDOS: SCF, NSCF, and required post-processing inputs from the accepted structure;
- COHP: compatible electronic-structure/projection inputs and explicit LOBSTER or equivalent dependencies;
- adsorption: route to adsorption-configuration design; do not place an arbitrary molecule or generate formal adsorption inputs here.

Materialize new files in `next_step_files/vNNN/`, statically validate them, and do not execute or submit them. A generated next-step package begins another external calculation cycle and must later use a separate result-return record.

## Output and stopping rules

For every analysis version produce JSON and Markdown containing actual files, termination, SCF, geometry, structure, parameter differences, missing evidence, problem attribution, exact decision, recommended action, reusable artifacts, and next-step access.

Use exactly one decision label:

```text
重新设计材料表面
重新设计材料界面
重新生成几何优化参数
生成优化重启文件
补充必要文件后重新判断
优化结构通过，可以进入下一步
```

Do not use ambiguous conclusions such as “基本可以”, “看起来没问题”, or “应该能继续”. Never generate formal electronic/bonding/mechanism files until the optimized structure is accepted. Never execute, submit, query, terminate, restart, monitor, wait for, or remotely download a calculation.
