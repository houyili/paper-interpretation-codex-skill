# Figure Extractor 调试小抄

当 `extract_figures.py` 漏抓 figure 或抓得不准时用这些 snippet 排错。

## 1. 检查 PDF 总览

```python
import fitz
doc = fitz.open('/path/to/paper.pdf')
print(f'Total pages: {doc.page_count}')
total_imgs = 0
for i in range(doc.page_count):
    imgs = doc[i].get_images(full=True)
    if imgs:
        total_imgs += len(imgs)
print(f'Total embedded images: {total_imgs}')
```

少量嵌入图 + 大量 vector content → 完全依赖 caption 检测
大量嵌入图 → extractor 优先用 image bbox

## 2. 列出某页所有的 text/image blocks

```python
import fitz
doc = fitz.open('/path/to/paper.pdf')
page = doc[N-1]  # page N
print(f'Page {N} size: {page.rect}')
for b in page.get_text('dict')['blocks']:
    if b['type'] == 0:
        text = ''.join(span['text'] for line in b['lines'] for span in line['spans'])
        text = text.replace('\u200b', '').strip()
        print(f'  T y={b["bbox"][1]:.0f}-{b["bbox"][3]:.0f} ({len(text)}c): {text[:80]!r}')
    elif b['type'] == 1:
        print(f'  I y={b["bbox"][1]:.0f}-{b["bbox"][3]:.0f}: {b["bbox"]}')
```

## 3. 找所有看起来像 caption 的文字（不管 regex 是否匹配）

```python
import fitz, re
doc = fitz.open('/path/to/paper.pdf')
for p in range(doc.page_count):
    page = doc[p]
    for b in page.get_text('dict')['blocks']:
        if b['type'] != 0:
            continue
        text = ''.join(span['text'] for line in b['lines'] for span in line['spans'])
        text = text.replace('\u200b', '').strip()
        if re.search(r'(Figure|Table|Fig\.)\s*\d', text[:30], re.IGNORECASE):
            print(f'p{p+1} y={b["bbox"][1]:.0f}-{b["bbox"][3]:.0f}: {text[:120]!r}')
```

如果输出里有 caption 但 extractor 没抓到，问题在 caption regex 或 prose detection。

## 4. 跟踪某个具体 caption 的 bbox 计算

```python
import sys
sys.path.insert(0, '/path/to/skill/scripts')
from extract_figures import get_blocks, find_gaps, compute_figure_bbox, CAPTION_RE
import fitz

doc = fitz.open('/path/to/paper.pdf')
p = N  # target page
blocks = get_blocks(doc[p-1])
prev = get_blocks(doc[p-2]) if p > 1 else None

for b in blocks:
    if b.kind != 'text':
        continue
    m = CAPTION_RE.match(b.text)
    if not m:
        continue
    print(f'CAPTION: {m.group(1)!r}')
    at, ab, bt, bb = find_gaps(b, blocks, doc[p-1].rect)
    print(f'  above: y={at:.0f}-{ab:.0f}, h={ab-at:.0f}')
    print(f'  below: y={bt:.0f}-{bb:.0f}, h={bb-bt:.0f}')
    offset, bbox = compute_figure_bbox(b, blocks, doc[p-1].rect, prev_blocks=prev)
    print(f'  result: offset={offset}, bbox={bbox}')
```

## 5. 常见问题与修复

### Caption regex 不匹配

- 缺少分隔符：检查原文是 `Figure 1: ...` 还是 `Figure 1. ...` 还是 `[Figure 1] ...`，确保 regex 的 `[\]:.\u2014\u2013-]` 涵盖
- 中文论文：caption 可能是 `图 1` / `表 1`，需要扩展 regex
- 字母后缀格式：`Figure 4.5.5.1.A` 用 `\d+(\.\d+)*(\.[A-Z]\d*)?`

### 图被正文文字"挤掉"

症状：above_h 和 below_h 都很小（5-20px）→ 返回 -1 去找 prev page 但 prev 也没有合适的图。

原因：`is_prose_text` 把图周围的轴标签 / 表头当成了 prose。

修复：调整 `is_prose_text` 的阈值：
- 提高 `len(text) < 60` 的阈值 → 允许更短的文字算 prose
- 提高 `avg_line_len < 18` 的阈值 → 允许更短的行算 prose
- 但提得太高会错过真正的段落

或者：增加专门的 figure 内部文字检测（如检测短数字 "85", "0.5"）

### 抓到的图含相邻段落 / caption 文字

症状：output PNG 的顶部或底部有一行无关文字。

原因：margin 太大，或 prev_text_bottom 检测有偏。

修复：减小 margin，或加 zero-width space 过滤。当前版本已设 margin = 2，应该够用。

### 多页 figure（caption 在下一页）

症状：page N 是空白图，page N+1 caption 被检测但 bbox 错。

修复：当前版本已支持，offset = -1 去找 prev page 的 image union。如果 prev page 都是 vector（无 image block），需要额外逻辑。

### Prompt/template figure 被裁错或跨页漏拼

症状：caption 数量对得上，但 PNG 只包含 prompt 右半边、左边界被裁掉，或跨页 prompt 的第一页被替换成上一张图的 caption / 下一节标题。

典型模式：宽 prompt/template 图不能用居中的 caption `x0` 当左边界；跨页 prompt 图可能从前一页的前一个 caption 之后开始，并在下一页自己的 caption 之前结束。

修复方向：
- prompt-like caption（prompt, template, listing, sample dialogue 等）不要套用 wrapfig 的 caption-x 裁剪。
- 回溯跨页 prompt 时，如果上一页有 caption，只把最后一个 caption 之后的 prompt-like text blocks 当作候选 continuation。
- 视觉核验时打开 source page，对照 PNG 开头/结尾，确认没有漏掉跨页开头或包含后续 section heading。

## 6. 批量重新抽取 + 对比

```bash
mkdir -p /tmp/test_figs
python3 <skill_dir>/scripts/extract_figures.py \
    /path/to/paper.pdf /tmp/test_figs

# 列出抓到的 figure
ls /tmp/test_figs

# 检查特定 figure
ls /tmp/test_figs | rg -i 4_5  # all figures from section 4.5
```
