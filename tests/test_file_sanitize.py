from pathlib import Path

from omega_protocol.engines.file_sanitize import FileSanitizer
from omega_protocol.models import AssuranceLevel, ExecutionPlan, OperationMode, TargetKind
from omega_protocol.native_bridge import NativeBridge


def test_python_file_sanitize_removes_file(tmp_path):
    target = tmp_path / "wipe-me.bin"
    target.write_bytes(b"classified")
    plan = ExecutionPlan(
        plan_id="file-test",
        mode=OperationMode.FILE_SANITIZE,
        target_kind=TargetKind.FILE,
        target=str(target),
        display_name=target.name,
        dry_run=False,
        assurance_target=AssuranceLevel.BEST_EFFORT_FILE_SANITIZE,
        method_name="test",
        executable=True,
        requires_admin=False,
        requires_offline=False,
        rationale="test",
    )

    sanitizer = FileSanitizer(NativeBridge())
    result = sanitizer.execute(plan, lambda *_args: None)

    assert result.success is True
    assert not Path(target).exists()
