# 输出目录

本目录用于保存实验脚本运行后的产物。

这里默认保存的是“实验运行结果”，不是 `pytest` 报告。

当前约定：

- `profile_asset_validation_summary.json`：资产完整性校验输出
- `base_profile_results.json`：基础样本画像结果
- `ablation_results.json`：消融实验结果
- `edge_case_results.json`：边界样本实验结果
- `stability_results.json`：稳定性复跑结果
- `manual_review_packets.json`：人工复核包
- `profile_experiment_summary.json`：整套实验汇总
- `charts/`：图表输出目录
- `plot_data/`：适合画图的 CSV 导出层
  - `base_profile_metrics.csv`
  - `base_profile_concept_gaps.csv`
  - `concept_gap_stats.csv`
  - `ablation_long.csv`
  - `ablation_confidence_matrix.csv`
  - `edge_case_metrics.csv`
  - `stability_summary.csv`
  - `manual_review_packets.csv`
  - `manual_review_summary.csv`
