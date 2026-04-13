"""Plan-building service."""

from __future__ import annotations

import hashlib

from omega_protocol.errors import InventoryError
from omega_protocol.models import InventorySnapshot, OperationMode, PreflightResult, now_iso
from omega_protocol.policy import create_drive_plan, create_file_plan
from omega_protocol.services.inventory import InventoryService
from omega_protocol.system import media_by_drive_letter


class PlanService:
    """Builds preflight plans from targets and inventory snapshots."""

    def __init__(self, inventory_service: InventoryService) -> None:
        self.inventory_service = inventory_service

    def build_preflight(
        self,
        mode: OperationMode,
        targets: list[str],
        dry_run: bool,
        force_inventory_refresh: bool = False,
    ) -> PreflightResult:
        """Build a preflight result for the given mode and targets."""

        request_key = f"{mode.value}|{dry_run}|{'|'.join(sorted(targets))}"
        request_id = hashlib.sha1(request_key.encode("utf-8", "replace")).hexdigest()[:12]
        warnings: list[str] = []
        errors: list[str] = []
        inventory: InventorySnapshot | None = None

        try:
            inventory = self.inventory_service.get_snapshot(force_refresh=force_inventory_refresh)
        except InventoryError as exc:
            self.inventory_service.remember_failure(exc)
            warnings.append(f"Drive inventory is unavailable right now: {exc}")

        if inventory and inventory.warning:
            warnings.append(inventory.warning)

        if mode is OperationMode.FILE_SANITIZE:
            media_map = media_by_drive_letter(inventory.disks if inventory else [])
            plans = [create_file_plan(target, dry_run, media_map) for target in targets]
            for plan in plans:
                plan.warnings.extend(warnings)
        else:
            disk_index = {str(disk.disk_number): disk for disk in (inventory.disks if inventory else [])}
            plans = [create_drive_plan(disk_index[target], dry_run) for target in targets if target in disk_index]
            if targets and len(plans) != len(targets):
                errors.append("One or more selected drives are no longer available in the latest inventory snapshot.")
            if inventory is None:
                errors.append("Drive inventory could not be loaded.")

        return PreflightResult(
            request_id=request_id,
            generated_at=now_iso(),
            mode=mode,
            dry_run=dry_run,
            plans=plans,
            inventory=inventory,
            warnings=warnings,
            errors=errors,
        )
