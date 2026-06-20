#!/usr/bin/env python3
"""Reconstruct logical paragraphs from PDF layout blocks.

This script is a companion to extract_pdf_text.py. The raw text extractor is
useful for search, but PDF line breaks and page breaks are not paragraph
boundaries. This script uses PyMuPDF layout blocks, line bboxes, indentation,
font size, repeated header/footer filtering, and conservative cross-page
stitching to produce paragraph records suitable as the translation backbone.

Usage:
    python3 reconstruct_pdf_paragraphs.py paper.pdf /tmp/paper_paragraphs.jsonl \
        --md /tmp/paper_paragraphs.md

Output JSONL fields:
    id, type, pages, bbox_by_page, text, join_notes, source_blocks
"""

from __future__ import annotations

import argparse
import json
import math
import re
import statistics
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import fitz


SECTION_RE = re.compile(
    r"^(?:"
    r"\d+(?:\.\d+)*\s+[A-Z][A-Za-z0-9 ,:;()\-\/&]+|"
    r"[A-Z]\.?\d*(?:\.\d+)*\s+[A-Z][A-Za-z0-9 ,:;()\-\/&]+|"
    r"(?:ABSTRACT|INTRODUCTION|RELATED WORK|CONCLUSION|LIMITATIONS|ACKNOWLEDGMENTS?|"
    r"REFERENCES|APPENDIX|ETHICS STATEMENT|REPRODUCIBILITY STATEMENT)"
    r")$"
)
CAPTION_RE = re.compile(r"^(?:Figure|Fig\.|Table|Algorithm|图|表)\s*\d+", re.IGNORECASE)
LIST_RE = re.compile(r"^(?:[-*•]\s+|\(?[a-zA-Z0-9ivxIVX]{1,4}\)?[.)]\s+)")
PAGE_NUM_RE = re.compile(r"^\d{1,4}$")
MATHY_RE = re.compile(r"[=+*∑ΣΠπ≤≥≈≠→←↦∞∈∉∪∩√∂∇]")
SENTENCE_END_RE = re.compile(r"[.!?。！？][\"')\]]?$")
CODE_RE = re.compile(
    r"^(?:"
    r"diff --git|index [0-9a-f]|@@ |--- |\+\+\+ |[+][^+]|-[^-]|"
    r"def |class |return |import |from |if |elif |else:|for |while |try:|except |"
    r"\{|\}|\]|\)|```|# |//"
    r")"
)

KEEP_HYPHEN_PREFIXES = {
    "self",
    "open",
    "long",
    "short",
    "cross",
    "multi",
    "single",
    "zero",
    "few",
    "fine",
    "co",
    "post",
    "pre",
    "non",
    "state",
    "task",
    "code",
    "codebase",
    "human",
    "agent",
    "model",
    "benchmark",
}


def norm_space(text: str) -> str:
    text = text.replace("\x00", "")
    return re.sub(r"\s+", " ", text).strip()


def line_text(line: dict[str, Any]) -> str:
    parts = []
    for span in line.get("spans", []):
        txt = span.get("text", "")
        if txt:
            parts.append(txt)
    return "".join(parts).strip()


def span_sizes(line: dict[str, Any]) -> list[float]:
    return [float(s.get("size", 0.0)) for s in line.get("spans", []) if s.get("text", "").strip()]


def span_fonts(line: dict[str, Any]) -> list[str]:
    return [str(s.get("font", "")) for s in line.get("spans", []) if s.get("text", "").strip()]


def weighted_body_size(lines: list[dict[str, Any]]) -> float:
    counts: Counter[float] = Counter()
    for ln in lines:
        txt = ln["text"]
        if not txt:
            continue
        for span in ln["raw"].get("spans", []):
            stext = span.get("text", "")
            if not stext.strip():
                continue
            size = round(float(span.get("size", 0.0)) * 2) / 2
            if 5.0 <= size <= 16.0:
                counts[size] += max(1, len(stext.strip()))
    if not counts:
        return 10.0
    return counts.most_common(1)[0][0]


