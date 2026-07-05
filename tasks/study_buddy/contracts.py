"""Study Buddy — 常量与数据结构定义。"""

BUDDY_TREE_SCHEMA_VERSION = "study_buddy.tree.v2"
BUDDY_MEMORY_SCHEMA_VERSION = "study_buddy.memory.v1"

# 树区域标识
BUDDY_REGION_TRUNK = "trunk"
BUDDY_REGION_LEARNED = "learned"
BUDDY_REGION_EXPLORE = "explore"

# 步骤状态（复用 learning_plan 状态语义）
BUDDY_STEP_STATUS_ACTIVE = "active"
BUDDY_STEP_STATUS_PENDING = "pending"
BUDDY_STEP_STATUS_COMPLETED = "completed"

# 记忆
BUDDY_MEMORY_FILENAME = "buddy_memory.jsonl"
BUDDY_MESSAGE_FILENAME = "buddy_messages.jsonl"
BUDDY_MEMORY_MAX_TAGS = 30
BUDDY_MEMORY_TAG_MAX_CHARS = 60
BUDDY_MESSAGE_MAX_ITEMS = 80

# 树持久化文件名
BUDDY_TREE_FILENAME = "tree.json"

# Agent
BUDDY_AGENT_NAME = "study_buddy_agent"
BUDDY_AGENT_MAX_TOKENS = 300
BUDDY_CHAT_MAX_REPLY_CHARS = 500
