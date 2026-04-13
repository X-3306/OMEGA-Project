"""Inventory services with caching, privilege awareness and graceful fallback."""

from __future__ import annotations

import json
import subprocess
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass

from omega_protocol.errors import (
    InventoryAccessDeniedError,
    InventoryError,
    InventoryParseError,
    InventoryTimeoutError,
    InventoryUnsupportedError,
)
from omega_protocol.models import InventorySnapshot, MediaCapabilities, now_iso
from omega_protocol.settings import INVENTORY_CACHE_TTL_SECONDS, PRIVILEGED_INVENTORY_TIMEOUT_SECONDS
from omega_protocol.system import build_media_capabilities, build_volume_fallback_inventory, is_windows_admin

InventoryRunner = Callable[[str, int], list[dict]]
VolumeFallbackRunner = Callable[[], list[MediaCapabilities]]
Clock = Callable[[], float]


PRIVILEGED_INVENTORY_SCRIPT = r"""
$ErrorActionPreference = 'Stop'
$bitlocker = @{}
try {
  Get-BitLockerVolume -ErrorAction Stop | ForEach-Object {
    $mountPoint = if ($_.MountPoint) { [string]$_.MountPoint } else { '' }
    $key = $mountPoint.TrimEnd(':', '\')
    if ($key) {
      $bitlocker[$key] = [PSCustomObject]@{
        ProtectionStatus = [string]$_.ProtectionStatus
        VolumeStatus = [string]$_.VolumeStatus
        EncryptionMethod = [string]$_.EncryptionMethod
      }
    }
  }
} catch {}
$disks = Get-Disk -ErrorAction Stop | Sort-Object Number | ForEach-Object {
  $disk = $_
  $parts = @()
  try {
    $parts = Get-Partition -DiskNumber $disk.Number -ErrorAction Stop | Sort-Object PartitionNumber | ForEach-Object {
      $part = $_
      $vol = $null
      try {
        $vol = $part | Get-Volume -ErrorAction Stop
      } catch {}
      $driveLetter = if ($vol -and $vol.DriveLetter) { [string]$vol.DriveLetter } else { '' }
      $lookupKey = $driveLetter.TrimEnd(':', '\')
      $bit = if ($lookupKey -and $bitlocker.ContainsKey($lookupKey)) { $bitlocker[$lookupKey] } else { $null }
      [PSCustomObject]@{
        PartitionNumber = [int]$part.PartitionNumber
        DriveLetter = $driveLetter
        FileSystem = if ($vol) { [string]$vol.FileSystem } else { '' }
        AccessPaths = @($part.AccessPaths | ForEach-Object { [string]$_ })
        Size = [int64]$part.Size
        Type = [string]$part.Type
        BitLocker = $bit
      }
    }
  } catch {}
  [PSCustomObject]@{
    Number = [int]$disk.Number
    FriendlyName = [string]$disk.FriendlyName
    BusType = [string]$disk.BusType
    MediaType = [string]$disk.MediaType
    PartitionStyle = [string]$disk.PartitionStyle
    HealthStatus = [string]$disk.HealthStatus
    OperationalStatus = [string]$disk.OperationalStatus
    IsBoot = [bool]$disk.IsBoot
    IsSystem = [bool]$disk.IsSystem
    IsReadOnly = [bool]$disk.IsReadOnly
    IsOffline = [bool]$disk.IsOffline
    IsRemovable = [bool]$disk.IsRemovable
    Size = [int64]$disk.Size
    Partitions = $parts
  }
}
$disks | ConvertTo-Json -Depth 8 -Compress
"""


@dataclass(slots=True)
class _CacheEntry:
    snapshot: InventorySnapshot
    expires_at: float


@dataclass(slots=True)
class _FailureEntry:
    error: InventoryError
    expires_at: float


def default_inventory_runner(script: str, timeout_seconds: int) -> list[dict]:
    """Run the privileged PowerShell inventory script and return decoded JSON."""

    try:
        process = subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-Command",
                script,
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout_seconds,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except subprocess.TimeoutExpired as exc:
        raise InventoryTimeoutError(f"Physical-drive inventory timed out after {timeout_seconds}s.") from exc
    except FileNotFoundError as exc:
        raise InventoryUnsupportedError("PowerShell is not available on this system.") from exc

    stderr = (process.stderr or process.stdout or "").strip()
    if process.returncode != 0:
        lowered = stderr.lower()
        if "access denied" in lowered or "0x80041003" in lowered:
            raise InventoryAccessDeniedError(_compact_error(stderr))
        if "is not recognized" in lowered or "not supported" in lowered:
            raise InventoryUnsupportedError(_compact_error(stderr))
        raise InventoryError(_compact_error(stderr or "PowerShell inventory failed."))

    raw = process.stdout.strip()
    if not raw:
        return []

    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise InventoryParseError(f"Inventory JSON parse failed: {exc}") from exc

    if isinstance(payload, list):
        return payload
    return [payload]


