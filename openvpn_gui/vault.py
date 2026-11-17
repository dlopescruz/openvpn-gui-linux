"""Stores the username/password in the system keyring (GNOME Keyring, KWallet, ...).

The app never writes credentials to a file: encryption is handled by the Secret Service,
which is unlocked together with the user's login. The MFA code never goes through here.
"""
from __future__ import annotations

import json

import keyring
from keyring.errors import KeyringError

SERVICE = "openvpn-gui"


def save(profile_id: str, username: str, password: str) -> None:
    """May raise KeyringError (e.g. no keyring available)."""
    keyring.set_password(SERVICE, profile_id, json.dumps({"u": username, "p": password}))


def load(profile_id: str) -> tuple[str, str] | None:
    try:
        raw = keyring.get_password(SERVICE, profile_id)
        if not raw:
            return None
        data = json.loads(raw)
        return data["u"], data["p"]
    except (KeyringError, ValueError, KeyError):
        return None


def delete(profile_id: str) -> None:
    try:
        keyring.delete_password(SERVICE, profile_id)
    except KeyringError:
        pass  # it did not exist, or there is no keyring: either way, nothing to do
