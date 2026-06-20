# Codex Paper Interpretation Skill

A Codex skill for full, grounded Chinese translation of academic PDF papers.

The skill is designed for paragraph-level translation rather than chapter-level
summary. It reconstructs PDF paragraphs, builds a full-paper context scaffold,
extracts figures/tables/footnotes, verifies image crops, translates captions,
and validates final Markdown outputs for common PDF extraction mistakes.

## Features

- Paragraph-level full translation into Chinese, while preserving key academic
  terms in English.
- Reconstructed paragraph backbone to reduce line-wrap and cross-page paragraph
  breakage from raw PDF text extraction.
- Full-paper context scaffold before local chunk translation.
- Figure/table extraction with caption manifests and visual grounding workflow.
- Table image fallback when ruled-table extraction fails.
- Footnote extraction and placement guidance.
- MacDown-compatible equation image generation for Markdown previewers that do
  not render display math reliably.
- Mechanical validator for image coverage, caption markers, grounding notes,
  paragraph coverage markers, and suspicious math/text extraction artifacts.

## Repository Layout

```text
.
├── skills/
│   └── paper-interpretation/
│       ├── SKILL.md
│       ├── agents/openai.yaml
│       ├── references/
│       ├── scripts/
│       └── templates/
├── install.sh
├── requirements.txt
└── README.md
```

The actual Codex skill lives at `skills/paper-interpretation`.

## Install

### Option 1: Ask Codex to install from GitHub

In Codex, ask:

```text
Install the paper-interpretation skill from
https://github.com/houyili/paper-interpretation-codex-skill/tree/main/skills/paper-interpretation
```

Codex should use the built-in `skill-installer` workflow. Restart Codex after
installation so the skill is discovered.

### Option 2: Manual clone

```bash
git clone https://github.com/houyili/paper-interpretation-codex-skill.git
cd paper-interpretation-codex-skill
./install.sh
```

If a previous copy already exists:

```bash
./install.sh --force
```

The script installs into `${CODEX_HOME:-$HOME/.codex}/skills/paper-interpretation`.

## Python Dependencies

Install the helper script dependencies on each machine that will run extraction:

```bash
python3 -m pip install -r requirements.txt
```

Optional system tools:

- `pdflatex` for `render_math_images.py` MacDown-safe equation PNGs.
- Poppler tools such as `pdfinfo`/`pdftoppm` are useful for PDF inspection and
  page rendering workflows.

## Usage

After installing and restarting Codex, ask something like:

```text
Use the paper-interpretation skill to fully translate /path/to/paper.pdf into
Chinese Markdown with figures, captions, grounding notes, and MacDown-safe math.
```

The default output contract is:

- Translate Abstract, main text, limitations, acknowledgements, appendices, and
  all substantive paragraphs.
- Keep key academic terms, variables, benchmark names, model names, equations,
  and dataset names in English or mixed Chinese/English.
- Preserve every detected figure/table near its first relevant discussion.
- Translate every included figure/table caption.
- Add a grounding note and visual verification status for each figure/table.
- Do not translate references entry by entry unless explicitly requested.

## Validation

Basic local checks:

```bash
python3 ~/.codex/skills/.system/skill-creator/scripts/quick_validate.py \
  skills/paper-interpretation

python3 -m py_compile skills/paper-interpretation/scripts/*.py
```

For a real paper run, follow the workflow in `skills/paper-interpretation/SKILL.md`
and finish with:

```bash
python3 skills/paper-interpretation/scripts/validate_translation_output.py \
  --markdown output.md \
  --captions paper_figures/captions.json
```

## License

MIT. See `LICENSE`.
