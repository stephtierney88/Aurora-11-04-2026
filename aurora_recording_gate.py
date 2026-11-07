"""Cooperating writer leases and exclusive, nonblocking retention access.

The sidecar is permanent: deleting/replacing it would split lock ownership.
Windows shared byte locks: https://learn.microsoft.com/windows/win32/api/fileapi/nf-fileapi-lockfileex
"""
import os
from pathlib import Path

from aurora_execution_history import ordinary


class RecordingGate:
    def __init__(self, root, *, exclusive=False):
        self.handle = None
        root = Path(root).absolute()
        root.mkdir(parents=True, exist_ok=True)
        ordinary(root, directory=True)
        path = root / 'recording.guard'
        if path.exists() or path.is_symlink():
            ordinary(path)
        handle = open(path, 'a+b')
        try:
            ordinary(path)
            if os.name == 'nt':
                import ctypes
                from ctypes import wintypes
                import msvcrt

                class Overlapped(ctypes.Structure):
                    _fields_ = [('Internal', ctypes.c_size_t), ('InternalHigh', ctypes.c_size_t),
                                ('Offset', wintypes.DWORD), ('OffsetHigh', wintypes.DWORD),
                                ('hEvent', wintypes.HANDLE)]

                self.overlapped = Overlapped()
                self.kernel = ctypes.WinDLL('kernel32', use_last_error=True)
                self.kernel.LockFileEx.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.DWORD,
                                                   wintypes.DWORD, wintypes.DWORD, ctypes.POINTER(Overlapped)]
                self.kernel.LockFileEx.restype = wintypes.BOOL
                self.kernel.UnlockFileEx.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.DWORD,
                                                     wintypes.DWORD, ctypes.POINTER(Overlapped)]
                self.kernel.UnlockFileEx.restype = wintypes.BOOL
                self.native_handle = msvcrt.get_osfhandle(handle.fileno())
                if not self.kernel.LockFileEx(self.native_handle, 1 | (2 if exclusive else 0),
                                               0, 1, 0, ctypes.byref(self.overlapped)):
                    raise ctypes.WinError(ctypes.get_last_error())
            else:
                import fcntl
                fcntl.flock(handle, (fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH) | fcntl.LOCK_NB)
            self.handle = handle
        except BaseException:
            handle.close()
            raise

    def close(self):
        if self.handle is None:
            return
        handle, self.handle = self.handle, None
        try:
            if os.name == 'nt':
                import ctypes
                self.kernel.UnlockFileEx(self.native_handle, 0, 1, 0, ctypes.byref(self.overlapped))
            else:
                import fcntl
                fcntl.flock(handle, fcntl.LOCK_UN)
        finally:
            handle.close()  # The OS also releases locks on close / process exit.

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()
