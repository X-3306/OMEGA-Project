from __future__ import annotations

from dataclasses import dataclass

from omega_protocol.models import (
    AssuranceLevel,
    ExecutionPlan,
    InventorySnapshot,
    OperationMode,
    PreflightResult,
    SessionBundle,
    TargetKind,
)
from omega_protocol.orchestrator import OmegaOrchestrator


@dataclass
class StubInventoryService:
    snapshot: InventorySnapshot
    invalidate_calls: int = 0

    def get_snapshot(self, force_refresh: bool = False) -> InventorySnapshot:
        return self.snapshot

    def invalidate(self) -> None:
        self.invalidate_calls += 1


@dataclass
class StubPlanService:
    preflight: PreflightResult
    calls: int = 0

    def build_preflight(self, **_kwargs) -> PreflightResult:
        self.calls += 1
        return self.preflight


@dataclass
class StubExecutionService:
    bundle: SessionBundle
    calls: int = 0

    def execute(self, **_kwargs) -> SessionBundle:
        self.calls += 1
        return self.bundle


class StubNativeBridge:
    class State:
        message = "fallback"

    state = State()


def test_orchestrator_uses_injected_services():
    plan = ExecutionPlan(
        plan_id="p1",
        mode=OperationMode.FILE_SANITIZE,
        target_kind=TargetKind.FILE,
        target="C:\\sample.txt",
        display_name="sample.txt",
        dry_run=True,
        assurance_target=AssuranceLevel.BEST_EFFORT_FILE_SANITIZE,
        method_name="Dry-run",
        executable=True,
        requires_admin=False,
        requires_offline=False,
        rationale="test",
    )
    snapshot = InventorySnapshot(generated_at="2026-04-11T10:00:00+02:00", from_cache=False, disks=[])
    preflight = PreflightResult(
        request_id="req-1",
        generated_at="2026-04-11T10:00:00+02:00",
        mode=OperationMode.FILE_SANITIZE,
        dry_run=True,
        plans=[plan],
        inventory=snapshot,
    )
    bundle = SessionBundle(
        session_id="session-1",
        generated_at="2026-04-11T10:00:01+02:00",
        mode=OperationMode.FILE_SANITIZE,
        dry_run=True,
        plans=[plan],
        results=[],
        report_paths={"html": "report.html"},
        native_bridge_state="fallback",
    )

    inventory_service = StubInventoryService(snapshot)
    plan_service = StubPlanService(preflight)
    execution_service = StubExecutionService(bundle)
    orchestrator = OmegaOrchestrator(
        inventory_service=inventory_service,
        plan_service=plan_service,
        execution_service=execution_service,
        native_bridge=StubNativeBridge(),
    )

    assert orchestrator.build_plans(OperationMode.FILE_SANITIZE, ["C:\\sample.txt"], True) == [plan]

    result = orchestrator.execute(OperationMode.FILE_SANITIZE, ["C:\\sample.txt"], True)

    assert result.session_id == "session-1"
    assert plan_service.calls == 2
    assert execution_service.calls == 1
    assert inventory_service.invalidate_calls == 1
