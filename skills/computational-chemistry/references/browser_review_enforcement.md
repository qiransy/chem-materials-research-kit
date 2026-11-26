# Browser review enforcement

## Default route

Browser review is the final checkpoint after progressive stage-1 intake, not the first response to a short request.

Do not create any review file until all applicable intake fields are present and consistent:

- calculation goal and requested operation;
- structure file or a precise statement of what existing file will be used;
- target software and version;
- run location and operating environment;
- environment-loading command and executable;
- requested deliverables;
- result files that the user should return;
- key method, charge/spin, periodicity, convergence, and constraint choices;
- scheduler resources, only when a submission script is requested.

If information is missing, ask the next small group of relevant questions and remain in intake. Do not create `.review/`, calculation inputs, manifests, approval records, or execution records.

When intake is complete, the default review artifact is exactly:

```text
.review/review.html
```

Generate it once for the current state. If the user requests a change, regenerate and overwrite that same file. Never generate `review_v1.html`, `review_v2.html`, `review_final.html`, timestamped review pages, or a review history directory.

Only when an automated browser-return mechanism is required may the workflow also create:

```text
.review/review_response.json
```

For a static local page, the page may let the user download the response JSON; the workflow must not pre-create an empty response file. Chat confirmation may be used when the environment has no return channel and the user has reviewed the page.

Use `scripts/staged_review.py check <intake.json>` to report missing fields and `scripts/staged_review.py render <intake.json> <project-directory>` to enforce the no-file-before-complete rule and the fixed output name.

## Page requirements

The review page must present readable sections and editable controls. Use text areas for goals and notes, text inputs for paths and commands, select controls for constrained choices, switches or checkboxes for Boolean choices, and numeric inputs for numeric parameters. Do not require a nontechnical user to edit a large JSON document.

The page must show at least the calculation goal, structure, software/version, environment, requested files, returned-result requirements, key parameters, unresolved warnings, and the decision requested from the user. It must not expose credentials, license keys, tokens, private server addresses, or arbitrary shell execution.

## Browser opening

Creating the page is sufficient to prepare review. Opening it automatically is an optional convenience.

On Windows, an allowed PowerShell attempt uses PowerShell 7 only:

```text
pwsh -NoLogo -NoProfile -NonInteractive
```

The operation must have a finite timeout and captured standard output/error. A successful process exit only means that the open request was sent; it does not prove that the user viewed or approved the page.

If browser opening fails, provide the absolute `.review/review.html` path or a verified local URL and continue the review flow. Do not create a status JSON file merely to record the failure, and do not make browser automation a prerequisite for scientific analysis.

## Approval and delivery

Review approval authorizes generation of the reviewed files only. The formal calculation directory contains the minimum files required by the target program and one `README.md`. Internal review artifacts remain in `.review/` and must not be copied into the formal calculation directory.

The default workflow must not create `approval_record.json`, `parameter_manifest.json`, `provenance_calc_record.json`, `provenance_model_record.json`, `review_content.md`, `RETURN_FILES_REQUIRED.md`, `execution_status.json`, `run_instructions.md`, or `validation_record.json`. If needed, concise run and return-file instructions belong in the single `README.md`.

## Advanced compatibility route

Version 1.0 projects may already use the repository's hash-bound Flask review server, `review_request.json`, `review_decision.json`, immutable stage records, and project-control state. Preserve that behavior only when the user opens an initialized advanced project or explicitly requests the advanced review mode.

Advanced compatibility artifacts are internal project records, not default calculation deliverables. Do not silently migrate, duplicate, or rewrite them into the default `.review/` format. Do not claim that advanced validation ran unless its actual scripts and decision checks were executed.
