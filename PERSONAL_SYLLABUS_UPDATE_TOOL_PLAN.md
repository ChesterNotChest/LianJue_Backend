# PERSONAL_SYLLABUS_UPDATE_TOOL_PLAN

## 全局约束

1. 普通画像刷新不能修改已有个人教学大纲的学习状态；个人教学大纲缺失时，可以初始化建档。
2. 只有显式调用个人大纲更新建议堆积器，才允许写入建议；是否真正改变个人大纲掌握状态，也只能由堆积器内部的阈值与确定性算法决定。
3. 推荐调用顺序是：先显式调用堆积器，让它完成建议堆积和必要的越位更新；再刷新画像。
4. 个人教学大纲属于画像域的最终状态属性之一，因此堆积器可以作为长期稳定工具保留；限制点不是“是否永久允许”，而是“必须显式调用，不能在普通画像刷新中隐式写入”。

## 1. 阶段一：profile agent 读取个人教学大纲工具

### 0. 新增的常量定义

本阶段不需要新增常量。继续复用：

```python
BasePath.PERSONAL_SYLLABUS_ROOT
```

第一版不建议为了工具名先加常量。

### 1. 影响的文件范围

- `tasks/learning_profile_task.py`
- `tasks/learning_task.py`
- `repositories/user_syllabus_repo.py`
- `docs/learning_profile_agent_workflow.md`
- 新增 `tests/test_profile_personal_syllabus_tools.py`

注意：`learning_task.py` 中原有个人教学大纲读取/初始化/更新逻辑先保留。本阶段只增量提供 profile agent 侧工具，不删除旧函数。

### 2. 函数级收口的完整数据流

1. profile agent 或画像刷新流程拿到 `user_id + syllabus_id`。
2. 调用 profile agent 侧读取函数。
3. 函数读取 `user_syllabus.personal_syllabus_path`。
4. 如果路径存在且 JSON 可读，返回个人教学大纲 dict。
5. 如果路径缺失或文件不可读，返回 `None`。
6. 本阶段读取函数不自动初始化，避免读操作隐藏写入行为。

### 3. 精确到输入输出的函数级收口，以及重要函数内部逻辑的描述

新增函数：

```python
def read_profile_personal_syllabus(
    user_id: int,
    syllabus_id: int,
    hydrate: bool = True,
) -> Optional[dict]
```

输入：

- `user_id`
- `syllabus_id`
- `hydrate`：是否用真实教学大纲补齐展示字段

输出：

- 成功：个人教学大纲 dict
- 失败：`None`

内部逻辑：

1. 校验 `user_id/syllabus_id`。
2. 调用 `get_user_syllabus(user_id, syllabus_id)`。
3. 获取 `personal_syllabus_path`。
4. 路径不存在时返回 `None`。
5. 读取 JSON。
6. 若 `hydrate=True`，复用或迁入 `learning_task._hydrate_personal_syllabus_fields(...)` 的等价逻辑。
7. 返回 dict。

新增 profile agent tool 包装：

```python
def _tool_read_personal_syllabus_context(state: Dict[str, Any]) -> Dict[str, Any]
```

输出：

```python
{
  "tool": "read_personal_syllabus_context",
  "loaded": true,
  "has_personal_syllabus": true,
  "week_count": 16
}
```

内部逻辑：

1. 调用 `read_profile_personal_syllabus(...)`。
2. 写入 `state["profile_personal_syllabus"]`。
3. 写入 `state["profile_personal_syllabus_loaded"] = True`。

### 4. 测试用例的构建描述

- 路径存在且 JSON 合法时返回 dict。
- 路径缺失时返回 `None`。
- JSON 损坏时返回 `None`。
- `hydrate=True` 时补齐真实教学大纲字段。
- `hydrate=False` 时只返回个人大纲原始字段。
- tool 能把结果写入 state，缺失时不抛异常。

## 2. 阶段二：profile agent 初始化个人教学大纲工具

### 0. 新增的常量定义

本阶段不新增常量。继续复用：

```python
BasePath.PERSONAL_SYLLABUS_ROOT
```

### 1. 影响的文件范围

- `tasks/learning_profile_task.py`
- `tasks/learning_task.py`
- `repositories/user_syllabus_repo.py`
- `tests/test_profile_personal_syllabus_tools.py`

注意：`learning_task.init_personal_syllabus(...)` 原函数保留。profile agent 侧新增等价初始化函数。

### 2. 函数级收口的完整数据流

