# Workflow

Use these nine steps for a new paper-to-deck job. For an existing-deck edit, reuse its sources, narrative and assets, apply only the affected steps and verify the revised deck. An outline-only request does not authorize deck generation. The paper-type fragment sets the narrative arc; the selected authoring workflow owns creation and export.

## Step 1. Read and extract source material

Extract, when available: title, authors, journal/preprint server, year, DOI; field and subfield; paper type; central problem and knowledge gap; main claim or thesis; study design, workflow, model, dataset, or experimental system; key methods and controls; main results and quantitative findings; key figures, tables, and figure legends; validation, robustness, ablation, or sensitivity analyses; limitations and unresolved questions; broader scientific, clinical, technical, environmental, or translational meaning.

Do not invent missing numbers, mechanisms, datasets, or figure details. Use a two-pass reading strategy: first capture metadata, abstract, headings, figure legends, and table captions; then read only the result and methods pages needed to support the slides. Start the Terminology Ledger here.

## Step 2. Classify the paper and choose the presentation logic

The router already detected the `paper_type` axis and loaded the matching arc fragment. Confirm the classification against the source, then follow that fragment's arc (`claim-first`, `question-to-evidence`, `problem-to-solution`, `workflow-to-validation`, or `evidence-map`) when ordering slides.

## Step 3. Build the Chinese presentation plan

Default length: 12-16 slides for a 15-20 minute report; prefer 10-14 for a quick or unspecified request; expand beyond 16 only for a detailed seminar deck or when the paper genuinely needs the space. Use the default slide structure from the loaded paper-type fragment and adapt it to the paper. Do not force every paper into the same template.

Before authoring, plan the visual rhythm: assign each slide a visual role and a composition type, and avoid repeating the same role/composition too often. For the composition-type catalogue and the rule against single-layout-family decks, open `references/design-and-layout.md`.

## Step 4. Select figures as evidence, not decoration

Prioritize figures that carry the argument: design/workflow, main evidence, validation/robustness, mechanism/model/synthesis, then practical/conceptual implication. Prefer a few readable key panels over many unreadable full figures. For the full selection checklist, open `references/figure-assets.md`.

## Step 5. Extract and prepare figure assets

Extract or render only selected figures, crop dense panels, keep original data visuals unchanged, save under `output/assets/figures/`, and record traceability in `output/asset_manifest.md`. For a standard 10-14 slide deck, usually select 4-8 assets. Prefer editable PPT-native tables/charts when values are explicit. Run the figure-crop self-check before insertion. A crop that removes panel letters, axes, legends, scale bars, method labels, table headers, or scientifically necessary annotations is a high-severity defect and must be re-extracted, expanded, or split into multiple slides before insertion. Full extraction, crop, and self-check rules are in `references/figure-assets.md`.

## Step 6. Write slide-by-slide content

For each slide write: Chinese title (conclusion-style where possible), slide purpose, suggested layout, 2-4 concise Chinese bullets, the selected figure/table asset if any, Chinese caption and interpretation, one core takeaway sentence, and a concise Chinese speaker note when oral explanation helps. Each slide makes one point. Avoid template-like phrases such as “一句话总结”, “最有价值的后续方向”, “不是……而是……”, generic “提供新视角”, or repeated slogan structures; use paper-specific, evidence-grounded Chinese instead.

Respect the on-slide text budget: write for the slide, not the manuscript; most explanation belongs in speaker notes. Order each result slide as hero evidence first, then a narrow interpretation rail, then only the minimum labels. The detailed text budget, evidence hierarchy, layout-adaptation, anti-template, archetype, title, and density rules are in `references/design-and-layout.md`.

## Step 7. Build the actual PPTX deck

Create and edit the real `.pptx` through the installed `Presentations` skill, following its toolchain and any user-provided template or style. Use 16:9 by default when no format is specified, Chinese titles/bullets/captions/notes, source labels on figure slides, content-sized text boxes with conservative margins, and consistent typography. Let slide geometry follow the figure rather than forcing the figure into a fixed 1:1 template. Align titles, figure edges, source labels, caption bands, and bottom notes to a small set of slide guides. Prefer shorter text, larger boxes, or splitting the slide over shrinking text; never deliver expected clipping. Full composition and text-fitting guidance is in `references/design-and-layout.md`.

## Step 8. Self-review and corrective revision loop

Follow the rendered self-review and correction process in `Presentations`. Inspect the PPTX and assets, fix high-severity and feasible medium-severity defects, then complete its finalization checks. The bundled `scripts/audit_pptx_quality.py` may supplement review as a backend-independent structural check; the checklist and its limits are in `references/self-review.md`.

## Step 9. Final verification

Complete the `Presentations` finalization checks and inspect the rendered slides. The local XML audit is supplementary and does not replace rendered review. Correct high-severity defects before delivery and report any remaining verification limitation. See `references/self-review.md`.
