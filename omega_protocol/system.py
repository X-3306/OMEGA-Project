"""Windows-specific helpers used by the application."""

from __future__ import annotations

import ctypes
import os
import re
from pathlib import Path

from omega_protocol.models import InventorySource, MediaCapabilities
from omega_protocol.runtime import application_root, resource_root

FILE_ATTRIBUTE_REPARSE_POINT = 0x0400
DRIVE_REMOVABLE = 2
DRIVE_FIXED = 3
DRIVE_REMOTE = 4
DELETE_FILE = ctypes.windll.kernel32.DeleteFileW
GET_DRIVE_TYPE = ctypes.windll.kernel32.GetDriveTypeW
GET_FILE_ATTRIBUTES = ctypes.windll.kernel32.GetFileAttributesW
GET_LOGICAL_DRIVE_STRINGS = ctypes.windll.kernel32.GetLogicalDriveStringsW
GET_VOLUME_INFORMATION = ctypes.windll.kernel32.GetVolumeInformationW
GET_DISK_FREE_SPACE_EX = ctypes.windll.kernel32.GetDiskFreeSpaceExW
IS_USER_AN_ADMIN = ctypes.windll.shell32.IsUserAnAdmin


def is_windows_admin() -> bool:
    """Return True when the current process has administrator rights."""

    try:
        return bool(IS_USER_AN_ADMIN())
    except Exception:
        return False


def build_media_capabilities(items: list[dict]) -> list[MediaCapabilities]:
    """Normalize raw privileged inventory payloads into public models."""

    result: list[MediaCapabilities] = []
    for item in items:
        partitions = item.get("Partitions") or []
        drive_letters = sorted(
            {
                str(partition.get("DriveLetter", "")).upper()
                for partition in partitions
                if partition.get("DriveLetter")
            },
        )
        notes: list[str] = []
        bus_type = (item.get("BusType") or "").upper()
        media_type = (item.get("MediaType") or "").upper()
        supports_reinitialize = None
        supports_block = None
        supports_crypto = None

        if bus_type == "NVME":
            supports_reinitialize = True
            supports_block = True
            supports_crypto = True
            notes.append("NVMe media may support storage sanitize through IOCTL_STORAGE_REINITIALIZE_MEDIA.")
        elif bus_type in {"SATA", "ATA", "RAID"} and media_type == "SSD":
            supports_reinitialize = False
            supports_block = False
            supports_crypto = False
            notes.append("SATA SSD media usually requires an ATA security or offline workflow.")
        elif media_type == "HDD":
            supports_reinitialize = True
            notes.append("Rotational media may qualify for Device Clear if the driver accepts the request.")
        elif bus_type in {"USB", "SD"} or item.get("IsRemovable"):
            supports_reinitialize = False
            notes.append("Removable or USB media cannot be treated as a reliable purge target from the standard Windows stack.")

        bitlocker_state = any(
            (partition.get("BitLocker") or {}).get("ProtectionStatus") not in {"", "Off", "0", None}
            for partition in partitions
        )

        result.append(
            MediaCapabilities(
                disk_number=int(item["Number"]),
                friendly_name=item.get("FriendlyName") or "Unknown device",
                bus_type=item.get("BusType") or "Unknown",
                media_type=item.get("MediaType") or "Unknown",
                partition_style=item.get("PartitionStyle") or "",
                health_status=item.get("HealthStatus") or "",
                operational_status=item.get("OperationalStatus") or "",
                is_boot=bool(item.get("IsBoot")),
                is_system=bool(item.get("IsSystem")),
                is_read_only=bool(item.get("IsReadOnly")),
                is_offline=bool(item.get("IsOffline")),
                is_removable=bool(item.get("IsRemovable")),
                size_bytes=int(item.get("Size") or 0),
                partitions=partitions,
                drive_letters=drive_letters,
                supports_reinitialize_media=supports_reinitialize,
                supports_block_erase=supports_block,
                supports_crypto_erase=supports_crypto,
                is_bitlocker_protected=bitlocker_state,
                notes=notes,
                inventory_source=InventorySource.PHYSICAL_DISK,
                supports_direct_device_ops=True,
            ),
        )
    return result


