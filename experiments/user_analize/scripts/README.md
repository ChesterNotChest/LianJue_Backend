# 实验脚本

当前目录里的脚本只是包装器，不是主入口。

主入口请使用：

```bash
python -m experiments.user_analize.runner
```

如需基于导出的 CSV 继续生成统计图，请执行：

```bash
python -m experiments.user_analize.statistics_charts
```

推送前优先使用 git 检查：

```bash
git status --short
git diff -- experiments/user_analize
git ls-files experiments/user_analize/samples
```

- `run_profile_experiment_suite.ps1`
  - 调用 Python runner 执行整套画像实验
  - 依赖本地可用 Python 解释器
  - 产出 `base_profile_results.json`、`ablation_results.json`、`edge_case_results.json`、`stability_results.json`、`manual_review_packets.json`
- `validate_profile_experiment_assets.ps1`
  - 在当前机器可直接运行
  - 校验 `samples/` 和 `reports/` 资产是否完整
  - 产出 `outputs/profile_asset_validation_summary.json`

如果你在 Windows 下需要包装器，常用方式是：

```powershell
powershell -ExecutionPolicy Bypass -File .\experiments\user_analize\scripts\run_profile_experiment_suite.ps1
```
