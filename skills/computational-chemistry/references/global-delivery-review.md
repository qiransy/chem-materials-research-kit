# Stage 5 Delivery and Archive Review

## Contents

1. Entry gate
2. Delivery categories
3. Explicit file intake
4. Validation sequence
5. Missing-item severity
6. Required reports
7. Cleanup policy
8. User review and archive
9. Reopening

## Entry gate

Require all of:

- stage 3 local state `RESULTS_APPROVED` with approved conclusion records;
- stage 4 local state `MANUSCRIPT_CONTENT_APPROVED`;
- the six approved manuscript Markdown files and manuscript approval record;
- actual-method provenance for every result used in approved prose;
- no approved conclusion marked `TRACEABILITY_INCOMPLETE`;
- a separation between actual computation and any open-source reproduction suggestion.

If the user requests delivery early, run a read-only readiness check and list the nearest missing items. Do not fabricate empty approvals to open stage 5.

## Delivery categories

Use exactly these category directories:

```text
01_planning
02_models
03_calculation_inputs
04_hpc_scripts
05_user_results
06_processed_data
07_analysis
08_manuscript
09_open_source_reproduction
10_provenance
```

Treat `09_open_source_reproduction` as prospective unless actual results prove otherwise. Never place the existing actual-method record only in that directory.

## Explicit file intake

Use `delivery-add` for each file or a reviewed explicit list. Record source path, destination path, category, stage, task, model/parameter/result versions, original/approved flags, provenance source, license/share status, SHA-256, and notes.

Copy the file; never move or delete its source. Refuse destination collisions with different hashes. Restricted or non-redistributable dependencies remain external records and must not be copied.

## Validation sequence

1. Audit global/local state consistency and locked hashes.
2. Verify the stage-1 approved plan.
3. Verify every approved model referenced by a calculation.
4. Verify actual inputs and outputs correspond through registry IDs and hashes.
5. Verify processed data trace to real user results.
6. Verify every approved conclusion trace.
7. Verify manuscript methods use actual rather than planned parameters.
8. Verify software/method citations and version gaps.
9. Verify actual non-open software remains named.
10. Verify reproduction suggestions are separate and labeled unvalidated when not rerun.
11. Verify copied delivery files against source and manifest hashes.
12. Generate missing-item and reproducibility classifications.

Do not infer provenance from the folder tree alone.

## Missing-item severity

Classify every item:

- `BLOCKING_CORE`: breaks a conclusion, actual-method, model/result, or approved-manuscript trace.
- `BLOCKING_DELIVERY`: prevents a required deliverable from being inspected or opened.
- `REPRODUCTION_LIMITATION`: limits independent rerun but does not invalidate the supported paper claim.
- `DISCLOSURE_ONLY`: known optional or restricted item with an adequate disclosure.

Any blocking core item sets `DELIVERY_ITEMS_MISSING`. Reproduction limitations appear prominently but do not automatically block a scientifically complete package.

Each missing item names the file or record, task, reproduction impact, manuscript impact, suggested remedy, and whether acceptance of absence is scientifically defensible.

## Required reports

`FILE_MANIFEST.csv` records one row per delivery file. Include file ID, name, relative delivery path, type, stage, task, model version, parameter version, result version, original/approved flags, provenance source, hash, license/share status, and notes.

`README.md` states project objective, workflow, models, actual software, task sequence, directory map, processing methods, locations of conclusions/manuscript/reproduction notes, known gaps, and resume method. Unknown versions stay explicitly unknown.

`REPRODUCIBILITY_RECORD.md` distinguishes completely reproducible results, missing dependencies, non-open calculations, license-restricted files, proposed open alternatives, whether alternatives were actually validated, and expected sources of cross-program numerical differences.

`SOFTWARE_AND_LICENSES.md` distinguishes actual software from post-processing and prospective alternatives. Never guess a version, license, citation, or sharing right.

`DELIVERY_CHECKLIST.md` shows each gate, evidence, and pass/fail/unknown result. `DELIVERY_REPORT.md` summarizes completed stages, approved models, formal tasks, returned results, processed data, evidence nodes, manuscript content, software/license status, reproduction status, missing items, file count, and items the user must retain.

## Cleanup policy

Generate `files_recommended_for_cleanup.md` only as a recommendation. Never delete or move files automatically. Never recommend deletion of original input, output, structure, or data uploads.

If the user explicitly approves cleanup later, prefer a recoverable move to `project_delivery/_archive_unused/` and record source/destination hashes. That operation is outside the default delivery check and requires separate authorization.

## User review and archive

After a clean check, set `DELIVERY_USER_REVIEW_REQUIRED`. Run `project_control.py delivery-review` and show the package plus unresolved nonblocking disclosures. Only its matching confirmed browser `approved` decision may set `DELIVERY_PACKAGE_READY`. Then run the separate `archive-review` request; only its new matching confirmed browser `approved` decision may set `PROJECT_ARCHIVED`.

Archive records include global revision, project version, package manifest hash, report hash, traceability summary, missing-item summary, actor, confirmation note, and timestamp.

## Reopening

An archived project may be reopened. Require a reason and affected return state, increment `project_version`, preserve the earlier archive/delivery package, and record affected IDs and dependencies. Route only to the affected stage. A supplemental formal calculation ordinarily returns to stage 2 step 3, then stage 3 and stage 4 for the affected evidence and prose; it does not erase unchanged approved work.
