"""Core domain models for OMEGA Protocol."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field, is_dataclass
from datetime import datetime
from enum import Enum, StrEnum
from typing import Any


class OperationMode(StrEnum):
    """Supported high-level operation modes."""

    FILE_SANITIZE = "file_sanitize"
    DRIVE_SANITIZE = "drive_sanitize"


class TargetKind(StrEnum):
    """Describes whether a target is a file or a drive."""

    FILE = "file"
    DRIVE = "drive"


class AssuranceLevel(StrEnum):
    """User-facing assurance levels."""

    LOGICAL_DELETE = "Logical Delete"
    BEST_EFFORT_FILE_SANITIZE = "Best-Effort File Sanitize"
    DEVICE_CLEAR = "Device Clear"
    DEVICE_PURGE = "Device Purge"
    DESTROY_REQUIRED = "Destroy Required"
    UNSUPPORTED = "Unsupported"


class OperationStage(StrEnum):
    """Execution stages used in reports and UI."""

    ANALYSIS = "Analysis"
    LOCK = "Lock"
    SANITIZE = "Sanitize"
    VERIFY = "Verification"
    REPORT = "Report"


class AppPhase(StrEnum):
    """High-level UI/application states."""

    IDLE = "idle"
    PREFLIGHT = "preflight"
    RUNNING = "running"
    COMPLETE = "complete"
    ERROR = "error"


class InventorySource(StrEnum):
    """How the application obtained a drive inventory entry."""

    PHYSICAL_DISK = "physical_disk"
    LOGICAL_VOLUME = "logical_volume"


@dataclass(slots=True)
class PlanStep:
    """Single step shown in a preflight plan."""

    stage: OperationStage
    title: str
    detail: str
    required: bool = True


@dataclass(slots=True)
class MediaCapabilities:
    """Normalized view of one Windows device or fallback volume."""

    disk_number: int
    friendly_name: str
    bus_type: str
    media_type: str
    partition_style: str = ""
    health_status: str = ""
    operational_status: str = ""
    is_boot: bool = False
    is_system: bool = False
    is_read_only: bool = False
    is_offline: bool = False
    is_removable: bool = False
    size_bytes: int = 0
    partitions: list[dict[str, Any]] = field(default_factory=list)
    drive_letters: list[str] = field(default_factory=list)
    supports_reinitialize_media: bool | None = None
    supports_block_erase: bool | None = None
    supports_crypto_erase: bool | None = None
    is_bitlocker_protected: bool = False
    notes: list[str] = field(default_factory=list)
    inventory_source: InventorySource = InventorySource.PHYSICAL_DISK
    supports_direct_device_ops: bool = True

    @property
    def short_label(self) -> str:
        """Return a compact one-line label for UI lists."""

        if self.inventory_source is InventorySource.LOGICAL_VOLUME and self.drive_letters:
            return f"Volume {self.drive_letters[0]}:"
        return f"Disk {self.disk_number} | {self.bus_type or 'Unknown'} | {self.media_type or 'Unknown'}"

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a plain dictionary."""

        return to_serializable(self)


@dataclass(slots=True)
class InventorySnapshot:
    """Cached inventory of disks at a given point in time."""

    generated_at: str
    from_cache: bool
    disks: list[MediaCapabilities]
    warning: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a plain dictionary."""

        return to_serializable(self)


@dataclass(slots=True)
class ExecutionPlan:
    """Sanitization plan for a single target."""

    plan_id: str
    mode: OperationMode
    target_kind: TargetKind
    target: str
    display_name: str
    dry_run: bool
    assurance_target: AssuranceLevel
    method_name: str
    executable: bool
    requires_admin: bool
    requires_offline: bool
    rationale: str
    restrictions: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    steps: list[PlanStep] = field(default_factory=list)
    capability_snapshot: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a plain dictionary."""

        return to_serializable(self)


@dataclass(slots=True)
class PreflightResult:
    """Full preflight response for one user action."""

    request_id: str
    generated_at: str
    mode: OperationMode
    dry_run: bool
    plans: list[ExecutionPlan]
    inventory: InventorySnapshot | None
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a plain dictionary."""

        return to_serializable(self)


@dataclass(slots=True)
class AuditRecord:
    """Single low-level audit record emitted during execution."""

    timestamp: str
    target: str
    mode: str
    stage: str
    status: str
    detail: str


@dataclass(slots=True)
class ExecutionResult:
    """Result of executing one plan."""

    plan_id: str
    target: str
    display_name: str
    mode: OperationMode
    success: bool
    summary: str
    detail: str
    assurance_achieved: AssuranceLevel
    method_name: str
    started_at: str
    finished_at: str
    duration_ms: int
    warnings: list[str] = field(default_factory=list)
    artifacts: dict[str, str] = field(default_factory=dict)
    stage_log: list[AuditRecord] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a plain dictionary."""

        return to_serializable(self)


@dataclass(slots=True)
class SessionBundle:
    """Complete execution bundle with reports and results."""

    session_id: str
    generated_at: str
    mode: OperationMode
    dry_run: bool
    plans: list[ExecutionPlan]
    results: list[ExecutionResult]
    report_paths: dict[str, str]
    native_bridge_state: str

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a plain dictionary."""

        return to_serializable(self)


@dataclass(slots=True)
class RetryPolicy:
    """Retry policy for transient storage operations."""

    max_attempts: int = 3
    base_delay_seconds: float = 0.25
    backoff_multiplier: float = 2.0


@dataclass(slots=True)
class AppState:
    """High-level application state used by the GUI."""

    phase: AppPhase = AppPhase.IDLE
    mode: OperationMode = OperationMode.FILE_SANITIZE
    dry_run: bool = False
    progress: float = 0.0
    status_text: str = ""
    selected_files: tuple[str, ...] = ()
    selected_disks: tuple[int, ...] = ()
    latest_report_paths: dict[str, str] = field(default_factory=dict)


def now_iso() -> str:
    """Return a timezone-aware ISO timestamp."""

    return datetime.now().astimezone().isoformat(timespec="seconds")


def to_serializable(value: Any) -> Any:
    """Convert domain objects into JSON-friendly primitives."""

    if isinstance(value, Enum):
        return value.value
    if isinstance(value, datetime):
        return value.astimezone().isoformat(timespec="seconds")
    if is_dataclass(value) and not isinstance(value, type):
        return {key: to_serializable(item) for key, item in asdict(value).items()}
    if isinstance(value, dict):
        return {str(key): to_serializable(item) for key, item in value.items()}
    if isinstance(value, list):
        return [to_serializable(item) for item in value]
    if isinstance(value, tuple):
        return [to_serializable(item) for item in value]
    return value
