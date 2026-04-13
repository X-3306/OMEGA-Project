"""Qt item models used by the PySide6 frontend."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QAbstractListModel, QModelIndex, QPersistentModelIndex, Qt

from omega_protocol.models import InventorySource, MediaCapabilities

EMPTY_MODEL_INDEX = QModelIndex()
ModelIndex = QModelIndex | QPersistentModelIndex


class FileListModel(QAbstractListModel):
    """List model storing selected file targets."""

    def __init__(self) -> None:
        super().__init__()
        self._paths: list[str] = []

    def rowCount(self, parent: ModelIndex = EMPTY_MODEL_INDEX) -> int:
        if parent.isValid():
            return 0
        return len(self._paths)

    def data(self, index: ModelIndex, role: int = int(Qt.ItemDataRole.DisplayRole)):
        if not index.isValid():
            return None
        path = self._paths[index.row()]
        if role == int(Qt.ItemDataRole.DisplayRole):
            return f"{Path(path).name}  |  {path}"
        if role == int(Qt.ItemDataRole.ToolTipRole):
            return path
        if role == int(Qt.ItemDataRole.UserRole):
            return path
        return None

    def add_paths(self, paths: list[str]) -> bool:
        """Append unique paths and return True when the model changed."""

        new_paths = [path for path in paths if path not in self._paths]
        if not new_paths:
            return False
        start = len(self._paths)
        end = start + len(new_paths) - 1
        self.beginInsertRows(QModelIndex(), start, end)
        self._paths.extend(new_paths)
        self.endInsertRows()
        return True

    def remove_rows(self, rows: list[int]) -> bool:
        """Remove rows from the model."""

        changed = False
        for row in sorted(set(rows), reverse=True):
            if 0 <= row < len(self._paths):
                self.beginRemoveRows(QModelIndex(), row, row)
                self._paths.pop(row)
                self.endRemoveRows()
                changed = True
        return changed

    def clear(self) -> None:
        """Reset the model to empty."""

        self.beginResetModel()
        self._paths = []
        self.endResetModel()

    def paths(self) -> list[str]:
        """Return the current file targets."""

        return list(self._paths)


class DriveListModel(QAbstractListModel):
    """Checkable list model storing known drives and user selection."""

    def __init__(self) -> None:
        super().__init__()
        self._drives: list[MediaCapabilities] = []
        self._selected: set[int] = set()

    def rowCount(self, parent: ModelIndex = EMPTY_MODEL_INDEX) -> int:
        if parent.isValid():
            return 0
        return len(self._drives)

    def data(self, index: ModelIndex, role: int = int(Qt.ItemDataRole.DisplayRole)):
        if not index.isValid():
            return None
        disk = self._drives[index.row()]
        if role == int(Qt.ItemDataRole.DisplayRole):
            letters = ", ".join(f"{letter}:" for letter in disk.drive_letters) or "no mounted letters"
            suffix = " | SYSTEM" if disk.is_system or disk.is_boot else ""
            if disk.inventory_source is InventorySource.LOGICAL_VOLUME:
                return f"Volume {letters} | {disk.friendly_name}{suffix}"
            return (
                f"Disk {disk.disk_number} | {disk.friendly_name} | "
                f"{disk.bus_type} | {disk.media_type} | {letters}{suffix}"
            )
        if role == int(Qt.ItemDataRole.ToolTipRole):
            notes = "\n".join(disk.notes) if disk.notes else "No additional notes."
            size_gb = disk.size_bytes / (1024**3) if disk.size_bytes else 0.0
            return f"{disk.short_label}\nSize: {size_gb:.1f} GB\n{notes}"
        if role == int(Qt.ItemDataRole.CheckStateRole):
            if not disk.supports_direct_device_ops:
                return Qt.CheckState.Unchecked
            return Qt.CheckState.Checked if disk.disk_number in self._selected else Qt.CheckState.Unchecked
        if role == int(Qt.ItemDataRole.UserRole):
            return disk.disk_number
        return None

    def flags(self, index: ModelIndex) -> Qt.ItemFlag:
        if not index.isValid():
            return Qt.ItemFlag.NoItemFlags
        disk = self._drives[index.row()]
        base_flags = Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable
        if disk.supports_direct_device_ops:
            return base_flags | Qt.ItemFlag.ItemIsUserCheckable
        return base_flags

    def setData(self, index: ModelIndex, value: object, role: int = int(Qt.ItemDataRole.EditRole)) -> bool:
        if role != int(Qt.ItemDataRole.CheckStateRole) or not index.isValid():
            return False
        disk = self._drives[index.row()]
        if not disk.supports_direct_device_ops:
            return False
        if value == Qt.CheckState.Checked:
            self._selected.add(disk.disk_number)
        else:
            self._selected.discard(disk.disk_number)
        self.dataChanged.emit(index, index, [int(Qt.ItemDataRole.CheckStateRole)])
        return True

    def set_drives(self, drives: list[MediaCapabilities]) -> None:
        """Replace the entire drive inventory while preserving valid selection."""

        valid_numbers = {disk.disk_number for disk in drives if disk.supports_direct_device_ops}
        self.beginResetModel()
        self._drives = list(drives)
        self._selected &= valid_numbers
        self.endResetModel()

    def clear_selection(self) -> None:
        """Clear all checked drives."""

        self._selected.clear()
        if self._drives:
            top_left = self.index(0, 0)
            bottom_right = self.index(len(self._drives) - 1, 0)
            self.dataChanged.emit(top_left, bottom_right, [int(Qt.ItemDataRole.CheckStateRole)])

    def selected_disks(self) -> list[int]:
        """Return the selected disk numbers."""

        return sorted(self._selected)
