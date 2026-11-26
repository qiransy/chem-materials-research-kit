# Stage 3: Data-Processing Guidance and Evidence Validation

## Contents

1. Scope and entry gate
2. Identify the user's data state
3. Provide resumable processing guidance
4. Ingest data without overwriting it
5. Check completeness and comparability
6. Analyze results and evidence
7. Resolve contradictions and evidence gaps
8. Review and approval
9. Completion and isolation rules

## Scope and entry gate

Use this stage to guide the user from real stage-2 outputs to analyzable data, inspect user-processed tables or values, explain their scientific meaning, and validate their role in the approved evidence chain. Do not create publication, presentation, or visualization figures. A figure is never an entry requirement or completion condition.

Require and checksum these read-only sources:

- `planning/stage1_plan_approved.json` and `planning/stage1_plan_approved.md`;
- `formal_calculations/formal_task_graph.json`;
- `formal_calculations/formal_result_status.json`.

Stage 1 must be `APPROVED`. At least one current formal task must have a real returned result or an accepted result. The entire formal workflow need not be complete. Analyze only the supplied task and its relationship to existing accepted results; never infer that other tasks finished.

Write only under `results_analysis/`. Never change `planning/`, `surface_design/`, `interface_design/`, `calculation_results/`, or `formal_calculations/`. If the frozen formal source records change because the user completed another formal batch, use the explicit source-sync operation and create a new source-snapshot history entry before continuing.

This stage may inspect text, CSV, Excel, JSON, Markdown, key values, integrations, peak positions, density/charge/DOS/COHP/QTAIM files, and user-supplied images. It may perform safe format inspection and simple tabular organization. It must not run a scientific code, post-processing program, generated command, scheduler, MPI launcher, remote downloader, or plotting pipeline.

## Identify the user's data state

When the user has not already stated their position, ask exactly:

> 请说明当前数据属于以下哪种情况：
>
> 1. 只有计算软件的原始输出文件；
> 2. 已经提取部分数据，但尚未完成处理；
> 3. 已经完成数据处理，需要分析结果和结论；
> 4. 不清楚如何处理，希望先获得完整教程；
> 5. 已经进行到某一步，需要从当前步骤继续。
>
> 可以直接上传文件，并说明当前做到第几步。

Do not ask this again when the user already supplied a category, files, or a current step. Map raw files to `RAW_DATA_RECEIVED`, partial work to `USER_PROCESSING_IN_PROGRESS`, processed data to `PROCESSED_DATA_RECEIVED`, an unknown method to `PROCESSING_GUIDE_REQUIRED`, and a declared step to that dataset's current progress record.

Maintain progress separately for every dataset/task/data type. A new file may reopen a failed prerequisite without erasing other completed steps or resetting unrelated datasets.

## Provide resumable processing guidance

When the user requests a complete tutorial, first show eight numbered steps. Each step states only its purpose, input, output, and pass standard:

1. confirm calculation completion and result integrity;
2. compare actual parameters with the approved plan;
3. extract only the target data;
4. unify units, references, coordinates, atom mapping, lattice, grid, or strain as applicable;
5. apply the approved formula, integration, projection, or partition;
6. establish method, model, and numerical comparability;
7. organize a traceable CSV, Excel, TXT, or Markdown table;
8. upload processed data for conclusion analysis.

After a full overview, say exactly:

> 你可以直接说“第 3 步不会”“我进行到第 5 步”或“第 6 步检查没有通过”，我会从对应位置继续。

Do not initially dump every command or GUI detail. When the user requests step N, expand only step N and its direct prerequisites/next handoff. Start after the highest genuinely completed step. If an uploaded file shows a missing earlier requirement, identify that requirement and preserve all unaffected progress.

Provide task-specific eight-step frameworks for binding energy, adsorption energy, charge-density difference, Bader charge, DOS/PDOS, COHP, and QTAIM. Use the formula, reference definition, sign convention, selected atoms/orbitals, and observable approved in stage 1. Do not silently replace them with a generic convention.

For CDD, guide grid-identical density subtraction and quantitative extraction but do not draw an isosurface. For DOS/PDOS, guide standardized energy-density tables but do not draw a DOS curve. A CDD image may be interpreted only with its isovalue, color definition, and quantitative support. A single atomic Bader value cannot establish whole-interface net transfer. ICOHP must be interpreted with pair identity, distance, composition, and sign convention.

## Ingest data without overwriting it

Copy every upload into a new immutable dataset version under either `user_raw_results/` or `user_processed_data/`. Checksum every stored file and preserve its semantic role, task ID, system ID, and user description. Never analyze a mutable source path in place and never overwrite an earlier upload.

Prefer processed-data metadata containing system name, model version, task, parameter, value, unit, reference definition, software, method, atom/orbital assignment, and completed processing steps. Missing noncritical metadata may remain an explicit limitation. Ask only for the specific missing item that changes the current judgment.

