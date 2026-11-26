# Stage 2 Step 1: Material Surface Design and Model Confirmation

## Contents

1. Scope and entry gate
2. Mandatory user-input pause
3. Input review
4. Bulk-reference validation
5. Facet and termination design
6. Slab, vacuum, supercell, and constraints
7. Defects, doping, functionalization, and spin
8. Candidate generation and screening
9. Software and reproducibility
10. Outputs and completion boundary

## Scope and entry gate

Design, generate, inspect, screen, review, and approve a small set of physically meaningful surface models that serve the evidence chain approved in stage 1. Permit candidate structure generation, deterministic structure checks, and explicitly labeled low-cost prescreening. Do not start formal adsorption, interface binding, DOS/PDOS, COHP, charge-density difference, quantitative charge, QTAIM, reaction-barrier, or production-MD calculations.

Before doing anything else, read and verify:

```text
planning/stage1_plan_approved.json
planning/stage1_plan_approved.md
planning/stage1_approval_record.json
planning/stage1_status.json
```

Require status `APPROVED`, `stage2_access: true`, all approved files, and a matching approved-plan checksum when recorded. Extract the research object, composition, core question, target observables, controls, software constraints, experiment links, and evidence roles. Never revise them silently. If surface feasibility conflicts with the approved goal, stop this step and request explicit re-approval of the affected earlier decision.

Start the isolated state store with:

```text
python <skill>/scripts/surface_review.py start --stage1-planning-dir <project>/planning --surface-dir <project>/surface_design
```

## Mandatory user-input pause

Set `WAITING_FOR_SURFACE_INPUT`, then ask the user before generating formal surface structures. Use this natural prompt:

> 在开始构建材料表面之前，请确认你是否已经有自己的表面模型设计方案，例如目标晶面、Miller 指数、表面终止、slab 层数、真空层、面内超胞、固定层、缺陷类型、掺杂位置、表面官能团或界面接触方式。
>
> 同时请说明是否有能够支持表面选择的实验数据，例如 XRD 择优取向、HRTEM 晶格条纹、SAED、XPS 表面价态、EPR 缺陷信息、EXAFS 配位结果、FTIR 或 Raman 表面基团、BET、接触角、材料形貌、合成条件、热处理条件或相关文献结果。
>
> 若已有方案或实验数据，将优先以这些信息为依据进行模型构建和合理性审查；若没有，将根据晶体结构、第一阶段批准的科学目标和计算工作量提出候选表面方案。

Do not bypass this pause using assumptions. After the reply, create a structured input summary and run the `input` command described in `stage-2-step-1-surface-review.md`.

## Input review

If the user supplies a proposal, classify each choice as retain, adjust, convergence-test, or not recommended. Check scientific alignment, target-site exposure, stoichiometry, termination, polarity, dipole, coordination, supercell size, slab thickness, vacuum, constraints, and periodic images. Do not copy it blindly or replace it with defaults.

If the user supplies experiments:

- use XRD preferred orientation, HRTEM fringes, and SAED to constrain plausible facets without treating one spacing as unique proof;
- use XPS, EPR, EXAFS, and composition to constrain oxidation, defects, under-coordination, and doping;
- use FTIR, Raman, contact angle, humidity, and surface-chemistry observations to assess hydroxyls, water, residual ligands, or other functionalization;
- use synthesis temperature, calcination, redox atmosphere, solvent, and post-treatment to assess termination and environment.

Treat experiments as constraints, not automatic one-to-one model assignments. Build a main model plus a few explicit alternatives when uncertainty remains. If proposal and experiment conflict materially, remain before model generation and explain consequences for adsorption sites, energies, electronic structure, charge transfer, and mechanism interpretation.

If no proposal and no experiment exist, continue from the approved goal and a validated bulk structure. Distinguish theoretical-stability candidates, functional candidates, and comparison surfaces. Never claim a theoretical candidate is experimentally exposed.

