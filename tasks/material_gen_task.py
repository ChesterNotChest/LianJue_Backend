# TODO 这里计划构建教学资源生成任务系统，负责根据教师的需求生成相应的教学资源。现在只做试卷。


from datetime import datetime
import json
import os
from pathlib import Path
from typing import Dict, List, Optional

from repositories.graph_repo import get_graph_by_id
from repositories.material_repo import create_material, set_material_draft_path, set_material_pdf_path
from repositories.syllabus_graph_repo import list_graphs_by_syllabus
from repositories.syllabus_repo import get_syllabus_by_id
from repositories.syllabusmaterial_repo import create_syllabus_material, get_syllabusmaterials_by_material, remove_syllabusmaterial, set_ok_to_recommend
from utils.llm_utils import get_model_instance
from utils.markdown_utils import preprocess_markdown_content, clean_llm_response
from knowlion.abution_knowlion_driver import KnowLion
from config import MODEL_CONFIGS
import time


def _normalize_involved_weeks(involved_weeks):
	weeks = []
	if not isinstance(involved_weeks, list):
		return weeks
	for value in involved_weeks:
		try:
			week_index = int(value)
		except Exception:
			continue
		if week_index not in weeks:
			weeks.append(week_index)
	return weeks


def _sync_material_week_bindings(material_id: int, syllabus_id: int, involved_weeks, default_ok_to_recommend: bool = False):
	if material_id is None or syllabus_id is None:
		return

	target_weeks = set(_normalize_involved_weeks(involved_weeks))
	existing_rows = [
		row for row in get_syllabusmaterials_by_material(material_id)
		if getattr(row, 'syllabus_id', None) == syllabus_id
	]
	existing_by_week = {
		int(getattr(row, 'week_index')): row
		for row in existing_rows
		if getattr(row, 'week_index', None) is not None
	}

	for week_index, row in existing_by_week.items():
		if week_index not in target_weeks:
			remove_syllabusmaterial(material_id, syllabus_id, week_index)

	for week_index in target_weeks:
		existing = existing_by_week.get(week_index)
		ok_to_recommend = getattr(existing, 'ok_to_recommend', default_ok_to_recommend) if existing else default_ok_to_recommend
		create_syllabus_material(material_id, syllabus_id, week_index, ok_to_recommend=ok_to_recommend)

