# 用户画像实验执行说明

这里的重点是“跑实验并产出实验结果”，不是“跑构建级单元测试”。


## 主执行入口

整套实验通过标准 Python 模块入口执行：

```bash
python -m experiments.user_analize.runner
```

这条路径负责：

- 读取 `samples/` 下的实验数据集
- 运行基础画像样本
- 运行消融实验
- 运行边界样本实验
- 运行稳定性复跑实验
- 生成人工复核包
- 把结果写入 `outputs/`
- 同时导出 `outputs/plot_data/` 下适合画图的 CSV

如需生成统计图，可继续执行：

```bash
python -m experiments.user_analize.statistics_charts
```

这条路径会读取 `outputs/plot_data/` 下的聚合 CSV，并把统计图写入 `outputs/charts/`。

## 推送前检查

如果目标是推到远端，优先使用 git 检查：

```bash
git status --short
git diff -- experiments/user_analize
git ls-files experiments/user_analize/samples
```

推荐关注：

1. `samples/` 是否已经自包含
2. `outputs/` 是否只保留本轮需要提交的实验结果
3. `reports/` 和 `records/` 是否与当前实验一致

## Windows 包装器

`scripts/` 下保留了 PowerShell 包装器，适合 Windows 本地使用，但它们不是主入口：

- `run_profile_experiment_suite.ps1`
- `validate_profile_experiment_assets.ps1`