def collect_lines(doc: fitz.Document) -> list[dict[str, Any]]:
    all_lines: list[dict[str, Any]] = []
    for page_index in range(doc.page_count):
        page = doc[page_index]
        page_rect = page.rect
        data = page.get_text("dict", sort=False)
        for block_index, block in enumerate(data.get("blocks", [])):
            if block.get("type") != 0:
                continue
            for line_index, raw_line in enumerate(block.get("lines", [])):
                txt = norm_space(line_text(raw_line))
                if not txt:
                    continue
                bbox = tuple(float(v) for v in raw_line.get("bbox", block.get("bbox", (0, 0, 0, 0))))
                sizes = span_sizes(raw_line)
                fonts = span_fonts(raw_line)
                all_lines.append(
                    {
                        "page": page_index + 1,
                        "page_width": float(page_rect.width),
                        "page_height": float(page_rect.height),
                        "block": block_index,
                        "line": line_index,
                        "bbox": bbox,
                        "text": txt,
                        "size": statistics.median(sizes) if sizes else 0.0,
                        "fonts": fonts,
                        "raw": raw_line,
                    }
                )
    return all_lines


def repeated_header_footer_keys(lines: list[dict[str, Any]]) -> set[tuple[int, str]]:
    """Return (page, text) keys that are likely repeated headers/footers."""
    occurrences: defaultdict[str, list[dict[str, Any]]] = defaultdict(list)
    for ln in lines:
        x0, y0, x1, y1 = ln["bbox"]
        page_h = ln["page_height"]
        if y1 < page_h * 0.10 or y0 > page_h * 0.90:
            occurrences[ln["text"].lower()].append(ln)

    repeated: set[tuple[int, str]] = set()
    for text, items in occurrences.items():
        pages = {it["page"] for it in items}
        if len(pages) >= 3:
            for it in items:
                repeated.add((it["page"], it["text"]))
    return repeated


def is_page_artifact(ln: dict[str, Any], repeated: set[tuple[int, str]]) -> bool:
    text = ln["text"]
    x0, y0, x1, y1 = ln["bbox"]
    page_h = ln["page_height"]
    if (ln["page"], text) in repeated:
        return True
    if PAGE_NUM_RE.match(text) and (y0 > page_h * 0.88 or y1 < page_h * 0.12):
        return True
    return False


def line_kind(ln: dict[str, Any], body_size: float) -> str:
    text = ln["text"]
    size = ln["size"] or body_size
    x0, y0, x1, y1 = ln["bbox"]
    width = max(1.0, x1 - x0)
    page_w = ln["page_width"]
    page_h = ln["page_height"]

    if CAPTION_RE.match(text):
        return "caption"
    if y0 > page_h * 0.80 and size <= body_size - 1.0 and re.match(r"^[*†‡§]|\d+\s", text):
        return "footnote"
    if "://" in text:
        return "body"
    if SECTION_RE.match(text) and (size >= body_size - 0.5 or text.isupper()):
        return "heading"
    if LIST_RE.match(text):
        return "list"
    if CODE_RE.match(text) or any(ch in text for ch in ("=>", "::", "\\n", "```")):
        return "code"
    if any("Mono" in f or "Courier" in f or "Code" in f for f in ln["fonts"]):
        return "code"
    math_density = len(MATHY_RE.findall(text)) / max(1, len(text))
    centered = abs(((x0 + x1) / 2.0) - (page_w / 2.0)) < page_w * 0.12
    if math_density > 0.08 and (centered or width < page_w * 0.65):
        return "equation"
    if size >= body_size + 2.0 and len(text) < 90:
        return "heading"
    # Short isolated text near figures/diagrams should not become a body paragraph.
    if len(text) < 90 and width < page_w * 0.45 and not SENTENCE_END_RE.search(text):
        return "figure_text"
    return "body"


