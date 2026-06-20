# Vision Verification in Codex

Use this reference after `extract_figures.py` writes PNGs and `captions.json`.
The goal is to verify that every figure/table image is correctly extracted and grounded before it appears in the translation.

## Core Rule

Codex can inspect local PNGs with `view_image`. Use that as the default. Use `multi_agent_v1.spawn_agent` only when the user has explicitly authorized subagents or parallel agent work; Codex policy does not allow spawning merely because a workflow mentions subagents.

## Inputs

- Figure directory: `<paper>_figures/`
- Manifest: `<paper>_figures/captions.json`
- Extracted PNGs: `Figure_*.png`, `Table_*.png`

`captions.json` is the source of truth for figure id, filename, caption page, source pages, and original caption text.

## Mode 1: Figure/Table Crop Verification

### When

Run after figure extraction and before writing final Markdown.

- `<= 10` images: inspect all with `view_image`.
- `> 10` images: inspect a representative set: first figure, all tables, dense charts, multi-panel figures, appendix figures, and any debug-suspicious outputs.
- Authorized subagents: use one bounded subagent per small batch of images.

### Check

For each image:

- No unrelated body paragraph at top/bottom.
- No next section heading or page footer included.
- No large blank crop.
- Axes, legends, panel labels, key numbers, and visual content are present.
- Tables: first identifier/method/model column and final metric column are visible.
- Tables: no neighboring prose column is included in wrap-table layouts.
- Edge check: if content is flush against the left/right crop boundary, inspect the full page or rerun with a wider crop.
- Prompt/template figures: check both left and right edges and verify whether the prompt body starts on a previous page after another caption.
- Missing caption text in the PNG is not a defect; captions are translated from `captions.json`.

### Status Labels

- `OK`: crop matches caption and is visually usable.
- `SUSPICIOUS`: likely usable but needs manual note or recheck.
- `BROKEN`: wrong crop, blank crop, missing core panel, or includes unrelated text.

`OK` requires visual completeness, not just a matching filename. A `captions.json`
count match can still hide cropped tables; inspect suspicious table edges.

For prompt/template figures, count matches are especially weak evidence. The
crop may contain a valid-looking prompt while clipping the left margin, or it may
capture the wrong post-caption region. Render the full source page when a prompt
image begins or ends abruptly.

### Parent-Agent Output Note

Record a short note for final Markdown:

```markdown
**视觉校验 / Grounding note**：OK。图像裁切完整；左侧展示 X，右侧展示 Y；关键趋势是 ...
```

## Mode 2: Booktabs Table OCR Fallback

### When

Use when `extract_tables.py` returns `0` but the PDF has visual tables. `extract_figures.py` usually extracts those as `Table_N.png`.

If `extract_tables.py` returns `0` and `captions.json` contains `Table_*`, treat
the tables as image-fallback required. Record that in output metadata or notes.

### Parent-Agent Path

1. Read `captions.json` and locate `Table N`.
2. Inspect `Table_N.png` with `view_image`.
3. Confirm the first and last columns are visible. If a column is clipped, rerun extraction or render the relevant PDF page and crop wider.
4. Transcribe the table into Markdown only when useful for the requested scope; otherwise keep the image and ground key cells in prose.
5. Preserve bold/best markers when visible.
6. Add caption translation and grounding note.

### Authorized Subagent Prompt Shape

When the user explicitly authorized subagents, spawn a bounded worker with only the table image path and caption text:

```text
Task: Convert this table image into a Markdown table.

Inputs:
- Image: /absolute/path/to/Table_N.png
- Original caption: "Table N: ..."

Return only:
1. A Markdown table.
2. A one-sentence uncertainty note if any cells are unreadable.

Do not summarize the table and do not invent unreadable cells.
```

The parent agent must still verify important numbers against the source text or image.

## Mode 3: Dense Multi-Panel Figure Grounding

### When

Use for charts with many panels, bars, or curves where the translation needs exact visual grounding.

### Procedure

1. Inspect the full image with `view_image`.
2. Identify panel count and panel titles.
3. Extract only the numbers/trends that the final translation will discuss.
4. Cross-check key numbers with PDF text when available.
5. If the image is too dense, mark uncertain values explicitly rather than over-reading.

### Authorized Subagent Prompt Shape

```text
Task: Deep-read one multi-panel figure for grounding.

Inputs:
- Image: /absolute/path/to/Figure_X.png
- Original caption: "Figure X: ..."

Return a compact Markdown table with:
- Panel title
- Visual quantity read from the figure
- Confidence: high / medium / low

Do not infer values that are not visible.
```

## Mode 4: Footnote Anchor Localization

`extract_footnotes.py` extracts likely footnote text but may not map every footnote to its body anchor. If anchor placement matters:

1. Render the relevant PDF page to PNG with PyMuPDF or `pdftoppm`.
2. Inspect the page image with `view_image`.
3. Locate the superscript number and surrounding sentence.
4. If uncertain, place the footnote after the nearest translated paragraph and label the anchor as uncertain.

## Defensive Parsing for Subagent Results

If subagents are used, require compact JSON or Markdown. Still parse defensively: subagents may add preambles. Treat their outputs as assistance, not final truth.

```python
import json, re

def parse_last_json_object(text):
    matches = re.findall(r'\{[^{}]*\}', text)
    return json.loads(matches[-1]) if matches else None
```

## Anti-Patterns

- Do not inspect 100+ images in the main context unless unavoidable.
- Do not spawn Codex subagents without explicit user authorization.
- Do not ask a subagent to translate pure text captions; the parent agent can translate captions while writing.
- Do not let missing caption text inside the PNG count as extraction failure.
- Do not OCR a visual table and skip number verification for key claims.
- Do not place figures at the end of the document.
- Do not mark a table verified when its first column is clipped, even if the numeric columns are readable.
- Do not fix a clipped wrap-table by expanding so far that unrelated body prose enters the crop; use the table row/header extents.
