#!/usr/bin/env python3
"""
Extract tables from a PDF using pdfplumber's ruling-line detection.

This is much more reliable than parsing PDF text extraction directly, which
often jumbles columns. pdfplumber uses the visual structure (lines, cell
boundaries) to identify cells correctly.

Output: a markdown file with one section per detected table, showing:
- The table's page number
- The auto-detected caption (if a "Table N: ..." line is nearby)
- The table contents formatted as markdown

Usage:
    python3 extract_tables.py <pdf_path> <output_md>
    python3 extract_tables.py <pdf_path> <output_md> --min-cols 2 --min-rows 2
"""

import sys, os, re

try:
    import pdfplumber
except ImportError:
    print('ERROR: pdfplumber not installed. Run: pip install pdfplumber',
          file=sys.stderr)
    sys.exit(1)

CAPTION_RE = re.compile(
    r'^[\s\u200b\[]*'
    r'((?:Table|表)\s*\d+(?:\.\d+)*(?:\.[A-Z]\d*)?)'
    r'[\s\u200b]*([\]:.\u2014\u2013\-、：。])'
    r'\s*(.{0,200})',
    re.IGNORECASE,
)


def cell_to_md(cell):
    """Clean a cell value for markdown."""
    if cell is None:
        return ''
    # Replace newlines with <br> for inline rendering
    s = str(cell).replace('\n', ' ').strip()
    # Escape pipe characters
    s = s.replace('|', '\\|')
    return s or '—'


def table_to_md(table):
    """Convert a 2D list to a markdown table string."""
    if not table or not table[0]:
        return ''
    cleaned = [[cell_to_md(c) for c in row] for row in table]
    # Pad short rows
    width = max(len(row) for row in cleaned)
    cleaned = [row + [''] * (width - len(row)) for row in cleaned]

    out = []
    out.append('| ' + ' | '.join(cleaned[0]) + ' |')
    out.append('|' + '|'.join(['---'] * width) + '|')
    for row in cleaned[1:]:
        out.append('| ' + ' | '.join(row) + ' |')
    return '\n'.join(out)


def find_caption_for_table(page_text, table_bbox=None):
    """Find a 'Table N: ...' caption in the page text. Return (id, title) or None."""
    if not page_text:
        return None
    for line in page_text.split('\n'):
        m = CAPTION_RE.match(line.strip())
        if m:
            return m.group(1).strip(), m.group(3).strip()
    return None


def is_substring_table(table, others):
    """Single-column tables whose cells are all subsets of a larger multi-col
    table on the same page are sub-cells of the larger table."""
    if not table or not table[0]:
        return True
    if len(table[0]) > 1:
        return False
    cell_texts = {str(row[0]).strip() for row in table if row[0]}
    for other in others:
        if other is table or len(other[0]) <= 1:
            continue
        other_cells = set()
        for r in other:
            for c in r:
                if c:
                    for piece in str(c).strip().split('\n'):
                        piece = piece.strip()
                        if piece:
                            other_cells.add(piece)
        if cell_texts and cell_texts.issubset(other_cells):
            return True
    return False


def cell_emptiness(table):
    """Fraction of cells that are empty/None."""
    total = 0
    empty = 0
    for row in table:
        for c in row:
            total += 1
            if c is None or not str(c).strip() or str(c).strip() == '—':
                empty += 1
    return empty / max(total, 1)


def _looks_like_data_column(col_values):
    """Check if a column looks like real table data (not prose fragments).
    True if cells are mostly: numbers, percentages, short labels, model names.
    """
    non_empty = [str(v).strip() for v in col_values if v and str(v).strip()]
    if len(non_empty) < 2:
        return False
    # Numeric column: most cells contain a digit
    numeric = sum(1 for v in non_empty if any(c.isdigit() for c in v))
    if numeric / len(non_empty) >= 0.6:
        return True
    # Short-label column: most cells are short and don't look like sentence fragments
    short = sum(1 for v in non_empty if len(v) <= 35 and v.count(' ') <= 4)
    if short / len(non_empty) >= 0.8:
        return True
    return False


