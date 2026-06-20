#!/usr/bin/env python3
"""
Caption-based figure / table extractor for academic PDFs.

Algorithm:
1. Scan all pages and collect text blocks + image blocks (sorted by y).
2. Detect caption blocks: text starting with "Figure N", "Table N", "[Figure N.X]" etc.
   Distinguish "real" captions (figure / table title) from in-text references
   by requiring a colon, period, or bracket immediately after the number.
3. For each caption, examine the vertical gap above AND below it on the same page.
   - Above gap: from bottom of nearest preceding text block to top of caption.
   - Below gap: from bottom of caption to top of nearest following text block.
   - Pick the larger gap as the figure region (typically: figures above caption,
     tables below caption, but the algorithm decides per caption).
4. If both gaps are tiny on the current page, look at the previous page
   (figure-on-prev-page pattern).
5. Render that bounding box at 3× resolution.
"""

import fitz, re, sys, os
from collections import namedtuple

try:
    from PIL import Image
    HAS_PIL = True
except ImportError:
    HAS_PIL = False

# Match captions: "Figure N", "Figure N.Y", "Figure N.Y.Z", "Figure N.Y.Z.A",
# appendix-style "Figure A.1" / "Table F.2",
# also Chinese 图 N / 表 N. Must be followed by ONE of:
#   - non-period separator: : ] — – - 、 ：(full) 。
#   - period followed by space (or end-of-string) — NOT period followed by digit,
#     otherwise body text "Table 6.3.A summarizes..." backtracks to "Table 6.3"+"."
#     and gets falsely matched
#   - space + Title Case word (MIMO/some papers use no separator) — Latin or Chinese
#
# The (?-i:...) inline modifier disables IGNORECASE for the lookahead so the Title
# Case check is actually case-sensitive. Without this, "Figure N shows..." (lowercase
# 's') would also match.
CAPTION_RE = re.compile(
    r'^[\s\u200b\[]*'                                                # leading ws / bracket
    r'((?:Figure|Table|Fig\.|图|表)\s*'
    r'(?:\d+(?:\.\d+)*(?:\.[A-Z]\d*)?|[A-Z]\.\d+(?:\.\d+)*))'        # ID (en + zh)
    r'(?:'
    r'[\s\u200b]*[\]:\u2014\u2013\-、：。]'                            # non-period seps
    r'|[\s\u200b]*\.(?:\s|$)'                                         # period + ws/end
    r'|\s+(?-i:(?=[A-Z\u4e00-\u9fff]))'                               # space + Title Case
    r')',
    re.IGNORECASE,
)

Block = namedtuple('Block', 'kind bbox text')


def get_blocks(page):
    out = []
    for b in page.get_text('dict')['blocks']:
        bbox = tuple(b['bbox'])
        if b['type'] == 0:
            text = ''
            for line in b['lines']:
                for span in line['spans']:
                    text += span['text']
                text += '\n'
            text = text.replace('\u200b', '').replace('\u00a0', ' ').strip()
            if text:
                out.append(Block('text', bbox, text))
        elif b['type'] == 1:
            out.append(Block('image', bbox, ''))
    out.sort(key=lambda b: b.bbox[1])
    return out


def slugify(name):
    return re.sub(r'[^A-Za-z0-9]+', '_', name).strip('_')


CODE_MARKERS_RE = re.compile(r'(?:</?\w+>|\{[\w_]+\}|"""|```|\bdef \w+\(|\bimport \w+|=\s*\w+\(|\$\{)')

# Captions that indicate the figure body is prose-style content (prompts,
# templates, code listings, dialogue transcripts). When matched, the extractor
# uses loose mode: all text blocks are treated as figure content (no prose
# boundaries). Added after visual verification of cross-page prompt figures.
# (v0.5.3) and extended in v0.5.4 to cover dialogue/transcript figures.
#
# The "sample/example + noun" forms require a specific noun (dialogue, transcript,
# conversation, interaction, output) to avoid matching generic phrases like
# "example results" or "sample of N".
PROMPT_CAPTION_RE = re.compile(
    r'\b(?:'
    r'prompts?|templates?|listing|pseudocode'
    r'|user\s+prompt|system\s+prompt'
    r'|(?:sample|example)\s+(?:dialogue|transcript|conversation|interaction|output|response)'
    r'|conversation\s+(?:transcript|example|sample)'
    r')\b',
    re.IGNORECASE,
)


def caption_is_prompt_like(cap_text):
    """A figure caption that signals the body is text/prose content."""
    return bool(PROMPT_CAPTION_RE.search(cap_text))

# Numbered section headings: "6 Pretraining", "6.1 Reasoning", "6.1.2 Eval...".
# These are short (often < 60 chars) so the length-based prose detection misses them,
# but they ARE hard boundaries — without this, table/figure bboxes bleed into the
# next section's first heading. Discovered via visual verification on
# wrapped table crops (v0.4 -> v0.5 fix).
#
# Three prefix forms (v0.5.3 — letter prefixes safe to add now that prompt-like
# captions get loose-mode rescue, see PROMPT_CAPTION_RE):
#   - Numeric: 6, 6.1, 6.1.2, optionally with trailing dot
#   - Letter+dot-num: B.1, B.1.2, C.3 (appendix subsections)
#   - Standalone letter B-W: "B Evaluation Details", "C Algorithms"
#     (excludes A, I as common sentence starters; excludes X/Y/Z to avoid axis-label
#      false positives like "Y Axis"). Title Case follower required by regex.
SECTION_HEADING_RE = re.compile(
    r'^\s*'
    r'(?:'
    r'\d+(?:\.\d+){0,3}\.?'        # numeric: 6, 6.1, 6.1.2
    r'|[A-Z]\.\d+(?:\.\d+){0,2}'   # letter+dot+num: B.1, B.1.2
    r'|[B-HJ-W]'                   # standalone letter (excl. A/I/X/Y/Z)
    r')'
    r'\s+[A-Z\u4e00-\u9fff]'
)


