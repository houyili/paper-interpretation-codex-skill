---
name: paper-interpretation
description: Academic paper PDF full translation and grounded image-text interpretation workflow. Use when Codex needs to translate, interpret, dissect, or closely read a PDF paper into Chinese Markdown with paragraph-level full translation, preserved academic English terms, extracted figures/tables, translated captions, visual grounding, footnotes, appendix coverage, and hallucination checks.
---

# Paper Interpretation

Use this skill to turn academic PDFs into grounded Chinese Markdown reports. The default output is **paragraph-level full translation**, not a chapter summary. Preserve the original paper's structure, translate every substantive paragraph into Chinese, keep key academic terms in English, and place every figure/table next to the relevant translated text with a translated caption and grounding note.

## Non-Negotiable Output Contract

1. **Full translation, not summary**: each original paragraph maps to a Chinese paragraph. You may translate at paragraph level rather than word-for-word, but every claim, condition, number, caveat, and comparison in the source paragraph must be represented.
2. **Chinese-first with English terms**: write mostly in Chinese; preserve terms such as `Vision-Language-Action (VLA)`, `flow matching`, `mid-training`, `retargeting`, `DoF`, `SE(3)`, model names, benchmark names, datasets, equations, and variables.
3. **Structure fidelity**: keep the paper's order: Abstract, all numbered sections/subsections, limitations, acknowledgements, appendices, and unusual sections. Do not skip appendices unless the user explicitly narrows scope.
4. **Figures/tables are first-class content**: every figure/table must be kept, inserted near its first relevant discussion, and include:
   - Markdown image/table reference.
   - Original figure/table number.
   - Chinese translation of the original caption.
   - Grounding note: what the visual shows, key numbers/trends, and whether the image was visually verified.
5. **References default**: do not translate references one by one unless the user asks. Add a short note that References are preserved/omitted from full translation by default.
6. **Interpretation is secondary**: add `译后注` / `Grounding note` only after the translation. Do not replace translation paragraphs with bullet summaries.
7. **Exact quotes are optional and limited**: use direct English quotes only for especially important source sentences. Never put paraphrases in quote blocks.
8. **No interpretation-template masquerade**: output titles or sections such as `一句话总结`, `为什么读这篇`, `关键观察`, `核心主张`, or `全文翻译与论文解读` are warning signs. They are allowed only as small notes after the full translation has been written; they must never be the main body.

## Codex Tool Mapping

| Task | Use in Codex | Avoid |
|---|---|---|
| Inspect files/text | `rg`, `sed -n`, `wc`, `pdfinfo`, `exec_command` | Reading PDF bytes directly |
| Extract raw PDF text | `scripts/extract_pdf_text.py <pdf> /tmp/<paper>_full.txt` | Treating raw TXT blank lines as true paragraphs |
| Reconstruct paragraph backbone | `scripts/reconstruct_pdf_paragraphs.py <pdf> /tmp/<paper>_paragraphs.jsonl --md /tmp/<paper>_paragraphs.md` | Translating from raw TXT line breaks directly |
| Build full-paper context | `scripts/build_global_context.py /tmp/<paper>_paragraphs.jsonl --captions paper_figures/captions.json --out /tmp/<paper>_global_context.md` | Translating chunks before understanding the whole paper |
| Extract figures/tables as images | `scripts/extract_figures.py <pdf> <figures_dir> --debug` | Whole-page screenshots as figure substitutes |
| Extract ruled tables | `scripts/extract_tables.py <pdf> /tmp/<paper>_tables.md` | Hand-copying columns from raw PDF text |
| Extract footnotes | `scripts/extract_footnotes.py <pdf> /tmp/<paper>_footnotes.md` | Raw-text-only search |
| Visual verification | `view_image` for PNGs; optionally authorized `multi_agent_v1.spawn_agent` | Assuming extraction is correct |
| Write/edit Markdown | `apply_patch` for manual edits; safe helper scripts only when intended | `echo >`, heredocs, blind `sed -i` |
| MacDown-safe formulas | `scripts/render_math_images.py --markdown output.md --out output_MacDown.md` | Assuming `$$...$$` renders everywhere |
| Validate final Markdown | `scripts/validate_translation_output.py --markdown output.md --captions paper_figures/captions.json` | Manual count-only checks |
| Track writing tasks | `update_plan` checklist | Non-Codex task APIs |

