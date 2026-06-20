# Caption Regex 设计与变体

## 默认 regex（英文论文）

```python
CAPTION_RE = re.compile(
    r'^[\s\u200b\[]*'                                           # leading whitespace / [
    r'((?:Figure|Table|Fig\.)\s*\d+(?:\.\d+)*(?:\.[A-Z]\d*)?)'  # ID
    r'[\s\u200b]*([\]:.\u2014\u2013-])',                        # required separator
    re.IGNORECASE,
)
```

### 各组件解释

| 组件 | 含义 | 例子 |
|---|---|---|
| `^[\s\u200b\[]*` | 行首允许有空白或 `[` | `[Figure...` 或 `   Figure...` |
| `(?:Figure\|Table\|Fig\.)` | 关键词（不捕获组） | `Figure`, `Table`, `Fig.` |
| `\s*` | 可选空白 | `Figure 1` 或 `Figure1` |
| `\d+(?:\.\d+)*` | 主编号 + 任意层级子编号 | `1`, `1.2`, `4.5.5.1` |
| `(?:\.[A-Z]\d*)?` | 可选字母后缀（带可选数字） | `.A`, `.B`, `.A1` |
| `[\s\u200b]*` | 可选 ws / zero-width space | |
| `[\]:.\u2014\u2013-]` | **必需的分隔符** | `:`, `]`, `.`, `—`, `–`, `-` |

### 为什么需要分隔符

避免匹配正文里的引用：
- ✓ `Figure 1: Results of...` → 匹配 → 是 caption
- ✓ `[Figure 4.5.5.1.A] Per-turn...` → 匹配 → 是 caption
- ✗ `Figure 1 shows the results...` → 不匹配（空格不是分隔符）→ 是 in-text reference
- ✗ `as shown in Figure 2 above...` → 不匹配 → 是 in-text reference

## 中文论文变体

```python
CAPTION_RE_ZH = re.compile(
    r'^[\s\u200b]*'
    r'((?:图|表|Figure|Table|Fig\.)\s*\d+(?:\.\d+)*(?:\.[A-Z]\d*)?)'
    r'[\s\u200b]*([:：.。\u2014\u2013\-]|\s)',
    re.IGNORECASE,
)
```

**注意**：中文论文常用全角冒号 `：` 和句号 `。`，需要加进分隔符集合。

## 仅 Figure / 仅 Table 的 variant

如果只想抓 Figures：

```python
FIGURE_ONLY_RE = re.compile(
    r'^[\s\u200b\[]*'
    r'((?:Figure|Fig\.)\s*\d+(?:\.\d+)*(?:\.[A-Z]\d*)?)'
    r'[\s\u200b]*([\]:.\u2014\u2013-])',
    re.IGNORECASE,
)
```

## 带子编号字母的特殊格式

某些论文用 `Figure 1a`、`Figure 1b`（无点号）：

```python
CAPTION_RE_INLINE_LETTER = re.compile(
    r'^[\s\u200b\[]*'
    r'((?:Figure|Table|Fig\.)\s*\d+(?:\.\d+)*[a-z]?)'  # allow trailing lowercase letter
    r'[\s\u200b]*([\]:.\u2014\u2013-])',
    re.IGNORECASE,
)
```

## "Equation" / "Algorithm" 也想抓

```python
CAPTION_RE_EXTENDED = re.compile(
    r'^[\s\u200b\[]*'
    r'((?:Figure|Table|Fig\.|Equation|Eq\.|Algorithm|Alg\.)\s*\d+(?:\.\d+)*(?:\.[A-Z]\d*)?)'
    r'[\s\u200b]*([\]:.\u2014\u2013-])',
    re.IGNORECASE,
)
```

## 测试 regex 的快速方法

```python
import re
RE = re.compile(r'^[\s\u200b\[]*((?:Figure|Table|Fig\.)\s*\d+(?:\.\d+)*(?:\.[A-Z]\d*)?)[\s\u200b]*([\]:.\u2014\u2013-])', re.IGNORECASE)

test_cases = [
    '[Figure 4.5.5.1.A] Per-turn evaluation...',  # ✓
    'Figure 1: Results on the benchmark...',      # ✓
    'Figure 1 shows the results...',              # ✗
    'as shown in Figure 2 above',                 # ✗
    'Table 6.3.A — Capability Summary...',        # ✓
]
for t in test_cases:
    m = RE.match(t)
    print(f'{"✓" if m else "✗"} {t[:60]} → {m.group(1) if m else None}')
```
