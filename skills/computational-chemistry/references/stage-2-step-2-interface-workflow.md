# Stage 2 Step 2: Interface Selection, Construction, and File Generation

## Contents

1. Scope and entry gates
2. Mandatory browser selection
3. User proposal review
4. Interface typing and software compatibility
5. Periodic lattice matching and strain
6. Interface form, contacts, distance, and constraints
7. Defects, boundary conditions, and spin
8. Candidate generation and static checks
9. Calculation and reference files
10. Scheduler and local-run templates
11. Completion boundary

## Scope and entry gates

Use this step only to select two approved surfaces, construct traceable interface candidates, and generate files that the user may later run. Permit structure parsing/transformation, two-dimensional lattice matching, coordinate construction, duplicate detection, static geometry checks, input-file rendering, dependency manifests, and scheduler/local-run script rendering.

Never launch a scientific executable, MPI launcher, scheduler command, queue query, post-processor, or generated script. In particular, do not execute `pw.x`, `cp2k.psmp`, `g16`, `orca`, `gmx`, `mdrun`, `lammps`, `vasp`, `mpirun`, `srun`, `sbatch`, `qsub`, `bsub`, `squeue`, `qstat`, or `bjobs`. Do not invent optimized structures, energies, convergence, equilibrium distances, binding, charge transfer, DOS/PDOS, COHP, or bonding results. File generation is not calculation completion.

Before creating `interface_design/`, verify both immutable upstream baselines:

```text
planning/stage1_status.json                    status = APPROVED
planning/stage1_plan_approved.json
planning/stage1_plan_approved.md
planning/stage1_approval_record.json

surface_design/surface_status.json             status = SURFACE_DESIGN_APPROVED
surface_design/surface_design_approved.json
surface_design/surface_design_approved.md
surface_design/surface_approval_record.json
```

Require matching project IDs, recorded checksums, stage-1 `stage2_access: true`, and surface `next_step_access: true`. Recheck the frozen checksums before initialization, editing, and approval. Treat every upstream file as read-only. If either baseline is incomplete, unapproved, inconsistent, or modified, stop before generating interface files.

Extract the stage-1 goal, evidence tasks, approved software/module/method, functional, basis or pseudopotential, dispersion, spin, convergence policy, and target observables. Extract every retained approved surface's material, facet, termination, cell, layers, vacuum, constraints, defect/dopant/functionalization state, spin, structure files, generator provenance, and version.

Start the isolated workflow with:

```text
python <skill>/scripts/interface_review.py start \
  --stage1-planning-dir <project>/planning \
  --surface-dir <project>/surface_design \
  --interface-dir <project>/interface_design
```

## Mandatory browser selection

Set `WAITING_FOR_INTERFACE_SELECTION`. Open the local review page and show all retained approved surface models. Display more than a material name: show the material, Miller index, termination, in-plane cell, slab layers, pristine/defect/doped/functionalized state, fixed region, spin, structure checksum, and surface version.

Require the user to choose the lower and upper surface and confirm the order. Do not infer the final pair from the research goal. Permit swapping the order; do not treat reversed asymmetric stacks as equivalent. Record `user_selected: true` and `order_confirmed: true` before progressing.

For command-line capture, prepare a selection JSON and run:

```text
python <skill>/scripts/interface_review.py select \
  --interface-dir <project>/interface_design \
  --selection <selection.json>
```

Copy selected upstream structures into `interface_design/selected_surfaces/` without changing the upstream originals. Preserve their checksums. A browser upload or user path may be copied to `user_interface_proposal/`, but it is evidence or a proposed composite, never an authorization to replace the two approved components.

## User proposal review

When the user supplies an interface structure, matching proposal, experimental interface image, literature model, or contact hypothesis, read the actual content before using it. Classify each choice as directly usable, requires modification, requires confirmation, or not recommended.

Check whether it uses the approved component surfaces and aligns with the approved goal. Inspect lattice mismatch, atom overlap, short bonds, cell size, vacuum, strain allocation, fixed regions, retained defects/dopants/functional groups, spin, and periodicity. Compare it with system candidates in experimental relevance, matching quality, contact chemistry, access to target observables, and relative workload. Do not silently overwrite it or silently prefer it.

