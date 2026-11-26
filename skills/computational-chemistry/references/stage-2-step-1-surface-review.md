# Stage 2 Step 1 Surface Review and Approval

## Contents

1. State machine
2. Input capture
3. Initial design generation
4. Browser review
5. Versioning and impact analysis
6. User decisions
7. Approval baseline
8. Failure and stage boundary

## State machine

Use only the isolated surface states:

```text
WAITING_FOR_SURFACE_INPUT
├─ proposal/experiment supplied → SURFACE_INPUT_RECEIVED
│    └─ review passes → SURFACE_INPUT_VALIDATED
└─ user explicitly has neither → SURFACE_INPUT_NOT_AVAILABLE

SURFACE_INPUT_VALIDATED or SURFACE_INPUT_NOT_AVAILABLE
└─ candidates recorded → SURFACE_CANDIDATES_GENERATED
     └─ reasonability checks pass → SURFACE_MODELS_VALIDATED
          └─ screening/duplicate review completes → SURFACE_MODELS_SCREENED
               └─ browser generated → WAITING_FOR_SURFACE_REVIEW
                    ├─ user edit → SURFACE_USER_EDITED
                    │    └─ impact analysis → WAITING_FOR_SURFACE_APPROVAL
                    ├─ explicit acceptance → SURFACE_DESIGN_APPROVED
                    ├─ continue → WAITING_FOR_SURFACE_REVIEW
                    ├─ restore → new version → WAITING_FOR_SURFACE_APPROVAL
                    └─ reject edit → previous valid candidate → WAITING_FOR_SURFACE_REVIEW
```

Do not skip the input states. Do not interpret browser generation as approval.

## Input capture

Start only after the skill has asked the mandatory question:

```text
python <skill>/scripts/surface_review.py start \
  --stage1-planning-dir <project>/planning \
  --surface-dir <project>/surface_design
```

After reading the user's reply and files, create an input-summary JSON following `stage-2-step-1-surface-schema.md`, then run:

```text
python <skill>/scripts/surface_review.py input \
  --surface-dir <project>/surface_design \
  --summary <input-summary.json>
```

The command generates `user_input_summary.json`, `user_surface_proposal.md`, and `experimental_constraints.md`. It sets `SURFACE_INPUT_VALIDATED`, `SURFACE_INPUT_NOT_AVAILABLE`, or remains at `SURFACE_INPUT_RECEIVED` when conflicts require confirmation.

Do not treat silence or missing files as explicit absence.

## Initial design generation

After input validation/unavailability and after real candidate structures/check records exist, create a design JSON following the schema and run:

```text
python <skill>/scripts/surface_review.py init-design \
  --surface-dir <project>/surface_design \
  --design <surface-design-source.json>
```

Generate immutable `surface_design_v001.json`, `surface_matrix_v001.csv`, and `surface_screening_report_v001.md`. Record each state transition through candidates generated, models validated, models screened, and browser review.

The command must fail rather than approve placeholders when required structure files, bulk validation, reasonability checks, duplicate resolution, or screening decisions are missing.

## Browser review

Run:

```text
python <skill>/scripts/surface_review.py serve --surface-dir <project>/surface_design --open
```

Prefer the in-app/current browser. If automatic opening fails, keep the local service running and give the printed loopback address.

Display:

- stage-1 approved goal and target evidence;
- user proposal and experimental constraints;
- bulk-reference validation;
- side-by-side candidate model matrix;
- facet, termination, thickness, vacuum, cell, constraints, defects, doping, functionalization, spin, sites, previews, reasons, and downstream uses;
- scientific/workload weights;
- version history, changes, evidence/downstream impacts, and risks.

Permit editing through structured JSON, adding models, excluding/restoring models, and changing all user-authorized surface fields. Do not permit historical-file overwrite.

## Versioning and impact analysis

For every submitted edit:

1. set `SURFACE_USER_EDITED`;
2. create the next immutable JSON/CSV/Markdown version;
3. compare the previous candidate by stable model ID;
4. validate bulk/model references, protected values, structures, duplicates, checks, and weights;
5. analyze experimental relevance, stability comparison, exposed sites, later adsorption-site design, adsorption-energy comparability, charge/electronic/bonding analyses, and final interpretation;
6. write a version-specific impact report and update `surface_impact_analysis.md`;
7. set `WAITING_FOR_SURFACE_APPROVAL`.

Use concrete rules:

- deleting the primary experimental facet lowers experiment-model consistency;
- deleting a stability-control surface removes the test of whether a functional surface is merely a high-energy special case;
- shrinking an in-plane cell increases image interaction, defect concentration, and coverage;
- reducing slab layers may prevent a bulk-like center;
- reducing vacuum may introduce artificial slab/slab or adsorbate interactions;
- changing termination can fundamentally change coordination, charge, polarity, sites, and electronic structure;
- adding defects, doping, or functionalization is valuable only when it adds independent evidence aligned with the approved goal.

Assign `LOW`, `MEDIUM`, `HIGH`, or `CRITICAL` with a reason. Do not emit only a label. Keep scientific and workload weights separate; never convert workload to time or hardware estimates.

## User decisions

Offer:

- 接受当前表面方案
- 继续修改
- 恢复上一版本
- 拒绝当前修改

Continuing keeps history and reopens editing. Restoring creates a new version copied from the selected historical version. Rejecting retains the rejected version and returns the previous valid candidate. Acceptance requires explicit confirmation and generates the approved baseline; it never launches later computations.

## Approval baseline

From `WAITING_FOR_SURFACE_REVIEW` or `WAITING_FOR_SURFACE_APPROVAL`, run `surface_review.py review`; only its matching confirmed browser `approved` decision may validate all completion checks and generate, without overwriting an existing baseline:

```text
surface_design_approved.json
surface_design_approved.csv
surface_design_approved.md
surface_approval_record.json
```

Record final version, bulk source, core facets, terminations, layers, vacuum, cells, constraints, defects, doping, functionalization, spin, retained/rejected models, experimental basis, assumptions, risks, structure/generator checksums, user confirmation, and approval time.

Set `SURFACE_DESIGN_APPROVED` only after every baseline file exists. The next surface optimization, adsorption, interface, or other step may read this baseline, but only after a separate explicit user request.

## Failure and stage boundary

- If stage 1 is not approved or its checksum fails, do not create the surface state store.
- If the user has not answered the mandatory question, remain `WAITING_FOR_SURFACE_INPUT`.
- If proposal and experiments conflict, remain before candidate generation until the user resolves or authorizes an explicit hypothesis branch.
- If structure libraries are unavailable, do not invent candidate files; keep the design unapproved and report the dependency gap.
- If model files fail reasonability/provenance checks, correct or reject them before browser approval.
- Never overwrite original bulk structures, historical versions, or an approved surface baseline.
- Never start formal adsorption, interface binding, electronic structure, charge, bonding, reaction, or production-MD work in this step.
