#!/usr/bin/env python3

import os
import sys
import logging
import argparse
from dataclasses import dataclass
from typing import Dict, Any, List, Optional, Literal
from PySide6.QtWidgets import QApplication, QDialog, QVBoxLayout, QListWidget, QPushButton, QLabel

from Classes.GUI.MainWindow import MainWindow
from Classes.Steam.Steam import SteamPaths, SteamUser
from Classes.CLI import load_prefixes, build_parser, run_cli
from Classes.Steam.SteamDetector import find_all, from_path, SteamInstallation



logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)



@dataclass
class Context:
    prefixes: List[Dict[str, Any]]
    steam_root: str
    steam_installation: SteamInstallation
    user_id: str
    verbose: bool = False



def resolve_install(args: argparse.Namespace, mode: Literal["CLI", "GUI"] = "CLI") -> Optional[SteamInstallation]:
    """Resolve Steam installation from CLI/env/etc"""
    if args.steam_root:
        logger.debug(f"Checking --steam-root: {args.steam_root}")
        install = from_path(args.steam_root)
        if not install:
            logger.error(f"Invalid Steam installation: {args.steam_root}")
            sys.exit(f"Invalid Steam installation: {args.steam_root}")
        logger.debug(f"Using --steam-root: {install.name}")
        return install

    env_root = os.environ.get("STEAM_ROOT")
    if env_root:
        logger.debug(f"Checking STEAM_ROOT: {env_root}")
        install = from_path(env_root)
        if not install:
            logger.error(f"Invalid STEAM_ROOT: {env_root}")
            sys.exit(f"Invalid STEAM_ROOT: {env_root}")
        logger.debug(f"Using STEAM_ROOT: {install.name}")
        return install

    installs = find_all()
    if not installs:
        logger.error("No Steam installations found")
        sys.exit("No Steam installations found.")

    logger.debug(f"Found {len(installs)} installation(s)")

    if mode == "CLI" and len(installs) > 1:
        logger.error("Multiple Steam installations found:")
        for i, inst in enumerate(installs, 1):
            print(f"  {i}. {inst.name} - {inst.path}")
        sys.exit("Specify --steam-root or STEAM_ROOT env var")

    if len(installs) == 1:
        logger.debug(f"Using only installation: {installs[0].name}")
        return installs[0]

    logger.debug("Multiple installations found, showing selector")
    return show_steam_selector_gui(installs)



def init_context(install: SteamInstallation, verbose: bool = False) -> Context:
    """Initializes context by loading Steam user data and prefixes."""
    paths = SteamPaths(install.path)
    user = SteamUser(paths.root)
    user_id, display_name = user.get_active_user()

    if not user_id:
        logger.error("No active Steam user found")
        sys.exit("No active Steam user found")

    prefixes = load_prefixes(install.path, user_id)
    logger.debug(f"Active user: {display_name} (ID: {user_id})")
    logger.debug(f"Loaded {len(prefixes)} prefixes")

    return Context(prefixes, install.path, install, user_id, verbose)



def show_steam_selector_gui(installs) -> Optional[SteamInstallation]:
    """Display a GUI dialog for the user to select which Steam installation to use."""
    if not installs:
        logger.error("No installations found for selector")
        return None

    dialog = QDialog()
    dialog.setWindowTitle("Protontricks at Home")
    dialog.resize(500, 300)

    layout = QVBoxLayout(dialog)
    layout.addWidget(QLabel("Multiple Steam installations found:"))

    list_widget = QListWidget()
    for inst in installs:
        list_widget.addItem(f"{inst.name}\n{inst.path}")
    layout.addWidget(list_widget)

    selected = None

    def select():
        """Handle selection button click or double-click."""
        nonlocal selected
        idx = list_widget.currentRow()
        if idx >= 0:
            selected = installs[idx]
        dialog.accept()

    btn = QPushButton("Select")
    btn.clicked.connect(select)
    list_widget.doubleClicked.connect(select)

    layout.addWidget(btn)

    dialog.exec()
    if selected:
        logger.debug(f"Selected {selected.name} at {selected.path}")
    return selected



def main() -> None:
    """Main entry point."""
    parser = build_parser()
    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
        logger.debug("Verbose mode enabled")

    if args.command:
        logger.debug(f"CLI mode with command: {args.command}")
        install = resolve_install(args, mode="CLI")
        if not install:
            sys.exit("Could not find Steam installation.")

        ctx = init_context(install, args.verbose)
        run_cli(ctx, args)
        return

    app = QApplication(sys.argv)
    install = resolve_install(args, mode="GUI")
    if not install:
        sys.exit("No Steam installation selected.")

    ctx = init_context(install, args.verbose)

    def switch_user(new_user_id: str, new_user_name: str) -> None:
        logger.debug(f"Switching to user: {new_user_name} (ID: {new_user_id})")
        new_prefixes = load_prefixes(ctx.steam_root, new_user_id)
        logger.debug(f"Loaded {len(new_prefixes)} prefixes for new user")
        win.refresh_data(new_prefixes)

    win = MainWindow(ctx.prefixes, ctx.steam_root, ctx.user_id, ctx.steam_installation, switch_user)
    win.show()

    sys.exit(app.exec())



if __name__ == "__main__":
    main()