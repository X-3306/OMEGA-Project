"""Execution service emitting typed events."""

from __future__ import annotations

from collections.abc import Callable

from omega_protocol.audit import ReportWriter
from omega_protocol.events import SessionCompleted, SessionLogEvent, SessionProgressEvent
from omega_protocol.models import AssuranceLevel, ExecutionPlan, ExecutionResult, OperationMode, SessionBundle, now_iso


class ExecutionService:
    """Executes plans and emits typed session events."""

    def __init__(
        self,
        file_sanitizer,
        drive_sanitizer,
        report_writer: ReportWriter,
        native_backend_state_getter: Callable[[], str],
    ) -> None:
        self.file_sanitizer = file_sanitizer
        self.drive_sanitizer = drive_sanitizer
        self.report_writer = report_writer
        self.native_backend_state_getter = native_backend_state_getter

    def execute(
        self,
        mode: OperationMode,
        plans: list[ExecutionPlan],
        dry_run: bool,
        event_callback: Callable[[object], None] | None = None,
    ) -> SessionBundle:
        """Execute all plans and write the final report bundle."""

        callback = event_callback or (lambda _event: None)
        results = []
        total = max(1, len(plans) * 5)
        current = 0

        for plan in plans:
            def emit(inner_plan, stage: str, status: str, detail: str) -> None:
                nonlocal current
                current += 1
                callback(SessionLogEvent(title=f"{inner_plan.display_name} | {stage}", status=status, detail=detail))
                callback(SessionProgressEvent(current=current, total=total))

            try:
                if mode is OperationMode.FILE_SANITIZE:
                    results.append(self.file_sanitizer.execute(plan, emit))
                else:
                    results.append(self.drive_sanitizer.execute(plan, emit))
            except Exception as exc:
                failure = self._build_failure_result(plan, str(exc))
                results.append(failure)
                callback(
                    SessionLogEvent(
                        title=f"{plan.display_name} | Failure",
                        status="error",
                        detail=str(exc),
                    ),
                )

        bundle = self.report_writer.write_session(
            mode=mode,
            dry_run=dry_run,
            plans=plans,
            results=results,
            native_bridge_state=self.native_backend_state_getter(),
        )
        callback(SessionProgressEvent(current=total, total=total))
        callback(SessionCompleted(bundle=bundle))
        return bundle

    def _build_failure_result(self, plan: ExecutionPlan, detail: str) -> ExecutionResult:
        """Convert an unexpected exception into a transparent failed result."""

        timestamp = now_iso()
        return ExecutionResult(
            plan_id=plan.plan_id,
            target=plan.target,
            display_name=plan.display_name,
            mode=plan.mode,
            success=False,
            summary="The plan failed during execution.",
            detail=detail,
            assurance_achieved=AssuranceLevel.UNSUPPORTED,
            method_name=plan.method_name,
            started_at=timestamp,
            finished_at=timestamp,
            duration_ms=0,
            warnings=list(plan.warnings) + list(plan.restrictions),
        )
