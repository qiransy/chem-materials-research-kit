# Output files, citation, and quality rules

## Citation and attribution rules

Include source information:

- title slide: paper title, authors if useful, journal/preprint server, year, DOI if available,
- figure slides: small labels such as `Source: Fig. 2b, Nature, 2024`,
- adapted or redrawn content: label as `整理自` or `改绘自`,
- do not remove original figure labels or alter scientific data.

## Output files

Generate a minimal but complete output package when a deck is requested. For revisions, retain unchanged assets and update the existing working copy and QA record rather than recreating the whole package. Honor outline-only or explanation-only requests.

### 1. `output/final_presentation_cn.pptx`
The main deliverable: a complete Chinese PPTX deck with figures, captions, takeaways, source labels, and speaker notes.

### 2. `output/qa_report.md`
When a QA note is useful or requested, record PPTX creation status; slide count; figures inserted; missing or placeholder figures; figure-crop QA results; alignment checks; self-review defects found and corrected; overflow checks; verification method; and material limitations. Follow the available backend's rendered review and finalization path. The local XML audit is supplementary.

### 3. `output/assets/figures/`
Extracted or cropped figure assets used in the deck.

### 4. `output/asset_manifest.md`
Figure asset traceability file, generated only when external figure/table assets are extracted: asset filename; original figure / panel; source page or source file; extraction method; slide placement; crop rectangle or page-render method when known; quality notes, including whether titles, axes, legends, scale bars, table headers, and panel labels are preserved.

If no external figure/table assets are extracted, omit `asset_manifest.md` or write a one-line note in `qa_report.md` instead.

### Optional files
Create these only when useful for review, debugging, or user-requested traceability, and skip them by default unless they materially reduce back-and-forth:

- `output/ppt_outline_cn.md` — Chinese outline: paper information, paper type, central argument, slide structure, slide purpose.
- `output/figure_plan.md` — figure selection plan: figure / panel, what it shows, why it matters, recommended slide, Chinese caption, interpretation.
- `output/ppt_script_cn_with_figures.md` — slide-by-slide script (Purpose / Layout / On-slide bullets / Figure-Table / Chinese caption / Core takeaway / Speaker note per slide).
- `output/rendered/` — save preview images when useful or requested; inspect the rendered deck using the selected backend's preview path when available.

## Quality rules

- Build the `.pptx` whenever tooling is available; do not stop at a markdown outline or script.
- Do not fabricate results, methods, numbers, or figure details.
- Do not add expensive processing steps unless they improve the deck or were requested.
- Do not overload slides with text.
- Do not deliver slides with text extending beyond visible boxes, clipped by boxes, or likely to overflow after font substitution.
- Do not make result slides text-only when figures are available.
- Make every slide serve the paper's argument.
- Ensure figures are readable at presentation scale, and that selected crops preserve all scientifically necessary context before placement. Cropped-off axes, legends, panel labels, scale bars, method labels, or table headers are delivery blockers.
- Ensure text, captions, and figures do not overlap.
- Ensure font hierarchy is consistent across slides and that figures, captions, source labels, and metrics feel visually related rather than independently placed.
- Ensure layout alignment is intentional: repeated title blocks, figure edges, caption/source strips, and bottom notes should share stable guides rather than drifting by a few points.
- Ensure Chinese expression is academic and source-specific; remove obvious AI-template phrases and repetitive slogan patterns.
- Ensure the visual rhythm does not feel like a repeated AI template; vary composition based on evidence role and figure geometry.
- Ensure the deck is not visually underfilled: empty regions should be intentional whitespace, not leftover template space.
- Run at least one self-review and corrective revision pass; do not deliver a first draft with known high-severity defects.
- Use the selected tool for PPTX authoring, rendered review, and finalization. Record whether checks were structural or visual.
- Document uncertainty and missing source material clearly.

## Fallback rules

If only partial content is available: still create a useful PPTX structure when possible; clearly mark uncertain slides or missing details; use placeholders only when a required figure is unavailable; do not invent exact values or claims; write `output/qa_report.md` explaining what could not be verified.

If PPTX tooling is unavailable: generate a concise markdown outline and figure plan; prepare figure assets if possible; explain why the PPTX could not be built in the current environment; keep the outputs structured enough for a downstream PPTX builder to run without re-reading the paper.
