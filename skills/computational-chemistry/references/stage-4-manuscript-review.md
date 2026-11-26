# Stage 4 Browser Review and Edit Rules

## Contents

1. Review purpose
2. Required views
3. Editable values
4. Protected values and rejected edits
5. Impact and history
6. Approval interaction
7. Browser security

## Review purpose

Use `manuscript_generation/manuscript_review.html` to review and version manuscript content. JSON files remain authoritative. The page never calculates, post-processes, plots, searches licenses without an explicit workflow action, or treats open-source mapping as completed reproduction.

## Required views

Display separate views for:

- frozen upstream approvals and stage-3 conclusion sources;
- actual task/software/version/module/input/output/parameter records;
- plan-versus-actual parameter differences;
- full and concise actual computational methods;
- data/property/mechanism/overall conclusions with inherited strengths;
- results/discussion and evidence-node paragraphs;
- direct versus interpretive theory–experiment mappings;
- software/method citation list;
- license/restricted-dependency/file-sharing review;
- open-source reproduction mapping and non-equivalence limits;
- pending user information, impact, version history, and approval gate.

Use visually distinct panels headed `真实计算方法与来源` and `开源软件复现建议`. Never merge their paragraphs.

## Editable values

Allow edits to:

- document type and target style;
- language and method detail;
- terminology and paragraph order;
- prose length and organization;
- conclusion wording and draft strength at or below the source ceiling;
- direct/interpretive labels when supported by the approved analysis;
- optional open-source alternatives/parameter mappings;
- whether the separate open-source note is retained when no non-open actual task requires it.

Every save creates a new immutable version and impact analysis. Do not edit upstream files through this page.

## Protected values and rejected edits

Do not allow ordinary edits to change project/task/evidence/conclusion IDs, source hashes, actual software/version/module, actual parameters, source strength, model/input/output provenance, formula/reference definitions, execution flags, or approval history.

Reject an edit that:

- replaces actual software A with unexecuted software B;
- describes mapped parameters/results as already recalculated;
- raises a stage-3 conclusion strength;
- removes a limitation required by the source analysis;
- upgrades an interpretive experimental link into a direct causal proof;
- adds a formula not used by an approved result;
- embeds a restricted dependency or long manual/help quotation.

Explain the conflict and preserve the current valid version.

## Impact and history

Show every changed JSON path, old/new summary, impact level, scientific effect, and required action. Highlight critical/high items. Restoration creates a new version rather than overwriting history.

Show source inventory, license review, candidate, impact, and approval checksums. Never infer state from the DOM.

## Approval interaction

From `WAITING_FOR_MANUSCRIPT_REVIEW`, let the user continue editing or mark the current version ready for approval. From `WAITING_FOR_MANUSCRIPT_APPROVAL`, let the user explicitly approve, return to editing, or restore a prior version as a new candidate.

Approval generates only the required immutable manuscript files and sets `MANUSCRIPT_CONTENT_APPROVED`. It does not submit a paper, upload a repository, distribute restricted files, or claim open-source recomputation.

## Browser security

Bind to `127.0.0.1` by default. Restrict file serving to safe paths inside `manuscript_generation/`. Limit JSON request sizes, encode output safely, and invoke the same source/hash/factual/strength validations as the CLI for every browser mutation.
