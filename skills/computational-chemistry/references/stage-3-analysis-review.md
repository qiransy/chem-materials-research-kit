# Stage 3 Review Page and Interaction Rules

## Contents

1. Purpose
2. Required views
3. Progress and guide interactions
4. Analysis interactions
5. Text-only boundary
6. Security and history

## Purpose

Use `results_analysis/result_review.html` to review data provenance, processing progress, scientific interpretation, and evidence-chain status. The page is an interaction and confirmation surface, not a plotting program and not the authoritative state store.

The page must state visibly that the Skill did not run calculations or post-processing and does not create publication/presentation/data-visualization figures in stage 3.

## Required views

Show all of:

- frozen stage-1 and formal source records;
- dataset versions, raw/partial/processed stage, file roles, checksums, and format inspection;
- per-dataset current and completed processing steps;
- generated guide versions and requested step;
- parameter names, values, units, reference definitions, method, and model versions;
- completeness and comparability findings;
- direct trends and anomalies;
- stage-1 evidence role and formal task/node mapping;
- conclusion strengths, supporting evidence, limitations, and experimental correspondence;
- contradictions and the eight processing-error checks;
- missing information, next action, validated nodes, and overall-stage-complete flag;
- immutable analysis/progress/source-sync history.

Never reconstruct formal state from the DOM. Load the authoritative JSON through `/api/state`.

## Progress and guide interactions

The user may submit exactly these markers:

```text
该数据尚未处理
正在进行第几步
处理已完成
需要步骤指导
数据存在疑问
```

The acceptance and reanalysis markers are handled by analysis actions. A progress submission includes dataset ID, task ID, data type, current step, completed steps, reopened steps, and notes. Completed steps are monotonic.

A guide request chooses `full` or a single step. The browser displays the overview or requested step and writes a new immutable guide; it never executes displayed instructions.

## Analysis interactions

From `WAITING_FOR_RESULT_APPROVAL`, the page allows:

- `接受当前分析`, which calls `accept-analysis` and freezes the current version;
- `要求重新分析`, which requires a reason and calls `request-reanalysis`.

Do not expose a button that marks all evidence complete. Completion is derived from approved analyses, the formal task graph, and required evidence nodes.

The browser may present JSON examples but cannot let the user change project/task/evidence IDs, checksums, execution flags, source snapshots, validated-node history, or engine-owned states.

## Text-only boundary

Use text, lists, tables, status badges, and downloadable source files. Do not use chart libraries, SVG plots, `canvas`, automatic figure export, color maps for scientific fields, or a generated figure preview. A user-supplied image may appear only as a provenance-listed file; numerical definitions and quantitative support remain necessary for scientific acceptance.

The page must not request an image when a CSV, TXT, Excel, integration, peak table, or key-value record is sufficient.

## Security and history

Bind the server to `127.0.0.1` by default. Decode requested file paths into a safe path under `results_analysis/`; reject traversal and files outside the store. Limit JSON request bodies and return JSON errors without leaking unrelated files.

Every API mutation invokes the same validation and source-snapshot checks as the CLI. Browser actions create immutable records and change-log entries. The page cannot run commands, scientific software, post-processing tools, schedulers, remote fetches, or plotting pipelines.
