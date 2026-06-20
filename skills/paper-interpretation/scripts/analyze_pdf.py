#!/usr/bin/env python3
"""
Analyze a PDF and print structured info to inform the interpretation workflow.

Detects:
- Paper type (System Card / Tech Report / Research Paper / Other)
- Page count
- Total caption count (Figure + Table)
- Top-level chapters / sections
- Whether it has an appendix
- Notable non-standard sections (Easter Eggs, Limitations, etc.)
- Suggested sub-section breakdown size

Usage:
    python3 analyze_pdf.py <pdf_path>

Output is human-readable + structured (one fact per line) so you can search it.
"""

import fitz, re, sys, os


def detect_paper_type(filename, first_page_text, page_count):
    """Return one of: System Card / Tech Report / Research Paper / Other."""
    fn = filename.lower()
    fp = first_page_text.lower()
    if 'system card' in fn or 'system card' in fp[:1500]:
        return 'System Card'
    if 'tech report' in fn or 'technical report' in fp[:1500]:
        return 'Tech Report'
    if re.search(r'\barxiv:\s*\d{4}\.\d+', fp[:2000]):
        if page_count > 100:
            return 'Tech Report'
        return 'Research Paper'
    if page_count > 100:
        return 'System Card'
    if page_count < 30:
        return 'Research Paper'
    return 'Tech Report'


CAPTION_RE = re.compile(
    r'^[\s\u200b\[]*'
    r'((?:Figure|Table|Fig\.|图|表)\s*\d+(?:\.\d+)*(?:\.[A-Z]\d*)?)'
    r'[\s\u200b]*([\]:.\u2014\u2013\-、：。])',
    re.IGNORECASE,
)

CHAPTER_RE = re.compile(r'^(\d+)\s+([A-Z][\w\s\-/&]{2,}?)\s*$')
CHAPTER_2LINE_RE = re.compile(r'^(\d+)\s*$')  # number alone, title on next line


def analyze(pdf_path):
    doc = fitz.open(pdf_path)
    page_count = doc.page_count
    fname = os.path.basename(pdf_path)

    first_page = doc[0].get_text()

    captions = []
    chapters = []
    appendix_page = None

    # Skip the first 10 pages for chapter/appendix detection to avoid TOC noise
    chapter_skip_pages = 10 if page_count > 50 else 2

    for i in range(page_count):
        page = doc[i]
        text = page.get_text()
        for line in text.split('\n'):
            m = CAPTION_RE.match(line.strip())
            if m:
                captions.append((i + 1, m.group(1).strip()))

        if i + 1 < chapter_skip_pages:
            continue

        # Same-line chapter heading
        lines = text.split('\n')
        for j, line in enumerate(lines[:15]):
            m = CHAPTER_RE.match(line.strip())
            if m:
                ch_num = int(m.group(1))
                ch_title = m.group(2).strip()
                if 1 <= ch_num <= 15 and len(ch_title) > 3:
                    chapters.append((i + 1, ch_num, ch_title))
                    break
            # Two-line: "N" alone, title on next line
            m2 = CHAPTER_2LINE_RE.match(line.strip())
            if m2 and j + 1 < len(lines):
                next_line = lines[j + 1].strip()
                if re.match(r'^[A-Z][\w\s\-/&]{3,}$', next_line) and len(next_line) < 60:
                    ch_num = int(m2.group(1))
                    if 1 <= ch_num <= 15:
                        chapters.append((i + 1, ch_num, next_line))
                        break

    # Find appendix by chapter title (more reliable than text search)
    for pn, num, title in chapters:
        if 'appendix' in title.lower() or '附录' in title:
            appendix_page = pn
            break

    paper_type = detect_paper_type(fname, first_page, page_count)

    if page_count < 30:
        suggested_chunk = '5 pages per sub-section'
    elif page_count < 80:
        suggested_chunk = '5-8 pages per sub-section'
    else:
        suggested_chunk = '5-8 pages per sub-section, split aggressively'

    print(f'=== {fname} ===')
    print(f'paper_type: {paper_type}')
    print(f'page_count: {page_count}')
    print(f'figures_and_tables: {len(captions)}')
    print(f'unique_chapters: {len(set(c[1] for c in chapters))}')
    print(f'has_appendix: {"yes" if appendix_page else "no"}')
    if appendix_page:
        print(f'appendix_starts_at: page {appendix_page}')
    print(f'suggested_chunk_size: {suggested_chunk}')
    print()
    print('Top-level chapters:')
    seen_chapters = set()
    for pn, num, title in chapters:
        if num in seen_chapters:
            continue
        seen_chapters.add(num)
        print(f'  Ch{num} (p{pn}): {title}')
    print()
    print(f'Captions detected: {len(captions)}')
    if captions[:5]:
        print('  First 5:')
        for pn, cid in captions[:5]:
            print(f'    p{pn}: {cid}')
    if len(captions) > 5:
        print(f'  ... and {len(captions) - 5} more')

    unusual_keywords = ['easter egg', 'broader impact', 'limitations',
                        'acknowledgement', 'project vend']
    found_unusual = []
    full_text = '\n'.join(doc[i].get_text() for i in range(page_count))
    for kw in unusual_keywords:
        if kw in full_text.lower():
            found_unusual.append(kw)
    if found_unusual:
        print()
        print(f'Notable non-standard sections found: {", ".join(found_unusual)}')
        print('  → these often contain useful context. Cover them in the interpretation.')


if __name__ == '__main__':
    if len(sys.argv) != 2:
        print('Usage: analyze_pdf.py <pdf>', file=sys.stderr)
        sys.exit(1)
    analyze(sys.argv[1])
