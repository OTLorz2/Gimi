"""
文件锁实现 - 用于.gimi目录的并发控制
实现基于PID文件的互斥锁，防止多个gimi进程同时写入索引
"""

import os
import time
import atexit
from pathlib import Path
from typing import Optional


class FileLockError(Exception):
    """文件锁相关错误"""
    pass


class FileLock:
    """
    基于PID文件的进程级互斥锁

    使用场景:
    - 防止多个gimi进程同时写入.gimi/index或.gimi/vectors
    - 支持阻塞等待和非阻塞模式

    锁文件格式:
    - 第一行: 持有锁的进程PID
    - 第二行: 锁获取时间戳(ISO格式)
    """

    DEFAULT_TIMEOUT = 30  # 默认超时秒数
    LOCK_POLL_INTERVAL = 0.1  # 轮询间隔秒数

    def __init__(self, lock_file: Path, timeout: Optional[float] = None):
        """
        初始化文件锁

        Args:
            lock_file: 锁文件路径
            timeout: 获取锁的超时时间(秒),None表示无限等待
        """
        self.lock_file = Path(lock_file)
        self.timeout = timeout if timeout is not None else self.DEFAULT_TIMEOUT
        self._locked = False
        self._pid = os.getpid()

        # 注册退出时自动释放锁
        atexit.register(self._atexit_release)

    def _atexit_release(self) -> None:
        """程序退出时自动释放锁"""
        if self._locked:
            try:
                self.release()
            except Exception:
                pass  # 退出时忽略错误

    def _is_lock_valid(self) -> bool:
        """
        检查当前锁是否有效(即持有锁的进程是否仍在运行)

        Returns:
            True if 锁存在且持有进程仍在运行
        """
        if not self.lock_file.exists():
            return False

        try:
            with open(self.lock_file, "r") as f:
                lines = f.readlines()
                if not lines:
                    return False

                lock_pid = int(lines[0].strip())

                # 检查进程是否存在
                try:
                    os.kill(lock_pid, 0)
                    return True
                except OSError:
                    # 进程不存在
                    return False

        except (ValueError, IOError, OSError):
            return False

    def acquire(self, blocking: bool = True) -> bool:
        """
        获取锁

        Args:
            blocking: True表示阻塞直到获取锁,False表示非阻塞

        Returns:
            True if 成功获取锁

        Raises:
            FileLockError: 非阻塞模式下获取失败或超时
        """
        if self._locked:
            return True

        start_time = time.time()

        while True:
            # 检查锁是否有效
            if self._is_lock_valid():
                if not blocking:
                    raise FileLockError(
                        f"锁已被其他进程持有: {self.lock_file}"
                    )

                # 检查超时
                if self.timeout > 0 and (time.time() - start_time) >= self.timeout:
                    raise FileLockError(
                        f"获取锁超时({self.timeout}秒): {self.lock_file}"
                    )

                # 等待后重试
                time.sleep(self.LOCK_POLL_INTERVAL)
                continue

            # 锁无效或不存在,尝试获取
            try:
                # 创建锁文件
                with open(self.lock_file, "w") as f:
                    f.write(f"{self._pid}\n")
                    f.write(f"{time.strftime('%Y-%m-%dT%H:%M:%S')}\n")

                self._locked = True
                return True

            except IOError as e:
                if not blocking:
                    raise FileLockError(f"创建锁文件失败: {e}")
                time.sleep(self.LOCK_POLL_INTERVAL)

    def release(self) -> None:
        """
        释放锁

        Raises:
            FileLockError: 锁文件操作失败
        """
        if not self._locked:
            return

        try:
            if self.lock_file.exists():
                # 验证当前进程确实持有锁
                try:
                    with open(self.lock_file, "r") as f:
                        lines = f.readlines()
                        if lines and int(lines[0].strip()) == self._pid:
                            self.lock_file.unlink()
                except (ValueError, IOError):
                    # 尝试删除 anyway
                    try:
                        self.lock_file.unlink()
                    except OSError:
                        pass

        except OSError as e:
            raise FileLockError(f"删除锁文件失败: {e}")

        finally:
            self._locked = False

    def __enter__(self):
        """上下文管理器入口"""
        self.acquire()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """上下文管理器出口"""
        self.release()
        return False


class GimiLockManager:
    """
    Gimi专用的锁管理器

    管理.gimi目录下不同资源的锁:
    - index: 轻量索引写入锁
    - vectors: 向量索引写入锁
    - cache: 缓存写入锁
    """

    def __init__(self, gimi_dir: Path):
        self.gimi_dir = Path(gimi_dir)
        self.locks_dir = self.gimi_dir / "locks"
        self.locks_dir.mkdir(parents=True, exist_ok=True)

    def get_lock(self, resource: str, timeout: Optional[float] = None) -> FileLock:
        """
        获取指定资源的锁

        Args:
            resource: 资源名称(index/vectors/cache)
            timeout: 超时时间(秒)

        Returns:
            FileLock实例
        """
        lock_file = self.locks_dir / f"{resource}.lock"
        return FileLock(lock_file, timeout=timeout)

    def __enter__(self):
        """支持上下文管理"""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """退出时无需特殊处理"""
        pass
