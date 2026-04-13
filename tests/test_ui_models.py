from PySide6.QtCore import QModelIndex, Qt

from omega_protocol.models import MediaCapabilities
from omega_protocol.ui.list_models import DriveListModel, FileListModel


def test_file_list_model_add_remove_clear(qapp):
    model = FileListModel()

    assert model.add_paths(["C:\\alpha.txt", "C:\\beta.txt"]) is True
    assert model.add_paths(["C:\\alpha.txt"]) is False
    assert model.rowCount() == 2
    assert "alpha.txt" in model.data(model.index(0, 0), int(Qt.ItemDataRole.DisplayRole))

    assert model.remove_rows([0]) is True
    assert model.paths() == ["C:\\beta.txt"]

    model.clear()
    assert model.rowCount(QModelIndex()) == 0


def test_drive_list_model_tracks_selection(qapp):
    model = DriveListModel()
    drives = [
        MediaCapabilities(
            disk_number=1,
            friendly_name="Disk 1",
            bus_type="NVMe",
            media_type="SSD",
            drive_letters=["E"],
        ),
        MediaCapabilities(
            disk_number=2,
            friendly_name="Disk 2",
            bus_type="SATA",
            media_type="HDD",
            drive_letters=["F"],
        ),
    ]

    model.set_drives(drives)
    index = model.index(0, 0)
    assert model.setData(index, Qt.CheckState.Checked, int(Qt.ItemDataRole.CheckStateRole)) is True
    assert model.selected_disks() == [1]

    model.clear_selection()
    assert model.selected_disks() == []
