"""Policy helpers that translate inventory into execution plans."""

from __future__ import annotations

import hashlib
import os
from pathlib import Path

from omega_protocol.models import (
    AssuranceLevel,
    ExecutionPlan,
    InventorySource,
    MediaCapabilities,
    OperationMode,
    OperationStage,
    PlanStep,
    TargetKind,
)
from omega_protocol.system import is_ads_path, is_reparse_point, is_unc_path, resolve_drive_letter


def _plan_id(prefix: str, target: str) -> str:
    digest = hashlib.sha1(target.encode("utf-8", "replace")).hexdigest()[:12]
    return f"{prefix}-{digest}"


def create_file_plan(path: str, dry_run: bool, media_map: dict[str, MediaCapabilities]) -> ExecutionPlan:
    """Create a file-sanitization plan for one path."""

    normalized = os.path.abspath(path)
    restrictions: list[str] = []
    warnings: list[str] = []
    executable = True
    method_name = "Rename -> zero overwrite -> verify -> random overwrite -> truncate -> unlink"
    assurance_target = AssuranceLevel.BEST_EFFORT_FILE_SANITIZE
    rationale = (
        "The file will be sanitized at the filesystem level without overstating "
        "the achievable assurance for SSD media."
    )

    if not os.path.exists(normalized):
        executable = False
        restrictions.append("The selected file does not exist.")
        assurance_target = AssuranceLevel.UNSUPPORTED

    if is_unc_path(normalized):
        executable = False
        restrictions.append("UNC and network paths are blocked.")
        assurance_target = AssuranceLevel.UNSUPPORTED

    if os.path.islink(normalized) or is_reparse_point(normalized):
        executable = False
        restrictions.append("Symlinks and reparse points are blocked for safety.")
        assurance_target = AssuranceLevel.UNSUPPORTED

    if is_ads_path(normalized):
        warnings.append(
            "An alternate data stream was detected. The selected stream will be "
            "sanitized without renaming the base file.",
        )

    drive_letter = resolve_drive_letter(normalized)
    media = media_map.get(drive_letter)
    display_name = Path(normalized).name or normalized
    capability_snapshot = media.to_dict() if media else {}

    if media:
        if media.media_type.upper() == "SSD":
            warnings.append("SSD media remains best-effort at file level.")
        elif media.media_type.upper() == "HDD":
            warnings.append("Single-file sanitization on HDD media is still reported as file-level best effort.")
        if media.is_bitlocker_protected:
            warnings.append("The volume is encrypted. This reduces exposure but does not replace media sanitization.")
        if media.inventory_source is InventorySource.LOGICAL_VOLUME:
            warnings.append("The backing media type could not be verified because the app is running in limited inventory mode.")

    steps = [
        PlanStep(OperationStage.ANALYSIS, "Preflight", "Validate the path, media mapping, ADS and reparse-point status."),
        PlanStep(OperationStage.SANITIZE, "File workflow", "Overwrite the file, verify the zero pass and randomize residual content."),
        PlanStep(OperationStage.VERIFY, "Removal", "Truncate and unlink the target while verifying the final state."),
        PlanStep(OperationStage.REPORT, "Audit", "Write JSONL, CSV, HTML and PDF reports."),
    ]

    return ExecutionPlan(
        plan_id=_plan_id("file", normalized),
        mode=OperationMode.FILE_SANITIZE,
        target_kind=TargetKind.FILE,
        target=normalized,
        display_name=display_name,
        dry_run=dry_run,
        assurance_target=assurance_target,
        method_name=method_name,
        executable=executable or dry_run,
        requires_admin=False,
        requires_offline=False,
        rationale=rationale,
        restrictions=restrictions,
        warnings=warnings,
        steps=steps,
        capability_snapshot=capability_snapshot,
    )


