import os
import sys

from PySide6.QtNetwork import QLocalServer, QLocalSocket
from PySide6.QtWidgets import QApplication

from .app import MainWindow


def main() -> None:
    app = QApplication(sys.argv)
    app.setApplicationName("OpenVPN GUI")
    app.setDesktopFileName("openvpn-gui")  # matches the openvpn-gui.desktop launcher
    app.setQuitOnLastWindowClosed(False)  # closing the window only hides it (system tray)

    # Single instance: launching the app again raises the window of the running one.
    name = f"openvpn-gui-{os.getuid()}"
    probe = QLocalSocket()
    probe.connectToServer(name)
    if probe.waitForConnected(300):
        probe.write(b"show")
        probe.waitForBytesWritten(300)
        return

    window = MainWindow()
    server = QLocalServer()
    QLocalServer.removeServer(name)  # clean up a stale socket left by a crashed run
    server.listen(name)

    def on_connection() -> None:
        conn = server.nextPendingConnection()
        if conn:
            conn.deleteLater()
        window.bring_to_front()

    server.newConnection.connect(on_connection)
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
