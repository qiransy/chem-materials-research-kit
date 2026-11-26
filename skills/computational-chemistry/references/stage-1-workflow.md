# Stage 1: Research Goals and Computational Plan

## Contents

1. Scope and intake
2. Goal formulation
3. Scientific-question decomposition
4. Models and controls
5. Evidence-chain construction
6. Task design
7. Redundancy and resource review
8. Decision gates
9. Review and approval handoff
10. Stage boundary

## Scope and intake

Design the research logic; do not execute it. Use the user's current message, previous context, project files, existing calculations, experimental observations, software environment, and compute resources as inputs.

Extract or provisionally infer:

- research object and system class;
- comparison object or baseline;
- experimental phenomenon to explain;
- central scientific question;
- conclusion the work must support or refute;
- available structures, trajectories, wavefunctions, or prior results;
- allowed software, licenses, hardware, and practical cost limits.

Do not block the whole design because some facts are missing. State consequential assumptions, give conditional branches where needed, and list only the details that must be confirmed before implementation.

## Goal formulation

Write the goal as a falsifiable or parameter-testable question. Avoid vague goals such as “study the interface,” “analyze electronic structure,” or “explore the mechanism.”

Prefer forms such as:

- determine whether an interface is thermodynamically stable relative to defined components;
- quantify the direction and magnitude of charge transfer;
- identify which atoms or orbitals dominate an interfacial interaction;
- test whether adsorption changes states near the Fermi level consistently with a conductivity response;
- explain why one material is more selective toward a target gas than explicit competitors;
- determine whether a proposed reaction path is kinetically viable.

Separate the user's desired claim from what the planned calculations can actually establish. Label trend-only support as qualitative or semi-quantitative.

## Scientific-question decomposition

Split the central goal into subquestions with one principal evidence target each. Arrange them in a dependency chain, normally:

1. model and method reliability;
2. structural stability or representative-state selection;
3. thermodynamic or energetic tendency;
4. spatial and quantitative charge redistribution;
5. orbital or bonding origin;
6. kinetic, dynamic, or conformational behavior when relevant;
7. relationship to measured performance.

Do not name a property as the question. Replace “calculate DOS” with the scientific decision the DOS would inform. If one subquestion mixes stability, charge transfer, bonding, and transport, split it further.

## Models and controls

Define the main system and only those controls that yield a direct comparison. Depending on the project, consider isolated components versus complex, before versus after adsorption, adsorption sites, defects, dopants, conformers, spin states, reaction paths, or models corresponding to different experimental conditions.

For direct comparisons, keep all relevant settings consistent: functional, basis set or pseudopotential, dispersion treatment, cell, cutoff, k-point sampling, convergence thresholds, spin treatment, solvation/environment model, and post-processing definition. For difference quantities, explicitly verify consistent reference states and energy or density definitions.

Reject controls that cannot produce a clear comparative conclusion. State what each retained control isolates and which confounder it addresses.

## Evidence-chain construction

Assign different evidence roles to different observables. A compact chain may combine:

- reliability evidence: optimization, frequency or stability checks, convergence tests, equilibration diagnostics;
- structural evidence: distances, angles, coordination, distortions, or conformational populations;
- energetic evidence: binding, adsorption, formation, reaction, activation, or free energies;
- charge evidence: spatial redistribution plus one suitable quantitative population analysis;
- electronic or orbital evidence: DOS/PDOS, band edges where appropriate, orbital composition, or occupations;
- bonding evidence: one method that answers a defined atom-pair or interaction question;
- kinetic/dynamic evidence: transition states, minimum-energy paths, sampling, or free-energy profiles;
- experimental correspondence: a stated qualitative, semi-quantitative, or quantitative comparison.

For one scientific question, prefer one core observable and one necessary validation observable. Add more only when interpretation is non-unique, method-dependent, or otherwise insufficient.

## Task design

Describe every proposed calculation using this complete logic:

> Use **[software] [module/function]** on **[specific system/control]** to perform **[calculation]**, obtaining **[parameter/data/plot]** that characterizes **[physical or chemical property]**; cross-check it against **[another calculation or experiment]** to support **[specific conclusion]**.

Then state:

- prerequisite and dependency;
- priority: foundation, core, mechanism, or supplemental;
- necessity and unique evidence role;
- viable alternative and why it is secondary;
- estimated cost as low, medium, high, or very high, with the main scaling driver;
- whether representative systems are sufficient;
- effect of cancellation on the core conclusion.

Do not give unsupported fixed parameter values. Give the selection basis, a defensible range or test plan when no unique value is justified, and the acceptance criterion.

## Redundancy and resource review

Audit every task after drafting the plan.

Keep calculations that are genuinely complementary, such as charge-density difference for spatial redistribution and one population scheme for transfer magnitude, or DOS for the global distribution and PDOS for local origin.

Merge or remove calculations when they only repeat the same conclusion by different methods. Typical warning cases include:

- several population schemes used only to show the same charge-transfer direction;
- DOS, PDOS, and band structure all used only to claim a changed band gap;
- COHP, QTAIM, ELF, and bond order all used vaguely to claim “bond formation”;
- adsorption, binding, and formation energies with equivalent reference definitions used only to claim greater stability.

Mark each item as retain, merge, conditional, or delete. Explain whether removal changes the central conclusion.

Use low-cost calculations for model, configuration, composition, or pathway screening. Reserve high-accuracy charge, orbital, bonding, transition-state, or free-energy work for representative systems selected by earlier results. Do not mechanically run every high-cost analysis on every structure.

## Decision gates

Define explicit entry and stop conditions:

- Start electronic-structure or bonding analysis only after optimization succeeds, the model remains chemically reasonable, and required convergence or stability checks pass.
- Start high-accuracy interfacial analysis only after candidate configurations are screened and representative stable structures are selected.
- Start transition-state or kinetic work only when the candidate chemistry and preliminary path are plausible and endpoint definitions are sound.
- Start production-trajectory analysis only after minimization and equilibration give reasonable temperature, pressure, energy, and structural behavior.
- Stop expensive downstream work when early results reject the hypothesis, reveal an invalid model, fail essential convergence, or make the planned observable unable to answer the question.

When stopping, state whether to revise the model, reformulate the scientific question, change the method, or obtain missing validation data.

## Review and approval handoff

After the scientific plan passes the stage-1 quality check, serialize it according to `stage-1-plan-schema.md` and follow `stage-1-review-and-approval.md`. Generate the immutable initial version and browser review artifacts with `scripts/stage1_review.py`.

Do not treat the initial plan or initial browser display as stage completion. Remain in stage 1 while the status is `WAITING_FOR_USER_APPROVAL`, `USER_EDITED_PENDING_ANALYSIS`, `IMPACT_ANALYSIS_READY`, or `WAITING_FOR_FINAL_APPROVAL`.

## Stage boundary

Conclude the scientific plan with a dependency-ordered execution route, but do not create production inputs, run software, submit jobs, extract results, or perform post-processing.

Mark stage 1 complete only after the user explicitly confirms the final candidate, the approved baseline files exist, and `stage1_status.json` reports `APPROVED`. Do not automatically start stage 2.
