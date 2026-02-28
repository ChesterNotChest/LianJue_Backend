import json
import logging
import os
import re
import sys
import uuid
from typing import Dict, List, Any
import requests
import base64

from abutionpy.abution_connector import AbutionConnector
from abutionpy.abution_core import Knowledge
from abutionpy.abution_schema import Agg
from abutionpy.abution_traversal import Graph
from sentry_sdk import monitor

from knowlion.doc_parsing_markdown import Document2Markdown
from knowlion.knowlion_schema import get_knowlion_schema
from knowlion.multi_model_litellm import LitellmMultiModel
from knowlion.knowledge_to_search import AdvancedHyperGraphRAG
from knowlion.triples_to_knowledge import Triples2Knowledge
from knowlion.markdown_to_triples import Markdown2Triples
from config import ABUTION_CONFIG, PROCESSING_CONFIG
import time
import utils.network_utils as netutils

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


class KnowLion:
    def __init__(self, model_configs, graph_name:str, abution_url: str = None,
                 username: str = None, password: str = None):
        """
        初始化知识图谱处理管道

        :param model_configs: 模型配置字典
        :param model_path: 本地模型路径
        :param save_path: 存储目录路径
        """
        #self.work_path = work_path # 存储主目录
        #self.save_path = None # 以每个文件一个目录
        # self.classify_id = None
        self.file_name = None
        self.graph_name = graph_name
        self.model_configs = model_configs

        # 使用 config 中的 abution 设置作为默认（若未在构造函数中传入）
        cfg = ABUTION_CONFIG or {}
        abution_url = abution_url or cfg.get("abution_url", "localhost:9996")
        username = username or cfg.get("username", "abution")
        password = password or cfg.get("password", "abution")

        # 初始化组件
        self.model = LitellmMultiModel(model_configs)
        # 在初始化 AbutionConnector 前，先尝试一次独立的授权请求（pre-auth），
        # 以让代理/认证层建立会话状态，避免后续请求在认证流程中被拒绝或导致头部丢失。
        try:
            cfg = ABUTION_CONFIG or {}
            # Global SSL config (for urllib/stdlib usage)
            netutils.configure_global_ssl(cfg)

            # assemble base URL respecting whether config provided a scheme
            provided_url = abution_url or cfg.get("abution_url", "localhost:9996")
            base = netutils.build_base_url(provided_url, cfg)

            base_url = base + "/rest"
            sess = requests.Session()
            sess.auth = (username, password)
            _scheme, verify_val = netutils.configure_ssl_session(cfg, sess)

            try:
                resp = sess.get(base_url, timeout=5, verify=sess.verify)
                if resp.status_code == 200:
                    logger.info("Pre-auth successful to %s", base_url)
                else:
                    logger.info("Pre-auth returned %s for %s", resp.status_code, base_url)
            except Exception as e:
                logger.warning(f"Pre-auth request failed: {e}")

            try:
                sess.close()
            except Exception:
                pass
        except Exception as e:
            logger.warning(f"Pre-auth setup failed: {e}")

        # 初始化 AbutionConnector，优先使用配置的 scheme
        try:
            gdb_base = base + "/rest"
        except Exception:
            gdb_base = ("https://" + abution_url + "/rest")

        self.gdb_client = AbutionConnector(gdb_base)
        # 注入一个显式的 Authorization header 以及更安全的 graph-id header
        # 以确保 nginx/auth 层能在每次请求中看到凭证与图ID（避免连接重用/代理丢失问题）
        try:
            client_obj = getattr(self.gdb_client, "client", None)
            if client_obj is not None:
                auth_value = "Basic " + base64.b64encode(f"{username}:{password}".encode()).decode()
                # 客户端基础 headers
                try:
                    if hasattr(client_obj, "headers") and isinstance(client_obj.headers, dict):
                        client_obj.headers.setdefault("Authorization", auth_value)
                        client_obj.headers.setdefault("abution-graph-id", graph_name)
                        client_obj.headers.setdefault("abution.graphId", graph_name)
                except Exception:
                    logger.warning("无法注入到 client.headers（非致命）")

                # Requests session headers（如果存在）
                try:
                    if hasattr(client_obj, "_session") and client_obj._session is not None:
                        client_obj._session.headers.setdefault("Authorization", auth_value)
                        client_obj._session.headers.setdefault("abution-graph-id", graph_name)
                        client_obj._session.headers.setdefault("abution.graphId", graph_name)
                        # ensure SSL verify setting propagates to connector session when possible
                        try:
                            # if we configured sess earlier, reuse its verify setting
                            cfg = ABUTION_CONFIG or {}
                            if cfg.get("use_ssl", False):
                                allow_self_signed = bool(cfg.get("allow_self_signed", False))
                                ssl_ca_cert = cfg.get("ssl_ca_cert")
                                if allow_self_signed:
                                    client_obj._session.verify = False
                                elif ssl_ca_cert:
                                    client_obj._session.verify = ssl_ca_cert
                                else:
                                    client_obj._session.verify = True
                        except Exception:
                            pass
                except Exception:
                    logger.warning("无法注入到 session.headers（非致命）")
        except Exception:
            logger.warning("注入认证 header 发生错误（非致命）")
        # 延迟创建 Graph 对象：不要在初始化时强绑定 graph，这样即便图服务不可用
        # 也不会阻塞后续处理（OCR/MD/三元组流程）。在需要写入/读取图时再尝试创建。
        self._graph = None
        self._advanced_retriever = None

    def init_graph(self, agent:bool=False, agent_sim_threshold=0.8):
        # 选择使用的模型
        print(f"初始化知识图谱: {self.graph_name}")
        if agent:
            monitor = Agg.VectorSimCrudAgent(self.graph_name, self.model_configs, threshold=agent_sim_threshold, enabled=True)
        else:
            monitor = Agg.FloatArrayAdd()
        print(monitor)

        # Attempt to create graph, but do not fail the whole process if graph service is down.
        try:
            self.gdb_client.add_graph(self.graph_name, get_knowlion_schema(monitor))
        except Exception as e:
            logger.warning(f"无法在 init_graph 中创建图（服务可能离线）: {e}")
            try:
                from utils.graph_outbox import enqueue_graph_creation
                schema = get_knowlion_schema(monitor)
                path = enqueue_graph_creation(self.graph_name, schema, {"reason": "init_graph_failed"})
                logger.info(f"图创建请求已写入 outbox: {path}")
            except Exception:
                logger.debug("写入 outbox 以延迟创建图失败（非致命）")

    def _ensure_graph(self, raise_on_fail: bool = False):
        """Lazily create and return Graph instance. If creation fails, return None
        (or raise if raise_on_fail=True)."""
        if getattr(self, '_graph', None) is not None:
            return self._graph
        try:
            self._graph = self.gdb_client.Graph(self.graph_name)
            return self._graph
        except Exception as e:
            logger.warning(f"无法创建图对象 ({self.graph_name}): {e}")
            if raise_on_fail:
                raise
            return None

    def _get_advanced_retriever(self):
        if getattr(self, '_advanced_retriever', None) is not None:
            return self._advanced_retriever
        g = self._ensure_graph(raise_on_fail=False)
        if g is None:
            logger.warning("高级检索器未初始化：图服务不可用")
            self._advanced_retriever = None
            return None
        try:
            self._advanced_retriever = AdvancedHyperGraphRAG(g, self.model)
            return self._advanced_retriever
        except Exception as e:
            logger.warning(f"初始化高级检索器失败: {e}")
            self._advanced_retriever = None
            return None

    def delete_graph(self):
        self.gdb_client.delete_graph(self.graph_name)

    def convert_to_markdown(self, model_path, file_path, file_name=None, save_pdf_dir=None, job_id: str = None, process_index: int = 0):
        """
        步骤1: 将原始文件转换为Markdown格式

        :param file_name: 文档名，未提供则大模型生成
        :param file_path: 原始文件路径
        :param save_pdf_dir: PDF保存目录，如果提供则保存PDF文件
        :return: 生成的Markdown内容
        """
        if file_name is None:
            file_name = self.extract_file_name(file_path)
        self.file_name = file_name

        # 创建文档解析器实例
        # 根据全局 PROCESSING_CONFIG 决定 OCR 使用 CPU 还是 GPU
        proc_cfg = PROCESSING_CONFIG or {}
        device_mode = str(proc_cfg.get("device_mode", "cpu")).lower()
        device_gpu = device_mode in ("cuda", "gpu")
        logger.info(f"初始化 Document2Markdown，device_mode={device_mode}")

        parser = Document2Markdown(
            vl_model=self.model,
            model_path=model_path,
            device_gpu=device_gpu
        )

        try:
            # 1. 将文档转换为PDF bytes
            logger.info(f"开始转换文档: {file_path}")
            pdf_bytes = parser.doc_to_pdf(file_path)
            logger.info(f"文档转换完成，PDF大小: {len(pdf_bytes)} bytes")

            # 2. 如果指定了保存PDF的目录，则保存PDF文件
            if save_pdf_dir:
                logger.info(f"保存PDF文件到目录: {save_pdf_dir}")
                parser.save_pdf_file(pdf_bytes, save_pdf_dir)

            # 3. 将PDF转换为Markdown
            logger.info("开始将PDF转换为Markdown")
            md_res = parser.pdf_to_markdown(pdf_bytes, job_id=job_id, process_index=process_index)
            # pdf_to_markdown 返回 (final_md, partial_files) 或 (final_md, partial_files, total_batches)
            total_batches = None
            if isinstance(md_res, tuple):
                if len(md_res) >= 3:
                    md_content, partial_files, total_batches = md_res[0], md_res[1], md_res[2]
                elif len(md_res) == 2:
                    md_content, partial_files = md_res
                else:
                    md_content = md_res[0]
                    partial_files = []
            else:
                md_content = md_res
                partial_files = []

            logger.info(f"Markdown转换完成，内容长度: {len(md_content)} 字符，部分文件数: {len(partial_files)}")

            return md_content, partial_files, total_batches

        except Exception as e:
            logger.error(f"文档转换失败: {e}")
            raise


    # 生成三元组
    def markdown_to_triple(self, job_id: int) -> List[Dict[str, Any]]:
        """从 `job.split_markdown_path` 指定的持久化文件中逐条处理待处理段落。
        每处理完一条，会从持久化文件中删除对应条目以便断点继续。
        """
        from repositories.jobs_repo import get_job_by_id

        job = get_job_by_id(job_id)
        if not job:
            logger.error(f"无效的 job_id: {job_id}")
            return []

        split_path = job.split_markdown_path
        if not split_path or not os.path.exists(split_path):
            logger.error(f"split_markdown_path 不存在: {split_path}")
            return []

        try:
            with open(split_path, 'r', encoding='utf-8') as f:
                to_process = json.load(f)
        except Exception as e:
            logger.error(f"读取 split_markdown_path 失败: {e}")
            return []

        extractor = Markdown2Triples(
            model_instance=self.model,
            md_content="",
            file_name=self.file_name,
            chunk_size=5000,
            overlap_size=600,
            max_chunk_limit=8000
        )

        # If called under a Flask app context, attach the app object to the extractor
        try:
            from flask import current_app
            try:
                extractor.app = current_app._get_current_object()
            except Exception:
                extractor.app = None
        except Exception:
            extractor.app = None

        logger.info(f"从持久化文件处理待处理段落数: {len(to_process)}")
        processed = extractor.process_paragraphs_parallel(to_process, job_id, persist_path=split_path)
        return processed

    def markdown_split_paragraphs(self, md_content) -> List[Dict[str, Any]]:
        """只做智能切分并返回段落列表（用于外部保存 to_process 列表）。"""
        extractor = Markdown2Triples(
            model_instance=self.model,
            md_content=md_content,
            file_name=self.file_name,
            chunk_size=5000,
            overlap_size=600,
            max_chunk_limit=8000
        )
        try:
            logger.info("智能切分Markdown文档（仅切分）")
            paragraphs = extractor.split_markdown_intelligently()
            logger.info(f"切分得到 {len(paragraphs)} 个段落（仅切分）")
            return paragraphs
        except Exception as e:
            logger.error(f"❌ Markdown 切分失败: {e}")
            return []


    def triple_to_knowledge(self, para_triples:List[Dict[str, Any]], classify_id=None) -> List[Knowledge]:
        """
        步骤2: 从Markdown内容提取知识

        :param additional_prompt: 附加提示语
        :param examples: 示例数据
        :return: 提取的知识信息
        """
        if para_triples is None:
            raise ValueError("请先执行提取知识程序！")

        extractor = Triples2Knowledge(
            model_instance=self.model,
            para_triples=para_triples,
            file_name=self.file_name,
            #file_name="中印度洋盆岩心沉殖物中稀土元素赋存特征",
            classify=classify_id
        )

        # 3. 构建知识图谱对象
        logger.info("构建知识图谱对象")
        knowledge_list = extractor.build_knowledge_objects()
        logger.info(f"构建了 {len(knowledge_list)} 个知识对象")

        logger.info("✅ 处理完成")
        return knowledge_list


    def knowledge_to_save(self, knowledge_list:list[Knowledge], classify_id=None):
        """
        步骤3: 将向量图谱并存储到图数据库
        """
        if classify_id is not None and not re.match(r'^[a-zA-Z0-9]+$', classify_id):
            raise ValueError("classify_id必须为英文和数字的组合")
        self.classify_id = classify_id

        if knowledge_list is None:
            raise ValueError("请先执行extract_knowledge方法提取知识信息")

        # 分段/批量传输以避免一次性请求体过大或内存峰值
        cfg = ABUTION_CONFIG or {}
        # 降低默认批大小以更保守地避免超大请求导致 413
        batch_size = int(cfg.get("batch_size", 20))
        max_retries = int(cfg.get("batch_retries", 2))
        retry_delay = float(cfg.get("batch_retry_delay", 0.5))

        total = len(knowledge_list)
        logger.info(f"开始分批保存知识对象，共 {total} 条，批大小 {batch_size}")

        from utils.graph_outbox import enqueue_batch

        for start in range(0, total, batch_size):
            end = min(start + batch_size, total)
            batch = knowledge_list[start:end]
            attempt = 0
            saved = False

            # Try to get/create Graph lazily
            graph = self._ensure_graph(raise_on_fail=False)
            if graph is None:
                logger.warning("图服务暂不可用：将批次写入本地 outbox 并继续")
                meta = {"start": start, "end": end}
                path = enqueue_batch(self.graph_name, batch, meta)
                logger.info(f"已写入 outbox: {path}")
                continue

            while True:
                try:
                    graph.add_knowledge(batch)
                    logger.info(f"已保存批次: {start}-{end-1}，数量: {len(batch)}")
                    saved = True
                    break
                except Exception as e:
                    attempt += 1
                    logger.warning(f"保存批次 {start}-{end-1} 失败 (尝试 {attempt}/{max_retries}): {e}")
                    if attempt > max_retries:
                        # On repeated failure, enqueue to outbox to avoid blocking
                        meta = {"start": start, "end": end, "error": str(e)}
                        path = enqueue_batch(self.graph_name, batch, meta)
                        logger.error(f"保存失败，已写入 outbox: {path}")
                        break
                    time.sleep(retry_delay)


    def search(self, text: str, top_k: int = 10, # TODO: 如果我们用自己的模型，可以只执行此函数
                        classify_list: List[str] = None) -> Dict[str, Any]:
        """
        先进的混合检索方法
        """
        try:
            results = self.advanced_retriever.hybrid_retrieval(text, top_k, classify_list)
            return results
        except Exception as e:
            logger.error(f"高级检索失败: {e}")
            return {"error": str(e)}

    def search_call(self, text: str, top_k: int = 10, # TODO: 或者依旧调用这个函数，配好api即可
                             classify_list: List[str] = None,
                             prompt: str = None, stream: bool = False):
        """
        基于先进检索的问答调用
        """
        # 执行检索
        retrieval_results = self.search(text, top_k, classify_list)

        if "error" in retrieval_results:
            return f"检索失败: {retrieval_results['error']}"

        # 构建LLM提示
        system_prompt = """
        你是一名专业知识解答助手，基于提供的检索结果回答用户问题。
        检索结果包含多路召回的综合排名，请优先参考高排名内容。
        """
        system_prompt = """
                    "你是一名专业知识解答助手，请通过大模型自主回答用户问题，再将答案与提供的信息结合给出更准确可靠的回答。" +
                    "如果问题相关的知识图谱数据缺失，则由AI助手根据经验回答。
                    """

        user_prompt = f"""
        用户问题: {text}

        知识库中检索到的内容:
        {json.dumps(retrieval_results.get('reasoning_paths', []), ensure_ascii=False, indent=2)}
        {json.dumps(retrieval_results.get('paragraphs', []), ensure_ascii=False, indent=2)}

        {prompt.strip() if prompt else ""}
        """

        return self.model.call_text_model(system_prompt, user_prompt, stream=stream)


    def extract_file_name(self, file_path):
        # 从file_path中提取文件名并进行特殊字符处理
        file_path = os.path.abspath(file_path)
        base_name = os.path.basename(file_path)
        file_name = os.path.splitext(base_name)[0]
        # 处理特殊字符，只保留字母、数字、中文和下划线，其他替换为下划线
        file_name = re.sub(r'[^\w\u4e00-\u9fff]', '_', file_name)
        # 避免多个连续下划线
        file_name = re.sub(r'_+', '_', file_name)
        # 去除首尾下划线
        file_name = file_name.strip('_')
        if file_name == "":
            file_name = str(uuid.uuid4())
        return file_name


