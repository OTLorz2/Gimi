"""
混合检索实现
结合关键词、路径和向量检索
"""

import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Dict, Tuple, Callable

from gimi.indexing.git_collector import CommitMetadata
from gimi.indexing.lightweight_index import LightweightIndex


@dataclass
class SearchResult:
    """搜索结果"""

    commit: CommitMetadata
    score: float
    keyword_score: float = 0.0
    path_score: float = 0.0
    vector_score: float = 0.0

    @property
    def combined_score(self) -> float:
        """综合得分（用于排序）"""
        return self.score


class HybridSearcher:
    """
    混合检索器

    结合多种检索策略:
    1. 关键词检索: 基于commit message的BM25/TF-IDF
    2. 路径检索: 基于文件路径的匹配
    3. 向量检索: 基于语义相似度（需要向量索引）

    融合策略: 加权求和 + RRF(Reciprocal Rank Fusion)
    """

    def __init__(
        self,
        lightweight_index: LightweightIndex,
        keyword_weight: float = 0.3,
        path_weight: float = 0.3,
        vector_weight: float = 0.4,
        use_rrf: bool = True,
        rrf_k: int = 60,
    ):
        """
        初始化混合检索器

        Args:
            lightweight_index: 轻量索引实例
            keyword_weight: 关键词检索权重
            path_weight: 路径检索权重
            vector_weight: 向量检索权重
            use_rrf: 是否使用RRF融合
            rrf_k: RRF参数
        """
        self.lw_index = lightweight_index
        self.keyword_weight = keyword_weight
        self.path_weight = path_weight
        self.vector_weight = vector_weight
        self.use_rrf = use_rrf
        self.rrf_k = rrf_k

        # 归一化权重
        total = keyword_weight + path_weight + vector_weight
        if total > 0:
            self.keyword_weight /= total
            self.path_weight /= total
            self.vector_weight /= total

    def _keyword_search(
        self,
        query: str,
        candidate_hashes: Optional[set] = None,
        top_k: int = 100,
    ) -> Dict[str, float]:
        """
        关键词检索

        使用简单的TF-IDF风格评分
        """
        results = {}

        # 分词
        query_terms = set(query.lower().split())
        if not query_terms:
            return results

        # 获取候选commits
        if candidate_hashes:
            commits = []
            for h in candidate_hashes:
                c = self.lw_index.get_commit_by_hash(h)
                if c:
                    commits.append(c)
        else:
            # 从全文索引搜索
            commits = self.lw_index.search_by_keyword(query, limit=top_k * 2)

        # 计算每个commit的得分
        for commit in commits:
            message_lower = commit.message.lower()
            message_terms = set(message_lower.split())

            # 计算重叠词
            overlap = query_terms & message_terms
            if not overlap:
                continue

            # 简单TF-IDF评分
            tf = len(overlap) / len(message_terms) if message_terms else 0
            idf = math.log(1 + 1 / (len(overlap) + 0.1))  # 简化IDF

            score = tf * idf * 100  # 归一化到0-100
            results[commit.hash] = score

        return results

    def _path_search(
        self,
        file_path: str,
        candidate_hashes: Optional[set] = None,
        top_k: int = 100,
    ) -> Dict[str, float]:
        """
        路径检索

        基于文件路径的精确匹配和前缀匹配
        """
        results = {}

        # 从索引中搜索
        commits = self.lw_index.search_by_path(file_path, limit=top_k * 2)

        # 过滤候选集
        if candidate_hashes:
            commits = [c for c in commits if c.hash in candidate_hashes]

        # 计算得分
        for commit in commits:
            # 计算路径匹配得分
            max_score = 0
            for changed_file in commit.changed_files:
                if file_path == changed_file:
                    # 精确匹配
                    max_score = 100
                    break
                elif changed_file.startswith(file_path) or file_path in changed_file:
                    # 前缀或包含匹配
                    match_ratio = len(file_path) / len(changed_file)
                    max_score = max(max_score, match_ratio * 80)

            if max_score > 0:
                results[commit.hash] = max_score

        return results

    def _rrf_fusion(
        self,
        keyword_results: Dict[str, float],
        path_results: Dict[str, float],
        vector_results: Optional[Dict[str, float]] = None,
        top_k: int = 10,
    ) -> List[Tuple[str, float]]:
        """
        RRF (Reciprocal Rank Fusion)

        公式: score = sum(1 / (k + rank))
        其中k是常数（默认60），rank是该结果在单个列表中的排名
        """
        # 收集所有出现的commit hash
        all_hashes = set(keyword_results.keys()) | set(path_results.keys())
        if vector_results:
            all_hashes |= set(vector_results.keys())

        # 计算每个hash在每个列表中的排名
        def get_rank(results: Dict[str, float], h: str) -> Optional[int]:
            if h not in results:
                return None
            # 按分数排序，确定排名
            sorted_items = sorted(results.items(), key=lambda x: -x[1])
            for i, (hash_val, _) in enumerate(sorted_items):
                if hash_val == h:
                    return i + 1  # 排名从1开始
            return None

        # 计算RRF分数
        rrf_scores = {}
        for h in all_hashes:
            score = 0.0

            k_rank = get_rank(keyword_results, h)
            if k_rank:
                score += self.keyword_weight * (1.0 / (self.rrf_k + k_rank))

            p_rank = get_rank(path_results, h)
            if p_rank:
                score += self.path_weight * (1.0 / (self.rrf_k + p_rank))

            if vector_results:
                v_rank = get_rank(vector_results, h)
                if v_rank:
                    score += self.vector_weight * (1.0 / (self.rrf_k + v_rank))

            rrf_scores[h] = score

        # 按分数排序，返回top_k
        sorted_results = sorted(rrf_scores.items(), key=lambda x: -x[1])
        return sorted_results[:top_k]

    def _weighted_fusion(
        self,
        keyword_results: Dict[str, float],
        path_results: Dict[str, float],
        vector_results: Optional[Dict[str, float]] = None,
        top_k: int = 10,
    ) -> List[Tuple[str, float]]:
        """
        加权融合

        简单地将各来源的分数按权重加权求和
        """
        all_hashes = set(keyword_results.keys()) | set(path_results.keys())
        if vector_results:
            all_hashes |= set(vector_results.keys())

        # 归一化各来源的分数到0-1范围
        def normalize(scores: Dict[str, float]) -> Dict[str, float]:
            if not scores:
                return {}
            max_score = max(scores.values())
            if max_score == 0:
                return {k: 0 for k in scores}
            return {k: v / max_score for k, v in scores.items()}

        norm_keyword = normalize(keyword_results)
        norm_path = normalize(path_results)
        norm_vector = normalize(vector_results) if vector_results else {}

        # 加权求和
        fused_scores = {}
        for h in all_hashes:
            score = 0.0
            if h in norm_keyword:
                score += self.keyword_weight * norm_keyword[h]
            if h in norm_path:
                score += self.path_weight * norm_path[h]
            if h in norm_vector:
                score += self.vector_weight * norm_vector[h]
            fused_scores[h] = score

        # 排序返回
        sorted_results = sorted(fused_scores.items(), key=lambda x: -x[1])
        return sorted_results[:top_k]

    def search(
        self,
        query: str,
        file_path: Optional[str] = None,
        top_k: int = 10,
    ) -> List[SearchResult]:
        """
        混合检索

        Args:
            query: 查询文本
            file_path: 可选的文件路径过滤
            top_k: 返回结果数量

        Returns:
            排序后的搜索结果列表
        """
        # 1. 关键词检索
        keyword_results = self._keyword_search(query, top_k=top_k * 3)

        # 2. 路径检索（如果提供了文件路径）
        path_results = {}
        candidate_hashes = None

        if file_path:
            path_results = self._path_search(file_path, top_k=top_k * 3)
            # 使用路径检索结果作为候选集，缩小关键词检索范围
            candidate_hashes = set(path_results.keys())
            if candidate_hashes:
                keyword_results = {
                    k: v
                    for k, v in keyword_results.items()
                    if k in candidate_hashes
                }

        # 3. 向量检索（TODO: 需要实现向量索引）
        vector_results = None

        # 4. 融合结果
        if self.use_rrf:
            fused = self._rrf_fusion(keyword_results, path_results, vector_results, top_k)
        else:
            fused = self._weighted_fusion(
                keyword_results, path_results, vector_results, top_k
            )

        # 5. 构建结果对象
        results = []
        for commit_hash, score in fused:
            commit = self.lw_index.get_commit_by_hash(commit_hash)
            if commit:
                k_score = keyword_results.get(commit_hash, 0)
                p_score = path_results.get(commit_hash, 0)
                v_score = vector_results.get(commit_hash, 0) if vector_results else 0

                results.append(
                    SearchResult(
                        commit=commit,
                        score=score,
                        keyword_score=k_score,
                        path_score=p_score,
                        vector_score=v_score,
                    )
                )

        return results