def block_records(lines: list[dict[str, Any]], body_size: float) -> list[dict[str, Any]]:
    grouped: defaultdict[tuple[int, int], list[dict[str, Any]]] = defaultdict(list)
    for ln in lines:
        grouped[(ln["page"], ln["block"])].append(ln)

    records = []
    for (page, block), blines in grouped.items():
        blines = sorted(blines, key=lambda x: (x["bbox"][1], x["bbox"][0], x["line"]))
        runs: list[list[dict[str, Any]]] = []
        current: list[dict[str, Any]] = []
        current_kind: str | None = None
        prev_line: dict[str, Any] | None = None
        for ln in blines:
            kind = line_kind(ln, body_size)
            hard_kind = kind in {"heading", "caption", "equation", "code", "footnote", "figure_text"}
            prev_hard = current_kind in {"heading", "caption", "equation", "code", "footnote", "figure_text"}
            gap = 0.0
            if prev_line is not None:
                gap = ln["bbox"][1] - prev_line["bbox"][3]
            large_gap = gap > max(10.0, body_size * 1.8)
            caption_continuation = current_kind == "caption" and kind in {"body", "caption"} and not large_gap
            footnote_continuation = current_kind == "footnote" and kind in {"body", "footnote"} and not large_gap
            code_continuation = current_kind == "code" and kind == "code" and not large_gap
            if (
                current
                and not caption_continuation
                and not footnote_continuation
                and not code_continuation
                and (hard_kind or prev_hard or large_gap)
            ):
                runs.append(current)
                current = []
                current_kind = None
            current.append(ln)
            current_kind = kind if current_kind is None else current_kind
            prev_line = ln
        if current:
            runs.append(current)

        for run_index, run in enumerate(runs):
            kinds = [line_kind(ln, body_size) for ln in run]
            kind = Counter(kinds).most_common(1)[0][0]
            if kinds[0] in {"heading", "caption", "footnote", "figure_text", "equation", "code"}:
                kind = kinds[0]
            text = join_wrapped_lines([ln["text"] for ln in run])
            bboxes = [ln["bbox"] for ln in run]
            x0 = min(b[0] for b in bboxes)
            y0 = min(b[1] for b in bboxes)
            x1 = max(b[2] for b in bboxes)
            y1 = max(b[3] for b in bboxes)
            records.append(
                {
                    "type": kind,
                    "page": page,
                    "block": block,
                    "run": run_index,
                    "bbox": (x0, y0, x1, y1),
                    "text": text,
                    "line_count": len(run),
                    "avg_size": statistics.median([ln["size"] for ln in run if ln["size"]] or [body_size]),
                    "page_width": run[0]["page_width"],
                    "page_height": run[0]["page_height"],
                }
            )

    two_col_pages = detect_two_column_pages(records)
    return sorted(records, key=lambda rec: reading_order_key(rec, two_col_pages))


def detect_two_column_pages(records: list[dict[str, Any]]) -> set[int]:
    by_page: defaultdict[int, list[dict[str, Any]]] = defaultdict(list)
    for rec in records:
        if rec["type"] != "body":
            continue
        if len(rec["text"]) < 120 or rec["line_count"] < 2:
            continue
        by_page[rec["page"]].append(rec)

    two_col = set()
    for page, items in by_page.items():
        left = 0
        right = 0
        for rec in items:
            x0, y0, x1, y1 = rec["bbox"]
            page_w = rec["page_width"]
            width = x1 - x0
            if width > page_w * 0.58:
                continue
            if x0 < page_w * 0.35:
                left += 1
            elif x0 > page_w * 0.45:
                right += 1
        if left >= 2 and right >= 2:
            two_col.add(page)
    return two_col


def reading_order_key(rec: dict[str, Any], two_col_pages: set[int]) -> tuple[int, int, float, float]:
    page = rec["page"]
    x0, y0, x1, y1 = rec["bbox"]
    page_w = rec["page_width"]
    width = x1 - x0
    if page in two_col_pages and width < page_w * 0.58 and x0 > page_w * 0.45:
        col = 1
    else:
        col = 0
    if page not in two_col_pages or width > page_w * 0.70:
        col = 0
    return (page, col, y0, x0)


def join_wrapped_lines(texts: list[str]) -> str:
    out = ""
    for text in texts:
        text = text.strip()
        if not text:
            continue
        if not out:
            out = text
            continue
        out = join_text(out, text)
    return out.strip()


