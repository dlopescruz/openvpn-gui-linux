"""Importing and storing .ovpn profiles."""
from __future__ import annotations

import json
import os
import shlex
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path

MAX_SIZE = 1_000_000  # 1 MB - real profiles are only a few KB


def data_dir() -> Path:
    base = Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share")
    root = base / "openvpn-gui"
    (root / "profiles").mkdir(parents=True, exist_ok=True)
    os.chmod(root, 0o700)
    os.chmod(root / "profiles", 0o700)
    return root


@dataclass
class Profile:
    id: str
    name: str
    server: str            # first 'remote' (display only)
    needs_auth: bool       # has 'auth-user-pass' without a file
    mfa_text: str | None   # 'static-challenge' prompt, if any

    @property
    def path(self) -> Path:
        return data_dir() / "profiles" / f"{self.id}.ovpn"


def parse_ovpn(text: str) -> dict:
    """Extract from the .ovpn only what the UI needs to know."""
    server, needs_auth, mfa_text = None, False, None
    block = None  # inside <ca>...</ca>, <key>...</key>, etc.
    for raw in text.splitlines():
        line = raw.strip()
        if block:
            if line == f"</{block}>":
                block = None
            continue
        if line.startswith("<") and line.endswith(">") and not line.startswith("</"):
            block = line[1:-1]
            continue
        if not line or line[0] in "#;":
            continue
        try:
            parts = shlex.split(line)
        except ValueError:
            continue
        if not parts:
            continue
        key = parts[0]
        if key == "remote" and len(parts) >= 2 and server is None:
            server = parts[1] + (f":{parts[2]}" if len(parts) > 2 else "")
        elif key == "auth-user-pass" and len(parts) == 1:
            needs_auth = True
        elif key == "static-challenge" and len(parts) >= 2:
            mfa_text = parts[1]
    return {"server": server, "needs_auth": needs_auth, "mfa_text": mfa_text}


def _index_path() -> Path:
    return data_dir() / "profiles.json"


def _save_index(profiles: list[Profile]) -> None:
    tmp = _index_path().with_suffix(".tmp")
    tmp.write_text(json.dumps([asdict(p) for p in profiles], indent=2), encoding="utf-8")
    os.chmod(tmp, 0o600)
    tmp.replace(_index_path())


def load_profiles() -> list[Profile]:
    try:
        items = json.loads(_index_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    profiles = []
    for item in items:
        try:
            p = Profile(**item)
        except TypeError:
            continue
        if p.path.exists():
            profiles.append(p)
    return profiles


def import_profile(src: Path) -> Profile:
    """Copy the .ovpn into the app folder (mode 0600: it contains the private key)."""
    if src.stat().st_size > MAX_SIZE:
        raise ValueError("File too large to be an OpenVPN profile.")
    text = src.read_text(encoding="utf-8", errors="replace")
    info = parse_ovpn(text)
    if info["server"] is None:
        raise ValueError("No 'remote' directive found - this does not look like an OpenVPN profile.")
    profile = Profile(id=uuid.uuid4().hex, name=src.stem, **info)
    fd = os.open(profile.path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(text)
    _save_index(load_profiles() + [profile])
    return profile


def remove_profile(profile: Profile) -> None:
    profile.path.unlink(missing_ok=True)
    _save_index([p for p in load_profiles() if p.id != profile.id])
