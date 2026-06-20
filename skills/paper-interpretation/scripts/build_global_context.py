#!/usr/bin/env python3
"""Build a global context scaffold before paragraph-level translation.

Paragraph reconstruction prevents boundary mistakes, but good translation also
requires whole-paper understanding: consistent terminology, claim ownership,
section dependencies, figure/table placement, and appendix scope. This helper
turns reconstructed paragraph JSONL plus optional captions.json into a compact
Markdown scaffold the agent must read and maintain before translating chunks.

Usage:
    python3 build_global_context.py /tmp/paper_paragraphs.jsonl \
        --captions paper_figures/captions.json \
        --out /tmp/paper_global_context.md
"""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any


TERM_RE = re.compile(
    r"\b(?:"
    r"[A-Z][A-Za-z]+(?:-[A-Za-z]+)*(?:\s+[A-Z][A-Za-z]+(?:-[A-Za-z]+)*)+|"
    r"[A-Z]{2,}(?:-[A-Za-z0-9]+)*|"
    r"[a-z]+(?:-[a-z]+){1,3}"
    r")\b"
)

NUMBER_RE = re.compile(
    r"(?:\b\d+(?:\.\d+)?\s?%|\b\d+(?:\.\d+)?(?:[kKmMbB])?\b|USD\s?\$?\d[\d,]*(?:\.\d+)?)"
)

SECTION_NUM_RE = re.compile(r"^(?:(\d+(?:\.\d+)*)|([A-Z](?:\.\d+)*))\s+(.+)$")
REFERENCE_RE = re.compile(r"REFERENCES?$", re.IGNORECASE)

