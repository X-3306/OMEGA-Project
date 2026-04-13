"""Drive sanitization engine."""

from __future__ import annotations

import time
from collections.abc import Callable

from omega_protocol.errors import StorageLockPermanentError, StorageLockTransientError
from omega_protocol.low_level import (
    StorageSanitizeMethodBlockErase,
    StorageSanitizeMethodCryptoErase,
    lock_and_dismount_volume,
    reinitialize_media,
    unlock_volume,
)
from omega_protocol.models import (
    AssuranceLevel,
    AuditRecord,
    ExecutionPlan,
    ExecutionResult,
    OperationStage,
    RetryPolicy,
    now_iso,
)
from omega_protocol.native_bridge import NativeBridge
from omega_protocol.settings import DRIVE_SANITIZE_TIMEOUT_SECONDS
from omega_protocol.system import is_windows_admin

LogCallback = Callable[[ExecutionPlan, str, str, str], None]
SleepFn = Callable[[float], None]
LockFn = Callable[[str], None]
UnlockFn = Callable[[str], None]
ReinitializeFn = Callable[[int, int, int], None]


class DriveSanitizer:
    """Executes drive-level sanitization plans."""

    def __init__(
        self,
        native_bridge: NativeBridge,
        retry_policy: RetryPolicy | None = None,
        sleep_fn: SleepFn = time.sleep,
        lock_fn: LockFn = lock_and_dismount_volume,
        unlock_fn: UnlockFn = unlock_volume,
        reinitialize_fn: ReinitializeFn = reinitialize_media,
    ) -> None:
        self.native_bridge = native_bridge
        self.retry_policy = retry_policy or RetryPolicy()
        self.sleep_fn = sleep_fn
        self.lock_fn = lock_fn
        self.unlock_fn = unlock_fn
        self.reinitialize_fn = reinitialize_fn

    def execute(self, plan: ExecutionPlan, emit: LogCallback) -> ExecutionResult:
        """Execute one drive sanitization plan."""

        started = time.time()
        started_iso = now_iso()
        audit: list[AuditRecord] = []
        warnings = list(plan.warnings)

        def log(stage: OperationStage, status: str, detail: str) -> None:
            record = AuditRecord(
                timestamp=now_iso(),
                target=plan.target,
                mode=plan.mode.value,
                stage=stage.value,
                status=status,
                detail=detail,
            )
            audit.append(record)
            emit(plan, stage.value, status, detail)

        log(OperationStage.ANALYSIS, "ok", "The drive plan was created.")

        if plan.dry_run:
            log(OperationStage.REPORT, "ok", "Dry run completed without destructive device operations.")
            finished = time.time()
            return ExecutionResult(
                plan_id=plan.plan_id,
                target=plan.target,
                display_name=plan.display_name,
                mode=plan.mode,
                success=True,
                summary="Drive dry run completed.",
                detail="The method, lock sequence and restrictions were evaluated without invoking sanitize.",
                assurance_achieved=AssuranceLevel.LOGICAL_DELETE,
                method_name=f"Dry run | {plan.method_name}",
                started_at=started_iso,
                finished_at=now_iso(),
                duration_ms=int((finished - started) * 1000),
                warnings=warnings,
                stage_log=audit,
            )

        if not plan.executable:
            log(OperationStage.ANALYSIS, "blocked", "The drive plan is blocked by policy.")
            finished = time.time()
            return ExecutionResult(
                plan_id=plan.plan_id,
                target=plan.target,
                display_name=plan.display_name,
                mode=plan.mode,
                success=False,
                summary="Drive sanitization is blocked.",
                detail="; ".join(plan.restrictions) or "No safe device workflow is available.",
                assurance_achieved=AssuranceLevel.UNSUPPORTED,
                method_name=plan.method_name,
                started_at=started_iso,
                finished_at=now_iso(),
                duration_ms=int((finished - started) * 1000),
                warnings=warnings + plan.restrictions,
                stage_log=audit,
            )

        if plan.requires_admin and not is_windows_admin():
            log(OperationStage.ANALYSIS, "blocked", "Administrator rights are required for this operation.")
            finished = time.time()
            return ExecutionResult(
                plan_id=plan.plan_id,
                target=plan.target,
                display_name=plan.display_name,
                mode=plan.mode,
                success=False,
                summary="Administrator rights are required.",
                detail="Restart the application as administrator to lock volumes and call storage IOCTL operations.",
                assurance_achieved=AssuranceLevel.UNSUPPORTED,
                method_name=plan.method_name,
                started_at=started_iso,
                finished_at=now_iso(),
                duration_ms=int((finished - started) * 1000),
                warnings=warnings,
                stage_log=audit,
            )

        if plan.requires_offline:
            log(OperationStage.ANALYSIS, "blocked", "This workflow requires offline or WinPE execution.")
            finished = time.time()
            return ExecutionResult(
                plan_id=plan.plan_id,
                target=plan.target,
                display_name=plan.display_name,
                mode=plan.mode,
                success=False,
                summary="An offline runner is required.",
                detail="Run omega_offline.py from WinPE or from a maintenance session outside the active operating system.",
                assurance_achieved=AssuranceLevel.UNSUPPORTED,
                method_name=plan.method_name,
                started_at=started_iso,
                finished_at=now_iso(),
                duration_ms=int((finished - started) * 1000),
                warnings=warnings,
                stage_log=audit,
            )

        disk_number = int(plan.target)
        drive_letters = [str(letter).upper() for letter in plan.capability_snapshot.get("drive_letters", []) if letter]
        locked: list[str] = []

        try:
            for drive_letter in drive_letters:
                self._lock_with_retry(drive_letter)
                locked.append(drive_letter)
                log(OperationStage.LOCK, "ok", f"Volume {drive_letter}: was locked and dismounted.")

            sanitize_method = _select_sanitize_method(plan)
            native_ok, native_message = self.native_bridge.reinitialize_media(
                disk_number,
                sanitize_method,
                DRIVE_SANITIZE_TIMEOUT_SECONDS,
            )
            if native_ok:
                log(OperationStage.SANITIZE, "ok", native_message)
            else:
                if self.native_bridge.state.available:
                    warnings.append(native_message)
                else:
                    warnings.append("The native backend is unavailable. The direct WinAPI fallback was used instead.")
                self.reinitialize_fn(disk_number, sanitize_method, DRIVE_SANITIZE_TIMEOUT_SECONDS)
                log(OperationStage.SANITIZE, "ok", "IOCTL_STORAGE_REINITIALIZE_MEDIA was accepted by the storage driver.")

            log(OperationStage.VERIFY, "ok", "The storage driver reported success for the requested sanitize workflow.")
            success = True
            achieved = plan.assurance_target
            summary = "Drive sanitization completed."
            detail = "The sanitize request reached the storage stack. The report records the exact method and any resulting limits."
        except (StorageLockPermanentError, StorageLockTransientError) as exc:
            log(OperationStage.VERIFY, "error", str(exc))
            success = False
            achieved = AssuranceLevel.UNSUPPORTED
            summary = "Drive sanitization failed."
            detail = str(exc)
        except OSError as exc:
            log(OperationStage.VERIFY, "error", str(exc))
            success = False
            achieved = AssuranceLevel.UNSUPPORTED
            summary = "Drive sanitization failed."
            detail = str(exc)
        finally:
            for drive_letter in locked:
                try:
                    self.unlock_fn(drive_letter)
                except OSError:
                    warnings.append(
                        f"The application could not unlock volume {drive_letter}. "
                        "A remount or reboot may be required.",
                    )
            log(OperationStage.REPORT, "ok", "The session is ready for report generation.")

        finished = time.time()
        return ExecutionResult(
            plan_id=plan.plan_id,
            target=plan.target,
            display_name=plan.display_name,
            mode=plan.mode,
            success=success,
            summary=summary,
            detail=detail,
            assurance_achieved=achieved,
            method_name=plan.method_name,
            started_at=started_iso,
            finished_at=now_iso(),
            duration_ms=int((finished - started) * 1000),
            warnings=warnings,
            stage_log=audit,
        )

    def _lock_with_retry(self, drive_letter: str) -> None:
        """Retry transient locking errors with exponential backoff."""

        delay = self.retry_policy.base_delay_seconds
        last_error: OSError | None = None
        for attempt in range(1, self.retry_policy.max_attempts + 1):
            try:
                self.lock_fn(drive_letter)
                return
            except OSError as exc:
                last_error = exc
                if not _is_transient_storage_error(exc) or attempt == self.retry_policy.max_attempts:
                    break
                self.sleep_fn(delay)
                delay *= self.retry_policy.backoff_multiplier

        if last_error is None:
            raise StorageLockPermanentError(f"Could not lock volume {drive_letter}.")
        if _is_transient_storage_error(last_error):
            raise StorageLockTransientError(
                f"Could not lock volume {drive_letter} after {self.retry_policy.max_attempts} attempts: {last_error}",
            ) from last_error
        raise StorageLockPermanentError(f"Locking volume {drive_letter} failed: {last_error}") from last_error


def _is_transient_storage_error(error: OSError) -> bool:
    """Return True for lock errors that often disappear after retry."""

    code = getattr(error, "winerror", None) or getattr(error, "errno", None)
    return code in {5, 32, 33}


def _select_sanitize_method(plan: ExecutionPlan) -> int:
    """Choose the most appropriate sanitize method for the plan."""

    method_name = plan.method_name.lower()
    if "crypto" in method_name:
        return StorageSanitizeMethodCryptoErase
    return StorageSanitizeMethodBlockErase
