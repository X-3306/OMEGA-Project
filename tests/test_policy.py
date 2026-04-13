from omega_protocol.models import AssuranceLevel, MediaCapabilities
from omega_protocol.policy import create_drive_plan, create_file_plan


def test_file_plan_for_ssd_is_best_effort(tmp_path):
    target = tmp_path / "secret.bin"
    target.write_bytes(b"abc")
    disk = MediaCapabilities(
        disk_number=0,
        friendly_name="UnitTest SSD",
        bus_type="NVMe",
        media_type="SSD",
        drive_letters=[target.drive.replace(":\\", "")],
    )

    plan = create_file_plan(str(target), dry_run=False, media_map={target.drive[0].upper(): disk})

    assert plan.assurance_target is AssuranceLevel.BEST_EFFORT_FILE_SANITIZE
    assert any("SSD" in warning for warning in plan.warnings)


def test_drive_plan_for_usb_requires_destroy():
    disk = MediaCapabilities(
        disk_number=4,
        friendly_name="USB stick",
        bus_type="USB",
        media_type="SSD",
        is_removable=True,
    )

    plan = create_drive_plan(disk, dry_run=False)

    assert plan.assurance_target is AssuranceLevel.DESTROY_REQUIRED
    assert plan.executable is False
