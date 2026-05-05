# RAG评测脚本使用教程

## 1. 目的

本目录下提供 3 个快速评测脚本：

- `eval_recall.py`
  用于评估 5 路联合检索的召回表现，统计 `Top1 / Top3 / Top5`。
- `eval_precision.py`
  用于先生成有 RAG 的回答，再对回答做精确率评估。
- `eval_hallucination.py`
  用于生成无 RAG 回答，并与有 RAG 回答做幻觉率对比。

公共逻辑在：

- `rag_eval_common.py`


## 2. 当前执行约束

为了控制资源消耗与 token 风险，当前脚本按以下规则执行：

- 检索阶段不并行。
- LLM 阶段当前实现也不并行。
- 因此当前实现天然满足“检索不能并行；LLM 并行最多 10 个实体”的要求。

如果以后要改成并行：

- 检索并行度必须保持为 `1`。
- LLM 并行度上限必须小于等于 `10`。


## 3. 建议运行环境

建议使用 WSL 里的 Python 运行，而不是 Windows 自带的 `python.exe` 别名。

示例：

```bash
wsl
cd /mnt/e/AI/Learning-Platform/Lianjue_Backend
python3 --version
```

如果你的依赖在 conda 环境中，也可以先激活：

```bash
wsl
cd /mnt/e/AI/Learning-Platform/Lianjue_Backend
conda activate lianjue
python3 --version
```


## 4. 输入与输出

默认输入测试用例文件：

- `测试用例.md`

默认输出目录：

- `scripts/eval_outputs/`

常见输出文件：

- `recall_eval.json`
- `recall_eval.md`
- `precision_top1.json`
- `precision_top1.md`
- `precision_top3.json`
- `precision_top3.md`
- `precision_summary.md`
- `hallucination_eval.json`
- `hallucination_eval.md`


## 5. 核心参数

三个脚本都支持以下思路：

- 用 `--phase` 拆分“生成阶段”和“judge 阶段”。
- 用 `--offset` + `--limit` 控制一次只跑一段测试用例。
- 用 `--append` 把这一段结果并入已有总结果文件。
- 用 `--batch-size 20` 控制每一批处理与落盘的条数。

常用参数说明：

- `--graph-name`
  图谱名称。`eval_recall.py` 和 `eval_precision.py` 必填。
- `--phase`
  可选值取决于脚本：
  - `eval_recall.py`: `retrieve | judge | all`
  - `eval_precision.py`: `generate | judge | all`
  - `eval_hallucination.py`: `generate | judge | all`
- `--offset`
  从第几条开始取。
- `--limit`
  本次最多取多少条。
- `--append`
  将本次结果合并进已有结果文件，而不是覆盖。
- `--batch-size`
  每批处理多少条。建议保持 `20`。


## 6. 推荐工作流

建议按 20 条一组完整推进。

总共 50 条测试用例时，可分成 3 组：

- 第 1 组：`offset=0 limit=20`
- 第 2 组：`offset=20 limit=20`
- 第 3 组：`offset=40 limit=20`

推荐顺序：

1. 先跑召回检索阶段。
2. 再跑精确率生成阶段。
3. 再跑幻觉率生成阶段。
4. 最后在确认前面结果都已落盘后，再分组跑 judge。

这样即使中途 token 不够，前面的原始结果也已经保住。


## 7. 召回率脚本

### 7.1 只做检索，不做 judge

第 1 组：

```bash
python3 scripts/eval_recall.py --graph-name RAG --phase retrieve --offset 0 --limit 20 --batch-size 20 --append
```

第 2 组：

```bash
python3 scripts/eval_recall.py --graph-name RAG --phase retrieve --offset 20 --limit 20 --batch-size 20 --append
```

第 3 组：

```bash
python3 scripts/eval_recall.py --graph-name RAG --phase retrieve --offset 40 --limit 20 --batch-size 20 --append
```

这一步结束后，`recall_eval.json` 里会先保存检索结果，但还没有最终召回率统计。


### 7.2 最后再做 judge

第 1 组：

```bash
python3 scripts/eval_recall.py --graph-name RAG --phase judge --offset 0 --limit 20 --batch-size 50 --append
```

第 2 组：

```bash
python3 scripts/eval_recall.py --graph-name RAG --phase judge --offset 20 --limit 20 --batch-size 20 --append
```

第 3 组：

```bash
python3 scripts/eval_recall.py --graph-name RAG --phase judge --offset 40 --limit 20 --batch-size 50 --append
```

完成后查看：

- `scripts/eval_outputs/recall_eval.json`
- `scripts/eval_outputs/recall_eval.md`


## 8. 精确率脚本

### 8.1 先生成有 RAG 的回答

第 1 组：

```bash
python3 scripts/eval_precision.py --graph-name RAG --phase generate --top-k 1 3 --offset 0 --limit 20 --batch-size 20 --append
```

第 2 组：

```bash
python3 scripts/eval_precision.py --graph-name RAG --phase generate --top-k 1 3 --offset 20 --limit 20 --batch-size 20 --append
```

第 3 组：

```bash
python3 scripts/eval_precision.py --graph-name RAG --phase generate --top-k 1 3 --offset 40 --limit 20 --batch-size 20 --append
```

完成后会得到：

- `precision_top1.json`
- `precision_top1.md`
- `precision_top3.json`
- `precision_top3.md`

其中 `.md` 文件里已经有你要的回答表：

- `编号`
- `测试用例内容`
- `回答内容`


### 8.2 最后再做 judge

第 1 组：

```bash
python3 scripts/eval_precision.py \
  --graph-name YOUR_GRAPH_NAME \
  --phase judge \
  --top-k 1 3 \
  --offset 0 \
  --limit 20 \
  --batch-size 20 \
  --append
```