Read actual CIF, POSCAR/CONTCAR, XYZ, PDB, MOL, images, diffraction/spectroscopy data, reports, papers, and prior outputs before using them. Do not infer contents from filenames. Save extracted facts and uncertainties to the required input-summary artifacts.

## Bulk-reference validation

Build every surface from a traceable, validated bulk reference: a user experimental structure, a verified database structure, or a previously optimized periodic structure. Preserve the original and record source, path, checksum, transformations, and optimization status.

Check composition, space group, lattice parameters, coordinates, occupancies, partial occupancy, disorder, missing hydrogen, oxidation states, spin, periodicity, overlaps, isolated atoms, abnormal bonds, and lattice distortion. Resolve disorder or partial occupancy into explicit ordered models and record the method. Do not generate surfaces from an unknown, incomplete, overlapping, or otherwise invalid bulk model.

Keep bulk and surface theory comparable: functional, pseudopotential/basis, dispersion, spin, and convergence definitions must support later comparisons.

## Facet and termination design

Select facets from the approved scientific question rather than enumerating every low-index surface. Prefer experimental facets when supported. Without experiments, choose a few low-index candidates, a stability comparison, and any scientifically necessary functional facet exposing a target metal, defect, pore mouth, edge, or under-coordinated site.

Do not use lowest surface energy as the sole criterion. A higher-energy facet may remain when experiments or the target function justify it. Remove facets with neither experimental relevance nor independent mechanism value.

For every termination, check stoichiometry, surface charge, coordination, equivalence of the two faces, polarity, and net normal dipole. Prefer stoichiometrically and electrostatically defensible slabs. For polar surfaces, explicitly choose among a symmetric slab, stoichiometric adjustment, physical reconstruction, compensating adsorbate, or dipole correction. Do not pass an uncompensated artificial field into formal work.

Treat the ideal bare surface as a theoretical reference, not automatically as the experimental surface. Add only a few environment-supported hydroxylated, oxidized, reduced, hydrated, or ligand-covered terminations.

## Slab, vacuum, supercell, and constraints

Choose slab thickness from layer spacing, material type, polarity, target property, and recovery of bulk-like structure/electronic character in the center. Plan at least two defensibly different thicknesses and define convergence observables before choosing the final slab.

For equivalent two-sided symmetric slabs, surface energy may be evaluated as:

`gamma = (E_slab - N E_bulk) / (2 A)`

Use the factor 2 only when the two surfaces are equivalent. Do not use that expression to assign a single surface energy to an asymmetric slab.

Start vacuum testing for an ordinary neutral surface near 15 Å only as a provisional candidate, never as a universal value. Increase or test it for dipolar/charged surfaces, long adsorbates, extended densities, or large molecules. Define convergence using total energy, work function, electrostatic potential, or the actual target surface observable; visual separation is insufficient.

Choose in-plane cells from adsorbate size, coverage, defect/dopant concentration, interface matching, and periodic-image separation. Record actual defect/dopant concentration and coverage. Compare 2x2, 3x3, or another expansion only when appropriate; never apply a fixed multiplier mechanically. For interfaces, document orientation, rotation, strain allocation, mismatch, and atom count. Do not place all strain on one component without justification.

Specify fixed and relaxed atoms. Common valid patterns include fixing lower bulk-like layers for one-sided models or central layers in symmetric slabs. Avoid both excessive constraints that suppress reconstruction and unconstrained motion that destroys the bulk-like interior. Decide by layer response and target properties.

## Defects, doping, functionalization, and spin

Systematically build defects only when required by the approved plan or experimental evidence. Record type, inequivalent site, concentration, charge state, spin, and coordination. Keep a pristine surface control. Screen inequivalent sites by environment and low-cost calculations before expensive analyses.

For a neutral defect, define the sign convention and use a composition-consistent expression such as `E_f = E_defect - E_perfect + sum_i(n_i mu_i)`. For charged defects, additionally treat Fermi level, band edges, electrostatic/finite-size corrections, and charge compensation. Never apply a neutral expression to a charged defect.

