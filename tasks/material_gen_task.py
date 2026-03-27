# TODO 这里计划构建教学资源生成任务系统，负责根据教师的需求生成相应的教学资源。现在只做试卷。


from datetime import datetime
import json
import os
from pathlib import Path
from typing import Dict, List, Optional

from repositories.material_repo import create_material, set_material_draft_path
from repositories.syllabus_repo import get_syllabus_by_id
from utils.llm_utils import get_model_instance
from utils.markdown_utils import preprocess_markdown_content, clean_llm_response
from knowlion.abution_knowlion_driver import KnowLion
from config import MODEL_CONFIGS
import time

def generate_material(syllabus_id: int, involved_weeks: List[int], question_type_distribution: Dict[str, int]):
	"""
	1. 选涉及的周次
	2. 选题量（单选、判断、简答）
	3. 开始检索（每周的单独做一次content检索）
	4. 构建草稿提示词（系统提示词：要求只产生json。）（用户提示词：知识+各类题数量）
	5. 生成草稿（具体 a.知识点内容 b.设问点）（json里question字段包括[]列表。列表内为每道题json子元组，结构为：type（题型）, related_knowledge（LLM选出的知识）, query_key（设问点）。）
	（剩下描述的字段不由大模型承担生成。json里另一字段为material_title，为syllabus_title+{timestamp}。json里另一字段为involved_week["week_index":,...]，存涉及的周次。）

	Behavior:
	- Create a `Material` DB record via `repositories.material_repo.create_material`.
	- Attempt to read the syllabus draft (if exists) to provide context.
	- Call the text model to request a strict JSON draft describing questions.
	- Persist the draft JSON to `./material/draft_material_json/` and update the
	  material record's `draft_material_path` via `set_material_draft_path`.

	Returns the created material DB object on success, or None on failure.
	"""

	# validate syllabus
	syllabus = get_syllabus_by_id(syllabus_id)
	if not syllabus:
		print(f"   ❌ [MATERIAL] 无效的 syllabus_id: {syllabus_id}")
		return None

	# create material DB record (title filled later)
	now_ts = datetime.now().strftime("%Y%m%d%H%M%S")
	base_title = getattr(syllabus, 'title', None) or f"material_{syllabus_id}"
	draft_title = f"{base_title}_{now_ts}"
	material = create_material(syllabus_id=syllabus_id, title=draft_title)
	if not material:
		print("   ❌ [MATERIAL] 无法创建 material 记录。")
		return None

	# 1. 选涉及的周次
	context_text = ""
	syllabus_json_path = getattr(syllabus, 'syllabus_path', None)
	if syllabus_json_path and os.path.exists(syllabus_json_path):
		try:
			with open(syllabus_json_path, 'r', encoding='utf-8') as f:
				d = json.load(f)
				# join contents for involved weeks if present
				period = d.get('period', []) if isinstance(d, dict) else []
				parts = []
				for w in period:
					try:
						wi = int(w.get('week_index'))
					except Exception:
						continue
					if wi in involved_weeks:
						parts.append(w.get('content', ''))
				context_text = "\n\n".join(parts)
		except Exception as e:
			print(f"   ⚠️ [MATERIAL] 读取 syllabus (final) 失败: {e}")

	# prepare LLM prompts — follow syllabus_task style and enforce strict JSON output
	# sanitize question_type_distribution to only allow the three supported types
	allowed_types = ("single", "judge", "short")
	clean_dist = {t: int(question_type_distribution.get(t, 0) or 0) for t in allowed_types}
	# cap counts to avoid excessive requests
	for k in clean_dist:
		if clean_dist[k] < 0:
			clean_dist[k] = 0
		if clean_dist[k] > 200:
			clean_dist[k] = 200

	# 2. 选题量（单选、判断、简答）
	# 解析 single/judge/short 题型的数量，构建更详细的提示词
	distribution_fragment = f"single: {clean_dist['single']}, judge: {clean_dist['judge']}, short: {clean_dist['short']}"

	# 3. 开始检索（每周的单独做一次content检索）
	graph_name = None
	try:
		# if syllabus JSON was loaded above as `d`, prefer its graph_name
		graph_name = d.get('graph_name') if isinstance(d, dict) else None
		if not graph_name:
			graph_name = getattr(syllabus, 'graph_name', None) or 'RAG'
		kl = KnowLion(model_configs=MODEL_CONFIGS or {}, graph_name=graph_name)
	except Exception:
		kl = None

	retrieval_fragments = []
	if kl is not None:
		for widx in involved_weeks:
			# find corresponding period entry's enhanced_content
			enh = None
			try:
				for entry in (d.get('period', []) if isinstance(d, dict) else []):
					if int(entry.get('week_index')) == int(widx):
						enh = entry.get('enhanced_content') or entry.get('original_content') or entry.get('content')
						break
					
			except Exception:
				pass
			if not enh:
				continue
			# call search, try top_k 6 then 3
			try:
				res = kl.search(enh, top_k=6)
			except Exception:
				print(f"   ⚠️ [MATERIAL] RAG 检索失败，跳过周 {widx}: {e}")
				res = None
			if res:
				frag = json.dumps(res.get('reasoning_paths', []) or res.get('paragraphs', []), ensure_ascii=False, indent=2)
				retrieval_fragments.append(f"周{widx} 检索:\n" + frag)
			# polite pause
			time.sleep(0.2)

	retrieval_text = "\n\n".join(retrieval_fragments)
	# 4. 构建草稿提示词（系统提示词：要求只产生json。）（用户提示词：知识+各类题数量）
	# user prompt: 知识（来自RAG） + 各类题数量（distribution_fragment）
	user_prompt = f"知识（来自RAG）:\n{retrieval_text}\n题量分配: {distribution_fragment}"

	system_prompt = """
你是一个试题生成专家，负责根据给定的教学大纲片段和题量分配，生成试卷草稿的题目提纲。

【任务说明】
请根据下方提供的`题量分配`和`涉及周次`，为每一道题输出一条描述性的草案条目（只包含题目元数据，不需要生成题干或答案）。

【输出格式要求】
必须严格返回一个 JSON 对象，且不应包含任何额外的自然语言说明或注释。JSON 格式如下：
{
  "questions": [
    {
      "type": "single|judge|short",
      "related_knowledge": "<string: 列出该题涉及的关键知识点或节选>",
      "query_key": "<string: 对应的设问要点/考查方向>"
    }
  ]
}

【字段说明】
- `questions`: 题目列表；每个题目对象必须包含 `type`/`related_knowledge`/`query_key` 三个字段。

【题型与约束】
- 仅允许三类题型：`single`（单选）、`judge`（判断）、`short`（简答）。
- 题目数量必须严格按照提供的 `题量分配`（user prompt 中给出）生成；不要要求或等待额外输入，也不要改变数量。

【处理步骤】
1. 使用提供的教学大纲片段，从中抽取与每道题匹配的关键知识点。
2. 为每道题生成一个 `related_knowledge`（长文本，要求覆盖题干全部内容，包括干扰项信息）和一个 `query_key`（设问方向，错误点、答案要点）。
3. 严格按照题型数量构造 `questions` 列表；若某类题数量为 0，则该类不应出现在列表中。

【重要】
- 输出必须是干净的 JSON，不能包含 Markdown、代码块或任何额外说明。
"""

	# 5. 生成草稿（具体 a.知识点内容 b.设问点) (json里question字段包括[]列表。列表内为每道题json子元组，结构为：type（题型）, related_knowledge（LLM选出的知识）, query_key（设问点）。）
	# 5.a. 调用 LLM 生成草稿 JSON
	draft_obj = None
	cleaned = None
	try:
		model = get_model_instance()
		raw = model.call_text_model(system_prompt, user_prompt)
		cleaned = clean_llm_response(raw)
		try:
			draft_obj = json.loads(cleaned)
		except Exception:
			print("   ❌ [MATERIAL] 无法解析模型返回的 JSON 草稿。")
	except Exception as e:
		print(f"   ⚠️ [MATERIAL] 调用 LLM 生成草稿失败: {e}")
	
	# 5.b. 加上LLM 不负责生成的字段，构建完整草稿对象
	if isinstance(draft_obj, dict) and isinstance(draft_obj.get('questions'), list):
		# attach title and involved_weeks
		draft_obj['material_title'] = draft_title
		# ensure involved_weeks is a list of ints
		try:
			draft_obj['involved_weeks'] = [int(w) for w in involved_weeks]
		except Exception:
			draft_obj['involved_weeks'] = involved_weeks

		# persist draft JSON to disk
		try:
			drafts_dir = Path('./material/draft_material_json')
			drafts_dir.mkdir(parents=True, exist_ok=True)
			safe_name = draft_title.replace(' ', '_')
			draft_fname = f"{safe_name}_{int(time.time())}.json"
			draft_path = drafts_dir / draft_fname
			with draft_path.open('w', encoding='utf-8') as f:
				json.dump(draft_obj, f, ensure_ascii=False, indent=2)

			# update DB record
			set_material_draft_path(material.material_id, str(draft_path))
			print(f"   💾 [MATERIAL] 草稿已保存: {draft_path}")
		except Exception as e:
			print(f"   ❌ [MATERIAL] 保存草稿失败: {e}")
			return None
	else:
		# show failure and original LLM text for debugging
		print("   ❌ [MATERIAL] 无法解析模型返回的 JSON 草稿。")
		if cleaned is not None:
			print("   ❗ 原始模型返回:\n" + cleaned)
		return None

	return material