Only use Codex subagents when the user explicitly authorizes subagents or parallel agent work. Otherwise perform visual checks in the parent context with `view_image`.

## Standard Workflow

Run these steps in order.

### 0. Analyze the PDF

```bash
python3 <skill_dir>/scripts/analyze_pdf.py paper.pdf
```

Record paper type, page count, caption count, top-level sections, appendix boundary, unusual sections, and suggested chunk size.

Treat analyzer output as an orientation aid, not ground truth. If the reported chapter count is suspicious, or if early sections such as Introduction/Method/Experiments are missing, continue with manual section reconstruction from the extracted text and page markers.

### 1. Extract Raw Text

```bash
python3 <skill_dir>/scripts/extract_pdf_text.py paper.pdf /tmp/paper_full.txt
```

Read the extracted text by page/line chunks with `sed -n` or locate anchors with `rg`. Do not read the PDF binary as text.

Raw TXT is a **search index**, not the translation backbone. PDF extraction often
turns one visual paragraph into multiple text paragraphs, especially when a
paragraph crosses a page boundary, column boundary, figure/table, or displayed
equation. Never use raw TXT blank lines as authoritative paragraph boundaries.

### 1b. Reconstruct Paragraphs

```bash
python3 <skill_dir>/scripts/reconstruct_pdf_paragraphs.py \
  paper.pdf /tmp/paper_paragraphs.jsonl \
  --md /tmp/paper_paragraphs.md
```

Use `/tmp/paper_paragraphs.md` as the default source for paragraph-level
translation. The JSONL/Markdown records include paragraph ids, page ranges,
paragraph type (`body`, `heading`, `caption`, `equation`, `list`, `code`), bbox
metadata, and join notes such as `cross_page_stitch`.

The reconstruction script is conservative, not magic. Before translating a
section, inspect the relevant paragraph ids and page ranges:

- If a paragraph is marked `cross_page_stitch`, check that the joined text reads
  naturally across the page boundary.
- If a body paragraph is suspiciously short, check the neighboring paragraph;
  raw PDF layout may have split it around a figure/table/equation.
- If a paragraph includes caption/table/code content inside body text, split it
  manually in the Markdown skeleton and record the correction in a grounding note.
- If reconstruction disagrees with the PDF visual layout, the PDF visual layout
  wins. Use page screenshots or `view_image` for the affected page/region.

### 2. Locate Section Boundaries

Use `rg -n` on both `/tmp/paper_full.txt` and `/tmp/paper_paragraphs.md` to locate:

- Abstract.
- Numbered sections/subsections.
- Limitations, Acknowledgements, Broader Impact, Ethics, Appendix.
- References boundary.
- `Figure N`, `Table N`, footnote anchors.

If `analyze_pdf.py` misses sections, derive boundaries from the extracted text and page markers.

Do a section sanity pass before writing: compare detected section numbers against the PDF page order. PDF text extraction can split headings across lines or pages, so do not rely only on a single `rg` pattern or the analyzer's `unique_chapters` count.

For each section/subsection, write down the paragraph id range you will translate
(for example `P0034-P0058`). These ids make it much easier to catch skipped,
duplicated, or accidentally summarized paragraphs.

### 2b. Build Global Paper Context

After paragraph reconstruction and section boundary detection, build a full-paper
context scaffold:

```bash
python3 <skill_dir>/scripts/build_global_context.py \
  /tmp/paper_paragraphs.jsonl \
  --captions paper_figures/captions.json \
  --out /tmp/paper_global_context.md
```

This file is a working artifact, not a replacement for reading. It gathers the
section map, figure/table map, candidate terminology, numeric claims, and
cross-page joins that need grounding. Before translating any section, read this
global context and update its "Required Full-Paper Understanding Notes" with the
paper's actual thesis, method, experimental story, limitations, and appendix
role. Translation must be guided by this full-paper understanding, not only by
the local paragraph chunk.

Use the global context to make stable decisions before drafting:

- Which English terms should be retained versus rendered into Chinese.
- Which abbreviations, variables, benchmarks, and model names must stay exact.
- What each section contributes to the paper's argument.
- Which figures/tables are central evidence versus appendix support.
- Which numbers are headline results, ablations, costs, or implementation details.
- Which appendix/code/prompt blocks should be preserved rather than paraphrased.

