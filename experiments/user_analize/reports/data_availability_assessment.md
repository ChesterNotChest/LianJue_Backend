# 画像实验数据可得性评估

本评估只基于当前仓库内容、SQL dump 和现有文档，不假设外部系统已经接通。

## 结论

当前仓库已经能直接支撑：

- 课程边界基准实验
- 合成样本驱动的输入规范化实验
- 合成样本驱动的对话 / 行为 / 答题 / 风险特征实验
- 消融实验、边界实验、稳定性实验、人工复核实验

当前仓库还不能直接支撑：

- 基于真实学习行为流的画像实验
- 基于真实答题历史的掌握度实验
- 基于真实资源消费日志的偏好实验
- 真实在线 `POST /api/user_learning_profile` 联调

一句话收口：

> 现在已经够把“整套画像实验框架”跑完，但大部分行为类和结果类信号仍是实验样本，不是生产真实数据。

## 已经可获取的数据

### 1. syllabus

可直接获取且质量最高：

- `experiments/user_analize/samples/source_refs/syllabus_大数据概论_20260322235507.json`
- `schedule/syllabus/大数据概论_20260322235507.json`
- `knowlion_full_20260504.sql` 中的 `syllabus` 表

这部分适合直接作为课程知识边界，不需要额外 Agent 补数。

### 2. personal_syllabus

本地已有结构与更新逻辑：

- `experiments/user_analize/samples/source_refs/student_alt_user_1_8_personal.json`
- `experiments/user_analize/samples/source_refs/student_alt_user_1_17_personal.json`
- `schedule/student_alt/user_1/8_personal.json`
- `schedule/student_alt/user_1/17_personal.json`
- `tasks/learning_task.py`
- `user_syllabus` 表

问题不是“有没有结构”，而是“真实覆盖面不够”。当前只有极少量用户样本，不能代表真实总体。

### 3. history / dialogue 风格参考

可用于参考问答风格：

- `experiments/user_analize/samples/source_refs/history_8_1.json`
- `history/8_1.json`

同时 `tasks/learning_task.py` 里也确实有 history window 维护逻辑。但当前本地历史样本量太小，只适合做风格参考，不适合当真实评测集。

### 4. question themes

题目主题可直接取：

- `experiments/user_analize/samples/source_refs/测试用例.md`
- `测试用例.md`

这适合作为答题记录生成和知识点映射的“题目主题来源”。

## 当前缺失或仅部分可得的数据

### 1. learning_records

缺失。当前仓库里没有：

- 学习行为表
- 学习事件接口
- 稳定的学习日志文件

所以这部分现在只能用合成样本。

建议后续由：

- 学习行为采集 Agent
- 前端埋点或服务端事件聚合层

来提供。

### 2. answer_records

缺失。当前没有：

- 答题记录表
- 题目作答日志
- 知识点对齐后的答题历史池

所以当前 `answer_records` 只能用于实验集构造，不能声称“真实可得”。

建议后续由：

- 测验 / 题库 Agent
- 题目结果落库链路

来提供。

### 3. resource_usage

缺失。当前虽然有 `material` 实体，但没有用户资源消费事件：

- 点击
- 浏览
- 完成
- 停留时长

所以只能生成合成样本，不能从现有仓库直接回放。

建议后续由：

- 资源消费埋点 Agent
- 前端事件采集层

来提供。

### 4. learning_goal

字段契约已经有，但没有稳定持久化来源。现阶段更像“请求时输入”，而不是可回溯的历史字段。

建议后续由：

- 画像编排 Agent
- 前端显式目标输入
- 对话摘要落库逻辑

来补齐。

### 5. expected labels / 金标准

缺失。比如：

- `goal_clarity`
- `emotion_state`
- `dropout_risk`
- `resource_preference`

这些都没有天然真值，必须通过人工复核或标注流程生成。

建议后续由：

- 评测标注 Agent
- 人工复核流程

来提供。

### 6. learning_profile 正式运行链路

现在已经有基础实现，但还不是完整生产接入：

- `tasks/learning_profile_task.py`
- `experiments/user_analize/profile_runtime.py`
- `experiments/user_analize/runner.py`
- `POST /api/user_learning_profile`

所以当前已经能做“实验运行和画像接口基础联调”，但还不是“接入真实行为流后的完整生产画像”。

建议后续由：

- 画像算法 Agent
- API 实现 Agent

来补齐。

## 对“这些数据大部分都已经可获取吗”的直接回答

不是。

更准确的说法是：

- 课程边界类数据，大部分已经可获取
- 个人 syllabus 结构类数据，部分可获取
- 历史问答风格类数据，少量可获取
- 行为、答题、资源消费、标签真值，这几类核心画像信号目前大部分还不可获取

因此当前最合理的实验口径仍然是：

> 用真实 syllabus 和真实结构，配合可控合成样本，先把画像算法链路验证完；等后续 Agent 把行为流、答题流、资源流接上，再替换掉合成部分。
