# API Contract

## `OmegaOrchestrator`

### `inventory_snapshot(force_refresh: bool = False) -> InventorySnapshot`

- Returns an inventory snapshot.
- Uses cached inventory unless `force_refresh=True`.

### `inventory_drives(force_refresh: bool = False) -> list[MediaCapabilities]`

- Compatibility wrapper that returns only the drive list.

### `build_preflight(mode, targets, dry_run, force_inventory_refresh=False) -> PreflightResult`

- Builds the full preflight object.
- For `file_sanitize`, inventory failures may be downgraded to warnings.
- For `drive_sanitize`, hard inventory failures are surfaced unless a safe fallback snapshot is available.

### `build_plans(mode, targets, dry_run, force_inventory_refresh=False) -> list[ExecutionPlan]`

- Compatibility wrapper that returns plans only.

### `execute(mode, targets, dry_run, event_callback=None, force_inventory_refresh=False) -> SessionBundle`

- Builds preflight.
- Executes the session through the execution service.
- Invalidates inventory cache after the session finishes.

## UI Events

- `PreflightRequested`
- `PreflightReady`
- `SessionLogEvent`
- `SessionProgressEvent`
- `SessionCompleted`
- `SessionFailed`

## Contract Guarantees

- The UI does not receive raw WinAPI failures as if they were successful results.
- Every plan includes an `assurance_target`.
- Every result includes an `assurance_achieved`.
- A final report bundle is generated even when the session ends with partial failure.
