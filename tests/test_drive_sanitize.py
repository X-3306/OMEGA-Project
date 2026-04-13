from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from omega_protocol.engines import drive_sanitize as drive_sanitize_module
from omega_protocol.engines.drive_sanitize import DriveSanitizer
from omega_protocol.models import AssuranceLevel, ExecutionPlan, OperationMode, RetryPolicy, TargetKind


class StubNativeBridge:
    def __init__(self, native_ok: bool = True, message: str = "native ok") -> None:
        self.state = SimpleNamespace(available=native_ok, message=message)
        self.native_ok = native_ok
        self.message = message

    def reinitialize_media(self, _disk_number: int, _method: int, _timeout: int) -> tuple[bool, str]:
        return self.native_ok, self.message


def _drive_plan(**kwargs) -> ExecutionPlan:
    base: dict[str, Any] = {
        "plan_id": "drive-1",
        "mode": OperationMode.DRIVE_SANITIZE,
        "target_kind": TargetKind.DRIVE,
        "target": "1",
        "display_name": "Disk 1",
        "dry_run": False,
        "assurance_target": AssuranceLevel.DEVICE_PURGE,
        "method_name": "IOCTL_STORAGE_REINITIALIZE_MEDIA (NVMe sanitize)",
        "executable": True,
        "requires_admin": True,
        "requires_offline": False,
        "rationale": "test",
        "capability_snapshot": {"drive_letters": ["E"]},
    }
    base.update(kwargs)
    return ExecutionPlan(
        plan_id=base["plan_id"],
        mode=base["mode"],
        target_kind=base["target_kind"],
        target=base["target"],
        display_name=base["display_name"],
        dry_run=base["dry_run"],
        assurance_target=base["assurance_target"],
        method_name=base["method_name"],
        executable=base["executable"],
        requires_admin=base["requires_admin"],
        requires_offline=base["requires_offline"],
        rationale=base["rationale"],
        capability_snapshot=base["capability_snapshot"],
    )


def test_drive_sanitize_blocks_without_admin(monkeypatch):
    monkeypatch.setattr(drive_sanitize_module, "is_windows_admin", lambda: False)
    sanitizer = DriveSanitizer(StubNativeBridge())

    result = sanitizer.execute(_drive_plan(), lambda *_args: None)

    assert result.success is False
    assert "administrator" in result.detail.lower()


def test_drive_sanitize_retries_transient_lock_error(monkeypatch):
    attempts = {"count": 0}
    sleep_calls: list[float] = []
    unlock_calls: list[str] = []

    def flaky_lock(_drive_letter: str) -> None:
        attempts["count"] += 1
        if attempts["count"] == 1:
            error = OSError("busy")
            error.winerror = 32
            raise error

    monkeypatch.setattr(drive_sanitize_module, "is_windows_admin", lambda: True)
    sanitizer = DriveSanitizer(
        StubNativeBridge(native_ok=True),
        retry_policy=RetryPolicy(max_attempts=3, base_delay_seconds=0.01, backoff_multiplier=2.0),
        sleep_fn=sleep_calls.append,
        lock_fn=flaky_lock,
        unlock_fn=unlock_calls.append,
    )

    result = sanitizer.execute(_drive_plan(), lambda *_args: None)

    assert result.success is True
    assert attempts["count"] == 2
    assert sleep_calls == [0.01]
    assert unlock_calls == ["E"]


def test_drive_sanitize_requires_offline_runner(monkeypatch):
    monkeypatch.setattr(drive_sanitize_module, "is_windows_admin", lambda: True)
    sanitizer = DriveSanitizer(StubNativeBridge())

    result = sanitizer.execute(
        _drive_plan(executable=True, requires_offline=True),
        lambda *_args: None,
    )

    assert result.success is False
    assert "offline" in result.summary.lower() or "offline" in result.detail.lower()