def is_section_heading(text):
    """Numbered heading like '6.1.2 Evaluation of Coding Benchmarks'.
    Returns True if this short text block should still bound figure regions.

    PyMuPDF often splits the section number and the title across two lines
    in the same block — we join them with a space before matching.

    BEWARE OF DATA LABELS: a bar chart label like "95.8\\nTool Call" joins to
    "95.8 Tool Call" which also matches the section heading regex. We filter
    these out by requiring the leading integer to be ≤ 30, and if a decimal
    point is present, ≤ 19 (real subsections rarely have > 19 chapters).
    """
    text = text.strip()
    if not text:
        return False
    # Join multi-line headings: PyMuPDF often makes "6.1.2\nEvaluation..." one block
    joined = ' '.join(line.strip() for line in text.split('\n') if line.strip())
    if len(joined) > 80 or len(joined) < 5:
        return False
    # Headings don't contain mid-sentence punctuation. List items inside prose
    # like "1. If the agent asks ...:" would otherwise match the regex.
    if ',' in joined or ';' in joined or ':' in joined:
        return False
    if not SECTION_HEADING_RE.match(joined):
        return False
    # Filter out chart data labels misidentified as headings
    num_m = re.match(r'^\s*(\d+)((?:\.\d+){0,3})', joined)
    if num_m:
        first_int = int(num_m.group(1))
        has_dot = bool(num_m.group(2))
        if first_int > 30:  # Real chapter numbers rarely exceed 30
            return False
        if has_dot and first_int > 19:  # Decimal labels like "30.5 ..." are data
            return False
    return True


def is_prose_text(b, page_width):
    """A text block is 'prose' (paragraph body text) if it's long enough.
    Short text blocks are figure labels / axis ticks / legends / table cells / code
    and should be treated as figure content, not boundaries."""
    if b.kind != 'text':
        return False
    text = b.text.strip()
    # Numbered section headings are hard boundaries even when short
    if is_section_heading(text):
        return True
    if len(text) < 60:
        return False
    # Code / markup blocks (XML tags, template placeholders, def/import) are not prose
    if CODE_MARKERS_RE.search(text):
        return False
    # Figure legends often look like sentences but end with a bare numeric value
    # (e.g., "hidden state mean before gate, avg 0.71"). Filter these out so they
    # don't shrink figure regions.
    last_line = text.split('\n')[-1].strip()
    if last_line and re.search(r'\d+(?:\.\d+)?$', last_line):
        return False
    # Tables / data rows have many digits
    letters = sum(c.isalpha() or '\u4e00' <= c <= '\u9fff' for c in text)
    digits = sum(c.isdigit() for c in text)
    if letters + digits > 0:
        digit_ratio = digits / (letters + digits)
        if digit_ratio > 0.30:
            return False
    lines = [ln for ln in text.split('\n') if ln.strip()]
    if not lines:
        return False
    # For Chinese text: characters are denser, so use char count thresholds
    has_chinese = any('\u4e00' <= c <= '\u9fff' for c in text)
    if has_chinese:
        if len(text) >= 30:  # Chinese paragraphs are dense
            return True
        return False
    avg_line_len = len(text) / max(len(lines), 1)
    if avg_line_len < 18:
        return False
    if len(lines) >= 2 and avg_line_len >= 25:
        return True
    if len(text) >= 100:
        return True
    return False


def is_code_example_page(blocks, page_width):
    """A page is a 'code example page' if its top text content is code-like
    (XML tags, JSON, prompt templates). On such pages, the entire page area
    around the caption should be treated as figure content."""
    text_blocks = [b for b in blocks if b.kind == 'text']
    if len(text_blocks) < 2:
        return False
    # Look at first 4 text blocks (top of page)
    top_blocks = sorted(text_blocks, key=lambda b: b.bbox[1])[:4]
    code_count = sum(1 for b in top_blocks if CODE_MARKERS_RE.search(b.text))
    return code_count >= 1


def detect_columns(blocks, page_width):
    """Detect if the page is multi-column (typically 2-column conference paper).
    Returns a list of (col_x_min, col_x_max) tuples, or [(0, page_width)] for
    single-column pages.

    Heuristic: cluster text-block x-centers; if there are two clear modes
    that are FAR APART (centers differ by ≥ 25% of page width), the page is
    2-column. Single-column pages have all centers near the page midpoint
    and we must NOT misdetect them as 2-column.
    """
    text_blocks = [b for b in blocks if b.kind == 'text' and len(b.text.strip()) > 20]
    if len(text_blocks) < 6:
        return [(0, page_width)]
    centers = sorted((b.bbox[0] + b.bbox[2]) / 2 for b in text_blocks)

    # Quick reject: if all centers are within 15% of page width, it's single-column
    if centers[-1] - centers[0] < page_width * 0.15:
        return [(0, page_width)]

    mid = page_width / 2
    left = [c for c in centers if c < mid]
    right = [c for c in centers if c >= mid]
    if len(left) < 3 or len(right) < 3:
        return [(0, page_width)]

    # Cluster centroids
    left_mean = sum(left) / len(left)
    right_mean = sum(right) / len(right)

    # The two clusters must be FAR APART (≥ 25% of page width)
    if right_mean - left_mean < page_width * 0.25:
        return [(0, page_width)]

    # Each cluster should be tightly grouped around its centroid
    def cluster_std(xs, mean):
        return (sum((x - mean) ** 2 for x in xs) / len(xs)) ** 0.5
    if cluster_std(left, left_mean) > page_width * 0.08:
        return [(0, page_width)]
    if cluster_std(right, right_mean) > page_width * 0.08:
        return [(0, page_width)]

    col_split = (max(left) + min(right)) / 2
    return [(0, col_split), (col_split, page_width)]


