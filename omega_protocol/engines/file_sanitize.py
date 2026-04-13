"""File sanitization engine."""

from __future__ import annotations

import os
import secrets
import time
from collections.abc import Callable
from pathlib import Path

from omega_protocol.models import AssuranceLevel, AuditRecord, ExecutionPlan, ExecutionResult, OperationStage, now_iso
from omega_protocol.native_bridge import NativeBridge
from omega_protocol.settings import FILE_CHUNK_SIZE
from omega_protocol.system import delete_path_windows

LogCallback = Callable[[ExecutionPlan, str, str, str], None]


class FileSanitizer:
    """Executes file-level sanitization plans."""

    def __init__(self, native_bridge: NativeBridge) -> None:
        self.native_bridge = native_bridge

    def execute(self, plan: ExecutionPlan, emit: LogCallback) -> ExecutionResult:
        """Execute one file sanitization plan."""

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

        log(OperationStage.ANALYSIS, "ok", "Preflight completed.")
        if plan.dry_run:
            log(OperationStage.REPORT, "ok", "Dry run completed without modifying data.")
            finished = time.time()
            return ExecutionResult(
                plan_id=plan.plan_id,
                target=plan.target,
                display_name=plan.display_name,
                mode=plan.mode,
                success=True,
                summary="Dry run completed.",
                detail="The plan was validated without changing user data.",
                assurance_achieved=AssuranceLevel.LOGICAL_DELETE,
                method_name=f"Dry run | {plan.method_name}",
                started_at=started_iso,
                finished_at=now_iso(),
                duration_ms=int((finished - started) * 1000),
                warnings=warnings,
                stage_log=audit,
            )

        if not plan.executable:
            log(OperationStage.ANALYSIS, "blocked", "The plan was blocked by preflight policy.")
            finished = time.time()
            return ExecutionResult(
                plan_id=plan.plan_id,
                target=plan.target,
                display_name=plan.display_name,
                mode=plan.mode,
                success=False,
                summary="The file does not qualify for sanitization.",
                detail="; ".join(plan.restrictions) or "No safe execution path is available.",
                assurance_achieved=AssuranceLevel.UNSUPPORTED,
                method_name=plan.method_name,
                started_at=started_iso,
                finished_at=now_iso(),
                duration_ms=int((finished - started) * 1000),
                warnings=warnings + plan.restrictions,
                stage_log=audit,
            )

        native_ok, native_message = self.native_bridge.sanitize_file(plan.target, False)
        if native_ok:
            log(OperationStage.SANITIZE, "ok", native_message)
            log(OperationStage.VERIFY, "ok", "The native backend reported success.")
        else:
            if self.native_bridge.state.available:
                warnings.append(native_message)
            else:
                warnings.append("The native backend is unavailable. The Python fallback workflow was used instead.")
            self._python_overwrite(plan.target, log)

        log(OperationStage.REPORT, "ok", "The result is ready for reporting.")
        finished = time.time()
        return ExecutionResult(
            plan_id=plan.plan_id,
            target=plan.target,
            display_name=plan.display_name,
            mode=plan.mode,
            success=True,
            summary="File sanitization completed.",
            detail="The file was overwritten and removed without overstating SSD assurance.",
            assurance_achieved=AssuranceLevel.BEST_EFFORT_FILE_SANITIZE,
            method_name=plan.method_name,
            started_at=started_iso,
            finished_at=now_iso(),
            duration_ms=int((finished - started) * 1000),
            warnings=warnings,
            stage_log=audit,
        )

    def _python_overwrite(self, path: str, log: Callable[[OperationStage, str, str], None]) -> None:
        """Fallback file sanitizer implemented in pure Python."""

        size = os.path.getsize(path)
        file_path = Path(path)
        is_ads = ":" in file_path.name

        with open(path, "r+b", buffering=0) as handle:
            handle.seek(0)
            remaining = size
            while remaining > 0:
                size_to_write = min(FILE_CHUNK_SIZE, remaining)
                handle.write(b"\x00" * size_to_write)
                remaining -= size_to_write
            handle.flush()
            os.fsync(handle.fileno())
            log(OperationStage.SANITIZE, "ok", "Zero-overwrite pass completed.")

            handle.seek(0)
            while True:
                block = handle.read(FILE_CHUNK_SIZE)
                if not block:
                    break
                if any(byte != 0 for byte in block):
                    raise RuntimeError("Zero-overwrite verification failed.")
            log(OperationStage.VERIFY, "ok", "Zero-overwrite verification completed.")

            handle.seek(0)
            remaining = size
            while remaining > 0:
                size_to_write = min(FILE_CHUNK_SIZE, remaining)
                handle.write(secrets.token_bytes(size_to_write))
                remaining -= size_to_write
            handle.flush()
            os.fsync(handle.fileno())
            log(OperationStage.SANITIZE, "ok", "Random-overwrite pass completed.")

        current_path = path
        if not is_ads:
            renamed = file_path.with_name(f".omega-{secrets.token_hex(8)}.bin")
            os.replace(path, renamed)
            current_path = str(renamed)
            log(OperationStage.SANITIZE, "ok", f"The file was renamed to {renamed.name}.")

            with open(current_path, "r+b", buffering=0) as handle:
                handle.truncate(0)
                handle.flush()
                os.fsync(handle.fileno())
            log(OperationStage.VERIFY, "ok", "The file was truncated to zero bytes.")

        delete_path_windows(current_path)
        if os.path.exists(current_path):
            raise RuntimeError("DeleteFileW returned without removing the final path.")
        log(OperationStage.VERIFY, "ok", "The file was unlinked.")
