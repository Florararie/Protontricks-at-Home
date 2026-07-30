import os
import vdf
import logging

from typing import Dict, List, Any, Tuple, Optional



logger = logging.getLogger(__name__)



class SteamPaths:
    def __init__(self, steam_root: str) -> None:
        """Initialize SteamPaths with the Steam installation root."""
        self.root = os.path.expanduser(steam_root)
        self.userdata = os.path.join(self.root, "userdata")


    def library_paths(self) -> List[str]:
        """Get all Steam library paths including the main library and additional ones."""
        paths: List[str] = []

        main = os.path.join(self.root, "steamapps")
        if os.path.isdir(main):
            paths.append(main)

        lib_vdf = os.path.join(main, "libraryfolders.vdf")
        if not os.path.isfile(lib_vdf):
            return paths

        try:
            with open(lib_vdf, "r", encoding="utf-8", errors="ignore") as f:
                data = vdf.load(f)

            for lib in data.get("libraryfolders", {}).values():
                lib_path = lib.get("path")
                if not lib_path:
                    continue

                sa = os.path.join(lib_path, "steamapps")
                if os.path.isdir(sa) and sa not in paths:
                    paths.append(sa)

        except Exception as e:
            logger.warning(f"Failed to read library folders: {e}")

        return paths



class SteamUser:
    def __init__(self, steam_root: str) -> None:
        """Initialize SteamUser with the Steam root directory."""
        self.root = steam_root
        self._users_cache = None


    def _load_users(self) -> dict:
        """Load user data from loginusers.vdf."""
        if self._users_cache is not None:
            return self._users_cache
            
        path = os.path.join(self.root, "config", "loginusers.vdf")
        users = {}
        
        if os.path.isfile(path):
            try:
                with open(path, "r", encoding="utf-8", errors="ignore") as f:
                    data = vdf.load(f)
                users = data.get("users", {})
            except Exception as e:
                logger.warning(f"Failed to load users: {e}")
        
        self._users_cache = users
        return users


    def get_all_users(self) -> List[Tuple[str, str]]:
        """Get all Steam users that have logged in."""
        users_data = self._load_users()
        return [(steamid, info.get("PersonaName", "Unknown")) for steamid, info in users_data.items()]


    def get_active_user(self) -> Tuple[Optional[str], Optional[str]]:
        """Get the most recently active Steam user."""
        users_data = self._load_users()

        if not users_data:
            return None, None

        steamid, info = max(users_data.items(), key=lambda item: int(item[1].get("Timestamp", 0)))
        return steamid, info.get("PersonaName", "Unknown")



class SteamApps:
    def __init__(self, paths: SteamPaths, steamid: str) -> None:
        """Initialize SteamApps for a specific user."""
        if not steamid or not steamid.isdigit():
            raise ValueError(f"Invalid steamid: {steamid}")
        self.paths = paths
        self.steamid = steamid
        self.user_id = str(int(steamid) & 0xFFFFFFFF)


    def _localconfig_path(self) -> str:
        """Get the path to the user's localconfig.vdf file."""
        return os.path.join(
            self.paths.userdata,
            self.user_id,
            "config",
            "localconfig.vdf"
        )


    def _load_playtimes(self) -> Dict[str, int]:
        """Load playtime data from localconfig.vdf."""
        playtimes: Dict[str, int] = {}
        path = self._localconfig_path()

        if not os.path.isfile(path):
            return playtimes

        try:
            with open(path, "r", encoding="utf-8", errors="ignore") as f:
                data = vdf.load(f)

            apps = (
                data.get("UserLocalConfigStore", {})
                    .get("Software", {})
                    .get("Valve", {})
                    .get("Steam", {})
                    .get("apps", {})
            )

            for appid, info in apps.items():
                try:
                    playtimes[str(appid)] = int(info.get("Playtime", 0))
                except (ValueError, TypeError):
                    continue

        except Exception as e:
            logger.warning(f"Failed to load playtimes: {e}")

        return playtimes


    def installed(self) -> Dict[str, Dict[str, Any]]:
        """Find all installed Steam games/apps for the user."""
        apps: Dict[str, Dict[str, Any]] = {}
        playtimes = self._load_playtimes()

        for library in self.paths.library_paths():
            common_path = os.path.join(library, "common")
            try:
                for fname in os.listdir(library):
                    if not (fname.startswith("appmanifest_") and fname.endswith(".acf")):
                        continue

                    manifest = os.path.join(library, fname)

                    try:
                        with open(manifest, "r", encoding="utf-8", errors="ignore") as f:
                            data = vdf.load(f)

                        app = data.get("AppState", {})
                        if app.get("LastOwner") != self.steamid:
                            continue

                        appid = str(app.get("appid") or fname[12:-4])
                        installdir = app.get("installdir")
                        name = app.get("name")
                        if not name or not installdir:
                            continue

                        install_path = os.path.join(common_path, installdir)
                        if os.path.isfile(os.path.join(install_path, "proton")):
                            continue

                        if appid in apps:
                            continue

                        meta = dict(app)
                        meta["Playtime"] = playtimes.get(appid, 0)

                        apps[appid] = {
                            "appid": appid,
                            "name": name,
                            "type": "steam",
                            "meta": meta,
                        }

                    except Exception as e:
                        logger.warning(f"Failed to parse manifest {manifest}: {e}")
                        continue

            except OSError as e:
                logger.warning(f"Failed to read library directory {library}: {e}")
                continue

        return apps



