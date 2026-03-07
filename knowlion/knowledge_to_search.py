import logging
import json
import math
import sys
import traceback
from typing import Dict, List, Any, Tuple, Set
from collections import defaultdict
import numpy as np
from abutionpy import abution_functions as f
from abutionpy import abution_predicates as p
from abutionpy import abution_aggregator as agg

logger = logging.getLogger(__name__)


class AdvancedHyperGraphRAG:
    def __init__(self, graph, model_instance):
        self.graph = graph
        self.model_instance = model_instance
        self.rrf_k = 60  # RRF融合参数

    def cosine_similarity(self, vec1: List[float], vec2: List[float]) -> float:
        """计算余弦相似度"""
        if not vec1 or not vec2 or len(vec1) != len(vec2):
            return 0.0

        dot_product = sum(a * b for a, b in zip(vec1, vec2))
        norm_a = math.sqrt(sum(a * a for a in vec1))
        norm_b = math.sqrt(sum(b * b for b in vec2))

        if norm_a == 0 or norm_b == 0:
            return 0.0

        return dot_product / (norm_a * norm_b)

    def vector_and_bm25_retrieval(self, query_text: str, query_vector: List[float], top_k: int,
                                  classify_list: List[str] = None) -> tuple[set[Any], dict[str, float], dict[str, float]]:
        """优化的向量和BM25联合召回"""
        try:
            vec_sim = p.VectorIndexForSim([query_vector], top_k)
            bm25_sim = p.BM25IndexForSim(query_text, top_k=top_k)

            # 单次查询同时获取vector和BM25结果
            similarity_results = (self.graph
                                  # 1）计算vector和bm25相似度 - 作为核心结果与其它推理子查询的起点
                                  .V().label("Doc")
                                  .transform("vector", vec_sim).alias("sim_vec", "java.util.Map")
                                  .transform("doc_bm25", bm25_sim).alias("bm25_sim", "java.util.Map")
                                  .selectProps("sim_vec", "bm25_sim")
                                  .Store("SimEntity")

                                  # 1.1）获取向量相似的Top段落名和得分
                                  .Map([f.ItFunc([f.ExtractProperty("sim_vec")])])
                                  .Reduce(agg.HashMapAggregator(top_k))
                                  .Store("result_vec")

                                  # 1.2）查询向量相似的Top段落内容
                                  .Map([f.DictKeys()]).ToEntityIds()
                                  .V().label("Para")
                                  .transform(["vector"], f.FloatArraySimilarity(query_vector)).alias("vector_sim_score", "java.lang.Float")
                                  .selectProps("doc_name", "content", "type", "entity_count", "vector_sim_score")
                                  .Map([f.ParaContextTopScore(top_k)]).Store("vector_para_result")

                                  # 2.1）获取BM25相似的Top段落名和得分
                                  .Select("SimEntity")
                                  .Map([f.ItFunc([f.ExtractProperty("bm25_sim")])])
                                  .Reduce(agg.HashMapAggregator(top_k))
                                  .Store("result_bm25")

                                  # 2.2）查询BM25相似的Top段落内容
                                  .Map([f.DictKeys()]).ToEntityIds()
                                  .V().label("Para")
                                  .transform(["vector"], f.FloatArraySimilarity(query_vector)).alias("vector_sim_score", "java.lang.Float")
                                  .selectProps("doc_name", "content", "type", "entity_count", "vector_sim_score")
                                  .Map([f.ParaContextTopScore(top_k)]).Store("bm25_para_result")

                                  .Selects(["result_vec", "result_bm25", "vector_para_result", "bm25_para_result"])
                                  .exec(classify_list))

            vec_result_raw:dict[str, float] = similarity_results.get("result_vec", [])[0]
            bm25_result_raw:dict[str, float] = similarity_results.get("result_bm25", [])[0]
            vector_para_result:dict[str, float] = similarity_results.get("vector_para_result", [])[0]
            bm25_para_result:dict[str, float] = similarity_results.get("bm25_para_result", [])[0]

            # print(vec_result_raw.keys())
            # print(vector_para_result)
            # print(bm25_para_result)

            # 汇总keys
            initial_para_keys = set()
            if vec_result_raw:
                initial_para_keys.update(vec_result_raw.keys())
            if bm25_result_raw:
                initial_para_keys.update(bm25_result_raw.keys())

            return initial_para_keys, vector_para_result, bm25_para_result

        except Exception as e:
            logger.error(f"向量召回失败: {e}")
            return set(), {}, {}


    def multi_hop_reasoning_retrieval(self, initial_paras: List[str],
                                              query_vector: List[float],
                                              top_k: int, classify_list: List[str] = None) -> Dict[str, Any]:
        """多跳推理召回 - 返回结构化推理路径信息"""
        # 新方案（一次计算）
        vectorSimWeight = 0.4
        importanceWeight = 0.3
        occurCountWeight = 0.2
        neighborsWeight = 0.1
        reasoning_paths = (self.graph.V(initial_paras)
           .OutV().label("Entity").transform(["vector"], f.FloatArraySimilarity(query_vector)).alias("vector_sim_score", "java.lang.Float")
           .selectProps("vector_sim_score", "importance", "occur_count", "neighbors", "details")
           .Map([f.EntityScoreTopK(top_k)]).Store("paths")  # 起点（过滤出相似度高的TopN - 各属性使用默认权重）
           .ToVertices().Store("vertex_start").Store("vertex_list")
           # 从所有起点出发推理关系
           .Select("vertex_start").ToEntityIds()
           # （出边）
           # 一跳邻居
           .OutV().label("Entity").transform(["vector"], f.FloatArraySimilarity(query_vector)).alias("vector_sim_score", "java.lang.Float")
           .selectProps("vector_sim_score", "importance", "occur_count", "neighbors", "details")
           .Map([f.EntityScoreTopK(top_k * 2)]).Store("paths")  # 多属性融合排序（过滤出相似度高的TopN）
           .ToVertices().Store("vertex_list").ToEntityIds()
           # 二跳邻居
           .OutV().label("Entity").transform(["vector"], f.FloatArraySimilarity(query_vector)).alias("vector_sim_score", "java.lang.Float")
           .selectProps("vector_sim_score", "importance", "occur_count", "neighbors", "details")
           .Map([f.EntityScoreTopK(top_k)]).Store("paths")  # 多属性融合排序（过滤出相似度高的TopN）
           .ToVertices().Store("vertex_list")
           # （进边）
           .Select("vertex_start").ToEntityIds()
           # 一跳邻居
           .InV().label("Entity").transform(["vector"], f.FloatArraySimilarity(query_vector)).alias("vector_sim_score", "java.lang.Float")
           .selectProps("vector_sim_score", "importance", "occur_count", "neighbors", "details")
           .Map([f.EntityScoreTopK(top_k * 2)]).Store("paths")  # 多属性融合排序（过滤出相似度高的TopN）
           .ToVertices().Store("vertex_list").ToEntityIds()
           # 二跳邻居
           .InV().label("Entity").transform(["vector"], f.FloatArraySimilarity(query_vector)).alias("vector_sim_score", "java.lang.Float")
           .selectProps("vector_sim_score", "importance", "occur_count", "neighbors", "details")
           .Map([f.EntityScoreTopK(top_k)]).Store("paths")  # 多属性融合排序（过滤出相似度高的TopN）
           .ToVertices().Store("vertex_list").ToEntityIds()

           # 获取所有实体的关系
           .Select("vertex_list").ToEntityIds()
           .WithinE().label("Entity2Entity").selectProps("fact").Store("paths")
           .Select("paths").Map([f.ReasoningPathTop(top_k * 2)])
           .exec(classify_list))

        print(reasoning_paths)

        # 返回结构：{"entity_in_para_details":["vertex:details",...], "edges":["source-target:fact"]}
        return reasoning_paths


    def _parse_and_structure_reasoning_paths(self, reasoning_paths: Dict, query_vector: List[float],
                                             seed_entities: Set[str], top_k: int) -> Dict[str, Any]:
        """解析推理路径并转换为结构化格式"""
        # 分离节点和边
        nodes = reasoning_paths.get("path_nodes", [])
        edges = reasoning_paths.get("path_edges", [])

        # 构建节点映射和边映射
        node_map = {}
        edge_map = {}

        for node in nodes:
            if isinstance(node, dict) and node.get("class", "").endswith("Entity"):
                vertex = node.get("vertex")
                if vertex:
                    node_map[vertex] = node

        for edge in edges:
            if isinstance(edge, dict) and edge.get("class", "").endswith("Edge"):
                source = edge.get("source")
                target = edge.get("target")
                if source and target:
                    edge_key = f"{source}->{target}"
                    edge_map[edge_key] = edge
                    # 同时存储反向边
                    reverse_key = f"{target}->{source}"
                    edge_map[reverse_key] = edge

        # 构建路径并计算得分
        all_paths = []

        def build_paths(current_path: List[str], current_vectors: List[List[float]],
                        current_entities: List[Dict], depth: int, max_depth: int = 2):
            if depth >= max_depth:
                return

            current_entity = current_path[-1]

            # 查找所有邻居
            for target_entity in node_map.keys():
                if target_entity == current_entity or target_entity in current_path:
                    continue

                edge_key = f"{current_entity}->{target_entity}"
                if edge_key in edge_map:
                    # 构建新路径
                    new_path = current_path + [target_entity]
                    target_node = node_map[target_entity]
                    target_vector = target_node.get("properties", {}).get("vector", {}).get("[F", [])
                    new_vectors = current_vectors + [target_vector]
                    new_entities = current_entities + [target_node]

                    # 计算路径得分
                    path_score = self._calculate_path_score(new_path, new_vectors, new_entities,
                                                            query_vector, seed_entities)

                    all_paths.append((new_path, path_score))

                    # 继续构建路径
                    build_paths(new_path, new_vectors, new_entities, depth + 1, max_depth)

        # 从每个种子实体开始构建路径
        for seed in seed_entities:
            if seed in node_map:
                seed_node = node_map[seed]
                seed_vector = seed_node.get("properties", {}).get("vector", {}).get("[F", [])
                build_paths([seed], [seed_vector], [seed_node], 0)

        # 去重并取topN路径
        unique_paths = self._deduplicate_and_select_paths(all_paths, top_k)

        # 转换为结构化格式
        return self._convert_to_structured_format(unique_paths, node_map, edge_map)

    def _deduplicate_and_select_paths(self, all_paths: List[Tuple[List[str], float]], top_k: int) -> List[
        Tuple[List[str], float]]:
        """去重并选择topN路径"""
        if not all_paths:
            return []

        # 按得分排序
        sorted_paths = sorted(all_paths, key=lambda x: x[1], reverse=True)

        # 去重策略：基于路径实体集合
        unique_paths = []
        seen_entity_sets = set()

        for path, score in sorted_paths:
            # 创建路径的实体集合（排序后作为唯一标识）
            entity_set = frozenset(sorted(path))

            if entity_set not in seen_entity_sets and len(path) >= 2:
                unique_paths.append((path, score))
                seen_entity_sets.add(entity_set)

                if len(unique_paths) >= top_k:
                    break

        return unique_paths

    def _convert_to_structured_format(self, paths: List[Tuple[List[str], float]],
                                      node_map: Dict, edge_map: Dict) -> Dict[str, Any]:
        """将路径转换为结构化格式"""
        # 收集所有实体和边
        all_entities = set()
        all_edges = set()

        for path, score in paths:
            # 提取路径中的所有实体
            all_entities.update(path)

            # 提取路径中的所有边（两两组合）
            for i in range(len(path) - 1):
                source = path[i]
                target = path[i + 1]
                edge_key = f"{source}->{target}"
                all_edges.add((source, target, edge_key))

        # 构建实体描述列表
        entities_list = []
        for entity_name in all_entities:
            if entity_name in node_map:
                entity_data = node_map[entity_name]
                description = self._extract_entity_description(entity_data)
                entities_list.append(f"{entity_name}:{description}")

        # 构建边描述列表
        edges_list = []
        for source, target, edge_key in all_edges:
            if edge_key in edge_map:
                edge_data = edge_map[edge_key]
                fact_description = self._extract_edge_fact_description(edge_data)
                edges_list.append(f"{source}->{target}:{fact_description}")
            else:
                # 如果没有关系事实，使用空描述
                edges_list.append(f"{source}->{target}:")

        return {
            "entities": entities_list,
            "edges": edges_list
        }

    def _extract_entity_description(self, entity_data: Dict) -> str:
        """提取实体描述"""
        properties = entity_data.get("properties", {})

        # 1. 首先尝试从details中提取描述
        details = properties.get("details", {})
        if "cn.thutmose.abution.graph.type.CustomMap" in details:
            custom_map = details["cn.thutmose.abution.graph.type.CustomMap"]
            json_storage = custom_map.get("jsonStorage", [])
            if json_storage:
                # 取第一个pair的second作为描述
                first_pair = json_storage[0]
                if "cn.thutmose.abution.graph.commonutil.pair.Pair" in first_pair:
                    pair_data = first_pair["cn.thutmose.abution.graph.commonutil.pair.Pair"]
                    description = pair_data.get("second", "")
                    if description:
                        return description

        # 2. 如果details中没有，尝试从labels中获取
        labels = properties.get("labels", {})
        if "java.util.TreeSet" in labels:
            label_list = labels["java.util.TreeSet"]
            if label_list:
                return f"类型:{','.join(label_list)}"

        # 3. 最后返回空字符串
        return ""

    def _extract_edge_fact_description(self, edge_data: Dict) -> str:
        """提取边关系事实描述"""
        properties = edge_data.get("properties", {})
        fact_data = properties.get("fact", {})

        if "java.util.TreeSet" in fact_data:
            facts = fact_data["java.util.TreeSet"]
            if facts:
                # 拼接所有事实描述
                return ';'.join(facts)

        return ""

    def hybrid_retrieval(self, query_text: str, top_k: int = 10,
                         classify_list: List[str] = None) -> Dict[str, Any]:
        """优化的混合检索主方法 - 避免重复查询"""
        # 1. 查询向量化
        query_vector = self.model_instance.call_embed_model([query_text])[0]

        # 2. 多路召回
        all_results = {}
        paragraph_cache = {}  # 缓存段落详细信息

        # 路1+2：基础向量+BM25文本联合召回
        initial_para_keys, vector_para_result, bm25_para_result = self.vector_and_bm25_retrieval(
            query_text, query_vector, top_k * 2, classify_list)
        all_results["vector_similarity_para"] = vector_para_result
        all_results["bm25_similarity_para"] = bm25_para_result

        # 初始化推理路径结果
        reasoning_retrieval = {"entity_in_para_details": [], "edges": []}

        if initial_para_keys:
            # 路3：上下文关联召回
            context_para_score_map = self.context_associated_retrieval(
                list(initial_para_keys), query_vector, top_k * 2, classify_list)
            all_results["related_context_para"] = context_para_score_map

            # 路4 & 路5：跨文档段落关联召回 & 多跳推理召回
            context_para_ids = [para_info.split("(")[0] for para_info in context_para_score_map.keys()]
            cross_doc_para_score_map, reasoning_retrieval = self.cross_doc_and_multi_hop_retrieval(
                list(initial_para_keys), context_para_ids, query_vector, top_k, classify_list)
            all_results["cross_doc_para"] = cross_doc_para_score_map

        print("All results for RRF fusion:", {k: len(v) for k, v in all_results.items()})

        # 3. RRF融合排序（vector_similarity_para+bm25_similarity_para+related_context_para+cross_doc_para）
        final_results = self.rrf_fusion_with_formatted_paragraphs(all_results, top_k)

        return {
            "query": query_text,
            #"final_ranking": final_results,
            "path_scores": {k: len(v) for k, v in all_results.items()},
            "reasoning_paths": reasoning_retrieval,
            "paragraphs": [para for para, score in final_results]  # 只返回段落内容，不包含分数
        }

    def rrf_fusion_with_formatted_paragraphs(self, all_results: Dict[str, Any], top_k: int) -> List[Tuple[str, float]]:
        """RRF融合排序算法 - 处理格式化段落结果"""

        # 提取段落ID到格式化内容的映射
        para_id_to_content = {}

        # 处理vector_similarity_para
        vector_ranked_list = []
        if all_results.get("vector_similarity_para"):
            for formatted_content, score in all_results["vector_similarity_para"].items():
                # 从格式化内容中提取段落ID（第一个括号前的内容）
                para_id = formatted_content.split("(")[0].strip()
                para_id_to_content[para_id] = formatted_content
                vector_ranked_list.append((para_id, score))

        # 处理bm25_similarity_para
        bm25_ranked_list = []
        if all_results.get("bm25_similarity_para"):
            for formatted_content, score in all_results["bm25_similarity_para"].items():
                para_id = formatted_content.split("(")[0].strip()
                para_id_to_content[para_id] = formatted_content
                bm25_ranked_list.append((para_id, score))

        # 处理related_context_para
        related_ranked_list = []
        if all_results.get("related_context_para"):
            for formatted_content, score in all_results["related_context_para"].items():
                para_id = formatted_content.split("(")[0].strip()
                para_id_to_content[para_id] = formatted_content
                related_ranked_list.append((para_id, score))

        # 处理cross_doc_para
        cross_doc_ranked_list = []
        if all_results.get("cross_doc_para"):
            for formatted_content, score in all_results["cross_doc_para"].items():
                para_id = formatted_content.split("(")[0].strip()
                para_id_to_content[para_id] = formatted_content
                cross_doc_ranked_list.append((para_id, score))

        # print(f"Extracted {len(para_id_to_content)} unique paragraphs from all methods")

        # 构建RRF输入
        ranked_lists = {}
        if vector_ranked_list:
            # 按原始分数排序
            vector_ranked_list.sort(key=lambda x: x[1], reverse=True)
            ranked_lists["vector"] = vector_ranked_list
            # print(f"Vector results: {len(vector_ranked_list)} items")

        if bm25_ranked_list:
            bm25_ranked_list.sort(key=lambda x: x[1], reverse=True)
            ranked_lists["bm25"] = bm25_ranked_list
            # print(f"BM25 results: {len(bm25_ranked_list)} items")

        if related_ranked_list:
            related_ranked_list.sort(key=lambda x: x[1], reverse=True)
            ranked_lists["related"] = related_ranked_list
            # print(f"Related context results: {len(related_ranked_list)} items")

        if cross_doc_ranked_list:
            cross_doc_ranked_list.sort(key=lambda x: x[1], reverse=True)
            ranked_lists["cross_doc"] = cross_doc_ranked_list
            # print(f"Cross-doc results: {len(cross_doc_ranked_list)} items")

        # 执行RRF融合
        if ranked_lists:
            rrf_results = self.reciprocal_rank_fusion(ranked_lists, top_k * 2)  # 取2倍用于后续处理
            # print(f"RRF fusion produced {len(rrf_results)} candidate results")

            # 将段落ID转换回格式化内容
            final_formatted_results = []
            for para_id, rrf_score in rrf_results:
                if para_id in para_id_to_content:
                    final_formatted_results.append((para_id_to_content[para_id], rrf_score))
                else:
                    # 如果找不到格式化内容，使用段落ID作为内容
                    final_formatted_results.append((para_id, rrf_score))

            # 按RRF分数排序并返回top_k
            final_formatted_results.sort(key=lambda x: x[1], reverse=True)
            return final_formatted_results[:top_k]
        else:
            print("No valid results for RRF fusion")
            return []

    def reciprocal_rank_fusion(self, ranked_lists: Dict[str, List[Tuple[str, float]]], top_k: int) -> List[Tuple[str, float]]:
        """RRF算法融合多路召回结果"""
        from collections import defaultdict

        scores = defaultdict(float)

        for list_name, ranked_list in ranked_lists.items():
            if not ranked_list:
                continue
            for rank, (item, score) in enumerate(ranked_list):
                # RRF公式: 1 / (k + rank)
                # 注意: rank从0开始，所以实际排名是rank+1
                scores[item] += 1.0 / (self.rrf_k + rank + 1)

        # 按RRF分数排序
        fused_results = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        return fused_results[:top_k]


    def _calculate_path_score(self, path: List[str], path_vectors: List[List[float]],
                              path_entities: List[Dict], query_vector: List[float],
                              seed_entities: Set[str]) -> float:
        """计算单条路径的得分"""
        if not path_vectors:
            return 0.0

        # 1. 计算路径向量聚合（加权平均）
        aggregated_vector = self._aggregate_path_vectors(path_vectors, path_entities)

        # 2. 语义相似度得分
        semantic_score = self.cosine_similarity(query_vector, aggregated_vector)

        # 3. 路径质量得分
        path_quality_score = self._calculate_path_quality(path_entities, seed_entities)

        # 4. 实体重要性得分
        importance_score = self._calculate_path_importance(path_entities)

        # 5. 路径多样性得分
        diversity_score = self._calculate_path_diversity(path_entities)

        # 综合得分
        final_score = (semantic_score * 0.4 +
                       path_quality_score * 0.3 +
                       importance_score * 0.2 +
                       diversity_score * 0.1)

        return max(0.0, min(1.0, final_score))

    def _aggregate_path_vectors(self, path_vectors: List[List[float]], path_entities: List[Dict]) -> List[float]:
        """加权平均聚合路径上所有实体的向量"""
        if not path_vectors:
            return []

        # 计算每个实体的权重（基于置信度和重要性）
        weights = []
        for entity in path_entities:
            properties = entity.get("properties", {})
            confidence = self._extract_quantile_value(properties.get("confidence", {}), 0.5)
            importance = self._extract_quantile_value(properties.get("importance", {}), 0.5)
            weight = confidence * importance
            weights.append(weight)

        # 归一化权重
        if sum(weights) > 0:
            weights = [w / sum(weights) for w in weights]
        else:
            weights = [1.0 / len(weights)] * len(weights)

        # 加权平均
        vector_dim = len(path_vectors[0])
        aggregated = [0.0] * vector_dim

        for i, vector in enumerate(path_vectors):
            if len(vector) == vector_dim:
                for j in range(vector_dim):
                    aggregated[j] += vector[j] * weights[i]

        return aggregated

    def _calculate_path_quality(self, path_entities: List[Dict], seed_entities: Set[str]) -> float:
        """计算路径质量得分"""
        if not path_entities:
            return 0.0

        quality_scores = []

        for i, entity in enumerate(path_entities):
            entity_name = entity.get("vertex")
            properties = entity.get("properties", {})

            # 基础质量指标
            confidence = self._extract_quantile_value(properties.get("confidence", {}), 0.3)
            importance = self._extract_quantile_value(properties.get("importance", {}), 0.3)

            # 距离惩罚（距离种子实体越远，权重越低）
            distance_penalty = 1.0
            if entity_name not in seed_entities:
                distance_penalty = max(0.5, 1.0 - i * 0.2)  # 每跳减少20%

            entity_quality = (confidence + importance) / 2 * distance_penalty
            quality_scores.append(entity_quality)

        return sum(quality_scores) / len(quality_scores)

    def _calculate_path_importance(self, path_entities: List[Dict]) -> float:
        """计算路径重要性得分"""
        if not path_entities:
            return 0.0

        importance_scores = []

        for entity in path_entities:
            properties = entity.get("properties", {})
            importance = self._extract_quantile_value(properties.get("importance", {}), 0.0)

            # 邻居多样性奖励
            neighbors = properties.get("neighbors", {})
            diversity_bonus = 1.0
            if "cn.thutmose.abution.graph.type.cardinality.DistinctCountHllp" in neighbors:
                neighbor_count = neighbors["cn.thutmose.abution.graph.type.cardinality.DistinctCountHllp"].get(
                    "cardinality", 0)
                diversity_bonus = 1.0 + min(neighbor_count * 0.05, 0.3)  # 最多增加30%

            entity_importance = importance * diversity_bonus
            importance_scores.append(entity_importance)

        return sum(importance_scores) / len(importance_scores)

    def _calculate_path_diversity(self, path_entities: List[Dict]) -> float:
        """计算路径多样性得分"""
        if len(path_entities) <= 1:
            return 0.0

        # 计算实体类型的多样性
        entity_types = set()
        for entity in path_entities:
            labels = entity.get("properties", {}).get("labels", {})
            if "java.util.TreeSet" in labels:
                entity_types.update(labels["java.util.TreeSet"])

        type_diversity = len(entity_types) / max(len(path_entities), 1)
        return type_diversity

    def _extract_quantile_value(self, quantile_data: Dict, default: float) -> float:
        """提取分位数数据中的值"""
        if not quantile_data:
            return default

        quantile_class = "cn.thutmose.abution.graph.type.quantile.QuantileDoubles"
        if quantile_class in quantile_data:
            values = quantile_data[quantile_class].get("values", [default])
            # 处理 None 值和空值的情况
            if values is None or not values:
                return default
            return float(values[0]) if values else default
        return default

    def context_associated_retrieval(self, initial_paras: List[str], query_vector: List[float], top_k: int,
                                     classify_list: List[str] = None) -> dict[str, float]:
        """优化的上下文关联召回 - 返回段落ID和格式化字符串"""
        if not initial_paras:
            return {}

        try:
            # 获取直接相邻的上下文段落
            context_results = \
                (self.graph.V(list(initial_paras))
                   .BothV().label("Para")
                   .transform(["vector"], f.FloatArraySimilarity(query_vector)).alias("vector_sim_score", "java.lang.Float")
                   .selectProps("doc_name", "content", "type", "entity_count", "vector_sim_score")
                   .ToSet()
                   .Map([f.ParaContextTopScore(top_k)])
                   .exec(classify_list))

            return context_results

        except Exception as e:
            logger.error(f"上下文关联召回失败: {e}")
            return {}


    def cross_doc_and_multi_hop_retrieval(self, initial_paras: List[str], context_para_ids: List[str], query_vector: List[float],
                                    top_k: int, classify_list: List[str] = None) -> Tuple[dict[str, float], dict[str, float]]:
        """跨文档段落关联召回 - 返回段落ID和格式化字符串"""
        if not initial_paras:
            return {},{}

        result_34 = \
            (self.graph.V(initial_paras)

             # # 路3：跨文档段落关联召回 --------------------------------------------------------------------------------
              .ToEntityIds().Store("initial_paras")
              .OutV().label("Entity").selectProps()
              .InV().label("Para").has(["VERTEX"], p.Not(p.IsIn( initial_paras+context_para_ids )))
              .transform(["vector"], f.FloatArraySimilarity(query_vector)).alias("vector_sim_score", "java.lang.Float")
              .selectProps("doc_name", "content", "type", "entity_count", "vector_sim_score")
              .ToSet()
              .Map([f.ParaContextTopScore(top_k)])
              .Store("cross_doc_para_result")

             # # 路4：多跳推理召回 ----------------------------------------------------------------------------
             .Select("initial_paras")
             .OutV().label("Entity").transform(["vector"], f.FloatArraySimilarity(query_vector))
                .alias("vector_sim_score", "java.lang.Float")
             .selectProps("vector_sim_score", "importance", "occur_count", "neighbors", "details")
             .ToSet()
             .Map([f.EntityScoreTopK(top_k)]).Store("paths")  # 起点（过滤出相似度高的TopN - 各属性使用默认权重）
             .ToVertices().ToSet().Store("vertex_start").Store("vertex_list")
             # 从所有起点出发推理关系
             .Select("vertex_start").ToEntityIds()
             # （出边）
             # 一跳邻居
             .OutV().label("Entity").transform(["vector"], f.FloatArraySimilarity(query_vector))
                .alias("vector_sim_score", "java.lang.Float")
             .selectProps("vector_sim_score", "importance", "occur_count", "neighbors", "details")
             .ToSet()
             .Map([f.EntityScoreTopK(top_k * 2)]).Store("paths")  # 多属性融合排序（过滤出相似度高的TopN）
             .ToVertices().Store("vertex_list").ToEntityIds()
             # 二跳邻居
             .OutV().label("Entity").transform(["vector"], f.FloatArraySimilarity(query_vector))
                .alias("vector_sim_score", "java.lang.Float")
             .selectProps("vector_sim_score", "importance", "occur_count", "neighbors", "details")
             .ToSet()
             .Map([f.EntityScoreTopK(top_k)]).Store("paths")  # 多属性融合排序（过滤出相似度高的TopN）
             .ToVertices().Store("vertex_list")
             # （进边）
             .Select("vertex_start").ToEntityIds()
             # 一跳邻居
             .InV().label("Entity").transform(["vector"], f.FloatArraySimilarity(query_vector))
                .alias("vector_sim_score", "java.lang.Float")
             .selectProps("vector_sim_score", "importance", "occur_count", "neighbors", "details")
             .ToSet()
             .Map([f.EntityScoreTopK(top_k * 2)]).Store("paths")  # 多属性融合排序（过滤出相似度高的TopN）
             .ToVertices().Store("vertex_list").ToEntityIds()
             # 二跳邻居
             .InV().label("Entity").transform(["vector"], f.FloatArraySimilarity(query_vector))
                .alias("vector_sim_score", "java.lang.Float")
             .selectProps("vector_sim_score", "importance", "occur_count", "neighbors", "details")
             .ToSet()
             .Map([f.EntityScoreTopK(top_k)]).Store("paths")  # 多属性融合排序（过滤出相似度高的TopN）
             .ToVertices().Store("vertex_list").ToEntityIds()

             # 获取所有实体的关系
             .Select("vertex_list").ToEntityIds().ToSet()
             .WithinE().label("Entity2Entity").selectProps("fact").Store("paths")
             .Select("paths")
             .Map([f.ReasoningPathTop(top_k * 2)])
             .Store("reasoning_retrieval")

             .Selects(["cross_doc_para_result", "reasoning_retrieval"])
             .exec(classify_list))

        return result_34.get("cross_doc_para_result",[])[0], result_34.get("reasoning_retrieval",[])[0]

'''
相关自定义扩展函数解释：
· ReasoningPathTop：对Entity/Edge集合的推理召回路径进行简化处理，解析为格式化字符串，分别组织到entity_in_para_details和edges列表中，内设多属性融合排序与剪支算法。
· EntityScoreTopK：对Entity集合中每个实体进行多属性融合评分后排序，将4个属性("occur_count", "importance", "neighbors", "vector_sim_score")按权重比例计算得分后融合排序，保留top_entity
· FloatArraySimilarity：计算两个浮点数组的余弦相似度
· ParaContextTopK：对ParaEntity集合按照vector_sim_score倒序排序，取top_k个并格式化为字符串返回
· ParaContextTopScore：对ParaEntity集合按照融合得分（相似度得分 + 实体质量得分）倒序排序，返回字典：{取top_k个实体格式化为字符串作为key, 评分为value}
· VectorSimTopEntity：对Entity集合按照字段vector_sim_score排序，返回top_k个Entity集合
· 
'''
