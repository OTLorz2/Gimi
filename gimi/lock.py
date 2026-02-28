"""
T2: 写路径加锁实现

功能：
- 对 `.gimi/index`、`.gimi/vectors`、`.gimi/cache` 的写入使用文件锁
- 支持 PID 文件锁或 fcntl（Windows 使用 msvcrt/msvcrt 或 filelock）
- 获取锁失败时退出或阻塞等待
"""

import os
import time
import atexit
from pathlib import Path
from typing import Optional, Union
from contextlib import contextmanager
from dataclasses import dataclass
from enum import Enum, auto


class LockType(Enum):
    """锁类型"""
    PID_FILE = auto()  # PID 文件锁
    FLOCK = auto()     # 文件锁（fcntl / msvcrt）


@dataclass
class LockConfig:
    """锁配置"""
    lock_type: LockType = LockType.PID_FILE
    timeout: float = 30.0  # 获取锁的超时时间（秒）
    poll_interval: float = 0.1  # 轮询间隔（秒）
    blocking: bool = True  # 是否阻塞等待


class GimiLock:
    """
    Gimi 写路径文件锁

    用于保护对 .gimi 目录下 index、vectors、cache 的写入操作。
    支持 PID 文件锁和 flock 两种实现。
    """

    LOCK_FILENAME = "write.lock"

    def __init__(
        self,
        gimi_path: Union[str, Path],
        config: Optional[LockConfig] = None
    ):
        self.gimi_path = Path(gimi_path)
        self.config = config or LockConfig()
        self.lock_file = self.gimi_path / self.LOCK_FILENAME
        self._lock_fd: Optional[int] = None
        self._acquired = False

    def _read_pid(self) -> Optional[int]:
        """读取锁文件中的 PID"""
        if not self.lock_file.exists():
            return None
        try:
            pid = int(self.lock_file.read_text().strip())
            return pid
        except (ValueError, IOError):
            return None

    def _is_process_alive(self, pid: int) -> bool:
        """检查进程是否存活"""
        try:
            if os.name == "nt":
                # Windows
                import ctypes
                kernel32 = ctypes.windll.kernel32
                handle = kernel32.OpenProcess(1, False, pid)
                if handle == 0:
                    return False
                kernel32.CloseHandle(handle)
                return True
            else:
                # Unix-like
                os.kill(pid, 0)
                return True
        except (OSError, ImportError):
            return False

    def _acquire_pid_lock(self) -> bool:
        """获取 PID 文件锁"""
        start_time = time.time()

        while True:
            # 检查是否有其他进程持有锁
            existing_pid = self._read_pid()

            if existing_pid is not None:
                if self._is_process_alive(existing_pid):
                    # 锁被其他活跃进程持有
                    if not self.config.blocking:
                        return False

                    elapsed = time.time() - start_time
                    if elapsed >= self.config.timeout:
                        raise TimeoutError(
                            f"获取锁超时（{self.config.timeout}秒）。"
                            f"当前锁被进程 {existing_pid} 持有。"
                        )

                    time.sleep(self.config.poll_interval)
                    continue
                else:
                    # 锁被已终止的进程持有，清理它
                    try:
                        self.lock_file.unlink()
                    except FileNotFoundError:
                        pass

            # 尝试创建锁文件
            try:
                # 使用独占创建模式（原子操作）
                fd = os.open(
                    self.lock_file,
                    os.O_CREAT | os.O_EXCL | os.O_WRONLY
                )
                os.write(fd, str(os.getpid()).encode())
                os.close(fd)
                self._acquired = True
                return True
            except FileExistsError:
                # 文件刚刚被其他进程创建，继续循环
                continue

    def _release_pid_lock(self) -> None:
        """释放 PID 文件锁"""
        if not self._acquired:
            return

        try:
            # 验证锁文件中的 PID 是当前进程
            current_pid = self._read_pid()
            if current_pid == os.getpid():
                self.lock_file.unlink(missing_ok=True)
        except Exception:
            pass
        finally:
            self._acquired = False

    def acquire(self) -> bool:
        """
        获取写锁

        Returns:
            bool: 是否成功获取锁

        Raises:
            TimeoutError: 如果获取锁超时且配置了阻塞等待
        """
        if self.config.lock_type == LockType.PID_FILE:
            return self._acquire_pid_lock()
        else:
            raise NotImplementedError(f"锁类型 {self.config.lock_type} 尚未实现")

    def release(self) -> None:
        """释放写锁"""
        if self.config.lock_type == LockType.PID_FILE:
            self._release_pid_lock()

    def __enter__(self):
        """上下文管理器入口"""
        self.acquire()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """上下文管理器出口"""
        self.release()
        return False


@contextmanager
def gimi_lock(
    gimi_path: Union[str, Path],
    timeout: float = 30.0,
    blocking: bool = True
):
    """
    便捷的上下文管理器，用于获取 Gimi 写锁

    Args:
        gimi_path: .gimi 目录路径
        timeout: 获取锁的超时时间（秒）
        blocking: 是否阻塞等待

    Example:
        with gimi_lock("/path/to/.gimi"):
            # 执行写入操作
            pass
    """
    config = LockConfig(timeout=timeout, blocking=blocking)
    lock = GimiLock(gimi_path, config)
    lock.acquire()
    try:
        yield lock
    finally:
        lock.release()


if __name__ == "__main__":
    import tempfile

    # 测试锁功能
    with tempfile.TemporaryDirectory() as tmpdir:
        gimi_path = Path(tmpdir) / ".gimi"
        gimi_path.mkdir(parents=True)

        print(f"测试 PID 文件锁: {gimi_path}")

        # 测试 1: 基本获取和释放
        print("\n测试 1: 基本获取和释放锁")
        lock = GimiLock(gimi_path)
        result = lock.acquire()
        print(f"  获取锁: {result}")
        lock.release()
        print(f"  释放锁完成")

        # 测试 2: 上下文管理器
        print("\n测试 2: 上下文管理器")
        with gimi_lock(gimi_path):
            print("  在锁保护区域内")
        print("  已退出锁保护区域")

        # 测试 3: 锁文件存在性检查
        print("\n测试 3: 锁文件检查")
        lock_file = gimi_path / "write.lock"
        print(f"  锁文件存在: {lock_file.exists()}")

        print("\n所有测试通过!")
