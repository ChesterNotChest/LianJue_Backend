from abc import ABC, abstractmethod
import time
from typing import List, Any, Dict


class GraphAdapter(ABC):
    """抽象图适配器接口。

    实现至少需要提供邻居/前驱、节点产出(outcomes)和学习耗时(cost)的查询方法，
    以便候选生成器在内存图或远程图服务间切换。
    """

    @abstractmethod
    def get_neighbors(self, node: Any, direction: str = 'forward') -> List[Any]:
        raise NotImplementedError()

    @abstractmethod
    def get_prerequisites(self, node: Any) -> List[Any]:
        raise NotImplementedError()

    @abstractmethod
    def get_outcomes(self, node: Any) -> List[str]:
        raise NotImplementedError()

    @abstractmethod
    def get_cost(self, node: Any) -> float:
        raise NotImplementedError()

    def get_edge_metadata(self, source: Any, target: Any) -> Dict[str, Any]:
        return {"source": "syllabus", "confidence": 1.0}

    def incr_read(self):
        """可选：统计一次图读操作（默认无-op）。"""
        return


class InMemoryGraphAdapter(GraphAdapter):
    def __init__(self, learning_tree: Dict[str, Dict], simulate_delay: float = 0.0):
        self.learning_tree = learning_tree
        self._reads = 0
        self.delay = float(simulate_delay or 0.0)

    def get_neighbors(self, node, direction: str = 'forward'):
        self.incr_read()
        if direction == 'forward':
            nbrs = []
            for nid, n in self.learning_tree.items():
                if node in n.get('prerequisites', []):
                    nbrs.append(nid)
            return nbrs
        else:
            return self.get_prerequisites(node)

    def get_prerequisites(self, node):
        self.incr_read()
        return list(self.learning_tree.get(node, {}).get('prerequisites', []))

    def get_outcomes(self, node):
        self.incr_read()
        return list(self.learning_tree.get(node, {}).get('outcomes', []))

    def get_cost(self, node):
        self.incr_read()
        return float(self.learning_tree.get(node, {}).get('learning_time_est', 1))

    def get_edge_metadata(self, source, target):
        self.incr_read()
        target_node = self.learning_tree.get(target, {})
        edge_sources = target_node.get("edge_sources") if isinstance(target_node.get("edge_sources"), dict) else {}
        edge_confidence = target_node.get("edge_confidence") if isinstance(target_node.get("edge_confidence"), dict) else {}
        source_key = str(source)
        return {
            "source": edge_sources.get(source_key, "syllabus"),
            "confidence": float(edge_confidence.get(source_key, 1.0)),
        }

    def incr_read(self):
        self._reads += 1
        if self.delay > 0:
            time.sleep(self.delay)

    def get_stats(self):
        return {'node_reads': self._reads}


class KnowLionGraphAdapter(GraphAdapter):
    """轻量封装 KnowLion/Abution 的适配器。

    说明：KnowLion 的运行环境与 API 可能因安装/配置不同而有所差异，
    本实现尝试按常见方法调用图对象的遍历API（`.V(...).OutV()` 等）。
    如果你的服务有不同的方法签名，可以在此处调整实现。
    """
    def __init__(self, knowlion_instance):
        self.k = knowlion_instance
        self._reads = 0

    def _ensure_graph(self):
        g = None
        try:
            g = self.k._ensure_graph(raise_on_fail=False)
        except Exception:
            g = None
        return g

    def get_neighbors(self, node, direction: str = 'forward'):
        self.incr_read()
        g = self._ensure_graph()
        if g is None:
            return []
        try:
            if direction == 'forward':
                res = g.V(node).OutV().ToEntityIds().exec(None)
            else:
                res = g.V(node).InV().ToEntityIds().exec(None)
            # exec may return list or structure; try to normalize
            if isinstance(res, list):
                return [r for r in res]
            if isinstance(res, dict) and 'vertex_list' in res:
                return res.get('vertex_list', [])
            return []
        except Exception:
            return []

    def get_prerequisites(self, node):
        # assume prerequisites are incoming edges
        return self.get_neighbors(node, direction='backward')

    def get_outcomes(self, node):
        self.incr_read()
        g = self._ensure_graph()
        if g is None:
            return []
        try:
            props = g.V(node).selectProps('details').exec(None)
            # best-effort parse
            if isinstance(props, list) and props:
                p = props[0]
                # attempt to find stored outcomes in details
                return p.get('details', {}).get('outcomes', []) if isinstance(p, dict) else []
        except Exception:
            pass
        return []

    def get_cost(self, node):
        self.incr_read()
        g = self._ensure_graph()
        if g is None:
            return 1.0
        try:
            props = g.V(node).selectProps('learning_time_est').exec(None)
            if isinstance(props, list) and props:
                val = props[0].get('learning_time_est')
                return float(val) if val is not None else 1.0
        except Exception:
            pass
        return 1.0

    def incr_read(self):
        self._reads += 1

    def get_stats(self):
        return {'node_reads': self._reads}