def generate_material_draft(syllabus_id: int, involved_weeks: List[int], question_type_distribution: Dict[str, int]):
	"""
	1. 选涉及的周次
	2. 选题量（单选、判断、简答）
	3. 开始检索（每周的单独做一次content检索）
	4. 构建草稿提示词（系统提示词：要求只产生json。）（用户提示词：知识+各类题数量）
	5. 生成草稿（具体 a.知识点内容 b.设问点）（json里question字段包括[]列表。列表内为每道题json子元组，结构为：type（题型）, related_knowledge（LLM选出的知识）, query_key（设问点）。）
	（剩下描述的字段不由大模型承担生成。json里另一字段为material_title，为syllabus_title+{timestamp}。json里另一字段为involved_week["week_index":,...]，存涉及的周次。）

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
						# prefer enhanced_content when available to keep LLM grounded
						parts.append(w.get('enhanced_content') or w.get('original_content') or w.get('content', ''))
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
		graph_ids = list_graphs_by_syllabus(syllabus_id)
		graph_id = graph_ids[0] if graph_ids else None
		graph = get_graph_by_id(graph_id) if graph_id is not None else None
		graph_name = getattr(graph, 'graphId', None) if graph else None
		kl = KnowLion(model_configs=MODEL_CONFIGS or {}, graph_name=graph_name) if graph_name else None
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
				# include the original enhanced content along with RAG results to avoid drift
				orig_fragment = enh or ''
				res_fragment = json.dumps(res.get('reasoning_paths', []) or res.get('paragraphs', []), ensure_ascii=False, indent=2)
				frag = f"周{widx} 教学原文片段:\n{orig_fragment}\n\n检索结果:\n{res_fragment}"
				retrieval_fragments.append(frag)
			# polite pause
			time.sleep(0.2)

	retrieval_text = "\n\n".join(retrieval_fragments)
	# 4. 构建草稿提示词（系统提示词：要求只产生json。）（用户提示词：知识+各类题数量）
	# user prompt: 知识（来自RAG） + 各类题数量（distribution_fragment）
	# provide both the original (enhanced) syllabus fragments and the retrieval results
	user_prompt = f"教学片段:\n{context_text}\n\n检索结果（按周）:\n{retrieval_text}\n\n题量分配: {distribution_fragment}"

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
	  "related_knowledge": "<string: 列出该题涉及的知识内容或节选>",
	  "query_key": "<string: 设问要点，即具体曲解、调换了related_knowledge的哪个短语或概念来出题；或related_knowledge里唯一原话的哪个短语作为正确答案>"
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
		# 编上question_index，方便前端展示和后续处理使用
		for idx, q in enumerate(draft_obj['questions']):
			q['question_index'] = idx + 1
			
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
			_sync_material_week_bindings(material.material_id, int(syllabus.syllabus_id), draft_obj.get('involved_weeks', []), default_ok_to_recommend=False)
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


# def update_material_draft(material_id: int, material_title: str, new_related_knowledge: List[Dict] = None, new_query_keys: List[int] = None, involved_weeks: List[int] = None):
def update_material_draft(material_id: int, material_title: str = None, new_related_knowledge: List[Dict] = None, new_query_keys: List[Dict] = None, involved_weeks: List[int] = None):
	"""
	6. 人工审核草稿（调整 知识点内容 与 设问点）
	 此方法本质就是 编辑json 与 更新数据库对应字段。
	 material_id: 需要更新的 material 的 ID。
	 material_title: 可选的新标题，如果提供则更新。
	 new_related_knowledge: [{"question_index": int, "related_knowledge": str}]
	 new_query_keys: [{"question_index": int, "query_key": str}]

	Returns the material DB object on success, or None on failure.
	"""
	from repositories.material_repo import get_material_by_id, set_material_draft_path, set_material_title

	# 得到 material 记录
	material = get_material_by_id(material_id)
	if not material:
		print(f"   ❌ [MATERIAL] 无效的 material_id: {material_id}")
		return None

	# 取出 draft_path，读取草稿 JSON
	draft_path = getattr(material, 'draft_material_path', None)
	if not draft_path or not os.path.exists(draft_path):
		print(f"   ❌ [MATERIAL] 草稿文件不存在: {draft_path}")
		return None

	try:
		with open(draft_path, 'r', encoding='utf-8') as f:
			draft_obj = json.load(f)
	except Exception as e:
		print(f"   ❌ [MATERIAL] 读取草稿文件失败: {e}")
		return None

	# 更新 involved_weeks（涉及周次）
	if involved_weeks is not None:
		try:
			draft_obj['involved_weeks'] = [int(w) for w in involved_weeks]
		except Exception:
			draft_obj['involved_weeks'] = involved_weeks

	# 更新 related_knowledge （相关知识点）
	if new_related_knowledge:
		for item in new_related_knowledge:
			try:
				qi = int(item.get('question_index'))
			except Exception:
				continue
			# question_index is 1-based
			idx = qi - 1
			if idx < 0 or idx >= len(draft_obj.get('questions', [])):
				continue
			val = item.get('related_knowledge')
			if val is not None:
				draft_obj['questions'][idx]['related_knowledge'] = val

	# 更新 query_key（设问点）
	if new_query_keys:
		for item in new_query_keys:
			try:
				qi = int(item.get('question_index'))
			except Exception:
				continue
			idx = qi - 1
			if idx < 0 or idx >= len(draft_obj.get('questions', [])):
				continue
			val = item.get('query_key')
			if val is not None:
				draft_obj['questions'][idx]['query_key'] = val

	# 更新 material title（材料标题）
	if material_title:
		try:
			set_material_title(material_id, material_title)
			draft_obj['material_title'] = material_title
		except Exception as e:
			print(f"   ⚠️ [MATERIAL] 更新 material.title 失败: {e}")

	# persist changes back to the same draft path
	try:
		with open(draft_path, 'w', encoding='utf-8') as f:
			json.dump(draft_obj, f, ensure_ascii=False, indent=2)
		# ensure DB draft path matches (no-op if unchanged)
		set_material_draft_path(material_id, draft_path)
		_sync_material_week_bindings(material_id, int(getattr(material, 'syllabus_id', None)), draft_obj.get('involved_weeks', []), default_ok_to_recommend=False)
		print(f"   💾 [MATERIAL] 草稿已更新: {draft_path}")
	except Exception as e:
		print(f"   ❌ [MATERIAL] 保存更新后的草稿失败: {e}")
		return None

	return get_material_by_id(material_id)


def update_material_draft_json(material_id: int, material_draft_json: dict):
	"""Replace the whole material draft JSON with the submitted raw json."""
	from repositories.material_repo import get_material_by_id, set_material_draft_path, set_material_title

	if not isinstance(material_draft_json, dict):
		print("   [MATERIAL] `material_draft_json` must be a dict.")
		return None

	required_fields = ("material_title", "involved_weeks", "questions")
	if any(field not in material_draft_json for field in required_fields):
		print(f"   [MATERIAL] material_draft_json must contain: {required_fields}")
		return None

	questions = material_draft_json.get("questions")
	if not isinstance(questions, list) or not all(isinstance(item, dict) for item in questions):
		print("   [MATERIAL] `questions` must be a list of dict.")
		return None

	material = get_material_by_id(material_id)
	if not material:
		print(f"   [MATERIAL] invalid material_id: {material_id}")
		return None

	draft_path = getattr(material, 'draft_material_path', None)
	if not draft_path or not os.path.exists(draft_path):
		print(f"   [MATERIAL] draft material file does not exist: {draft_path}")
		return None

	try:
		with open(draft_path, 'w', encoding='utf-8') as f:
			json.dump(material_draft_json, f, ensure_ascii=False, indent=2)
		set_material_draft_path(material_id, draft_path)
		_sync_material_week_bindings(material_id, int(getattr(material, 'syllabus_id', None)), material_draft_json.get('involved_weeks', []), default_ok_to_recommend=False)
	except Exception as e:
		print(f"   [MATERIAL] failed to save updated draft: {e}")
		return None

	title = material_draft_json.get('material_title')
	if isinstance(title, str) and title.strip():
		try:
			set_material_title(material_id, title)
		except Exception as e:
			print(f"   [MATERIAL] failed to persist draft title to DB: {e}")

	print(f"   [MATERIAL] draft updated and saved: {draft_path}")
	return get_material_by_id(material_id)

def get_material_draft_detail_info(material_id: int) -> dict:
	"""获取 material 草稿的详细信息，包含解析后的 JSON 内容和相关字段。"""
	from repositories.material_repo import get_material_by_id

	material = get_material_by_id(material_id)
	if not material:
		print(f"   ❌ [MATERIAL] 无效的 material_id: {material_id}")
		return {}

	draft_path = getattr(material, 'draft_material_path', None)
	if not draft_path or not os.path.exists(draft_path):
		print(f"   ❌ [MATERIAL] 草稿文件不存在: {draft_path}")
		return {}

	try:
		with open(draft_path, 'r', encoding='utf-8') as f:
			draft_obj = json.load(f)
			return draft_obj
	except Exception as e:
		print(f"   ❌ [MATERIAL] 读取草稿文件失败: {e}")
		return {}
	
def list_materials_draft_brief_info(syllabus_id: int):
	"""List brief info of all materials for a given syllabus_id, including draft paths."""
	from repositories.material_repo import list_materials_by_syllabus
	items = []
	for m in list_materials_by_syllabus(syllabus_id):
		items.append({
			'material_id': getattr(m, 'material_id', None),
			'title': getattr(m, 'title', None),
			'draft_path': getattr(m, 'draft_material_path', None),
			'final_path': getattr(m, 'material_path', None),
			'pdf_path': getattr(m, 'pdf_path', None),
			'create_time': getattr(m, 'create_time', None)
		})
	return items


def generate_final_material(material_id: int):
	"""
	7. 构建正式提示词 （每个小问都单独生成。3种类型的题目提供3种不同的系统提示词。每个小问用户提示词提供对应的type（题型）, related_knowledge（LLM选出的知识）, query_key?（设问点））
	8. 生成题目。每个题目的结果产生为json，包含："question_content"与"answer"与"reason"。
	接下来不再是llm生成内容。加上部分草稿json内容，构建出最终json应有question[{"question_content","answer", "reason", "question_type(来自draft对应问题)"}]和material_title（同草稿）

	Behavior:
	- Load material record and its draft JSON.
	- For each draft question, call LLM (per-type system prompt) to produce
	  `question_content`, `answer`, `reason`.
	- Keep `type` and `material_title` from the draft (do NOT let LLM change them).
	- Persist final JSON to `./material/material_json/` and update DB via
	  `set_material_path(material_id, path)`.

	Returns the updated material DB object on success, or None on failure.
	"""

	from repositories.material_repo import get_material_by_id, set_material_path

	allowed_types = ("single", "judge", "short")

	material = get_material_by_id(material_id)
	if not material:
		print(f"   ❌ [MATERIAL] 无效的 material_id: {material_id}")
		return None

	draft_path = getattr(material, 'draft_material_path', None)
	if not draft_path or not os.path.exists(draft_path):
		print(f"   ❌ [MATERIAL] 草稿文件不存在: {draft_path}")
		return None

	try:
		with open(draft_path, 'r', encoding='utf-8') as f:
			draft_obj = json.load(f)
	except Exception as e:
		print(f"   ❌ [MATERIAL] 读取草稿文件失败: {e}")
		return None

	questions = draft_obj.get('questions')
	if not isinstance(questions, list):
		print("   ❌ [MATERIAL] 草稿中没有有效的 questions 列表。")
		return None

	# perform LLM calls in parallel (up to 10 workers) similar to syllabus_task
	from concurrent.futures import ThreadPoolExecutor, as_completed
	from tenacity import retry, stop_after_attempt, wait_exponential

	model = get_model_instance()
	graph_name = None
	kl = None
	try:
		syllabus_id = getattr(material, 'syllabus_id', None)
		graph_ids = list_graphs_by_syllabus(syllabus_id) if syllabus_id is not None else []
		graph_id = graph_ids[0] if graph_ids else None
		graph = get_graph_by_id(graph_id) if graph_id is not None else None
		graph_name = getattr(graph, 'graphId', None) if graph else None
		kl = KnowLion(model_configs=MODEL_CONFIGS or {}, graph_name=graph_name) if graph_name else None
	except Exception as e:
		print(f"   ⚠️ [MATERIAL] 无法通过 material -> syllabus -> graph 反查图谱，将跳过 RAG: {e}")
		kl = None

	@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=4))
	def call_model_with_retry(sys_prompt: str, usr_prompt: str) -> str:
		return model.call_text_model(sys_prompt, usr_prompt)

	def make_prompts(q: dict):
		qtype = q.get('type')
		related = q.get('related_knowledge', '')
		query_key = q.get('query_key', '')
		if qtype == 'single':
			system_prompt = '''
你是试题编写专家。请根据提供的知识要点与设问方向，生成一道标准的单选题。
严格以 JSON 返回，格式:
{
  "question_content": "题干文本",
  "options": {"A": "选项A", "B": "选项B", "C": "选项C", "D": "选项D"},
  "answer": "A|B|C|D",
  "reason": "解析文本"
}
题干 20-60 字；解析 30-80 字；选项四个；仅返回 JSON，不要任何额外说明。
'''
			user_prompt = f"知识：{related}\n考点：{query_key}"
		elif qtype == 'judge':
			system_prompt = '''
你是试题编写专家。请根据提供的知识要点与设问方向，生成一道判断题（陈述句）。
严格以 JSON 返回，格式:
{
  "question_content": "判断陈述",
  "answer": true|false,
  "reason": "解析文本"
}
题干为一句陈述；解析 20-60 字；仅返回 JSON，不要任何额外说明。
'''
			user_prompt = f"知识：{related}\n考点：{query_key}"
		else:
			system_prompt = '''
你是试题编写专家。请根据提供的知识要点与设问方向，生成一道简答题（可回答要点）。
严格以 JSON 返回，格式:
{
  "question_content": "问题文本",
  "answer": "简短答案（1-3句）",
  "reason": "要点提示"
}
问题 10-40 字；答案 1-3 句；解析 20-60 字；仅返回 JSON，不要任何额外说明。
'''
			user_prompt = f"知识：{related}\n考点：{query_key}"
		return system_prompt, user_prompt

	def task_wrapper(q: dict):
		q_index = q.get('question_index') or None
		qtype = q.get('type')
		if qtype not in allowed_types:
			return (q_index, None, f"非法题型: {qtype}", None)
		sys_p, usr_p = make_prompts(q)
		if kl is not None:
			try:
				search_query = f"{q.get('related_knowledge', '')}\n{q.get('query_key', '')}".strip()
				if search_query:
					rag_result = kl.search(search_query, top_k=4)
					rag_text = json.dumps(rag_result.get('reasoning_paths', []) or rag_result.get('paragraphs', []), ensure_ascii=False, indent=2)
					usr_p = f"{usr_p}\n补充参考资料（来自图谱 {graph_name}）：\n{rag_text}"
			except Exception as e:
				print(f"   ⚠️ [MATERIAL] 题 {q_index} 的图谱检索失败，继续使用草稿内容生成: {e}")
		try:
			raw = call_model_with_retry(sys_p, usr_p)
			cleaned = clean_llm_response(raw)
			parsed = json.loads(cleaned)
		except Exception as e:
			err_text = None
			try:
				err_text = cleaned
			except Exception:
				err_text = None
			return (q_index, None, str(e), err_text)

		# basic validation
		if not isinstance(parsed, dict):
			return (q_index, None, "模型返回非对象 JSON", json.dumps(parsed, ensure_ascii=False))

		# required keys
		if qtype == 'single':
			required = ("question_content", "options", "answer", "reason")
		else:
			required = ("question_content", "answer", "reason")
		for k in required:
			if k not in parsed:
				return (q_index, None, f"缺少字段: {k}", json.dumps(parsed, ensure_ascii=False))

		new_q = {
			'type': qtype, # 便于回显和后续调整，不计划让update_material这个接口调整这个字段
			'question_index': q_index,
			'related_knowledge': q.get('related_knowledge'), # 同上，update_material接口不调整这个字段
			'query_key': q.get('query_key'), # 同上
		}
		new_q.update(parsed)
		return (q_index, new_q, None, None)

	final_questions_map = {}
	futures = []
	max_workers = min(10, max(1, len(questions)))
	with ThreadPoolExecutor(max_workers=max_workers) as exc:
		for q in questions:
			futures.append(exc.submit(task_wrapper, q))

		for fut in as_completed(futures):
			qi, new_q, err, raw_text = fut.result()
			if err is not None:
				print(f"   ❌ [MATERIAL] 题目生成失败 (题 {qi}): {err}")
				if raw_text is not None:
					print("   ❗ 原始模型返回:\n" + raw_text)
				return None
			final_questions_map[qi] = new_q

	# collect in order of question_index
	final_questions = [final_questions_map[k] for k in sorted(final_questions_map.keys())]

	# build final object
	final_obj = {
		'material_title': draft_obj.get('material_title'),
		'involved_weeks': draft_obj.get('involved_weeks'),
		'questions': final_questions
	}

	# persist final JSON
	try:
		finals_dir = Path('./material/material_json')
		finals_dir.mkdir(parents=True, exist_ok=True)
		safe_name = (draft_obj.get('material_title') or f"material_{material_id}").replace(' ', '_')
		fname = f"{safe_name}_{int(time.time())}.json"
		final_path = finals_dir / fname
		with final_path.open('w', encoding='utf-8') as f:
			json.dump(final_obj, f, ensure_ascii=False, indent=2)

		# update DB record
		set_material_path(material_id, str(final_path))
		_sync_material_week_bindings(material_id, int(getattr(material, 'syllabus_id', None)), final_obj.get('involved_weeks', []), default_ok_to_recommend=False)
		_sync_material_week_bindings(material_id, int(getattr(material, 'syllabus_id', None)), final_obj.get('involved_weeks', []), default_ok_to_recommend=False)
		print(f"   💾 [MATERIAL] 最终材料已保存: {final_path}")
	except Exception as e:
		print(f"   ❌ [MATERIAL] 保存最终材料失败: {e}")
		return None

	return get_material_by_id(material_id)

def update_final_material(
	material_id: int,
	material_title: str = None,
	question_content: List[Dict] = None,
	answer: List[Dict] = None,
	reason: List[Dict] = None,
	options: List[Dict] = None,
	involved_weeks: List[int] = None,
):
	"""
	9. 人工审核正式卷（调整 题目内容 与 答案与 解析）。

	参数格式 (与 update_material_draft 对齐):
	- question_content: [{"question_index": int, "question_content": str}]
	- answer: [{"question_index": int, "answer": str}]
	- reason: [{"question_index": int, "reason": str}]
	- options: [{"question_index": int, "options_index": str(A/B/...), "option": str}] 仅单选题有 options。

	行为与 `update_material_draft` 相似：读取 final JSON（`material.material_path`），按 `question_index` 更新字段，
	写回同一路径并通过仓库方法更新 DB（`set_material_path` / `set_material_title`）。

	返回更新后的 material DB 对象或在失败时返回 None。
	"""

	from repositories.material_repo import get_material_by_id, set_material_path, set_material_title

	material = get_material_by_id(material_id)
	if not material:
		print(f"   ❌ [MATERIAL] 无效的 material_id: {material_id}")
		return None

	final_path = getattr(material, 'material_path', None)
	if not final_path or not os.path.exists(final_path):
		print(f"   ❌ [MATERIAL] 最终材料文件不存在: {final_path}")
		return None

	try:
		with open(final_path, 'r', encoding='utf-8') as f:
			final_obj = json.load(f)
	except Exception as e:
		print(f"   ❌ [MATERIAL] 读取最终材料文件失败: {e}")
		return None

	questions = final_obj.get('questions')
	if not isinstance(questions, list):
		print("   ❌ [MATERIAL] 最终材料中没有有效的 questions 列表。")
		return None

	# 更新 involved_weeks
	if involved_weeks is not None:
		try:
			final_obj['involved_weeks'] = [int(w) for w in involved_weeks]
		except Exception:
			final_obj['involved_weeks'] = involved_weeks

	# helper: apply updates by question_index (1-based)
	def apply_update(list_of_updates, field_name):
		if not list_of_updates:
			return
		for item in list_of_updates:
			try:
				qi = int(item.get('question_index'))
			except Exception:
				continue
			idx = qi - 1
			if idx < 0 or idx >= len(questions):
				continue
			val = item.get(field_name)
			if val is not None:
				questions[idx][field_name] = val

	apply_update(question_content, 'question_content')
	apply_update(answer, 'answer')
	apply_update(reason, 'reason')

	# 修改选项仅适用于单选题，且更新整个 options 字段（不支持单个选项的局部更新），因此单独处理
	if options:
		for item in options:
			try:
				qi = int(item.get('question_index'))
			except Exception:
				continue
			idx = qi - 1
			if idx < 0 or idx >= len(questions):
				continue

			# 仅允许单选题更新单个选项（按选项编号 A/B/... 修改对应选项文本）
			if questions[idx].get("type") != "single":
				continue

			opt_index = item.get('options_index')
			# accept alternative key names for backward compatibility
			if opt_index is None:
				opt_index = item.get('option_index')
			if not isinstance(opt_index, str):
				continue
			opt_index = opt_index.strip()

			new_option_text = item.get('option')
			if new_option_text is None:
				continue

			current_opts = questions[idx].get('options')
			if not isinstance(current_opts, dict):
				# cannot apply single-option update if options are not a dict
				continue

			# ensure the specified option key exists
			if opt_index not in current_opts:
				print(f"   ⚠️ [MATERIAL] 题 {qi} 不存在选项 {opt_index}，跳过。")
				continue

			# apply the single-option update
			current_opts[opt_index] = new_option_text
	# 更新 material title
	if material_title:
		try:
			set_material_title(material_id, material_title)
			final_obj['material_title'] = material_title
		except Exception as e:
			print(f"   ⚠️ [MATERIAL] 更新 material.title 失败: {e}")

	# persist changes
	try:
		with open(final_path, 'w', encoding='utf-8') as f:
			json.dump(final_obj, f, ensure_ascii=False, indent=2)
		# ensure DB final path matches (no-op if unchanged)
		set_material_path(material_id, str(final_path))
		print(f"   💾 [MATERIAL] 最终材料已更新: {final_path}")
	except Exception as e:
		print(f"   ❌ [MATERIAL] 保存更新后的最终材料失败: {e}")
		return None

	return get_material_by_id(material_id)


def update_final_material_json(material_id: int, material_json: dict):
	"""Replace the whole final material JSON with the submitted raw json."""
	from repositories.material_repo import get_material_by_id, set_material_path, set_material_title

	if not isinstance(material_json, dict):
		print("   [MATERIAL] `material_json` must be a dict.")
		return None

	required_fields = ("material_title", "involved_weeks", "questions")
	if any(field not in material_json for field in required_fields):
		print(f"   [MATERIAL] material_json must contain: {required_fields}")
		return None

	questions = material_json.get("questions")
	if not isinstance(questions, list) or not all(isinstance(item, dict) for item in questions):
		print("   [MATERIAL] `questions` must be a list of dict.")
		return None

	material = get_material_by_id(material_id)
	if not material:
		print(f"   [MATERIAL] invalid material_id: {material_id}")
		return None

	final_path = getattr(material, 'material_path', None)
	if not final_path or not os.path.exists(final_path):
		print(f"   [MATERIAL] final material file does not exist: {final_path}")
		return None

	try:
		with open(final_path, 'w', encoding='utf-8') as f:
			json.dump(material_json, f, ensure_ascii=False, indent=2)
		set_material_path(material_id, str(final_path))
		_sync_material_week_bindings(material_id, int(getattr(material, 'syllabus_id', None)), material_json.get('involved_weeks', []), default_ok_to_recommend=False)
	except Exception as e:
		print(f"   [MATERIAL] failed to save updated final material: {e}")
		return None

	title = material_json.get('material_title')
	if isinstance(title, str) and title.strip():
		try:
			set_material_title(material_id, title)
		except Exception as e:
			print(f"   [MATERIAL] failed to persist final title to DB: {e}")

	print(f"   [MATERIAL] final material updated and saved: {final_path}")
	return get_material_by_id(material_id)


# def publish_material(material_id: int, new_pdf: bool = False, do_publish: bool = False):
# 10. new_pdf则更新卷子pdf。pdf生成（生成一份卷子。页面末尾附上答案与解析。）
#   10.1 生成pdf后，创file件记录，更新material表的pdf_path与file_id字段。
# 11. do_publish则发布。此举后意味着学生提问时有概率推荐此卷子给学生。


def publish_material(material_id: int, new_pdf: bool = False, do_publish: bool = False):
	"""Publish a material: optionally regenerate PDF and optionally mark as published.

	- new_pdf: regenerate PDF from the final JSON (`material.material_path`) and
	  save it under `./material/material_pdf/`. The PDF will include questions and
	  an answers+reasons section at the end. After PDF creation, a file record is
	  created and `set_material_pdf_path` is called to persist `pdf_path` and `file_id`.
	- do_publish: attempt to mark material as published via repository helper
	  `set_material_published(material_id, True)` if available; otherwise logs a warning.

	Returns the updated material DB object or None on failure.
	"""

	from repositories.material_repo import get_material_by_id, set_material_pdf_path

	material = get_material_by_id(material_id)
	if not material:
		print(f"   ❌ [PUBLISH] 无效的 material_id: {material_id}")
		return None

	# Regenerate PDF if requested
	if new_pdf:
		final_path = getattr(material, 'material_path', None)
		if not final_path or not os.path.exists(final_path):
			print(f"   ❌ [PUBLISH] 无法找到最终材料 JSON: {final_path}")
			return None

		try:
			with open(final_path, 'r', encoding='utf-8') as f:
				final_obj = json.load(f)
		except Exception as e:
			print(f"   ❌ [PUBLISH] 读取最终 JSON 失败: {e}")
			return None

		# prepare pdf directory
		pdfs_dir = Path('./material/material_pdf')
		pdfs_dir.mkdir(parents=True, exist_ok=True)
		now_ts = int(time.time())
		safe_title = (final_obj.get('material_title') or getattr(material, 'title', f"material_{material_id}")).replace(' ', '_')
		pdf_fname = f"{safe_title}_{now_ts}.pdf"
		pdf_path = str(pdfs_dir / pdf_fname)
		# Build a markdown representation of the final material and convert to PDF via pypandoc
		mds_dir = Path('./material/material_md_cache')
		mds_dir.mkdir(parents=True, exist_ok=True)
		md_fname = f"{safe_title}_{now_ts}.md"
		md_path = str(mds_dir / md_fname)
		# compose markdown
		lines = []
		lines.append(f"# {final_obj.get('material_title') or getattr(material, 'title', '')}\n")
		involved = final_obj.get('involved_weeks') or []
		lines.append(f"**涉及周次:** {', '.join(str(x) for x in involved)}\n")
		lines.append('\n---\n')
		for q in final_obj.get('questions', []) or []:
			qi = q.get('question_index') or ''
			lines.append(f"## {qi}. {q.get('question_content','')}\n")
			opts = q.get('options')
			if isinstance(opts, dict):
				for k, v in opts.items():
					lines.append(f"- **{k}** {v}")
			lines.append('\n')
		# answers
		lines.append('---\n')
		lines.append('## 答案与解析\n')
		for q in final_obj.get('questions', []) or []:
			qi = q.get('question_index') or ''
			lines.append(f"### {qi}. 答案: {q.get('answer')}\n")
			lines.append(f"{q.get('reason','')}\n")

		md_content = '\n'.join(lines)
		# write md
		try:
			with open(md_path, 'w', encoding='utf-8') as mf:
				mf.write(md_content)
		except Exception as e:
			print(f"   ❌ [PUBLISH] 写入 Markdown 失败: {e}")
			return None

		# convert md -> pdf using pypandoc (requires system pandoc)
		try:
			import pypandoc
			# specify outputfile and force xelatex with a CJK font to ensure proper CJK rendering
			extra_args = [
				'--pdf-engine=xelatex',
				'-V', 'CJKmainfont=Noto Serif CJK SC'
			]
			pypandoc.convert_text(md_content, 'pdf', format='md', outputfile=pdf_path, extra_args=extra_args)
		except Exception as e:
			print("   ❌ [PUBLISH] 使用 pypandoc 将 Markdown 转为 PDF 失败: %s" % e)
			print("   ❗ 请确保已安装 pandoc（系统）和 pypandoc（pip install pypandoc），或在环境中可用 pandoc 可执行文件。")
			# ensure md is removed even on failure
			try:
				if os.path.exists(md_path):
					os.remove(md_path)
			except Exception:
				pass
			return None
		finally:
			# remove the temporary markdown cache file regardless of success
			try:
				if os.path.exists(md_path):
					os.remove(md_path)
			except Exception:
				pass

		# create file record and update material
		try:
			upload_time = datetime.utcnow().isoformat()
			# use file_task.add_file to register file (no bytes to write here)
			from tasks.file_task import add_file as add_file_task
			save_dir = os.path.dirname(pdf_path)
			fname = os.path.basename(pdf_path)
			file_id = add_file_task(save_dir, fname, file_bytes=None, upload_time=upload_time)
			set_material_pdf_path(material_id, pdf_path, file_id=file_id)
			print(f"   💾 [PUBLISH] PDF 已生成并保存: {pdf_path}")
		except Exception as e:
			print(f"   ⚠️ [PUBLISH] 保存 PDF 记录到 DB 失败: {e}")

	# publish flag (best-effort)
	if do_publish:
		# when publishing, mark related syllabus-week mappings as recommendable
		try:
			mappings = get_syllabusmaterials_by_material(material_id)
			if not mappings:
				# if no mapping exists yet, try to infer from material.final JSON
				try:
					from repositories.material_repo import get_material_by_id
					mat = get_material_by_id(material_id)
					final_path = getattr(mat, 'material_path', None)
					if final_path and os.path.exists(final_path):
						with open(final_path, 'r', encoding='utf-8') as _f:
							obj = json.load(_f)
							for wk in obj.get('involved_weeks', []) or []:
								try:
									create_syllabus_material(material_id, int(getattr(mat, 'syllabus_id', None)), int(wk), ok_to_recommend=False)
								except Exception:
									pass
				except Exception:
					pass
			# now set ok_to_recommend True for all mappings
			for rec in get_syllabusmaterials_by_material(material_id):
				try:
					set_ok_to_recommend(rec.material_id, rec.syllabus_id, rec.week_index, ok=True)
				except Exception:
					pass
			print(f"   🔔 [PUBLISH] Material {material_id} 的相关 syllabus-week 条目已标记为可推荐。")
		except Exception as e:
			print(f"   ⚠️ [PUBLISH] 标记可推荐时发生错误: {e}")

	return get_material_by_id(material_id)

def list_materials_brief_info(syllabus_id: int):
	"""List all materials for a given syllabus_id."""
	from repositories.material_repo import list_materials_by_syllabus
	items = []
	for m in list_materials_by_syllabus(syllabus_id):
		items.append({
			'material_id': getattr(m, 'material_id', None),
			'title': getattr(m, 'title', None),
			'draft_path': getattr(m, 'draft_material_path', None),
			'final_path': getattr(m, 'material_path', None),
			'pdf_path': getattr(m, 'pdf_path', None),
			'create_time': getattr(m, 'create_time', None)
		})
	return items

def get_material_detail_info(material_id: int):
	"""Get detailed information for a material JSON for display, including parsed JSON content and related fields."""
	'''repo方法 *不具备解析JSON的能力*，仅返回material记录。必须读json文件并解析后才能得到题目信息等。'''
	from repositories.material_repo import get_material_by_id
	material = get_material_by_id(material_id)
	if not material:
		print(f"   ❌ [MATERIAL] 无效的 material_id: {material_id}")
		return None
	final_path = getattr(material, 'material_path', None)
	if not final_path or not os.path.exists(final_path):
		print(f"   ❌ [MATERIAL] 最终材料文件不存在: {final_path}")
		return None
	try:
		with open(final_path, 'r', encoding='utf-8') as f:
			final_obj = json.load(f)
			return final_obj
	except Exception as e:
		print(f"   ❌ [MATERIAL] 读取最终材料文件失败: {e}")
		return None
