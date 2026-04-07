import sys
from PySide6.QtWidgets import QApplication

from Classes.GUI.MainWindow import MainWindow
from Classes.Steam import SteamPaths, SteamUser, SteamApps, SteamShortcuts, ProtonPrefixes



def load_user_data(steam_root: str, user_id: str):
    paths = SteamPaths(steam_root)
    steam_apps = SteamApps(paths, user_id).installed()
    shortcuts = SteamShortcuts(paths, user_id).installed()
    prefixes = ProtonPrefixes(paths, steam_apps, shortcuts).all()
    return prefixes


def main():
    steam_root = "~/.local/share/Steam"
    paths = SteamPaths(steam_root)
    steam_user = SteamUser(paths.root)
    user_id, display_name = steam_user.get_active_user()

    if not user_id:
        print("No active Steam user found.")
        return

    app = QApplication(sys.argv)
    prefixes = load_user_data(steam_root, user_id)
    
    def switch_user(new_user_id: str):
        new_prefixes = load_user_data(steam_root, new_user_id)
        win.refresh_data(new_prefixes)
    
    win = MainWindow(prefixes, paths.root, user_id, switch_user)
    win.show()
    sys.exit(app.exec())



if __name__ == "__main__":
    main()