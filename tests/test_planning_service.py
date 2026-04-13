from __future__ import annotations

import pytest

from omega_protocol.errors import InventoryAccessDeniedError
from omega_protocol.models import InventorySnapshot, MediaCapabilities, OperationMode
from omega_protocol.services.planning import PlanService


class StubInventoryService:
    def __init__(self, snapshot=None, error: Exception | None = None) -> None:
        self.snapshot = snapshot
        self.error = error
        self.remembered: Exception | None = None

    def get_snapshot(self, force_refresh: bool = False):
        if self.error:
            raise self.error
        return self.snapshot

    def remember_failure(self, error: Exception) -> None:
        self.remembered = error


def test_build_preflight_for_files_survives_inventory_failure(tmp_path):
    target = tmp_path / "secret.bin"
    target.write_bytes(b"abc")
    inventory_service = StubInventoryService(error=InventoryAccessDeniedError("denied"))
    service = PlanService(inventory_service)

    result = service.build_preflight(OperationMode.FILE_SANITIZE, [str(target)], dry_run=True)

    assert len(result.plans) == 1
    assert any("inventory" in warning.lower() for warning in result.warnings)
    assert inventory_service.remembered is not None


def test_build_preflight_for_drives_reports_missing_targets():
    snapshot = InventorySnapshot(
        generated_at="2026-04-11T13:00:00+02:00",
        from_cache=False,
        disks=[MediaCapabilities(disk_number=2, friendly_name="Disk 2", bus_type="NVMe", media_type="SSD")],
    )
    service = PlanService(StubInventoryService(snapshot=snapshot))

    result = service.build_preflight(OperationMode.DRIVE_SANITIZE, ["2", "9"], dry_run=True)

    assert len(result.plans) == 1
    assert result.errors


def test_build_preflight_for_drives_propagates_inventory_errors():
    inventory_service = StubInventoryService(error=InventoryAccessDeniedError("denied"))
    service = PlanService(inventory_service)

    with pytest.raises(InventoryAccessDeniedError):
        service.build_preflight(OperationMode.DRIVE_SANITIZE, ["2"], dry_run=True)
