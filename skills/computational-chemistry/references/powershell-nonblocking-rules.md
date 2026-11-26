# Controlled PowerShell 7 execution

Use PowerShell 7 only as an optional Windows-local executor. It may provide file content,
directory metadata, process results, browser launch requests, and user-requested script results.
It must never make scientific judgments or decide whether the workflow can continue.

## Invocation

Use only:

```text
pwsh -NoLogo -NoProfile -NonInteractive
```

Never fall back to `powershell.exe` or mix Windows PowerShell 5.1 with PowerShell 7.
If the version must be checked, do it once:

```text
pwsh -NoLogo -NoProfile -NonInteractive -Command '$PSVersionTable.PSVersion.ToString()'
```

Treat a missing executable, a failed check, or a major version below 7 as
`powershell7_unavailable`. Do not probe repeatedly.

## Allowed operations

PowerShell 7 may:

- read or write ordinary local text files;
- check paths, list directories, and return stable JSON metadata;
- run bounded local static checks;
- start Windows-native software;
- request that Windows open the current review page;
- run a `.ps1` file only when the user explicitly requests it.

Prefer a native file interface or direct Python/Node API when one is available. When using
PowerShell for UTF-8 text, prefer `System.IO.File.ReadAllText` with strict UTF-8 decoding over
`Get-Content`. Pass user paths through safe parameters, `-LiteralPath`, or .NET path APIs.
Never use `Invoke-Expression` or execute user-provided paths, names, structures, or parameters
as code.

## Non-interactive and bounded behavior

Prohibit `Start-Job`, `Receive-Job`, `Wait-Job`, `Enter-PSSession`, `Read-Host`,
`Pause`, `Out-GridView`, interactive menus, key confirmation, infinite loops, continuous
refresh, nested `pwsh`, and `cmd.exe`-mediated PowerShell.

Keep one primary purpose per call. Do not combine file reading, file mutation, program launch,
and validation in one command chain. A script block may include only the existence, error, and
output checks necessary for its single purpose.

Default limits:

- path check: 5 seconds;
- one text-file read or write: 10 seconds;
- directory scan: 15 seconds;
- browser launch request: 10 seconds;
- local program start check: 30 seconds.

Terminate the current process on timeout. Never wait in the foreground for a long calculation.

## Result validation

Do not infer success from exit code alone. A file read succeeds only when:

- the process exits within its timeout with code 0;
- stderr contains no unhandled exception;
- the file exists, is regular, and has nonzero size;
- stdout contains non-whitespace text;
- the returned length is plausible for the file size;
- the output is content rather than startup, job, or command text;
- the decoded body reaches the current analysis context.

Keep stdout and stderr separate. If exit code is 0 but stdout is empty, record
`read_incomplete`.

## Retry and fallback

Allow at most one retry for the same task and only with a specific correction:

- normalize a demonstrably invalid path;
- change decoding after a confirmed encoding error;
- correct a concrete command syntax error.

Do not retry a missing program, permission failure, or unexplained timeout. Never elevate
privileges or permanently change execution policy. After the bounded retry fails, continue in
the applicable state: `file_content_required`, `manual_file_check_required`,
`manual_execution_required`, `browser_manual_open_required`, `analysis_only`, or
`file_generation_only`.

PowerShell failure affects only that local operation. Continue goal analysis, parameter design,
file preparation, and every other step that does not require the missing result.

## Environment routing

- Windows-native file and software operations may use controlled PowerShell 7.
- WSL software uses Bash and the software's native commands.
- Linux servers use Bash and their scheduler commands.
- Slurm/PBS jobs are not simulated through local PowerShell.

For a long calculation, PowerShell may only verify process creation or submission and capture a
job identifier. Continue later from logs, output files, the job identifier, or user-returned
results.

## Script and state-file limits

Do not generate a `.ps1` file by default. Only generate one when the user explicitly requests a
Windows-native PowerShell 7 script. It must start with:

```powershell
#requires -Version 7.0
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
```

Do not silently use `Set-ExecutionPolicy Unrestricted` or permanently change CurrentUser or
LocalMachine policy.

Record executor, purpose, status, exit code, stdout/stderr presence, timeout, fallback, and next
stage in the current conversation. Do not create `execution_status.json` or helper scripts just
to record PowerShell activity.