def build_volume_fallback_inventory() -> list[MediaCapabilities]:
    """Enumerate logical volumes without requiring privileged storage APIs."""

    drives = logical_drive_roots()
    system_drive = os.environ.get("SystemDrive", "C:").rstrip("\\").upper()
    fallback: list[MediaCapabilities] = []

    for root in drives:
        drive_letter = root[:1].upper()
        drive_type = int(GET_DRIVE_TYPE(root))
        if drive_type == DRIVE_REMOTE:
            continue

        label = volume_label(root) or f"{drive_letter}:"
        size_bytes = volume_size(root)
        notes = [
            "Limited inventory mode: this view is based on logical volumes only.",
            "Restart the application as administrator to enumerate physical disks and enable drive sanitization.",
        ]
        if drive_type == DRIVE_REMOVABLE:
            notes.append("This volume appears to be removable media.")

        fallback.append(
            MediaCapabilities(
                disk_number=-_drive_letter_to_index(drive_letter),
                friendly_name=label,
                bus_type="Logical Volume",
                media_type="Removable" if drive_type == DRIVE_REMOVABLE else "Unknown",
                operational_status="Mounted",
                is_system=f"{drive_letter}:" == system_drive,
                is_removable=drive_type == DRIVE_REMOVABLE,
                size_bytes=size_bytes,
                drive_letters=[drive_letter],
                notes=notes,
                inventory_source=InventorySource.LOGICAL_VOLUME,
                supports_direct_device_ops=False,
            ),
        )

    return fallback


def logical_drive_roots() -> list[str]:
    """Return all logical drive roots visible to the current process."""

    required = GET_LOGICAL_DRIVE_STRINGS(0, None)
    if required <= 0:
        return []

    buffer = ctypes.create_unicode_buffer(required + 1)
    written = GET_LOGICAL_DRIVE_STRINGS(required, buffer)
    raw = buffer[:written]
    return [part for part in raw.split("\x00") if part]


def volume_label(root: str) -> str:
    """Return the user-visible volume label, if available."""

    label_buffer = ctypes.create_unicode_buffer(261)
    filesystem_buffer = ctypes.create_unicode_buffer(261)
    serial = ctypes.c_uint(0)
    component_length = ctypes.c_uint(0)
    flags = ctypes.c_uint(0)

    success = GET_VOLUME_INFORMATION(
        root,
        label_buffer,
        len(label_buffer),
        ctypes.byref(serial),
        ctypes.byref(component_length),
        ctypes.byref(flags),
        filesystem_buffer,
        len(filesystem_buffer),
    )
    if not success:
        return ""
    return label_buffer.value.strip()


def volume_size(root: str) -> int:
    """Return the total size of a logical volume in bytes."""

    free_bytes_available = ctypes.c_ulonglong(0)
    total_bytes = ctypes.c_ulonglong(0)
    total_free_bytes = ctypes.c_ulonglong(0)
    success = GET_DISK_FREE_SPACE_EX(
        root,
        ctypes.byref(free_bytes_available),
        ctypes.byref(total_bytes),
        ctypes.byref(total_free_bytes),
    )
    if not success:
        return 0
    return int(total_bytes.value)


def media_by_drive_letter(disks: list[MediaCapabilities]) -> dict[str, MediaCapabilities]:
    """Map drive letters to their parent inventory entries."""

    mapping: dict[str, MediaCapabilities] = {}
    for disk in disks:
        for drive_letter in disk.drive_letters:
            mapping[drive_letter.upper()] = disk
    return mapping


def get_file_attributes(path: str) -> int:
    """Return Win32 file attributes for a path."""

    attributes = GET_FILE_ATTRIBUTES(path)
    if attributes == 0xFFFFFFFF:
        return 0
    return int(attributes)


def is_reparse_point(path: str) -> bool:
    """Return True if the path is a Windows reparse point."""

    return bool(get_file_attributes(path) & FILE_ATTRIBUTE_REPARSE_POINT)


def is_unc_path(path: str) -> bool:
    """Return True if the path is a UNC or network path."""

    return os.path.abspath(path).startswith("\\\\")


def is_ads_path(path: str) -> bool:
    """Return True when the path addresses an alternate data stream."""

    normalized = os.path.abspath(path)
    match = re.match(r"^[A-Za-z]:(.*)$", normalized)
    if not match:
        return False
    return ":" in match.group(1)


def resolve_drive_letter(path: str) -> str:
    """Return the drive letter for an absolute path."""

    drive, _ = os.path.splitdrive(os.path.abspath(path))
    return drive[:1].upper()


def delete_path_windows(path: str) -> None:
    """Delete a file path using DeleteFileW and raise on failure."""

    if not DELETE_FILE(path):
        raise ctypes.WinError()


def native_dll_candidates() -> list[Path]:
    """Return supported omega_native.dll search paths."""

    bundle_root = resource_root()
    app_root = application_root()
    return [
        bundle_root / "omega_native.dll",
        app_root / "omega_native.dll",
        app_root / "build" / "Release" / "omega_native.dll",
        app_root / "build" / "omega_native.dll",
    ]


def _drive_letter_to_index(letter: str) -> int:
    normalized = letter[:1].upper()
    if "A" <= normalized <= "Z":
        return ord(normalized) - ord("A") + 1
    return 1000