# def generate_material(syllabus_id: int, involved_weeks: List[int], question_type_distribution: Dict[str, int]):
#1. 选涉及的周次
#2. 选题量（单选、判断、简答）
#3. 开始检索（每周的单独做一次content检索）
#4. 构建草稿提示词（系统提示词：要求只产生json。）（用户提示词：知识+各类题数量）
#5. 生成草稿（具体 a.知识点内容 b.设问点）（json里question字段包括[]列表。列表内为每道题json子元组，结构为：type（题型）, related_knowledge（LLM选出的知识）, query_key（设问点）。）
#（剩下描述的字段不由大模型承担生成。json里另一字段为material_title，为syllabus_title+{timestamp}。json里另一字段为involved_week["week_index":,...]，存涉及的周次。）


# def update_material_draft(material_id: int, question_updates: List[Dict]):
#6. 人工审核草稿（调整 知识点内容 与 设问点）

# def generate_final_material(material_id: int):
#7. 构建正式提示词 （每个小问都单独生成。3种类型的题目提供3种不同的系统提示词。每个小问用户提示词提供对应的type（题型）, related_knowledge（LLM选出的知识）, query_key?（设问点））
#8. 生成题目。每个题目的结果产生为json，包含："question_content"与"answer"与"reason"。
# 接下来不再是llm生成内容。加上部分草稿json内容，构建出最终json应有question[{"question_content","answer", "reason", "question_type(来自draft对应问题)"}]和material_title（同草稿）

# def update_final_material(material_id: int, question_updates: List[Dict]):
# 9. 人工审核正式卷（调整 题目内容 与 答案与 解析）

# def publish_material(material_id: int, new_pdf: bool = False, do_publish: bool = False):
# 10. new_pdf则更新卷子pdf。pdf生成（生成一份卷子。页面末尾附上答案与解析。）
#   10.1 生成pdf后，创file件记录，更新material表的pdf_path与file_id字段。
# 11. do_publish则发布。此举后意味着学生提问时有概率推荐此卷子给学生。