def is_garbage_table(table):
    """Reject tables that are clearly not real data tables.
    Real data tables have:
    - Multiple rows AND multiple columns
    - At least one column that looks like data (numbers, short labels)
    - Reasonable row count (< 30 typical)
    - Not mostly empty
    - No very long cells
    """
    if not table or not table[0]:
        return True
    if len(table) < 2 or len(table[0]) < 2:
        return True
    if cell_emptiness(table) > 0.55:
        return True
    if len(table) > 30:
        return True

    long_cells = 0
    very_long_cells = 0
    total_cells = 0
    for row in table:
        for c in row:
            if c and str(c).strip():
                total_cells += 1
                cl = len(str(c).strip())
                if cl > 80:
                    long_cells += 1
                if cl > 200:
                    very_long_cells += 1
    if total_cells == 0:
        return True
    if long_cells / total_cells > 0.20:
        return True
    if very_long_cells > 0:
        return True

    # At least one column must look like real data (numbers or short labels)
    n_cols = max(len(row) for row in table)
    has_data_col = False
    for ci in range(n_cols):
        col = [row[ci] if ci < len(row) else None for row in table]
        if _looks_like_data_column(col):
            has_data_col = True
            break
    if not has_data_col:
        return True

    return False


def extract_page_tables(page):
    """Use pdfplumber's lines strategy to extract ruled tables.

    NOTE: This works well for tables with explicit ruling lines (booktabs
    horizontal rules, gridded tables, System Card tables). It does NOT
    work for tightly-integrated text-aligned tables in some research papers
    (e.g., small inline tables) — pdfplumber can't separate them
    from surrounding body text without visual rulings. For those papers,
    fall back to manual transcription via visual inspection of the figure
    image extracted by extract_figures.py.
    """
    try:
        tables = page.extract_tables() or []
    except Exception as e:
        print(f'  page extract error: {e}', file=sys.stderr)
        return []
    return [t for t in tables if not is_garbage_table(t)
            and not is_substring_table(t, tables)]


def extract(pdf_path, out_path, min_cols=2, min_rows=2):
    sections = []
    total_kept = 0

    with pdfplumber.open(pdf_path) as pdf:
        for pn, page in enumerate(pdf.pages, start=1):
            kept = extract_page_tables(page)
            if not kept:
                continue

            # Apply user-controlled min size filters
            kept = [t for t in kept
                    if t and len(t) >= min_rows and len(t[0]) >= min_cols]
            if not kept:
                continue

            page_text = page.extract_text() or ''
            caption_info = find_caption_for_table(page_text)

            for i, t in enumerate(kept):
                total_kept += 1
                rows = len(t)
                cols = len(t[0])
                cap_str = ''
                if caption_info:
                    cid, ctitle = caption_info
                    cap_str = f'**{cid}** — {ctitle}' if ctitle else f'**{cid}**'
                sections.append({
                    'page': pn,
                    'index': i,
                    'rows': rows,
                    'cols': cols,
                    'caption': cap_str,
                    'markdown': table_to_md(t),
                })

    # Write output
    with open(out_path, 'w', encoding='utf-8') as f:
        f.write(f'# Tables extracted from {os.path.basename(pdf_path)}\n\n')
        f.write(f'Total: {total_kept} tables (min {min_cols}×{min_rows})\n\n')
        f.write('---\n\n')
        for s in sections:
            f.write(f'## Page {s["page"]} — Table {s["index"]+1} ({s["rows"]}×{s["cols"]})\n\n')
            if s['caption']:
                f.write(f'{s["caption"]}\n\n')
            f.write(s['markdown'])
            f.write('\n\n---\n\n')

    print(f'Extracted {total_kept} tables to {out_path}')
    return sections


if __name__ == '__main__':
    args = [a for a in sys.argv[1:] if not a.startswith('--')]
    flags = {a.split('=')[0]: (a.split('=', 1)[1] if '=' in a else True)
             for a in sys.argv[1:] if a.startswith('--')}
    if len(args) != 2:
        print('Usage: extract_tables.py <pdf> <output.md> '
              '[--min-cols=N] [--min-rows=N]', file=sys.stderr)
        sys.exit(1)
    min_cols = int(flags.get('--min-cols', 2))
    min_rows = int(flags.get('--min-rows', 2))
    extract(args[0], args[1], min_cols=min_cols, min_rows=min_rows)
