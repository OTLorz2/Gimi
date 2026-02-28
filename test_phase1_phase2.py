"""
Test script for Phase 1 and Phase 2 implementation.

This script tests:
- T1: Repository parsing and .gimi directory creation
- T2: Write path locking
- T3: CLI entry and argument parsing
- T4: Configuration loading and refs snapshot
- T5: Index validity checking
"""

import os
import subprocess
import sys
import tempfile
from pathlib import Path

# Ensure we're testing the local gimi package
sys.path.insert(0, str(Path(__file__).parent))

def run_test(name, func):
    """Run a test and report results."""
    print(f"\n{'='*60}")
    print(f"Test: {name}")
    print('='*60)
    try:
        func()
        print(f"✓ PASSED: {name}")
        return True
    except AssertionError as e:
        print(f"✗ FAILED: {name}")
        print(f"  Error: {e}")
        return False
    except Exception as e:
        print(f"✗ ERROR: {name}")
        print(f"  Exception: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_t1_repo_parsing():
    """Test T1: Repository parsing and .gimi directory creation."""
    from gimi.repo import find_repo_root, setup_gimi, GimiPaths, NotAGitRepoError

    # Test 1: Should raise NotAGitRepoError outside of git repo
    original_dir = os.getcwd()
    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            os.chdir(tmpdir)
            try:
                find_repo_root()
                assert False, "Should have raised NotAGitRepoError"
            except NotAGitRepoError:
                pass  # Expected
    finally:
        os.chdir(original_dir)

    # Test 2: Should find repo root inside git repo
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create git repo
        repo_dir = Path(tmpdir) / "test_repo"
        repo_dir.mkdir()
        subprocess.run(["git", "init"], cwd=repo_dir, check=True, capture_output=True)
        subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=repo_dir, check=True, capture_output=True)
        subprocess.run(["git", "config", "user.name", "Test"], cwd=repo_dir, check=True, capture_output=True)

        # Create initial commit
        (repo_dir / "test.txt").write_text("hello")
        subprocess.run(["git", "add", "."], cwd=repo_dir, check=True, capture_output=True)
        subprocess.run(["git", "commit", "-m", "initial"], cwd=repo_dir, check=True, capture_output=True)

        # Test finding repo root from root
        found_root = find_repo_root(repo_dir)
        assert found_root == repo_dir.resolve(), f"Expected {repo_dir}, got {found_root}"

        # Test finding repo root from subdirectory
        subdir = repo_dir / "subdir" / "nested"
        subdir.mkdir(parents=True)
        found_root = find_repo_root(subdir)
        assert found_root == repo_dir.resolve(), f"Expected {repo_dir}, got {found_root}"

        # Test setup_gimi creates .gimi directory
        gimi_paths = setup_gimi(repo_dir)
        assert gimi_paths.exists(), ".gimi directory should exist"
        assert gimi_paths.index_dir.exists(), "index directory should exist"
        assert gimi_paths.vectors_dir.exists(), "vectors directory should exist"
        assert gimi_paths.cache_dir.exists(), "cache directory should exist"
        assert gimi_paths.logs_dir.exists(), "logs directory should exist"

        print(f"  Repository root: {found_root}")
        print(f"  .gimi directory: {gimi_paths.gimi_dir}")
        print(f"  Subdirectories created: index, vectors, cache, logs")


def test_t2_locking():
    """Test T2: Write path locking."""
    from gimi.lock import FileLock, LockHeldByOtherProcess
    import time
    import threading

    with tempfile.TemporaryDirectory() as tmpdir:
        lock_path = Path(tmpdir) / "test.lock"

        # Test 1: Basic lock acquire and release
        lock = FileLock(lock_path)
        assert lock.acquire()
        assert lock._owned
        lock.release()
        assert not lock._owned
        print("  ✓ Basic lock acquire/release works")

        # Test 2: Context manager
        with FileLock(lock_path):
            pass
        print("  ✓ Context manager works")

        # Test 3: Concurrent access protection
        results = []

        def try_lock():
            l = FileLock(lock_path)
            try:
                l.acquire()
                results.append('acquired')
                time.sleep(0.1)
                l.release()
            except LockHeldByOtherProcess:
                results.append('blocked')

        # First thread acquires lock
        t1 = threading.Thread(target=try_lock)
        t1.start()
        time.sleep(0.05)

        # Second thread tries (should fail immediately)
        t2 = threading.Thread(target=try_lock)
        t2.start()

        t1.join()
        t2.join()

        assert 'acquired' in results
        assert 'blocked' in results
        print("  ✓ Concurrent access protection works")


