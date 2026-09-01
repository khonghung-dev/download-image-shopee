"""Spreadsheet-style single-column editor for Shopee URL input."""

from __future__ import annotations

from collections.abc import Iterable

from PySide6.QtCore import QAbstractTableModel, QEvent, QModelIndex, QTimer, Qt, Signal
from PySide6.QtGui import QKeyEvent, QKeySequence, QPainter
from PySide6.QtWidgets import (
    QAbstractItemDelegate,
    QAbstractItemView,
    QApplication,
    QStyleOptionViewItem,
    QStyledItemDelegate,
    QTableView,
    QWidget,
)


class UrlTableModel(QAbstractTableModel):
    """Lightweight editable URL rows with one structural trailing blank row."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._rows: list[str] = [""]

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self._rows)

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return 0 if parent.isValid() else 1

    def data(
        self,
        index: QModelIndex,
        role: int = Qt.ItemDataRole.DisplayRole,
    ) -> object | None:
        if not index.isValid() or index.column() != 0:
            return None
        if role in {
            Qt.ItemDataRole.DisplayRole,
            Qt.ItemDataRole.EditRole,
        }:
            return self._rows[index.row()]
        if role == Qt.ItemDataRole.TextAlignmentRole:
            return int(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
        return None

    def setData(
        self,
        index: QModelIndex,
        value: object,
        role: int = Qt.ItemDataRole.EditRole,
    ) -> bool:
        if (
            role != Qt.ItemDataRole.EditRole
            or not index.isValid()
            or index.column() != 0
        ):
            return False
        self._rows[index.row()] = str(value)
        self.dataChanged.emit(index, index, [role])
        if index.row() == len(self._rows) - 1 and self._rows[-1]:
            self._append_rows(1)
        return True

    def flags(self, index: QModelIndex) -> Qt.ItemFlag:
        if not index.isValid():
            return Qt.ItemFlag.NoItemFlags
        return (
            Qt.ItemFlag.ItemIsEnabled
            | Qt.ItemFlag.ItemIsSelectable
            | Qt.ItemFlag.ItemIsEditable
        )

    def headerData(
        self,
        section: int,
        orientation: Qt.Orientation,
        role: int = Qt.ItemDataRole.DisplayRole,
    ) -> object | None:
        if role != Qt.ItemDataRole.DisplayRole:
            return None
        if orientation == Qt.Orientation.Vertical:
            return str(section + 1)
        return "URL"

    def set_text(self, text: str) -> None:
        """Replace editor rows without trimming or validating URL values."""
        rows = str(text).replace("\r\n", "\n").replace("\r", "\n").split("\n")
        if not rows:
            rows = [""]
        if rows[-1] != "":
            rows.append("")
        self.beginResetModel()
        self._rows = rows
        self.endResetModel()

    def plain_text(self) -> str:
        """Return rows in the canonical parser's existing newline format."""
        rows = list(self._rows)
        if rows and rows[-1] == "":
            rows.pop()
        return "\n".join(rows)

    def paste(self, start_row: int, values: Iterable[str]) -> QModelIndex:
        """Write clipboard lines downward in order without altering content."""
        rows = list(values)
        if not rows:
            return self.index(max(0, start_row), 0)
        self.ensure_row(start_row + len(rows) - 1)
        for offset, value in enumerate(rows):
            index = self.index(start_row + offset, 0)
            self._rows[index.row()] = value
            self.dataChanged.emit(index, index, [Qt.ItemDataRole.EditRole])
        if self._rows[-1] != "":
            self._append_rows(1)
        return self.index(start_row + len(rows) - 1, 0)

    def clear_indexes(self, indexes: Iterable[QModelIndex]) -> None:
        for index in indexes:
            if index.isValid() and index.column() == 0:
                self.setData(index, "")

    def ensure_row(self, row: int) -> None:
        if row >= len(self._rows):
            self._append_rows(row - len(self._rows) + 1)

    def _append_rows(self, count: int) -> None:
        if count < 1:
            return
        first = len(self._rows)
        self.beginInsertRows(QModelIndex(), first, first + count - 1)
        self._rows.extend([""] * count)
        self.endInsertRows()


