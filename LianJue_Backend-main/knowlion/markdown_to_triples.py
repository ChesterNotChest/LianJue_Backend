import logging
import re
import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Dict, Any, Optional, Tuple
import tenacity
from tenacity import retry, stop_after_attempt, wait_exponential
import threading

from abutionpy import abution
from abutionpy.abution_core import Knowledge
from knowlion.multi_model_litellm import LitellmMultiModel
from repositories.jobs_repo import get_job_by_id, update_partial_triples_path

# 强制重新配置日志
for handler in logging.root.handlers[:]:
    logging.root.removeHandler(handler)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)


class Markdown2Triples:
    def __init__(self,
                 model_instance: LitellmMultiModel,
                 md_content: str,
                 file_name: str,
                 #classify: str = "PUBLIC",
                 chunk_size: int = 4000,
                 overlap_size: int = 500,
                 max_chunk_limit: int = 7500,
                 #user_id: str = "default_user"
                 ):
        """
        初始化Markdown到知识图谱转换器
        """
        self.model_instance = model_instance
        self.md_content = md_content
        self.file_name = file_name        #self.classify = classify if classify and classify != "PUBLIC" else None
        self.chunk_size = chunk_size
        self.overlap_size = overlap_size
        self.max_chunk_limit = max_chunk_limit
        #self.user_id = user_id

        # 内容块标识符
        self.block_patterns = [
            (r'Table::\n(.*?)::Table', 'Table'),
            (r'Formulas::\n(.*?)::Formulas', 'Formulas'),
            (r'Image::\n(.*?)::Image', 'Image'),
            (r'Code::\n(.*?)::Code', 'Code')
        ]
        # 用于保护对 partial 文件与增量保存的并发访问
        self._file_lock = threading.Lock()

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=4, max=10))
    def call_llm_with_retry(self, prompt: str, query: str) -> str:
        """带重试的LLM调用"""
        try:
            return self.model_instance.call_text_model(prompt, query)
        except Exception as e:
            logger.error(f"LLM调用失败: {e}")
            raise

    def clean_llm_response(self, response: str) -> str:
        """清理LLM响应，精确去除```json头和```尾标记，提取完整JSON内容"""
        # 1. 去除开头的```json（不区分大小写）及可能的空白/换行
        # 匹配模式：以```json开头，忽略大小写，后面可跟任意空白字符（空格/换行等）
        response = re.sub(r'^```json\s*', '', response, flags=re.IGNORECASE)

        # 2. 去除结尾的```及可能的空白/换行
        # 匹配模式：任意空白字符后面跟```，并确保在字符串末尾
        response = re.sub(r'\s*```$', '', response)

        return response

    def validate_and_fix_json(self, json_str: str) -> Dict[str, Any]:
        """验证和修复JSON格式"""
        try:
            return json.loads(json_str)
        except json.JSONDecodeError as e:
            logger.warning(f"JSON解析失败，尝试修复: {e}")
            # 尝试简单的修复：检查常见的JSON问题
            try:
                # 修复单引号问题
                json_str = json_str.replace("'", '"')
                # 修复无引号的key
                json_str = re.sub(r'(\w+):', r'"\1":', json_str)
                return json.loads(json_str)
            except:
                logger.error("JSON修复失败，返回空字典")
                return {}

    def preprocess_markdown_content(self) -> str:
        """预处理Markdown内容，去除噪声数据"""
        content = self.md_content

        # 1. 移除页码和空白行
        content = re.sub(r'^\s*\d+\s*$', '', content, flags=re.MULTILINE)
        content = re.sub(r'\n\s*\n', '\n\n', content)  # 压缩多个空行

        # 2. 修复表格格式（确保表格有正确的分隔符）
        content = re.sub(r'\|(\s*)\n', '|\n', content)

        # 3. 移除孤立的数字行（可能是页码）
        lines = content.split('\n')
        cleaned_lines = []
        for i, line in enumerate(lines):
            line = line.strip()
            # 跳过纯数字行（可能是页码），但保留表格中的数字
            if re.match(r'^\d+$', line) and not self._is_in_table(lines, i):
                continue
            # 跳过过短的无意义行
            if len(line) < 3 and not any(char in line for char in ['#', '|', '-']):
                continue
            cleaned_lines.append(line)

        content = '\n'.join(cleaned_lines)

        # 4. 确保内容块标识符格式正确
        for pattern, block_type in self.block_patterns:
            start_pattern = f"{block_type}::"
            end_pattern = f"::{block_type}"
            content = re.sub(f'{re.escape(start_pattern)}\\s*', f'{start_pattern}\n', content)
            content = re.sub(f'\\s*{re.escape(end_pattern)}', f'\n{end_pattern}', content)

        return content

    def _is_in_table(self, lines: List[str], line_index: int) -> bool:
        """检查某行是否在表格中"""
        # 向前查找表格开始
        for i in range(line_index, max(0, line_index - 10), -1):
            if '|' in lines[i] and '--' in lines[i]:
                return True
            if i < line_index and not lines[i].strip():
                break
        return False

    def split_markdown_intelligently(self) -> List[Dict[str, Any]]:
        """
        智能切分Markdown文本，包含容错处理
        """
        # 预处理内容
        processed_content = self.preprocess_markdown_content()

        paragraphs = []
        current_pos = 0
        content_length = len(processed_content)

        # 识别所有内容块边界
        block_markers = self._identify_content_blocks(processed_content)

        while current_pos < content_length:
            # 确定当前块的结束位置
            end_pos = min(current_pos + self.chunk_size, content_length)

            # 检查是否需要补全不完整的内容块
            end_pos, chunk_end_type = self._complete_incomplete_blocks(
                current_pos, end_pos, block_markers, processed_content)

            # 确保不超过最大块限制
            if end_pos - current_pos > self.max_chunk_limit:
                logger.warning(f"块大小超过限制，在合理边界截断")
                end_pos = self._find_safe_cut_point(
                    current_pos, current_pos + self.max_chunk_limit, processed_content)

            # 提取当前块内容
            chunk_content = processed_content[current_pos:end_pos].strip()

            if not chunk_content:
                current_pos = end_pos
                continue

            # 清理内容块标识符
            cleaned_content = self._clean_block_identifiers(chunk_content)

            # 确定内容类型
            content_type = self._determine_content_type(cleaned_content, chunk_end_type)

            # 添加重叠区域（如果不是第一个块）
            supplement = ""
            if current_pos > 0 and self.overlap_size > 0:
                supplement_start = max(0, current_pos - self.overlap_size)
                supplement = processed_content[supplement_start:current_pos].strip()
                supplement = self._clean_block_identifiers(supplement)

            paragraphs.append({
                "content": cleaned_content,
                "supplement": supplement,
                "start_pos": current_pos,
                "end_pos": end_pos,
                "type": content_type,
                "index": len(paragraphs) + 1
            })

            current_pos = end_pos

            # 避免无限循环
            if current_pos >= content_length:
                break

        return paragraphs

    def _identify_content_blocks(self, content: str) -> List[Dict[str, Any]]:
        """识别所有内容块的位置和类型"""
        block_markers = []

        for pattern, block_type in self.block_patterns:
            for match in re.finditer(pattern, content, re.DOTALL):
                block_markers.append({
                    'start': match.start(),
                    'end': match.end(),
                    'type': block_type,
                    'content': match.group(1).strip(),
                    'full_match': match.group(0)
                })

        # 按位置排序
        block_markers.sort(key=lambda x: x['start'])
        return block_markers

    def _complete_incomplete_blocks(self, start_pos: int, end_pos: int,
                                    block_markers: List[Dict[str, Any]], content: str) -> Tuple[int, str]:
        """补全不完整的内容块"""
        chunk_end_type = "Text"

        for marker in block_markers:
            # 检查是否在内容块中间被切断
            if marker['start'] < end_pos < marker['end']:
                # 调整到内容块结束
                end_pos = marker['end']
                chunk_end_type = marker['type']
                break

            # 检查是否有只有开始标识没有结束标识的情况
            if end_pos > marker['start'] and end_pos < marker['end']:
                # 尝试查找结束标识
                remaining_content = content[end_pos:marker['end'] + 100]
                end_pattern = f"::{marker['type']}"
                end_match = re.search(re.escape(end_pattern), remaining_content)

                if end_match:
                    # 找到结束标识，补全内容
                    actual_end = end_pos + end_match.end()
                    if actual_end - start_pos <= self.max_chunk_limit:
                        end_pos = actual_end
                        chunk_end_type = marker['type']
                    else:
                        # 超过限制，在合理位置截断
                        logger.warning(f"内容块超过最大限制，在合理位置截断")
                        end_pos = self._find_safe_cut_point(start_pos, start_pos + self.max_chunk_limit, content)
                break

        return end_pos, chunk_end_type

    def _find_safe_cut_point(self, start_pos: int, max_end_pos: int, content: str) -> int:
        """在合理边界寻找安全截断点"""
        # 优先在段落边界截断
        paragraph_end = content.find('\n\n', start_pos, max_end_pos)
        if paragraph_end != -1:
            return paragraph_end + 2

        # 其次在句子边界截断
        sentence_end = max(
            content.rfind('. ', start_pos, max_end_pos),
            content.rfind('。', start_pos, max_end_pos),
            content.rfind('! ', start_pos, max_end_pos),
            content.rfind('? ', start_pos, max_end_pos)
        )

        if sentence_end != -1:
            return sentence_end + 2

        # 最后在单词边界截断
        word_end = content.rfind(' ', start_pos, max_end_pos)
        if word_end != -1:
            return word_end + 1

        return max_end_pos

    def _clean_block_identifiers(self, content: str) -> str:
        """清理内容块标识符"""
        cleaned = content
        for pattern, block_type in self.block_patterns:
            # 移除开始和结束标识
            start_pattern = f"{block_type}::"
            end_pattern = f"::{block_type}"
            cleaned = re.sub(re.escape(start_pattern), '', cleaned)
            cleaned = re.sub(re.escape(end_pattern), '', cleaned)
        return cleaned.strip()

    def _determine_content_type(self, content: str, chunk_end_type: str) -> str:
        """确定内容类型"""
        if chunk_end_type != "Text":
            return chunk_end_type

        # 通过内容特征判断类型
        if re.search(r'```[\s\S]*?```', content):
            return "Code"
        elif re.search(r'\|\s*[^-]+\s*\|', content):
            return "Table"
        elif re.search(r'\$\$[\s\S]*?\$\$|\$[^$]*\$', content):
            return "Formulas"
        else:
            return "Text"

    def extract_element_from_paragraph(self, paragraph: Dict[str, Any]) -> List[Dict[str, Any]]:
        """从单个段落中提取知识（返回主题列表）"""
        max_retries = 2
        retry_count = 0

        while retry_count <= max_retries:
            try:
                # 检查段落内容是否有效
                if not self._is_valid_paragraph(paragraph):
                    logger.warning(f"段落 {paragraph['index']} 内容无效，跳过处理")
                    return [self._create_error_response(paragraph, "段落内容无效")]

                # 构建优化的提示词
                system_prompt, user_prompt = self._build_optimized_prompt(paragraph)
                result = self.call_llm_with_retry(system_prompt, user_prompt)

                # 简单清洗返回结果
                cleaned_result = self.clean_llm_response(result)
                knowledge_list = self.validate_and_fix_json_list(cleaned_result)

                # 验证结果完整性并处理每个主题
                valid_results = []
                for i, item in enumerate(knowledge_list):
                    if self._validate_knowledge_item(item):
                        # 合并上下文索引信息
                        item.update({
                            "paragraph_index": paragraph["index"],
                            "theme_index": i + 1,  # 主题在段落中的索引
                            "start_pos": paragraph.get("start_pos", 0),
                            "end_pos": paragraph.get("end_pos", 0),
                            "original_content": paragraph["content"][:200] + "..." if len(
                                paragraph["content"]) > 200 else paragraph["content"]  # 保存部分原文用于调试
                        })
                        valid_results.append(item)
                    else:
                        logger.warning(f"段落 {paragraph['index']} 的主题 {i + 1} 验证失败")
                        # 记录详细错误信息用于调试
                        logger.debug(f"无效的主题内容: {item}")

                if valid_results:
                    logger.info(f"段落 {paragraph['index']} 提取到 {len(valid_results)} 个主题")
                    return valid_results
                else:
                    retry_count += 1
                    logger.warning(f"段落 {paragraph['index']} 结果验证失败，重试 {retry_count}/{max_retries}")

            except Exception as e:
                retry_count += 1
                logger.error(f"段落 {paragraph['index']} 处理异常: {str(e)}")
                if retry_count > max_retries:
                    break

        # 所有重试都失败
        error_response = self._create_error_response(paragraph, f"处理失败，重试{max_retries}次后仍无效")
        return [error_response]

    def validate_and_fix_json_list(self, json_str: str) -> List[Dict[str, Any]]:
        """验证和修复JSON列表格式"""
        try:
            data = json.loads(json_str)
            if isinstance(data, list):
                return data
            elif isinstance(data, dict):
                # 如果是单个对象，包装成列表
                return [data]
            else:
                logger.warning(f"JSON格式不是列表或对象: {type(data)}")
                return []
        except json.JSONDecodeError as e:
            logger.warning(f"JSON列表解析失败，尝试修复: {e}")
            # 尝试简单的修复：检查常见的JSON问题
            try:
                # 修复单引号问题
                json_str = json_str.replace("'", '"')
                # 修复无引号的key
                fixed_json = re.sub(r'(\w+):', r'"\1":', json_str)
                data = json.loads(fixed_json)
                if isinstance(data, list):
                    return data
                elif isinstance(data, dict):
                    return [data]
            except json.JSONDecodeError as e2:
                logger.error(f"JSON修复失败，返回空字典: {e2}")

            logger.error("所有JSON修复尝试都失败")
            return []

    def _validate_knowledge_item(self, item: Dict[str, Any]) -> bool:
        """验证单个知识项的完整性（适应新的字段类型）"""
        if not isinstance(item, dict):
            logger.debug("主题不是字典类型")
            return False

        # 检查必需字段
        required_fields = ["title", "type", "content", "graph"]
        missing_fields = [field for field in required_fields if field not in item]
        if missing_fields:
            logger.debug(f"主题缺少必需字段: {missing_fields}")
            return False

        # 检查字段类型
        if not isinstance(item.get("title", ""), str):
            logger.debug("title字段不是字符串类型")
            return False

        # type字段现在是列表
        if not isinstance(item.get("type", []), list):
            logger.debug("type字段不是列表类型")
            return False

        # catalog字段现在是列表
        if not isinstance(item.get("catalog", []), list):
            logger.debug("catalog字段不是列表类型")
            return False

        # 检查content字段
        if not isinstance(item["content"], dict):
            logger.debug("content字段不是字典类型")
            return False

        # 检查graph字段结构
        graph = item.get("graph", {})
        if not isinstance(graph, dict):
            logger.debug("graph字段不是字典类型")
            return False

        # entities和relation应该是列表
        if not isinstance(graph.get("entities", []), list):
            logger.debug("entities字段不是列表类型")
            return False

        if not isinstance(graph.get("relation", []), list):
            logger.debug("relation字段不是列表类型")
            return False

        # 检查标题是否有效
        title = item.get("title", "").strip()
        if not title or len(title) < 2:
            logger.debug("标题无效或过短")
            return False

        return True

    def _is_valid_paragraph(self, paragraph: Dict[str, Any]) -> bool:
        """检查段落内容是否有效"""
        content = paragraph.get("content", "").strip()
        # 过滤掉过短或无意义的内容
        if len(content) < 10:
            return False
        # 过滤掉纯数字或符号的内容
        if re.match(r'^[\d\s.\-]+$', content):
            return False
        return True

    def _build_optimized_prompt(self, paragraph: Dict[str, Any]) -> Tuple[str, str]:
        """构建优化的提示词"""
        # 段落类型（通过大模型按主题输出类型更好）
        content_type = paragraph["type"]

        system_prompt = """
        你是一个专业的知识提取助手，请从提供的文本段落中提取结构化信息。
        提供的文本段可能包含1个或多个内容差异大的主题，请识别并提取所有区别明确的相关主题。请按照以下JSON列表格式返回结果（必须严格遵守）：
        ```json
        [
            {
               "title": "内容的标题",
               "type": ["Text/Table/Formulas/Image/Code"],
               "catalog": ["识别到的原文目录标题（如果有）"],
               "content": {
                 "子字段1": ["内容项1", "内容项2"],
                 "子字段2": ["内容项1", "内容项2"]
               },
                "graph": {
                    "entities": [
                       {
                         "vertex": "非常识性知识的新概念或对象的名称（实体名称）",
                         "synonyms": ["同义词1", "同义词2", "别名1", "别名2"],
                         "labels": ["实体类型", "标签"],
                         "details": "实体的详细描述，包含属性信息",
                         "confidence": 0.3（置信度评分取值：[0-1]）,
                         "importance": 0.6（重要性评分取值：[0-1]）
                       }
                    ],
                    "relation": [
                        {
                            "source": "源实体",
                            "target": "目标实体", 
                            "fact": "表示边和连接节点的事实"
                        }
                    ]
                }
            }
        ]
        ```
        注意：
        1. 最终结果是JSON列表，格式：[{}, {}, ...]（即使1个主题也要用列表包装）
        2. 每个列表项必须包含5个字段：title、type、content、graph、catalog
        3. 字段说明：
           - title：主题的30字以内名称（如“GC04岩心样品信息”），且要求能对应上文章或章节信息
           - type：列表类型，返回（Text/Table/Formulas/Image/Code）中的一个或多个值
           - content：高质量的关键信息提取与结构化整理（段落的关键内容：核心概念、步骤、命令、配置、代码、列表、配置项、注意事项、表格、公式、数值数据、关系和数据模式等）
           - graph：实体关系（entities含vertex/synonyms/labels/details/confidence，relation含source/target/fact），其中confidence和importance的值必须为float类型
           - catalog：列表类型，原文中出现的目录标题-如果有（如“### 2. 样品与方法”“## 3. 结果分析”，无则填空列表：[]）
        4. 确保每个主题都有完整的结构
        5. 输出纯净的内容不要包含：```json```

        """

        user_prompt = f"""
        文档名称：{self.file_name}
        段落索引：{paragraph['index']}
        段落内容：{paragraph['content']}
        """

        if paragraph.get("supplement"):
            user_prompt += f"\n上下文补充：{paragraph['supplement']}"

        return system_prompt, user_prompt

    def _validate_knowledge_result(self, result: Dict[str, Any]) -> bool:
        """验证知识提取结果的完整性"""
        required_fields = ["title", "type", "content", "graph"]
        if not all(field in result for field in required_fields):
            return False

        # 检查content字段
        if not isinstance(result["content"], dict):
            return False

        # 检查graph字段结构
        graph = result.get("graph", {})
        if not isinstance(graph, dict):
            return False

        # entities和relation应该是列表
        if not all(isinstance(graph.get(key, []), list) for key in ["entities", "relation"]):
            return False

        return True

    def _create_error_response(self, paragraph: Dict[str, Any], error_msg: str) -> Dict[str, Any]:
        """创建错误响应"""
        return {
            "title": f"段落_{paragraph['index']}",
            "type": paragraph["type"],
            "content": {"错误": [error_msg]},
            "graph": {"entities": [], "relation": []},
            "paragraph_index": paragraph["index"],
            "error": error_msg,
            "original_content": paragraph["content"]
        }

    def process_paragraphs_parallel(self, to_process: List[Dict[str, Any]], job_id: int, persist_path: Optional[str] = None) -> List[Dict[str, Any]]:
        """处理来自持久化文件的待处理条目（每处理完一条即从文件中删除对应项）。
        参数:
          - to_process: 列表，元素为 {"paragraph_index": int, "content_to_process": str}
          - job_id: 任务ID，用于在保存三元组结果时关联任务信息
          - persist_path: 可选，指向持久化 JSON 文件路径；如果提供，会在处理后更新该文件，删除已处理项
        为了保证一致性，此实现采用逐条处理（非并行），并在每条处理后持久化剩余队列。
        """

        # Expect `to_process` to be a list of dicts with keys:
        #   - 'paragraph_index': int
        #   - 'content_to_process': str
        total = len(to_process)

        all_themes = []

        # capture Flask app from current context (if any) so we can push app_context in worker threads
        flask_app = None
        try:
            from flask import current_app
            try:
                flask_app = current_app._get_current_object()
            except Exception:
                print("无法获取当前 Flask app 对象，可能不在 Flask 上下文中")
                flask_app = None
        except Exception:
            flask_app = None

        def process_wrapper(item: Dict[str, Any]) -> List[Dict[str, Any]]:
            para = {
                "content": item.get("content_to_process", ""),
                "supplement": "",
                "start_pos": 0,
                "end_pos": 0,
                "type": "Text",
                "index": item.get("paragraph_index")
            }
            try:
                themes = self.extract_element_from_paragraph(para)
                valid_themes = []
                for i, theme in enumerate(themes):
                    if not theme.get("error") and self._validate_knowledge_item(theme):
                        valid_themes.append(theme)
                    else:
                        logger.warning(f"段落 {para['index']} 的主题 {theme.get('theme_index', i+1)} 处理结果无效")

                if valid_themes:
                    # 使用文件锁保护增量保存，避免竞态
                    with self._file_lock:
                        if flask_app is not None:
                            try:
                                with flask_app.app_context():
                                    self._save_triple_results(valid_themes, job_id)
                            except Exception as e:
                                logger.warning(f"在传递的 app context 内保存失败: {e}")
                                # 尝试不使用 app context 保存（降级）
                                try:
                                    self._save_triple_results(valid_themes, job_id)
                                except Exception as e2:
                                    logger.warning(f"降级保存也失败: {e2}")
                        else:
                            # 没有可用的 Flask app，上下文不可用，直接保存（可能会触发工作上下文错误）
                            try:
                                self._save_triple_results(valid_themes, job_id)
                            except Exception as e:
                                logger.warning(f"直接保存失败: {e}")

                    logger.info(f"✅ 已完成段落 {para['index']}/{total}，提取 {len(valid_themes)} 个主题")
                else:
                    logger.warning(f"❌ 段落 {para['index']} 处理失败或无有效主题")

                return valid_themes

            except Exception as e:
                logger.error(f"段落 {para['index']} 处理异常: {e}")
                return []

            finally:
                # 从持久化文件中移除已处理的条目（同样需要锁保护）
                if persist_path:
                    try:
                        with self._file_lock:
                            if os.path.exists(persist_path):
                                with open(persist_path, 'r', encoding='utf-8') as f:
                                    current = json.load(f)
                                # filter out entries with same paragraph_index
                                remaining = [x for x in current if x.get('paragraph_index') != item.get('paragraph_index')]
                                with open(persist_path, 'w', encoding='utf-8') as f:
                                    json.dump(remaining, f, ensure_ascii=False, indent=2)
                    except Exception as e:
                        logger.warning(f"更新 persist_path 失败 ({persist_path}): {e}")

        # 并发执行处理器
        with ThreadPoolExecutor(max_workers=min(4, (os.cpu_count() or 1))) as executor:
            future_to_item = {executor.submit(process_wrapper, item): item for item in list(to_process)}

            for future in as_completed(future_to_item):
                item = future_to_item[future]
                try:
                    themes = future.result(timeout=300)
                    if themes:
                        all_themes.extend(themes)
                        logger.info(f"✅ 已完成段落 {item.get('paragraph_index')}/{total}，提取 {len(themes)} 个主题")
                    else:
                        logger.warning(f"❌ 段落 {item.get('paragraph_index')} 处理失败")
                except Exception as e:
                    logger.error(f"段落 {item.get('paragraph_index')} 异常: {e}")

        # 按原始顺序排序（段落索引 + 主题索引）
        # 从文件partial中读取所有结果进行排序和过滤

        all_themes = []
        results_dir = "./triples"
        partial_file = os.path.join(results_dir, f"{job_id}_partial.json")
        print(f"从 partial 文件读取结果进行最终排序和过滤: {partial_file}")
        if os.path.exists(partial_file):
            print(f"找到 partial 文件，正在读取: {partial_file}")
            try:
                with open(partial_file, 'r', encoding='utf-8') as f:
                    all_themes = json.load(f) or []
            except Exception as e:
                logger.warning(f"读取 partial 文件失败 ({partial_file}): {e}")
                all_themes = []

        all_themes.sort(key=lambda x: (x["paragraph_index"], x["theme_index"]))
        logger.info(f"从 partial 文件读取 {len(all_themes)} 个主题，准备过滤脏数据")
        # 过滤脏数据
        clean_themes = self._filter_dirty_data(all_themes)

        logger.info(f"处理完成: {len(clean_themes)} 个主题（来自 {total} 个段落）")
        return clean_themes

    def _filter_dirty_data(self, themes: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """过滤脏数据（适应主题列表）"""
        clean_themes = []

        for theme in themes:
            # 检查是否有错误
            if theme.get("error"):
                continue

            # 检查内容是否过于简单
            content = theme.get("content", {})
            if not content or all(len(items) == 0 for items in content.values()):
                continue

            # 检查标题是否有效
            title = theme.get("title", "").strip()
            if not title or title.startswith("段落_"):
                continue

            # 检查实体和关系是否有效
            graph = theme.get("graph", {})
            entities = graph.get("entities", [])
            relations = graph.get("relation", [])

            # 如果既没有实体也没有关系，且内容简单，则跳过
            if len(entities) == 0 and len(relations) == 0:
                content_str = str(content)
                if len(content_str) < 50:  # 降低内容长度阈值，因为现在是主题级别
                    continue

            clean_themes.append(theme)

        return clean_themes


    def execute(self) -> List[Dict[str, Any]]:
        """
        ！不要采用此方法！
        TODO SCHEDULED FOR DEPRECATION -
        XXXXXXXXXXXXXXXXXXXXXXX
        这是一个被 *弃用* 的执行方法，保留仅供参考。
        请使用 `process_paragraphs_parallel` 方法来处理段落并保存结果。
        """
        logger.info("开始处理Markdown文档")

        try:
            # 1. 智能切分Markdown
            logger.info("步骤1: 智能切分Markdown文档")
            paragraphs = self.split_markdown_intelligently()
            logger.info(f"切分得到 {len(paragraphs)} 个段落")

            # 2. 转换为持久化处理格式并处理
            logger.info("步骤2: 转换为 to_process 并提取知识")
            to_process = [{
                "paragraph_index": p.get("index"),
                "content_to_process": p.get("content")
            } for p in paragraphs]
            # For deprecated execute path we call processing with a sentinel job_id=0
            processed_paragraphs = self.process_paragraphs_parallel(to_process, job_id=0)

            if not processed_paragraphs:
                logger.error("没有有效的处理结果，流程终止")
                return []

            logger.info("✅ 处理完成")
            return processed_paragraphs

        except Exception as e:
            logger.error(f"❌ 处理过程发生错误: {e}")
            return []

    def _save_triple_results(self, processed_paragraphs: List[Dict[str, Any]], job_id: int):
        """增量追加保存处理结果到 ../triples/{job_id}_partial.json

        约束:
        - `job_id` 必须为大于0的整数。
        - 仅使用 `{job_id}_partial.json` 文件名，严格禁止其它命名。
        - 仅追加语义（将新主题追加到文件中保存），不进行覆盖写入除非目标文件损坏需重建。
        """
        try:
            if not isinstance(job_id, int) or job_id <= 0:
                raise ValueError("job_id 必须为大于0的整数以执行增量保存")

            if not processed_paragraphs:
                logger.info("没有要保存的处理结果，跳过保存")
                return
            if getattr(self, 'app', None):
                try:
                    with self.app.app_context():
                        job = get_job_by_id(job_id)
                        if not job:
                            logger.warning(f"未找到 job_id={job_id} 的任务信息，无法关联保存路径")
            
                        partial_triples_path = job.partial_triples_path

                        target_file = ''

                        if partial_triples_path == '' or partial_triples_path is None:
                            logger.info(f"第一次保存三元组结果，创建新的 partial 文件 job_id={job_id}")
                            triples_dir = os.path.join(os.path.dirname(__file__), "../triples")
                            os.makedirs(triples_dir, exist_ok=True)
                            target_file = os.path.join(triples_dir, f"{job_id}_partial.json")
                            update_partial_triples_path(job_id, f"triples/{job_id}_partial.json")
                        else:
                            target_file = os.path.join(os.path.dirname(partial_triples_path), os.path.basename(partial_triples_path))

                        existing = []
                        if os.path.exists(target_file):
                            try:
                                with open(target_file, 'r', encoding='utf-8') as f:
                                    existing = json.load(f) or []
                            except Exception as e:
                                logger.warning(f"读取已存在 partial 文件失败，将重建: {e}")
                                existing = []

                        existing.extend(processed_paragraphs)

                        with open(target_file, 'w', encoding='utf-8') as f:
                            json.dump(existing, f, ensure_ascii=False, indent=2)

                        logger.info(f"增量追加保存 {len(processed_paragraphs)} 个主题到: {target_file}")
                except Exception as e:
                    logger.warning(f"使用 Flask app_context 保存三元组失败 {e}")
                    raise e  # 继续执行直接保存的逻辑
            else:
                logger.warning(f"没有 Flask app 可用，直接保存失败: {e}")
                raise Exception("没有 Flask app 可用，无法执行保存操作")
        except Exception as e:
            logger.warning(f"保存处理结果失败: {e}")

# 使用示例
if __name__ == "__main__":
    # 初始化模型
    from config import MODEL_CONFIGS

    model_instance = LitellmMultiModel(MODEL_CONFIGS)

    # 读取Markdown内容
    # md_file_path = "/root/knowlion/markdowns/基于RAG的维修手册智能问答系统研究与应用_郭超.md"
    md_file_path = "/root/knowlion/markdowns/第1章+绪论.md"
    try:
        with open(md_file_path, "r", encoding="utf-8") as f:
            md_content = f.read()
        logger.info(f"成功读取MD文件，长度: {len(md_content)} 字符")
    except Exception as e:
        logger.error(f"读取MD文件失败: {e}")
        sys.exit(1)

    # 创建处理器
    processor = Markdown2Triples(
        model_instance=model_instance,
        md_content=md_content,
        file_name="第1章+绪论",
        # classify="地质研究",
        chunk_size=5000,  # 减小块大小以提高处理质量
        overlap_size=500,
        max_chunk_limit=7500
    )

    # 执行处理
    knowledge_objects = processor.execute()
    print(knowledge_objects)

    # with open("/media/raini/新加卷12/Abution-3.0/GDB/AbutionRag/knowlion/processing_results/中印度洋盆岩心沉积物中稀土元素赋存特征/processed_result.json", "r", encoding="utf-8") as f:
    #     processed_paragraphs = json.load(f)
    # knowledge_objects = processor.build_knowledge_objects(processed_paragraphs)
    # print(knowledge_objects)
    #
    # if knowledge_objects:
    #     logger.info(f"成功生成 {len(knowledge_objects)} 个知识对象")
    # else:
    #     logger.error("未能生成知识对象")