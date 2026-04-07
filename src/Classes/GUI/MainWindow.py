import re
import os
import vdf
import random

from PySide6.QtGui import (
    QFont, QIcon, QPixmap, QColor, QPainter, QBrush, QPen
)
from PySide6.QtCore import (
    QTimer, Qt, QEvent, QSortFilterProxyModel, QAbstractListModel,
    QModelIndex, QRunnable, QThreadPool, Signal, QObject
)
from PySide6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QLineEdit, QPushButton, QHBoxLayout,
    QLabel, QListView, QMessageBox, QMenu, QAbstractItemView, QComboBox, QCheckBox
)

from Classes.Steam import SteamUser
from Classes.Actions import Actions
from Classes.GUI.ActionDialog import ActionDialog
from Classes.GUI.HighlightDelegate import HighlightDelegate



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

        fallback_pixmap = QPixmap(32, 32)
        fallback_pixmap.fill(Qt.transparent)
        painter = QPainter(fallback_pixmap)
        painter.setRenderHint(QPainter.Antialiasing)

        painter.setBrush(QBrush(QColor(60, 60, 60)))
        painter.setPen(QPen(QColor(80, 80, 80)))
        painter.drawRoundedRect(0, 0, 32, 32, 4, 4)
        
        painter.setPen(QPen(QColor(150, 150, 150)))
        painter.setFont(QFont("Arial", 16, QFont.Bold))
        painter.drawText(0, 0, 32, 32, Qt.AlignCenter, "?")
        painter.end()
        
        self.empty_icon = QIcon(fallback_pixmap)
    

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



