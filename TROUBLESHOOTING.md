# Troubleshooting

## `Get-Disk` returns `Access denied`

- Restart the application as administrator.
- In a restricted environment, file preflight still works, but drive inventory may fall back to a limited logical-volume view.

## `omega_native.dll not found`

- The application falls back to the Python implementation.
- For large files and device operations, this may reduce performance or block selected workflows.

## Drive sanitization requires offline mode

- This is expected for the system disk and for many SATA or ATA scenarios.
- Use `omega_offline.py` from WinPE or a service session.

## PyInstaller does not include reports or help assets

- Build only through `OMEGA_BETA.spec`.
- Confirm that `omega_protocol/report_templates` and `omega_protocol/help` are included in `datas`.

## The UI feels stuck

- Preflight and execution run asynchronously, but the first inventory refresh may still take a moment.
- If the UI freezes again, check whether a local change reintroduced blocking I/O into [omega_protocol/ui/app.py](omega_protocol/ui/app.py).

## PowerShell blocks `Activate.ps1`

- Use the direct interpreter path instead of activating the environment:

```powershell
.\.venv\Scripts\python.exe OMEGA_BETA.py
```

- Or use the helper launcher:

```powershell
.\Run-OMEGA-Source.cmd
```
