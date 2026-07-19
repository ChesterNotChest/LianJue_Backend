# 联觉系统后端

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](./LICENSE)

联觉系统后端是一个基于 Flask 的教学辅助服务端，负责承接教师端与学生端的真实业务接口、教学大纲与材料管理、个人学习进度维护、知识图谱构建任务，以及基于 KnowLion / AbutionGraph 的检索问答能力。

当前仓库已经不再是单纯的 KnowLion 示例仓库，而是联觉系统自己的后端工程。

## 当前职责

- 用户注册、登录、用户信息维护
- 教学大纲上传、草稿构建、终稿更新、状态查询
- 教学材料草稿生成、终稿发布、详情与状态查询
- 图谱创建、图谱列表、文件上传与文件详情查询
- 学生个人教学大纲初始化、学习时长回写、提问问答
- 后台 JobChecker 轮询执行文档处理流水线
- RAG 检索效果评测脚本

## 技术栈

- Web 框架：Flask
- ORM：Flask-SQLAlchemy
- 数据库：MySQL
- 图数据库 / 检索底座：AbutionGraph + KnowLion
- 模型调用：LiteLLM 兼容 OpenAI 风格接口
- 文档处理：EasyOCR / pypdf / pandoc / docling 等

## 仓库结构

```text
Lianjue_Backend/
├─ app.py                    Flask app 工厂，注册 11 个 blueprint，初始化数据库
├─ run.py                    服务启动入口，同时可拉起 JobChecker
├─ config.py                 配置加载
├─ config.example.json       配置模板
├─ constant.py               枚举常量（JobStage、BasePath、UserPermission 等）
├─ blueprint/                HTTP API 路由层（11 个 blueprint）
├─ tasks/                    业务逻辑层
│   ├─ total_agent/          总 Agent（全局调度中枢，pydantic-ai 工具调用）
│   ├─ study_buddy/          学伴 Agent（陪聊与轻量提醒）
│   ├─ study_graph/          学习成长树（Student Agent、掌握度计算）
│   ├─ personal_recommendation/  学习路径推荐（图谱构建、候选生成、IB-GRPO 选择）
│   ├─ generative/           资源生成（文档/思维导图/测验/编程练习/PPT）
│   ├─ learning_profile/     学习画像（特征计算、画像组装、周次推进）
│   └─ common/               共享工具（Agent 模型构建、搜索、状态事件）
├─ repositories/             数据访问层
├─ schemas/                  SQLAlchemy 数据表定义（含 Agent 运行时状态表）
├─ utils/                    通用工具与 JobChecker
├─ material/                 教学材料产物
├─ schedule/                 教学大纲、个人教学大纲、日历产物
├─ pdfs/                     原始上传文件缓存
├─ markdowns/                文档解析产物
├─ triples/                  三元组产物
├─ knowledge/                知识产物
├─ generative/               AI 生成资源文件
├─ study_graph/              学习成长树文件存储
├─ study_buddy/              学伴树与消息历史
├─ profiles/                 学习画像 JSON
├─ history/                  聊天历史
├─ experiments/              实验计划、RAG 评测脚本
├─ docs/                     补充文档
│   ├─ *_dev_doc.md          各模块关闭报告（唯一事实源）
│   ├─ *_contract.md         跨模块设计契约
│   └─ archive/              已废弃的 small_plan 文档
└─ tests/                    各类测试与调试脚本
```

## 主要数据实体

当前 MySQL 层主要围绕以下实体组织：

- `user`
- `user_syllabus`
- `syllabus`
- `syllabus_graph`
- `material`
- `syllabusmaterials`
- `graph`
- `files`
- `file_graph`
- `jobs`

这些表会在服务启动时由 `app.py` 自动执行 `db.create_all()` 创建。

## API 分组

后端当前通过 11 组 blueprint 提供接口：

| Blueprint | 前缀 | 职责 |
|-----------|------|------|
| `user_api` | `/api` | 用户注册/登录、画像查看/刷新、知识图谱快照 |
| `learning_api` | `/api` | 学习路径推荐、学习计划管理、知识搜索 |
| `total_agent_api` | `/api` | 总 Agent 统一调度入口（同步 + SSE 流式） |
| `study_buddy_api` | `/api` | 学伴独立对话与消息历史 |
| `study_graph_api` | `/api` | 学习成长树查看与 Student Agent 更新 |
| `generative_api` | `/api` | AI 资源生成（文档/思维导图/测验/编程练习/PPT） |
| `quiz_attempt_api` | `/api` | 测验提交与历史 |
| `syllabus_material_api` | `/api` | 教学大纲与教学材料管理 |
| `file_transmit_api` | `/api` | 文件上传与下载 |
| `knowledge_build_api` | `/api` | 图谱构建 Job 管理 |
| `admin_api` | `/api/admin` | 管理员：大纲发布、学生进度、权限管理 |

部分旧端点已废弃（返回 410）：`learning_ask_question`、`learning_update_personal_syllabus`、旧 `syllabus_material_*` 写入端点。

详细接口文档见 `docs/interface_call_dev_doc.md`。

## 后台任务流水线

文档知识构建由 `jobs` 表和 `utils/job_checker.py` 驱动，当前主流程阶段为：

1. `pdf_to_md`
2. `md_to_triples`
3. `triple_to_knowledge`
4. `knowledge_to_save`

对应状态：

- `pending`
- `paused`
- `in_progress`
- `completed`
- `failed`

默认启动 `run.py` 时会同时启动 Flask 服务和 `JobChecker`。如果只想单独启动 API，可加：

