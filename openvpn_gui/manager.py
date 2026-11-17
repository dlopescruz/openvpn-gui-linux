"""Runs OpenVPN (through pkexec) and talks to it over the Management Interface."""
from __future__ import annotations

import os
import secrets
import shutil
import socket
import tempfile

from PySide6.QtCore import QObject, QProcess, QTimer, Signal
from PySide6.QtNetwork import QHostAddress, QTcpSocket

from . import protocol
from .profiles import Profile

_OPENVPN_PATHS = ("/usr/sbin/openvpn", "/usr/local/sbin/openvpn", "/sbin/openvpn")


def _find_openvpn() -> str | None:
    # On Debian, /usr/sbin is usually not in a regular user's PATH.
    return shutil.which("openvpn") or next(
        (p for p in _OPENVPN_PATHS if os.access(p, os.X_OK)), None
    )


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class VpnSession(QObject):
    """One VPN connection. Emitted states: STARTING, CONNECTING, WAIT, AUTH, GET_CONFIG,
    ASSIGN_IP, ADD_ROUTES, CONNECTED, RECONNECTING, EXITING (from OpenVPN) and
    AUTH_FAILED, DISCONNECTED, FAILED (ours)."""

    state_changed = Signal(str, str)        # (state, detail)
    log = Signal(str)
    traffic = Signal(int, int)              # (bytes received, bytes sent)
    auth_requested = Signal(str, bool, bool)  # (MFA prompt, echo, is_retry)

    def __init__(self, profile: Profile, parent: QObject | None = None):
        super().__init__(parent)
        self._profile = profile
        self._proc: QProcess | None = None
        self._sock: QTcpSocket | None = None
        self._buf = ""
        self._port = 0
        self._mgmt_pw = secrets.token_urlsafe(24)
        self._pwfile: str | None = None
        self._mgmt_ok = False
        self._auth_failed = False
        self._stopping = False
        self.username = ""
        self.password = ""

    # ---------- lifecycle ----------
    def start(self, username: str, password: str) -> None:
        self.username, self.password = username, password
        openvpn, pkexec = _find_openvpn(), shutil.which("pkexec")
        if not openvpn or not pkexec:
            missing = "openvpn" if not openvpn else "pkexec (polkit)"
            self.state_changed.emit("FAILED", f"{missing} not found. Please install it first.")
            return

        self._port = _free_port()
        fd, self._pwfile = tempfile.mkstemp(prefix="ovpn-mgmt-", dir=os.environ.get("XDG_RUNTIME_DIR"))
        with os.fdopen(fd, "w") as f:  # mkstemp already creates the file with mode 0600
            f.write(self._mgmt_pw + "\n")

        args = [
            openvpn, "--config", str(self._profile.path),
            "--management", "127.0.0.1", str(self._port), self._pwfile,
            "--management-query-passwords",  # credentials come from the GUI, not the terminal
            "--management-hold",             # do not connect until 'hold release'
            "--auth-retry", "interact",      # wrong password/MFA -> ask again
            "--auth-nocache",                # do not cache the password inside OpenVPN
        ]
        proc = QProcess(self)
        proc.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)
        proc.readyRead.connect(self._on_output)
        proc.finished.connect(self._on_finished)
        proc.errorOccurred.connect(self._on_proc_error)
        self._proc = proc
        self.state_changed.emit("STARTING", "")
        proc.start(pkexec, args)
        QTimer.singleShot(300, self._try_connect)

    def stop(self) -> None:
        self._stopping = True
        if self._mgmt_ok and self._sock:
            self._cmd("signal SIGTERM")
        elif self._running():
            self._proc.terminate()
        QTimer.singleShot(8000, self._force_kill)

    def _force_kill(self) -> None:
        if self._running():
            self._proc.kill()

    def _running(self) -> bool:
        return self._proc is not None and self._proc.state() != QProcess.ProcessState.NotRunning

    # ---------- process ----------
    def _on_output(self) -> None:
        text = bytes(self._proc.readAll()).decode("utf-8", "replace")
        for line in text.splitlines():
            if line.strip():
                self.log.emit(line)

    def _on_proc_error(self, err) -> None:
        if err == QProcess.ProcessError.FailedToStart:
            self.state_changed.emit("FAILED", "Could not start pkexec.")

    def _on_finished(self, code: int, _status) -> None:
        proc, self._proc = self._proc, None
        if proc:
            proc.deleteLater()
        if self._sock:
            self._sock.deleteLater()
            self._sock = None
        self._mgmt_ok = False
        if self._pwfile:
            try:
                os.unlink(self._pwfile)
            except OSError:
                pass
            self._pwfile = None

        if self._stopping or code == 0:
            self.state_changed.emit("DISCONNECTED", "")
        elif code == 126:
            self.state_changed.emit("FAILED", "Authorization cancelled.")
        elif code == 127:
            self.state_changed.emit("FAILED", "The system did not authorize running OpenVPN (polkit).")
        else:
            self.state_changed.emit("FAILED", f"OpenVPN exited with an error (code {code}). Check the log.")

    # ---------- Management Interface ----------
    def _try_connect(self) -> None:
        if not self._running() or self._mgmt_ok:
            return
        sock = QTcpSocket(self)
        self._sock = sock
        sock.connected.connect(self._on_connected)
        sock.readyRead.connect(self._on_mgmt_data)
        sock.errorOccurred.connect(self._on_sock_error)
        sock.connectToHost(QHostAddress(QHostAddress.SpecialAddress.LocalHost), self._port)

    def _on_sock_error(self, _err) -> None:
        sock, self._sock = self._sock, None
        if sock:
            sock.deleteLater()
        if self._running() and not self._mgmt_ok:   # OpenVPN is still starting (or polkit is asking for the password)
            QTimer.singleShot(300, self._try_connect)

    def _on_connected(self) -> None:
        self._mgmt_ok = True
        self._sock.write((self._mgmt_pw + "\n").encode())

    def _cmd(self, text: str) -> None:
        if self._sock:
            self._sock.write((text + "\n").encode())

    def _on_mgmt_data(self) -> None:
        self._buf += bytes(self._sock.readAll()).decode("utf-8", "replace")
        while "\n" in self._buf:
            line, self._buf = self._buf.split("\n", 1)
            self._handle_line(line.rstrip("\r"))

    def _handle_line(self, line: str) -> None:
        # The "ENTER PASSWORD:" prompt has no trailing newline, so it arrives glued to the reply.
        line = line.removeprefix("ENTER PASSWORD:")
        if line.startswith("SUCCESS: password is correct"):
            self._cmd("state on")
            self._cmd("bytecount 2")
            self._cmd("hold release")
        elif line.startswith(">STATE:"):
            self.state_changed.emit(*protocol.parse_state(line[7:]))
        elif line.startswith(">BYTECOUNT:"):
            self.traffic.emit(*protocol.parse_bytecount(line[11:]))
        elif line.startswith(">PASSWORD:"):
            self._handle_password(line[10:])
        elif line.startswith(">FATAL:"):
            self.log.emit(line[7:])

    def _handle_password(self, msg: str) -> None:
        kind = protocol.password_kind(msg)
        if kind == "failed":
            self._auth_failed = True
            self.log.emit("[gui] The server rejected the authentication.")
            self.state_changed.emit("AUTH_FAILED", "")
        elif kind == "unsupported":
            self.log.emit(f"[gui] Request not supported by the app yet: {msg}")
            self.stop()  # e.g. a password-protected private key
        elif kind == "auth":
            challenge, echo = protocol.parse_need_auth(msg)
            retry, self._auth_failed = self._auth_failed, False
            if challenge or retry:
                self.auth_requested.emit(challenge or "", echo, retry)
            else:
                self.submit_auth(self.username, self.password, None)
        # 'token' and 'other': ignore (the auth-token is a secret and must never be logged)

    def submit_auth(self, user: str, password: str, mfa: str | None) -> None:
        self.username, self.password = user, password
        for cmd in protocol.auth_commands(user, password, mfa):
            self._cmd(cmd)