def join_text(prev: str, cur: str) -> str:
    if not prev:
        return cur
    if not cur:
        return prev
    if prev.endswith("-"):
        left = re.search(r"([A-Za-z]+)-$", prev)
        right = re.match(r"([A-Za-z]+)", cur)
        if left and right:
            prefix = left.group(1).lower()
            if prefix in KEEP_HYPHEN_PREFIXES:
                return prev + cur
            return prev[:-1] + cur
    if prev.endswith(("/", "(", "[", "{")):
        return prev + cur
    return prev + " " + cur


def starts_continuation(text: str) -> bool:
    if not text:
        return False
    first = text.lstrip()[0]
    if first.islower() or first in ",;:)]}":
        return True
    if text.startswith(("and ", "or ", "but ", "which ", "that ", "where ", "with ")):
        return True
    return False


def ends_hard(text: str) -> bool:
    if not text:
        return False
    if text.endswith(":"):
        return True
    return bool(SENTENCE_END_RE.search(text))


def should_merge(prev: dict[str, Any], cur: dict[str, Any]) -> tuple[bool, str | None]:
    if prev["type"] not in {"body", "list"} or cur["type"] not in {"body", "list"}:
        return False, None
    if cur["type"] == "list" and prev["type"] != "list":
        return False, None

    px0, py0, px1, py1 = prev["bbox"]
    cx0, cy0, cx1, cy1 = cur["bbox"]
    same_page = prev["page"] == cur["page"]
    similar_indent = abs(px0 - cx0) < 24
    prev_text = prev["text"].rstrip()
    cur_text = cur["text"].lstrip()

    if prev_text.endswith("-"):
        return True, "hyphenated_line_or_page_join"

    if same_page:
        gap = cy0 - py1
        line_h = max(8.0, prev["avg_size"] * 1.5)
        if gap < line_h * 1.25 and (similar_indent or starts_continuation(cur_text)) and not ends_hard(prev_text):
            return True, "same_page_soft_break"
        return False, None

    if cur["page"] == prev["page"] + 1:
        near_page_bottom = py1 > prev["page_height"] * 0.72
        near_page_top = cy0 < cur["page_height"] * 0.28
        if near_page_bottom and near_page_top and (starts_continuation(cur_text) or not ends_hard(prev_text)):
            return True, "cross_page_stitch"

    return False, None