def block_column(b, columns):
    """Return the column index of a block based on its x-center."""
    if len(columns) == 1:
        return 0
    cx = (b.bbox[0] + b.bbox[2]) / 2
    for i, (x0, x1) in enumerate(columns):
        if x0 <= cx < x1:
            return i
    return 0


def find_gaps(caption_block, blocks, page_rect, columns=None, loose=False):
    """
    Find the vertical gap above and below the caption on this page.
    Boundaries are set by *prose* text blocks; small labels (axis ticks,
    legend entries, code/template tokens) are treated as figure content.

    Multi-column aware: if columns is provided, only blocks in the same
    column as the caption are considered as boundaries. (Wide blocks that
    span multiple columns — like full-width figures — are still considered.)

    Special case: on a "code example page" (top of page contains code/template
    markers), the figure region extends to the page edges regardless of
    intermediate prose-looking blocks (which are usually embedded natural
    language inside the prompt example).

    loose: When True, treat all text blocks as figure content (skip prose
    detection). Used for prompt-like captions where the figure body is
    natural-language prose.
    """
    cap = caption_block.bbox
    cap_top, cap_bot = cap[1], cap[3]
    page_w = page_rect.width

    code_page = loose or is_code_example_page(blocks, page_w)

    if columns is None:
        columns = [(0, page_w)]
    cap_col = block_column(caption_block, columns)

    def in_same_column(b):
        if len(columns) == 1:
            return True
        # Wide blocks (spanning >70% page width) are full-page; they bound everything
        bw = b.bbox[2] - b.bbox[0]
        if bw > page_w * 0.7:
            return True
        return block_column(b, columns) == cap_col

    # Above gap: bounded above by the lowest prose text block above caption.
    # Other captions on the page also act as boundaries (so stacked tables on
    # one page don't bleed into each other).
    above_top = 30
    if not code_page:
        for b in blocks:
            if b is caption_block:
                continue
            is_boundary = (b.kind == 'text' and (
                is_prose_text(b, page_w) or
                bool(CAPTION_RE.match(b.text))))
            if not is_boundary:
                continue
            if not in_same_column(b):
                continue
            if b.bbox[3] <= cap_top - 1 and b.bbox[3] > above_top:
                above_top = b.bbox[3]
    above_bot = cap_top

    # Below gap: bounded below by the topmost prose / caption block below caption
    below_top = cap_bot
    below_bot = page_rect.height - 30
    if not code_page:
        for b in blocks:
            if b is caption_block:
                continue
            is_boundary = (b.kind == 'text' and (
                is_prose_text(b, page_w) or
                bool(CAPTION_RE.match(b.text))))
            if not is_boundary:
                continue
            if not in_same_column(b):
                continue
            if b.bbox[1] >= cap_bot + 1 and b.bbox[1] < below_bot:
                below_bot = b.bbox[1]

    return above_top, above_bot, below_top, below_bot


def collect_imgs_in_range(blocks, y_top, y_bot):
    """Image blocks whose center is within [y_top, y_bot]."""
    out = []
    for b in blocks:
        if b.kind != 'image':
            continue
        cy = (b.bbox[1] + b.bbox[3]) / 2
        if y_top - 2 <= cy <= y_bot + 2:
            out.append(b)
    return out


def region_has_table_content(blocks, y_top, y_bot):
    """Heuristic: does this vertical region contain table-like content?
    True if there are ≥ 2 text blocks with high digit ratio (table data rows).
    Used to detect MIMO-style tables where the caption sits BELOW the table.
    """
    digit_heavy = 0
    for b in blocks:
        if b.kind != 'text':
            continue
        if b.bbox[1] < y_top - 2 or b.bbox[3] > y_bot + 2:
            continue
        text = b.text.strip()
        if len(text) < 5:
            continue
        digits = sum(c.isdigit() for c in text)
        letters = sum(c.isalpha() for c in text)
        if letters + digits == 0:
            continue
        if digits / (letters + digits) > 0.25:
            digit_heavy += 1
    return digit_heavy >= 2


def refine_table_extent_below(blocks, cap_bot, max_y, page_w):
    """Return the y-bottom of the LAST wide multi-line block below cap_bot.

    We track only WIDE (> 28% of page width) multi-line blocks as "table rows".
    Narrow group headers ("Gating Position Variants", w ≈ 14%) are ignored —
    they don't stop the walk but also don't update the last-row marker.
    Walking stops at the first prose paragraph (hard boundary).

    This approach correctly handles:
    - Narrow group headers mid-table: walk past them
    - Figure histogram content below a table (Gated page 7): stop at last wide NL row
    - Intra-table single-line group headers like "28 Layer, 1.7B Parameters, ..."
    """
    candidates = sorted(
        [b for b in blocks if b.kind == 'text'
         and b.bbox[1] >= cap_bot - 1 and b.bbox[3] <= max_y + 1],
        key=lambda b: b.bbox[1])
    last_row_y = None
    for b in candidates:
        text = b.text.strip()
        if not text:
            continue
        if is_prose_text(b, page_w):
            break  # prose paragraph = hard boundary, stop scanning
        bw = b.bbox[2] - b.bbox[0]
        if '\n' in text and bw > page_w * 0.28:
            last_row_y = b.bbox[3]  # track the LAST wide table data row
    return last_row_y if last_row_y is not None else max_y


