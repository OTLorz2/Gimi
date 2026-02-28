"""Prompt builder for Gimi LLM interactions."""

from dataclasses import dataclass
from typing import List, Optional, Dict, Any

from gimi.context.diff_manager import DiffResult


@dataclass
class PromptResult:
    """Result of building a prompt."""
    system_message: str
    user_message: str
    context_tokens: int
    referenced_commits: List[str]

    def to_messages(self) -> List[Dict[str, str]]:
        """Convert to list of message dicts for LLM APIs."""
        return [
            {"role": "system", "content": self.system_message},
            {"role": "user", "content": self.user_message}
        ]


class PromptBuilder:
    """Builder for constructing prompts from diffs and queries."""

    SYSTEM_PROMPT = """You are Gimi, an expert programming assistant that helps developers understand code changes and provides insightful suggestions.

Your task is to analyze commit diffs and answer the user's question based on the provided context. Be specific, reference relevant code changes, and provide actionable suggestions.

Guidelines:
1. Analyze the commit diffs carefully before responding
2. Reference specific commits and file changes when relevant
3. Provide code examples when appropriate
4. Be concise but thorough
5. If the context doesn't contain enough information, say so clearly

The user will provide:
- Their question or requirement
- Relevant commit diffs as context"""

    def __init__(self, max_context_tokens: int = 4000):
        """
        Initialize prompt builder.

        Args:
            max_context_tokens: Maximum tokens for context (diffs)
        """
        self.max_context_tokens = max_context_tokens

    def build_prompt(
        self,
        query: str,
        diff_results: List[DiffResult],
        max_commits: int = 10
    ) -> PromptResult:
        """
        Build prompt from query and diffs.

        Args:
            query: User query
            diff_results: List of diff results to include
            max_commits: Maximum number of commits to include

        Returns:
            PromptResult with system/user messages
        """
        # Limit number of diffs
        diff_results = diff_results[:max_commits]

        # Build context from diffs
        context_parts = []
        referenced_commits = []
        total_tokens = 0

        for diff_result in diff_results:
            diff_text = diff_result.to_text()
            # Rough token estimation
            estimated_tokens = len(diff_text) // 4

            if total_tokens + estimated_tokens > self.max_context_tokens:
                # Skip this diff if it would exceed limit
                continue

            context_parts.append(diff_text)
            referenced_commits.append(diff_result.commit_hash)
            total_tokens += estimated_tokens

        # Build user message
        context = "\n\n".join([
            "=== Relevant Commit Diffs ===",
            "\n\n".join(context_parts),
            "=== End of Diffs ==="
        ])

        user_message = f"""{context}

User Question: {query}

Please analyze the above commit diffs and answer the user's question. Reference specific commits and code changes in your response."""

        return PromptResult(
            system_message=self.SYSTEM_PROMPT,
            user_message=user_message,
            context_tokens=total_tokens,
            referenced_commits=referenced_commits
        )

    def build_simple_prompt(
        self,
        query: str,
        commit_hashes: List[str]
    ) -> PromptResult:
        """
        Build a simple prompt without full diffs (for when diffs not available).

        Args:
            query: User query
            commit_hashes: List of referenced commit hashes

        Returns:
            PromptResult
        """
        user_message = f"""User Question: {query}

Referenced commits: {', '.join(commit_hashes[:10])}

Please answer based on your knowledge."""

        return PromptResult(
            system_message=self.SYSTEM_PROMPT,
            user_message=user_message,
            context_tokens=0,
            referenced_commits=commit_hashes[:10]
        )
