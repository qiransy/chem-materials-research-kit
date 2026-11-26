# Toolchain policy and fast path

## Toolchain policy

Use the user's chosen authoring workflow when available. Otherwise select one available backend that can create or edit PPTX, such as `Presentations`, `ppt-master` if installed, or an equivalent presentation tool. This skill supplies the paper-specific narrative, figure choices, and speaker notes.

Use the selected backend's export and review procedures. Preserve editable text, shapes, and connectors where supported, and identify retained source figures. Inspect the deck in the available renderer, or record the scope of structural checks when a renderer is unavailable.

If the environment can read the paper but cannot create a PPTX, produce the slide-by-slide script with source-figure locations and speaker notes. Respect the user's template and use available document or PDF tools for the source.

## Default fast path

For a normal selectable-text paper PDF, run the shortest complete path:

1. Extract metadata, abstract, headings, figure legends, and table captions with an available PDF reader.
2. Identify the paper type, argument, and candidate figures before rendering high-resolution pages.
3. Render low-resolution contact sheets only when figure locations are unclear.
4. Render high-resolution images only for selected figure/table pages and crop only assets that will appear in the deck.
5. Build or edit the deck with the selected backend, using editable elements and source figure crops as appropriate.
6. Inspect crop quality, slide density, layout bounds, source labels, notes, and figure readability.
7. Complete the backend's package and rendered review checks. The bundled XML audit provides supplementary structural checks.

OCR, full supplementary extraction, all-page high-resolution rendering, all-slide rendered QA, and long script files are opt-in or justified exceptions, not defaults.
