# Stage 1 Structured Plan Contract

## Contents

1. Data-source rules
2. Top-level object
3. Task object
4. Weight objects
5. Evidence-chain object
6. Protected values
7. Prohibited estimates
8. Minimal skeleton

## Data-source rules

Use `planning/stage1_plan_vNNN.json` as the formal source for review and later stages. Treat Markdown as a readable rendering and HTML as an interaction surface. Never reconstruct formal state from browser DOM or Markdown when the JSON exists.

Keep every numbered JSON plan immutable. Create a new sequential version for every submitted edit or restoration. Store version metadata inside `version_record` and retain the corresponding change-log event.

## Top-level object

Require these top-level fields:

| Field | Type | Meaning |
| --- | --- | --- |
| `project_id` | string | Stable project identifier; protected after initialization |
| `stage` | integer | Always `1` |
| `research_goal` | object | Research object, comparison, phenomenon, core question, and target conclusion |
| `scientific_questions` | array | Independent subquestions with IDs, evidence targets, and dependencies |
| `systems` | array | Main models with IDs, names, roles, and descriptions |
| `controls` | array | Controls with IDs, isolated variables, and consistency requirements |
| `evidence_chain` | array | Evidence nodes, supported conclusions, and task IDs |
| `tasks` | array | Full computation-task records |
| `redundancy_review` | object or array | Retain/merge/conditional/delete decisions and reasons |
| `execution_route` | array or object | Dependency-ordered stage-1 execution logic |
| `assumptions` | array | Provisional assumptions and confirmation conditions |
| `risks` | array | Scientific, technical, compatibility, or resource risks |
| `weight_settings` | object | Include non-negative `lambda`; use only for relative priority ranking |
| `protected_records` | object | Detected software versions, source-data references, and checksums when present |
| `change_intents` | optional array | Explicit merge, split, or replacement relations for the next submitted edit |

The version tool adds `plan_version`, `generated_at`, and `version_record`. Do not rely on user-edited values for those fields.

Use these `research_goal` fields:

- `research_object`
- `comparison_object`
- `experimental_phenomenon`
- `core_question`
- `target_conclusion`

Give every item in `scientific_questions`, `systems`, `controls`, and `evidence_chain` a stable unique `id`.

When a user merges, splits, or replaces tasks, optionally encode the semantic relationship so the diff does not need to infer intent:

```json
"change_intents": [
  {
    "type": "merged",
    "source_task_ids": ["T04", "T05"],
    "target_task_ids": ["T04"],
    "reason": "Both tasks produced the same evidence; retain one method"
  }
]
```

## Task object

Require every task to contain all fields below. Use an empty list, empty string, or a justified `not_applicable` value instead of omitting a field.

| Field | Meaning |
| --- | --- |
| `id` | Stable task identifier |
| `name` | Concise task name |
| `scientific_question_id` | Scientific subquestion answered |
| `systems` / `controls` | Referenced model and control IDs |
| `software` / `module` / `method` | Implementation choice; do not invent capabilities |
| `target_parameters` | Observables or quantities to obtain |
| `target_data_forms` | Numeric table, structure, curve, density grid, image, trajectory, or other output form |
| `scientific_meaning` | Property represented by the output |
| `supported_conclusions` | Exact conclusions supported or refuted |
| `experimental_correspondence` | Experimental links and qualitative/semi-quantitative/quantitative strength |
| `corroborates_with` | Other task or experiment IDs that provide complementary evidence |
| `prerequisites` / `downstream_dependencies` | Task IDs defining an acyclic dependency graph |
| `evidence_role` | Reliability, structure, thermodynamics, charge-spatial, charge-quantitative, orbital, bonding, kinetics, dynamics, experiment, or a project-specific role |
| `scientific_weight` | Component scores, rationales, and derived value |
| `workload_weight` | Component scores, rationales, and derived value |
| `result_sensitivity` | How strongly the final conclusion depends on this result |
| `irreplaceability` | Whether another calculation or experiment can substitute for it |
| `priority` | Foundation, core, mechanism, or supplemental execution priority |
| `necessity` | Necessary, conditional, optional, merge, or delete decision with reason |
| `alternatives` | Executable alternatives and tradeoffs |
| `redundancy` | Complementary or duplicate judgment |
| `status` | Proposed, conditional, retained, deleted, or another explicit planning state |
| `user_notes` | User-entered comments |

## Weight objects

Represent scientific weight as:

```json
{
  "I": 0,
  "U": 0,
  "S": 0,
  "N": 0,
  "rationale": {
    "I": "importance to the core conclusion",
    "U": "independence of the evidence",
    "S": "conclusion sensitivity to the result",
    "N": "difficulty of replacement"
  }
}
```

Score each component from 0 to 100. Let the review tool calculate:

`W_sci = 0.35 I + 0.25 U + 0.20 S + 0.20 N`

Represent workload weight as:

```json
{
  "M": 0,
  "C": 0,
  "K": 0,
  "P": 0,
  "H": 0,
  "rationale": {
    "M": "model scale",
    "C": "method complexity",
    "K": "configuration/control count",
    "P": "workflow and parameter-test count",
    "H": "post-processing and interpretation difficulty"
  }
}
```

Let the review tool calculate:

`W_work = 0.25 M + 0.25 C + 0.20 K + 0.15 P + 0.15 H`

Let it calculate `P = W_sci / (1 + lambda W_work)` only as an ordering aid. Never use the index to remove a scientifically necessary task automatically.

## Evidence-chain object

Use at least:

```json
{
  "id": "E01",
  "role": "thermodynamic evidence",
  "task_ids": ["T02"],
  "supports": "the exact conclusion supported",
  "required": true
}
```

Choose evidence roles from the actual research goal. Do not require every project to contain structural, energetic, charge, orbital, bonding, dynamic, and experimental layers. Mark `required: true` only when losing every referenced task would remove a necessary evidence node.

## Protected values

Protect `project_id` and `protected_records`. Put detected software versions, original-output references, experimental-source references, and checksums in `protected_records` when available.

To change a protected value, include:

```json
"manual_overrides": [
  {
    "path": "protected_records.detected_software",
    "reason": "User supplied a corrected environment record",
    "manual_override": true
  }
]
```

Do not modify or delete historical plan files, historical change entries, raw computation outputs, raw experimental data, or checksum records through the review page.

## Prohibited estimates

Do not add fields such as `estimated_runtime`, `runtime_hours`, `estimated_memory`, `memory_gb`, `estimated_storage`, or `storage_gb`. Workload weights express only relative complexity inside the current plan.

## Minimal skeleton

```json
{
  "project_id": "project-stable-id",
  "stage": 1,
  "research_goal": {
    "research_object": "",
    "comparison_object": "",
    "experimental_phenomenon": "",
    "core_question": "",
    "target_conclusion": ""
  },
  "scientific_questions": [],
  "systems": [],
  "controls": [],
  "evidence_chain": [],
  "tasks": [],
  "redundancy_review": {},
  "execution_route": [],
  "assumptions": [],
  "risks": [],
  "weight_settings": {"lambda": 0.01},
  "protected_records": {}
}
```

Treat `lambda: 0.01` as a transparent default for displaying a bounded relative ranking, not a scientific or hardware constant. Replace it when the project defines another workload constraint policy.
