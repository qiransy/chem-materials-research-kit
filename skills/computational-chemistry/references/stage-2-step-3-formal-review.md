# Stage 2 Step 3 Review, Versioning, and API

## Contents

1. Review lifecycle
2. Browser fields
3. Allowed edits and impact
4. Approval and restore behavior
5. Result review behavior
6. CLI and local API

## Review lifecycle

Use `scripts/formal_review.py` as the deterministic state/version gate. The model supplies scientifically reviewed JSON and file contents; the engine verifies frozen inputs, task IDs, dependencies, safe paths, required roles, comparability assertions, immutable versions, and exact transitions. It never executes generated commands.

Lifecycle:

```text
start
→ select-batch
→ submit (materialize candidate vNNN and static checks)
→ serve (browser review)
→ submit revisions / restore-as-new / reject / continue
→ approve
→ external user calculation
→ ingest-results
→ analyze-results
→ select/submit next batch or regenerate
```

`start` writes the task graph and `WAITING_FOR_FORMAL_TASK_SELECTION` only. `select-batch` records a user-confirmed minimum prerequisite-ready batch but does not generate files. `submit` creates a new immutable version and enters `WAITING_FOR_FORMAL_FILE_APPROVAL` only after validation.

## Browser fields

The browser page shows:

- frozen approvals and accepted optimization structure;
- task graph and current prerequisite-ready nodes;
- current batch purpose and evidence role;
- software, module, method, systems, controls, and target data;
- reference definitions and comparability requirements;
- selected PDOS atoms/orbitals or COHP pairs;
- all generated input/postprocess/reference/dependency files;
- HPC/local scripts as user instructions only;
- static-validation categories, pending fields, reconfirmations, risks, versions, and impact;
- result state and latest exact conclusion when returned data exists.

Never show predicted runtime, memory, or storage. Label every command as external user instruction.

## Allowed edits and impact

Allow task inclusion only for retained prerequisite-ready tasks or approved supplemental tasks whose activation condition is met. Preserve necessary/core tasks unless the user returns to stage 1. Allow priority, reference names, projection atoms/orbitals/pairs, post-processing output/window, user-provided scheduler values, placeholders, and safe directories.

High-impact edits include structure/lattice, functional, pseudopotential/basis, dispersion, Hubbard U, spin method, charge, primary boundary, or mathematical reference definition. High-impact conflicts with approved baselines block approval and identify the owning stage. Medium-impact edits include k-point/grid/cutoff/numerical electronic settings and analysis scope. Script-resource edits are normally low-impact but remain statically checked.

Reject protected-field edits, deleted task restoration, unapproved new tasks, manually claimed completion, execution flags, estimates, or path traversal.

## Approval and restore behavior

- `approve`: require explicit user confirmation, no errors/reconfirmation, and freeze a batch-specific approved copy plus root approved aliases.
- `continue`: keep the current version editable.
- `reselect`: abandon only the current unapproved candidate pointer, restore task readiness, and return to batch selection while retaining every generated version.
- `restore`: copy a historical candidate into a new version; never make the old directory writable.
- `reject`: move the current pointer to the previous valid candidate without deleting any file.

Approval records that files are delivered and unexecuted. Immediately return the formal handoff prompt and wait state.

## Result review behavior

Ingest returned data into a new result version before interpretation. The browser may display the latest result manifest and analysis but cannot modify raw uploads or engine-owned decision fields. Analysis must cite immutable result records and choose one exact decision from the schema.

For regeneration decisions, a new candidate version may reuse valid accepted structure, methods, and unaffected files, but must record before/after changes. For reference failure, regenerate the entire related reference set. For upstream model failures, record a return route and stop; do not mutate upstream status files.

## CLI and local API

CLI commands:

```text
formal_review.py start
formal_review.py select-batch
formal_review.py submit
formal_review.py action
formal_review.py ingest-results
formal_review.py analyze-results
formal_review.py serve
formal_review.py status
formal_review.py environment
```

Browser API:

```text
GET  /api/state
GET  /files/<safe-relative-path>
POST /api/select-batch
POST /api/submit
POST /api/action
```

Bind to localhost by default. API requests are limited in size and use safe relative paths. The service is only a review interface; it does not wait for or retrieve external results.
