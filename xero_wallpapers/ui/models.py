from urllib.parse import quote, urlparse

from PyQt6.QtCore import QAbstractListModel, QModelIndex, Qt

from ..sources.base import Item

LABELS = {
    "wallhaven": "Wallhaven",
    "4kwallpapers": "4K Wallpapers",
    "moewalls": "MoeWalls",
    "motionbgs": "MotionBGs",
}


def source_label(name: str) -> str:
    return LABELS.get(name, name)


def _allowed(url: str, schemes=("http", "https")) -> str:
    # The provider reads "blur\n"/"hero\n" prefixes and file: URLs, so source data must never smuggle them in.
    return url if "\n" not in url and urlparse(url).scheme.lower() in schemes else ""


def thumb_url(url: str) -> str:
    url = _allowed(url)
    return "image://thumb/" + quote(url, safe="") if url else ""


def hero_url(original: str, preview: str, thumb: str) -> str:
    slots = ["hero", *(_allowed(u) for u in (original, preview, thumb))]
    return "image://thumb/" + quote("\n".join(slots), safe="")


def fill_url(url: str, local: bool = False) -> str:
    if not _allowed(url, ("http", "https", "file") if local else ("http", "https")):
        return ""
    return "image://thumb/" + quote("blur\n" + url, safe="")


def cover_url(item: Item) -> str:
    original = item.download_url if item.kind == "static" else ""
    return hero_url(original, item.extra.get("preview", ""), item.thumb_url)


_ROLES = ("title", "thumb", "resolution", "source", "kind", "duration", "index", "author", "cover", "fill")


class WallpaperModel(QAbstractListModel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._items: list[Item] = []
        self._role_ids = {Qt.ItemDataRole.UserRole + 1 + i: name for i, name in enumerate(_ROLES)}
        self._title_role = Qt.ItemDataRole.UserRole + 1 + _ROLES.index("title")
        self._index_role = Qt.ItemDataRole.UserRole + 1 + _ROLES.index("index")

    def roleNames(self):
        return {k: v.encode() for k, v in self._role_ids.items()}

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self._items)

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid() or not 0 <= index.row() < len(self._items):
            return None
        item = self._items[index.row()]
        match self._role_ids.get(role):
            case "title":
                return item.title
            case "thumb":
                return thumb_url(item.thumb_url)
            case "resolution":
                return item.resolution()
            case "source":
                return source_label(item.source)
            case "kind":
                return item.kind
            case "duration":
                return item.duration
            case "index":
                return index.row()
            case "author":
                return item.author
            case "cover":
                return cover_url(item)
            case "fill":
                return fill_url(item.thumb_url)
        return None

    def set_items(self, items: list[Item]):
        self.beginResetModel()
        self._items = list(items)
        self.endResetModel()

    def append_items(self, items: list[Item]):
        if not items:
            return
        start = len(self._items)
        self.beginInsertRows(QModelIndex(), start, start + len(items) - 1)
        self._items.extend(items)
        self.endInsertRows()

    def remove(self, row: int):
        self.beginRemoveRows(QModelIndex(), row, row)
        del self._items[row]
        self.endRemoveRows()
        if row < len(self._items):
            self.dataChanged.emit(self.index(row, 0), self.index(len(self._items) - 1, 0), [self._index_role])

    def replace(self, row: int, item: Item):
        self._items[row] = item
        idx = self.index(row, 0)
        self.dataChanged.emit(idx, idx)

    def update_title(self, row: int, title: str):
        if not 0 <= row < len(self._items):
            return
        self._items[row].title = title
        idx = self.index(row, 0)
        self.dataChanged.emit(idx, idx, [self._title_role])

    def row_of(self, item: Item) -> int:
        return next((i for i, it in enumerate(self._items) if it is item), -1)

    def item(self, i: int) -> Item:
        return self._items[i]
