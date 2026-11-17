"""Pure helpers (no Qt) for talking to the OpenVPN Management Interface.

Kept separate from the rest so they can be tested without a GUI.
Reference: https://openvpn.net/community-resources/management-interface/
"""
from __future__ import annotations

import base64
import re

# >PASSWORD:Need 'Auth' username/password SC:1,Challenge text
_NEED_AUTH = re.compile(
    r"Need 'Auth' username/password(?: SC:(?P<echo>[01]),(?P<text>.*))?$"
)


def esc(value: str) -> str:
    """Escape an argument for the Management Interface (and strip line breaks,
    which would allow injecting other commands)."""
    value = value.replace("\r", "").replace("\n", "")
    return value.replace("\\", "\\\\").replace('"', '\\"')


def b64(value: str) -> str:
    return base64.b64encode(value.encode("utf-8")).decode("ascii")


def parse_need_auth(msg: str) -> tuple[str | None, bool] | None:
    """Parse the text that follows '>PASSWORD:'.

    Returns None if it is not a username/password request. Otherwise returns
    (challenge_text_or_None, echo); echo=True means the MFA code may be shown
    while typing (the 2nd argument of static-challenge).
    """
    m = _NEED_AUTH.match(msg)
    if not m:
        return None
    return m.group("text"), m.group("echo") == "1"


def auth_commands(user: str, password: str, mfa: str | None) -> list[str]:
    """Commands that answer an 'Auth' credentials request.

    With static-challenge the password is sent as SCRV1:base64(password):base64(code).
    """
    secret = password if mfa is None else f"SCRV1:{b64(password)}:{b64(mfa)}"
    return [f'username "Auth" "{esc(user)}"', f'password "Auth" "{esc(secret)}"']


def parse_state(payload: str) -> tuple[str, str]:
    """'>STATE:' payload -> (state, detail). For CONNECTED the detail is the local IP."""
    f = payload.split(",")
    state = f[1] if len(f) > 1 else ""
    if state == "CONNECTED" and len(f) > 3:
        return state, f[3]
    return state, f[2] if len(f) > 2 else ""


def parse_bytecount(payload: str) -> tuple[int, int]:
    rx, tx = payload.split(",")[:2]
    return int(rx), int(tx)


def password_kind(msg: str) -> str:
    """Classify the text that follows '>PASSWORD:'.

    'failed'      - the server rejected the credentials
    'token'       - the server handed out an auth-token (arrives right after CONNECTED;
                    informational, NOT a request - and it must never be logged)
    'auth'        - username/password request ('Auth')
    'unsupported' - another request that needs an answer (e.g. a private key passphrase)
    'other'       - any other notification: ignore it
    """
    if msg.startswith("Verification Failed"):
        return "failed"
    if msg.startswith("Auth-Token:"):
        return "token"
    if parse_need_auth(msg) is not None:
        return "auth"
    if msg.startswith("Need "):
        return "unsupported"
    return "other"
