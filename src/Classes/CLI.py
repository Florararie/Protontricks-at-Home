import os
import sys
import logging
import argparse

from typing import List, Dict, Any, Optional

from Classes.Actions import Actions
from Classes.Steam.Steam import SteamPaths, SteamUser, SteamApps, SteamShortcuts, ProtonPrefixes



logger = logging.getLogger(__name__)



def load_prefixes(steam_root: str, user_id: str) -> List[Dict[str, Any]]:
    """Load all Proton prefixes for the given Steam user."""
    paths = SteamPaths(steam_root)
    apps = SteamApps(paths, user_id).installed()
    shortcuts = SteamShortcuts(paths, user_id).installed()
    return ProtonPrefixes(paths, apps, shortcuts).all()



def build_parser() -> argparse.ArgumentParser:
    """Build the argument parser with proper help formatting."""
    parser = argparse.ArgumentParser(
        description="Protontricks at Home",
        epilog="Run without arguments to launch the GUI.\n\n"
               "Environment Variables:\n"
               "  STEAM_ROOT    Path to specific Steam installation (overrides auto-detection)\n\n"
               "Examples:\n"
               "  %(prog)s list\n"
               "  %(prog)s --steam-root ~/.local/share/Steam list\n"
               "  STEAM_ROOT=~/.var/app/com.valvesoftware.Steam/data/Steam %(prog)s\n"
               "  %(prog)s search Skyrim\n"
               "  %(prog)s winetricks 12345 d3dx9\n"
               "  %(prog)s run 12345 ~/Downloads/installer.exe\n"
               "  %(prog)s launch 12345",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )

    parser.add_argument("-v", "--verbose", action="store_true", help="Enable verbose output")
    parser.add_argument("-sr", "--steam-root", type=str, help="Path to specific Steam installation")

    subparsers = parser.add_subparsers(dest="command", title="Commands", metavar="")

    # List
    subparsers.add_parser("list", help="List all prefixes")

    # Search
    search = subparsers.add_parser("search", help="Search for games")
    search.add_argument("term", help="Search term")

    # Winetricks
    winetricks = subparsers.add_parser("winetricks", help="Run winetricks")
    winetricks.add_argument("appid", help="Steam App ID")
    winetricks.add_argument("verbs", nargs="+", help="Winetricks verbs to run")

    # Run
    run = subparsers.add_parser("run", help="Run executable")
    run.add_argument("appid", help="Steam App ID")
    run.add_argument("exe", help="Executable path")
    run.add_argument("args", nargs="*", help="Arguments to pass")

    # Launch
    launch = subparsers.add_parser("launch", help="Launch game")
    launch.add_argument("appid", help="Steam App ID")

    return parser



def find_entry(prefixes: List[Dict[str, Any]], appid: str) -> Optional[Dict[str, Any]]:
    """Find a prefix entry by its AppID."""
    return next((p for p in prefixes if p["appid"] == appid), None)



def run_winetricks(ctx, appid: str, verbs: List[str]) -> None:
    """Run winetricks commands in a prefix."""
    entry = find_entry(ctx.prefixes, appid)
    if not entry:
        logger.error(f"AppID {appid} not found")
        sys.exit(1)

    if ctx.verbose:
        logger.info(f"Running winetricks {' '.join(verbs)} in {entry['name']}")

    code = Actions.run_command_blocking("winetricks", verbs, {"WINEPREFIX": entry["path"]})
    if code:
        logger.error(f"Winetricks exited with code {code}")
        sys.exit(code)



def run_exe(ctx, appid: str, exe_path: str, args: List[str]) -> None:
    """Run an executable in a prefix."""
    entry = find_entry(ctx.prefixes, appid)
    if not entry:
        logger.error(f"AppID {appid} not found")
        sys.exit(1)

    exe_path = os.path.abspath(os.path.expanduser(exe_path))
    if not os.path.isfile(exe_path):
        logger.error(f"Executable not found: {exe_path}")
        sys.exit(1)

    if ctx.verbose:
        logger.info(f"Running wine {exe_path} in {entry['name']}")

    code = Actions.run_command_blocking(
        "wine",
        [exe_path] + args,
        {"WINEPREFIX": entry["path"]},
        cwd=os.path.dirname(exe_path),
    )
    if code:
        logger.error(f"Command exited with code {code}")
        sys.exit(code)



def launch_game(ctx, appid: str) -> None:
    """Launch a game through Steam."""
    entry = find_entry(ctx.prefixes, appid)
    if not entry:
        logger.error(f"AppID {appid} not found")
        sys.exit(1)

    if ctx.verbose:
        logger.info(f"Launching {entry['name']}")

    Actions.launch_game(ctx.steam_installation, entry["type"], appid)



def run_cli(ctx, args: argparse.Namespace) -> None:
    """Route CLI commands to appropriate handlers."""
    print()
    if args.command == "list":
        print(f"Prefixes listed: {len(ctx.prefixes)}")
        for p in ctx.prefixes:
            print(f"{p['name']} ({p['appid']})")

    elif args.command == "search":
        term = args.term.lower()
        matches = [p for p in ctx.prefixes if term in p["name"].lower()]
        if not matches:
            print("No matches found.")
        else:
            count = len(matches)
            total = len(ctx.prefixes)
            print(f"Matched {count} {'entry' if count == 1 else 'entries'} out of {total} prefixes")
            for m in matches:
                print(f"{m['name']} ({m['appid']})")

    elif args.command == "winetricks":
        run_winetricks(ctx, args.appid, args.verbs)

    elif args.command == "run":
        run_exe(ctx, args.appid, args.exe, args.args)

    elif args.command == "launch":
        launch_game(ctx, args.appid)