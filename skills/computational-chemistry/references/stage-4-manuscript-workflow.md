# Stage 4: Scientific Conclusions, Methods, and Reproduction Notes

## Contents

1. Scope and entry gate
2. Freeze the actual source record
3. Review software citation, license, and sharing
4. Generate evidence-calibrated conclusions
5. Write the actual computational method
6. Write results and discussion
7. Generate a separate open-source reproduction route
8. Review edits and their impact
9. Approve immutable manuscript content
10. Isolation and stopping rules

## Scope and entry gate

Use stage 4 to turn approved scientific questions, actual models/inputs/parameters, and approved stage-3 analyses into manuscript-ready computational methods, results/discussion, layered conclusions, citation/sharing records, and reproduction guidance. Do not design a new task, run a calculation, post-process data, or create a research figure.

Require and checksum read-only records from:

- the approved stage-1 plan, Markdown, status, and evidence chain;
- applicable approved surface/interface model records;
- geometry and formal result states, actual user-run inputs/outputs, and parameter-difference records;
- the formal task graph and result projection;
- `results_analysis/processing_status.json` with `RESULTS_APPROVED`;
- every stage-3 analysis approval record, its cited analysis, data validation, datasets, evidence matrix, and source snapshot;
- available experimental observations and theory–experiment mappings.

Write only under `manuscript_generation/`. Never change an upstream status, approval, input, result, dataset, or conclusion-strength record.

## Freeze the actual source record

Before drafting, build one software/source inventory per actual task. Record task, actual software, version, module, actual input, main output, relevant data, actual method parameters, post-processing software, model record, and differences from the stage-1 plan.

Do not identify software from a filename extension alone. Require at least two mutually supporting identification observations, such as input syntax, output header, embedded version string, or user statement, and bind every observation to an immutable stored file/checksum. If the version cannot be confirmed from existing files, write exactly:

> 软件版本信息未在现有文件中确认，正式投稿前需由用户补充。

Never guess a version. Use actual parameters when plan and execution differ, and preserve the difference report. Unknown result-relevant parameters block final manuscript approval rather than being silently filled from the plan.

Classify each actual software/license record as `open_source`, `commercial_or_closed`, `free_non_open`, `institutional_license`, or `unconfirmed`. This classification controls citation/sharing/reproduction handling only; it never changes the actual software name.

## Review software citation, license, and sharing

For every actual software and post-processing tool, record:

- official recommended software citation when verifiable;
- primary theory/algorithm references needed by the actual method;
- software/version/module provenance;
- whether input files may be shared;
- restricted pseudopotential, basis, force-field, database, or parameter dependencies;
- whether screenshots/manual quotations are included;
- the permitted public representation and acquisition instructions.

When current citation or license facts are needed, verify them against authoritative official sources and primary literature; do not invent them. A non-open-source program may be named normally in a paper. Do not reproduce long manual/help/website passages. Rewrite methods from actual inputs. Keep any excerpt short, attributed, and within applicable copyright limits.

Do not package a license-restricted file. Name the parameter/library, provenance, version, and authorized acquisition route instead. Mark an unconfirmed sharing right as blocked for public release until checked.

## Generate evidence-calibrated conclusions

Use only approved stage-3 conclusions. Preserve their direct data basis, physical meaning, evidence role, cross-result relationship, experimental correspondence, limitations, and strength. Do not arrange conclusions in software-output order.

Generate four levels:

1. data-level: values and direct trends only;
2. property-level: stability, charge transfer, electronic structure, bonding, adsorption, or another represented property;
3. mechanism-level: integrate multiple independent physical dimensions to explain how composition/structure changes a property;
4. overall: answer the approved core scientific question and state the justified theory–experiment relationship.

Do not jump from one value to a mechanism. A mechanism assertion requires multiple independent evidence roles, or it must remain partial/inconclusive.

Inherit the stage-3 strength ceiling:

- `STRONGLY_SUPPORTED`: “多个独立结果共同表明/支持”;
- `SUPPORTED`: “结果表明/支持/说明”;
- `PARTIALLY_SUPPORTED`: “结果提示/在一定程度上支持/可能相关”;
- `INCONCLUSIVE`: explicitly uncertain; never a definitive mechanism;
- `CONTRADICTED`: explicitly inconsistent with the original hypothesis.

Never use “完全证明”, “进一步证明”, or an equivalent certainty claim for merely supportive calculations. A user may lower a strength but cannot raise it above the approved source.

## Write the actual computational method

Write the full and concise methods from actual source records, not the stage-1 proposal. Include only reproduction- and interpretation-relevant items:

