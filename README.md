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
├─ app.py                    Flask app 工厂，注册 blueprint，初始化数据库
├─ run.py                    服务启动入口，同时可拉起 JobChecker
├─ config.py                 配置加载
├─ config.example.json       配置模板
├─ blueprint/                HTTP API 路由层
├─ tasks/                    业务逻辑层
├─ repositories/             数据访问层
├─ schemas/                  SQLAlchemy 数据表定义
├─ utils/                    通用工具与 JobChecker
├─ material/                 教学材料相关产物
├─ schedule/                 教学大纲、个人教学大纲、日历相关产物
├─ pdfs/                     原始上传文件缓存
├─ markdowns/                文档解析产物
├─ triples/                  三元组产物
├─ knowledge/                知识产物
├─ scripts/                  RAG 评测脚本
├─ docs/                     补充文档
└─ tests/ / test_*.py        各类测试与调试脚本
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

后端当前通过 5 组 blueprint 提供接口。

### 1. 用户接口

位置：`blueprint/user_api.py`

- `POST /api/user_register`
- `POST /api/user_login`
- `POST /api/user_change_password`
- `POST /api/user_reset_password`
- `POST /api/user_update`
- `POST /api/user_detail`
- `GET /api/user_list`

### 2. 教学大纲 / 教学材料接口

位置：`blueprint/syllabus_material_api.py`

教学大纲相关：

- `POST /api/syllabus_build_draft`
- `POST /api/syllabus_build`
- `POST /api/syllabus_update_draft`
- `POST /api/syllabus_update`
- `POST /api/syllabus_detail`
- `POST /api/syllabus_draft_detail`
- `POST /api/syllabus_status`
- `POST /api/syllabus_list`

教学材料相关：

- `POST /api/syllabus_material_generate_draft`
- `POST /api/syllabus_material_update_draft`
- `POST /api/syllabus_material_generate_final`
- `POST /api/syllabus_material_update`
- `POST /api/syllabus_material_publish`
- `POST /api/syllabus_material_draft_detail`
- `POST /api/syllabus_material_detail`
- `POST /api/syllabus_material_status`
- `POST /api/syllabus_material_list`

### 3. 学习接口

位置：`blueprint/learning_api.py`

- `POST /api/learning_init_personal_syllabus`
- `POST /api/learning_personal_syllabus_detail`
- `POST /api/learning_ask_question`
- `POST /api/learning_update_personal_syllabus`

### 4. 文件接口

位置：`blueprint/file_transmit_api.py`

- `POST /api/file_upload`
- `POST /api/file_upload_calendar`，支持可选 `user_id`，用于在创建 syllabus 后同步建立 owner 绑定
- `POST /api/file_list_graph_files`
- `POST /api/file_list_syllabus_files`
- `POST /api/file_detail`

### 5. 图谱 / Job 接口

位置：`blueprint/knowledge_build_api.py`

- `POST /api/job_graph_create`
- `GET /api/job_graph_list`
- `POST /api/job_create`
- `POST /api/job_pause`
- `POST /api/job_resume`
- `POST /api/job_end`
- `POST /api/job_detail`
- `GET /api/job_list`

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

`scripts/` 下保留了当前用于检索评测的脚本，例如：

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