class SteamShortcuts:
    def __init__(self, paths: SteamPaths, steamid: str) -> None:
        """Initialize SteamShortcuts for a specific user."""
        self.paths = paths
        self.user_id = str(int(steamid) & 0xFFFFFFFF) if steamid else None


    def installed(self) -> Dict[str, Dict[str, Any]]:
        """Find all non-Steam shortcuts for the user."""
        if not self.user_id:
            return {}

        cfg = os.path.join(self.paths.userdata, self.user_id, "config", "shortcuts.vdf")

        if not os.path.isfile(cfg):
            return {}

        shortcuts: Dict[str, Dict[str, Any]] = {}

        try:
            with open(cfg, "rb") as f:
                data = vdf.binary_loads(f.read())

            for _, info in data.get("shortcuts", {}).items():
                raw = info.get("appid")
                if raw is None:
                    continue

                cid = str(raw & 0xFFFFFFFF)

                entry = dict(info)
                entry["appid"] = cid

                shortcuts[cid] = {
                    "appid": cid,
                    "name": f"Non-Steam Shortcut: {entry.get('AppName')}",
                    "type": "shortcut",
                    "meta": entry,
                }

        except Exception as e:
            logger.warning(f"Failed to read shortcuts: {e}")

        return shortcuts



class ProtonPrefixes:    
    def __init__(self, paths: SteamPaths, apps: Dict[str, Dict[str, Any]], shortcuts: Dict[str, Dict[str, Any]]) -> None:
        """Initialize ProtonPrefixes with Steam apps and shortcuts."""
        self.paths = paths
        self.entries = {**apps, **shortcuts}


    def _is_initialized(self, app_folder: str, pfx: str) -> bool:
        """Check if a Proton prefix has been initialized."""
        if not os.path.isdir(pfx):
            return False

        markers = ("config_info", "pfx.lock")
        return any(os.path.isfile(os.path.join(app_folder, m)) for m in markers)


    def all(self) -> List[Dict[str, Any]]:
        """Find all Proton prefixes for the installed apps and shortcuts."""
        seen = {}

        for library in self.paths.library_paths():
            compat = os.path.join(library, "compatdata")
            if not os.path.isdir(compat):
                continue

            for appid, entry in self.entries.items():
                app_folder = os.path.join(compat, appid)
                pfx = os.path.join(app_folder, "pfx")

                try:
                    real_path = os.path.realpath(pfx)
                    st = os.stat(real_path)
                except (FileNotFoundError, OSError):
                    continue

                key = (st.st_dev, st.st_ino)
                
                if key not in seen:
                    seen[key] = {
                        "name": entry["name"],
                        "appid": appid,
                        "path": real_path if os.path.isdir(pfx) else app_folder,
                        "type": entry["type"],
                        "meta": entry["meta"],
                        "initialized": self._is_initialized(app_folder, pfx),
                    }

        return sorted(seen.values(), key=lambda x: x["name"].lower())
