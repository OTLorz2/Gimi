"""
T10, T11, T12: 检索与融合

T10: 关键词与路径检索
- 在轻量索引上实现关键词匹配和路径匹配
- 输出候选 commit 列表

T11: 语义检索与一阶段融合
- 对候选集用向量相似度排序，取 Top-K
- 实现融合策略（加权或 RRF）

T12: 可选二阶段重排
- 对 Top-K 用 cross-encoder 或 LLM 做相关性打分
- 通过配置开关启用/关闭
"""

import numpy as np
from pathlib import Path
from typing import List, Optional, Dict, Set, Tuple, Callable
from dataclasses import dataclass
from enum import Enum

from gimi.light_index import LightIndex
from gimi.vector_index import VectorIndex
from gimi.config import RetrievalConfig


class RetrievalStage(Enum):
    """检索阶段"""
    KEYWORD = "keyword"      # 关键词检索
    PATH = "path"           # 路径检索
    SEMANTIC = "semantic"   # 语义检索
    FUSION = "fusion"       # 融合结果
    RERANK = "rerank"       # 重排结果


@dataclass
class RetrievedCommit:
    """检索到的 commit"""
    commit_hash: str
    score: float                          # 最终分数
    stage_scores: Dict[str, float] = None  # 各阶段分数
    retrieval_stage: str = ""              # 来源阶段


