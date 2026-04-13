"""Domain-specific exceptions for OMEGA Protocol."""

from __future__ import annotations


class OmegaError(RuntimeError):
    """Base class for domain-specific errors."""


class InventoryError(OmegaError):
    """Base class for inventory and PowerShell failures."""


class InventoryTimeoutError(InventoryError):
    """Raised when inventory collection exceeds the configured timeout."""


class InventoryAccessDeniedError(InventoryError):
    """Raised when Windows blocks access to disk inventory APIs."""


class InventoryParseError(InventoryError):
    """Raised when PowerShell returns invalid JSON."""


class InventoryUnsupportedError(InventoryError):
    """Raised when the current platform cannot provide inventory."""


class NativeBackendError(OmegaError):
    """Raised when the native backend is unavailable or fails to initialize."""


class StorageOperationError(OmegaError):
    """Base class for low-level storage errors."""


class StorageLockTransientError(StorageOperationError):
    """Raised for retryable volume locking failures."""


class StorageLockPermanentError(StorageOperationError):
    """Raised for non-retryable volume locking failures."""
