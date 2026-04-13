"""Background workers used by the Qt frontend."""

from __future__ import annotations

from PySide6.QtCore import QObject, QRunnable, Signal

from omega_protocol.events import PreflightReady, SessionFailed
from omega_protocol.models import OperationMode, PreflightResult


class WorkerSignals(QObject):
    """Signal container for worker threads."""

    event_emitted = Signal(object)


class PreflightWorker(QRunnable):
    """Compute preflight results without blocking the UI thread."""

    def __init__(
        self,
        orchestrator,
        request_token: int,
        mode: OperationMode,
        targets: list[str],
        dry_run: bool,
        force_inventory_refresh: bool,
    ) -> None:
        super().__init__()
        self.orchestrator = orchestrator
        self.request_token = request_token
        self.mode = mode
        self.targets = list(targets)
        self.dry_run = dry_run
        self.force_inventory_refresh = force_inventory_refresh
        self.signals = WorkerSignals()

    def run(self) -> None:
        try:
            result = self.orchestrator.build_preflight(
                mode=self.mode,
                targets=self.targets,
                dry_run=self.dry_run,
                force_inventory_refresh=self.force_inventory_refresh,
            )
            self.signals.event_emitted.emit(PreflightReady(request_token=self.request_token, result=result))
        except Exception as exc:
            fallback = PreflightResult(
                request_id=f"preflight-error-{self.request_token}",
                generated_at="",
                mode=self.mode,
                dry_run=self.dry_run,
                plans=[],
                inventory=None,
                warnings=[],
                errors=[str(exc)],
            )
            self.signals.event_emitted.emit(PreflightReady(request_token=self.request_token, result=fallback))


class SessionWorker(QRunnable):
    """Execute a sanitization session on a worker thread."""

    def __init__(
        self,
        orchestrator,
        mode: OperationMode,
        targets: list[str],
        dry_run: bool,
    ) -> None:
        super().__init__()
        self.orchestrator = orchestrator
        self.mode = mode
        self.targets = list(targets)
        self.dry_run = dry_run
        self.signals = WorkerSignals()

    def run(self) -> None:
        try:
            self.orchestrator.execute(
                mode=self.mode,
                targets=self.targets,
                dry_run=self.dry_run,
                event_callback=self.signals.event_emitted.emit,
            )
        except Exception as exc:
            self.signals.event_emitted.emit(SessionFailed(message=str(exc)))