1. profile agent 判断个人教学大纲缺失。
2. 调用初始化工具。
3. 初始化工具读取真实教学大纲 `syllabus.syllabus_path`。
4. 根据真实教学大纲 `period` 生成个人教学大纲 JSON。
5. 写入 `schedule/student_alt/user_{user_id}/{syllabus_id}_personal.json`。
6. 调用 `set_personal_syllabus_path(...)` 写回 DB。
7. 返回个人教学大纲路径和 JSON。

### 3. 精确到输入输出的函数级收口，以及重要函数内部逻辑的描述

新增函数：

```python
def init_profile_personal_syllabus(user_id: int, syllabus_id: int) -> Optional[dict]
```

输出成功：

```python
{
  "personal_syllabus_path": "...",
  "personal_syllabus": {}
}
```

内部逻辑：

1. 校验 `user_id/syllabus_id`。
2. 读取 `syllabus` 和 `syllabus.syllabus_path`。
3. 读取真实教学大纲 JSON。
4. 构建个人教学大纲：

```python
{
  "syllabus_id": syllabus_id,
  "user_id": user_id,
  "period": [
    {
      "week_index": ...,
      "content": ...,
      "enhanced_content": ...,
      "importance": ...,
      "competance": "none",
      "competance_progress": 0,
      "suggested_competance_list": [],
      "suggestion_review_count": 0,
      "suggestion_history": [],
      "updated_at": 0
    }
  ]
}
```

5. 确保目录存在。
6. 写 JSON。
7. 写回 `user_syllabus.personal_syllabus_path`。
8. 返回路径和 JSON。

新增 tool 包装：

```python
def _tool_init_personal_syllabus_context(state: Dict[str, Any]) -> Dict[str, Any]
```

输出：

```python
{
  "tool": "init_personal_syllabus_context",
  "created": true,
  "personal_syllabus_path": "...",
  "week_count": 16
}
```

### 4. 测试用例的构建描述

- 能基于真实教学大纲生成个人教学大纲。
- 生成 JSON 包含 `suggestion_history`。
- 能写入 `user_syllabus.personal_syllabus_path`。
- 真实教学大纲缺失时返回 `None`。
- tool 初始化成功时更新 state，失败时返回 `created=False`。

## 3. 阶段三：profile agent 个人大纲更新建议堆积器

### 0. 新增的常量定义

建议新增：

```python
class ProfilePersonalSyllabusSuggestionSource(Enum):
        PROFILE_AGENT = "profile_agent"
        TOTAL_AGENT = "total_agent"
        LEGACY_LEARNING_QA = "legacy_learning_qa"
        MANUAL = "manual"


class ProfilePersonalSyllabusSuggestionThreshold(Enum):
        CONFIDENCE_MIN = 0.65
        WEEK_REVIEW_THRESHOLD = 5
        SUGGESTION_HISTORY_MAX = 50
```

继续复用：

```python
PersonalSyllabus.PROGRESS_MAX
PersonalSyllabus.PROGRESS_MIN
```

### 1. 影响的文件范围

- `constant.py`
- `tasks/learning_profile_task.py`
- `docs/learning_profile_agent_workflow.md`
- `tests/test_profile_personal_syllabus_tools.py`
- `tests/test_learning_profile_toolchain.py`

注意：原 `learning_task._toggle_competance(...)`、`learning_task._update_competance(...)` 先保留给 legacy 流程，但 profile agent 的建议堆积器不复用这些私有函数。profile agent 侧单独维护建议堆积与晋级/降级确定性算法，避免两个业务域共享隐式状态规则。

### 2. 函数级收口的完整数据流

1. profile agent 或总 Agent 判断某个 week 有学习状态更新建议。
2. 显式调用建议堆积器，传入 `user_id/syllabus_id/week_index/suggested_competance/confidence/reason/evidence`。
3. 工具读取个人教学大纲。
4. 工具校验 week 是否存在。
5. 工具把建议追加到目标 week 的 `suggested_competance_list` 和 `suggestion_history`。
6. 工具累加目标 week 的 `suggestion_review_count`。
7. 未达到阈值时只保存堆积建议。
8. 达到阈值时，堆积器内部自动调用确定性函数检查晋级/降级。
9. 写回个人教学大纲 JSON。
10. 返回更新结果。

### 3. 精确到输入输出的函数级收口，以及重要函数内部逻辑的描述

建议结构：

```python
{
  "week_index": 5,
  "suggested_competance": "weak",
  "confidence": 0.76,
  "reason": "本轮对话暴露 HBase 基础概念薄弱",
  "evidence": ["dialogue_text", "history", "personal_syllabus"],
  "source": "profile_agent",
  "created_at": 1760000000
}
```

新增函数：

