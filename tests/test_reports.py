from pathlib import Path

from omega_protocol.audit import ReportWriter
from omega_protocol.models import AssuranceLevel, ExecutionPlan, ExecutionResult, OperationMode, TargetKind


def test_report_writer_emits_all_artifacts(tmp_path):
    writer = ReportWriter(tmp_path)
    plan = ExecutionPlan(
        plan_id="p1",
        mode=OperationMode.FILE_SANITIZE,
        target_kind=TargetKind.FILE,
        target="C:\\sample.txt",
        display_name="sample.txt",
        dry_run=True,
        assurance_target=AssuranceLevel.BEST_EFFORT_FILE_SANITIZE,
        method_name="Dry-run",
        executable=True,
        requires_admin=False,
        requires_offline=False,
        rationale="test",
    )
    result = ExecutionResult(
        plan_id="p1",
        target="C:\\sample.txt",
        display_name="sample.txt",
        mode=OperationMode.FILE_SANITIZE,
        success=True,
        summary="Unicode output should remain readable.",
        detail="The report pipeline should preserve UTF-8 text.",
        assurance_achieved=AssuranceLevel.LOGICAL_DELETE,
        method_name="Dry-run",
        started_at="2026-04-10T12:00:00+02:00",
        finished_at="2026-04-10T12:00:01+02:00",
        duration_ms=1000,
    )

    bundle = writer.write_session(OperationMode.FILE_SANITIZE, True, [plan], [result], "fallback")

    for path in bundle.report_paths.values():
        assert Path(path).exists()

    html = Path(bundle.report_paths["html"]).read_text(encoding="utf-8")
    bundle_json = Path(tmp_path / bundle.session_id / "bundle.json").read_text(encoding="utf-8")

    assert "Unicode output should remain readable." in html
    assert "preserve UTF-8 text" in bundle_json
    assert writer.pdf_font_name != "Helvetica"