def simplify_similarity_knows_list(data):
    """
    简化 similarityKnowsList 数据结构，保留所有属性但进行简化处理
    1. 对于desc属性，提取java.util.TreeSet中的值列表
    2. 对于hll属性，只保留cardinality值
    3. 使用更简洁的格式表示实体和关系
    """
    if not isinstance(data, dict):
        return data

    # 定义需要特殊处理的列表字段
    LIST_FIELDS = data.keys()

    # 定义需要移除的字段
    REMOVE_FIELDS = {'class', 'directed', 'matchedVertex'}

    def process_vertex(item):
        """处理顶点实体"""
        if not isinstance(item, dict):
            return item

        # 提取基本信息
        entity_name = item.get("vertex", "")
        # entity_label = item.get("label", "")
        properties = item.get("properties", {})
        if properties["v_label"]:
            properties.pop("v_label")

        # 处理特殊属性
        processed_props = {}
        for key, value in properties.items():
            if key in REMOVE_FIELDS:
                continue

            # 处理desc属性
            if key == "desc" and isinstance(value, dict):
                # 提取TreeSet中的值
                tree_set = value.get("java.util.TreeSet", [])
                if tree_set:
                    processed_props["desc"] = tree_set
                continue

            # 处理hll属性
            if key == "hll" and isinstance(value, dict):
                # 提取cardinality值
                cardinality = None
                for inner_value in value.values():
                    if isinstance(inner_value, dict) and "cardinality" in inner_value:
                        cardinality = inner_value["cardinality"]
                        break
                if cardinality is not None:
                    processed_props["hll"] = cardinality
                continue

            # 其他属性直接保留
            processed_props[key] = value

        # 构建结果字符串
        prop_str = "; ".join([f"{k}:{v}" for k, v in processed_props.items()])
        return f"{entity_name}: {{{prop_str}}}"
        # return f"{entity_name}({entity_label}): {{{prop_str}}}"

    def process_relation(item):
        """处理关系"""
        if not isinstance(item, dict):
            return item

        # 提取基本信息
        source = item.get("source", "")
        target = item.get("target", "")
        label = item.get("label", "")
        properties = item.get("properties", {})

        # 处理特殊属性
        processed_props = {}
        for key, value in properties.items():
            if key in REMOVE_FIELDS:
                continue

            # 处理desc属性
            if key == "relational" and isinstance(value, dict):
                # 提取TreeSet中的值
                tree_set = value.get("java.util.TreeSet", [])
                if tree_set:
                    label = tree_set
                continue

            # 其他属性直接保留
            processed_props[key] = value

        # 构建结果字符串
        prop_str = "; ".join([f"{k}:{v}" for k, v in processed_props.items()])
        return f"{source} → {target}: {{{prop_str}}}" # ({label})

    def process_chapter(item):
        """处理章节信息"""
        if 'abstract' in item:
            # 提取关键内容，移除重复信息
            abstract = item['abstract']
            # 只保留前3个关键点
            key_points = [point for point in abstract.split('\n') if point][:3]
            return "\n".join(key_points)
        return item.get('vertex', "") or item.get('label', "")

    simplified_data = {}
    for k, v in data.items():
        if k in LIST_FIELDS and isinstance(v, list):
            if k == 'vertex_entity':
                simplified_data[k] = [process_vertex(item) for item in v]
            elif k == 'vertex_relations':
                simplified_data[k] = [process_relation(item) for item in v]
            elif k in ['vertex_belong_chapters', 'vertex_belong_chapter_contexts']:
                simplified_data[k] = [process_chapter(item) for item in v]
            else:
                # 其他列表字段简单处理
                simplified_data[k] = [f"{item.get('vertex', '')} {item.get('label', '')}" for item in v]
        else:
            simplified_data[k] = v

    return simplified_data