class _UrlItemDelegate(QStyledItemDelegate):
    def __init__(self, view: "UrlTableView") -> None:
        super().__init__(view)
        self._view = view

    def createEditor(
        self,
        parent: QWidget,
        option: QStyleOptionViewItem,
        index: QModelIndex,
    ) -> QWidget:
        editor = super().createEditor(parent, option, index)
        editor.setProperty("urlEditorRow", index.row())
        return editor

    def eventFilter(self, editor: QWidget, event: object) -> bool:
        if (
            isinstance(event, QKeyEvent)
            and event.type() == QEvent.Type.KeyPress
            and event.key() in {Qt.Key.Key_Return, Qt.Key.Key_Enter}
        ):
            row = int(editor.property("urlEditorRow"))
            self.commitData.emit(editor)
            self.closeEditor.emit(
                editor,
                QAbstractItemDelegate.EndEditHint.NoHint,
            )
            QTimer.singleShot(0, lambda: self._view.advance_after_edit(row))
            return True
        return super().eventFilter(editor, event)


class UrlTableView(QTableView):
    """Excel-like URL entry surface with predictable clipboard behavior."""

    textChanged = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._url_model = UrlTableModel(self)
        self._placeholder_text = ""
        self.setModel(self._url_model)
        self.setItemDelegate(_UrlItemDelegate(self))
        self.setObjectName("urlTable")
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectItems)
        self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.setEditTriggers(
            QAbstractItemView.EditTrigger.DoubleClicked
            | QAbstractItemView.EditTrigger.EditKeyPressed
        )
        self.setAlternatingRowColors(True)
        self.horizontalHeader().hide()
        self.horizontalHeader().setStretchLastSection(True)
        self.verticalHeader().setDefaultSectionSize(30)
        self.verticalHeader().setMinimumWidth(34)
        self._url_model.dataChanged.connect(self._on_content_changed)
        self._url_model.rowsInserted.connect(self._on_content_changed)
        self._url_model.modelReset.connect(self._on_content_changed)

    @property
    def url_model(self) -> UrlTableModel:
        return self._url_model

    def setPlainText(self, text: str) -> None:
        self._url_model.set_text(text)

    def toPlainText(self) -> str:
        return self._url_model.plain_text()

    def setPlaceholderText(self, text: str) -> None:
        self._placeholder_text = str(text)
        self.viewport().update()

    def placeholderText(self) -> str:
        return self._placeholder_text

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.matches(QKeySequence.StandardKey.SelectAll):
            self.selectAll()
            event.accept()
            return
        if event.matches(QKeySequence.StandardKey.Copy):
            self.copy_selection()
            event.accept()
            return
        if event.matches(QKeySequence.StandardKey.Paste):
            self.paste_clipboard()
            event.accept()
            return
        if event.key() == Qt.Key.Key_Delete:
            self._url_model.clear_indexes(self.selectedIndexes())
            event.accept()
            return
        if event.key() == Qt.Key.Key_F2:
            current = self.currentIndex()
            if current.isValid():
                self.edit(current)
            event.accept()
            return
        super().keyPressEvent(event)

    def copy_selection(self) -> None:
        indexes = sorted(
            (index for index in self.selectedIndexes() if index.column() == 0),
            key=lambda index: index.row(),
        )
        values = [
            str(index.data(Qt.ItemDataRole.DisplayRole) or "")
            for index in indexes
        ]
        if (
            indexes
            and indexes[-1].row() == self._url_model.rowCount() - 1
            and values[-1] == ""
        ):
            values.pop()
        QApplication.clipboard().setText("\n".join(values))

    def paste_clipboard(self) -> None:
        text = QApplication.clipboard().text()
        values = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
        if values and values[-1] == "" and text.endswith(("\n", "\r")):
            values.pop()
        current = self.currentIndex()
        start_row = current.row() if current.isValid() else 0
        final_index = self._url_model.paste(start_row, values)
        self.setCurrentIndex(final_index)
        self.scrollTo(final_index)

    def advance_after_edit(self, row: int) -> None:
        next_row = row + 1
        self._url_model.ensure_row(next_row)
        index = self._url_model.index(next_row, 0)
        self.setCurrentIndex(index)
        self.scrollTo(index)

    def paintEvent(self, event: object) -> None:
        super().paintEvent(event)
        if self.toPlainText() or not self._placeholder_text:
            return
        painter = QPainter(self.viewport())
        color = self.palette().placeholderText().color()
        painter.setPen(color)
        painter.drawText(
            self.viewport().rect().adjusted(44, 8, -8, -8),
            int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop),
            self._placeholder_text,
        )

    def _on_content_changed(self, *_args: object) -> None:
        self.textChanged.emit()
        self.viewport().update()