def refine_figure_extent_above(blocks, cap_top, min_y, page_w):
    """For Figure caption with figure ABOVE, walk up from cap_top accumulating
    figure-content blocks. Stops at the first WIDE multi-line digit-heavy block,
    which signals a table row from a stacked table above the figure.

    The width criterion (> 45% of page width) is critical: narrow multi-line
    blocks like axis tick labels ("20k\\n40k\\n60k") or chart legends
    ("ZMultiDialBench\\n1400") must NOT stop the walk — only wide blocks that
    span most of the column (actual table rows) should stop it.
    """
    candidates = sorted(
        [b for b in blocks
         if b.bbox[3] <= cap_top + 1 and b.bbox[1] >= min_y - 1],
        key=lambda b: b.bbox[1], reverse=True)  # bottom to top
    start_y = cap_top
    for b in candidates:
        if b.kind == 'image':
            start_y = min(start_y, b.bbox[1])
            continue
        text = b.text.strip()
        if not text:
            continue
        # Wide multi-line digit-heavy block = table row from a preceding table.
        # Narrow blocks (< 45% of page width) are chart axis labels / legends —
        # do NOT stop on them.
        if '\n' in text:
            digits = sum(c.isdigit() for c in text)
            letters = sum(c.isalpha() for c in text)
            if letters + digits > 0 and digits / (letters + digits) > 0.20:
                block_w = b.bbox[2] - b.bbox[0]
                if block_w > page_w * 0.45:  # wide = spans column → table row
                    break
        start_y = min(start_y, b.bbox[1])
    return start_y


def caption_data_proximity(caption_block, blocks):
    """Distance from a caption to the nearest digit-heavy block above vs below.
    The closer side is where the table data lives.

    Returns (above_dist, below_dist). Used to disambiguate MIMO-style tables
    (caption below data) from standard tables (caption above data) — works
    even when only one data row exists, where region_has_table_content fails.
    """
    cap_top = caption_block.bbox[1]
    cap_bot = caption_block.bbox[3]
    above_dist = float('inf')
    below_dist = float('inf')
    for b in blocks:
        if b.kind != 'text' or b is caption_block:
            continue
        text = b.text.strip()
        if len(text) < 5:
            continue
        digits = sum(c.isdigit() for c in text)
        letters = sum(c.isalpha() for c in text)
        if letters + digits == 0:
            continue
        if digits / (letters + digits) < 0.20:
            continue
        if b.bbox[3] <= cap_top:
            d = cap_top - b.bbox[3]
            if d < above_dist:
                above_dist = d
        elif b.bbox[1] >= cap_bot:
            d = b.bbox[1] - cap_bot
            if d < below_dist:
                below_dist = d
    return above_dist, below_dist


def refine_table_x_bounds(blocks, y0, y1, page_w, default_x0, default_x1):
    """Expand table crops horizontally to include table text touching the sides.

    This protects centered table captions from being mistaken for right-side
    wrapfig captions. The crop should follow the table body/header extents,
    not the caption's x-position. This handles wrap-table layouts where the
    Method column was clipped by the generic wrapfig heuristic.
    """
    xs = []
    for b in blocks:
        if b.kind != 'text':
            continue
        if b.bbox[3] < y0 - 2 or b.bbox[1] > y1 + 2:
            continue
        text = b.text.strip()
        if not text or CAPTION_RE.match(text):
            continue
        # Table headers/rows are often short or multi-line; prose paragraphs
        # are excluded so right-side wrap tables don't absorb body text.
        digits = sum(c.isdigit() for c in text)
        letters = sum(c.isalpha() or '\u4e00' <= c <= '\u9fff' for c in text)
        digit_ratio = digits / (letters + digits) if letters + digits else 0
        prose = is_prose_text(b, page_w)
        table_like = (
            not prose
            or (digit_ratio > 0.30 and '\n' in text and len(text) < 160)
        )
        if table_like:
            xs.append((b.bbox[0], b.bbox[2]))
    if not xs:
        return default_x0, default_x1
    x0 = min(default_x0, min(x[0] for x in xs) - 8)
    x1 = max(default_x1, max(x[1] for x in xs) + 8)
    return max(0, x0), min(page_w, x1)


def _trim_page_footer(page_blocks, page_rect, y_min, y_max):
    """Return a y_max trimmed to exclude trailing page numbers / running footers.
    Algorithm: find content blocks in [y_min, y_max] and return the max y3 of any
    block that is NOT a short text block in the bottom 8% of the page.
    """
    page_h = page_rect.height
    footer_zone = page_h * 0.92
    content_y_max = y_min
    for b in page_blocks:
        if b.bbox[1] < y_min - 2 or b.bbox[3] > y_max + 2:
            continue
        if b.kind == 'text':
            t = b.text.strip()
            # Page numbers / footers: very short text in bottom 8% of page
            if len(t) < 6 and b.bbox[1] >= footer_zone:
                continue
        content_y_max = max(content_y_max, b.bbox[3])
    if content_y_max <= y_min:
        return y_max - 4
    return min(content_y_max + 4, y_max - 4)


def page_is_figure_only(blocks, page_w):
    """Detect a page whose content is entirely figure (no body prose).
    Used for detecting multi-page figures where caption is on the last page."""
    has_image = any(b.kind == 'image' and
                    (b.bbox[2] - b.bbox[0]) > 100 and
                    (b.bbox[3] - b.bbox[1]) > 100 for b in blocks)
    if not has_image:
        return False
    # No prose blocks (only short labels / captions / page numbers)
    for b in blocks:
        if is_prose_text(b, page_w):
            return False
    return True