class HybridRetriever:
    """
    混合检索器

    实现关键词 + 路径 + 语义的混合检索策略。
    """

    def __init__(
        self,
        light_index: LightIndex,
        vector_index: VectorIndex,
        config: Optional[RetrievalConfig] = None,
    ):
        self.light_index = light_index
        self.vector_index = vector_index
        self.config = config or RetrievalConfig()

    def keyword_search(
        self,
        keywords: List[str],
        branch: Optional[str] = None,
        limit: int = 100
    ) -> Dict[str, float]:
        """
        T10: 关键词检索

        在轻量索引中搜索包含关键词的 commit。

        Args:
            keywords: 关键词列表
            branch: 分支过滤
            limit: 最大返回数量

        Returns:
            Dict[str, float]: commit_hash -> 相关性分数
        """
        if not keywords:
            return {}

        results = self.light_index.search_by_message(
            keywords=keywords,
            branch=branch,
            limit=limit
        )

        # 计算简单的相关性分数（关键词出现次数）
        scores = {}
        for commit in results:
            score = 0
            message_lower = commit.message.lower()
            for kw in keywords:
                score += message_lower.count(kw.lower())
            scores[commit.hash] = min(score / len(keywords), 1.0)

        return scores

    def path_search(
        self,
        file_path: str,
        branch: Optional[str] = None,
        limit: int = 100
    ) -> Dict[str, float]:
        """
        T10: 路径检索

        搜索涉及特定文件的 commit。

        Args:
            file_path: 文件路径（支持前缀匹配）
            branch: 分支过滤
            limit: 最大返回数量

        Returns:
            Dict[str, float]: commit_hash -> 相关性分数
        """
        results = self.light_index.search_by_path(
            file_path=file_path,
            branch=branch,
            limit=limit
        )

        # 路径匹配分数（简单实现）
        scores = {}
        for commit in results:
            # 完全匹配给高分，前缀匹配给较低分
            exact_match = any(f == file_path for f in commit.files_changed)
            scores[commit.hash] = 1.0 if exact_match else 0.7

        return scores

    def semantic_search(
        self,
        query: str,
        candidate_hashes: Optional[Set[str]] = None,
        top_k: int = 25
    ) -> Dict[str, float]:
        """
        T11: 语义检索

        使用向量相似度搜索相关 commit。

        Args:
            query: 查询文本
            candidate_hashes: 可选的候选 commit hash 集合（用于一阶段过滤后）
            top_k: 返回结果数量

        Returns:
            Dict[str, float]: commit_hash -> 相似度分数
        """
        results = self.vector_index.search(
            query=query,
            top_k=top_k,
            filter_hashes=candidate_hashes,
        )

        return {commit_hash: float(score) for commit_hash, score in results}

    def reciprocal_rank_fusion(
        self,
        keyword_results: Dict[str, float],
        path_results: Dict[str, float],
        semantic_results: Dict[str, float],
        k: int = 60
    ) -> Dict[str, float]:
        """
        使用 RRF（Reciprocal Rank Fusion）融合多路召回结果

        Args:
            keyword_results: 关键词检索结果
            path_results: 路径检索结果
            semantic_results: 语义检索结果
            k: RRF 参数，默认 60

        Returns:
            Dict[str, float]: commit_hash -> 融合后的分数
        """
        # 收集所有候选 commit
        all_commits = set()
        all_commits.update(keyword_results.keys())
        all_commits.update(path_results.keys())
        all_commits.update(semantic_results.keys())

        # 计算每个 commit 的 RRF 分数
        fused_scores = {}
        for commit_hash in all_commits:
            score = 0.0

            # 关键词结果中的排名
            if commit_hash in keyword_results:
                # 计算排名（按分数降序）
                sorted_results = sorted(
                    keyword_results.items(),
                    key=lambda x: x[1],
                    reverse=True
                )
                rank = next(i for i, (h, _) in enumerate(sorted_results) if h == commit_hash)
                score += 1.0 / (k + rank + 1)

            # 路径结果中的排名
            if commit_hash in path_results:
                sorted_results = sorted(
                    path_results.items(),
                    key=lambda x: x[1],
                    reverse=True
                )
                rank = next(i for i, (h, _) in enumerate(sorted_results) if h == commit_hash)
                score += 1.0 / (k + rank + 1)

            # 语义结果中的排名
            if commit_hash in semantic_results:
                sorted_results = sorted(
                    semantic_results.items(),
                    key=lambda x: x[1],
                    reverse=True
                )
                rank = next(i for i, (h, _) in enumerate(sorted_results) if h == commit_hash)
                score += 1.0 / (k + rank + 1)

            fused_scores[commit_hash] = score

        return fused_scores

    def retrieve(
        self,
        query: str,
        keywords: Optional[List[str]] = None,
        file_paths: Optional[List[str]] = None,
        branch: Optional[str] = None,
        top_k: Optional[int] = None,
        enable_rerank: Optional[bool] = None,
    ) -> List[RetrievedCommit]:
        """
        执行完整的混合检索流程

        T10 + T11: 关键词、路径检索 + 语义检索 + 融合
        T12: 可选重排

        Args:
            query: 用户查询
            keywords: 额外的关键词
            file_paths: 文件路径过滤
            branch: 分支过滤
            top_k: 返回结果数量，默认使用配置
            enable_rerank: 是否启用重排，默认使用配置

        Returns:
            List[RetrievedCommit]: 检索结果
        """
        top_k = top_k or self.config.top_k
        enable_rerank = enable_rerank if enable_rerank is not None else self.config.enable_rerank

        # T10: 关键词检索
        keyword_results = {}
        all_keywords = []
        if query:
            all_keywords.extend(query.split())
        if keywords:
            all_keywords.extend(keywords)

        if all_keywords:
            keyword_results = self.keyword_search(
                keywords=all_keywords,
                branch=branch,
                limit=self.config.candidate_factor * top_k
            )

        # T10: 路径检索
        path_results = {}
        if file_paths:
            for fp in file_paths:
                results = self.path_search(
                    file_path=fp,
                    branch=branch,
                    limit=self.config.candidate_factor * top_k
                )
                # 合并结果
                for commit_hash, score in results.items():
                    if commit_hash in path_results:
                        path_results[commit_hash] = max(path_results[commit_hash], score)
                    else:
                        path_results[commit_hash] = score

        # T11: 语义检索（在候选集上）
        candidate_hashes = None
        if keyword_results or path_results:
            # 如果关键词或路径有结果，作为候选集
            candidate_hashes = set()
            candidate_hashes.update(keyword_results.keys())
            candidate_hashes.update(path_results.keys())

        semantic_results = self.semantic_search(
            query=query,
            candidate_hashes=candidate_hashes,
            top_k=top_k * 2 if candidate_hashes else top_k
        )

        # T11: 融合结果（使用 RRF）
        fused_scores = self.reciprocal_rank_fusion(
            keyword_results=keyword_results,
            path_results=path_results,
            semantic_results=semantic_results,
        )

        # 构建初步结果
        results = []
        for commit_hash, score in sorted(
            fused_scores.items(),
            key=lambda x: x[1],
            reverse=True
        )[:top_k * 2]:
            results.append(RetrievedCommit(
                commit_hash=commit_hash,
                score=score,
                stage_scores={
                    "fusion": score,
                    "keyword": keyword_results.get(commit_hash, 0),
                    "path": path_results.get(commit_hash, 0),
                    "semantic": semantic_results.get(commit_hash, 0),
                },
                retrieval_stage="fusion",
            ))

        # T12: 可选重排
        if enable_rerank and results:
            results = self._rerank(query, results)

        # 截取最终 top_k
        final_results = results[:top_k]

        return final_results

    def _rerank(
        self,
        query: str,
        candidates: List[RetrievedCommit]
    ) -> List[RetrievedCommit]:
        """
        T12: 二阶段重排

        使用更精确的模型对候选结果重新排序。
        这里使用简化的启发式规则，实际应该使用：
        - Cross-encoder 模型
        - LLM 打分
        """
        reranked = []

        for commit in candidates:
            score = commit.score

            # 从轻量索引获取完整信息
            meta = self.light_index.get_commit(commit.commit_hash)
            if meta:
                # 启发式 1: 查询词在 message 中的完全匹配
                query_terms = set(query.lower().split())
                message_terms = set(meta.message.lower().split())
                overlap = query_terms & message_terms
                if overlap:
                    score += 0.1 * len(overlap) / len(query_terms)

                # 启发式 2: 最近时间的 commit 略微加分
                from datetime import datetime, timedelta
                if meta.author_date:
                    age = datetime.now() - meta.author_date
                    if age < timedelta(days=7):
                        score += 0.05
                    elif age < timedelta(days=30):
                        score += 0.02

            reranked.append(RetrievedCommit(
                commit_hash=commit.commit_hash,
                score=score,
                stage_scores=commit.stage_scores,
                retrieval_stage="rerank",
            ))

        # 按新分数排序
        reranked.sort(key=lambda x: x.score, reverse=True)

        return reranked


if __name__ == "__main__":
    import tempfile

    print("测试混合检索...")

    with tempfile.TemporaryDirectory() as tmpdir:
        gimi_path = Path(tmpdir) / ".gimi"
        gimi_path.mkdir(parents=True)

        # 由于需要真实 git 仓库，这里仅测试配置和接口
        print("混合检索器配置测试完成")

        # 测试 RRF 融合
        print("\n测试 RRF 融合...")

        retriever = HybridRetriever(
            light_index=None,  # 不实际使用
            vector_index=None,
            config=RetrievalConfig(),
        )

        keyword_results = {
            "hash1": 0.9,
            "hash2": 0.8,
            "hash3": 0.7,
        }

        path_results = {
            "hash2": 1.0,
            "hash4": 0.9,
        }

        semantic_results = {
            "hash1": 0.95,
            "hash3": 0.85,
            "hash5": 0.75,
        }

        fused = retriever.reciprocal_rank_fusion(
            keyword_results,
            path_results,
            semantic_results,
        )

        print("融合结果:")
        for hash_val, score in sorted(fused.items(), key=lambda x: x[1], reverse=True):
            print(f"  {hash_val}: {score:.4f}")

    print("\n所有测试完成!")
