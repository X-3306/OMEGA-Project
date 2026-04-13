# Threat Model

## Goal

OMEGA Protocol is intended to reduce the recoverability of data after an intentional sanitization workflow, without making false claims of absolute security when the selected method cannot provide that level of assurance.

## Covered Scenarios

- Ordinary recovery after `delete` or `unlink`
- Logical recovery attempts against HDD file remnants
- Supported NVMe workflows where the driver accepts `IOCTL_STORAGE_REINITIALIZE_MEDIA`
- Operator mistakes caused by poor or unclear preflight information

## Out of Scope

- Laboratory NAND cell recovery after file-level overwrite on SSD media
- Malicious or defective firmware
- Cloud copies, backups, shadow copies, journals, pagefile, and hibernation data
- Firmware translation behavior inside low-cost USB storage devices

## Key Limits

- `SSD + single file` only qualifies as `Best-Effort File Sanitize`
- `SATA SSD` often requires offline or WinPE handling
- `USB / removable` media may end in `Destroy Required`
- The online system disk path is blocked

## Reporting Rule

If the application cannot prove a stronger sanitization outcome, the report must show the limitation instead of reporting a marketing-style success message.
