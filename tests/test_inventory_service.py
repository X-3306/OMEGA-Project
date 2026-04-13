from __future__ import annotations

import subprocess
from types import SimpleNamespace

import pytest

from omega_protocol.errors import InventoryAccessDeniedError, InventoryTimeoutError, InventoryUnsupportedError
from omega_protocol.models import InventorySource, MediaCapabilities
from omega_protocol.services import inventory as inventory_module
from omega_protocol.services.inventory import InventoryService, default_inventory_runner


def _sample_payload() -> list[dict]:
    return [
        {
            "Number": 1,
            "FriendlyName": "UnitTest Disk",
            "BusType": "NVMe",
            "MediaType": "SSD",
            "PartitionStyle": "GPT",
            "Partitions": [{"DriveLetter": "E"}],
        },
    ]


def test_default_inventory_runner_classifies_access_denied(monkeypatch):
    def fake_run(*_args, **_kwargs):
        return SimpleNamespace(returncode=1, stdout="", stderr="Access denied")

    monkeypatch.setattr(subprocess, "run", fake_run)

    with pytest.raises(InventoryAccessDeniedError):
        default_inventory_runner("Get-Disk", 1)


def test_default_inventory_runner_classifies_timeout(monkeypatch):
    def fake_run(*_args, **_kwargs):
        raise subprocess.TimeoutExpired(cmd="powershell", timeout=1)

    monkeypatch.setattr(subprocess, "run", fake_run)

    with pytest.raises(InventoryTimeoutError):
        default_inventory_runner("Get-Disk", 1)


def test_default_inventory_runner_classifies_missing_powershell(monkeypatch):
    def fake_run(*_args, **_kwargs):
        raise FileNotFoundError("powershell not found")

    monkeypatch.setattr(subprocess, "run", fake_run)

    with pytest.raises(InventoryUnsupportedError):
        default_inventory_runner("Get-Disk", 1)


def test_inventory_service_uses_cache(monkeypatch):
    calls = {"count": 0}
    ticks = iter([0.0, 0.0, 5.0, 5.0, 35.0, 35.0])

    def fake_clock() -> float:
        return next(ticks)

    def fake_runner(_script: str, _timeout: int) -> list[dict]:
        calls["count"] += 1
        return _sample_payload()

    monkeypatch.setattr(inventory_module, "is_windows_admin", lambda: True)
    service = InventoryService(
        runner=fake_runner,
        volume_fallback_runner=lambda: [],
        cache_ttl_seconds=30,
        clock=fake_clock,
    )

    first = service.get_snapshot()
    second = service.get_snapshot()

    assert calls["count"] == 1
    assert first.from_cache is False
    assert second.from_cache is True
    assert second.disks[0].disk_number == 1


def test_inventory_service_caches_failures(monkeypatch):
    calls = {"count": 0}

    def fake_runner(_script: str, _timeout: int) -> list[dict]:
        calls["count"] += 1
        raise InventoryAccessDeniedError("denied")

    monkeypatch.setattr(inventory_module, "is_windows_admin", lambda: True)
    service = InventoryService(
        runner=fake_runner,
        volume_fallback_runner=lambda: [],
        cache_ttl_seconds=30,
        clock=lambda: 0.0,
    )

    with pytest.raises(InventoryAccessDeniedError):
        service.get_snapshot()
    with pytest.raises(InventoryAccessDeniedError):
        service.get_snapshot()

    assert calls["count"] == 1


def test_inventory_service_returns_logical_volume_fallback_for_non_admin(monkeypatch):
    monkeypatch.setattr(inventory_module, "is_windows_admin", lambda: False)
    fallback = [
        MediaCapabilities(
            disk_number=-3,
            friendly_name="Volume E",
            bus_type="Logical Volume",
            media_type="Unknown",
            drive_letters=["E"],
            inventory_source=InventorySource.LOGICAL_VOLUME,
            supports_direct_device_ops=False,
        ),
    ]
    service = InventoryService(volume_fallback_runner=lambda: fallback)

    snapshot = service.get_snapshot(force_refresh=True)

    assert len(snapshot.disks) == 1
    assert snapshot.disks[0].inventory_source is InventorySource.LOGICAL_VOLUME
    assert snapshot.disks[0].supports_direct_device_ops is False
    assert snapshot.warning is not None
