from __future__ import annotations

import time
from pathlib import Path

from omega_protocol.events import SessionCompleted, SessionProgressEvent
from omega_protocol.models import (
    AssuranceLevel,
    ExecutionPlan,
    ExecutionResult,
    InventorySnapshot,
    MediaCapabilities,
    OperationMode,
    PreflightResult,
    SessionBundle,
    TargetKind,
)
from omega_protocol.ui.app import OmegaMainWindow


class FakeOrchestrator:
    version = "test"

    def __init__(self, delay: float = 0.0) -> None:
        self.delay = delay
        self.preflight_calls = 0
        self.execute_calls = 0

    def build_preflight(self, mode, targets, dry_run, force_inventory_refresh=False):
        self.preflight_calls += 1
        time.sleep(self.delay)
        inventory = InventorySnapshot(
            generated_at="2026-04-11T12:00:00+02:00",
            from_cache=not force_inventory_refresh,
            disks=[
                MediaCapabilities(
                    disk_number=3,
                    friendly_name="Disk 3",
                    bus_type="NVMe",
                    media_type="SSD",
                    drive_letters=["E"],
                ),
            ],
        )
        plans = [
            ExecutionPlan(
                plan_id="preflight-1",
                mode=mode,
                target_kind=TargetKind.FILE if mode is OperationMode.FILE_SANITIZE else TargetKind.DRIVE,
                target=targets[0] if targets else "3",
                display_name=Path(targets[0]).name if targets else "Disk 3",
                dry_run=dry_run,
                assurance_target=AssuranceLevel.BEST_EFFORT_FILE_SANITIZE
                if mode is OperationMode.FILE_SANITIZE
                else AssuranceLevel.DEVICE_PURGE,
                method_name="Dry-run" if dry_run else "Execute",
                executable=True,
                requires_admin=False,
                requires_offline=False,
                rationale="test",
            ),
        ] if targets or mode is OperationMode.DRIVE_SANITIZE else []
        return PreflightResult(
            request_id="qt-1",
            generated_at="2026-04-11T12:00:00+02:00",
            mode=mode,
            dry_run=dry_run,
            plans=plans,
            inventory=inventory,
        )

    def execute(self, mode, targets, dry_run, event_callback=None, force_inventory_refresh=False):
        self.execute_calls += 1
        result = ExecutionResult(
            plan_id="session-1",
            target=targets[0],
            display_name=Path(targets[0]).name,
            mode=mode,
            success=True,
            summary="ok",
            detail="detail",
            assurance_achieved=AssuranceLevel.LOGICAL_DELETE,
            method_name="Dry-run",
            started_at="2026-04-11T12:00:00+02:00",
            finished_at="2026-04-11T12:00:01+02:00",
            duration_ms=1000,
        )
        bundle = SessionBundle(
            session_id="bundle-qt",
            generated_at="2026-04-11T12:00:01+02:00",
            mode=mode,
            dry_run=dry_run,
            plans=[],
            results=[result],
            report_paths={"html": "session.html"},
            native_bridge_state="fallback",
        )
        if event_callback:
            event_callback(SessionProgressEvent(current=5, total=5))
            event_callback(SessionCompleted(bundle=bundle))
        return bundle


def _spin_until(qapp, predicate, timeout: float = 3.0) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        qapp.processEvents()
        if predicate():
            return
        time.sleep(0.01)
    raise AssertionError("Condition not met before timeout.")


def test_schedule_preflight_is_async(qapp):
    window = OmegaMainWindow(orchestrator=FakeOrchestrator(delay=0.2))
    try:
        start = time.perf_counter()
        window.schedule_preflight(force_inventory_refresh=True, immediate=True)
        elapsed = time.perf_counter() - start

        assert elapsed < 0.1
        _spin_until(qapp, lambda: "Planned targets:" in window.preflight_text.toPlainText())
    finally:
        window.close()


def test_session_completion_updates_report(qapp, tmp_path):
    target = tmp_path / "classified.bin"
    target.write_bytes(b"secret")

    window = OmegaMainWindow(orchestrator=FakeOrchestrator())
    try:
        window.file_model.add_paths([str(target)])
        window.start_execution()

        _spin_until(qapp, lambda: "bundle-qt" in window.report_text.toPlainText())

        assert window.progress_bar.value() == 100
        assert "session.html" in window.report_text.toPlainText()
    finally:
        window.close()
