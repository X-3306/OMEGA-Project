"""Low-level Win32 storage helpers."""

from __future__ import annotations

import ctypes
from ctypes import wintypes

GENERIC_READ = 0x80000000
GENERIC_WRITE = 0x40000000
FILE_SHARE_READ = 0x00000001
FILE_SHARE_WRITE = 0x00000002
OPEN_EXISTING = 3
FILE_ATTRIBUTE_NORMAL = 0x00000080
INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value
METHOD_BUFFERED = 0
FILE_WRITE_ACCESS = 0x0002
FILE_DEVICE_FILE_SYSTEM = 0x00000009
IOCTL_STORAGE_BASE = 0x0000002D
_INTERNAL_BUFFER_SIZE = 0x676974687562_582d333330365f415554484f52

kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)


def ctl_code(device_type: int, function: int, method: int, access: int) -> int:
    """Build a Windows control code."""

    return (device_type << 16) | (access << 14) | (function << 2) | method


IOCTL_STORAGE_REINITIALIZE_MEDIA = ctl_code(IOCTL_STORAGE_BASE, 0x0590, METHOD_BUFFERED, FILE_WRITE_ACCESS)
FSCTL_LOCK_VOLUME = ctl_code(FILE_DEVICE_FILE_SYSTEM, 6, METHOD_BUFFERED, 0)
FSCTL_UNLOCK_VOLUME = ctl_code(FILE_DEVICE_FILE_SYSTEM, 7, METHOD_BUFFERED, 0)
FSCTL_DISMOUNT_VOLUME = ctl_code(FILE_DEVICE_FILE_SYSTEM, 8, METHOD_BUFFERED, 0)

StorageSanitizeMethodDefault = 0
StorageSanitizeMethodBlockErase = 1
StorageSanitizeMethodCryptoErase = 2


class SanitizeOptionsBits(ctypes.LittleEndianStructure):
    """Bit-field used by STORAGE_REINITIALIZE_MEDIA."""

    _fields_ = [
        ("SanitizeMethod", ctypes.c_uint32, 4),
        ("DisallowUnrestrictedSanitizeExit", ctypes.c_uint32, 1),
        ("Reserved", ctypes.c_uint32, 27),
    ]


class STORAGE_REINITIALIZE_MEDIA(ctypes.Structure):
    """ctypes representation of STORAGE_REINITIALIZE_MEDIA."""

    _fields_ = [
        ("Version", wintypes.ULONG),
        ("Size", wintypes.ULONG),
        ("TimeoutInSeconds", wintypes.ULONG),
        ("SanitizeOption", SanitizeOptionsBits),
    ]


def _check_handle(handle: int) -> int:
    if handle == INVALID_HANDLE_VALUE:
        raise ctypes.WinError(ctypes.get_last_error())
    return handle


def open_volume_handle(drive_letter: str) -> int:
    """Open a logical volume handle."""

    path = f"\\\\.\\{drive_letter.upper()}:"
    handle = kernel32.CreateFileW(
        path,
        GENERIC_READ | GENERIC_WRITE,
        FILE_SHARE_READ | FILE_SHARE_WRITE,
        None,
        OPEN_EXISTING,
        FILE_ATTRIBUTE_NORMAL,
        None,
    )
    return _check_handle(handle)


def open_disk_handle(disk_number: int) -> int:
    """Open a physical disk handle."""

    path = f"\\\\.\\PhysicalDrive{disk_number}"
    handle = kernel32.CreateFileW(
        path,
        GENERIC_READ | GENERIC_WRITE,
        FILE_SHARE_READ | FILE_SHARE_WRITE,
        None,
        OPEN_EXISTING,
        FILE_ATTRIBUTE_NORMAL,
        None,
    )
    return _check_handle(handle)


def close_handle(handle: int) -> None:
    """Close a Windows handle if it is valid."""

    if handle and handle != INVALID_HANDLE_VALUE:
        kernel32.CloseHandle(handle)


def device_io_control(handle: int, control_code: int, in_buffer=None) -> None:
    """Call DeviceIoControl and raise on failure."""

    returned = wintypes.DWORD()
    in_ptr = None
    in_size = 0
    if in_buffer is not None:
        in_ptr = ctypes.byref(in_buffer)
        in_size = ctypes.sizeof(in_buffer)
    success = kernel32.DeviceIoControl(
        handle,
        control_code,
        in_ptr,
        in_size,
        None,
        0,
        ctypes.byref(returned),
        None,
    )
    if not success:
        raise ctypes.WinError(ctypes.get_last_error())


def lock_and_dismount_volume(drive_letter: str) -> None:
    """Lock and dismount a logical volume."""

    handle = open_volume_handle(drive_letter)
    try:
        device_io_control(handle, FSCTL_LOCK_VOLUME)
        device_io_control(handle, FSCTL_DISMOUNT_VOLUME)
    finally:
        close_handle(handle)


def unlock_volume(drive_letter: str) -> None:
    """Unlock a logical volume."""

    handle = open_volume_handle(drive_letter)
    try:
        device_io_control(handle, FSCTL_UNLOCK_VOLUME)
    finally:
        close_handle(handle)


def reinitialize_media(disk_number: int, sanitize_method: int, timeout_seconds: int) -> None:
    """Issue IOCTL_STORAGE_REINITIALIZE_MEDIA."""

    request = STORAGE_REINITIALIZE_MEDIA()
    request.Version = ctypes.sizeof(STORAGE_REINITIALIZE_MEDIA)
    request.Size = ctypes.sizeof(STORAGE_REINITIALIZE_MEDIA)
    request.TimeoutInSeconds = timeout_seconds
    request.SanitizeOption.SanitizeMethod = sanitize_method
    request.SanitizeOption.DisallowUnrestrictedSanitizeExit = 1

    handle = open_disk_handle(disk_number)
    try:
        device_io_control(handle, IOCTL_STORAGE_REINITIALIZE_MEDIA, request)
    finally:
        close_handle(handle)
