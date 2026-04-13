import os
import sys
import logging
import subprocess

from typing import List, Optional, Dict, Callable, Any

from PySide6.QtWidgets import QApplication, QMessageBox
from PySide6.QtCore import QTimer, QProcess, QProcessEnvironment



logger = logging.getLogger(__name__)



class Actions():
    _running_processes: List[QProcess] = []

    @staticmethod
    def run_command_blocking(command: str, args: Optional[List[str]] = None, env: Optional[Dict[str, str]] = None, cwd: Optional[str] = None) -> int:
        """Run a command synchronously and wait for completion (for CLI mode)."""
        if args is None:
            args = []

        full_env = os.environ.copy()
        if env:
            full_env.update(env)

        try:
            process = subprocess.Popen(
                [command] + args,
                env=full_env,
                cwd=cwd,
                stdout=sys.stdout,
                stderr=sys.stderr
            )
            process.wait()
            return process.returncode
        except Exception as e:
            logger.error(f"Failed to run {command}: {e}")
            return 1


    @staticmethod
    def _run_command(command: str, args: Optional[List[str]] = None, env: Optional[Dict[str, str]] = None, on_finished: Optional[Callable[[int, QProcess.ExitStatus], None]] = None) -> QProcess:
        """Run a command asynchronously using QProcess (for GUI mode)."""
        if args is None:
            args = []
            
        process = QProcess()
        Actions._running_processes.append(process)

        def cleanup(exit_code: int, exit_status: QProcess.ExitStatus) -> None:
            """Clean up the process after it finishes."""
            if process in Actions._running_processes:
                Actions._running_processes.remove(process)
            process.deleteLater()
            if callable(on_finished):
                on_finished(exit_code, exit_status)

        process.finished.connect(cleanup)
        process.errorOccurred.connect(lambda error: logger.error(f"Failed to run {command}: {error}"))

        if env:
            env_obj = QProcessEnvironment.systemEnvironment()
            for key, value in env.items():
                env_obj.insert(key, value)
            process.setProcessEnvironment(env_obj)

        process.start(command, args)
        return process


    @staticmethod
    def show_info_message(message: str, parent: Optional[Any] = None, duration: int = 1500, title: str = "Protontricks at Home") -> None:
        """Display a temporary informational message in a dialog."""
        msg_box = QMessageBox(parent)
        msg_box.setWindowTitle(title)
        msg_box.setText(message)
        msg_box.setIcon(QMessageBox.Information)
        msg_box.show()
        QTimer.singleShot(duration, msg_box.close)


    @staticmethod
    def copy_with_feedback(text: str, message: str, parent: Optional[Any] = None) -> None:
        """Copy text to clipboard and show a confirmation message."""
        QApplication.clipboard().setText(text)
        Actions.show_info_message(message, parent)


    @staticmethod
    def open_compatfolder(path: str, parent: Optional[Any] = None) -> None:
        """Open a folder in the file manager."""
        Actions.show_info_message("Opening folder...", parent)
        Actions._run_command("xdg-open", [path])


    @staticmethod
    def run_winetricks(path: str, parent: Optional[Any] = None) -> None:
        """Launch Winetricks for a given Wine prefix."""
        Actions.show_info_message("Launching Winetricks...", parent)
        Actions._run_command("winetricks", [], {"WINEPREFIX": path})


    @staticmethod
    def launch_game(install: SteamInstallation, type: str, appid: str, parent: Optional[Any] = None) -> None:
        """Launch a game through the selected Steam installation."""
        if type == "steam":
            url = f"steam://rungameid/{appid}"
        elif type == "shortcut":
            appid_64 = (int(appid) << 32) | 0x02000000
            url = f"steam://rungameid/{appid_64}"
        else:
            logger.warning(f"Unknown game type: {type}")
            return

        cmd = install.command + [url]
        
        try:
            Actions._run_command(cmd[0], cmd[1:])
        except Exception as e:
            logger.warning(f"Failed to launch with {install.name} Steam: {e}")
            logger.warning("Falling back to xdg-open")
            Actions._run_command("xdg-open", [url])