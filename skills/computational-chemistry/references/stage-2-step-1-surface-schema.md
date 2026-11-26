# Stage 2 Step 1 Surface-Design Data Contract

## Contents

1. Directory contract
2. Input summary
3. Design object
4. Bulk reference
5. Surface-model record
6. Weight records
7. Structure provenance
8. Protected and forbidden data

## Directory contract

Use only this stage-specific namespace:

```text
surface_design/
├── bulk_reference/
├── candidate_surfaces/
├── screened_surfaces/
├── rejected_surfaces/
├── scripts/
├── previews/
├── user_input_summary.json
├── user_surface_proposal.md
├── experimental_constraints.md
├── surface_design_v001.json
├── surface_matrix_v001.csv
├── surface_screening_report_v001.md
├── surface_change_log.json
├── surface_impact_analysis.md
├── surface_review.html
└── surface_status.json
```

Create later `vNNN` JSON/CSV/Markdown files without modifying earlier versions. Never write surface artifacts into `planning/`, and never modify any stage-1 approved file.

## Input summary

Require `user_input_summary.json` to record:

- `user_has_surface_proposal` and `user_has_experimental_constraints`;
- `explicitly_no_input` when the user confirms neither is available;
- the user response without invented details;
- files actually read, their types, paths, and checksums;
- extracted structural/experimental facts and uncertainties;
- proposal review categories: retain, adjust, convergence-test, not recommended;
- conflicts between proposal, experiment, structure, and stage-1 goals;
- `validation_status`: `validated`, `not_available`, or `conflict_requires_confirmation`.

Do not mark an absent reply as `not_available`; require an explicit user statement.

## Design object

Require top-level fields:

| Field | Meaning |
| --- | --- |
| `project_id` | Stable identifier matching stage 1 |
| `workflow_step` | `stage2_step1_surface_design` |
| `stage1_link` | Approved version, plan checksum, approval checksum, and goal snapshot |
| `input_summary_ref` | Path/checksum of `user_input_summary.json` |
| `bulk_reference` | Validated bulk metadata and copied-source provenance |
| `experimental_constraints` | Evidence, interpretation, confidence, conflicts, and model implications |
| `design_assumptions` | Explicit theoretical assumptions and confirmation conditions |
| `models` | Structured candidate surface records |
| `comparison_groups` | Core/control/functional relations and fair-comparison settings |
| `duplicate_review` | Equivalent-model matches, retained representative, and reason |
| `screening_summary` | Method, label, criteria, retained/rejected models, and limitations |
| `weight_settings` | Transparent component coefficients for relative model weights |
| `known_risks` | Scientific, structural, experimental, software, or dependency risks |
| `workflow_checks` | Required completion booleans and evidence |

The version tool adds `design_version`, `generated_at`, and `version_record`. JSON is the formal data source; CSV is the comparison matrix; Markdown is the human-readable screening report.

## Bulk reference

Require:

- `source_type`, `source_path`, `source_copy`, and `sha256`;
- `composition`, `space_group`, and `lattice_parameters`;
- `partial_occupancy`, `disorder`, `missing_atoms`, and how each was handled;
- `oxidation_state_assessment`, `spin_assessment`, and `periodicity`;
- `optimized`, `optimization_reference`, and transformations;
- `validation_status` and concrete validation notes.

Require `validation_status: validated` before candidate design approval. Keep the copied source in `bulk_reference/`; do not overwrite the user's original.

## Surface-model record

Give each model a stable ID and all fields below. Use explicit `not_applicable` values rather than omitting context-sensitive fields.

