# {论文标题}_全文翻译

> **论文**：{Full Title}  
> **作者**：{Authors / Org}  
> **发表**：{arXiv ID / venue}, {date}  
> **页数**：{N pages}  
> **源文件**：{PDF path or URL}  
> **生成说明**：段落级全文翻译；关键学术术语保留英文；图表 caption 已翻译并做 grounding。
> **段落依据**：正文翻译基于 `reconstruct_pdf_paragraphs.py` 生成的 paragraph ids；raw TXT 仅作搜索辅助。
> **全文理解依据**：翻译前先建立 `paper_global_context.md`，统一论文主线、术语、图表证据链、关键数字和 appendix 覆盖策略；该上下文不替代逐段译文。

---

## 翻译与 Grounding 规则

- 本文是**段落级全文翻译**，不是章节摘要。
- 翻译基于全文理解：先读完整 paper context，再逐段翻译；全文理解只用于保持术语、指代、证据链和图表位置一致，不能压缩或替代原文段落。
- 中文为主，保留关键英文术语、变量、公式、模型名、数据集名和 benchmark 名。
- 每张 Figure/Table 均保留编号、图片/表格、caption 中文翻译和视觉 grounding note。
- References 默认不逐条翻译；如需参考文献注释，请另行生成。

---

## Abstract / 摘要全文翻译

<!-- source: P0001-P000X; pages: 1 -->

{逐段翻译 Abstract。每个原文段落对应一个中文段落；不要只总结。}

**译后注 / Grounding**：

- {可选：说明 abstract 的核心贡献、关键数字和 caveat。}

---

## 第 1 章：{Chapter 1 Title}

### 1.1 {Section Title}

<!-- source: P00XX-P00YY; pages: N-M -->

{逐段翻译该小节。每个原文段落都要覆盖完整信息。}

![Figure X - {中文短标题}](figures/Figure_X.png)

**Figure X caption 翻译**：{完整翻译原始 caption。}

**视觉校验 / Grounding note**：{说明图像是否校验通过、图中 panel/曲线/柱状图/流程图对应什么、关键数字或趋势是什么。}

**译后注**：

- {可选：只在需要时解释术语、实验条件或重要 caveat。}

### 1.2 {Section Title}

{继续逐段翻译。}

---

## 第 2 章：{Chapter 2 Title}

### 2.1 {Section Title}

{逐段翻译。}

| {列1} | {列2} | {列3} |
|---|---:|---:|
| {row} | **{key value}** | {row} |

**Table X caption 翻译**：{完整翻译原始 table caption。}

**表格 Grounding note**：{说明列含义、关键数字、best/second-best、条件和 caveat。}

---

## Acknowledgement / 致谢全文翻译

{如果论文有致谢，逐段翻译。}

---

## Appendix A：{Appendix Title}

{逐段翻译 appendix。不要因为是附录就只总结。}

---

## References / 参考文献说明

默认未逐条翻译 References。原文参考文献位于 PDF 第 {N-M} 页；如果需要，可另行生成逐条中文注释版。

---

## 全文 Grounding Checklist

- [ ] Abstract、正文、致谢、附录均已覆盖。
- [ ] 每个原文段落都有对应中文段落或明确合并说明。
- [ ] 未把旧式解读稿当作全文翻译交付：`一句话总结`、`为什么读这篇`、`关键观察`、`核心主张`、`全文翻译与论文解读` 等如出现，只能是译后补充，不能替代正文。
- [ ] 每张 Figure/Table 均有图片/表格、caption 翻译、grounding note。
- [ ] 所有图片相对路径存在。
- [ ] 关键数字已抽样回原文核对。
- [ ] 重要相关性没有被翻成因果关系。
