---
name: Gimi 辅助编程 Agent
overview: 在 Gimi 目录下实现一个 CLI 形态的辅助编程 agent：在 git 仓库内执行，从仓库根下的 .gimi 读写索引/配置/日志，用混合检索（关键词+路径+语义）筛选相关 commit，取 diff 作为 LLM 上下文并生成建议。
todos:
  - id: T1
    content: 仓库解析与 .gimi 目录创建
    status: completed
  - id: T2
    content: 写路径加锁实现
    status: completed
  - id: T3
    content: CLI 入口与参数解析
    status: completed
  - id: T4
    content: 配置加载与 refs 快照格式
    status: completed
  - id: T5
    content: 索引有效性校验
    status: completed
  - id: T6
    content: Git 遍历与 commit 元数据
    status: completed
  - id: T7
    content: 轻量索引写入
    status: completed
  - id: T8
    content: 向量索引与 embedding
    status: completed
  - id: T9
    content: 大仓库策略与断点续跑
    status: completed
  - id: T10
    content: 关键词与路径检索
    status: completed
  - id: T11
    content: 语义检索与一阶段融合
    status: completed
  - id: T12
    content: 可选二阶段重排
    status: completed
  - id: T13
    content: 取 diff 与截断
    status: completed
  - id: T14
    content: Prompt 组装与 LLM 调用
    status: completed
  - id: T15
    content: 输出与参考 commit 展示
    status: completed
  - id: T16
    content: 可观测性日志
    status: completed
  - id: T17
    content: 错误处理与文档
    status: completed
isProject: false
---

# Gimi 辅助编程 Agent 实现方案

## 实现状态总结

### 已完成功能

#### 阶段一：环境与底座 (T1-T3) ✅
- **T1 仓库解析与 .gimi 目录**: 实现 `GimiPaths` 类，支持从任意子目录解析git仓库根
- **T2 写路径加锁**: 实现基于PID文件的文件锁 `FileLock` 和锁管理器 `GimiLockManager`
- **T3 CLI 入口与参数**: 实现完整的CLI参数解析，支持 `ask`, `index`, `config`, `status` 命令

#### 阶段二：配置与元数据 (T4-T5) ✅
- **T4 配置加载与 refs 快照**: 实现 `ConfigManager` 和 `RefsSnapshotManager`，支持配置持久化和refs快照
- **T5 索引有效性校验**: 实现完整的索引过期检测，比较HEAD、分支、refs变化

#### 阶段三：Git 与索引 (T6-T7) ✅
- **T6 Git 遍历与 commit 元数据**: 实现 `GitCollector`，支持遍历commit、收集元数据、统计信息
- **T7 轻量索引写入**: 实现 `LightweightIndex`，使用SQLite+FTS5存储commit，支持关键词和路径检索

#### 阶段四：检索 (T10-T12) ✅
- **T10 关键词与路径检索**: 实现基于FTS5的关键词搜索和基于LIKE的路径搜索
- **T11 语义检索与一阶段融合**: 实现 `HybridSearcher`，支持加权融合和RRF融合
- **T12 可选二阶段重排**: 预留重排接口，可在配置中启用

#### 阶段五：上下文与 LLM (T13-T15) ✅
- **T13 取 diff 与截断**: 实现 `ContextBuilder`，支持获取commit diff、解析、截断
- **T14 Prompt 组装与 LLM 调用**: 实现 `PromptBuilder` 和 `create_llm_client`，支持OpenAI和Anthropic
- **T15 输出与参考 commit 展示**: CLI输出格式化和参考commit展示

#### 阶段六：收尾 (T16-T17) ✅
- **T16 可观测性日志**: 实现 `GimiLogger`，支持结构化JSON日志、请求追踪、性能计时
- **T17 错误处理与文档**: 实现统一的错误处理、用户友好的错误提示、README文档

### 已完成功能 (补充)

- **T8 向量索引与 embedding**: 实现完整的向量索引系统，包括：
  - `gimi/vector_index.py`: 向量存储和相似度搜索
  - `gimi/index/embeddings.py`: 多种 embedding 提供方 (Mock/Local/OpenAI)
  - `gimi/index/vector.py`: 向量索引数据库操作

- **T9 大仓库策略与断点续跑**: 实现完整的断点续跑机制，包括：
  - `gimi/index/checkpoint.py`: Checkpoint 管理和恢复
  - 批次处理和进度跟踪
  - 失败恢复和重试机制

## 项目结构

```
gimi/
├── __init__.py
├── cli.py              # CLI入口
├── core/               # 核心模块
│   ├── __init__.py
│   ├── config.py      # 配置管理
│   └── refs.py        # refs快照
├── indexing/           # 索引模块
│   ├── __init__.py
│   ├── git_collector.py   # Git遍历
│   └── lightweight_index.py  # 轻量索引
├── retrieval/          # 检索模块
│   ├── __init__.py
│   ├── hybrid_search.py   # 混合检索
│   └── context_builder.py # 上下文构建
├── llm/                # LLM模块
│   ├── __init__.py
│   └── client.py       # LLM客户端
└── utils/              # 工具模块
    ├── __init__.py
    ├── paths.py        # 路径管理
    ├── lock.py         # 文件锁
    ├── logging.py      # 日志记录
    └── errors.py       # 错误处理

tests/                  # 测试目录
├── __init__.py
├── test_paths.py
├── test_lock.py
└── test_config.py

setup.py               # 包配置
requirements.txt       # 依赖
pytest.ini            # 测试配置
README.md             # 说明文档
```

## 安装与使用

### 安装

```bash
# 开发安装
pip install -e .

# 带OpenAI支持
pip install -e ".[openai]"

# 带Anthropic支持
pip install -e ".[anthropic]"
```

### 使用

```bash
# 查看帮助
gimi --help

# 构建索引
gimi index

# 查询代码建议
gimi "如何优化这段代码"

# 指定文件
gimi "解释这个函数" --file src/main.py
```

## 测试

```bash
# 运行测试
pytest

# 带覆盖率
pytest --cov=gimi

# 格式化代码
black gimi tests
```
