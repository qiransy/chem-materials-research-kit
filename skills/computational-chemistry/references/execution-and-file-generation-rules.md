# Intake, execution, and minimal-file rules

## Separate the layers

Keep four layers distinct:

1. Analysis: understand the scientific goal, system, methods, evidence, and risks.
2. Intake and review: collect missing information and obtain explicit user confirmation.
3. File generation and optional execution: create only required files and optionally attempt a
   bounded local launch.
4. Result analysis: inspect real user-returned inputs, outputs, logs, structures, and data.

Execution availability must not control scientific reasoning.

## Progressive stage-1 intake

For a simple or uninitialized request, collect information progressively rather than creating a
review page immediately. Confirm, in a natural order:

- calculation goal and calculation type;
- structure or existing files;
- software and version;
- run location: Windows, WSL, local Linux, or remote server;
- local/WSL/server environment and executable or module command;
- scheduler name only when relevant;
- whether an input, structure, helper script, or submit script is requested;
- result files the user will return;
- charge, spin, periodicity, method, basis/pseudopotential, cutoffs, k points, convergence,
  constraints, and resource-sensitive settings.

Ask scheduler resource questions only when the user requests a submit script. Before the required
information is complete, do not create review files, calculation inputs, approval records, or
manifests.

Use `scripts/staged_review.py check` when a deterministic completeness check is useful.

## Single final review

After intake completeness and consistency checks pass, generate or overwrite:

```text
.review/review.html
```

Use `scripts/staged_review.py render` for deterministic generation. Create
`.review/review_response.json` only if a programmatic browser-return channel is actually needed.
Edits overwrite the same HTML file. Never generate `review_v1.html`, `review_v2.html`,
`review_final.html`, or timestamped copies.

The page must use readable form controls—text fields, select boxes, checkboxes, toggles, and
numeric inputs—rather than requiring ordinary users to edit a large JSON document.

Browser auto-open is optional. A failed launch returns `browser_manual_open_required` and the
local page path; it does not regenerate the page or block analysis.

## Minimal calculation delivery

After explicit confirmation, the calculation directory contains only:

- input files the target software needs;
- a structure or parameter file only when the software needs it separately;
- one `README.md`.

Put the run command, expected output, requested return files, parameter cautions, and known risks
in that README. Do not create additional explanatory Markdown files.

Do not generate these by default:

```text
approval_record.json
parameter_manifest.json
provenance_calc_record.json
provenance_model_record.json
review_content.md
RETURN_FILES_REQUIRED.md
execution_status.json
run_instructions.md
validation_record.json
```

Advanced initialized projects may maintain internal provenance and immutable stage records
outside the calculation delivery directory. Do not copy those internal records into the minimal
calculation package.

## Script and scheduler routing

Do not generate a run script for a simple native command. Put that command in `README.md`.
Generate one helper script only when the user explicitly asks or the command is genuinely
error-prone.

- WSL and Linux use Bash and native program commands.
- Generate `submit.slurm` only when the user asks for a Slurm submission script.
- Generate a `.ps1` only on an explicit Windows-native PowerShell 7 request.

Never wait synchronously for a long calculation. A bounded launch may establish a process or job
identifier; later work uses logs, outputs, scheduler state supplied by the user, or returned
files.
