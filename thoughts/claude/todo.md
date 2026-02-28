# Gimi Agent Implementation Todo

## Phase 1: Environment and Foundation - COMPLETE
- [x] T1: Repository parsing and .gimi directory creation
- [x] T2: Write path locking implementation
- [x] T3: CLI entry and argument parsing

## Phase 2: Configuration and Metadata - COMPLETE
- [x] T4: Configuration loading and refs snapshot
- [x] T5: Index validity verification

## Phase 3: Git and Index - IN PROGRESS
- [x] T6: Git traversal and commit metadata
- [x] T7: Lightweight index writing
- [ ] T8: Vector index and embedding
- [ ] T9: Large repository strategy and checkpoint

## Phase 4: Retrieval - PENDING
- [ ] T10: Keyword and path retrieval
- [ ] T11: Semantic retrieval and fusion
- [ ] T12: Optional two-stage reranking

## Phase 5: Context and LLM - PENDING
- [ ] T13: Get diff and truncation
- [ ] T14: Prompt assembly and LLM call
- [ ] T15: Output and reference commit display

## Phase 6: Finalization - PENDING
- [ ] T16: Observations logs
- [ ] T17: Error handling and documentation

## Testing - IN PROGRESS
- [x] Unit tests for repo module
- [ ] Unit tests for lock module
- [ ] Unit tests for config module
- [ ] Unit tests for git module
- [ ] Unit tests for index module
- [ ] End-to-end tests
