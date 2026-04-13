# Method Matrix

| Scenario | Method | Assurance Target | Status |
| --- | --- | --- | --- |
| Single file on HDD | Rename -> 0x00 -> verify -> random -> truncate -> unlink | Best-Effort File Sanitize | Supported |
| Single file on SSD/NVMe | Same file backend | Best-Effort File Sanitize | Supported with warning |
| NVMe data disk | `IOCTL_STORAGE_REINITIALIZE_MEDIA` | Device Purge | Conditionally supported |
| HDD data disk | `IOCTL_STORAGE_REINITIALIZE_MEDIA` | Device Clear | Conditionally supported |
| SATA SSD data disk | Offline runner / WinPE | Device Purge | Blocked online |
| System disk | Offline runner / WinPE | Depends on media | Blocked online |
| USB / removable | Conservative downgrade | Destroy Required / Unsupported | No purge promise |

## Notes

- `Best-Effort File Sanitize` is not equivalent to `Device Clear` or `Device Purge`.
- `Device Purge` is reported only after the device-level path succeeds.
- `BitLocker` improves the risk profile but does not replace media sanitization.
