# Troubleshooting

## Stage-1 and review issues

### A simple request did not create a review page

This is expected. The default workflow first collects the goal, structure/files, software/version, run location, environment command, deliverables, returned-result requirements, and key parameters. It creates `.review/review.html` only after those fields are complete and consistent.

### No `.review/review.html` was created

Run the deterministic completeness check if an intake JSON exists:

```text
python scripts/staged_review.py check intake.json
```

Missing fields are reported without creating review or calculation files. Correct the intake and then use `render`. Do not create placeholder approval, manifest, status, or review files.

### A revision created several review pages

That is not the version 1.1 default behavior. Delete the uncommitted/generated duplicates and regenerate the current state at `.review/review.html`. The page is overwritten on each revision. Preserve legacy versioned artifacts only inside an existing advanced project that explicitly uses the version 1.0 compatibility workflow.

### The browser did not open

Automatic opening is optional. Open the absolute `.review/review.html` path manually, or use the verified local URL printed by the tool. Browser-open failure does not block scientific analysis or calculation-file generation after approval.

## PowerShell 7

All allowed PowerShell calls use:

```text
pwsh -NoLogo -NoProfile -NonInteractive
```

They must have a finite timeout and captured standard output/error. Do not substitute `powershell.exe` or Windows PowerShell 5.1.

### `pwsh` is not found

Mark the Windows automation action unavailable and use the relevant fallback: direct file APIs/Python for local data, Bash for WSL/Linux, the software's native executable, or a manual command. Continue the scientific analysis and file generation. Installing PowerShell 7 is optional unless the user explicitly needs a Windows PowerShell action.

### PowerShell is older than version 7

Run one bounded version check. If the major version is below 7, do not use that executable for the Skill. Use a fallback or ask the user to install a current PowerShell 7 release. Do not fall back to Windows PowerShell 5.1.

### Exit code is zero but standard output is empty

Treat the operation as incomplete when output was required. Check timeout state, standard error, and whether the returned content is nonempty and valid for the expected format. Retry at most once and only when there is a concrete correction, such as fixing quoting or selecting the right output stream. Otherwise use the fallback and continue.

### A path contains Chinese characters or spaces

Pass the path as one literal argument. Do not interpolate it into an expression or command chain. Prefer an argument array or a script parameter. Validate the resolved target before writing. If encoding remains ambiguous, use a direct Python `pathlib` operation with UTF-8/UTF-8-BOM handling.

### A command timed out

Terminate the bounded action, capture the timeout and any partial standard output/error, and do not repeat the identical command. One retry is allowed only with a justified correction. Long calculations must be launched/submitted separately and observed later through logs, result files, or job identifiers; PowerShell must not wait in the foreground.

### Browser launch through PowerShell failed

Provide the local page path or verified address. Do not block review and do not generate an execution-status file solely for this failure.

### Local calculation software cannot be found

Verify the software version, environment-loading command, and executable name with the user. For WSL/Linux use Bash and the native command. If a Windows-native launch is required, try the corrected PowerShell invocation at most once, then switch to `manual_execution_required` and put the native command in the single calculation `README.md`.

### Execution policy error

The default workflow does not generate or require a `.ps1` script. Only a user-requested Windows-native script may need an execution-policy decision. Do not recommend permanently weakening the machine-wide policy; prefer a narrowly scoped, organization-approved invocation or the software's native command.

## Calculation-file issues

### Unexpected approval or provenance files appeared

The default formal calculation directory contains only necessary program inputs/structures/parameters and one `README.md`. Files such as `approval_record.json`, `parameter_manifest.json`, provenance records, `RETURN_FILES_REQUIRED.md`, `run_instructions.md`, and `execution_status.json` are not default deliverables. Keep advanced internal project records outside the calculation directory.

### A cluster input-only request asks for Slurm resources

Clarify that only the input file is requested and skip scheduler questions. Ask for partition, nodes, tasks, memory, wall time, or account only if `submit.slurm` is requested.

### A static check passed but the calculation failed

Static checks verify structure and syntax, not convergence or scientific validity. Inspect the real program output/error, actual input, environment, and final structure before diagnosing the cause. Never claim that a calculation ran based only on generated files or passing unit tests.
