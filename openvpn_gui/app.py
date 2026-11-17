"""Main window (PySide6)."""
from __future__ import annotations

from pathlib import Path

from keyring.errors import KeyringError
from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication, QIcon
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QDialog, QDialogButtonBox, QFileDialog, QFormLayout, QFrame,
    QHBoxLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem, QMainWindow, QMenu,
    QMessageBox, QPlainTextEdit, QPushButton, QStackedWidget, QSystemTrayIcon, QVBoxLayout, QWidget,
)

from . import vault
from .graph import TrafficGraph
from .icons import make_icon
from .rates import human_rate
from .manager import VpnSession
from .profiles import Profile, import_profile, load_profiles, remove_profile

STATES = {
    "STARTING": "Waiting for authorization…", "CONNECTING": "Connecting…",
    "WAIT": "Waiting for the server…", "AUTH": "Authenticating…",
    "GET_CONFIG": "Getting configuration…", "ASSIGN_IP": "Assigning IP address…",
    "ADD_ROUTES": "Adding routes…", "CONNECTED": "Connected",
    "RECONNECTING": "Reconnecting…", "EXITING": "Disconnecting…",
    "AUTH_FAILED": "Authentication rejected", "DISCONNECTED": "Disconnected",
}

STYLE = """
#page { background: #f4f5f7; color: #1f2a44; }
#sidebar { background: #1f2a44; }
#brand { color: white; font-size: 17px; font-weight: 600; padding: 4px 6px 10px 6px; }
#sidebar QListWidget { background: transparent; border: none; color: #dfe4f0; outline: 0; }
#sidebar QListWidget::item { padding: 10px 12px; border-radius: 6px; }
#sidebar QListWidget::item:selected { background: #2f3d63; color: white; }
#title { font-size: 22px; font-weight: 600; color: #1f2a44; }
#muted { color: #6b7488; }
#card { background: white; border: 1px solid #e1e4ea; border-radius: 10px; }
#card QLabel, #card QCheckBox { color: #1f2a44; background: transparent; }
QLineEdit, QPlainTextEdit { background: white; color: #1f2a44; border: 1px solid #ccd1dc;
    border-radius: 6px; padding: 6px; }
#primary { background: #ff6c1a; color: white; border: none; border-radius: 8px;
    padding: 12px 22px; font-weight: 600; font-size: 14px; }
#primary:disabled { background: #c9ccd4; }
#primary[connected="true"] { background: #c0392b; }
#secondary { background: #e3e6ed; color: #1f2a44; border: none; border-radius: 8px;
    padding: 12px 22px; font-weight: 600; font-size: 14px; }
#secondary:hover { background: #d6dae4; }
QDialog#page QLabel { color: #1f2a44; background: transparent; }
QLineEdit#mfa { font-size: 24px; font-family: monospace; padding: 10px; }
#import { background: #2f3d63; color: white; border: none; border-radius: 6px; padding: 9px; }
"""


