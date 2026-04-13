"""Top-level facade orchestrating services, engines and reports."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from omega_protocol import __version__
from omega_protocol.audit import ReportWriter
from omega_protocol.engines.drive_sanitize import DriveSanitizer
from omega_protocol.engines.file_sanitize import FileSanitizer
from omega_protocol.models import ExecutionPlan, InventorySnapshot, OperationMode, PreflightResult, SessionBundle
from omega_protocol.native_bridge import NativeBridge
from omega_protocol.services import ExecutionService, InventoryService, PlanService

EventCallback = Callable[[object], None]


class OmegaOrchestrator:
    """High-level facade used by the GUI and CLI entrypoints."""

    def __init__(
        self,
        report_root: Path | None = None,
        inventory_service: InventoryService | None = None,
        native_bridge: NativeBridge | None = None,
        file_sanitizer: FileSanitizer | None = None,
        drive_sanitizer: DriveSanitizer | None = None,
        report_writer: ReportWriter | None = None,
        plan_service: PlanService | None = None,
        execution_service: ExecutionService | None = None,
    ) -> None:
        self.report_root = report_root or (Path.cwd() / "reports")
        self.native_bridge = native_bridge or NativeBridge()
        self.inventory_service = inventory_service or InventoryService()
        self.file_sanitizer = file_sanitizer or FileSanitizer(self.native_bridge)
        self.drive_sanitizer = drive_sanitizer or DriveSanitizer(self.native_bridge)
        self.report_writer = report_writer or ReportWriter(self.report_root)
        self.plan_service = plan_service or PlanService(self.inventory_service)
        self.execution_service = execution_service or ExecutionService(
            file_sanitizer=self.file_sanitizer,
            drive_sanitizer=self.drive_sanitizer,
            report_writer=self.report_writer,
            native_backend_state_getter=lambda: self.native_bridge.state.message,
        )

    @property
    def version(self) -> str:
        """Return the current application version."""

        return __version__

    def inventory_snapshot(self, force_refresh: bool = False) -> InventorySnapshot:
        """Return a cached or fresh inventory snapshot."""

        return self.inventory_service.get_snapshot(force_refresh=force_refresh)

    def inventory_drives(self, force_refresh: bool = False):
        """Compatibility wrapper returning only the disk list."""

        return self.inventory_snapshot(force_refresh=force_refresh).disks

    def build_preflight(
        self,
        mode: OperationMode,
        targets: list[str],
        dry_run: bool,
        force_inventory_refresh: bool = False,
    ) -> PreflightResult:
        """Build a typed preflight result."""

        return self.plan_service.build_preflight(
            mode=mode,
            targets=targets,
            dry_run=dry_run,
            force_inventory_refresh=force_inventory_refresh,
        )

    def build_plans(
        self,
        mode: OperationMode,
        targets: list[str],
        dry_run: bool,
        force_inventory_refresh: bool = False,
    ) -> list[ExecutionPlan]:
        """Compatibility wrapper returning only the plans."""

        return self.build_preflight(
            mode=mode,
            targets=targets,
            dry_run=dry_run,
            force_inventory_refresh=force_inventory_refresh,
        ).plans

    def execute(
        self,
        mode: OperationMode,
        targets: list[str],
        dry_run: bool,
        event_callback: EventCallback | None = None,
        force_inventory_refresh: bool = False,
    ) -> SessionBundle:
        """Build plans, execute them and return the final bundle."""

        preflight = self.build_preflight(
            mode=mode,
            targets=targets,
            dry_run=dry_run,
            force_inventory_refresh=force_inventory_refresh,
        )
        bundle = self.execution_service.execute(
            mode=mode,
            plans=preflight.plans,
            dry_run=dry_run,
            event_callback=event_callback,
        )
        self.inventory_service.invalidate()
        return bundle