def simplify_entity_description(entity_name, entity_label, properties):
    """
    简化实体描述，转成字符串格式
    """
    if not properties:
        return f"{entity_name}({entity_label})"

    # 优先使用关键属性
    key_attributes = ["description", "描述", "name", "名称", "title", "标题"]
    for attr in key_attributes:
        if attr in properties and properties[attr]:
            return f"{entity_name}({entity_label}): {properties[attr]}"

    # 如果没有关键属性，合并重要属性信息
    important_attributes = ["type", "类型", "category", "类别", "function", "功能", "role", "角色"]
    selected_props = {}
    for attr in important_attributes:
        if attr in properties and properties[attr]:
            selected_props[attr] = properties[attr]

    # 如果找到了重要属性，使用它们
    if selected_props:
        properties_text = "; ".join([f"{k}:{v}" for k, v in selected_props.items()])
        return f"{entity_name}({entity_label}): {properties_text}"

    # 最后回退到合并所有属性
    properties_text = "; ".join([f"{k}:{v}" for k, v in properties.items() if v])
    return f"{entity_name}({entity_label}): {properties_text}" if properties_text else f"{entity_name}({entity_label})"


def simplify_relation_description(source, target, label, properties):
    """
    简化关系描述，转成字符串格式
    """
    if not properties:
        return f"{source} --({label})--> {target}"

    # 优先使用关键属性作为关系描述
    key_attributes = ["description", "描述", "purpose", "目的", "action", "作用", "function", "功能"]
    for attr in key_attributes:
        if attr in properties and properties[attr]:
            return f"{source} --({label})--> {target}: {properties[attr]}"

    # 合并所有属性信息
    properties_text = "; ".join([f"{k}:{v}" for k, v in properties.items() if v])
    return f"{source} --({label})--> {target}: {properties_text}" if properties_text else f"{source} --({label})--> {target}"
