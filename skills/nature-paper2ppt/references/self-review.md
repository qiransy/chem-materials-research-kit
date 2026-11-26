# Self-review and verification

## Contents

- [The loop](#the-loop)
- [Self-review checklist](#self-review-checklist)
- [Severity rules](#severity-rules)
- [Supplementary structural PPTX audit](#supplementary-structural-pptx-audit)
- [Rendered preview policy](#rendered-preview-policy)
- [Step 9 — final verification](#step-9-final-verification)


Open this reference for step 8 (self-review/corrective revision loop) and step 9 (final verification).

## The loop

After creating the first PPTX draft, run at least one explicit self-review pass before declaring the deck final. Treat this as a defect-finding step, not a confirmation step.

1. Inspect the generated PPTX and extracted assets.
2. Write a short defect list with severity (`high`, `medium`, `low`) and slide numbers.
3. Correct every high-severity issue and every medium-severity issue that can be fixed without expanding the task substantially.
4. Regenerate the PPTX after edits.
5. Re-run verification and update `output/qa_report.md` with what was checked, what was fixed, and what remains.

## Self-review checklist

Check content and structure:

- slide order follows the paper's argument, not merely the paper section order,
- each slide has one dominant claim,
- slide titles are conclusion-style where possible,
- no invented numbers, mechanisms, datasets, claims, or unsupported implications,
- result slides include source labels and do not remove original scientific labels,
- speaker notes exist when planned and are useful for oral explanation.

Check visual and layout quality:

- no cropped-off figure titles, axes, legends, panel labels, or important annotations,
- no source figure is squeezed so far that the evidence becomes unreadable,
- dense figures are split or cropped rather than placed as tiny full-figure screenshots,
- text boxes, figures, captions, source labels, and takeaway bands do not overlap,
- no text visually exceeds or is likely to exceed its text box; text overflow is a delivery-blocking defect,
- all shapes stay inside slide bounds,
- text density is reasonable; move excess explanation into speaker notes or split the slide,
- layout rhythm feels intentional rather than generated from one repeated card/rail template,
- no slide uses equal cards or metric chips merely to fill space,
- cards, metrics, and captions have consistent spacing and alignment,
- font choices are Office-safe; avoid relying on a font that is unavailable in the environment for text fitting.

## Severity rules

Use `high` for defects that can mislead the audience or make the deck look broken:

- clipped scientific evidence such as axes, legends, panel labels, table rows, figure titles, or method labels,
- unreadable main evidence on a key result slide,
- overlapping text/figures, text cut off by its box, or text extending beyond a visible boundary,
- wrong slide order or missing central evidence,
- fabricated or unsupported quantitative statements.

Use `medium` for defects that reduce professionalism or comprehension:

- overly dense slides,
- rigid AI-looking layouts, especially repeated equal cards, repeated right-side rails, or decorative metric rows,
- weak crop margins,
- figure captions detached from the visual,
- excessive repeated layouts,
- missing or unhelpful speaker notes,
- ambiguous source attribution.

Use `low` for cosmetic issues that do not affect comprehension:

- minor alignment imperfections,
- palette or typography refinements,
- optional split of a readable but dense figure.

## Supplementary structural PPTX audit

Use the installed `Presentations` skill for PPTX authoring, rendered review, and package finalization. When useful, run this backend-independent script to inspect PPTX XML after the first draft and after revision:

Resolve the bundled script relative to the directory containing this skill's `SKILL.md`; the sample path below is illustrative. Use the active shell's normal quoting and path syntax.

```bash
python skills/nature-paper2ppt/scripts/audit_pptx_quality.py \
  output/final_presentation_cn.pptx \
  --report output/pptx_audit.md \
  --fail-on high
```

If the script reports high-severity findings, treat the deck as not ready. Fix the deck, regenerate, and run the script again. Copy the final audit summary into `output/qa_report.md`.

The script checks common structural and language issues directly from PPTX XML:

- shapes outside the slide canvas,
- suspicious image crop settings,
- main evidence images that are too small for presentation use,
- repeated near-miss alignment between objects,
- text-heavy shapes likely to overflow,
- AI-template phrases such as `一句话总结`, `最有价值的后续方向`, and `不是……而是……`,
- slide count, media count, and notes count.

The authoring/finalization workflow should also check, when supported:

- reopen the PPTX with the active presentation tool,
- count slides and embedded media,
- count non-empty notes slides if notes were planned,
- check every shape's left/top/right/bottom stays within the slide canvas,
- flag text-heavy slides by character count and number of text boxes,
- flag any text box whose estimated text length is too large for its width/height, especially mixed Chinese-English strings,
- flag long unbroken tokens or labels that may overflow narrow boxes,
- count repeated layout patterns and flag decks that reuse the same composition too often,
- flag images whose displayed size is too small for their role,
- scan for placeholder text such as `lorem`, `xxxx`, or accidental unreplaced labels.

These checks cannot prove visual perfection, but they reliably catch many failures and should trigger a manual/self-review pass.

## Rendered preview policy

Use the rendered-slide review provided by the installed `Presentations` workflow. Inspect available previews for missing images; distortion or low resolution; unreadable panels; text overflow; overlaps; excessive density; wrong order; missing source labels; and missing or unhelpful speaker notes. Do not require a separate headless renderer when `Presentations` already provides previews.

If rendered preview reveals defects, revise and regenerate the PPTX. Do not deliver a deck with obvious visual defects merely because the package validates.

If no rendered preview is available through `Presentations`, complete structural and text checks that the available tools support, and state clearly in the requested QA note that visual inspection was not completed.

## Step 9 — final verification

After revision, complete the active `Presentations` finalization workflow; check slide count, embedded media, and planned speaker notes where supported. The local `audit_pptx_quality.py` and extracted-asset contact sheets are supplementary checks, not substitutes for rendered-slide inspection.

Do not stop at "PPTX opens" if the self-review found high-severity issues. Correct them first, then verify again. Document any remaining limitation in `output/qa_report.md`.