Update `/tmp/paper_global_context.md` when later sections change the
interpretation of earlier claims. If a local paragraph is ambiguous, resolve it
against the full-paper context and the PDF visual layout before translating.

### 3. Extract Figures and Table Images

```bash
python3 <skill_dir>/scripts/extract_figures.py paper.pdf paper_figures --debug
```

This writes PNGs plus `paper_figures/captions.json`. The extractor is caption-based and handles many figure/table layouts. Do not substitute full-page screenshots for extracted figure bodies unless the extractor fails and visual recovery is necessary.

If a table/figure crop touches a content edge, clips the first/last column, or includes unrelated prose, rerun extraction after fixing/expanding the crop or create a clearly labeled visual fallback. Do not mark the image as verified until the core visual content is complete.

### 4. Extract Tables

```bash
python3 <skill_dir>/scripts/extract_tables.py paper.pdf /tmp/paper_tables.md
```

If it returns zero tables but the paper has booktabs-style tables, use the `Table_*.png` outputs from `extract_figures.py` and visual OCR fallback described in `references/vision_verification.md`.

If `extract_tables.py` returns `0` while `captions.json` contains `Table_*`, this is a fallback trigger, not a clean pass. Preserve every table as an image, visually verify the crop, and transcribe only the cells that are needed for grounding or user scope.

### 5. Extract Footnotes

```bash
python3 <skill_dir>/scripts/extract_footnotes.py paper.pdf /tmp/paper_footnotes.md
```

Place substantive footnotes near the translated section they modify. If anchor mapping is uncertain, say so rather than guessing.

Filter false positives: table cells, chart labels, legends, and page artifacts may be detected as footnotes. Only place footnotes that have a real anchor in body text, or explicitly mark uncertain anchors.

### 6. Verify Figures

Open `captions.json`, then visually verify extracted PNGs.

- `<= 10` figures/tables: inspect all with `view_image`.
- `> 10`: inspect a representative set including first figure, final appendix figure, all tables, dense charts, multi-panel figures, and any suspicious debug cases. If the user has explicitly authorized subagents, use Codex subagents for parallel verification.

Each figure used in the final Markdown needs a grounding note: `视觉校验：通过 / 有疑点 / 需重抽`.

For tables, check left and right edges specifically: the first method/model column and final metric column must be visible. For multi-panel figures, check all panel titles and legends are visible. A file count match is not enough.

### 7. Create Translation Skeleton

Create the Markdown skeleton from `templates/interpretation_template.md`, adapted to the paper's actual structure. Include placeholders for every section, subsection, appendix, and figure/table insertion point.

Use `update_plan` to track all translation chunks. Chunk by section/subsection; if a source range exceeds 5-8 pages, split it.

Base the skeleton on reconstructed paragraph ids, not raw TXT blank lines. Add
lightweight source comments when useful:

```markdown
<!-- source: P0034-P0041; pages: 2-3 -->
```

These comments are especially useful for long appendices and for sections where
paragraphs cross pages.

Also add a short "全文理解依据 / Global Context" note in the metadata or opening
rules, pointing to `/tmp/paper_global_context.md` or the local context artifact
used for the run. Do not include a high-level summary as a substitute for the
translation body.

### 8. Translate Paragraph by Paragraph

For each chunk:

1. Re-read `/tmp/paper_global_context.md` for terminology, section role, figure/table placement, and headline claims.
2. Re-read the corresponding source paragraphs from `/tmp/paper_paragraphs.md`; use `/tmp/paper_full.txt` only as a search fallback.
3. Translate every substantive reconstructed source paragraph into Chinese, preserving key English terms.
4. Preserve equations, variables, lists, task definitions, numbered findings, conditions, and caveats.
5. Insert figures/tables immediately after the translated paragraph that first discusses them.
6. Translate captions and add a grounding note.
7. Add optional `译后注` only after the translation when it helps a Chinese AI researcher understand context.
8. Run the hallucination checklist before moving on.

Use `templates/sub_section_template.md` for the default section shape.

Do not blindly paste equations from extracted text. Reconstruct displayed equations from PDF visual context when text extraction breaks line layout, superscripts/subscripts, matrix shapes, or equation numbers. Preserve equation tags such as `(1)` / `\tag{1}` and keep variable ownership intact.

