import os
import logging

from dataclasses import dataclass
from typing import List, Optional



logger = logging.getLogger(__name__)



@dataclass(frozen=True)
class SteamInstallation:
    name: str
    path: str
    command: List[str]



_KNOWN_PATHS = [
    SteamInstallation("Native", "~/.local/share/Steam", ["steam"]),
    SteamInstallation("Flatpak", "~/.var/app/com.valvesoftware.Steam/data/Steam", ["flatpak", "run", "com.valvesoftware.Steam"]),
    SteamInstallation("Snap", "~/snap/steam/common/.local/share/Steam", ["snap", "run", "steam"]) # god I hope this is right
]



def _valid(path: str) -> bool:
    """Check if path is a valid Steam installation."""
    return os.path.isdir(path) and os.path.isdir(os.path.join(path, "steamapps"))


def find_all() -> List[SteamInstallation]:
    """Find existing Steam installations from known paths."""
    found = [
        SteamInstallation(p.name, os.path.expanduser(p.path), p.command)
        for p in _KNOWN_PATHS
        if _valid(os.path.expanduser(p.path))
    ]

    return found



def from_path(path: str) -> Optional[SteamInstallation]:
    """Get installation by path, returns custom install if valid but unknown."""
    path = os.path.expanduser(path)
    if not _valid(path):
        return None

    for inst in find_all():
        if inst.path == path:
            return inst

    logger.debug(f"Using custom Steam path: {path}")
    return SteamInstallation(f"Custom", path, ["xdg-open"]) # hard to have a fallback for this, so use sys default