def find_multipage_figure_pages(doc, page_blocks, caption_pnum, max_pages_back=6):
    """Walk backwards from caption page to find all consecutive figure-only pages.
    Returns a list of page numbers (1-indexed) covered by the multi-page figure,
    INCLUDING the caption page (which may or may not contain figure content).
    The list is ordered from earliest to latest page.
    """
    pages = [caption_pnum]
    pn = caption_pnum - 1
    steps = 0
    while pn >= 1 and steps < max_pages_back:
        blocks = page_blocks.get(pn)
        if not blocks:
            break
        page_w = doc[pn - 1].rect.width
        if not page_is_figure_only(blocks, page_w):
            break
        pages.insert(0, pn)
        pn -= 1
        steps += 1
    return pages


def page_is_prompt_continuation(blocks, page_w):
    """A page that is part of an ongoing prompt example.
    Heuristic: text-only page (no figure/table caption, no section heading)
    where content has prompt/code markers OR bullet/instruction patterns.
    """
    if not blocks:
        return False
    text_blocks = [b for b in blocks if b.kind == 'text']
    if not text_blocks:
        return False
    caption_blocks = [b for b in text_blocks if CAPTION_RE.match(b.text)]
    if caption_blocks:
        # Some prompt figures span pages and begin immediately after the
        # previous figure's caption on the preceding page.
        # Figure 13 starts below Figure 12's caption on page 38 and continues
        # above its own caption on page 39. Treat only the post-caption tail as
        # candidate continuation content.
        last_caption = max(caption_blocks, key=lambda b: b.bbox[3])
        text_blocks = [
            b for b in text_blocks
            if b.bbox[1] >= last_caption.bbox[3] + 2
            and not CAPTION_RE.match(b.text)
        ]
        if not text_blocks:
            return False
    # No standalone section headings in the candidate continuation region.
    for b in text_blocks:
        if is_section_heading(b.text):
            return False
    # Content should look prompt-style: code markers, bullets, or special tokens
    full_text = '\n'.join(b.text for b in text_blocks)
    if CODE_MARKERS_RE.search(full_text):
        return True
    # Bullet / instruction patterns: lines starting with `- ` or `# Note` etc.
    if re.search(r'(?m)^\s*[-*]\s', full_text):
        return True
    if re.search(r'###\w+###', full_text):
        return True
    return False


def prompt_continuation_crop_bbox(blocks, page_rect):
    """Crop only the prompt-like continuation region on a page.

    If the page contains a previous caption, use text blocks after that caption.
    Otherwise use all prompt-like text blocks. This prevents multi-page prompt
    figures from accidentally including an earlier figure/caption or the next
    section. Added for cross-page prompt/template figures.
    """
    text_blocks = [b for b in blocks if b.kind == 'text']
    caption_blocks = [b for b in text_blocks if CAPTION_RE.match(b.text)]
    if caption_blocks:
        last_caption = max(caption_blocks, key=lambda b: b.bbox[3])
        text_blocks = [
            b for b in text_blocks
            if b.bbox[1] >= last_caption.bbox[3] + 2
            and not CAPTION_RE.match(b.text)
        ]
    else:
        text_blocks = [b for b in text_blocks if not CAPTION_RE.match(b.text)]
    text_blocks = [
        b for b in text_blocks
        if b.text.strip()
        and not is_section_heading(b.text)
        and not (len(b.text.strip()) < 6 and b.bbox[1] >= page_rect.height * 0.92)
    ]
    if not text_blocks:
        return (40, 50, page_rect.width - 40, page_rect.height - 50)
    x0 = max(0, min(b.bbox[0] for b in text_blocks) - 4)
    x1 = min(page_rect.width, max(b.bbox[2] for b in text_blocks) + 4)
    y0 = max(30, min(b.bbox[1] for b in text_blocks) - 4)
    y1 = _trim_page_footer(blocks, page_rect, y0, page_rect.height - 30)
    return (x0, y0, x1, y1)


def find_multipage_prompt_pages(doc, page_blocks, caption_pnum, max_pages_back=6):
    """Walk backwards from a prompt-like caption page to find consecutive
    prompt-continuation pages (text-only, no captions/headings, prompt-style
    content). Returns 1-indexed page numbers ordered earliest-to-latest.
    """
    pages = [caption_pnum]
    pn = caption_pnum - 1
    steps = 0
    while pn >= 1 and steps < max_pages_back:
        blocks = page_blocks.get(pn)
        if not blocks:
            break
        page_w = doc[pn - 1].rect.width
        if not page_is_prompt_continuation(blocks, page_w):
            break
        pages.insert(0, pn)
        pn -= 1
        steps += 1
    return pages


def render_multipage_figure(doc, src_pages, bboxes, dpi_scale=3.0):
    """Render multiple page regions and stitch them vertically into one PNG.
    Returns a PIL Image. Requires PIL to be installed.
    """
    if not HAS_PIL:
        return None
    if len(src_pages) == 1:
        page = doc[src_pages[0] - 1]
        pix = page.get_pixmap(matrix=fitz.Matrix(dpi_scale, dpi_scale),
                              clip=fitz.Rect(*bboxes[0]), alpha=False)
        return Image.frombytes('RGB', (pix.width, pix.height), pix.samples)

    images = []
    for pn, bbox in zip(src_pages, bboxes):
        page = doc[pn - 1]
        pix = page.get_pixmap(matrix=fitz.Matrix(dpi_scale, dpi_scale),
                              clip=fitz.Rect(*bbox), alpha=False)
        images.append(Image.frombytes('RGB', (pix.width, pix.height), pix.samples))

    total_h = sum(im.height for im in images) + (len(images) - 1) * 4  # 4px gap
    max_w = max(im.width for im in images)
    out = Image.new('RGB', (max_w, total_h), (255, 255, 255))
    y = 0
    for im in images:
        x = (max_w - im.width) // 2
        out.paste(im, (x, y))
        y += im.height + 4
    return out


