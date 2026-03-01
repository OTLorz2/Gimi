"""
T3: CLI 入口与参数解析

功能：
- 解析子命令/位置参数（用户需求）、--file、--branch
- 校验必填项
- 将解析结果交给后续流程
"""

import sys
import argparse
from pathlib import Path
from typing import List, Optional
from dataclasses import dataclass

from gimi.repo import initialize_repo, RepoResolver
from gimi.engine import QueryEngine, QueryEngineError


@dataclass
class CliArgs:
    """解析后的 CLI 参数"""
    query: str                    # 用户需求/问题
    files: List[str]              # --file 指定的文件路径
    branch: Optional[str]         # --branch 指定的分支
    repo_root: Path               # 解析到的仓库根目录
    gimi_path: Path               # .gimi 目录路径
    verbose: bool                 # 是否输出详细信息


class GimiCli:
    """Gimi CLI 入口"""

    def __init__(self):
        self.parser = self._create_parser()

    def _create_parser(self) -> argparse.ArgumentParser:
        """创建参数解析器"""
        parser = argparse.ArgumentParser(
            prog="gimi",
            description="Gimi - 辅助编程 Agent，基于 git 历史提供代码建议",
            formatter_class=argparse.RawDescriptionHelpFormatter,
            epilog="""
示例:
  gimi "如何优化这个函数的性能？" --file src/utils.py
  gimi "解释这段代码的作用" --file src/main.py --branch develop
  gimi "最近有什么重要修改？"
            """
        )

        # 位置参数：用户需求
        parser.add_argument(
            "query",
            type=str,
            help="你的需求或问题（例如：如何优化这段代码？）"
        )

        # 可选参数
        parser.add_argument(
            "--file", "-f",
            type=str,
            action="append",
            dest="files",
            help="指定相关文件路径（可多次使用）"
        )

        parser.add_argument(
            "--branch", "-b",
            type=str,
            default=None,
            help="指定要检索的分支（默认为当前分支）"
        )

        parser.add_argument(
            "--verbose", "-v",
            action="store_true",
            help="输出详细日志信息"
        )

        parser.add_argument(
            "--version",
            action="version",
            version="%(prog)s 0.1.0"
        )

        return parser

    def parse_args(self, args: Optional[List[str]] = None) -> CliArgs:
        """
        解析命令行参数

        Args:
            args: 命令行参数列表，默认为 sys.argv[1:]

        Returns:
            CliArgs: 解析后的参数对象
        """
        parsed = self.parser.parse_args(args)

        # 解析仓库根目录并创建 .gimi 结构
        try:
            repo_root, gimi_path = initialize_repo()
        except RuntimeError as e:
            print(f"错误: {e}", file=sys.stderr)
            sys.exit(1)

        return CliArgs(
            query=parsed.query,
            files=parsed.files or [],
            branch=parsed.branch,
            repo_root=repo_root,
            gimi_path=gimi_path,
            verbose=parsed.verbose
        )

    def run(self, args: Optional[List[str]] = None) -> int:
        """
        运行 CLI

        Args:
            args: 命令行参数列表

        Returns:
            int: 退出码
        """
        cli_args = self.parse_args(args)

        if cli_args.verbose:
            print(f"仓库根目录: {cli_args.repo_root}")
            print(f".gimi 目录: {cli_args.gimi_path}")
            print(f"查询: {cli_args.query}")
            print(f"文件: {cli_args.files}")
            print(f"分支: {cli_args.branch}")

        # Initialize query engine and process query
        try:
            engine = QueryEngine(
                repo_root=cli_args.repo_root,
                gimi_dir=cli_args.gimi_path,
                progress_callback=lambda msg: print(f"  {msg}") if cli_args.verbose else None
            )

            # Validate index
            status = engine.validate()
            if not status.is_valid:
                print(f"\n错误: {status.message}", file=sys.stderr)
                print("请先运行 'gimi index' 构建索引。", file=sys.stderr)
                return 1

            # Process query
            print(f"\n处理查询: '{cli_args.query}'\n")

            # Use first file if provided
            file_path = cli_args.files[0] if cli_args.files else None

            result = engine.query(cli_args.query, file_path=file_path)

            # Output result
            print("=" * 60)
            print("回答:")
            print("=" * 60)
            print(result.answer)
            print("=" * 60)

            if cli_args.verbose:
                print(f"\n参考 commits: {', '.join(result.referenced_commits[:5])}")
                print(f"上下文 tokens: {result.context_tokens}")
                print(f"响应时间: {result.latency_ms:.0f}ms")

            return 0

        except QueryEngineError as e:
            print(f"\n查询错误: {e}", file=sys.stderr)
            return 1
        except Exception as e:
            print(f"\n意外错误: {e}", file=sys.stderr)
            if cli_args.verbose:
                import traceback
                traceback.print_exc()
            return 1


def main():
    """CLI 入口点"""
    cli = GimiCli()
    sys.exit(cli.run())


if __name__ == "__main__":
    main()
