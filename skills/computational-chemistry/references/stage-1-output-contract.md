# Stage 1 Output Contract

Produce a decision-ready research and computation plan. Lead with the conclusion, then use the required sections below. Adapt detail to the project, but do not omit a section; write “not applicable” with a reason where necessary.

## Opening conclusion

State in one compact passage:

- the recommended computational route;
- the central evidence chain;
- the highest-priority decisions;
- the proposed redundant calculations to remove or defer;
- the most important provisional assumptions.

## 研究目标

Identify the research object, comparison object, central scientific question, and precise claim to support or refute. Distinguish user-stated facts from provisional inferences.

## 科学问题拆分

List independent subquestions and explain their dependency order. Give each subquestion one principal evidence target.

## 计算体系与对照组

Define main models, controls, comparison logic, reference states, and the settings that must remain identical for comparability.

## 总体证据链

Map each planned result to its unique role across reliability, structure, energy, charge, electronic/orbital character, bonding, kinetics/dynamics, and experiment. Omit irrelevant layers rather than forcing completeness.

## 具体计算方案

For each task, include:

| Field | Required content |
| --- | --- |
| Scientific decision | The exact question answered |
| Task statement | Software + module/function + system/control + calculation + output + property + cross-check + supported conclusion |
| Evidence role | Foundation, core, mechanism, or supplemental |
| Prerequisite | Earlier result or model condition required |
| Parameter basis | Source/criterion; range or convergence test if unresolved |
| Scientific weight | I, U, S, and N component scores with separate rationales; calculate the weighted value |
| Workload weight | M, C, K, P, and H component scores with separate rationales; calculate the weighted value |
| Sensitivity and irreplaceability | How the result affects the conclusion and whether another result can replace it |
| Alternative | Viable substitute and tradeoff |
| Cost | Low/medium/high/very high and principal scaling factor |
| Scope | All models or representative subset |
| Cancellation impact | Whether and how the core conclusion weakens |

Never report uncomputed values or imply a calculation has converged.

## 重复性审查

Classify every potentially overlapping calculation as retain, merge, conditional, or delete. Explain whether tasks are complementary or duplicative and whether deletion affects the central conclusion.

## 资源优化方案

Identify low-cost screening, representative-system selection, conditional high-cost work, reusable existing results, and tasks that can be cancelled immediately.

## 与实验结果的对应关系

For each major observable, name the experimental comparison, classify it as qualitative/semi-quantitative/quantitative, and state confounders or limitations.

## 阶段进入与终止条件

Give measurable readiness checks for proceeding to production-input generation or formal computation. Give stop/review conditions for invalid models, failed convergence, contradictory evidence, hypothesis rejection, unavailable software, incompatible data, or excessive cost.

## 最终执行路线

Give a concise dependency-ordered sequence. Include decision branches and representative-system gates. Describe logic only; do not generate formal input files or commands that run the calculation.

## 结构化审查交接

After completing the narrative plan:

1. Serialize it to a JSON object that follows `stage-1-plan-schema.md`.
2. Validate that every task includes both weight structures and all display fields.
3. Run `scripts/stage1_review.py init --plan <source-plan.json> --planning-dir <project>/planning`.
4. Start the local review service with `scripts/stage1_review.py serve --planning-dir <project>/planning --open` and open the returned local URL. If automatic opening fails, keep the service running and give the user the exact local address.
5. Follow `stage-1-review-and-approval.md` for every edit, impact analysis, decision, and final approval.

Treat JSON plan versions—not browser state or Markdown—as the formal data source for later stages.

## Final quality check

Before responding, verify that:

- the plan begins with a scientific question rather than a software list;
- every task has a unique evidence role and a specified control;
- directly compared calculations use consistent conditions;
- fixed parameter values have explicit support or are labeled provisional;
- redundant methods are removed or conditionally justified;
- high-cost work follows screening and explicit entry criteria;
- experiment links do not exceed the evidential strength of the calculation;
- no software capability, result, citation, or convergence status is invented;
- no input file, job submission, computation, result extraction, or post-processing has been performed.
- the initial plan has been serialized, versioned, and presented for user review;
- stage 1 is not called complete unless the approved baseline exists and status is `APPROVED`.
