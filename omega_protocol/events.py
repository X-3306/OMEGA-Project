"""Typed UI and execution events."""

from __future__ import annotations

from dataclasses import dataclass, field

from omega_protocol.models import PreflightResult, SessionBundle, now_iso


@dataclass(slots=True)
class SessionEvent:
    """Base event emitted by the orchestrator and consumed by the UI."""

    timestamp: str = field(default_factory=now_iso)


@dataclass(slots=True)
class PreflightRequested(SessionEvent):
    """Signals that a preflight computation has been requested."""

    request_token: int = 0
    request_id: str = ""
    target_count: int = 0


@dataclass(slots=True)
class PreflightReady(SessionEvent):
    """Carries a completed preflight result."""

    request_token: int = 0
    result: PreflightResult | None = None


@dataclass(slots=True)
class SessionLogEvent(SessionEvent):
    """Single textual log line for the session feed."""

    title: str = ""
    status: str = "info"
    detail: str = ""


@dataclass(slots=True)
class SessionProgressEvent(SessionEvent):
    """Progress event emitted during execution."""

    current: int = 0
    total: int = 0


@dataclass(slots=True)
class SessionCompleted(SessionEvent):
    """Signals successful session completion."""

    bundle: SessionBundle | None = None


@dataclass(slots=True)
class SessionFailed(SessionEvent):
    """Signals failed session completion."""

    message: str = ""