- model construction, facet/termination/interface, cell/vacuum, fixed regions, and boundary conditions;
- actual software/version/module;
- functional, dispersion, basis or pseudopotential, Hubbard U, cutoffs/grid, k points, charge, spin, occupations, and convergence criteria as applicable;
- geometry optimization and static/electronic/post-processing task relationships;
- only formulas actually used by the approved analysis;
- exact reference systems, structure states, cells/strain, and sign conventions for every formula.

For an actually used interface binding definition, state `E_bind = E_interface - E_A - E_B` and define every term. For an actually used charge-density difference, state `Δρ = ρ_interface - ρ_A - ρ_B` and define cell, coordinates, grid, and component states. Do not introduce a formula that did not produce an approved result.

Exclude scheduler account, queue, scratch path, and node count unless the target venue/project explicitly requires them.

## Write results and discussion

Organize by the scientific question, normally:

```text
structure/contact → thermodynamic stability → charge redistribution
→ electronic-state change → local bonding → experimental relation
→ bounded mechanism conclusion
```

Every paragraph names its primary conclusion, direct evidence, independent corroboration, and boundary. Distinguish direct experimental correspondence from explanatory association. Examples of bounded links include structure with XRD/HRTEM/EXAFS, electronic environment with XPS, DOS/PDOS with conductivity/sensing trends, and adsorption energy with adsorption tendency/site preference.

Do not convert adsorption energy directly into sensitivity, net charge transfer directly into macroscopic conductivity, or a theoretical trend into the sole experimental cause.

## Generate a separate open-source reproduction route

If an actual task used non-open-source, licensed, or license-unconfirmed software, generate a task-matched open-source migration proposal in a visibly separate section. Preserve the actual software in the methods.

Possible routes depend on demonstrated capability and file/method compatibility:

- periodic crystals/surfaces/interfaces/DOS/density: Quantum ESPRESSO or CP2K;
- large periodic/MOF/organic–inorganic/AIMD: CP2K where suitable;
- finite molecules/clusters: ORCA, Psi4, or NWChem after feature checks;
- classical MD: GROMACS, LAMMPS, or OpenMM with a validated force field;
- structure/cell operations: ASE, pymatgen, and spglib;
- charge/wavefunction analysis: Multiwfn, Critic2, Bader, or a compatible tool;
- bonding: LOBSTER only after compatibility, band, and projection checks.

Map structure, functional, dispersion, accuracy tier, k-point density, charge/spin, convergence, fixed atoms, vacuum, periodicity, task type, and requested outputs where meaningful. Mark basis/pseudopotential, grid, dispersion implementation, SCF algorithm, defaults, and internal algorithms as approximate or non-transferable when they are not identical.

Always include exactly:

> 该开源方案用于提供等效复现路径，尚未用于重新生成本文结果。由于不同程序的数值实现、赝势或基组体系存在差异，复现时可能获得存在合理数值偏差的结果。

The mapped template is future reproduction guidance, not provenance for the existing result. Use a title such as `开源软件复现建议`, not a title claiming the study actually used the alternative.

## Review edits and their impact

Generate `manuscript_review.html` with clearly separated actual-method and open-source-migration regions. Let the user edit document type, target style, language, detail, terminology, paragraph order, conclusion phrasing/strength at or below its source ceiling, and whether to retain the separate reproduction note.

Every edit creates a new immutable `vNNN` and an impact record. Classify:

- critical: changes actual software, source provenance, model, result, formula/reference, or actual core parameter;
- high: raises strength, removes an evidence limitation, changes mechanism scope, or changes direct/interpretive experimental status;
- medium: changes method detail, section order, open-source mapping, citation/sharing note, or technical terminology;
- low: grammar, length, venue style, or formatting without scientific meaning change.

Reject a critical factual conflict. Refuse to put an unused program into the actual-method record. An alternative mapping may change without altering actual provenance. Removing caution or changing “提示” to “证明” must be blocked when it exceeds the stage-3 strength.

## Approve immutable manuscript content

Approve only after source validation, license/sharing review, evidence-calibrated conclusions, actual method, separate open-source mapping when required, impact review, no blocking unknown actual parameter, and explicit user confirmation.

Freeze:

```text
method_statement_approved.md
result_discussion_approved.md
conclusion_approved.md
software_citation_list_approved.md
license_review_approved.md
open_source_reproduction_note_approved.md
manuscript_approval_record.json
```

Set `MANUSCRIPT_CONTENT_APPROVED`. A generated open-source mapping never means the existing results were reproduced with it.

## Isolation and stopping rules

Never design a new calculation, execute/post-process/plot data, rewrite actual provenance, replace a commercial program with an unexecuted open-source program in the real method, copy restricted dependencies/manual text, raise conclusion strength, invent versions/parameters/citations/licenses/results, overwrite history, or mutate stages 1–3.
