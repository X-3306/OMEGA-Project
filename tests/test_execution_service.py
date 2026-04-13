from __future__ import annotations

from omega_protocol.events import SessionCompleted, SessionLogEvent, SessionProgressEvent
from omega_protocol.models import AssuranceLevel, ExecutionPlan, OperationMode, SessionBundle, TargetKind
from omega_protocol.services.execution import ExecutionService


class FailingFileSanitizer:
    def execute(self, _plan, _emit):
        raise RuntimeError("boom")


class UnusedDriveSanitizer:
    def execute(self, _plan, _emit):
        raise AssertionError("drive sanitizer should not be used in this test")


class StubReportWriter:
    def write_session(self, mode, dry_run, plans, results, native_bridge_state):
        return SessionBundle(
            session_id="bundle-1",
            generated_at="2026-04-11T11:00:00+02:00",
            mode=mode,
            dry_run=dry_run,
            plans=plans,
            results=results,
            report_paths={"jsonl": "session.jsonl"},
            native_bridge_state=native_bridge_state,
        )


def test_execution_service_converts_exceptions_into_failed_results():
    plan = ExecutionPlan(
        plan_id="p1",
        mode=OperationMode.FILE_SANITIZE,
        target_kind=TargetKind.FILE,
        target="C:\\boom.bin",
        display_name="boom.bin",
        dry_run=False,
        assurance_target=AssuranceLevel.BEST_EFFORT_FILE_SANITIZE,
        method_name="test",
        executable=True,
        requires_admin=False,
        requires_offline=False,
        rationale="test",
    )
    events: list[object] = []
    service = ExecutionService(
        file_sanitizer=FailingFileSanitizer(),
        drive_sanitizer=UnusedDriveSanitizer(),
        report_writer=StubReportWriter(),
        native_backend_state_getter=lambda: "fallback",
    )

    bundle = service.execute(OperationMode.FILE_SANITIZE, [plan], False, events.append)

    assert bundle.results[0].success is False
    assert bundle.results[0].assurance_achieved is AssuranceLevel.UNSUPPORTED
    assert any(isinstance(event, SessionLogEvent) and event.status == "error" for event in events)
    assert any(
        isinstance(event, SessionProgressEvent) and event.current == event.total
        for event in events
    )
    assert any(isinstance(event, SessionCompleted) for event in events)
