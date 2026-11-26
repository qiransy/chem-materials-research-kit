---
name: literature-review
description: Conduct a formal systematic or scoping literature review with an explicit search protocol, screening record, and cross-study synthesis. Use for requested systematic reviews; ordinary paper searches and single-paper reading use focused installed skills.
allowed-tools: Read Write Edit Bash
license: MIT license
metadata:
  version: "1.7-local"
  skill-author: K-Dense Inc.
---

# Systematic Literature Review

Use this workflow for a formal systematic or scoping review. For ordinary retrieval,
use [paper-lookup](../paper-lookup/SKILL.md); for a single-paper analysis, use
[nature-paper-card](../nature-paper-card/SKILL.md).
For an integrated multi-stage research-to-paper project, use
[academic-research-suite](../academic-research-suite/SKILL.md) when requested.

For chemistry and materials studies, preserve the user's control of scope,
mechanism interpretation, and experimental/computational criteria.

## Workflow

1. Define the research question, scope, inclusion/exclusion criteria, time span,
   accessible sources, and intended deliverable.
2. Select appropriate scholarly indexes and publisher searches. Record actual
   queries, dates, coverage, and counts. Use paper-lookup or currently available
   search tools. No particular CLI, API key, or fixed database count is required.
3. Deduplicate with traceable identifiers, screen titles/abstracts and available
   full text, and record reasons for exclusion. Separate inaccessible papers from
   studies excluded on scientific criteria.
4. Extract comparable evidence and limitations. In chemistry and materials
   research, distinguish experimental measurements from theoretical predictions,
   and preserve units, synthesis/testing conditions, computational levels, and
   reported uncertainties.
5. Synthesize around the research question. Do not force a biomedical risk-of-bias
   scheme or meta-analysis onto heterogeneous chemistry or materials results.
6. Verify included references through
   [nature-ref-verifier](../nature-ref-verifier/SKILL.md), and distinguish
   bibliographic accuracy from support for each scientific claim.
7. Deliver the requested format and state search limitations. Do not claim an
   exhaustive or PRISMA-compliant review without the corresponding records.

## On-demand resources

- `references/core_workflow.md`: detailed systematic-review phases when needed.
- `references/search_and_citation.md`: search and citation-format guidance.
- `references/example_workflow.md`: an example, not a mandatory output template.
- `assets/review_template.md`: use only if it suits the requested deliverable.
- `scripts/search_databases.py`, `scripts/verify_citations.py`, and
  `scripts/generate_pdf.py`: optional helpers; inspect their requirements before use.

These legacy resources may mention parallel-cli, biomedical tools, AI schematics,
or fixed source counts. They are examples, not required dependencies or grounds to
expand this task. Do not install tools, request paid services, or create a PDF
unless needed for the user's requested output.

Figures are optional. Use a source-grounded screening flow diagram or evidence
table when useful; do not invent counts or require AI-generated illustrations.
Use scientific-visualization for data plots. Verify current target-journal or
reporting guidance only when that standard is relevant to the requested review.
