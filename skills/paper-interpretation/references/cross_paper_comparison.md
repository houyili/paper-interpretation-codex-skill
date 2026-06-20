# 跨论文 Benchmark 对比的方法论

当解读涉及“model A vs model B vs model C”的跨论文对比时，不要直接把数字搬到同一张表里。不同论文即使报告同一个 benchmark，也可能使用不同 harness、tool setting、model version、trial count、thinking budget 或数据来源。

## 写对比表前必须确认的 5 件事

### 1. Harness 是否一致

Harness 指模型如何被调用、如何与环境交互、是否有 evaluator wrapper、timeout、retry、sandbox、browser、terminal、accessibility tree 等配置。同一个 benchmark 换 harness 后，分数可能差很多。

处理方式：

- 表头或脚注写清 harness。
- harness 不一致时不要直接排序；必须用 `*` 或 footnote 标出。
- 如果论文只给聚合分数，说明“该数字不保证与其他论文直接可比”。

### 2. Tools 是否一致

区分 no-tools、Python/tool-use、web/browser、image-cropping、terminal、IDE agent 等 setting。不要把 with-tools 的数字和 no-tools 的数字直接比较。

推荐表头：

```markdown
| Model | Benchmark (no tools) | Benchmark (with tools) |
|---|:---:|:---:|
| A | 56.8% | 64.7% |
| B | 39.8% | 52.1% |
```

### 3. Self-Reported 还是 Independent

Self-reported 是模型团队在论文、system card 或 blog 中报告的数字；independent 是第三方复现、评测平台或 benchmark maintainers 的数字。两者都可以引用，但必须标注来源。

处理方式：

- 在脚注里标注 `self-reported`、`independent`、`third-party`。
- 不要用第三方数字覆盖模型团队自报数字，也不要反过来；并列保留更诚实。

### 4. 模型版本号是否完全一致

同名模型、preview、checkpoint、API date、thinking mode、tool stack 都可能不同。跨论文表格必须写清具体版本。

处理方式：

- 表头、表注或正文中写清 model version。
- 版本不一致时，用 “not directly comparable” 标记。
- 不要把 “model family” 当成同一个 model checkpoint。

### 5. Thinking Budget / 推理深度是否一致

Reasoning models 的分数常受 thinking budget、effort level、token cap、parallel samples、best-of-N 或 majority vote 影响。

处理方式：

- 表头注明 `max effort`、`medium effort`、`fixed budget`、`adaptive budget` 等。
- 如果 budget 不明，明确写“budget not specified”。

## 标准跨论文表结构

```markdown
> **Sources**:
> - Paper A: official report, standard harness, no tools.
> - Paper B: independent evaluation, tool-use setting.
>
> **Caveats**:
> 1. Model versions differ across sources.
> 2. Benchmark harness differs for rows marked `*`.
> 3. `—` means not reported, not zero.

| Benchmark | Model A | Model B | Model C |
|---|:---:|:---:|:---:|
| SWE-bench Verified | 80.8 | 77.8* | — |
| HLE (no tools) | 40.0 | 30.5 | 43.9 |
```

关键元素：

- 列出所有数据来源。
- 写明 caveats：版本、harness、tool setting、trial count。
- 表头包含条件：no tools、with tools、averaged over N trials、max effort 等。
- 明确 `—`、`*`、bold、rank marker 的含义。

## 推荐表达

避免：

- “X 比 Y 强。”
- “X 在所有 benchmark 上领先。”
- “A 的 coding 能力弱于 B。”如果 harness/version 不一致，这句话风险很高。

推荐：

- “在同一 harness 和 no-tools setting 下，X 比 Y 高 6 percentage points。”
- “这个分数来自 self-reported official run；另一个来源使用 independent harness，因此不直接可比。”
- “排除 tool setting 差异后，当前证据只支持 X 在该 benchmark 的该 setting 下领先。”

## 简化 Checklist

- [ ] 每个数字都能定位到来源论文/博客/报告吗？
- [ ] 每个数字的 harness、tools、trial setup 清楚吗？
- [ ] 模型版本号一致吗？不一致是否标注？
- [ ] 表头或表注是否写明 condition？
- [ ] 是否区分 self-reported 和 independent？
- [ ] 排名或结论是否只在可比条件内成立？