```bash
python run.py --no-job-checker
```

## 配置说明

配置文件优先级：

1. `config.json`
2. `config.example.json`

如果仓库根目录不存在 `config.json`，程序会退回到 `config.example.json`，但这通常只适合查看结构，不适合正式运行。

### 推荐做法

```bash
copy config.example.json config.json
```

然后补齐以下配置：

- `MODEL_CONFIGS`
  - `text`
  - `image`
  - `embed`
- `ABUTION_CONFIG`
- `PROCESSING_CONFIG`
- `MYSQL`

### 最少需要确认的内容

- MySQL 连接信息
- AbutionGraph 地址、用户名、密码
- 文本模型 / 多模态模型 / 向量模型的 API Key
- 本地模型目录 `PROCESSING_CONFIG.MODEL_PATH`

## 启动方式

### 1. 安装依赖

推荐使用独立虚拟环境或 conda 环境。

```bash
pip install -r requirements.txt
```

### 1.1 预抓取 Docling 模型到本地 `model/` 目录

Docling 官方文档说明：首次处理 PDF、图片等需要其视觉管线的文档时，会自动下载所需模型；默认缓存目录是 `$HOME/.cache/docling/models`。为了避免服务首跑时临时拉取模型、也为了支持离线部署，建议在安装完成后先显式执行一次模型预抓取，再同步到本项目的 `PROCESSING_CONFIG.MODEL_PATH`（默认值为 `./model`）。

推荐步骤如下：

```bash
# 1) 先按 Docling 官方方式预下载模型到默认缓存目录
docling-tools models download

# 2) 将 Docling 默认缓存同步到项目本地 model 目录
mkdir -p ./model
cp -R ~/.cache/docling/models/. ./model/

# 3) 运行服务前，确认 config.json 中 PROCESSING_CONFIG.MODEL_PATH 指向 ./model
```

如果当前环境没有 `docling-tools` 可执行命令，可以按 Docling 官方文档提供的 Python 方式预下载模型：

```python
from docling.utils.model_downloader import download_models

download_models()
```

Windows PowerShell 可参考：

```powershell
# 1) 预下载模型到默认缓存目录
docling-tools models download

# 2) 同步到项目本地目录
New-Item -ItemType Directory -Force -Path .\model | Out-Null
Copy-Item "$HOME\\.cache\\docling\\models\\*" ".\\model\\" -Recurse -Force
```

补充说明：

- 本项目代码里会读取 `config.json` 的 `PROCESSING_CONFIG.MODEL_PATH`，并将其作为 Docling 的 `artifacts_path` 使用，因此 `./model` 下应保存的是 Docling 预下载后的模型目录内容，而不是再额外嵌套一层 `models/`。
- 如果你在仓库外单独运行 Docling 脚本或 CLI，也可以按官方文档设置环境变量 `DOCLING_ARTIFACTS_PATH` 指向同一个模型目录。
- 如果部署环境需要完全离线运行，建议在镜像构建或服务器初始化阶段完成上述预抓取和复制动作，再启动 `python run.py`。
- 如果你想把 Docling 模型直接放在其他绝对路径，也可以把 `PROCESSING_CONFIG.MODEL_PATH` 改成对应目录；只要该目录内容与 `$HOME/.cache/docling/models` 下的内容一致即可。

### 2. 准备外部依赖

运行前通常还需要：

- MySQL 服务
- AbutionGraph 服务
- OCR / 文档处理依赖
- 模型 API Key

部分系统依赖可参考 `requirements.txt` 末尾的注释，例如：

- `pandoc`
- `texlive`
- `fonts-noto-cjk`

### 3. 启动服务

```bash
python run.py --host 0.0.0.0 --port 5000
```

常用参数：

- `--host`：监听地址，默认 `0.0.0.0`
- `--port`：端口，默认 `5000`
- `--debug`：启用 Flask debug
- `--no-job-checker`：不启动后台轮询器

## 与前端的关系

当前后端是联觉系统前端 `Lianjue_Web` 的配套服务端。

常见联调方式：

1. 启动本仓库 Flask 服务
2. 启动 `Lianjue_Web`
3. 由前端直接请求当前后端的 `/api/*` 接口

## 目录约定

下面这些目录在当前业务中是实际使用中的，不只是示例文件夹：

- `tasks/`
  - 业务逻辑主入口
- `material/`
  - 教学材料 JSON / PDF / 缓存产物
- `schedule/`
  - 教学大纲、草稿、个人教学大纲、日历
- `blueprint/`
  - 路由定义
- `schemas/`
  - 数据表定义

## RAG 评测脚本

`experiments/RAG/` 下保留了当前用于检索评测的脚本，例如：

- `eval_recall.py`
- `eval_precision.py`
- `eval_hallucination.py`
- `eval_retrieval_speed.py`
- `RAG评测脚本使用教程.md`

这些脚本主要用于评估当前 KnowLion 检索能力在联觉系统中的召回、准确率、幻觉率和检索速度。

## 开发说明

- `app.py` 会在启动时自动注册 blueprint，并尝试确保数据库存在
- `run.py` 是推荐入口，而不是直接 `flask run`
- 当前不少测试脚本是“调试脚本”风格，不等同于完整的自动化测试体系
- 本仓库里仍保留了 KnowLion 相关代码与 wheel 包，因为联觉系统当前依赖其图谱构建与检索能力

## 许可证

本项目保留原 MIT 许可证。

详见 [LICENSE](./LICENSE)。
