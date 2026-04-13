# Development Guide

## Setup

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -e .[dev,build]
```

## Common Commands

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_inventory_service.py tests\test_reports.py
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m mypy omega_protocol tests OMEGA_BETA.py omega_offline.py
.\.venv\Scripts\pyinstaller.exe --noconfirm OMEGA_BETA.spec
```

## Change Rules

- Do not add blocking I/O back to the UI thread.
- Do not use `Clear`, `Purge`, or `Destroy` labels for individual file workflows.
- If an action cannot be justified honestly online, the plan must block it.
- New warnings and errors must remain understandable for the operator.

## Local Validation

- Unit tests: `python -m pytest`
- Coverage: enabled by default through `pytest.ini`
- Packaging smoke test: `pyinstaller --noconfirm OMEGA_BETA.spec`
- Native backend build (optional):
  ```powershell
  cmake -S . -B build -A x64 -DCMAKE_BUILD_TYPE=Release
  cmake --build build --config Release
  copy build\Release\omega_native.dll omega_protocol\omega_native.dll
  ```
