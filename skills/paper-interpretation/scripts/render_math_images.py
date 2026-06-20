#!/usr/bin/env python3
"""Render display math blocks in Markdown to local PNG images.

This is a compatibility helper for Markdown previewers such as MacDown when
TeX/MathJax rendering is disabled or unavailable. It replaces `$$...$$` blocks
with image references and stores the original LaTeX in HTML comments.
"""

import argparse
import hashlib
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import fitz
from PIL import Image, ImageChops


DISPLAY_MATH_RE = re.compile(r"(?ms)^\$\$\s*\n(.*?)\n\$\$\s*$")


LATEX_TEMPLATE = r"""
\documentclass[12pt]{{article}}
\usepackage[paperwidth=15in,paperheight=8in,margin=0.25in]{{geometry}}
\usepackage{{amsmath,amssymb,bm}}
\pagestyle{{empty}}
\begin{{document}}
\[
{body}
\]
\end{{document}}
"""


def run(cmd, cwd):
    return subprocess.run(
        cmd,
        cwd=cwd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        check=False,
    )


def crop_png(path: Path, pad: int = 18):
    im = Image.open(path).convert("RGB")
    bg = Image.new("RGB", im.size, "white")
    diff = ImageChops.difference(im, bg)
    bbox = diff.getbbox()
    if not bbox:
        return
    left = max(0, bbox[0] - pad)
    upper = max(0, bbox[1] - pad)
    right = min(im.size[0], bbox[2] + pad)
    lower = min(im.size[1], bbox[3] + pad)
    im.crop((left, upper, right, lower)).save(path)


def render_block(body: str, out_path: Path, scale: float = 2.0):
    pdflatex = shutil.which("pdflatex")
    if not pdflatex:
        raise RuntimeError("pdflatex not found; cannot render math images")

    with tempfile.TemporaryDirectory(prefix="codex_math_") as td:
        work = Path(td)
        tex_path = work / "eq.tex"
        tex_path.write_text(LATEX_TEMPLATE.format(body=body), encoding="utf-8")
        proc = run([pdflatex, "-interaction=nonstopmode", "eq.tex"], work)
        if proc.returncode != 0:
            raise RuntimeError(f"pdflatex failed for {out_path.name}:\n{proc.stdout[-2000:]}")
        pdf_path = work / "eq.pdf"
        doc = fitz.open(pdf_path)
        page = doc[0]
        pix = page.get_pixmap(matrix=fitz.Matrix(scale, scale), alpha=False)
        tmp_png = work / "eq.png"
        pix.save(tmp_png)
        shutil.copyfile(tmp_png, out_path)
    crop_png(out_path)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--markdown", required=True)
    ap.add_argument("--out", help="Output Markdown path. Defaults to in-place.")
    ap.add_argument("--equation-dir", default="equations")
    ap.add_argument("--alt-prefix", default="Equation")
    args = ap.parse_args()

    md_path = Path(args.markdown)
    out_path = Path(args.out) if args.out else md_path
    text = md_path.read_text(encoding="utf-8")
    eq_dir = md_path.parent / args.equation_dir
    eq_dir.mkdir(parents=True, exist_ok=True)

    replacements = []
    for idx, match in enumerate(DISPLAY_MATH_RE.finditer(text), 1):
        body = match.group(1).strip()
        digest = hashlib.sha1(body.encode("utf-8")).hexdigest()[:10]
        filename = f"equation_{idx:02d}_{digest}.png"
        img_path = eq_dir / filename
        render_block(body, img_path)
        rel = f"{args.equation_dir}/{filename}"
        replacement = (
            f"![{args.alt_prefix} {idx}]({rel})\n\n"
            f"<!-- LaTeX source for {args.alt_prefix} {idx}:\n{body}\n-->"
        )
        replacements.append((match.span(), replacement))

    if not replacements:
        print("No display math blocks found")
        return 0

    chunks = []
    last = 0
    for (start, end), replacement in replacements:
        chunks.append(text[last:start])
        chunks.append(replacement)
        last = end
    chunks.append(text[last:])
    out_path.write_text("".join(chunks), encoding="utf-8")
    print(f"Rendered {len(replacements)} display math blocks to {eq_dir}")
    print(f"Wrote {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