def human(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024


class AuthDialog(QDialog):
    """Asks for the MFA code (and, after a rejection, the username and password again)."""

    def __init__(self, parent, challenge: str, echo: bool, retry: bool, user: str, password: str):
        super().__init__(parent)
        self.setObjectName("page")
        self.setWindowTitle("Authentication")
        self.setMinimumWidth(440)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(26, 22, 26, 20)
        lay.setSpacing(12)

        title = QLabel("Two-step verification" if challenge else "Confirm your credentials")
        title.setStyleSheet("font-size: 17px; font-weight: 600;")
        lay.addWidget(title)

        if retry:
            warn = QLabel("The server rejected the credentials. Check them and try again.")
            warn.setWordWrap(True)
            warn.setStyleSheet("color: #c0392b;")
            lay.addWidget(warn)

        self.ed_user, self.ed_pass, self.ed_mfa = QLineEdit(user), QLineEdit(password), None
        self.ed_pass.setEchoMode(QLineEdit.EchoMode.Password)
        if retry:
            form = QFormLayout()
            form.addRow("Username", self.ed_user)
            form.addRow("Password", self.ed_pass)
            lay.addLayout(form)

        if challenge:
            hint = QLabel(challenge)
            hint.setWordWrap(True)
            lay.addWidget(hint)
            self.ed_mfa = QLineEdit()
            self.ed_mfa.setObjectName("mfa")
            self.ed_mfa.setAlignment(Qt.AlignmentFlag.AlignCenter)
            if not echo:
                self.ed_mfa.setEchoMode(QLineEdit.EchoMode.Password)
            lay.addWidget(self.ed_mfa)
            self.ed_mfa.setFocus()

        lay.addSpacing(6)
        box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        ok = box.button(QDialogButtonBox.StandardButton.Ok)
        cancel = box.button(QDialogButtonBox.StandardButton.Cancel)
        ok.setText("Confirm")
        cancel.setText("Cancel")
        ok.setIcon(QIcon())
        cancel.setIcon(QIcon())
        ok.setObjectName("primary")
        cancel.setObjectName("secondary")
        ok.setDefault(True)  # Enter confirms
        box.accepted.connect(self.accept)
        box.rejected.connect(self.reject)
        lay.addWidget(box)

    def values(self) -> tuple[str, str, str | None]:
        mfa = self.ed_mfa.text().strip() if self.ed_mfa else None
        return self.ed_user.text().strip(), self.ed_pass.text(), mfa


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("OpenVPN GUI")
        self.resize(900, 700)
        self.setWindowIcon(make_icon("idle"))
        self.setAcceptDrops(True)
        self.setStyleSheet(STYLE)

        self.profiles = load_profiles()
        self.current: Profile | None = None
        self.session: VpnSession | None = None
        self._quit_when_done = False
        self._tip_shown = False
        self._status_text = "Disconnected"
        self.tray: QSystemTrayIcon | None = None

        # ---- sidebar ----
        side = QWidget()
        side.setObjectName("sidebar")
        side.setFixedWidth(250)
        sl = QVBoxLayout(side)
        brand = QLabel("OpenVPN GUI")
        brand.setObjectName("brand")
        self.list = QListWidget()
        self.list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.list.customContextMenuRequested.connect(self._list_menu)
        self.list.currentRowChanged.connect(self._on_row)
        self.btn_import = QPushButton("＋  Import profile (.ovpn)")
        self.btn_import.setObjectName("import")
        self.btn_import.clicked.connect(self._import_dialog)
        sl.addWidget(brand)
        sl.addWidget(self.list, 1)
        sl.addWidget(self.btn_import)

        # ---- empty page ----
        empty = QWidget()
        empty.setObjectName("page")
        el = QVBoxLayout(empty)
        msg = QLabel("No profile selected\n\nDrag an .ovpn file onto this window\nor use the “Import profile” button.")
        msg.setObjectName("muted")
        msg.setAlignment(Qt.AlignmentFlag.AlignCenter)
        el.addWidget(msg)

        # ---- profile page ----
        page = QWidget()
        page.setObjectName("page")
        pl = QVBoxLayout(page)
        pl.setContentsMargins(32, 28, 32, 24)
        self.lbl_name, self.lbl_server = QLabel(), QLabel()
        self.lbl_name.setObjectName("title")
        self.lbl_server.setObjectName("muted")

        self.creds = QFrame()
        self.creds.setObjectName("card")
        form = QFormLayout(self.creds)
        form.setContentsMargins(18, 16, 18, 16)
        self.ed_user, self.ed_pass = QLineEdit(), QLineEdit()
        self.ed_pass.setEchoMode(QLineEdit.EchoMode.Password)
        self.ed_pass.returnPressed.connect(self._enter_pressed)
        self.chk_save = QCheckBox("Save username and password in the system keyring")
        self.lbl_mfa = QLabel()
        self.lbl_mfa.setObjectName("muted")
        form.addRow("Username", self.ed_user)
        form.addRow("Password", self.ed_pass)
        form.addRow("", self.chk_save)
        form.addRow("", self.lbl_mfa)

        self.btn = QPushButton("Connect")
        self.btn.setObjectName("primary")
        self.btn.clicked.connect(self._toggle)
        self.lbl_status, self.lbl_traffic = QLabel("Disconnected"), QLabel()
        self.lbl_status.setStyleSheet("font-weight: 600;")
        self.lbl_traffic.setObjectName("muted")
        self.graph = TrafficGraph()
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setMaximumBlockCount(2000)
        self.log.setStyleSheet("font-family: monospace; font-size: 11px;")

        pl.addWidget(self.lbl_name)
        pl.addWidget(self.lbl_server)
        pl.addSpacing(14)
        pl.addWidget(self.creds)
        pl.addSpacing(10)
        pl.addWidget(self.btn)
        pl.addWidget(self.lbl_status)
        pl.addWidget(self.lbl_traffic)
        pl.addWidget(self.graph)
        pl.addWidget(self.log, 1)

        self.stack = QStackedWidget()
        self.stack.addWidget(empty)
        self.stack.addWidget(page)

        root = QWidget()
        rl = QHBoxLayout(root)
        rl.setContentsMargins(0, 0, 0, 0)
        rl.setSpacing(0)
        rl.addWidget(side)
        rl.addWidget(self.stack, 1)
        self.setCentralWidget(root)

        self._refresh_list()
        self._setup_tray()

    # ---------- profiles ----------
    def _refresh_list(self, select_id: str | None = None) -> None:
        self.list.blockSignals(True)
        self.list.clear()
        for p in self.profiles:
            self.list.addItem(QListWidgetItem(p.name))
        self.list.blockSignals(False)
        row = next((i for i, p in enumerate(self.profiles) if p.id == select_id), 0 if self.profiles else -1)
        self.list.setCurrentRow(row)
        self._on_row(row)

    def _on_row(self, row: int) -> None:
        if row < 0 or row >= len(self.profiles):
            self.current = None
            self.stack.setCurrentIndex(0)
            return
        p = self.current = self.profiles[row]
        self.stack.setCurrentIndex(1)
        self.lbl_name.setText(p.name)
        self.lbl_server.setText(f"Server: {p.server}")
        self.creds.setVisible(p.needs_auth)
        self.lbl_mfa.setText("This profile uses a second factor: the code will be requested when you connect."
                             if p.mfa_text else "")
        self.lbl_mfa.setVisible(bool(p.mfa_text))
        saved = vault.load(p.id)
        self.ed_user.setText(saved[0] if saved else "")
        self.ed_pass.setText(saved[1] if saved else "")
        self.chk_save.setChecked(saved is not None)

    def _import_dialog(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Import profile", str(Path.home()), "OpenVPN profiles (*.ovpn *.conf);;All files (*)")
        if path:
            self._import_path(Path(path))

    def _import_path(self, path: Path) -> None:
        try:
            p = import_profile(path)
        except (OSError, ValueError) as e:
            QMessageBox.warning(self, "Could not import", str(e))
            return
        self.profiles.append(p)
        self._refresh_list(p.id)

    def _list_menu(self, pos) -> None:
        item = self.list.itemAt(pos)
        if not item or self.session:
            return
        menu = QMenu(self)
        act = menu.addAction("Remove profile")
        if menu.exec(self.list.mapToGlobal(pos)) is act:
            p = self.profiles[self.list.row(item)]
            if QMessageBox.question(self, "Remove", f"Remove “{p.name}” and its saved credentials?") \
                    == QMessageBox.StandardButton.Yes:
                remove_profile(p)
                vault.delete(p.id)
                self.profiles = [x for x in self.profiles if x.id != p.id]
                self._refresh_list()

    def dragEnterEvent(self, ev) -> None:
        if ev.mimeData().hasUrls():
            ev.acceptProposedAction()

    def dropEvent(self, ev) -> None:
        for url in ev.mimeData().urls():
            path = url.toLocalFile()
            if path.lower().endswith((".ovpn", ".conf")):
                self._import_path(Path(path))

    # ---------- connection ----------
    def _enter_pressed(self) -> None:
        if not self.session:
            self._start()

    def _toggle(self) -> None:
        if self.session:
            self.btn.setEnabled(False)
            self.session.stop()
        else:
            self._start()

    def _start(self) -> None:
        p = self.current
        user, pw = self.ed_user.text().strip(), self.ed_pass.text()
        if p.needs_auth and (not user or not pw):
            QMessageBox.information(self, "Credentials", "Enter your username and password.")
            return
        if not self.chk_save.isChecked():
            vault.delete(p.id)
        self.log.clear()
        self.lbl_traffic.clear()
        self.graph.reset()
        s = self.session = VpnSession(p, self)
        s.state_changed.connect(self._on_state)
        s.log.connect(self.log.appendPlainText)
        s.traffic.connect(self._on_traffic)
        s.auth_requested.connect(self._on_auth)
        self._set_busy(True)
        s.start(user, pw)

    def _on_auth(self, challenge: str, echo: bool, retry: bool) -> None:
        s = self.session
        dlg = AuthDialog(self, challenge, echo, retry, s.username, s.password)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            s.submit_auth(*dlg.values())
        else:
            s.stop()

    def _on_state(self, code: str, detail: str) -> None:
        if code == "FAILED":
            text, color = f"Failed: {detail}", "#c0392b"
        else:
            text = STATES.get(code, code)
            if code == "CONNECTED" and detail:
                text += f" — IP {detail}"
            color = {"CONNECTED": "#1e8e3e", "AUTH_FAILED": "#c0392b"}.get(code, "#1f2a44")
        self.lbl_status.setText(text)
        self.lbl_status.setStyleSheet(f"font-weight: 600; color: {color};")

        if code == "CONNECTED":
            self._save_credentials()
        elif code in ("DISCONNECTED", "FAILED"):
            if self.session:
                self.session.deleteLater()
                self.session = None
            self._set_busy(False)
            self.lbl_traffic.clear()
            if self._quit_when_done:
                QApplication.quit()
                return
        self._status_text = text
        self._update_tray(code)

    def _save_credentials(self) -> None:
        if self.chk_save.isChecked() and self.session and self.current:
            try:  # only save after a successful authentication
                vault.save(self.current.id, self.session.username, self.session.password)
                self.log.appendPlainText("[gui] Credentials saved to the keyring.")
            except KeyringError as e:
                self.log.appendPlainText(f"[gui] Could not save to the keyring: {e}")

    def _set_busy(self, busy: bool) -> None:
        self.btn.setText("Disconnect" if busy else "Connect")
        self.btn.setProperty("connected", busy)
        self.btn.style().unpolish(self.btn)
        self.btn.style().polish(self.btn)
        self.btn.setEnabled(True)
        for w in (self.creds, self.list, self.btn_import):
            w.setEnabled(not busy)

    # ---------- traffic ----------
    def _on_traffic(self, rx: int, tx: int) -> None:
        self.lbl_traffic.setText(f"Total — ↓ {human(rx)}    ↑ {human(tx)}")
        self.graph.add_sample(rx, tx)
        self._refresh_tray_tip()

    # ---------- system tray ----------
    def _setup_tray(self) -> None:
        if not QSystemTrayIcon.isSystemTrayAvailable():
            return  # no tray (e.g. GNOME without the extension): closing the window quits the app
        tray = QSystemTrayIcon(make_icon("idle"), self)
        menu = QMenu(self)
        menu.addAction("Show / hide window").triggered.connect(self._toggle_window)
        self.act_disconnect = menu.addAction("Disconnect")
        self.act_disconnect.setEnabled(False)
        self.act_disconnect.triggered.connect(self._tray_disconnect)
        menu.addSeparator()
        menu.addAction("Quit").triggered.connect(self._request_quit)
        tray.setContextMenu(menu)
        tray.activated.connect(self._tray_activated)
        tray.setToolTip("OpenVPN GUI — Disconnected")
        tray.show()
        self.tray, self._tray_menu = tray, menu

    def _update_tray(self, code: str) -> None:
        if not self.tray:
            return
        kind = "connected" if code == "CONNECTED" else \
            "idle" if code in ("DISCONNECTED", "FAILED") else "busy"
        icon = make_icon(kind)
        self.tray.setIcon(icon)
        self.setWindowIcon(icon)
        self.act_disconnect.setEnabled(self.session is not None)
        self._refresh_tray_tip()

    def _refresh_tray_tip(self) -> None:
        if not self.tray:
            return
        tip = f"OpenVPN GUI — {self._status_text}"
        if self.session and self._status_text.startswith("Connected"):
            down, up = self.graph.rates()
            tip += f"\n↓ {human_rate(down)}   ↑ {human_rate(up)}"
        self.tray.setToolTip(tip)

    def _tray_activated(self, reason) -> None:
        if reason == QSystemTrayIcon.ActivationReason.Trigger:  # single click
            self._toggle_window()

    def _toggle_window(self) -> None:
        if self.isVisible():
            self.hide()
        else:
            self.bring_to_front()

    def bring_to_front(self) -> None:
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def _tray_disconnect(self) -> None:
        if self.session:
            self.btn.setEnabled(False)
            self.session.stop()

    def _request_quit(self) -> None:
        if self.session:
            self.bring_to_front()
            ask = QMessageBox.question(self, "Quit", "There is an active connection. Disconnect and quit?")
            if ask == QMessageBox.StandardButton.Yes:
                self._quit_when_done = True
                self.session.stop()
        else:
            QApplication.quit()

    def closeEvent(self, ev) -> None:
        inst = QGuiApplication.instance()  # isSavingSession() is an instance method, not a static one
        if inst is not None and inst.isSavingSession():  # the session is ending (logout/shutdown): do not get in the way
            ev.accept()
            return
        ev.ignore()
        if self.tray:
            self.hide()  # the connection keeps running; the tray icon stays active
            print("[gui] Window minimized to the system tray; the connection stays active. "
                  "Click the tray icon to reopen it, or use “Quit” in its menu to exit.", flush=True)
            if not self._tip_shown:
                self._tip_shown = True
                self.tray.showMessage(
                    "OpenVPN GUI is still running",
                    "Click the icon to open the window. To exit, use “Quit” in the icon’s menu.",
                    QSystemTrayIcon.MessageIcon.Information, 6000)
        else:
            self._request_quit()
