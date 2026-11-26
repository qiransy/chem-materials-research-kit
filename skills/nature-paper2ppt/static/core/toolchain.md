# Toolchain policy and fast path

## Toolchain policy

Use the installed official `Presentations` skill as the PPTX authoring, editing, and rendering workflow. Follow its current implementation guidance and toolchain. This skill defines paper-specific research, figure-selection, and slide-story decisions; it must not prescribe a conflicting PPTX library.

When the user explicitly selects `ppt-master`, use that installed skill as the sole authoring workflow instead; this skill supplies source-grounded narrative and figure choices, not a competing export pipeline. Follow PPT Master's own gates and native PPTX checks. Microsoft PowerPoint is this user's primary compatibility target. Preserve native editable text, shapes and connectors where supported, and identify retained raster figures honestly.

For source-paper inspection and figure extraction, use the available document/PDF tools and image utilities that fit the current environment. Keep the minimum processing needed for the selected figures:

- extract metadata, text, page renders, and crops with available PDF/document tools,
- use image utilities for selected figure crops and contact sheets,
- create or edit the deck with the authoring path specified by `Presentations`,
- use the presentation workflow's package checks and rendered-slide review.

Respect the current environment and the user's selected template or style. Use Office-safe fonts where possible. Do not install an alternative presentation stack merely to follow this reference.

Use the rendering and finalization path documented by `Presentations`; do not substitute a different renderer if it would misrepresent the final deck.

Ask or document the tradeoff before doing expensive extras such as full supplementary-material processing, high-resolution recreation of many figures, full slide-by-slide rendered QA, or very long decks.

## Default fast path

For a normal selectable-text paper PDF, run the shortest complete path:

1. Extract metadata, abstract, headings, figure legends, and table captions with PyMuPDF.
2. Identify the paper type, argument, and candidate figures before rendering high-resolution pages.
3. Render low-resolution contact sheets only when figure locations are unclear.
4. Render high-resolution images only for selected figure/table pages and crop only assets that will appear in the deck.
5. Build/edit the PPTX through `Presentations`, using editable native elements when appropriate and source figure crops when the original visual carries the evidence.
6. Follow its rendered review and correction loop; inspect crop quality, slide density, layout bounds, source labels, notes, and figure readability.
7. Complete the package checks and rendered-slide review required by `Presentations`. Use the local XML audit only as a supplementary check.

OCR, full supplementary extraction, all-page high-resolution rendering, all-slide rendered QA, and long script files are opt-in or justified exceptions, not defaults.