Paragraph reconstruction does not replace semantic checking. Before finishing a
chunk, compare the translated paragraph count with the source paragraph ids you
intended to cover. If you intentionally merge two short source paragraphs into
one Chinese paragraph, make sure no claims, caveats, equations, or numbers were
lost.

Full-paper understanding also does not permit compression. Do not use the global
context to summarize away paragraphs. Use it to keep local translation faithful
to the paper's overall argument, terminology, and evidence chain.

If the user will open the Markdown in MacDown, do not rely solely on `$$...$$`
rendering. MacDown may display raw TeX when math rendering is disabled. Keep the
LaTeX source in the canonical Markdown, then generate a MacDown-safe copy with
local equation PNGs:

```bash
python3 <skill_dir>/scripts/render_math_images.py \
  --markdown output.md \
  --out output_MacDown.md \
  --equation-dir equations
```

Use the MacDown-safe file for user preview when formula rendering is uncertain.

### 9. Chapter-Level Checks

After each chapter or appendix:

```bash
rg -n '^###|^####|Figure|Table|视觉校验|译后注' output.md
rg -n '\d+(\.\d+)?%|\d{3,}|R\^2|R²' output.md
```

For 3-5 important numbers, locate the source sentence in `/tmp/paper_full.txt` and confirm number, owner, condition, and range.

### 10. Final Acceptance Checks

Before delivery:

- Every detected figure/table is either included with translated caption or explicitly marked as intentionally omitted with reason.
- All image paths exist relative to the Markdown file.
- Every table crop has visible first/last columns; every figure crop has visible panels/axes/legends needed by its caption.
- If table OCR returned zero but table captions exist, the final Markdown records image fallback and visual status.
- Abstract, main text, acknowledgement, appendix, and unusual sections are covered.
- A full-paper context pass was created and used before chunk translation.
- Terminology, abbreviation, benchmark, model, dataset, and variable decisions are consistent with the global context.
- Translation coverage was checked against reconstructed paragraph ids, not raw TXT blank lines.
- Cross-page paragraph joins and suspiciously short paragraphs were spot-checked against the PDF visual layout.
- Section coverage was checked against page order, not only analyzer output.
- The output is not an old interpretation template: run `rg -n '一句话总结|为什么读这篇|关键观察|核心主张|全文翻译与论文解读|章节总结' output.md` and confirm any hit is secondary, not replacing translated paragraphs.
- References are handled according to user scope.
- Key academic terms are preserved in English.
- Display equations were checked against PDF visual layout when extraction was broken.
- Claims do not strengthen correlation into causation.
- The Markdown opens cleanly in MacDown or another Markdown previewer when relative paths are preserved.

Run the mechanical validator when a `captions.json` manifest exists:

```bash
python3 <skill_dir>/scripts/validate_translation_output.py \
  --markdown output.md \
  --captions paper_figures/captions.json
```

Treat validator failures as blockers. It checks image coverage, caption markers, grounding notes, paragraph-count markers when present, and common PDF math/text extraction artifacts such as `O(L2)` or broken summation layout. It does not replace semantic reading.

## Resource Navigation

| Need | File |
|---|---|
| Output skeleton | `templates/interpretation_template.md` |
| Section translation structure | `templates/sub_section_template.md` |
| Hallucination checks | `references/hallucination_checklist.md` |
| Visual verification / OCR fallback | `references/vision_verification.md` |
| Figure extractor debugging | `references/extractor_debug.md` |
| Caption regex variants | `references/regex_patterns.md` |
| Cross-paper benchmark comparison | `references/cross_paper_comparison.md` |
| Output validation | `scripts/validate_translation_output.py` |
| MacDown-safe equation images | `scripts/render_math_images.py` |
| Paragraph reconstruction | `scripts/reconstruct_pdf_paragraphs.py` |
| Full-paper context scaffold | `scripts/build_global_context.py` |

## Red Lines

- Do not summarize instead of translating.
- Do not deliver a "全文翻译与论文解读" / "一句话总结" style interpretation report as the default full-translation output.
- Do not omit figures/tables or captions.
- Do not place all figures at the end.
- Do not invent captions, numbers, or missing table cells.
- Do not paraphrase text inside `> "..."` quote blocks.
- Do not skip appendix, limitations, acknowledgement, or unusual sections.
- Do not use subagents unless the user explicitly authorized them.
- Do not mutate an existing Markdown with `update_md_references.py` before running dry-run or confirming the target.