def create_drive_plan(capabilities: MediaCapabilities, dry_run: bool) -> ExecutionPlan:
    """Create a device-sanitization plan for one disk."""

    restrictions: list[str] = []
    warnings: list[str] = list(capabilities.notes)
    executable = True
    requires_offline = False
    requires_admin = True
    assurance_target = AssuranceLevel.UNSUPPORTED
    method_name = "Inventory only"
    rationale = "The plan is reduced to the highest honest assurance level available for the selected target."

    media = capabilities.media_type.upper()
    bus = capabilities.bus_type.upper()
    target = str(capabilities.disk_number)

    if not capabilities.supports_direct_device_ops:
        executable = False
        requires_admin = True
        method_name = "Administrator restart required"
        target = capabilities.drive_letters[0] if capabilities.drive_letters else capabilities.friendly_name
        restrictions.append("This entry was discovered in limited logical-volume mode and cannot be sanitized as a device.")
        restrictions.append("Restart the application as administrator to enumerate physical disks.")
        warnings.append("Logical-volume inventory is available for visibility only.")
    elif capabilities.is_system or capabilities.is_boot:
        executable = False
        requires_offline = True
        restrictions.append("System and boot media require an offline or WinPE workflow.")

    if capabilities.is_read_only:
        executable = False
        restrictions.append("The selected drive is marked as read-only.")

    if capabilities.is_removable or bus in {"USB", "SD"}:
        executable = False
        assurance_target = AssuranceLevel.DESTROY_REQUIRED
        method_name = "Manual destruction / dedicated appliance"
        rationale = "Removable and USB media cannot be treated as reliable purge targets from the standard Windows stack."
        warnings.append("Physical destruction or a dedicated sanitization appliance is recommended for this media type.")
    elif media == "SSD" and bus == "NVME":
        assurance_target = AssuranceLevel.DEVICE_PURGE
        method_name = "IOCTL_STORAGE_REINITIALIZE_MEDIA (NVMe sanitize)"
        rationale = (
            "NVMe media can attempt device sanitize through the Windows storage "
            "stack, but the result must still reflect the actual driver response."
        )
    elif media == "SSD" and bus in {"SATA", "ATA", "RAID"}:
        executable = False
        requires_offline = True
        assurance_target = AssuranceLevel.DEVICE_PURGE
        method_name = "ATA sanitize via offline runner"
        rationale = "SATA SSD media requires an offline workflow instead of a misleading online success state."
    elif media == "HDD":
        assurance_target = AssuranceLevel.DEVICE_CLEAR
        method_name = "IOCTL_STORAGE_REINITIALIZE_MEDIA where supported"
        rationale = "Rotational media targets Device Clear if the storage stack accepts the request."
    elif capabilities.supports_direct_device_ops:
        restrictions.append("The current bus or media type does not expose a trustworthy device-sanitize path.")

    if capabilities.is_bitlocker_protected:
        warnings.append("BitLocker is active. This improves the risk profile but does not replace media sanitization.")

    steps = [
        PlanStep(OperationStage.ANALYSIS, "Inventory", "Evaluate the drive topology, media class and Windows restrictions."),
        PlanStep(OperationStage.LOCK, "Volume lock", "Lock and dismount related volumes before device operations."),
        PlanStep(OperationStage.SANITIZE, "Device sanitize", method_name),
        PlanStep(OperationStage.VERIFY, "Completion", "Interpret the driver result and apply the honest assurance downgrade if needed."),
        PlanStep(OperationStage.REPORT, "Audit", "Write JSONL, CSV, HTML and PDF reports."),
    ]

    return ExecutionPlan(
        plan_id=_plan_id("drive", target),
        mode=OperationMode.DRIVE_SANITIZE,
        target_kind=TargetKind.DRIVE,
        target=target,
        display_name=capabilities.short_label,
        dry_run=dry_run,
        assurance_target=assurance_target,
        method_name=method_name,
        executable=executable or dry_run,
        requires_admin=requires_admin,
        requires_offline=requires_offline,
        rationale=rationale,
        restrictions=restrictions,
        warnings=warnings,
        steps=steps,
        capability_snapshot=capabilities.to_dict(),
    )