第 2 组：

```bash
python3 scripts/eval_precision.py \
  --graph-name YOUR_GRAPH_NAME \
  --phase judge \
  --top-k 1 3 \
  --offset 20 \
  --limit 20 \
  --batch-size 20 \
  --append
```

第 3 组：

```bash
python3 scripts/eval_precision.py \
  --graph-name YOUR_GRAPH_NAME \
  --phase judge \
  --top-k 1 3 \
  --offset 40 \
  --limit 20 \
  --batch-size 20 \
  --append
```

完成后额外会得到：

- `precision_summary.md`


## 9. 幻觉率脚本

### 9.1 先生成无 RAG 回答，并复用有 RAG 结果

默认会优先复用：

- `scripts/eval_outputs/precision_top3.json`

所以建议先完成精确率脚本的生成阶段。

第 1 组：

```bash
python3 scripts/eval_hallucination.py --phase generate --offset 0 --limit 20 --batch-size 20 --append
```

第 2 组：

```bash
python3 scripts/eval_hallucination.py --phase generate --offset 20 --limit 20 --batch-size 20 --append
```

第 3 组：

```bash
python3 scripts/eval_hallucination.py --phase generate --offset 40 --limit 20 --batch-size 20 --append
```

如果你想显式指定复用的有 RAG 结果文件：

```bash
python3 scripts/eval_hallucination.py \
  --phase generate \
  --rag-results scripts/eval_outputs/precision_top3.json \
  --offset 0 \
  --limit 20 \
  --batch-size 20 \
  --append
```


### 9.2 最后再做 judge

第 1 组：

```bash
python3 scripts/eval_hallucination.py \
  --phase judge \
  --offset 0 \
  --limit 20 \
  --batch-size 20 \
  --append
```

第 2 组：

```bash
python3 scripts/eval_hallucination.py \
  --phase judge \
  --offset 20 \
  --limit 20 \
  --batch-size 20 \
  --append
```

第 3 组：

```bash
python3 scripts/eval_hallucination.py \
  --phase judge \
  --offset 40 \
  --limit 20 \
  --batch-size 20 \
  --append
```

完成后查看：

- `hallucination_eval.json`
- `hallucination_eval.md`


## 10. 常见问题

### 10.1 为什么要分阶段

因为 judge 也要消耗 token。先完成生成并落盘，能避免中途 token 用尽时丢失前面的结果。


### 10.2 为什么要 `--append`

因为你现在是按 20 条一组推进。`--append` 会把每一组结果合并进总文件，而不是覆盖前一组。


### 10.3 如果同一组跑错了怎么办

直接对同样的 `offset + limit` 再跑一次，并继续带 `--append` 即可。

脚本会按 `case_id` 覆盖更新，不会重复堆积。


### 10.4 幻觉率脚本为什么默认复用 `precision_top3.json`

因为它需要“有 RAG 的回答”。这份结果正好来自精确率脚本的生成阶段，适合作为复用来源。


## 11. 最简推荐命令

如果你只想照抄：

### 第一轮：先把生成全部跑完

```bash
python3 scripts/eval_recall.py --graph-name YOUR_GRAPH_NAME --phase retrieve --offset 0 --limit 20 --batch-size 20 --append
python3 scripts/eval_recall.py --graph-name YOUR_GRAPH_NAME --phase retrieve --offset 20 --limit 20 --batch-size 20 --append
python3 scripts/eval_recall.py --graph-name YOUR_GRAPH_NAME --phase retrieve --offset 40 --limit 20 --batch-size 20 --append

python3 scripts/eval_precision.py --graph-name YOUR_GRAPH_NAME --phase generate --top-k 1 3 --offset 0 --limit 20 --batch-size 20 --append
python3 scripts/eval_precision.py --graph-name YOUR_GRAPH_NAME --phase generate --top-k 1 3 --offset 20 --limit 20 --batch-size 20 --append
python3 scripts/eval_precision.py --graph-name YOUR_GRAPH_NAME --phase generate --top-k 1 3 --offset 40 --limit 20 --batch-size 20 --append

python3 scripts/eval_hallucination.py --phase generate --offset 0 --limit 20 --batch-size 20 --append
python3 scripts/eval_hallucination.py --phase generate --offset 20 --limit 20 --batch-size 20 --append
python3 scripts/eval_hallucination.py --phase generate --offset 40 --limit 20 --batch-size 20 --append
```

### 第二轮：最后统一跑 judge

```bash
python3 scripts/eval_recall.py --graph-name YOUR_GRAPH_NAME --phase judge --offset 0 --limit 20 --batch-size 20 --append
python3 scripts/eval_recall.py --graph-name YOUR_GRAPH_NAME --phase judge --offset 20 --limit 20 --batch-size 20 --append
python3 scripts/eval_recall.py --graph-name YOUR_GRAPH_NAME --phase judge --offset 40 --limit 20 --batch-size 20 --append

python3 scripts/eval_precision.py --graph-name YOUR_GRAPH_NAME --phase judge --top-k 1 3 --offset 0 --limit 20 --batch-size 20 --append
python3 scripts/eval_precision.py --graph-name YOUR_GRAPH_NAME --phase judge --top-k 1 3 --offset 20 --limit 20 --batch-size 20 --append
python3 scripts/eval_precision.py --graph-name YOUR_GRAPH_NAME --phase judge --top-k 1 3 --offset 40 --limit 20 --batch-size 20 --append

python3 scripts/eval_hallucination.py --phase judge --offset 0 --limit 20 --batch-size 20 --append
python3 scripts/eval_hallucination.py --phase judge --offset 20 --limit 20 --batch-size 20 --append
python3 scripts/eval_hallucination.py --phase judge --offset 40 --limit 20 --batch-size 20 --append
```

