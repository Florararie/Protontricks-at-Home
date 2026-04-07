import os
import logging

from PySide6.QtWidgets import QApplication, QMessageBox
from PySide6.QtCore import QTimer, QProcess, QProcessEnvironment



logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')



class Actions():
    _running_processes = []


    @staticmethod
    def _run_command(command: str, args=None, env: dict = None, on_finished=None):
        if args is None:
            args = []
            
        process = QProcess()
        Actions._running_processes.append(process)

        def cleanup(exit_code, exit_status):
            if process in Actions._running_processes:
                Actions._running_processes.remove(process)
            process.deleteLater()
            if callable(on_finished):
                on_finished(exit_code, exit_status)

        process.finished.connect(cleanup)
        process.errorOccurred.connect(lambda error: logging.error(f"Failed to run {command}: {error}"))

        if env:
            env_obj = QProcessEnvironment.systemEnvironment()
            for key, value in env.items():
                env_obj.insert(key, value)
            process.setProcessEnvironment(env_obj)

        process.start(command, args)
        return process


    @staticmethod
    def show_info_message(message: str, parent=None, duration: int = 1500, title: str = "Protontricks at Home"):
        msg_box = QMessageBox(parent)
        msg_box.setWindowTitle(title)
        msg_box.setText(message)
        msg_box.setIcon(QMessageBox.Information)
        msg_box.show()
        QTimer.singleShot(duration, msg_box.close)


    @staticmethod
    def copy_with_feedback(text: str, message: str, parent=None):
        QApplication.clipboard().setText(text)
        Actions.show_info_message(message, parent)


    @staticmethod
    def open_compatfolder(path: str, parent=None):
        Actions.show_info_message("Opening folder...", parent)
        Actions._run_command("xdg-open", [path])


    @staticmethod
    def run_winetricks(path: str, parent=None):
        Actions.show_info_message("Launching Winetricks...", parent)
        Actions._run_command("winetricks", [], {"WINEPREFIX": path})


    @staticmethod
    def launch_game(type: str, appid: str, parent=None):
        if type == "steam":
            url = f"steam://rungameid/{appid}"
        elif type == "shortcut":
            appid_64 = (int(appid) << 32) | 0x02000000
            url = f"steam://rungameid/{appid_64}"
        else:
            logging.warning(f"Unknown game type: {type}")
            return

        Actions._run_command("xdg-open", [url])