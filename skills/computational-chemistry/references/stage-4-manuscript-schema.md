# Stage 4 Manuscript and Reproduction Data Contract

## Contents

1. Directory and states
2. Frozen upstream gate
3. Actual source inventory
4. License and citation review
5. Manuscript candidate
6. Conclusion claim and strength contract
7. Actual method contract
8. Open-source mapping contract
9. Version and impact contract
10. Approval and protected values

## Directory and states

Write only within:

```text
manuscript_generation/
├── source_records/
├── method_drafts/
├── result_discussion/
├── conclusions/
├── software_citations/
├── license_review/
├── open_source_migration/
├── user_edits/
├── source_snapshots/
├── manuscript_review.html
├── manuscript_plan_vNNN.json
├── method_statement_vNNN.md
├── result_discussion_vNNN.md
├── conclusion_vNNN.md
├── open_source_reproduction_note_vNNN.md
├── manuscript_impact_analysis_vNNN.json
├── manuscript_status.json
└── manuscript_change_log.json
```

Permit only:

```text
WAITING_FOR_MANUSCRIPT_INPUT
SOURCE_RECORDS_VALIDATED
SOFTWARE_LICENSE_REVIEWED
CONCLUSION_DRAFT_GENERATED
METHOD_STATEMENT_GENERATED
OPEN_SOURCE_MAPPING_GENERATED
WAITING_FOR_MANUSCRIPT_REVIEW
USER_MANUSCRIPT_EDITED
MANUSCRIPT_IMPACT_ANALYZED
WAITING_FOR_MANUSCRIPT_APPROVAL
MANUSCRIPT_CONTENT_APPROVED
```

Intermediate generation states may be recorded in the log before the current state advances to review. No state implies calculation, post-processing, plotting, or open-source recomputation.

## Frozen upstream gate

`manuscript_status.json.upstream_gate` contains absolute path, SHA-256, and size records for stage-1 approved sources/status; supplied surface/interface approvals; geometry/formal status and graph; stage-3 status; every stage-3 approval/analysis/validation/evidence matrix/dataset source needed by the approved conclusions; and supplied experiment records.

Require stage 1 `APPROVED` and stage 3 `RESULTS_APPROVED` with `overall_stage_complete: true`. Recheck all records before mutation. A legitimate upstream revision requires a separately authorized new stage-4 workflow; do not silently sync an approved manuscript source.

## Actual source inventory

Store immutable versions as `source_records/software_source_inventory_vNNN.json` and copy submitted actual input/output/supporting files into `source_records/inventory_vNNN/`.

Require:

```json
{
  "project_id": "P001",
  "models": [
    {
      "model_id": "M01",
      "model_type": "surface | interface | molecule | bulk | other",
      "approved_record": {"path": "", "sha256": ""},
      "final_structure": {"path": "", "sha256": ""},
      "description": ""
    }
  ],
  "tasks": [
    {
      "task_id": "T01",
      "task_name": "",
      "actual_software": {
        "name": "",
        "version": "",
        "version_status": "confirmed | unconfirmed",
        "module": "",
        "license_category": "open_source | commercial_or_closed | free_non_open | institutional_license | unconfirmed",
        "license_verification_source": ""
      },
      "files": [
        {"path": "", "role": "actual_input | main_output | result_data | postprocess_output | model | other", "description": ""}
      ],
      "software_identification_evidence": [
        {"type": "input_syntax | output_header | version_string | user_statement", "source_file_role": "", "observation": ""}
      ],
      "actual_parameters": {},
      "actual_vs_planned_differences": [],
      "postprocessing_software": [
        {
          "name": "",
          "version": "",
          "version_status": "confirmed | unconfirmed",
          "module": "",
          "license_category": "...",
          "license_verification_source": "",
          "software_identification_evidence": []
        }
      ],
      "stage3_analysis_versions": [],
      "stage3_dataset_ids": []
    }
  ]
}
```

Each task requires at least one actual input and one main/result/post-processing output. Require at least two identification-evidence types and at least one output header, version string, or user statement. Do not infer software from extension alone.

Required actual parameter keys are software, software version, functional, basis, pseudopotential, dispersion, Hubbard U, cutoffs, k points, spin, occupations, total charge, convergence, vacuum, fixed atoms, lattice/cell, and boundary conditions. Use `not_applicable` when justified. `unknown` on a result-relevant field is a final-approval blocker. Plan/actual differences remain explicit.

Every task cited by an approved stage-3 analysis requires a source-inventory task. Unknown version uses the exact missing-version statement; it is a declared publication-pending item and is never guessed.

## License and citation review

Store `license_review/license_review_vNNN.json` and Markdown. Require one item for every actual/main post-processing software:

```json
{
  "software_name": "",
  "actual_task_ids": [],
  "license_category": "...",
  "classification_source": "official URL, license text, or unconfirmed",
  "recommended_software_citations": [],
  "theory_algorithm_citations": [],
  "input_sharing": "allowed | restricted | unconfirmed",
  "restricted_dependencies": [],
  "public_release_action": "",
  "manual_or_web_quotes": [],
  "review_complete": true
}
```

