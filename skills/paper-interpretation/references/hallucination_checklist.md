# Hallucination Checklist — 写完每个 sub-section 后必跑

这不是泛泛地要求“零幻觉”，而是针对论文全文翻译和 grounded interpretation 的机械检查清单。每个 section/subsection 写完后都要跑一遍。

## 0. 段落覆盖完整性

**陷阱**：把原文 3-5 段压成 1 段“本节说明……”，这不是全文翻译。

**第二陷阱**：沿用旧式论文解读模板，把文件写成“全文翻译与论文解读”，开头放“一句话总结 / 为什么读这篇 / 关键观察 / 核心主张”，正文实际是章节总结。这也不是全文翻译。

**检查**：

- 对当前 source chunk 数原文段落/列表项数量。
- 输出中应有对应的中文段落/列表项；如果合并了短段，必须没有丢失 claim、数字、条件和 caveat。
- 译后注、关键观察、总结不能替代译文主体。
- 对最终 Markdown 跑：

```bash
rg -n '一句话总结|为什么读这篇|关键观察|核心主张|全文翻译与论文解读|章节总结' output.md
```

任何命中都必须人工确认只是译后补充，而不是主体结构。

## 1. 数字精度一致性

**陷阱**：把 `83.0%` 写成 `83%`，或把 `94.55%` 写成 `94.5%`，或把 `1,672` 写成 `1672`。

**检查**：

- 用 `rg` 搜索自己写的 Markdown 里的所有百分比和大数字。
- 回原文核对；如果原文写 `83.0%`，译文也应保留 `83.0%`。
- 不要主动四舍五入，除非你明确说明这是近似值。

## 2. 数字归属

**陷阱**：把 model A 的数字配给 model B，或把 ablation 的数字写成 main result。

**检查**：每个关键数字都回原文找到所在句子，确认主语、setting、表格行列和单位。

## 3. 数据来源

**陷阱**：把 self-reported、independent、third-party reproduction 的数字混为一谈。

**检查**：跨论文对比时给每个数字标注来源；表格里加 footnote 或在数字旁加 `(self)`、`(independent)`、`(third-party)`。

## 4. 范围限定词

**陷阱**：模糊掉关键 condition，例如：

- 是哪个 split、task subset、difficulty bucket？
- 是 with tools 还是 no tools？
- 是 averaged over N trials、best-of-N，还是 single run？
- 是 full model、smaller model，还是 ablation variant？

**检查**：每个数字旁边必须有 condition 的限定词，至少在表头、图注翻译或前文交代过。

## 5. 引文完整性

**陷阱**：把原文改写后放在 `>` blockquote 里，读者会误以为这是直接引用。

**检查**：每个 `> "..."` 必须从原文复制粘贴且一字不差。如果是改写，去掉引号和 blockquote。

## 6. 列表 / Bullet 数量核验

**陷阱**：原文有 5 条 key findings，译文只列了 3 条；原文 17 个 aspects，译文写成“几个 aspects”。

**检查**：写完任何 numbered list 或 bullet list 后，回原文数一遍。如果原文是 N 条，译文也应该是 N 条；如果只列代表性项目，必须明确写“以下是其中 3 条”。

## 7. Figure 描述与图内容一致

**陷阱**：caption 里写“左面板展示 X，右面板展示 Y”，但实际图没有左右面板，或者左右调换。

**检查**：写完 figure caption 后，用 `view_image` 看真实 PNG，逐项核对：

- panel 数量。
- 每个 panel 的标题。
- 关键数值、柱状图高度、曲线趋势。
- 颜色编码、legend、axis label。

## 7.5 Figure/Table 覆盖与 Caption 翻译

**陷阱**：正文翻译了，但漏掉 Figure 7、Appendix Table 3，或者只写“图 1 展示框架”而没有翻译原始 caption。

**检查**：

- 对照 `captions.json` 列出的每个 figure/table。
- 每个纳入范围的项目都应有：Markdown 引用或表格、编号、caption 中文翻译、grounding note、视觉校验状态。
- 如果某个 figure/table 不译，必须明确写出 omission reason。
- 文件数量一致不算通过；用 `view_image` 或 contact sheet 检查 crop 是否完整。

## 7.6 Table Crop 边缘完整性

**陷阱**：表格 PNG 存在，但左侧 Method/model 列被裁掉，或者右侧最后一个 metric 列被裁掉；另一种相反错误是为了扩边把旁边正文也裁进表格。

**检查**：

- 每个 `Table_*.png` 都确认 first column 和 last metric column 可见。
- 对 right-side wrap table，确认 crop 不包含左侧正文段落。
- 如果 `extract_tables.py` 返回 0 而 `captions.json` 有 Table，必须走 image fallback 并写明视觉状态。

## 7.7 公式重排与变量归属

**陷阱**：PDF text extraction 把公式拆成多行，导致 `W_V W_O`、上下标、矩阵形状或 equation number 错乱；直接复制会让数学含义变错。

**检查**：

- 对每个 display equation，回 PDF 页面或 page PNG 视觉核对。
- 保留原 equation number，例如 `(6)` 或 `\tag{6}`。
- 确认变量归属不变：哪个 head、哪个 token、哪个 matrix、哪个 score。
- 如果 raw text 和视觉公式冲突，以 PDF 视觉布局为准，并在必要时写 grounding note。

## 8. 因果 vs 相关

**陷阱**：把 “authors observe X coincides with Y” 写成 “authors prove X causes Y”。

**检查**：原文用 `correlated`、`coincides with`、`we observe`、`is associated with` 时，不能翻成“导致”“证明”“使得”，除非原文明确建立 causal claim。

## 检查方式

写完 sub-section 后，对照以上各项逐项自检。如果不确定哪项有问题：

```bash
# 找所有百分比和大数字
rg '\d+(\.\d+)?%|\d{3,}' your_section.md

# 找所有引文
rg '^> "' your_section.md
```

然后对每条 `rg` 命中，回原文 `/tmp/paper_full.txt` 或 `/tmp/paper_paragraphs.md` 验证。

## 不需要追求 100% 精确的场景

- 译后注中的高层解释句。
- 明确标为 commentary 的直觉判断。
- 跨章节的主观导航句。

但凡涉及段落覆盖、数字、引文、归属、范围、图表 caption、公式变量，都必须过检查。
