"""
T8: 向量索引与 embedding

功能：
- 对每个 commit 用「message + 路径列表」生成 embedding
- 写入 `.gimi/vectors`
- 与轻量索引通过 commit hash 关联

简化实现：使用简单的向量存储（NumPy 数组），
实际生产环境可以替换为 FAISS、Annoy 或专业向量数据库。
"""

import json
import hashlib
import numpy as np
from pathlib import Path
from typing import List, Optional, Dict, Tuple, Any
from dataclasses import dataclass

from gimi.git_traversal import CommitMeta


# 使用简单的 embedding 维度
EMBEDDING_DIM = 384  # 与 all-MiniLM-L6-v2 等模型一致


@dataclass
class VectorEntry:
    """向量条目"""
    commit_hash: str
    vector: np.ndarray
    text: str           # 用于生成向量的原始文本

    def to_dict(self) -> Dict:
        """转换为字典（用于序列化）"""
        return {
            "commit_hash": self.commit_hash,
            "vector": self.vector.tobytes().hex(),
            "text": self.text,
        }

    @classmethod
    def from_dict(cls, data: Dict) -> "VectorEntry":
        """从字典创建"""
        vector_bytes = bytes.fromhex(data["vector"])
        vector = np.frombuffer(vector_bytes, dtype=np.float32)
        return cls(
            commit_hash=data["commit_hash"],
            vector=vector,
            text=data["text"],
        )


class SimpleEmbedding:
    """
    简化的 embedding 生成器

    实际生产环境应该使用：
    - sentence-transformers
    - OpenAI Embedding API
    - 其他 embedding 服务

    这里使用简单的哈希方案作为演示。
    """

    def __init__(self, dim: int = EMBEDDING_DIM):
        self.dim = dim

    def embed(self, text: str) -> np.ndarray:
        """
        生成文本的 embedding 向量

        注意：这是简化实现，仅用于演示。
        实际应该使用预训练的语言模型。
        """
        # 使用文本哈希生成确定性向量
        # 实际应用中应该替换为真实的 embedding 模型
        hash_obj = hashlib.sha256(text.encode())
        hash_bytes = hash_obj.digest()

        # 将哈希转换为浮点数向量
        vector = np.zeros(self.dim, dtype=np.float32)
        for i in range(self.dim):
            # 使用多个字节构造一个浮点数
            byte_idx = (i * 4) % len(hash_bytes)
            val = int.from_bytes(
                hash_bytes[byte_idx:byte_idx+4],
                byteorder='little',
                signed=True
            )
            # 归一化到 [-1, 1]
            vector[i] = val / (2**31)

        # L2 归一化
        norm = np.linalg.norm(vector)
        if norm > 0:
            vector = vector / norm

        return vector

    def embed_batch(self, texts: List[str]) -> np.ndarray:
        """批量生成 embedding"""
        vectors = [self.embed(text) for text in texts]
        return np.array(vectors)


class VectorIndex:
    """
    向量索引

    存储 commit 的向量表示，支持相似度搜索。
    """

    INDEX_FILENAME = "vectors.json"

    def __init__(
        self,
        gimi_path: Path,
        embedding: Optional[SimpleEmbedding] = None
    ):
        self.gimi_path = Path(gimi_path)
        self.vectors_dir = self.gimi_path / "vectors"
        self.vectors_dir.mkdir(parents=True, exist_ok=True)

        self.index_path = self.vectors_dir / self.INDEX_FILENAME
        self.embedding = embedding or SimpleEmbedding()

        # 内存中的索引
        self._entries: Dict[str, VectorEntry] = {}
        self._load_index()

    def _load_index(self) -> None:
        """加载索引文件"""
        if not self.index_path.exists():
            return

        try:
            data = json.loads(self.index_path.read_text(encoding="utf-8"))
            for entry_data in data.get("entries", []):
                try:
                    entry = VectorEntry.from_dict(entry_data)
                    self._entries[entry.commit_hash] = entry
                except Exception:
                    # 跳过损坏的条目
                    continue
        except Exception:
            # 加载失败时重置
            self._entries = {}

    def _save_index(self) -> None:
        """保存索引文件"""
        data = {
            "version": "0.1.0",
            "entry_count": len(self._entries),
            "entries": [entry.to_dict() for entry in self._entries.values()],
        }
        self.index_path.write_text(
            json.dumps(data, indent=2, ensure_ascii=False),
            encoding="utf-8"
        )

    def _prepare_text(self, commit: CommitMeta) -> str:
        """
        准备用于生成向量的文本

        组合 message 和文件路径信息
        """
        parts = [commit.message]

        # 添加文件路径信息
        if commit.changed_files:
            # 提取文件名和路径关键词
            file_parts = []
            for f in commit.changed_files[:20]:  # 限制数量
                # 提取文件名和扩展名
                path_parts = f.replace("/", " ").replace("\\", " ").split()
                file_parts.extend(path_parts)
            parts.extend(file_parts)

        # 添加作者信息
        if commit.author_name:
            parts.append(commit.author_name)

        return " ".join(parts)

    def add_commit(self, commit: CommitMeta) -> None:
        """
        添加单个 commit 到向量索引

        Args:
            commit: commit 元数据
        """
        text = self._prepare_text(commit)
        vector = self.embedding.embed(text)

        entry = VectorEntry(
            commit_hash=commit.hash,
            vector=vector,
            text=text,
        )

        self._entries[commit.hash] = entry

    def add_commits(self, commits: List[CommitMeta]) -> None:
        """
        批量添加 commit 到向量索引

        Args:
            commits: commit 元数据列表
        """
        for commit in commits:
            self.add_commit(commit)

    def save(self) -> None:
        """保存索引到磁盘"""
        self._save_index()

    def search(
        self,
        query: str,
        top_k: int = 10,
        filter_hashes: Optional[Set[str]] = None
    ) -> List[Tuple[str, float]]:
        """
        向量相似度搜索

        Args:
            query: 查询文本
            top_k: 返回结果数量
            filter_hashes: 可选的 commit hash 过滤集合

        Returns:
            List[Tuple[str, float]]: (commit_hash, similarity) 列表，按相似度降序
        """
        if not self._entries:
            return []

        # 生成查询向量
        query_vector = self.embedding.embed(query)

        # 计算相似度
        results = []
        for commit_hash, entry in self._entries.items():
            # 应用过滤
            if filter_hashes and commit_hash not in filter_hashes:
                continue

            # 计算余弦相似度（向量已归一化，点积即相似度）
            similarity = float(np.dot(query_vector, entry.vector))
            results.append((commit_hash, similarity))

        # 按相似度降序排序
        results.sort(key=lambda x: x[1], reverse=True)

        return results[:top_k]

    def get_entry_count(self) -> int:
        """获取索引中的条目数量"""
        return len(self._entries)