def test_t3_cli():
    """Test T3: CLI entry and argument parsing."""
    from gimi.cli import GimiCLI, main
    from gimi.repo import NotAGitRepoError

    cli = GimiCLI()

    # Test 1: Help message
    try:
        cli.parse_args(['--help'])
        assert False, "Should have exited"
    except SystemExit as e:
        assert e.code == 0  # Help exits cleanly
    print("  ✓ Help parsing works")

    # Test 2: Subcommand parsing
    args = cli.parse_args(['index', '--full'])
    assert args.command == 'index'
    assert args.full is True
    print("  ✓ Index subcommand parsing works")

    args = cli.parse_args(['search', 'test query', '--top-k', '20'])
    assert args.command == 'search'
    assert args.query == 'test query'
    assert args.top_k == 20
    print("  ✓ Search subcommand parsing works")

    args = cli.parse_args(['ask', 'how does this work?', '--file', 'test.py'])
    assert args.command == 'ask'
    assert args.question == 'how does this work?'
    assert args.files == ['test.py']
    print("  ✓ Ask subcommand parsing works")

    # Test 3: CLI execution (outside git repo should fail gracefully)
    with tempfile.TemporaryDirectory() as tmpdir:
        os.chdir(tmpdir)
        exit_code = cli.run(['--help'])
        # Help should work even outside git repo
        assert exit_code == 0



def test_t4_t5_config_and_validation():
    """Test T4 and T5: Configuration and index validation."""
    from gimi.config import GimiConfig, RefsSnapshot, get_current_refs, setup_gimi
    from gimi.validation import (
        validate_index, IndexStatus, mark_index_fresh, load_stored_refs
    )

    with tempfile.TemporaryDirectory() as tmpdir:
        # Setup git repo
        repo_dir = Path(tmpdir) / "test_repo"
        repo_dir.mkdir()
        subprocess.run(["git", "init"], cwd=repo_dir, check=True, capture_output=True)
        subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=repo_dir, check=True, capture_output=True)
        subprocess.run(["git", "config", "user.name", "Test"], cwd=repo_dir, check=True, capture_output=True)

        # Initial commit
        (repo_dir / "test.txt").write_text("hello")
        subprocess.run(["git", "add", "."], cwd=repo_dir, check=True, capture_output=True)
        subprocess.run(["git", "commit", "-m", "initial"], cwd=repo_dir, check=True, capture_output=True)

        # Setup gimi
        repo_root, gimi_paths = setup_gimi(repo_dir)

        # Test 1: Initial state - no index
        result = validate_index(gimi_paths, repo_root)
        assert result.status == IndexStatus.NOT_FOUND
        print(f"  ✓ Initial state: {result.message}")

        # Test 2: Create config (T4)
        config = GimiConfig.create_default(gimi_paths.config)
        assert gimi_paths.config.exists()
        print(f"  ✓ Config created at: {gimi_paths.config}")

        # Load and verify config
        loaded_config = GimiConfig.load(gimi_paths.config)
        assert loaded_config.llm_model == config.llm_model
        print(f"  ✓ Config load/save works")

        # Test 3: Mark index as fresh (simulating successful index)
        mark_index_fresh(gimi_paths, repo_root)
        assert (gimi_paths.gimi_dir / 'refs_snapshot.json').exists()
        print(f"  ✓ Refs snapshot created")

        # Test 4: Now validation should show VALID
        result = validate_index(gimi_paths, repo_root)
        assert result.status == IndexStatus.VALID
        print(f"  ✓ Index validation: {result.message}")

        # Test 5: Make a change and verify update needed
        (repo_dir / "test2.txt").write_text("world")
        subprocess.run(["git", "add", "."], cwd=repo_dir, check=True, capture_output=True)
        subprocess.run(["git", "commit", "-m", "second"], cwd=repo_dir, check=True, capture_output=True)

        result = validate_index(gimi_paths, repo_root)
        # Should need incremental update since we have new commits
        assert result.status == IndexStatus.NEEDS_INCREMENTAL
        print(f"  ✓ Change detection: {result.message}")

        print("\n  All T4/T5 tests passed!")


def main():
    """Run all tests."""
    print("\n" + "="*60)
    print("Gimi Phase 1 & 2 Implementation Tests")
    print("="*60)

    original_dir = os.getcwd()

    tests = [
        ("T1: Repository Parsing", test_t1_repo_parsing),
        ("T2: Write Path Locking", test_t2_locking),
        ("T3: CLI Entry", test_t3_cli),
        ("T4/T5: Config and Validation", test_t4_t5_config_and_validation),
    ]

    results = []
    for name, test_func in tests:
        success = run_test(name, test_func)
        results.append((name, success))

    # Summary
    print("\n" + "="*60)
    print("Test Summary")
    print("="*60)
    passed = sum(1 for _, success in results if success)
    total = len(results)
    for name, success in results:
        status = "✓ PASSED" if success else "✗ FAILED"
        print(f"  {status}: {name}")
    print(f"\nTotal: {passed}/{total} tests passed")

    os.chdir(original_dir)
    return 0 if passed == total else 1


if __name__ == '__main__':
    sys.exit(main())
