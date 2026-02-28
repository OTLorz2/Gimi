"""
Gimi 主入口模块

整合所有组件，提供完整的 CLI 体验。
"""

import sys
from pathlib import Path
from typing import Optional, List

from gimi.cli import GimiCli, CliArgs, main as cli_main
from gimi.repo import initialize_repo, RepoResolver
from gimi.lock import gimi_lock
from gimi.config import (
    GimiConfig, ModelConfig, RetrievalConfig,
    LargeRepoConfig, TruncateConfig,
    get_config_path, get_refs_snapshot_path, capture_refs_snapshot,
)
from gimi.index_status import check_index_health, IndexStatus
from gimi.git_traversal import GitTraversal
from gimi.light_index import LightIndex
from gimi.vector_index import VectorIndex
from gimi.indexer import IncrementalIndexer
from gimi.retrieval import HybridRetriever, RetrievedCommit
from gimi.context_builder import DiffBuilder, format_diff_for_llm
from gimi.llm import (
    LLMClient, PromptBuilder, SuggestionPresenter,
    LLMResponse, SuggestionOutput,
)
from gimi.observability import ObservabilityLogger, RequestLog
from gimi.error_handler import (
    ErrorHandler, GimiError, ErrorCode, safe_execute,
)


class GimiApplication:
    """
    Gimi 应用程序主类

    整合所有组件，提供完整的端到端流程。
    """

    def __init__(self):
        self.cli = GimiCli()
        self.error_handler = ErrorHandler(verbose=False)
        self.logger: Optional[ObservabilityLogger] = None

        # 运行时状态
        self.args: Optional[CliArgs] = None
        self.config: Optional[GimiConfig] = None
        self.repo_root: Optional[Path] = None
        self.gimi_path: Optional[Path] = None

    def run(self, args: Optional[List[str]] = None) -> int:
        """
        运行应用程序

        Args:
            args: 命令行参数

        Returns:
            int: 退出码
        """
        try:
            return self._run_impl(args)
        except Exception as e:
            self.error_handler.handle(e, exit_on_error=False)
            return 1

    def _run_impl(self, args: Optional[List[str]] = None) -> int:
        """实际运行实现"""
        # 1. 解析 CLI 参数
        self.args = self.cli.parse_args(args)

        # 2. 初始化路径和配置
        self.repo_root = self.args.repo_root
        self.gimi_path = self.args.gimi_path

        # 3. 初始化日志记录器
        self.logger = ObservabilityLogger(self.gimi_path)
        request_id = self.logger.start_request(
            repo_root=str(self.repo_root),
            query=self.args.query,
            keywords=None,  # 可以从查询中提取
            file_paths=self.args.files,
            branch=self.args.branch or "",
        )

        if self.args.verbose:
            print(f"请求 ID: {request_id}")
            print(f"仓库根目录: {self.repo_root}")
            print(f".gimi 目录: {self.gimi_path}")

        # 4. 加载配置
        config_path = get_config_path(self.gimi_path)
        self.config = GimiConfig.load(config_path)

        if self.args.verbose:
            print(f"配置已加载: {config_path}")

        # 5. 检查索引健康状态
        if self.args.verbose:
            print("\n检查索引状态...")

        from gimi.index_status import check_index_health
        health = check_index_health(self.gimi_path)

        self.logger.log_index_status(
            reused=health.status.name == "VALID",
            stale=health.status.name == "STALE",
        )

        if self.args.verbose:
            print(f"  状态: {health.status.name}")
            print(f"  消息: {health.message}")

        # 如果索引无效或过期，提示用户
        if health.status.name in ["MISSING", "CORRUPTED", "STALE"]:
            print(f"\n注意: {health.message}")
            print("建议运行 'gimi index --rebuild' 重建索引。")
            # 继续执行，但检索结果可能不理想

        # 6. 初始化检索组件
        if self.args.verbose:
            print("\n初始化检索组件...")

        light_index = LightIndex(self.gimi_path)
        vector_index = VectorIndex(self.gimi_path)

        retriever = HybridRetriever(
            light_index=light_index,
            vector_index=vector_index,
            config=self.config.retrieval,
        )

        if self.args.verbose:
            print(f"  轻量索引: {light_index.get_commit_count()} commits")
            print(f"  向量索引: {vector_index.get_entry_count()} entries")

        # 7. 执行检索
        if self.args.verbose:
            print(f"\n执行检索: '{self.args.query}'")

        # 从查询中提取关键词
        keywords = self.args.query.split()

        results = retriever.retrieve(
            query=self.args.query,
            keywords=keywords,
            file_paths=self.args.files if self.args.files else None,
            branch=self.args.branch,
            top_k=self.config.retrieval.top_k,
            enable_rerank=self.config.retrieval.enable_rerank,
        )

        self.logger.log_retrieval_result(
            candidate_count=len(results) * 3,  # 估算
            top_k=len(results),
            stage="rerank" if self.config.retrieval.enable_rerank else "fusion",
        )

        if self.args.verbose:
            print(f"  检索到 {len(results)} 个结果")

        if not results:
            print("\n未找到匹配的 commit。请尝试修改查询条件。")
            return 0

        # 8. 构建上下文（获取 diff）
        if self.args.verbose:
            print("\n构建上下文...")

        diff_builder = DiffBuilder(
            repo_root=self.repo_root,
            config=self.config.truncate,
        )

        commit_diffs = []
        total_tokens = 0
        max_tokens = self.config.truncate.max_total_tokens

        for result in results:
            diff = diff_builder.build_commit_diff(result.commit_hash)
            if diff:
                # 检查 token 限制
                if total_tokens + diff.estimated_tokens > max_tokens:
                    if self.args.verbose:
                        print(f"  达到 token 限制，停止添加更多 commits")
                    break

                commit_diffs.append(diff)
                total_tokens += diff.estimated_tokens

        self.logger.log_context_info(
            commits=len(commit_diffs),
            files=sum(len(d.files) for d in commit_diffs),
            tokens=total_tokens,
            truncated=len(commit_diffs) < len(results),
        )

        if self.args.verbose:
            print(f"  包含 {len(commit_diffs)} 个 commits")
            print(f"  总 token 数: {total_tokens}")

        # 9. 调用 LLM
        if self.args.verbose:
            print("\n调用 LLM...")

        prompt, used_commits = PromptBuilder.build_prompt(
            query=self.args.query,
            commit_diffs=commit_diffs,
            max_length=8000,
        )

        llm_client = LLMClient(self.config.model)
        response = llm_client.complete(prompt)

        self.logger.log_llm_call(
            provider=self.config.model.provider,
            model=self.config.model.model,
            latency_ms=response.latency_ms,
            prompt_tokens=response.usage.get("prompt_tokens", 0),
            completion_tokens=response.usage.get("completion_tokens", 0),
        )

        self.logger.log_response(
            referenced_commits=response.referenced_commits,
            response_length=len(response.content),
        )

        if self.args.verbose:
            print(f"  延迟: {response.latency_ms:.2f} ms")
            print(f"  Token 使用: {response.usage}")

        # 10. 输出结果
        print("\n" + "=" * 80)

        # 获取被引用的 commit 信息
        referenced_commits_info = []
        for commit_hash in response.referenced_commits:
            meta = light_index.get_commit(commit_hash)
            if meta:
                referenced_commits_info.append({
                    "hash": meta.short_hash,
                    "message": meta.message,
                })
            else:
                referenced_commits_info.append({
                    "hash": commit_hash[:7],
                    "message": "Unknown commit",
                })

        # 格式化输出
        output = SuggestionPresenter.format_output(
            query=self.args.query,
            response=response,
            referenced_commits_info=referenced_commits_info,
        )

        # 打印输出
        SuggestionPresenter.print_output(
            output=output,
            verbose=self.args.verbose,
        )

        # 结束日志记录
        self.logger.end_request()

        return 0


def main():
    """CLI 入口点"""
    app = GimiApplication()
    sys.exit(app.run())


if __name__ == "__main__":
    main()
