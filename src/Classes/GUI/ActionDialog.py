from datetime import datetime
from typing import Any, Dict, Optional, Union

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QVBoxLayout, QLabel, QFrame, QPushButton, QGridLayout

from Classes.Actions import Actions



def format_bytes(size: int) -> str:
    """Format a byte size into a human-readable string with appropriate units."""
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if size < 1024:
            return f"{size:.2f} {unit}"
        size /= 1024
    return f"{size:.2f} PB"


def format_unix(ts: Union[str, int]) -> str:
    """Format a Unix timestamp into a readable date and time string."""
    try:
        ts = int(ts)
        return "Never" if ts == 0 else datetime.fromtimestamp(ts).strftime("%m/%d/%Y - %I:%M %p")
    except (ValueError, TypeError, OSError):
        return "Unknown"


def format_playtime(minutes: Union[int, str]) -> str:
    """Format playtime in minutes to hours."""
    try:
        return f"{int(minutes)/60:.1f} hours"
    except (ValueError, TypeError):
        return "Unknown"



class ActionDialog(QDialog):
    HEADER_WIDTH = 460

    def __init__(self, item: Dict[str, Any], parent: Optional[Any] = None) -> None:
        """Initialize the ActionDialog with game/shortcut data."""
        super().__init__(parent)
        self.item = item
        self.parent_ref = parent
        self.setWindowTitle("Protontricks at Home")
        layout = QVBoxLayout(self)

        self._add_title(layout)
        self._add_header(layout)
        self._add_info(layout)
        self._add_description(layout)
        self._add_buttons(layout)


    def _add_title(self, layout: QVBoxLayout) -> None:
        """Add the title section with game name and App ID."""
        name = self.item['name'] if self.item['type'] == "steam" else self.item['meta'].get('AppName')
        self.setWindowTitle(f"Protontricks at Home - {name}")
        label = QLabel(
            f"<b style='font-size:16px'>{name}</b><br>"
            f"<span style='color:gray'>App ID: {self.item['appid']}</span>"
        )
        label.setAlignment(Qt.AlignCenter)
        layout.addWidget(label)
        layout.addWidget(self._separator())


    def _add_header(self, layout: QVBoxLayout) -> None:
        """Add the game header image if available."""
        header = self.parent_ref.get_steam_header(self.item["appid"], self.item["type"])
        if not header:
            return

        img = QLabel()
        img.setPixmap(header.scaledToWidth(self.HEADER_WIDTH, Qt.SmoothTransformation))
        img.setAlignment(Qt.AlignCenter)
        layout.addWidget(img)
        layout.addWidget(self._separator())


    def _add_info(self, layout: QVBoxLayout) -> None:
        """Add the information section with playtime, size, and other metadata."""
        label = QLabel()
        label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        label.setText(self._build_info_text())
        layout.addWidget(label)
        layout.addWidget(self._separator())


    def _add_description(self, layout: QVBoxLayout) -> None:
        """Add the game description section (Steam games only)."""
        if self.item["type"] != "steam":
            return

        desc = self.parent_ref.get_steam_description(self.item["appid"])
        if not desc:
            return

        label = QLabel(desc)
        label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        label.setWordWrap(True)
        layout.addWidget(label)
        layout.addWidget(self._separator())


    def _add_buttons(self, layout: QVBoxLayout) -> None:
        """Add action buttons for Winetricks, opening paths, copying info, and launching."""
        initialized = self.item.get("initialized", True)
        is_owner = True
        parent = self.parent_ref
        
        if self.item["type"] == "steam" and hasattr(parent, 'logged_in_steam_id'):
            game_owner = self.item.get("meta", {}).get("LastOwner")
            is_owner = (game_owner == parent.logged_in_steam_id)
        
        button_grid = QGridLayout()
        
        buttons = [
            ("Run Winetricks", lambda: Actions.run_winetricks(self.item["path"], self), initialized, 0, 0, 1, 1),
            ("Open Compat Path", lambda: Actions.open_compatfolder(self.item["path"], self), initialized, 0, 1, 1, 1),
            ("Copy App ID", lambda: Actions.copy_with_feedback(self.item["appid"], f"App ID {self.item['appid']} Copied!", self), True, 1, 0, 1, 1),
            ("Copy Compat Path", lambda: Actions.copy_with_feedback(self.item["path"], "Compat Path Copied!", self), initialized, 1, 1, 1, 1),
            ("Launch Game", lambda: Actions.launch_game(parent.steam_installation, self.item["type"], self.item["appid"]), is_owner, 2, 0, 1, 2),
        ]
        
        for text, callback, enabled, row, col, row_span, col_span in buttons:
            btn = QPushButton(text)
            btn.clicked.connect(callback)
            btn.setEnabled(enabled)
            
            if not enabled:
                if text in ["Run Winetricks", "Open Compat Path", "Copy Compat Path"]:
                    btn.setToolTip("Option unavailable until Proton Prefix has been generated")
                elif text == "Launch Game":
                    btn.setToolTip("You don't own this game on your logged-in Steam account")
            
            button_grid.addWidget(btn, row, col, row_span, col_span)
        
        layout.addLayout(button_grid)


    def _build_info_text(self) -> str:
        """Build the HTML-formatted information text from metadata."""
        meta = self.item["meta"]
        
        if self.item["type"] == "steam":
            fields = [
                ("SizeOnDisk", "Size on Disk", format_bytes),
                ("Playtime", "Playtime", format_playtime),
                ("LastPlayed", "Last Played", format_unix),
                ("lastupdated", "Last Updated", format_unix),
            ]
            
            parts = []
            for key, label, formatter in fields:
                value = int(meta.get(key, 0))
                if value:
                    parts.append(f"{label}: {formatter(value)}")
            
            return "<br>".join(parts) if parts else "No additional information available"
        else:
            last_played = int(meta.get("LastPlayTime", 0))
            return f"Last Played: {format_unix(last_played)}" if last_played else "No additional information available"


    def _separator(self) -> QFrame:
        """Create a horizontal separator line."""
        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setFrameShadow(QFrame.Sunken)
        return line