## Interface typing and software compatibility

Record the type in `interface_type.json` before candidate construction. Distinguish:

- crystal–crystal periodic interfaces: full two-dimensional matching, rotation, strain, and termination;
- 2D–2D stacks: registry, twist, layer distance, and dispersion;
- MOF–inorganic interfaces: nodes, linkers, pore mouths, and termination;
- MOF–polymer and polymer–inorganic interfaces: chain conformation, protonation, functional-group orientation, cross interactions, and restraints;
- molecule–surface systems: route to the later adsorption workflow instead of forcing full 2D matching;
- finite cluster–cluster interfaces: nonperiodic boundary and cluster-specific methods.

Check the exact software approved in stage 1. Quantum ESPRESSO, CP2K, and a stage-1-approved periodic code may be compatible with periodic interfaces. Gaussian and ORCA require a justified finite cluster with treated boundaries and an approved cluster approximation. GROMACS requires validated component and cross-interaction force-field parameters; missing parameters block formal files. Multiwfn and LOBSTER are analysis tools, not interface optimizers. Do not change software automatically. If incompatible, stop formal input generation and explain whether stage 1 must be revised or a user-approved cluster approximation is possible.

## Periodic lattice matching and strain

For periodic interfaces, compare the complete two-dimensional lattice matrices, not one scalar length. Search physically meaningful surface supercells and rotations while jointly controlling mismatch, area, and atom count. Record for every match:

- the A and B in-plane integer transformations;
- relative rotation;
- matched in-plane vectors and angle;
- A and B strain along both in-plane directions;
- angle changes, area, total atom count, and ranking status;
- strain-distribution mode and its physical rationale.

Use `epsilon = (L_matched - L_original) / L_original * 100%` only as a directional summary. For nonorthogonal cells, retain the full matrix/tensor comparison. Do not obtain small mismatch by creating an unjustifiably huge system, and do not obtain a small model by imposing unjustifiably high strain.

Support substrate-fixed, A-only, B-only, shared, and explicitly weighted strain. Never default all strain to one side. Preserve an experimental substrate when the project justifies it. Softer polymers, 2D sheets, or MOFs may accept more strain only with a recorded rationale. Use one consistent reference-state rule across comparable candidates.

## Interface form, contacts, distance, and constraints

Choose one explicit model form: single interface plus vacuum, symmetric double interface, periodic superlattice, or finite cluster interface. Record how many interfaces the periodic cell contains and whether they are equivalent. Do not mix energy definitions between forms.

For each retained lattice match, construct only a few chemically distinct contacts. Use meaningful translations, high-symmetry registries, active-site alignments, donor–acceptor contacts, under-coordinated-metal/heteroatom contacts, hydrogen-bond orientations, aromatic stacking, or justified polymer conformations. Do not enumerate random rotations or near-duplicate microtranslations.

Record the upper component's fractional in-plane translation, rotation, target atom pairs, intended interaction, and initial separation. Choose separation from atomic radii, roughness, functional groups, and interaction type; never apply one universal value. Record the minimum intercomponent distance and reject overlap or penetration.

## Defects, boundary conditions, and spin

Preserve every approved defect, dopant, ligand, hydroxyl, adsorbed species, and functional group. If it clashes, alter registry, distance, or a documented local conformation; do not delete it for convenience. Identify whether a defect is interface-active or a background defect. When stage 1 asks for a defect effect, prepare matched pristine and defect controls with the same cell, strain, and calculation policy.

Define fixed and relaxed atoms by indices, layers, elements, or coordinate ranges. Keep interface-near atoms relaxable. Common choices are fixed bulk-like interior layers for crystal–crystal systems, fixed inorganic bottom layers for polymer–surface systems, or fixed matched in-plane lattice with ionic relaxation for 2D stacks. Do not freeze all contact atoms or release all lattice degrees without a scientific reason.

For a single interface plus vacuum, align vacuum with the interface normal and test for artificial periodic contact. For asymmetric slabs, record the software-specific dipole treatment. A periodic superlattice has no vacuum and normally creates two periodic interfaces; state their equivalence. Never mix 2D and 3D boundary assumptions.

