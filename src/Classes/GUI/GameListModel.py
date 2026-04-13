import os

from typing import Dict, Any, Optional

from PySide6.QtCore import (
    Qt, QAbstractListModel, QSortFilterProxyModel,
    QModelIndex, QRunnable, QThreadPool, Signal, QObject
)
from PySide6.QtGui import QIcon, QPixmap, QPainter, QBrush, QPen, QColor, QFont



class IconLoaderSignals(QObject):
    icon_loaded = Signal(str, QIcon, int)  # appid, icon, generation



class IconLoader(QRunnable):
    def __init__(self, appid: str, steam_root: str, assetcache_apps: dict, generation: int):
        super().__init__()
        self.appid = appid
        self.steam_root = steam_root
        self.assetcache_apps = assetcache_apps
        self.generation = generation
        self.signals = IconLoaderSignals()
    

    def run(self):
        icon = self._load_icon()
        self.signals.icon_loaded.emit(self.appid, icon, self.generation)
    

    def _load_icon(self) -> QIcon:
        entry = self.assetcache_apps.get(self.appid, {})
        icon_file = entry.get("4f")
        
        if icon_file:
            path = os.path.join(self.steam_root, "appcache", "librarycache", self.appid, icon_file)
            if os.path.isfile(path):
                return QIcon(path)

        return QIcon()



class GameListModel(QAbstractListModel):
    def __init__(self, icon_cache: dict, parent=None):
        super().__init__(parent)
        self.games = []
        self.appid_to_row = {}
        self.threadpool = QThreadPool.globalInstance()
        self.load_generation = 0
        self.pending_loads = set()
        self.icon_cache = icon_cache
        self.empty_icon = self._create_fallback_icon()
    

    @staticmethod
    def _create_fallback_icon() -> QIcon:
        """Create a fallback icon for games without icons."""
        pixmap = QPixmap(32, 32)
        pixmap.fill(Qt.transparent)
        
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setBrush(QBrush(QColor(60, 60, 60)))
        painter.setPen(QPen(QColor(80, 80, 80)))
        painter.drawRoundedRect(0, 0, 32, 32, 4, 4)
        painter.setPen(QPen(QColor(150, 150, 150)))
        painter.setFont(QFont("Arial", 16, QFont.Bold))
        painter.drawText(0, 0, 32, 32, Qt.AlignCenter, "?")
        painter.end()
        
        return QIcon(pixmap)


    def rowCount(self, parent=QModelIndex()):
        return len(self.games)
    

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid() or index.row() >= len(self.games):
            return None
        
        game = self.games[index.row()]
        
        if role == Qt.DisplayRole:
            return f"{game['name']}: {game['appid']}"
        elif role == Qt.UserRole:
            return game
        elif role == Qt.DecorationRole:
            icon = game.get("icon")
            return icon if icon is not None else self.empty_icon
        
        return None
    

    def setGames(self, games):
        self.beginResetModel()
        self.games = games
        self.appid_to_row = {game["appid"]: i for i, game in enumerate(games)}
        self.endResetModel()
    

    def getGame(self, row):
        if 0 <= row < len(self.games):
            return self.games[row]
        return None
    

    def getRowByAppid(self, appid: str):
        return self.appid_to_row.get(appid)
    

    def loadIconAsync(self, appid: str, steam_root: str, assetcache_apps: dict, generation: int):
        if appid in self.pending_loads:
            return
        
        self.pending_loads.add(appid)
        loader = IconLoader(appid, steam_root, assetcache_apps, generation)
        loader.signals.icon_loaded.connect(self._on_icon_loaded)
        self.threadpool.start(loader)
    

    def _on_icon_loaded(self, appid: str, icon: QIcon, generation: int):
        if appid in self.pending_loads:
            self.pending_loads.remove(appid)

        if generation != self.load_generation:
            return

        if icon.isNull():
            final_icon = self.empty_icon
        else:
            final_icon = icon
        
        self.icon_cache[appid] = final_icon
        row = self.appid_to_row.get(appid)
        if row is not None:
            self.games[row]["icon"] = final_icon
            index = self.index(row, 0)
            self.dataChanged.emit(index, index, [Qt.DecorationRole])
    

    def cancelPendingLoads(self):
        self.load_generation += 1
        self.pending_loads.clear()



class GameSortFilterProxyModel(QSortFilterProxyModel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.filter_text = ""
        self.show_only_uninitialized = False
        self.type_filter = "All Games"
        self.sort_mode = "Alphabetical"
    

    def setFilterText(self, text):
        self.filter_text = text.lower()
        self.invalidateFilter()
    

    def setShowOnlyUninitialized(self, enabled):
        self.show_only_uninitialized = enabled
        self.invalidateFilter()
    

    def setSortMode(self, mode):
        self.sort_mode = mode
        self.invalidate()
        self.sort(0)


    def setTypeFilter(self, filter_type):
        self.type_filter = filter_type
        self.invalidateFilter()
    

    def filterAcceptsRow(self, source_row, source_parent):
        model = self.sourceModel()
        index = model.index(source_row, 0)
        game = model.data(index, Qt.UserRole)
        
        if not game:
            return False
        
        if self.type_filter == "Steam Games Only" and game["type"] != "steam":
            return False
        if self.type_filter == "Non-Steam Shortcuts Only" and game["type"] != "shortcut":
            return False
        
        if self.show_only_uninitialized and game.get("initialized", True):
            return False
        
        if self.filter_text:
            search_text = f"{game['name']} {game['appid']}".lower()
            if self.filter_text not in search_text:
                return False
        
        return True
    

    def lessThan(self, left, right):
        model = self.sourceModel()
        left_game = model.data(left, Qt.UserRole)
        right_game = model.data(right, Qt.UserRole)
        
        if not left_game or not right_game:
            return super().lessThan(left, right)
        
        def get_meta(data, key, fallback_key=None):
            value = data.get("meta", {}).get(key, 0) or 0
            if fallback_key and not value:
                value = data.get("meta", {}).get(fallback_key, 0) or 0
            return int(value)
        
        mode = self.sort_mode
        
        if mode == "Alphabetical":
            return left_game["name"].lower() < right_game["name"].lower()
        elif mode == "Last Played":
            left_val = get_meta(left_game, "LastPlayed", "LastPlayTime")
            right_val = get_meta(right_game, "LastPlayed", "LastPlayTime")
            return left_val > right_val
        elif mode == "Last Updated":
            left_val = get_meta(left_game, "lastupdated")
            right_val = get_meta(right_game, "lastupdated")
            return left_val > right_val
        elif mode == "Size on Disk":
            left_val = get_meta(left_game, "SizeOnDisk")
            right_val = get_meta(right_game, "SizeOnDisk")
            return left_val > right_val
        elif mode == "Playtime High to Low":
            left_val = get_meta(left_game, "Playtime")
            right_val = get_meta(right_game, "Playtime")
            return left_val > right_val
        elif mode == "Playtime Low to High":
            left_val = get_meta(left_game, "Playtime")
            right_val = get_meta(right_game, "Playtime")
            return left_val < right_val
        
        return super().lessThan(left, right)