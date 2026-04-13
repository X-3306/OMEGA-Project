"""ctypes bridge for the optional native backend."""

from __future__ import annotations

import ctypes
from ctypes import wintypes
from dataclasses import dataclass
from pathlib import Path

from omega_protocol.system import native_dll_candidates


@dataclass(slots=True)
class NativeBridgeState:
    """Current load state of the native backend."""

    available: bool
    message: str


class NativeBridge:
    """Thin wrapper around omega_native.dll."""

    def __init__(self) -> None:
        self.dll: ctypes.CDLL | None = None
        self.path: Path | None = None
        self.state = NativeBridgeState(False, "Native backend not loaded.")
        self._load()

    def _load(self) -> None:
        for candidate in native_dll_candidates():
            if not candidate.exists():
                continue
            try:
                dll = ctypes.WinDLL(str(candidate))
                self.path = candidate
                dll.omega_file_sanitize.argtypes = [
                    wintypes.LPCWSTR,
                    wintypes.INT,
                    wintypes.INT,
                    wintypes.LPWSTR,
                    wintypes.UINT,
                ]
                dll.omega_file_sanitize.restype = wintypes.INT
                dll.omega_reinitialize_media.argtypes = [
                    wintypes.UINT,
                    wintypes.UINT,
                    wintypes.UINT,
                    wintypes.LPWSTR,
                    wintypes.UINT,
                ]
                dll.omega_reinitialize_media.restype = wintypes.INT
                self.dll = dll
                self.state = NativeBridgeState(True, f"Loaded native backend from {candidate.name}.")
                return
            except Exception as exc:
                self.state = NativeBridgeState(False, f"Failed to load {candidate.name}: {exc}")
        if not self.state.available:
            self.state = NativeBridgeState(False, "omega_native.dll not found; Python fallback remains active.")

    def sanitize_file(self, path: str, dry_run: bool) -> tuple[bool, str]:
        """Invoke native file sanitization when available."""

        dll = self.dll
        if dll is None:
            return False, self.state.message
        buffer = ctypes.create_unicode_buffer(512)
        code = int(dll.omega_file_sanitize(path, 2, int(dry_run), buffer, len(buffer)))
        return code == 0, buffer.value or f"Native backend returned code {code}"

    def reinitialize_media(self, disk_number: int, method: int, timeout_seconds: int) -> tuple[bool, str]:
        """Invoke native device sanitization when available."""

        dll = self.dll
        if dll is None:
            return False, self.state.message
        buffer = ctypes.create_unicode_buffer(512)
        code = int(
            dll.omega_reinitialize_media(
                int(disk_number),
                int(method),
                int(timeout_seconds),
                buffer,
                len(buffer),
            ),
        )
        return code == 0, buffer.value or f"Native backend returned code {code}"