if __name__ == "__main__":
    import tempfile

    print("测试向量索引...")

    with tempfile.TemporaryDirectory() as tmpdir:
        gimi_path = Path(tmpdir) / ".gimi"
        gimi_path.mkdir(parents=True)

        # 创建向量索引
        vindex = VectorIndex(gimi_path)
        print(f"向量索引已创建")

        # 创建测试 commit
        test_commits = [
            CommitMeta(
                hash="abc123def456789012345678901234567890abcd",
                short_hash="abc123d",
                message="Add user authentication feature with OAuth2",
                author_name="张三",
                author_email="zhangsan@example.com",
                author_date=datetime.now(),
                committer_name="张三",
                committer_email="zhangsan@example.com",
                committer_date=datetime.now(),
                branches=["main"],
                parents=["parent123"],
                files_changed=["src/auth.py", "src/oauth.py", "tests/test_auth.py"],
                stats={"insertions": 150, "deletions": 20, "files_changed": 3},
            ),
            CommitMeta(
                hash="def789abc0123456789012345678901234567890",
                short_hash="def789a",
                message="Fix database connection timeout issue in production",
                author_name="李四",
                author_email="lisi@example.com",
                author_date=datetime.now(),
                committer_name="李四",
                committer_email="lisi@example.com",
                committer_date=datetime.now(),
                branches=["main"],
                parents=["parent456"],
                files_changed=["src/db.py", "config/database.yml"],
                stats={"insertions": 45, "deletions": 10, "files_changed": 2},
            ),
            CommitMeta(
                hash="xyz789abc0123456789012345678901234567890",
                short_hash="xyz789a",
                message="Implement user profile page with React components",
                author_name="王五",
                author_email="wangwu@example.com",
                author_date=datetime.now(),
                committer_name="王五",
                committer_email="wangwu@example.com",
                committer_date=datetime.now(),
                branches=["feature/profile"],
                parents=["parent789"],
                files_changed=["src/Profile.jsx", "src/Profile.css", "tests/Profile.test.jsx"],
                stats={"insertions": 300, "deletions": 50, "files_changed": 3},
            ),
        ]

        # 测试 1: 添加 commit 到向量索引
        print("\n测试 1: 添加 commit 到向量索引")
        vindex.add_commits(test_commits)
        vindex.save()
        print(f"  已添加 {len(test_commits)} 个 commit")
        print(f"  索引条目数: {vindex.get_entry_count()}")

        # 测试 2: 向量搜索
        print("\n测试 2: 向量搜索 'authentication login'")
        results = vindex.search("authentication login", top_k=3)
        print(f"  找到 {len(results)} 个相关 commit")
        for commit_hash, similarity in results:
            commit = test_commits[0] if commit_hash == test_commits[0].hash else None
            if not commit:
                for c in test_commits:
                    if c.hash == commit_hash:
                        commit = c
                        break
            if commit:
                print(f"    - {commit.short_hash} (相似度: {similarity:.4f}): {commit.message[:50]}...")

        # 测试 3: 搜索 'database'
        print("\n测试 3: 向量搜索 'database timeout'")
        results = vindex.search("database timeout", top_k=3)
        print(f"  找到 {len(results)} 个相关 commit")
        for commit_hash, similarity in results:
            for c in test_commits:
                if c.hash == commit_hash:
                    print(f"    - {c.short_hash} (相似度: {similarity:.4f}): {c.message[:50]}...")
                    break

        # 测试 4: 加载索引
        print("\n测试 4: 重新加载索引")
        vindex2 = VectorIndex(gimi_path)
        print(f"  加载后条目数: {vindex2.get_entry_count()}")

    print("\n所有测试完成!")
