# Sub-Section 段落级全文翻译模板

一个 sub-section 的默认目标是**翻译完整原文内容**，不是把原文压缩成要点。

## 必备元素

每个 `###` 或 `####` 小节必须包含：

1. **小节标题**：保留英文标题，可加中文解释。
2. **段落级译文**：以 `reconstruct_pdf_paragraphs.py` 的 paragraph ids 为准；每个重建后的原文段落对应一个中文段落；允许段落级意译，但不得省略信息。
3. **全文上下文**：翻译本小节前回看 `paper_global_context.md`，确认该小节在全文论证中的作用、术语决策、figure/table 证据链和关键数字归属。
4. **术语保留**：关键学术词、方法名、变量、公式、benchmark、数据集和模型名保留英文。
5. **图表插入**：原小节涉及的 Figure/Table 紧贴相关段落插入。
6. **caption 翻译**：完整翻译原始 caption，不只写“图 X 展示结果”。
7. **Grounding note**：说明图/表内容、关键数字/趋势、视觉校验状态。
8. **译后注（可选）**：只用于解释背景、术语或 caveat；不得替代译文。

## 模板

~~~markdown
### {section number} {English Title} / {中文标题}

<!-- source: P00XX-P00YY; pages: N-M -->
<!-- global-context: checked terms / section role / figure-table evidence before translation -->

{原文第 1 段的中文段落级翻译。保留关键 English terms，并覆盖原段落所有条件、数字、限定词和 caveats。}

{原文第 2 段的中文段落级翻译。不要压缩成 bullet，除非原文就是列表。}

{如果原文有公式，保留原公式 / 变量定义，并在下一段翻译解释。}

![Figure X - {中文短标题}](figures/Figure_X.png)

**Figure X caption 翻译**：{完整翻译原始 caption。}

**视觉校验 / Grounding note**：{OK/SUSPICIOUS/BROKEN；说明图中 panel、坐标轴、颜色、关键数字、趋势和正文结论如何对应。}

| {列1} | {列2} | {列3} |
|---|---:|---:|
| {row} | **{key value}** | {row} |

**Table X caption 翻译**：{完整翻译原始 caption。}

**表格 Grounding note**：{解释列含义、最佳值、异常值和实验条件。}

**译后注（可选）**：

- {只写能帮助理解的 grounding / caveat / 术语说明。}
~~~

## 长度与拆分

| 原文范围 | 写法 |
|---|---|
| 1-2 页 | 一个小节内逐段翻译，图表就地插入 |
| 3-5 页 | 保持段落翻译；可用 `####` 按原文逻辑分组 |
| 5-8 页以上 | 必须拆成多个 translation chunks，避免漏段 |

## 禁止模式

### ❌ 摘要代替翻译

```markdown
### 3.2 Results

本节说明人类预训练很重要，平均成功率提高了。
```

问题：丢失实验设置、baseline、task-by-task 结果、数字条件和 caveat。

### ✅ 段落级翻译

```markdown
### 3.2 Large-Scale Human Pretraining Is Key...

为评估大规模人类预训练和 aligned mid-training 对策略学习效率的影响，作者比较了四个 checkpoint：（1）从零训练的模型，（2）只在 aligned human-robot play dataset 上预训练的模型，（3）在大规模人类数据上预训练的模型，以及（4）先经过 human pretraining、再经过 aligned human-robot mid-training 的模型。对每个 checkpoint，论文同时报告 task completion score 和 absolute success rate。

结果汇总在 Figure 4。跨所有任务，human pretraining 相比从零训练带来稳定且显著的性能收益，平均 task completion 提升超过 **55%**。值得注意的是，虽然 large-scale human pretraining 的数据是 noisy、unconstrained、且没有与具体任务或传感器对齐，它已经在大多数任务上超过 mid-training-only baseline。
```

特点：完整覆盖原段落信息，保留英文术语，关键数字加粗，未把原文压缩成一句话。