For doping, record substituted site, coordination, concentration, electron count/oxidation implications, and possible spin states. Compare inequivalent sites before selecting one. Keep cell and settings consistent between pristine and doped models.

Add hydroxyls, water, oxygen, hydrogen, ligands, solvent, or intermediates only when experimental environment and the approved goal justify them. Define coverage from count and surface area. Do not enumerate arbitrary coverages.

Identify later adsorption-site classes without running adsorption calculations: top, bridge, hollow, vacancy, under-coordinated metal, dopant, pore mouth, functional-group vicinity, or depression. Keep only chemically distinct environments; do not generate duplicates by small translations or rotations.

For transition metals, radicals, defects, unpaired electrons, or known magnetism, design a few physically meaningful initial FM/AFM/local-moment arrangements. Do not default to non-spin-polarized models. Maintain spin logic across pristine, defective, doped, and later adsorbed systems.

## Candidate generation and screening

Name generated models traceably:

`material_facet_termination_supercell_layers_vacuum_defect-or-functionalization_version`

Avoid names such as `model1`, `test2`, or `final_new`.

Organize every model in the structured matrix defined by `stage-2-step-1-surface-schema.md`. Separate core, stability-control, functional, screening, and rejected models. Keep original bulk, candidate, screened, and rejected structures in separate directories.

Detect symmetry, translation, origin, and atom-order duplicates using a reliable structure matcher when available. Merge physically identical surfaces. Retain genuinely different terminations, defect sites, coverages, or local environments and state their independent scientific role.

Check overlaps, short bonds, broken intact molecules/ligands, coordination, net charge, stoichiometry, polarity, periodic-image separation, vacuum, center recovery, constraints, and spin. Correct or reject obvious problems.

If many candidates remain, permit only low-cost screening such as structural checks, deliberately lower-accuracy relaxation, quick relative surface-energy comparison, or a validated force-field prescreen. Label it as screening. Never promote its energy or electronic outputs to final quantitative evidence.

## Software and reproducibility

Prefer reproducible scripts over manual GUI cutting. Record the input bulk file, Miller index, termination, slab/vacuum dimensions, supercell, constraints, defects, doping, functionalization, and spin for every model.

Use ASE, pymatgen, or another verified structure library when installed. Check its version and actual API before writing the project script. If no reliable surface-building library is available, do not fabricate generated structures; complete the design matrix, report the dependency gap, and keep the step unapproved until real structures can be generated and checked.

Use periodic electronic-structure software consistent with stage 1 for allowed low-cost prescreening. Quantum ESPRESSO can support later periodic relaxation and electronic analysis; CP2K can suit large, complex, MOF, hybrid, interface, AIMD, or QM/MM contexts. Do not use Multiwfn as a surface builder. Use LOBSTER only after compatible plane-wave results exist; it is not a surface-generation tool.

Record any manual coordinate change, its reason, and the affected atoms. Preserve a project-specific generator under `surface_design/scripts/` so every retained structure can be regenerated.

## Outputs and completion boundary

Produce the isolated directory contract from `stage-2-step-1-surface-schema.md`, then review and approve it using `stage-2-step-1-surface-review.md`.

Complete this step only when:

- the stage-1 approved baseline passed its integrity gate;
- the mandatory user-input question was answered;
- user input was validated or explicitly unavailable;
- the bulk structure was validated;
- candidate facets/terminations and slab/vacuum/cell/constraint choices were designed;
- required defect, doping, functionalization, and spin cases were reviewed;
- candidate structures and generation records exist;
- reasonability checks and duplicate handling are complete;
- the browser review and every edit impact analysis are complete;
- the user explicitly approves the final candidate;
- approved surface files exist and status is `SURFACE_DESIGN_APPROVED`.

Stop there. Do not automatically optimize surfaces formally, generate adsorption configurations, build interfaces, or perform any later calculation.