STOP_TERMS = {
    "Published",
    "Figure",
    "Table",
    "Algorithm",
    "Appendix",
    "References",
    "Abstract",
    "Introduction",
    "Related Work",
    "Conclusion",
}


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def without_references(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Drop reference-list records while keeping later appendix records."""
    ref_start = None
    appendix_start = None
    for idx, row in enumerate(rows):
        if row.get("type") == "heading" and REFERENCE_RE.match(row.get("text", "").strip()):
            ref_start = idx
        if ref_start is not None and row.get("type") == "heading" and row.get("text", "").strip().upper() == "APPENDIX":
            appendix_start = idx
            break
    if ref_start is None:
        return rows
    if appendix_start is None:
        return rows[:ref_start]
    return rows[:ref_start] + rows[appendix_start:]


def short(text: str, limit: int = 260) -> str:
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


def first_body(rows: list[dict[str, Any]], after_heading: str) -> dict[str, Any] | None:
    seen = False
    for row in rows:
        if row.get("type") == "heading" and after_heading.lower() in row.get("text", "").lower():
            seen = True
            continue
        if seen and row.get("type") == "body":
            return row
    return None


def section_map(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    sections = []
    for row in rows:
        if row.get("type") != "heading":
            continue
        text = row.get("text", "")
        if len(text) > 140:
            continue
        if text.isupper() or SECTION_NUM_RE.match(text) or text.lower() in {"abstract", "appendix"}:
            sections.append(
                {
                    "id": row.get("id"),
                    "pages": row.get("pages", []),
                    "title": text,
                }
            )
    return sections


def caption_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [r for r in rows if r.get("type") == "caption"]


def terms(rows: list[dict[str, Any]], top_n: int = 80) -> list[tuple[str, int]]:
    counts: Counter[str] = Counter()
    for row in rows:
        if row.get("type") not in {"body", "heading", "caption", "list"}:
            continue
        for match in TERM_RE.finditer(row.get("text", "")):
            term = match.group(0).strip()
            if len(term) < 4 or term in STOP_TERMS:
                continue
            if term.lower().startswith(("the ", "this ", "that ")):
                continue
            counts[term] += 1
    return counts.most_common(top_n)


def numeric_claims(rows: list[dict[str, Any]], limit: int = 80) -> list[dict[str, str]]:
    claims = []
    for row in rows:
        if row.get("type") not in {"body", "caption", "list"}:
            continue
        text = row.get("text", "")
        nums = NUMBER_RE.findall(text)
        if nums:
            claims.append(
                {
                    "id": row.get("id", ""),
                    "pages": ",".join(str(p) for p in row.get("pages", [])),
                    "numbers": ", ".join(nums[:8]),
                    "text": short(text, 320),
                }
            )
        if len(claims) >= limit:
            break
    return claims


def stitched(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [r for r in rows if any("stitch" in n for n in r.get("join_notes", []))]


def load_captions(path: Path | None) -> list[dict[str, Any]]:
    if not path or not path.exists():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    return data.get("figures", [])


def write_context(rows: list[dict[str, Any]], captions: list[dict[str, Any]], out: Path, source: Path) -> None:
    context_rows = without_references(rows)
    title = next((r["text"] for r in context_rows if r.get("type") == "heading" and len(r.get("text", "")) > 10), "")
    abstract = first_body(context_rows, "ABSTRACT")
    intro = first_body(context_rows, "INTRODUCTION")
    sections = section_map(context_rows)
    caps = caption_rows(context_rows)
    stitch_rows = stitched(context_rows)
    term_list = terms(context_rows)
    claims = numeric_claims(context_rows)

    lines: list[str] = []
    lines.extend(
        [
            f"# Global Paper Context: {title or source.name}",
            "",
            f"- source_paragraphs: `{source}`",
            f"- total_records: {len(rows)}",
            f"- context_records_excluding_references: {len(context_rows)}",
            f"- translatable_records: {sum(1 for r in context_rows if r.get('type') in {'body', 'heading', 'caption', 'list', 'footnote'})}",
            f"- detected_captions_in_paragraphs: {len(caps)}",
            f"- detected_captions_in_manifest: {len(captions)}",
            f"- stitched_records_to_spot_check: {len(stitch_rows)}",
            "",
            "## Required Full-Paper Understanding Notes",
            "",
            "Fill this section before translating chunks. Keep it short but concrete.",
            "",
            "- Core thesis / contribution:",
            "- What problem the paper is solving:",
            "- Method / system pipeline:",
            "- Main experiments and baselines:",
            "- Main results and caveats:",
            "- Limitations / safety / ethics:",
            "- Appendix material that changes interpretation of the main text:",
            "",
            "## Abstract / Intro Anchors",
            "",
        ]
    )
    if abstract:
        lines.append(f"- Abstract anchor `{abstract['id']}` pages={','.join(map(str, abstract.get('pages', [])))}: {short(abstract['text'], 700)}")
    if intro:
        lines.append(f"- Introduction anchor `{intro['id']}` pages={','.join(map(str, intro.get('pages', [])))}: {short(intro['text'], 700)}")

    lines.extend(["", "## Section Map", ""])
    for sec in sections:
        pages = ",".join(str(p) for p in sec["pages"])
        lines.append(f"- `{sec['id']}` pages={pages}: {sec['title']}")

    lines.extend(["", "## Figure/Table Map", ""])
    if captions:
        for fig in captions:
            lines.append(
                f"- {fig.get('id', '')} page={fig.get('caption_page', '?')} file={fig.get('filename', '')}: "
                f"{short(fig.get('caption_text', ''), 320)}"
            )
    else:
        for cap in caps:
            lines.append(f"- `{cap['id']}` pages={','.join(map(str, cap.get('pages', [])))}: {short(cap['text'], 320)}")

    lines.extend(["", "## Terminology Decisions", ""])
    lines.append("Use this table to keep Chinese terms and retained English terms consistent.")
    lines.append("")
    lines.append("| Source term | Count | Chinese rendering / keep English | Notes |")
    lines.append("|---|---:|---|---|")
    for term, count in term_list[:60]:
        lines.append(f"| {term} | {count} |  |  |")

    lines.extend(["", "## Numeric Claims To Ground", ""])
    lines.append("| Paragraph | Pages | Numbers | Source sentence preview |")
    lines.append("|---|---|---|---|")
    for claim in claims:
        preview = claim["text"].replace("|", "\\|")
        lines.append(f"| `{claim['id']}` | {claim['pages']} | {claim['numbers']} | {preview} |")

    lines.extend(["", "## Cross-Page / Suspicious Joins", ""])
    if stitch_rows:
        lines.append("| Paragraph | Pages | Join notes | Preview |")
        lines.append("|---|---|---|---|")
        for row in stitch_rows[:80]:
            preview = short(row.get("text", ""), 260).replace("|", "\\|")
            notes = ", ".join(row.get("join_notes", []))
            pages = ",".join(str(p) for p in row.get("pages", []))
            lines.append(f"| `{row.get('id')}` | {pages} | {notes} | {preview} |")
    else:
        lines.append("- None detected.")

    lines.extend(
        [
            "",
            "## Translation Strategy Checklist",
            "",
            "- [ ] Read this global context before translating any section.",
            "- [ ] Resolve terminology decisions before drafting Section 1.",
            "- [ ] Place each figure/table near the first paragraph that uses it.",
            "- [ ] For every numeric claim translated, confirm owner, condition, and comparison direction.",
            "- [ ] Revisit this file after each major section and update decisions if later sections change interpretation.",
            "- [ ] Before final delivery, check that the translation does not contradict this global context.",
            "",
        ]
    )
    out.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("paragraphs_jsonl")
    parser.add_argument("--captions", help="Optional captions.json")
    parser.add_argument("--out", required=True, help="Output global context Markdown")
    args = parser.parse_args()

    paragraphs = Path(args.paragraphs_jsonl)
    rows = load_jsonl(paragraphs)
    captions = load_captions(Path(args.captions) if args.captions else None)
    write_context(rows, captions, Path(args.out), paragraphs)
    print(f"wrote_global_context: {args.out}")
    print(f"records: {len(rows)}")
    print(f"captions_manifest: {len(captions)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