class MainWindow(QWidget):
    def __init__(self, data, steam_root, steam_id, user_switcher_callback=None):
        super().__init__()
        self.setWindowTitle("Protontricks at Home")
        self.resize(650, 750)

        self.data = data
        self.steam_root = steam_root
        self.steam_id = steam_id
        self.logged_in_steam_id = steam_id
        self.user_switcher_callback = user_switcher_callback

        self.icon_cache: dict[str, QIcon] = {}
        self.header_cache: dict[str, QPixmap] = {}
        self.assetcache_apps: dict[str, dict] = {}

        self.model = GameListModel(self.icon_cache)
        self.proxy = GameSortFilterProxyModel()
        self.proxy.setSourceModel(self.model)
        self.model.setGames(self.data)
        self.proxy.sort(0)

        self._load_assetcache()
        self._setup_async_loading()
        self._enrich_data_with_icons()

        self._build_ui()
        self._update_status()
        self._start_async_icon_loading()


    def _setup_async_loading(self):
        self.icon_load_queue = []
        self.current_loading_index = 0
        self.batch_size = 20


    def _enrich_data_with_icons(self):
        for item in self.data:
            if item["type"] == "steam":
                item["icon"] = None
            else:
                path = item["meta"].get("icon")
                if path:
                    item["icon"] = self.icon_cache.get(path)
                    if not item["icon"] and os.path.isfile(path):
                        icon = QIcon(path)
                        self.icon_cache[path] = icon
                        item["icon"] = icon
                else:
                    item["icon"] = self.model.empty_icon


    def _start_async_icon_loading(self):
        self.icon_load_queue = [item["appid"] for item in self.data if item["type"] == "steam"]
        self.current_loading_index = 0
        self._load_next_batch()
    

    def _load_next_batch(self):
        if self.current_loading_index >= len(self.icon_load_queue):
            return
        
        end_index = min(self.current_loading_index + self.batch_size, len(self.icon_load_queue))
        batch = self.icon_load_queue[self.current_loading_index:end_index]
        generation = self.model.load_generation
        
        for appid in batch:
            if appid in self.icon_cache:
                icon = self.icon_cache[appid]
                row = self.model.getRowByAppid(appid)
                if row is not None:
                    self.model.games[row]["icon"] = icon
                    model_index = self.model.index(row, 0)
                    self.model.dataChanged.emit(model_index, model_index, [Qt.DecorationRole])
            else:
                self.model.loadIconAsync(appid, self.steam_root, self.assetcache_apps, generation)
        
        self.current_loading_index = end_index
        
        if self.current_loading_index < len(self.icon_load_queue):
            QTimer.singleShot(30, self._load_next_batch)


    def _get_icon(self, item):
        path = item["meta"].get("icon")
        if path and os.path.isfile(path):
            return self.icon_cache.setdefault(path, QIcon(path))
        return self.model.empty_icon


    def refresh_data(self, new_data):
        self.model.cancelPendingLoads()
        self.icon_cache.clear()
        self.header_cache.clear()
        self._load_assetcache()
        
        self.data = new_data
        self._enrich_data_with_icons()
        self.model.setGames(new_data)
        self._start_async_icon_loading()
        
        self.search.clear()
        self.non_initialized_checkbox.setChecked(False)
        self.type_filter.setCurrentIndex(0)
        self._update_status()
        self._select_first_visible()


    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.addWidget(self._build_title())
        layout.addWidget(QLabel("Select Steam App"))

        self.search = QLineEdit()
        self.search.setToolTip("Type to filter games (Ctrl+V to paste)")
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self.on_search_text_changed)
        self.search.hide()
        
        self.list_view = QListView()
        self.list_view.setToolTip("Double-click to view details\nRight-click for more options")
        font = QFont()
        font.setPointSize(12)
        self.list_view.setFont(font)
        self.list_view.setModel(self.proxy)
        self.list_view.setItemDelegate(HighlightDelegate(self.search))
        self.list_view.doubleClicked.connect(self.open_selected)
        self.list_view.setContextMenuPolicy(Qt.CustomContextMenu)
        self.list_view.customContextMenuRequested.connect(self.show_context_menu)
        self.list_view.setResizeMode(QListView.Adjust)
        self.list_view.setHorizontalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.list_view.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        
        filter_layout = QHBoxLayout()
        
        self.sort_box = QComboBox()
        self.sort_box.setToolTip("Sort the game list by different criteria")
        self.sort_box.addItems([
            "Alphabetical", "Last Played", "Last Updated",
            "Size on Disk", "Playtime High to Low", "Playtime Low to High"
        ])
        self.sort_box.currentIndexChanged.connect(self.on_sort_changed)
        filter_layout.addWidget(self.sort_box, 2)
        
        self.type_filter = QComboBox()
        self.type_filter.setToolTip("Filter by game type")
        self.type_filter.addItems(["All Games", "Steam Games Only", "Non-Steam Shortcuts Only"])
        self.type_filter.currentIndexChanged.connect(self.on_filter_changed)
        filter_layout.addWidget(self.type_filter, 1)
        
        self.non_initialized_checkbox = QCheckBox("Non-Initialized?")
        self.non_initialized_checkbox.setToolTip("Show only games that haven't been launched yet")
        self.non_initialized_checkbox.stateChanged.connect(self.on_filter_changed)
        filter_layout.addWidget(self.non_initialized_checkbox, 0)
        
        layout.addLayout(filter_layout)
        layout.addWidget(self.search)
        layout.addWidget(self.list_view)
        layout.addWidget(self._build_random_button())
        layout.addLayout(self._build_bottom_bar())
        
        self.installEventFilter(self)
        self.sort_box.installEventFilter(self)
        self.list_view.installEventFilter(self)
        self.search.installEventFilter(self)
        self.user_dropdown.installEventFilter(self)


    def _build_title(self):
        label = QLabel("Protontricks at Home")
        font = QFont()
        font.setPointSize(18)
        label.setFont(font)
        label.setAlignment(Qt.AlignCenter)
        return label


    def _build_random_button(self):
        btn = QPushButton("Pick Random")
        btn.setToolTip("Select a random game from the current list")
        btn.clicked.connect(self.pick_random)
        return btn


    def _build_bottom_bar(self):
        layout = QHBoxLayout()
        layout.setContentsMargins(0, 3, 0, 0)
        layout.addWidget(self._build_profile_widget())
        layout.addStretch()

        self.status_label = QLabel()
        self.status_label.setAlignment(Qt.AlignRight)
        self.status_label.setStyleSheet("QLabel { color: gray; }")
        layout.addWidget(self.status_label)
        return layout


    def _build_profile_widget(self):
        widget = QWidget()
        layout = QHBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)

        self.user_dropdown = QComboBox()
        self.user_dropdown.setToolTip("Switch Steam user")
        self.user_dropdown.currentIndexChanged.connect(self.on_user_changed)
        self._populate_user_dropdown()
        layout.addWidget(self.user_dropdown)
        layout.addStretch()
        return widget


    def _populate_user_dropdown(self):
        self.user_dropdown.clear()
        steam_user = SteamUser(self.steam_root)
        users = steam_user.get_all_users()
        self.user_ids = []
        
        for user_id, user_name in users:
            avatar_icon = self._get_user_avatar(user_id)
            if user_id == self.steam_id:
                self.user_dropdown.addItem(avatar_icon, user_name)
                self.user_dropdown.setItemData(
                    self.user_dropdown.count() - 1,
                    QColor(0, 255, 0),
                    Qt.ForegroundRole
                )
            else:
                self.user_dropdown.addItem(avatar_icon, user_name)
            
            self.user_ids.append(user_id)
            if user_id == self.steam_id:
                self.user_dropdown.setCurrentIndex(self.user_dropdown.count() - 1)
        
        if self.user_dropdown.count() == 0:
            self.user_dropdown.addItem("No users found")
            self.user_dropdown.setEnabled(False)


    def on_user_changed(self, index):
        if not self.user_switcher_callback or index < 0 or index >= len(self.user_ids):
            return
        
        new_user_id = self.user_ids[index]
        if new_user_id == self.steam_id:
            return
        
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            self.user_switcher_callback(new_user_id)
            self.steam_id = new_user_id
        finally:
            QApplication.restoreOverrideCursor()


    def _get_user_avatar(self, user_id: str) -> QIcon:
        path = os.path.join(self.steam_root, "config", "avatarcache", f"{user_id}.png")
        if os.path.isfile(path):
            pix = QPixmap(path)
            if not pix.isNull():
                return QIcon(pix.scaled(32, 32, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        
        pix = QPixmap(32, 32)
        pix.fill(Qt.transparent)
        return QIcon(pix)


    def get_steam_header(self, appid: str, app_type: str = "steam") -> QPixmap | None:
        cache_key = f"{app_type}_{appid}"
        if cache_key in self.header_cache:
            return self.header_cache[cache_key]

        path = None
        if app_type == "steam":
            entry = self.assetcache_apps.get(appid, {})
            header_file = entry.get("3f")
            if header_file:
                path = os.path.join(self.steam_root, "appcache", "librarycache", appid, header_file)
        elif app_type == "shortcut":
            grid_folder = os.path.join(
                self.steam_root, "userdata",
                str(int(self.steam_id) & 0xFFFFFFFF), "config", "grid"
            )
            path = os.path.join(grid_folder, f"{appid}.jpg")

        if path and os.path.isfile(path):
            pix = QPixmap(path)
            self.header_cache[cache_key] = pix
            return pix

        return None


    def _select_first_visible(self):
        if self.proxy.rowCount() > 0:
            self.list_view.setCurrentIndex(self.proxy.index(0, 0))


    def on_search_text_changed(self, text):
        self.search.setVisible(bool(text))
        self.proxy.setFilterText(text)
        self.list_view.viewport().update()
        self._update_status()
        self._select_first_visible()


    def on_sort_changed(self):
        self.proxy.setSortMode(self.sort_box.currentText())
        self._update_status()
        self._select_first_visible()


    def on_filter_changed(self):
        self.proxy.setShowOnlyUninitialized(self.non_initialized_checkbox.isChecked())
        self.proxy.setTypeFilter(self.type_filter.currentText())
        self._update_status()
        self._select_first_visible()


    def _update_status(self):
        total = self.model.rowCount()
        visible = self.proxy.rowCount()
        sort_mode = self.sort_box.currentText()
        text = self.search.text().strip()

        if text:
            self.status_label.setText(f"{visible}/{total} matching '{text}' • Sorted: {sort_mode}")
        else:
            self.status_label.setText(f"{visible} items • Sorted: {sort_mode}")


    def open_selected(self):
        index = self.list_view.currentIndex()
        if index.isValid():
            source_index = self.proxy.mapToSource(index)
            game = self.model.getGame(source_index.row())
            if game:
                ActionDialog(game, self).exec()


    def pick_random(self):
        row_count = self.proxy.rowCount()
        if row_count == 0:
            QMessageBox.information(self, "Protontricks at Home - No Items", "No items available.")
            return
        
        index = self.proxy.index(random.randrange(row_count), 0)
        self.list_view.setCurrentIndex(index)
        self.open_selected()


    def show_context_menu(self, pos):
        index = self.list_view.indexAt(pos)
        if not index.isValid():
            return
        
        source_index = self.proxy.mapToSource(index)
        game = self.model.getGame(source_index.row())
        if not game:
            return
        
        initialized = game.get("initialized", True)
        is_owner = True
        
        if game["type"] == "steam":
            game_owner = game.get("meta", {}).get("LastOwner")
            is_owner = (game_owner == self.logged_in_steam_id)
        
        menu = QMenu(self)
        self._add_menu_action(menu, "Launch", lambda: Actions.launch_game(game["type"], game["appid"]), is_owner)
        self._add_menu_action(menu, "Show Info", self.open_selected)
        menu.addSeparator()
        
        self._add_menu_action(menu, "Run Winetricks", lambda: Actions.run_winetricks(game["path"], self), initialized)
        self._add_menu_action(menu, "Open Compat Path", lambda: Actions.open_compatfolder(game["path"], self), initialized)
        self._add_menu_action(menu, "Copy App ID", lambda: Actions.copy_with_feedback(game["appid"], f"App ID {game['appid']} Copied!", self))
        self._add_menu_action(menu, "Copy Compat Path", lambda: Actions.copy_with_feedback(game["path"], "Compat Path Copied!", self), initialized)
        menu.exec(self.list_view.mapToGlobal(pos))


    def _add_menu_action(self, menu, name, func, enabled=True):
        action = menu.addAction(name, func)
        action.setEnabled(enabled)


    def _load_assetcache(self):
        path = os.path.join(self.steam_root, "appcache", "librarycache", "assetcache.vdf")
        if not os.path.isfile(path):
            QMessageBox.warning(self, "Warning", "Could not find assetcache.vdf. Game icons may not load.")
            return

        try:
            with open(path, "rb") as f:
                data = vdf.binary_loads(f.read())
            self.assetcache_apps = data.get("", {}).get("0", {})
        except Exception as e:
            print(f"Failed to load assetcache: {e}")


    def get_steam_description(self, appid):
        path = os.path.join(
            self.steam_root, "userdata",
            str(int(self.steam_id) & 0xFFFFFFFF), "config", "librarycache", f"{appid}.json"
        )

        if not os.path.isfile(path):
            return None

        try:
            with open(path, "r", encoding="utf-8", errors="ignore") as f:
                data = f.read()

            match = re.search(r'"strSnippet"\s*:\s*"((?:[^"\\]|\\.)*)"', data)
            if match:
                return match.group(1).replace('\\"', '"').replace('\\\\', '\\')
        except Exception as e:
            print(f"Failed to load description: {e}")

        return None


    def eventFilter(self, obj, event):
        if event.type() != QEvent.KeyPress:
            return super().eventFilter(obj, event)

        key = event.key()
        modifiers = event.modifiers()
        text = event.text()

        def has_modifier():
            return modifiers & (Qt.ControlModifier | Qt.AltModifier | Qt.MetaModifier)

        if key == Qt.Key_V and modifiers == Qt.ControlModifier:
            if self.search.isVisible():
                self.search.setFocus()
            else:
                clipboard_text = QApplication.clipboard().text()
                self.search.show()
                self.search.setFocus()
                self.search.setText(clipboard_text)
                self.search.setCursorPosition(len(clipboard_text))
            return True

        if key == Qt.Key_Escape and self.search.isVisible():
            self.search.clear()
            self.search.hide()
            self.proxy.setFilterText("")
            self.list_view.setFocus()
            return True

        if not self.search.isVisible() and text and text.isprintable() and not text.isspace() and not has_modifier():
            self.search.show()
            self.search.setFocus()
            self.search.setText(text)
            self.search.setCursorPosition(len(text))
            return True

        return super().eventFilter(obj, event)