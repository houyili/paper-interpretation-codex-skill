#!/usr/bin/env python3
"""
Extract all text from a PDF into a single .txt file with page markers.

Usage:
    python3 extract_pdf_text.py <pdf_path> <output_txt_path>

Output format:
    === Page 1 ===
    {text of page 1}

    === Page 2 ===
    {text of page 2}
    ...

This is the raw search-index step of the paper-interpretation workflow.
Do not treat blank lines or page boundaries in this output as authoritative
paragraph boundaries. After running this script, run
reconstruct_pdf_paragraphs.py and use its paragraph ids/page ranges as the
translation backbone.
"""

import fitz, sys


def extract(pdf_path, out_path):
    doc = fitz.open(pdf_path)
    with open(out_path, 'w', encoding='utf-8') as f:
        for i in range(doc.page_count):
            f.write(f'=== Page {i + 1} ===\n')
            f.write(doc[i].get_text())
            f.write('\n')
    print(f'Extracted {doc.page_count} pages to {out_path}')


if __name__ == '__main__':
    if len(sys.argv) != 3:
        print('Usage: extract_pdf_text.py <pdf> <output.txt>', file=sys.stderr)
        sys.exit(1)
    extract(sys.argv[1], sys.argv[2])