```python
def normalize_profile_personal_syllabus_suggestion(
    suggestion: dict,
    default_source: str = ProfilePersonalSyllabusSuggestionSource.PROFILE_AGENT.value,
) -> Optional[dict]
```

内部逻辑：

1. 校验 `week_index` 可转 int。
2. 校验 `suggested_competance` 在 `weak_far/weak/normal/master/master_far`。
3. `confidence` 转 float 并裁剪到 `[0, 1]`。
4. 低于 `CONFIDENCE_MIN` 返回 `None`，避免低置信污染。
5. `reason` 转字符串。
6. `evidence` 统一成 list。
7. 补齐 `source/created_at`。

新增函数：

```python
def append_profile_personal_syllabus_suggestion(
    user_id: int,
    syllabus_id: int,
    suggestion: dict,
) -> Optional[dict]
```

输出成功：

```python
{
  "personal_syllabus": {},
  "personal_syllabus_path": "...",
  "suggestion": {},
  "applied": true,
  "week_index": 5,
  "suggestion_review_count": 0,
  "competance": "normal",
  "competance_progress": 0
}
```

内部逻辑：

1. 标准化 suggestion。
2. 读取个人教学大纲；缺失则初始化。
3. 找到目标 week。
4. 追加 `suggested_competance_list`。
5. 追加 `suggestion_history`，只保留最近 50 条。
6. 累加目标 week 的 `suggestion_review_count`。
7. 未达到 `WEEK_REVIEW_THRESHOLD` 时只写回堆积内容，`applied=False`。
8. 达到阈值时调用 profile agent 侧确定性函数检查是否晋级/降级；应用后清空目标 week 的 `suggested_competance_list`，并重置 `suggestion_review_count`。
9. 写回 JSON。

新增确定性函数：

```python
def maybe_apply_profile_personal_syllabus_progress(
    personal_syllabus: dict,
    week_index: int,
) -> tuple[dict, bool]
```

内部逻辑：

1. 读取目标 week 的 `suggestion_review_count` 和 `suggested_competance_list`。
2. 未达到 `WEEK_REVIEW_THRESHOLD` 时直接返回 `(personal_syllabus, False)`。
3. 达到阈值时应用。
4. 应用算法在 profile agent 侧单独维护，不调用 `learning_task._update_competance(...)`：
   - 建议列表映射成分数。
   - 算平均建议。
   - 根据当前 `competance` 调整 `competance_progress`。
   - 达到上下限时晋级/降级。
   - 清空 `suggested_competance_list`。
   - 重置目标 week 的 `suggestion_review_count`。

独立维护要求：

- 不调用 `learning_task._toggle_competance(...)`。
- 不调用 `learning_task._update_competance(...)`。
- 不依赖 `learning_task._update_review_count(...)`。
- 可复刻其等级映射思想，但实现放在 `learning_profile_task.py` 中，并用 profile agent 的测试单独覆盖。
- 不提供外部直接应用个人大纲状态的入口；所有新增更新都必须先进入堆积器。

### 4. 测试用例的构建描述

- 标准化合法建议成功。
- 非法 `week_index/suggested_competance` 返回 `None`。
- 低 confidence 返回 `None`。
- evidence 字符串会转成 list。
- 显式调用堆积器后，未达阈值只堆积，不改变 `competance/competance_progress`。
- 多次显式调用堆积器达到阈值后，自动通过确定性函数应用。
- `maybe_apply...` 覆盖 none 初始状态、progress 晋级、progress 降级。
- 确认不存在绕过堆积器直接更新个人大纲掌握状态的新入口。

## 4. 阶段四：profile agent 工具注册与调用策略

### 0. 新增的常量定义

本阶段不新增常量。

### 1. 影响的文件范围

- `tasks/learning_profile_task.py`
- `docs/learning_profile_agent_workflow.md`
- `tests/test_learning_profile_agent_choice.py`
- `tests/test_learning_profile_toolchain.py`

### 2. 函数级收口的完整数据流

1. profile agent 刷新画像。
2. agent 可调用读取个人教学大纲工具。
3. 如缺失，可调用初始化个人教学大纲工具。
4. agent 生成画像。
5. 如需要推动个人教学大纲变化，只能显式调用建议堆积器。
6. 堆积器先写入建议；达到阈值后，堆积器内部确定性地检查并应用晋级/降级。
7. agent 保存画像。

### 3. 精确到输入输出的函数级收口，以及重要函数内部逻辑的描述

在 `get_learning_profile_agent()` 中只注册读工具和初始化工具：

