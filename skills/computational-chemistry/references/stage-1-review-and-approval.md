# Stage 1 intake, review, and approval

## Default completion rule

Stage 1 begins with conversation, not file generation. For a short request, ask for missing information progressively and keep all current answers in the active analysis context. Do not infer unknown software versions, structures, environment commands, scheduler requirements, charge/spin, periodicity, or convergence choices.

Collect and check, in this order where applicable:

1. calculation goal and expected scientific outcome;
2. structure file or existing calculation files;
3. calculation software and exact version;
4. run location: Windows, WSL, local Linux/macOS, or remote server;
5. local environment activation or server module command and executable;
6. whether the user needs only input files, a local launcher, or a scheduler submission script;
7. files that the user should return after the calculation;
8. key scientific parameters and unresolved choices.

Ask scheduler name, partition, nodes, tasks, memory, wall time, account, and queue details only if the user requests a submission script. If the user requests only a Quantum ESPRESSO input file, do not ask Slurm questions merely because the calculation will run on a cluster.

Examples:

- “帮我用 CP2K 优化这个结构” is incomplete. Ask for the optimization objective and structure first, then software version and environment, then deliverables and key parameters. Create no files yet.
- Windows 11 + WSL Ubuntu 22.04 + CP2K 2024.3 + `use_cp2k` + `cp2k.psmp` uses Bash and the native CP2K command. Do not generate or invoke PowerShell.
- Linux cluster + Quantum ESPRESSO 7.5 + `module load qe/7.5` + input-only request needs no scheduler resource questions and no `submit.slurm`.

## Consistency gate

Before generating review files, confirm that:

- the structure format is supported by the selected program or a conversion is explicitly planned;
- the software version, executable, and environment-loading command agree;
- the run location matches the launcher type;
- requested files are sufficient for the chosen calculation;
- required return files are named in the review;
- charge, multiplicity or magnetization, boundary conditions, constraints, method, and convergence settings are either specified or visibly marked for user decision;
- scheduler resources are complete only when a submission script is requested.

An incomplete or inconsistent intake remains in stage 1 conversation. It must not create `.review/`, calculation parameter files, approval records, provenance records, manifests, status JSON, or supplemental Markdown.

## Final browser review

After the consistency gate passes, generate or overwrite exactly:

```text
.review/review.html
```

Use `scripts/staged_review.py` when available. The page must use understandable form controls and present every decision that will affect the generated calculation files. Only create `.review/review_response.json` when an automated response-return mechanism requires it. A user revision overwrites `review.html`; it does not create a versioned review page.

Automatically opening the page is optional. If it fails, return the absolute path or a verified local address and continue waiting for review. Do not make PowerShell availability a condition for completing stage-1 analysis.

## Approval and generation

Approval covers the exact contents displayed on the current page. After approval, generate the minimum target-software file set plus one `README.md`. Put commands, parameter notes, expected outputs, and return-file instructions in that README.

Do not generate default approval, provenance, manifest, review-content, return-file, validation, run-instruction, or execution-status files. Do not generate `.ps1` unless the user explicitly requests a Windows-native PowerShell script. Use Bash for WSL/Linux. Generate `submit.slurm` only when requested.

Static validation proves only file/schema consistency; it does not prove that a scientific calculation will converge or be physically meaningful. Do not claim external software ran unless real output was returned and checked.

## Advanced project compatibility

If the user explicitly opens an initialized advanced project, the immutable `planning/stage1_plan_vNNN.*`, hash-bound review service, impact analysis, approval record, and project-control state from version 1.0 remain available. Follow their existing schemas and scripts without presenting them as the default simple workflow.

Advanced records are internal project metadata. Keep them outside the formal calculation directory, preserve their histories, and never claim they were created or validated unless the corresponding repository scripts actually ran successfully.