Raw outputs are suitable for identifying what to extract and for checking their provenance; they are not automatically suitable for a mechanistic conclusion. A screenshot, rendered plot, or single number cannot by itself establish completeness, comparability, or convergence.

## Check completeness and comparability

Check in this order:

1. actual calculation completion and required dependency outputs;
2. actual versus approved method and numerical settings;
3. target-data extraction completeness;
4. units, energy zero, reference definition, coordinate/atom mapping, cell, grid, and strain basis;
5. approved formula or processing definition;
6. comparability across every system used in a difference or trend;
7. traceable upload format.

Record every check as `passed`, `failed`, `unknown`, or `not_applicable`, with a concrete observation and source-file checksum. `unknown` is never equivalent to `passed`.

If the raw calculation is valid and only extraction, alignment, unit conversion, atom mapping, sign interpretation, or table organization is missing, use `SUPPLEMENTARY_PROCESSING_REQUIRED`. Do not request recalculation.

Use `RETURN_TO_FORMAL_CALCULATION` only for one of these fundamental causes:

- a necessary raw calculation or output is absent;
- a scientific method or key parameter is wrong;
- a mathematical reference system is not comparable and cannot be repaired from existing outputs;
- output precision, grid, bands, projection quality, or another source-data property is insufficient.

Return only to the necessary stage-2 step-3 task and name the evidence gap. Do not expand the approved plan into unrelated new calculations.

## Analyze results and evidence

Lead with what the current data can support. Use this order:

```text
completeness → comparability → trend → anomaly → represented property
→ supported conclusion → unsupported conclusion → cross-evidence consistency
→ specific missing data or next action
```

Every result analysis contains:

- `数据结论`: the direct numerical or categorical trend;
- `物理含义`: the structure, stability, charge, electronic, bonding, or other property represented;
- `证据作用`: the distinct function assigned by the stage-1 evidence chain;
- `相互佐证`: concrete agreement or disagreement with existing evidence;
- `实验对应`: a justified qualitative, semiquantitative, or quantitative experimental link;
- `结论边界`: claims this dataset alone cannot prove;
- `下一步判断`: approve, continue processing, or return for a narrowly scoped calculation correction.

Every evidence item cites an immutable stored file/checksum and a concrete observation. Do not fabricate missing values. Do not make different observables repeat the same evidence role: energy addresses thermodynamic tendency, geometry addresses contact structure, CDD addresses spatial redistribution, Bader addresses partitioned net transfer, PDOS addresses state/orbital origin, and COHP addresses pair-specific bonding/antibonding contributions.

Assign every core claim exactly one strength:

- `STRONGLY_SUPPORTED`: at least two independent physical dimensions agree;
- `SUPPORTED`: direct core evidence supports the claim, with limited mechanism depth;
- `PARTIALLY_SUPPORTED`: only part of the claim is supported;
- `INCONCLUSIVE`: data or comparability is insufficient;
- `CONTRADICTED`: valid data directly opposes the claim.

Never raise a strength to complete a preferred narrative.

## Resolve contradictions and evidence gaps

Before treating disagreement as scientific, check reference systems, energy zeros, atom mapping, model versions, calculation parameters, unit conversion, sign conventions, and convergence/validity. If any processing cause remains failed or unknown, route to supplementary processing. Only after these causes pass may the analysis record a real scientific contradiction.

Guide additional processing before recommending new calculations whenever the existing raw result is adequate. A supplementary task must fill the named current evidence gap and cannot become a broad new workflow.

## Review and approval

Generate `result_review.html` only as a text-and-table review surface. Show dataset inventory, progress, parameter definitions, key values, trends, evidence-chain position, strengths, limitations, missing information, and analysis history. Do not include a plot, chart, canvas, figure-export control, or image-generation completion gate.

Allow the user to mark:

- `该数据尚未处理`;
- `正在进行第几步`;
- `处理已完成`;
- `需要步骤指导`;
- `数据存在疑问`;
- `接受当前分析`;
- `要求重新分析`.

Progress edits create immutable progress versions. Analysis edits create immutable analysis versions. Accepting an analysis freezes its cited datasets and current source snapshot. Reanalysis never overwrites an accepted or rejected history record.

## Completion and isolation rules

An individual evidence node may be accepted while other nodes remain incomplete. Record `overall_stage_complete: false` and do not describe the entire stage as complete.

Set `RESULTS_APPROVED` only when necessary processing is complete, processed data are uploaded, completeness and comparability pass, directed analyses exist, cross-evidence consistency is addressed, all core claim strengths are assigned, all required stage-1 evidence nodes selected for the project are validated, and the user explicitly approves. No figure is required.

Never run calculations or formal post-processing, submit/query/monitor jobs, fetch remote results, generate research figures, overwrite upstream/history files, infer unreturned tasks as complete, interpret a processing error as mechanism, or make a claim beyond the evidence role of the supplied data.