```python
@agent.tool(sequential=True)
def read_personal_syllabus(ctx: RunContext[LearningProfileDeps]) -> dict:
    return _tool_read_personal_syllabus_context(ctx.deps.state)


@agent.tool(sequential=True)
def init_personal_syllabus(ctx: RunContext[LearningProfileDeps]) -> dict:
    return _tool_init_personal_syllabus_context(ctx.deps.state)
```

建议堆积器不注册进普通画像 agent 的自动工具链，而是作为显式函数/API：

```python
def append_personal_syllabus_suggestion_from_profile(
    user_id: int,
    syllabus_id: int,
    week_index: int,
    suggested_competance: str,
    confidence: float,
    reason: str = "",
    evidence: Optional[list] = None,
) -> dict:
    ...
```

工具策略：

- 普通画像刷新不能修改已有个人教学大纲的学习状态。
- `refresh_profile=True` 时允许读取/初始化个人教学大纲。
- 建议堆积器是长期稳定工具，但必须被显式调用；它是新增流程里唯一允许更新个人大纲掌握状态的入口。
- 普通画像刷新流程不能隐式调用建议堆积器。
- 推荐范式是：总 Agent 或 profile agent 先显式调用建议堆积器，让建议堆积并在达阈值时自动落地；然后再调用画像刷新，使画像读取最新个人教学大纲。

### 4. 测试用例的构建描述

- agent 初始化时只包含读取/初始化工具。
- fallback 不会在普通画像读取中调用更新建议堆积器。
- 显式调用 append 工具时可写入建议。
- 普通画像刷新测试中，确认不会写入 `suggestion_history`。
- 显式调用堆积器后，再刷新画像时，画像能读到最新个人教学大纲状态。
- LLM smoke 测试仍可通过。

## 5. 阶段五：保持 learning_task.py 原逻辑兼容

### 0. 新增的常量定义

本阶段不新增常量。

### 1. 影响的文件范围

- `tasks/learning_task.py`
- `blueprint/learning_api.py`
- learning 相关旧测试

### 2. 函数级收口的完整数据流

1. `learning_task.py` 中旧函数暂不删除。
2. 旧 API 继续使用旧函数。
3. profile agent 新工具独立可用。
4. 后续总 Agent 接管交互入口后，再逐步把旧 API 切到 profile agent 工具。

### 3. 精确到输入输出的函数级收口，以及重要函数内部逻辑的描述

保持以下函数签名不变：

```python
learning_task.init_personal_syllabus(...)
learning_task.get_personal_syllabus_detail_info(...)
learning_task.update_personal_syllabus(...)
learning_task.ask_question(...)
```

短期不做迁移 wrapper，避免影响现有流程。

后续如果要收口，可以再改成：

```python
def init_personal_syllabus(...):
    return learning_profile_task.init_profile_personal_syllabus(...)
```

但这不属于第一轮增量工具交付。

### 4. 测试用例的构建描述

- 现有 `learning_update_personal_syllabus` API 不变。
- 现有 `ask_question` 中 competance 更新逻辑不变。
- profile agent 新工具不会影响旧 learning API。

## 6. 阶段六：profile 输出个人大纲更新建议

### 0. 新增的常量定义

本阶段不新增常量。

### 1. 影响的文件范围

- `tasks/learning_profile_task.py`
- `docs/learning_profile_agent_workflow.md`
- `tests/test_learning_profile_toolchain.py`

### 2. 函数级收口的完整数据流

1. profile agent 读取个人教学大纲。
2. profile agent 计算画像。
3. profile 中只输出 `suggested_personal_syllabus_updates` 作为候选建议，不直接写个人教学大纲。
4. 如果需要让候选建议进入个人大纲状态，外层流程必须显式调用建议堆积器；堆积器仍然是唯一写入口。
5. 保存画像。

### 3. 精确到输入输出的函数级收口，以及重要函数内部逻辑的描述

新增画像字段：

```python
"suggested_personal_syllabus_updates": []
```

新增函数：

```python
def _build_personal_syllabus_update_suggestions(
    profile: dict,
    feature_bundle: dict,
) -> list[dict]
```

内部逻辑：

1. 有 `week_signals` 时才生成建议。
2. 低分 week 生成建议。
3. 建议 confidence 不高于 profile confidence。
4. 附带 `reason/evidence/source`。
5. 最多返回 3 条。

### 4. 测试用例的构建描述

- 有弱 week 时输出建议。
- 无个人教学大纲时输出空建议。
- 建议 confidence 不超过 profile confidence。
- 建议数量不超过上限。
- profile 中始终包含 `suggested_personal_syllabus_updates` 字段。