| Field | Meaning |
| --- | --- |
| `id`, `name`, `material` | Stable identity and traceable name |
| `miller_index` | Three- or four-index facet representation as appropriate |
| `termination` | Atomic-layer termination and rationale |
| `stoichiometry` | Surface composition and deviation from bulk |
| `polarity` | Nonpolar/polar/unknown plus basis |
| `dipole_handling` | Symmetry, reconstruction, compensation, correction, or not applicable |
| `slab_layers`, `slab_thickness` | Layer count and geometric thickness with selection basis |
| `thickness_test` | Candidate values, observables, acceptance criterion, and status |
| `vacuum` | Candidate size, basis, convergence observable, and status |
| `in_plane_supercell` | Transformation/replication, area, and selection basis |
| `fixed_layers`, `relaxed_layers` | Constraint definition and rationale |
| `defect` | Type, site, concentration, charge, spin, coordination, or not applicable |
| `doping` | Element, substituted site, concentration, charge/spin implications, or not applicable |
| `functionalization` | Species, site, coverage definition, environment basis, or not applicable |
| `spin_setting` | Polarization, initial moments/order, alternatives, and rationale |
| `target_sites` | Chemically distinct later adsorption/interface sites |
| `experimental_support` | Technique, observation, support strength, and uncertainty |
| `evidence_function` | Stable reference, experimental core, functional model, defect control, etc. |
| `comparison_group` | Models and settings required for direct comparison |
| `downstream_uses` | Approved later tasks this model enables |
| `classification` | `core`, `stability_control`, `functional`, `screening`, or `rejected` |
| `retention_reason`, `rejection_reason` | Explicit model decision |
| `structure_files` | Relative paths and checksums for generated structures |
| `preview_file` | Optional relative PNG/SVG preview under `previews/` |
| `generation_record` | Script, input, parameters, versions, manual edits, and regeneration status |
| `reasonability_checks` | Overlap, short bond, coordination, charge, stoichiometry, polarity, images, vacuum, center, constraints, spin |
| `screening` | Not required/pending/passed/rejected, method, settings label, result use, and limitations |
| `scientific_weight`, `workload_weight` | Component scores, rationales, and derived values |
| `status`, `user_notes` | Current disposition and user comments |

Every non-rejected retained model must name a generated structure file and a reproducible generation record before approval. A design-only placeholder may exist while editing but blocks `SURFACE_DESIGN_APPROVED`.

## Weight records

Score each component from 0 to 100 and explain it separately. Use configurable coefficients stored in `weight_settings`.

Scientific components:

- `E`: experimental support;
- `R`: relevance of exposed target sites;
- `U`: independent evidence contribution;
- `S`: sensitivity of final interpretation to this model;
- `N`: irreplaceability.

Default to equal coefficients only when no project policy justifies another weighting. Record any override and its reason.

Workload components:

- `A`: atom/model size;
- `C`: in-plane cell complexity;
- `K`: configurations/terminations to handle;
- `D`: defect/doping/functionalization complexity;
- `S`: spin-state count/complexity;
- `H`: planned downstream analysis burden.

Default to equal coefficients only for neutral relative comparison. Do not convert workload values to runtime, memory, storage, or hardware requirements. Never delete a high-scientific-weight model automatically.

## Structure provenance

For each structure file, record:

- relative output path and SHA-256;
- bulk source checksum;
- generator script path and checksum;
- structure-library name/version;
- Miller index, termination selector, slab/vacuum/cell settings, constraints, defect/dopant/functionalization/spin inputs;
- all manual edits with affected atoms and reasons;
- generation timestamp and whether regeneration reproduced the checksum.

Use a reliable structure matcher to assess duplicates when available. Record matcher, tolerances, and mapping. Never claim symmetry equivalence based only on filenames or formula.

## Protected and forbidden data

Treat `project_id`, `stage1_link`, and `input_summary_ref` as immutable in the surface editor. Return to the owning stage or input-review flow to change them. Protect bulk source/checksum, original user files, detected software versions, historical versions, change history, and generated structure checksums. Require a recorded manual-override path and reason only for legitimate bulk/source metadata corrections, then regenerate every dependent surface. Never rewrite the external original file.

Reject fields that claim exact runtime, memory, storage, or hardware consumption without measured evidence. Reject any status implying formal adsorption, electronic-structure, bonding, reaction, or production-MD results in this step.

Require these checks before approval:

```json
{
  "stage1_gate_passed": true,
  "mandatory_user_question_answered": true,
  "bulk_validated": true,
  "candidates_generated": true,
  "reasonability_checked": true,
  "duplicates_resolved": true,
  "screening_completed_or_not_required": true,
  "browser_review_generated": true
}
```