def compute_figure_bbox(caption_block, page_blocks, page_rect,
                        prev_blocks=None, prev_rect=None,
                        min_dim=40):
    """
    Pick the larger gap (above or below) on this page that's tall enough.
    If neither is tall enough, fall back to previous page.
    Returns (page_offset, bbox) — page_offset is 0 for current, -1 for previous.

    Caption type bias:
    - Figure captions are typically BELOW the figure → prefer the above gap
    - Table captions are typically ABOVE the table → prefer the below gap
    """
    columns = detect_columns(page_blocks, page_rect.width)
    cap_text = caption_block.text.strip()
    # Prompt-like figures (e.g., "Figure N: The optimized user prompt for X")
    # have prose-style content as the figure body. Force loose mode so
    # is_prose_text doesn't shrink the gaps.
    is_table = bool(re.match(r'^[\s\u200b\[]*(?:Table|表)', cap_text, re.IGNORECASE))
    is_prompt_fig = (not is_table) and caption_is_prompt_like(cap_text)

    # Wrapfig detection: if the caption block starts significantly to the right
    # of the page margin, the figure/table is right-aligned with body text
    # wrapping on the left. Use the caption's x0 as the left bound for the crop
    # so that the wrapping body text is not included in the output PNG.
    # where body text appears left of the table.
    page_margin = 40
    cap_x0 = caption_block.bbox[0]
    if is_prompt_fig:
        constrained_x0 = page_margin
    elif cap_x0 > page_margin + page_rect.width * 0.10:
        constrained_x0 = max(page_margin, cap_x0 - 4)
    else:
        constrained_x0 = page_margin
    above_top, above_bot, below_top, below_bot = find_gaps(
        caption_block, page_blocks, page_rect, columns=columns, loose=is_prompt_fig)

    # Refine for stacked content disambiguation: when a Table caption sits ABOVE
    # its data and a Figure caption sits below the same region, both gap searches
    # collide. Walk content blocks to find the actual extent of THIS caption's data.
    if is_table:
        refined_below = refine_table_extent_below(
            page_blocks, below_top, below_bot, page_rect.width)
        if refined_below > below_top + 10:
            below_bot = min(below_bot, refined_below + 4)
    elif not is_prompt_fig:
        refined_above = refine_figure_extent_above(
            page_blocks, above_bot, above_top, page_rect.width)
        if refined_above < above_bot - 10:
            above_top = max(above_top, refined_above - 4)

    above_h = above_bot - above_top
    below_h = below_bot - below_top

    # Detect bundled-header captions: PyMuPDF sometimes glues a Table caption
    # together with the column header row in a single multi-line block (when
    # the visual gap between caption and header is tiny). In that case the
    # column header sits INSIDE the caption block, so excluding cap_bot would
    # lose the header.
    #
    # Distinguishing signal: bundled headers are MULTIPLE SHORT lines (one per
    # column), NOT a single long wrapped caption sentence. Pure wrapped captions
    # like "[Table N] long sentence wraps to\nanother long line ..." should
    # NOT trigger caption_bundled.
    caption_bundled = False
    if is_table and '\n' in cap_text:
        # The caption sentence usually fills the first line(s) and ends with '.'
        # The trailing column-header content sits as ≥ 2 short lines after that.
        # Heuristic: split entire block into lines, find lines that look like
        # short header cells (< 30 chars, no terminal '.').
        all_lines = [l.strip() for l in cap_text.split('\n') if l.strip()]
        # Skip the first line (caption start). Check if there are ≥ 2 short
        # tokens following that DO NOT look like prose continuation.
        short_header_lines = [
            l for l in all_lines[1:]
            if len(l) < 30 and not l.endswith('.') and not l.endswith(',')
        ]
        if len(short_header_lines) >= 2:
            caption_bundled = True

    # Look for embedded images in each gap
    imgs_above = collect_imgs_in_range(page_blocks, above_top, above_bot)
    imgs_below = collect_imgs_in_range(page_blocks, below_top, below_bot)

    # Detect MIMO-style tables where caption sits BELOW the table data.
    # Two complementary signals:
    #   1. region_has_table_content: ≥ 2 digit-heavy blocks in that region
    #   2. caption_data_proximity: distance to nearest digit-heavy block on each side
    # The proximity check handles single-row tables that the region check misses.
    above_has_table = is_table and region_has_table_content(
        page_blocks, above_top, above_bot)
    below_has_table = is_table and region_has_table_content(
        page_blocks, below_top, below_bot)
    above_dist, below_dist = (float('inf'), float('inf'))
    if is_table:
        above_dist, below_dist = caption_data_proximity(caption_block, page_blocks)
    table_caption_below_data = is_table and (
        (above_has_table and not below_has_table)
        or (above_dist < below_dist and above_dist < 30))

    # Score each candidate region. Prefer regions with embedded images, then
    # apply directional bias, then prefer the larger region.
    #
    # X-bound heuristic: if detected images cover ≥ 55% of column width, use
    # tight image x-bounds. If they cover less (some panels are vector-based PDF
    # paths and not detected as image objects), fall back to full column width.
    # Some figures have raster heatmaps on the right but
    # vector bar charts on the left — tight x would miss the left panels entirely.
    col_w = page_rect.width - 80  # approximate usable column width
    candidates = []  # (score, bbox)
    if above_h >= min_dim:
        if imgs_above:
            img_x0 = min(b.bbox[0] for b in imgs_above)
            img_x1 = max(b.bbox[2] for b in imgs_above)
            if img_x1 - img_x0 >= col_w * 0.55:
                # Images may be mixed raster/vector: PyMuPDF reports raster
                # blocks for icons/bars but nearby labels can sit just outside
                # that union. Keep a small pad so edge labels/panels survive.
                x0 = max(0, img_x0 - 8)
                x1 = min(page_rect.width, img_x1 + 8)
            else:
                x0, x1 = 40, page_rect.width - 40  # partial coverage → full col
            y0 = max(min(b.bbox[1] for b in imgs_above) - 4, above_top)
            y1 = above_bot - 2
            score = above_h + 1000  # bonus for having images
        else:
            x0 = constrained_x0
            x1 = page_rect.width - 40
            y0 = above_top + 4
            y1 = above_bot - 4
            if is_table:
                x0, x1 = refine_table_x_bounds(
                    page_blocks, y0, y1, page_rect.width, x0, x1)
            elif is_prompt_fig:
                x0, _, x1, _ = prompt_continuation_crop_bbox(
                    [b for b in page_blocks
                     if b.bbox[1] >= y0 - 2 and b.bbox[3] <= y1 + 2],
                    page_rect)
            score = above_h
        # Bias: figures prefer above (figure caption is below the figure).
        # Also: MIMO-style tables where caption sits BELOW the table.
        if not is_table:
            score += 500
        elif table_caption_below_data:
            score += 800  # strong preference: above has the actual table data
        candidates.append((score, (x0, y0, x1, y1)))

    # Skip the below candidate entirely when we're confident it's a MIMO-style
    # table (caption sits BELOW the data). Otherwise images in next figure's
    # region would win via the imgs_below +1000 bonus and produce wrong PNGs.
    if below_h >= min_dim and not table_caption_below_data:
        if imgs_below:
            img_x0 = min(b.bbox[0] for b in imgs_below)
            img_x1 = max(b.bbox[2] for b in imgs_below)
            if img_x1 - img_x0 >= col_w * 0.55:
                x0 = max(0, img_x0 - 8)
                x1 = min(page_rect.width, img_x1 + 8)
            else:
                x0, x1 = 40, page_rect.width - 40
            y0 = below_top + 2
            y1 = min(max(b.bbox[3] for b in imgs_below) + 4, below_bot)
            score = below_h + 1000
        else:
            x0 = constrained_x0
            x1 = page_rect.width - 40
            # When the caption block bundles the table header, start from
            # cap_top (with a small upward margin for font ascenders).
            y0 = (caption_block.bbox[1] - 4) if caption_bundled else (below_top + 4)
            # Trim trailing page numbers / footers from y1
            y1 = _trim_page_footer(page_blocks, page_rect, y0, below_bot)
            if is_table:
                x0, x1 = refine_table_x_bounds(
                    page_blocks, y0, y1, page_rect.width, x0, x1)
            elif is_prompt_fig:
                x0, _, x1, _ = prompt_continuation_crop_bbox(
                    [b for b in page_blocks
                     if b.bbox[1] >= y0 - 2 and b.bbox[3] <= y1 + 2],
                    page_rect)
            score = below_h
        if is_table:
            score += 500  # tables normally prefer below (caption-above-table)
        candidates.append((score, (x0, y0, x1, y1)))

    if candidates:
        candidates.sort(key=lambda c: -c[0])
        return 0, candidates[0][1]

    # Both gaps too small. Try previous page (figure occupies whole prev page).
    if prev_blocks is not None:
        prev_imgs = [b for b in prev_blocks if b.kind == 'image']
        # Filter out tiny ones (likely glyphs / icons)
        prev_imgs = [b for b in prev_imgs
                     if (b.bbox[2]-b.bbox[0]) > 80 and (b.bbox[3]-b.bbox[1]) > 80]
        if prev_imgs:
            x0 = min(b.bbox[0] for b in prev_imgs) - 4
            y0 = min(b.bbox[1] for b in prev_imgs) - 4
            x1 = max(b.bbox[2] for b in prev_imgs) + 4
            y1 = max(b.bbox[3] for b in prev_imgs) + 4
            return -1, (x0, y0, x1, y1)
        # No images on prev page either; probably a table that fits in the
        # tiny gap below caption — let's still return that even if small.

    # Last-resort: return whichever gap is larger even if small.
    if max(above_h, below_h) > 10:
        if below_h > above_h:
            return 0, (40, below_top + 2, page_rect.width - 40, below_bot - 2)
        return 0, (40, above_top + 2, page_rect.width - 40, above_bot - 2)
    return 0, None


