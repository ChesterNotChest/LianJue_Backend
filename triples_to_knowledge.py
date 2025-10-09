import logging
import math
import re
import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Dict, Any, Optional, Tuple
import tenacity
from html5lib.constants import entities
from tenacity import retry, stop_after_attempt, wait_exponential

from abutionpy import abution
from abutionpy.abution_core import Knowledge
from knowlion.multi_model_litellm import LitellmMultiModel

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


class Triples2Knowledge:
    def __init__(self,
                 model_instance: LitellmMultiModel,
                 para_triples:List[Dict[str, Any]],
                 file_name: str,
                 classify: str = None,
                 user_id: str = "default_user"):
        """
        初始化Markdown到知识图谱转换器
        """
        self.model_instance = model_instance
        self.para_triples = para_triples
        self.file_name = file_name
        self.classify = classify if classify != "" and classify != "PUBLIC" else None
        self.user_id = user_id

        # 内容块标识符
        self.block_patterns = [
            (r'Table::\n(.*?)::Table', 'Table'),
            (r'Formulas::\n(.*?)::Formulas', 'Formulas'),
            (r'Image::\n(.*?)::Image', 'Image'),
            (r'Code::\n(.*?)::Code', 'Code')
        ]

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
                         "details": "实体的详细描述，包含属性信息"
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
           - graph：实体关系（entities含vertex/synonyms/labels/details，relation含source/target/fact）
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

    def process_paragraphs_parallel(self, paragraphs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """并行处理所有段落（处理主题列表）"""
        all_themes = []

        def process_wrapper(paragraph):
            try:
                themes = self.extract_element_from_paragraph(paragraph)
                valid_themes = []
                for theme in themes:
                    # 过滤掉无效结果
                    if not theme.get("error") and self._validate_knowledge_item(theme):
                        valid_themes.append(theme)
                    else:
                        logger.warning(f"段落 {paragraph['index']} 的主题 {theme.get('theme_index', 1)} 处理结果无效")

                return valid_themes if valid_themes else None
            except Exception as e:
                logger.error(f"段落 {paragraph['index']} 处理异常: {e}")
                return None

        with ThreadPoolExecutor(max_workers=min(4, os.cpu_count())) as executor:
            future_to_para = {
                executor.submit(process_wrapper, para): para
                for para in paragraphs
            }

            for future in as_completed(future_to_para):
                para = future_to_para[future]
                try:
                    themes = future.result(timeout=300)
                    if themes:
                        all_themes.extend(themes)
                        logger.info(f"✅ 已完成段落 {para['index']}/{len(paragraphs)}，提取 {len(themes)} 个主题")
                    else:
                        logger.warning(f"❌ 段落 {para['index']} 处理失败")
                except Exception as e:
                    logger.error(f"⏰ 段落 {para['index']} 处理超时或失败: {e}")

        # 按原始顺序排序（段落索引 + 主题索引）
        all_themes.sort(key=lambda x: (x["paragraph_index"], x["theme_index"]))

        # 过滤脏数据
        clean_themes = self._filter_dirty_data(all_themes)

        logger.info(f"处理完成: {len(clean_themes)} 个主题（来自 {len(paragraphs)} 个段落）")
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

    def build_knowledge_objects(self) -> List[Knowledge]:
        """构建知识图谱对象"""
        knowledge_objects = []

        if not self.para_triples:
            logger.warning("没有有效的处理结果，无法构建知识对象")
            return knowledge_objects

        # 创建BM25索引
        bm25_index = {}

        # 创建vec索引
        vec_index = {}
        # 批量处理向量化
        paragraph_texts = []
        paragraph_titles = []
        for para in self.para_triples:
            para_str = self.build_paragraph_text(para)  # 替换 json.dumps(para, ensure_ascii=False)
            paragraph_texts.append(para_str)
            paragraph_titles.append(para["title"])
        # 批量调用向量化模型，每批不超过10个
        if paragraph_texts:
            batch_size = 10  # 设置批处理大小为10
            for i in range(0, len(paragraph_texts), batch_size):
                batch_texts = paragraph_texts[i:i + batch_size]
                batch_titles = paragraph_titles[i:i + batch_size]
                try:
                    embeddings = self.model_instance.call_embed_model(batch_texts)
                    # 将结果映射回vec_index
                    for title, embedding in zip(batch_titles, embeddings):
                        vec_index[title] = embedding
                except Exception as e:
                    logger.error(f"向量化处理失败，批处理 {i // batch_size + 1}: {e}")
                    # 可以选择跳过这批数据或采取其他处理措施
                    continue

        # 处理每个段落 + 段落中的实体关系
        for i, para in enumerate(self.para_triples):
            # 创建文档到段落的边
            doc_to_para_edge = (Knowledge.labelE("Doc2Para")
                                .edge(self.file_name, para["title"], True)
                                .property("user_id", self.user_id)
                                .property("classify", self.classify or None)
                                .build())
            knowledge_objects.append(doc_to_para_edge)

            # 创建段落间的上下文关系
            if i > 0:
                prev_para = self.para_triples[i - 1]
                para_to_para_edge = (Knowledge.labelE("Para2Para")
                                     .edge(prev_para["title"], para["title"], True)
                                     .property("user_id", self.user_id)
                                     .property("classify", self.classify or None)
                                     .build())
                knowledge_objects.append(para_to_para_edge)

            # 处理实体关系和bm25索引
            knowledge_elements, bm25_elements = self._process_entities_and_relations(para, vec_index)
            knowledge_objects.extend(knowledge_elements)
            bm25_index.update(bm25_elements)

        # 创建段落顶点
        para_vertex = self._create_para_vertex(self.para_triples, vec_index)
        knowledge_objects.extend(para_vertex)

        # 创建文档顶点
        doc_vertex = self._create_doc_vertex(self.para_triples, vec_index, bm25_index)
        knowledge_objects.append(doc_vertex)

        return knowledge_objects


    def build_paragraph_text(self, para):
        """构建语义优化的段落文本，用于向量化"""
        parts = []

        # 添加标题
        if para.get("title"):
            parts.append(f"标题：{para['title']}")

        # 添加目录信息
        if para.get("catalog"):
            catalog_text = str(para["catalog"])
            parts.append(f"目录：{catalog_text}")

        # 添加内容部分 - 按字段组织
        if para.get("content"):
            content_part = json.dumps(para["content"], ensure_ascii=False)
            parts.append("内容：" + "；".join(content_part))

        # 添加实体信息
        if para.get("graph") and para["graph"].get("entities"):
            entity_parts = []
            for entity in para["graph"]["entities"]:
                entity_desc = f"{entity['vertex']}"
                if entity.get("synonyms"):
                    entity_desc += f"（{','.join(entity['synonyms'])}）"
                if entity.get("labels"):
                    entity_desc += f"（{','.join(entity['labels'])}）"
                if entity.get("details"):
                    entity_desc += f"：{entity['details']}"
                entity_parts.append(entity_desc)

            if entity_parts:
                parts.append("实体：" + "；".join(entity_parts))

        return "。".join(parts)


    def _create_para_vertex(self, paragraphs: List[Dict[str, Any]], vec_index: Dict[str, Any]) -> List[Knowledge]:
        para_knowledge_objects = []
        titles = [para["title"] for para in paragraphs]
        all_entity_count = []
        for para in paragraphs:
            title = para["title"]
            entities = para.get("graph", {}).get("entities", [])
            entity_count = len(entities)
            all_entity_count.append(entity_count)
            para_vertex = (Knowledge.labelV("Para").vertex(title)
                           .property("doc_name", abution.tree_set({self.file_name}))
                           .property("content", json.dumps(para["content"], ensure_ascii=False))
                           .property("type", "|".join(para["type"]))
                           .property("entity_count", entity_count)
                           .property("vector", abution.float_array(vec_index.get(title)))
                           .property("user_id", self.user_id)
                           .property("classify", self.classify or None)
                           .build())
            para_knowledge_objects.append(para_vertex)

            # 收集所有标题作为一个段落
            if "catalog" in para and isinstance(para["catalog"], list):
                titles.extend(para["catalog"])

        try:
            # 将文档目录作为一个单独段落顶点，以丰富内容
            avg_entity_count = math.ceil(sum(all_entity_count) / len(all_entity_count)) if all_entity_count else 0
            para_content = "；".join(titles)
            embeddings = self.model_instance.call_embed_model([para_content])[0]
            para_vertex = (Knowledge.labelV("Para").vertex(self.file_name)
                           .property("doc_name", abution.tree_set({self.file_name}))
                           .property("content", para_content)
                           .property("type", "Text")
                           .property("entity_count", avg_entity_count)
                           .property("vector", abution.float_array(embeddings))
                           .property("user_id", self.user_id)
                           .property("classify", self.classify or None)
                           .build())
            para_knowledge_objects.append(para_vertex)
        except Exception as e:
            logger.error(f"目录(段落)向量化处理失败: {e}")

        return para_knowledge_objects

    def _create_doc_vertex(self, paragraphs: List[Dict[str, Any]], vec_index: Dict[str, Any], bm25_index: Dict[str, Any]) -> Knowledge:
        """创建文档顶点"""
        # 收集所有段落标题
        titles = {para["title"] for para in paragraphs}
        # 收集所有目录标题
        for para in paragraphs:
            if "catalog" in para and isinstance(para["catalog"], list):
                titles.update(para["catalog"])

        # 构建文档顶点
        doc_vertex = (Knowledge.labelV("Doc")
                      .vertex(self.file_name)
                      .property("titles", abution.tree_set(titles))
                      .property("vector", abution.vector_index(vec_index))
                      .property("doc_bm25", abution.bm25_index(bm25_index))
                      .property("user_id", self.user_id)
                      .property("classify", self.classify or None)
                      .property("updated_at", int(time.time() * 1000))
                      .build())

        return doc_vertex

    def _process_entities_and_relations(self, para: Dict[str, Any], vec_index: Dict[str, List[float]])\
            -> tuple[list[Any], dict[str, Dict[str, int]]]:
        """处理实体和关系"""
        # 创建BM25索引
        bm25_elements: Dict[str, Dict[str, int]] = {}

        # 获取段落向量 - 用于实体与段落的反向索引（Agent触发相似度更新）
        para_title_and_vector: Dict[str, List[float]] = {}
        title = para["title"]
        if vec_index.get(title):
            para_vector = vec_index.get(para["title"])
            para_title_and_vector[title] = para_vector

        # 构建实体与关系对象
        knowledge_objects = []
        graph = para.get("graph", {})

        # 处理实体和关系 - 将实体自身信息和有关系相连的邻居信息向量化返回一个实体名和向量的字典，
        # 如果有重名实体则使用向量聚合求平均进行合并，作为entity_vector变量的替换
        # 逻辑：先循环所有点边-处理成{"vertex"：自己的信息(vertex+labels+synonyms+details)+
        # 邻居的信息(vertex+labels+synonyms+details)},其中key为source和target的合集，
        # 其中value处理为source的vertex+target的vertex，labels、synonyms和details也做同样的处理，再拼成语义字符串

        # 1）构建实体信息映射 --------------------------------------------------------------
        entity_info_map = {}
        for entity in graph.get("entities", []):
            if entity.get("vertex"):
                vertex = entity["vertex"]
                # 组合实体的所有信息为语义字符串
                semantic_parts = [vertex]
                semantic_parts.extend(entity.get("labels", []))
                semantic_parts.extend(entity.get("synonyms", []))
                if entity.get("details"):
                    semantic_parts.append(entity.get("details", ""))

                # 创建语义字符串用于向量化
                semantic_string = " ".join(filter(None, semantic_parts))

                # 如果实体已经存在，聚合信息
                if vertex in entity_info_map:
                    # 合并信息
                    existing_info = entity_info_map[vertex]
                    existing_info["semantic_strings"].append(semantic_string)
                    # 合并labels和synonyms
                    existing_info["labels"].update(entity.get("labels", []))
                    existing_info["synonyms"].update(entity.get("synonyms", []))
                    # 添加details
                    if entity.get("details"):
                        existing_info["details_list"].append(entity.get("details"))
                else:
                    entity_info_map[vertex] = {
                        "semantic_strings": [semantic_string],
                        "labels": set(entity.get("labels", [])),
                        "synonyms": set(entity.get("synonyms", [])),
                        "details_list": [entity.get("details")] if entity.get("details") else [],
                        "relations": []  # 存储关联的关系
                    }

        # 1.1 记录实体间的关系以便后续处理邻居信息
        for relation in graph.get("relation", []):
            source = relation.get("source")
            target = relation.get("target")
            fact = relation.get("fact", "")

            if source and target:
                # 添加到source的关联关系
                if source in entity_info_map:
                    entity_info_map[source]["relations"].append({
                        "neighbor": target,
                        "fact": fact,
                        "direction": "out"
                    })

                # 添加到target的关联关系
                if target in entity_info_map:
                    entity_info_map[target]["relations"].append({
                        "neighbor": source,
                        "fact": fact,
                        "direction": "in"
                    })

        # 1.2 处理实体及其邻居信息，生成最终的语义字符串用于向量化
        entity_vectors = {}
        for vertex, info in entity_info_map.items():
            # 构建包含邻居信息的完整语义字符串
            full_semantic_parts = []

            # 添加实体自身的所有语义字符串
            full_semantic_parts.extend(info["semantic_strings"])

            # 添加邻居信息
            for relation in info["relations"]:
                neighbor_vertex = relation["neighbor"]
                fact = relation["fact"]

                # 添加关系事实
                if fact:
                    full_semantic_parts.append(fact)

                # 添加邻居实体信息（如果存在）
                if neighbor_vertex in entity_info_map:
                    neighbor_info = entity_info_map[neighbor_vertex]
                    neighbor_parts = [neighbor_vertex]
                    neighbor_parts.extend(neighbor_info["labels"])
                    neighbor_parts.extend(neighbor_info["synonyms"])
                    if neighbor_info["details_list"]:
                        neighbor_parts.extend(neighbor_info["details_list"])

                    neighbor_semantic = " ".join(filter(None, neighbor_parts))
                    full_semantic_parts.append(f"related entity: {neighbor_semantic}")

            # 合并所有语义信息
            full_semantic_string = " ".join(full_semantic_parts)

            # 向量化处理
            if full_semantic_string.strip():
                try:
                    vector = self.model_instance.call_embed_model([full_semantic_string])[0]
                    entity_vectors[vertex] = vector
                except Exception as e:
                    logger.warning(f"实体 '{vertex}' 向量化失败: {e}")
                    # 使用默认向量化方法作为备选
                    fallback_string = " ".join(info["semantic_strings"])
                    vector = self.model_instance.call_embed_model([fallback_string])[0]
                    entity_vectors[vertex] = vector

        # 2）处理实体 --------------------------------------------------------------
        for entity in graph.get("entities", []):
            if not entity.get("vertex"):
                continue

            entity_terms = [entity["vertex"]] + entity.get("labels", []) + entity.get("synonyms", [])
            bm25_elements[para["title"]] = {term: 1 for term in entity_terms if term}

            # 使用预计算的向量或者备选方案
            vertex_name = entity["vertex"]
            if vertex_name in entity_vectors:
                entity_vector = entity_vectors[vertex_name]
            else:
                # 备选向量化方案
                entity_text = vertex_name + (entity.get("details", "") or "")
                entity_vector = self.model_instance.call_embed_model([entity_text])[0]

            # 收集该实体的所有邻居节点信息用于高基数统计
            neighbors_info = []
            if vertex_name in entity_info_map:
                # 获取该实体的所有邻居关系信息
                for relation in entity_info_map[vertex_name]["relations"]:
                    neighbors_info.append(relation["neighbor"])

            entity_vertex = (Knowledge.labelV("Entity").vertex(entity["vertex"])
                             .property("labels", abution.tree_set(entity.get("labels", [])))
                             .property("synonyms", abution.tree_set(entity.get("synonyms", [])))
                             .property("details",  abution.custom_map_str_str({para["title"]: entity.get("details", "")}))
                             .property("occur_count", 1)
                             .property("confidence", abution.quantile_doubles([entity.get("confidence", 0.5)]))
                             .property("importance", abution.quantile_doubles([entity.get("importance", 0.5)]))
                             .property("neighbors", abution.hyper_log_log_plus(neighbors_info))  # 实时计算度中心性 - 邻居高基数统计，存储所有邻居节点信息
                             .property("vector", abution.float_array(entity_vector))
                             .property("vector_paras", abution.custom_map_str_float_array(para_title_and_vector))
                             .property("user_id", self.user_id)
                             .property("classify", self.classify or None)
                             .build())
            knowledge_objects.append(entity_vertex)

            # 3）创建段落到实体的边 --------------------------------------------------------------
            para_to_entity_edge = (Knowledge.labelE("Para2Entity")
                                   .edge(para["title"], entity["vertex"], True)
                                   .property("user_id", self.user_id)
                                   .property("classify", self.classify or None)
                                   .build())
            knowledge_objects.append(para_to_entity_edge)

        # 处理关系
        for relation in graph.get("relation", []):
            if not relation.get("source") or not relation.get("target"):
                continue

            entity_to_entity_edge = (Knowledge.labelE("Entity2Entity")
                                     .edge(relation["source"], relation["target"], True)
                                     .property("fact", abution.tree_set(relation.get("fact", None)))
                                     .property("occur_count", 1)
                                     .property("user_id", self.user_id)
                                     .property("classify", self.classify or None)
                                     .build())
            knowledge_objects.append(entity_to_entity_edge)

        return knowledge_objects, bm25_elements

    def execute(self) -> List[Knowledge]:
        """执行完整的处理流程"""
        logger.info("开始处理Markdown文档")

        try:
            # 构建知识图谱对象
            logger.info("步骤3: 构建知识图谱对象")
            knowledge_objects = self.build_knowledge_objects()
            logger.info(f"构建了 {len(knowledge_objects)} 个知识对象")

            logger.info("✅ 处理完成")
            return knowledge_objects

        except Exception as e:
            logger.error(f"❌ 处理过程发生错误: {e}")
            return []

    def _save_processing_results(self, knowledge_objects: List[Knowledge]):
        """保存处理结果"""
        try:
            # 创建结果目录
            results_dir = f"../test/knowlion/processing_results/{self.file_name}"
            os.makedirs(results_dir, exist_ok=True)

            # 保存知识对象摘要
            knowledge_summary = []
            for obj in knowledge_objects:
                summary = {
                    "label": obj.label,
                    "vertex": getattr(obj, 'vertex', ''),
                    "properties_count": len(getattr(obj, 'properties', {}))
                }
                knowledge_summary.append(summary)

            with open(f"{results_dir}/knowledge_summary.json", 'w', encoding='utf-8') as f:
                json.dump(knowledge_summary, f, ensure_ascii=False, indent=2)

            logger.info(f"结果已保存到: {results_dir}")

        except Exception as e:
            logger.warning(f"保存处理结果失败: {e}")


# 使用示例
if __name__ == "__main__":
    # 初始化模型
    MODEL_CONFIGS = {
        "text": {
            "model_name": "openai/qwen-max",
            "api_base": "https://dashscope.aliyuncs.com/compatible-mode/v1",
            "api_key": "sk-09a9980300ad40e0978eefe0f3bbb4f2"
        },
        "image": {
            "model_name": "openai/qwen-vl-plus",
            "api_base": "https://dashscope.aliyuncs.com/compatible-mode/v1",
            "api_key": "sk-09a9980300ad40e0978eefe0f3bbb4f2"
        },
        "embed": {
            "model_name": "openai/text-embedding-v4",
            "api_base": "https://dashscope.aliyuncs.com/compatible-mode/v1",
            "api_key": "sk-09a9980300ad40e0978eefe0f3bbb4f2"
        }
    }
    model_instance = LitellmMultiModel(MODEL_CONFIGS)

    # 读取Markdown内容
    md_file_path = "/media/raini/新加卷12/Abution-3.0/GDB/AbutionRag/test/storage/稀土论文/中印度洋盆岩心沉积物中稀土元素赋存特征/extract_marked.md"
    try:
        with open(md_file_path, "r", encoding="utf-8") as f:
            md_content = f.read()
        logger.info(f"成功读取MD文件，长度: {len(md_content)} 字符")
    except Exception as e:
        logger.error(f"读取MD文件失败: {e}")
        sys.exit(1)

    # 创建处理器
    processor = Triples2Knowledge(
        model_instance=model_instance,
        file_name="中印度洋盆岩心沉积物中稀土元素赋存特征",
        classify=None,
        # chunk_size=5000,  # 减小块大小以提高处理质量
        # overlap_size=600,
        # max_chunk_limit=8000
    )

    # 执行处理
    #knowledge_objects = processor.execute()
    #print(knowledge_objects)

    with open("/knowlion/test/processing_results/中印度洋盆岩心沉积物中稀土元素赋存特征/processed_result.json", "r", encoding="utf-8") as f:
        processed_paragraphs = json.load(f)
    knowledge_objects = processor.build_knowledge_objects(processed_paragraphs)
    print(knowledge_objects)

    if knowledge_objects:
        logger.info(f"成功生成 {len(knowledge_objects)} 个知识对象")
    else:
        logger.error("未能生成知识对象")