class InventoryService:
    """Provides cached drive inventory snapshots with graceful fallback."""

    def __init__(
        self,
        runner: InventoryRunner = default_inventory_runner,
        volume_fallback_runner: VolumeFallbackRunner = build_volume_fallback_inventory,
        cache_ttl_seconds: int = INVENTORY_CACHE_TTL_SECONDS,
        timeout_seconds: int = PRIVILEGED_INVENTORY_TIMEOUT_SECONDS,
        clock: Clock = time.monotonic,
    ) -> None:
        self.runner = runner
        self.volume_fallback_runner = volume_fallback_runner
        self.cache_ttl_seconds = cache_ttl_seconds
        self.timeout_seconds = timeout_seconds
        self.clock = clock
        self._cache: _CacheEntry | None = None
        self._failure: _FailureEntry | None = None
        self._lock = threading.RLock()

    def invalidate(self) -> None:
        """Drop cached inventory and cached failures."""

        with self._lock:
            self._cache = None
            self._failure = None

    def get_snapshot(self, force_refresh: bool = False) -> InventorySnapshot:
        """Return the latest inventory snapshot, using cache when possible."""

        with self._lock:
            now = self.clock()
            if not force_refresh and self._cache and now < self._cache.expires_at:
                cached = self._cache.snapshot
                return InventorySnapshot(
                    generated_at=cached.generated_at,
                    from_cache=True,
                    disks=cached.disks,
                    warning=cached.warning,
                )
            if not force_refresh and self._failure and now < self._failure.expires_at:
                fallback_snapshot = self._build_fallback_snapshot(self._failure.error)
                if fallback_snapshot is not None:
                    return fallback_snapshot
                raise self._failure.error

        if not is_windows_admin():
            snapshot = self._build_fallback_snapshot(
                InventoryAccessDeniedError(
                    "Administrative access is required for full physical-drive inventory.",
                ),
            )
            if snapshot is not None:
                self._store_snapshot(snapshot)
                return snapshot

        try:
            payload = self.runner(PRIVILEGED_INVENTORY_SCRIPT, self.timeout_seconds)
        except InventoryError as exc:
            self.remember_failure(exc)
            fallback_snapshot = self._build_fallback_snapshot(exc)
            if fallback_snapshot is not None:
                self._store_snapshot(fallback_snapshot)
                return fallback_snapshot
            raise

        disks = build_media_capabilities(payload)
        snapshot = InventorySnapshot(
            generated_at=now_iso(),
            from_cache=False,
            disks=disks,
        )
        self._store_snapshot(snapshot)
        return snapshot

    def get_disks(self, force_refresh: bool = False) -> list[MediaCapabilities]:
        """Convenience wrapper returning only the drive list."""

        return self.get_snapshot(force_refresh=force_refresh).disks

    def remember_failure(self, error: InventoryError) -> None:
        """Cache a recent inventory failure to avoid hammering PowerShell."""

        with self._lock:
            self._failure = _FailureEntry(error=error, expires_at=self.clock() + self.cache_ttl_seconds)

    def _build_fallback_snapshot(self, error: InventoryError) -> InventorySnapshot | None:
        """Build a limited logical-volume snapshot when physical inventory is unavailable."""

        volumes = self.volume_fallback_runner()
        if not volumes:
            return None
        return InventorySnapshot(
            generated_at=now_iso(),
            from_cache=False,
            disks=volumes,
            warning=(
                "Showing limited logical-volume inventory. "
                f"Full physical-drive inventory is currently unavailable: {error}"
            ),
        )

    def _store_snapshot(self, snapshot: InventorySnapshot) -> None:
        with self._lock:
            self._cache = _CacheEntry(snapshot=snapshot, expires_at=self.clock() + self.cache_ttl_seconds)
            self._failure = None


def _compact_error(text: str) -> str:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if not lines:
        return "PowerShell inventory failed."
    return " | ".join(lines[:3])