def extract(pdf_path, out_dir, dpi_scale=3.0, debug=False):
    os.makedirs(out_dir, exist_ok=True)
    doc = fitz.open(pdf_path)

    page_blocks = {}
    for i in range(doc.page_count):
        page_blocks[i + 1] = get_blocks(doc[i])

    saved = []
    captions_meta = []  # for captions.json — feeds vision-verification workflow
    skipped = []  # (page, id, reason)
    seen_ids = set()  # dedupe captions that appear twice (e.g. table continued)

    for pnum in range(1, doc.page_count + 1):
        blocks = page_blocks[pnum]
        for blk in blocks:
            if blk.kind != 'text':
                continue
            m = CAPTION_RE.match(blk.text)
            if not m:
                continue
            fig_id = m.group(1).strip()
            slug = slugify(fig_id)
            # Skip duplicates (same ID seen on a previous page is the real one)
            if slug in seen_ids:
                if debug:
                    skipped.append((pnum, fig_id, 'duplicate (already seen)'))
                continue

            page = doc[pnum - 1]
            prev = page_blocks.get(pnum - 1)
            prev_rect = doc[pnum - 2].rect if pnum > 1 else None

            if debug:
                cols = detect_columns(blocks, page.rect.width)
                code_pg = is_code_example_page(blocks, page.rect.width)
                at, ab, bt, bb = find_gaps(blk, blocks, page.rect, columns=cols)
                print(f'  [debug] p{pnum} {fig_id}: cols={len(cols)}, code_page={code_pg}, '
                      f'above_h={ab-at:.0f}, below_h={bb-bt:.0f}', file=sys.stderr)

            offset, bbox = compute_figure_bbox(
                blk, blocks, page.rect,
                prev_blocks=prev, prev_rect=prev_rect)
            if bbox is None:
                if debug:
                    skipped.append((pnum, fig_id, 'no viable bbox'))
                continue

            src_idx = pnum - 1 + offset
            src_page = doc[src_idx]
            x0, y0, x1, y1 = bbox
            x0 = max(0, x0)
            y0 = max(0, y0)
            x1 = min(src_page.rect.width, x1)
            y1 = min(src_page.rect.height, y1)
            if x1 - x0 < 60 or y1 - y0 < 30:
                if debug:
                    skipped.append((pnum, fig_id,
                                    f'bbox too small: {x1-x0:.0f}x{y1-y0:.0f}'))
                continue

            # Check for multi-page figure: walk back from src page to find
            # earlier consecutive figure-only pages. For prompt-like captions,
            # use the prompt-continuation walk (text-only, no images required).
            is_prompt_fig = (not bool(re.match(
                r'^[\s\u200b\[]*(?:Table|表)', blk.text, re.IGNORECASE))
                and caption_is_prompt_like(blk.text))
            if is_prompt_fig:
                multipage_pages = find_multipage_prompt_pages(
                    doc, page_blocks, src_idx + 1)
            else:
                multipage_pages = find_multipage_figure_pages(
                    doc, page_blocks, src_idx + 1)

            try:
                if len(multipage_pages) > 1 and HAS_PIL:
                    # Build bbox list: earlier pages = full figure-only area,
                    # last page = computed bbox
                    bboxes_list = []
                    for mp in multipage_pages[:-1]:
                        mp_blocks = page_blocks[mp]
                        mp_page = doc[mp - 1]
                        mp_imgs = [b for b in mp_blocks if b.kind == 'image'
                                   and (b.bbox[2]-b.bbox[0]) > 100
                                   and (b.bbox[3]-b.bbox[1]) > 100]
                        if mp_imgs:
                            mx0 = min(b.bbox[0] for b in mp_imgs) - 4
                            my0 = min(b.bbox[1] for b in mp_imgs) - 4
                            mx1 = max(b.bbox[2] for b in mp_imgs) + 4
                            my1 = max(b.bbox[3] for b in mp_imgs) + 4
                            bboxes_list.append((max(0, mx0), max(0, my0),
                                                min(mp_page.rect.width, mx1),
                                                min(mp_page.rect.height, my1)))
                        elif is_prompt_fig:
                            bboxes_list.append(
                                prompt_continuation_crop_bbox(
                                    mp_blocks, mp_page.rect))
                        else:
                            bboxes_list.append((40, 50, mp_page.rect.width-40,
                                                mp_page.rect.height-50))
                    bboxes_list.append((x0, y0, x1, y1))
                    img = render_multipage_figure(doc, multipage_pages,
                                                  bboxes_list, dpi_scale)
                    fname = f'{slug}.png'
                    img.save(os.path.join(out_dir, fname))
                    saved.append((multipage_pages[0], fig_id, fname))
                    captions_meta.append({
                        'id': fig_id,
                        'slug': slug,
                        'filename': fname,
                        'caption_page': pnum,
                        'src_pages': multipage_pages,
                        'multipage': True,
                        'caption_text': blk.text.strip(),
                    })
                    if debug:
                        print(f'  [debug] p{pnum} {fig_id}: stitched {len(multipage_pages)} pages',
                              file=sys.stderr)
                else:
                    pix = src_page.get_pixmap(matrix=fitz.Matrix(dpi_scale, dpi_scale),
                                              clip=fitz.Rect(x0, y0, x1, y1),
                                              alpha=False)
                    fname = f'{slug}.png'
                    pix.save(os.path.join(out_dir, fname))
                    saved.append((src_idx + 1, fig_id, fname))
                    captions_meta.append({
                        'id': fig_id,
                        'slug': slug,
                        'filename': fname,
                        'caption_page': pnum,
                        'src_pages': [src_idx + 1],
                        'multipage': False,
                        'caption_text': blk.text.strip(),
                    })
                seen_ids.add(slug)
            except Exception as e:
                print(f'  ERROR rendering {fig_id} from page {src_idx+1}: {e}',
                      file=sys.stderr)

    # Write captions.json — manifest for vision-verification workflow
    import json as _json
    with open(os.path.join(out_dir, 'captions.json'), 'w', encoding='utf-8') as f:
        _json.dump({'pdf': os.path.basename(pdf_path), 'figures': captions_meta},
                   f, ensure_ascii=False, indent=2)

    if debug:
        print(f'\n[debug] Saved {len(saved)}, skipped {len(skipped)}', file=sys.stderr)
        for pn, fid, reason in skipped:
            print(f'  [skip] p{pn} {fid}: {reason}', file=sys.stderr)
    return saved


if __name__ == '__main__':
    args = [a for a in sys.argv[1:] if not a.startswith('--')]
    flags = [a for a in sys.argv[1:] if a.startswith('--')]
    if len(args) != 2:
        print('Usage: extract_figures.py <pdf> <output_dir> [--debug]', file=sys.stderr)
        sys.exit(1)
    pdf_path, out_dir = args
    debug = '--debug' in flags
    saved = extract(pdf_path, out_dir, debug=debug)
    print(f'Saved {len(saved)} figures to {out_dir}')
    for sp, fid, fn in saved:
        print(f'  page {sp:>3}: {fid:>22}  ->  {fn}')