Inherit and recheck spin whenever either component contains transition metals, radicals, defects, dopants, or known magnetism. Generate a few approved representative magnetic arrangements only when scientifically required; keep the initial-spin policy consistent across comparisons.

## Candidate generation and static checks

Name candidates traceably:

`lower-surface__upper-surface__matchNN__stackNN__dXpY__vNNN`

Record structure files, checksums, source-surface checksums, generator script/version, lattice transforms, rotation, strain, translation, distance, constraints, manual edits, and reproducibility. Generate structures only through an installed, verified parser/builder or a project script that can reproduce them. If ASE, pymatgen, or another reliable library is unavailable, do not fabricate coordinates; keep the workflow unapproved until real structures and records exist.

Deduplicate by lattice, rotation, periodic translation, symmetry, atom mapping, contact pairs, and local fingerprints when tools permit. Merge candidates differing only by cell origin, symmetry, or atom ordering. Preserve chemically different terminations, contacts, defect locations, or conformations.

Perform only static checks: lattice and cell orientation, component identity, atom count, overlaps, short bonds, penetration, broken ligands, vacuum direction, strain, charge, spin, fixed indices, and provenance. Static checks do not prove relaxation convergence or scientific correctness.

## Calculation and reference files

Generate inputs only from the stage-1-approved software and method. Inherit the functional, basis/pseudopotential family, dispersion, spin, convergence logic, and evidence-related outputs. Adjust k-point density, periodicity, constraints, dipole settings, or cell degrees only when required by the interface model, and record every adjustment.

Separate low-cost prescreen files from formal optimization files. Label prescreen parameters as screening-only. Never describe them as final accuracy.

For Quantum ESPRESSO, normally generate fixed-cell `relax` inputs with `if_pos` constraints. Generate restricted `vc-relax` only when stage 1 permits the intended cell degree; do not release matched in-plane vectors indiscriminately. Recompute k points from comparable reciprocal-space density and list pseudopotential dependencies.

For CP2K, generate the necessary `GLOBAL`, `FORCE_EVAL`, `DFT`, `SUBSYS`, `SCF`, `MGRID`, `XC`, `MOTION`, boundary, and constraint sections. List basis, potential, and dispersion data dependencies.

For Gaussian or ORCA, first require a finite cluster, boundary treatment, charge, multiplicity, geometry constraints, and the approved cluster approximation. Do not relabel a complete periodic slab as a cluster. For GROMACS, block formal files until all component and cross parameters are traceable; generated `.mdp`, topology, index, and restraint files remain unexecuted.

When later binding energy is approved, generate the interface and isolated-component reference inputs with the same in-plane cell, strain, supercell, vacuum/reference convention, and numerical parameters. Do not substitute fully relaxed unstrained component energies without explicitly separating strain energy. This step generates references only; it computes no energy.

## Scheduler and local-run templates

Read user cluster information and existing scripts before rendering scheduler files. Accept scheduler, partition/queue, account, node/core layout, MPI policy, module commands, executable path, walltime, memory, work directory, and naming rules only from the user or a supplied cluster template. Otherwise use conspicuous placeholders such as `<PARTITION>` and list them as pending. Never claim a resource choice is optimal.

Generate SLURM, PBS, or LSF files and a submission-command explanation, but do not execute them. Generate local command templates when requested, using placeholders such as `<NPROC>`. Environment-loading and executable commands belong only in delivered text files.

Run static file checks without invoking the target program. Distinguish format passed, logic passed, dependencies pending, user fields pending, and properties that static checking cannot determine. Do not state that an input will converge merely because it parsed statically.

## Completion boundary

Review and approve using `stage-2-step-2-interface-review.md`. Complete only when:

- both upstream gates and checksums pass;
- the user explicitly selects two approved surfaces and their order;
- interface type and software compatibility are recorded;
- periodic matching/strain or a justified nonperiodic alternative is complete;
- distinct contacts, structures, provenance, duplicate review, and static geometry checks exist;
- prescreen/formal inputs as applicable, independent references, dependency manifest, and scheduler/local templates exist;
- static validation and browser impact review are complete;
- the user explicitly approves the final version;
- all immutable approved files exist and status is `INTERFACE_FILES_APPROVED`.

Stop there. Do not run, submit, query, terminate, restart, download results, or enter optimization/result analysis automatically.
