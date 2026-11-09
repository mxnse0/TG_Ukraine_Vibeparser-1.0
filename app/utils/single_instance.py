"""Make sure only one bot process polls the same token at a time."""

from __future__ import annotations

import sys
from pathlib import Path


class SingleInstance:
    """A cross-platform single-instance lock.

    On Windows a named mutex is used (it disappears with the process). On
    POSIX a locked file is kept open for the lifetime of the process.
    """

    def __init__(self, lock_path: str | Path, name: str = "VibeParserBot") -> None:
        self.lock_path = Path(lock_path)
        self.name = name
        self._handle = None
        self._file = None

    def acquire(self) -> bool:
        if sys.platform == "win32":
            return self._acquire_windows()
        return self._acquire_posix()

    def release(self) -> None:
        if self._handle is not None:
            try:
                import ctypes

                ctypes.windll.kernel32.CloseHandle(self._handle)
            except Exception:  # noqa: BLE001 - best effort on shutdown
                pass
            self._handle = None
        if self._file is not None:
            try:
                import fcntl

                fcntl.flock(self._file.fileno(), fcntl.LOCK_UN)
            except Exception:  # noqa: BLE001
                pass
            try:
                self._file.close()
            except OSError:
                pass
            self._file = None

    # ------------------------------------------------------------------ helpers
    def _acquire_windows(self) -> bool:
        import ctypes
        from ctypes import wintypes

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.CreateMutexW.argtypes = [
            wintypes.LPVOID,
            wintypes.BOOL,
            wintypes.LPCWSTR,
        ]
        kernel32.CreateMutexW.restype = wintypes.HANDLE

        handle = kernel32.CreateMutexW(None, False, f"Local\\{self.name}")
        if not handle:
            return False
        if ctypes.get_last_error() == 183:  # ERROR_ALREADY_EXISTS
            kernel32.CloseHandle(handle)
            return False
        self._handle = handle
        return True

    def _acquire_posix(self) -> bool:
        import fcntl

        try:
            self.lock_path.parent.mkdir(parents=True, exist_ok=True)
            self._file = open(self.lock_path, "a+")
            fcntl.flock(self._file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except (OSError, ImportError):
            if self._file is not None:
                self._file.close()
                self._file = None
            return False
        return True