def merge_records(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    paragraphs: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    pending_interruptions: list[dict[str, Any]] = []
    for rec in records:
        if current is None:
            current = start_para(rec)
            continue

        if current["type"] in {"body", "list"} and rec["type"] == "footnote":
            pending_interruptions.append(start_para(rec))
            continue

        merge, note = should_merge(current, rec)
        if merge:
            current["text"] = join_text(current["text"], rec["text"])
            current["pages"] = sorted(set(current["pages"]) | {rec["page"]})
            current["source_blocks"].append({"page": rec["page"], "block": rec["block"], "run": rec.get("run", 0), "type": rec["type"]})
            current["join_notes"].append(note or "merged")
            if pending_interruptions and note == "cross_page_stitch":
                current["join_notes"].append("stitched_over_footnote")
            current["bbox_by_page"] = merge_bbox_by_page(current["bbox_by_page"], rec)
            current["bbox"] = union_bbox(current["bbox"], rec["bbox"])
            current["page"] = min(current["page"], rec["page"])
            current["page_height"] = rec["page_height"]
            continue
        paragraphs.append(current)
        if pending_interruptions:
            paragraphs.extend(pending_interruptions)
            pending_interruptions = []
        current = start_para(rec)
    if current is not None:
        paragraphs.append(current)
    if pending_interruptions:
        paragraphs.extend(pending_interruptions)

    for idx, para in enumerate(paragraphs, 1):
        para["id"] = f"P{idx:04d}"
    return paragraphs


def start_para(rec: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": "",
        "type": rec["type"],
        "page": rec["page"],
        "pages": [rec["page"]],
        "bbox": rec["bbox"],
        "bbox_by_page": {str(rec["page"]): list(rec["bbox"])},
        "text": rec["text"],
        "join_notes": [],
        "source_blocks": [{"page": rec["page"], "block": rec["block"], "run": rec.get("run", 0), "type": rec["type"]}],
        "page_height": rec["page_height"],
        "avg_size": rec["avg_size"],
    }


def union_bbox(a: tuple[float, float, float, float], b: tuple[float, float, float, float]) -> tuple[float, float, float, float]:
    return (min(a[0], b[0]), min(a[1], b[1]), max(a[2], b[2]), max(a[3], b[3]))


def merge_bbox_by_page(existing: dict[str, list[float]], rec: dict[str, Any]) -> dict[str, list[float]]:
    key = str(rec["page"])
    box = list(rec["bbox"])
    if key not in existing:
        existing[key] = box
        return existing
    old = existing[key]
    existing[key] = [min(old[0], box[0]), min(old[1], box[1]), max(old[2], box[2]), max(old[3], box[3])]
    return existing


def write_jsonl(paragraphs: list[dict[str, Any]], path: Path) -> None:
    with path.open("w", encoding="utf-8") as f:
        for para in paragraphs:
            row = dict(para)
            row.pop("bbox", None)
            row.pop("page", None)
            row.pop("page_height", None)
            row.pop("avg_size", None)
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def write_md(paragraphs: list[dict[str, Any]], path: Path, pdf_path: Path, body_size: float) -> None:
    translatable_types = {"body", "heading", "caption", "list", "footnote"}
    translatable_count = sum(1 for p in paragraphs if p["type"] in translatable_types)
    lines = [
        f"# Reconstructed Paragraphs: {pdf_path.name}",
        "",
        f"- paragraph_count: {len(paragraphs)}",
        f"- translatable_record_count: {translatable_count}",
        f"- detected_body_font_size: {body_size:.1f}pt",
        "- This file is the translation backbone. Do not treat raw TXT blank lines as paragraph boundaries.",
        "- Translate `body`, `heading`, `caption`, `list`, and substantive `footnote` records. Use `figure_text`, `equation`, and `code` records for grounding, formula reconstruction, and appendix/code preservation rather than prose translation.",
        "",
    ]
    last_first_page = None
    for para in paragraphs:
        first_page = para["pages"][0]
        if first_page != last_first_page:
            lines.extend([f"## Page {first_page}", ""])
            last_first_page = first_page
        page_span = ",".join(str(p) for p in para["pages"])
        notes = ",".join(n for n in para["join_notes"] if n)
        note_text = f" joins={notes}" if notes else ""
        lines.append(f"### {para['id']} [{para['type']}] pages={page_span}{note_text}")
        lines.append("")
        lines.append(para["text"])
        lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


def summarize(paragraphs: list[dict[str, Any]], body_size: float) -> None:
    counts = Counter(p["type"] for p in paragraphs)
    joins = Counter(n for p in paragraphs for n in p["join_notes"])
    translatable_types = {"body", "heading", "caption", "list", "footnote"}
    translatable_count = sum(1 for p in paragraphs if p["type"] in translatable_types)
    print(f"paragraph_count: {len(paragraphs)}")
    print(f"translatable_record_count: {translatable_count}")
    print(f"detected_body_font_size: {body_size:.1f}pt")
    print("types: " + ", ".join(f"{k}={v}" for k, v in sorted(counts.items())))
    if joins:
        print("joins: " + ", ".join(f"{k}={v}" for k, v in sorted(joins.items())))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("pdf", help="Input PDF")
    parser.add_argument("jsonl", help="Output reconstructed paragraph JSONL")
    parser.add_argument("--md", help="Optional Markdown view of reconstructed paragraphs")
    args = parser.parse_args()

    pdf_path = Path(args.pdf)
    jsonl_path = Path(args.jsonl)
    doc = fitz.open(pdf_path)
    lines = collect_lines(doc)
    body_size = weighted_body_size(lines)
    repeated = repeated_header_footer_keys(lines)
    clean_lines = [ln for ln in lines if not is_page_artifact(ln, repeated)]
    records = block_records(clean_lines, body_size)
    paragraphs = merge_records(records)
    write_jsonl(paragraphs, jsonl_path)
    if args.md:
        write_md(paragraphs, Path(args.md), pdf_path, body_size)
    summarize(paragraphs, body_size)
    print(f"wrote_jsonl: {jsonl_path}")
    if args.md:
        print(f"wrote_md: {args.md}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
