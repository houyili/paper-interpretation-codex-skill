#!/usr/bin/env python3
"""
Extract footnotes from a PDF using font-size detection.

Footnotes in academic PDFs are usually:
- Smaller font than body text (often 8-9pt vs 10-11pt body)
- Located in the lower portion of the page (bottom 30%)
- Start with a digit (the footnote number)

This script finds such blocks and outputs them grouped by page, so you
can easily check which footnotes belong to which section during interpretation.

Usage:
    python3 extract_footnotes.py <pdf_path> <output.md>
    python3 extract_footnotes.py <pdf_path> <output.md> --min-text-len=30
"""

import fitz, sys, re

CAPTION_RE = re.compile(
    r'^[\s\u200b\[]*'
    r'(?:Figure|Table|Fig\.|图|表)\s*\d+(?:\.\d+)*(?:\.[A-Z]\d*)?'
    r'[\s\u200b]*[\]:.\u2014\u2013\-、：。]',
    re.IGNORECASE,
)


MATH_CHARS_RE = re.compile(r'[=∼∈≤≥−×÷∑∏∫θπλμσρφψωΘΠΛΣ∂∇←→↑↓⇒⇐⇔αβγδ]')
GREEK_RE = re.compile(r'[θπλμσρφψωΘΠΛΣαβγδ]')


def looks_like_math(text):
    """Math equations have many special chars and few real words."""
    if not text:
        return False
    # Strong signal: contains Greek letters
    if GREEK_RE.search(text):
        # Greek letters in body text are rare; if present + short → math
        if len(text) < 200:
            return True
    alpha = sum(1 for c in text if c.isalpha())
    total = len(text.strip())
    if total == 0:
        return False
    alpha_ratio = alpha / total
    has_math_chars = bool(MATH_CHARS_RE.search(text))
    if alpha_ratio < 0.5 and has_math_chars:
        return True
    return False


def extract(pdf_path, out_path, min_text_len=20):
    doc = fitz.open(pdf_path)

    all_sizes = []
    for i in range(doc.page_count):
        page = doc[i]
        for b in page.get_text('dict')['blocks']:
            if b['type'] != 0:
                continue
            for line in b['lines']:
                for span in line['spans']:
                    all_sizes.append(span['size'])
    if not all_sizes:
        print('No text found', file=sys.stderr)
        return
    body_size = sum(all_sizes) / len(all_sizes)

    footnotes_by_page = {}
    for i in range(doc.page_count):
        page = doc[i]
        page_h = page.rect.height
        page_footnotes = []

        for b in page.get_text('dict')['blocks']:
            if b['type'] != 0:
                continue
            bbox = b['bbox']

            if bbox[1] < page_h * 0.55:
                continue

            block_sizes = []
            text = ''
            for line in b['lines']:
                for span in line['spans']:
                    block_sizes.append(span['size'])
                    text += span['text']
                text += '\n'
            text = text.strip()

            if not block_sizes:
                continue
            block_avg = sum(block_sizes) / len(block_sizes)

            if block_avg >= body_size * 0.93:
                continue

            if len(text) < min_text_len:
                continue

            stripped = re.sub(r'\s+', '', text)
            if stripped.isdigit():
                continue

            # Skip figure/table captions
            if CAPTION_RE.match(text):
                continue

            # Skip math expressions
            if looks_like_math(text):
                continue

            m = re.match(r'^(\d{1,3})\s+(.+)', text, re.DOTALL)
            if m:
                fn_num = m.group(1)
                fn_text = m.group(2).strip()
            else:
                fn_num = None
                fn_text = text

            page_footnotes.append({
                'num': fn_num,
                'text': fn_text,
                'y': bbox[1],
                'font_size': block_avg,
            })

        if page_footnotes:
            footnotes_by_page[i + 1] = sorted(page_footnotes, key=lambda f: f['y'])

    total = sum(len(v) for v in footnotes_by_page.values())

    with open(out_path, 'w', encoding='utf-8') as f:
        f.write(f'# Footnotes extracted from {pdf_path}\n\n')
        f.write(f'Body font size detected: {body_size:.1f}pt\n')
        f.write(f'Total footnotes: {total} on {len(footnotes_by_page)} pages\n\n')
        f.write('---\n\n')
        for pn in sorted(footnotes_by_page.keys()):
            f.write(f'## Page {pn}\n\n')
            for fn in footnotes_by_page[pn]:
                num = f'**[{fn["num"]}]** ' if fn['num'] else ''
                f.write(f'- {num}{fn["text"]}\n\n')

    print(f'Extracted {total} footnotes to {out_path}')


if __name__ == '__main__':
    args = [a for a in sys.argv[1:] if not a.startswith('--')]
    flags = {a.split('=')[0]: (a.split('=', 1)[1] if '=' in a else True)
             for a in sys.argv[1:] if a.startswith('--')}
    if len(args) != 2:
        print('Usage: extract_footnotes.py <pdf> <output.md> [--min-text-len=N]',
              file=sys.stderr)
        sys.exit(1)
    min_len = int(flags.get('--min-text-len', 20))
    extract(args[0], args[1], min_text_len=min_len)