Every citation records title, authors/organization, year, DOI/URL when known, source type, and verification status. Do not fabricate a missing citation. Manual/web quote items contain source and excerpt; reject an excerpt over 25 words. A restricted dependency must record public name/provenance and authorized acquisition route, not copied file content.

## Manuscript candidate

Each `manuscript_plan_vNNN.json` requires:

```json
{
  "project_id": "P001",
  "document_profile": {
    "document_type": "research_article | thesis | report | supporting_information",
    "target_style": "",
    "language": "zh | en | bilingual",
    "method_detail": "full | concise | both",
    "paragraph_order": [],
    "terminology": {},
    "retain_open_source_note": true
  },
  "source_inventory_record": {},
  "license_review_record": {},
  "method_factual_assertions": [],
  "actual_method_software_mentions": [],
  "conclusion_claims": [],
  "method_full": "",
  "method_concise": "",
  "result_discussion": "",
  "overall_conclusion": "",
  "evidence_node_conclusions": [],
  "theory_experiment_correspondence": [],
  "software_citation_text": "",
  "license_review_text": "",
  "open_source_mappings": [],
  "open_source_reproduction_note": "",
  "pending_user_information": [],
  "manual_source_quotes": []
}
```

The engine adds version, timestamps, source hashes, impact, blocking items, and all false execution flags.

## Conclusion claim and strength contract

Every claim requires ID, level (`data | property | mechanism | overall`), source stage-3 conclusion IDs, source evidence item IDs, evidence roles, direct data basis, physical meaning, cross-evidence relation, experimental relation (`direct | interpretive | none`), boundary, source strength, draft strength, and text.

Order strengths as:

```text
INCONCLUSIVE < PARTIALLY_SUPPORTED < SUPPORTED < STRONGLY_SUPPORTED
```

`CONTRADICTED` is not an intensity value; it must remain contradicted unless a new approved stage-3 analysis replaces it. Draft strength may equal or be lower than the source ceiling, never higher. Partial/inconclusive wording must remain cautious. A mechanism claim requires at least two independent evidence roles and supporting source strengths; otherwise it is partial/inconclusive. Preserve conclusion boundaries.

## Actual method contract

Each `method_factual_assertions` item binds a task ID to source-inventory software name/version/module, model IDs, actual-parameter subset, formulas actually used, and file IDs. The values must exactly match the source inventory.

`method_full` and `method_concise` must name actual software. Structured `actual_method_software_mentions` must contain only software actually used for the cited task. Alternative software names are prohibited in the actual-method section unless they are separately recorded as actual tools.

Formulas require formula ID, task/evidence IDs, expression, term definitions, reference-system structure state, cell/strain/grid/sign convention, and confirmation that the formula was used in the approved stage-3 analysis.

## Open-source mapping contract

Require a mapping for every task whose actual software license is not `open_source`. A mapping contains actual task/software, proposed alternatives, task-capability checks, parameter mappings, non-equivalent items, suggested template, references, and limitations.

Each parameter mapping classifies equivalence as `direct`, `approximate`, or `not_transferable`. A proposed alternative cannot appear in actual-method software mentions unless it was also actually used and independently sourced.

The reproduction note must contain exactly:

```text
该开源方案用于提供等效复现路径，尚未用于重新生成本文结果。由于不同程序的数值实现、赝势或基组体系存在差异，复现时可能获得存在合理数值偏差的结果。
```

Set `open_source_recalculation_performed: false` and `existing_results_attributed_to_alternative: false`.

## Version and impact contract

Never overwrite `vNNN`. Compare a submitted/restored candidate against the prior version by JSON path and write `manuscript_impact_analysis_vNNN.json`/Markdown.

Protect source inventory and license-review records, project/task/evidence/conclusion IDs, source strengths, factual software/parameter/formula provenance, stage-3 analysis references, hashes, timestamps, and execution flags.

Classify critical/high/medium/low as defined in the workflow. Any critical conflict, raised conclusion strength, removed required boundary, false actual-software mention, or open-source-as-actual attribution blocks materialization/approval. Style/detail/order changes are allowed and versioned.

## Approval and protected values

Run `manuscript_review.py review` only for the current validated version from `WAITING_FOR_MANUSCRIPT_APPROVAL` with no blockers. Create the seven required approved files and an approval manifest linking every source and draft checksum only after a matching confirmed browser `approved` decision.

Store as false in state, candidates, mappings, and approvals:

```text
calculation_executed_by_skill
postprocessing_executed_by_skill
job_submitted_by_skill
queue_queried_by_skill
remote_result_retrieval
background_monitoring
research_figures_generated_by_skill
open_source_recalculation_performed
existing_results_attributed_to_alternative
```

Reject path traversal, overwritten versions, invented source facts, unapproved conclusion IDs, strength escalation, formulas not used in approved analysis, restricted-file packaging, long copied manual text, or changes to stages 1–3.
