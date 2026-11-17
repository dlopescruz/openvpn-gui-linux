"""Tests for the parts that do not need Qt. Run: python3 tests/test_core.py  (or pytest)."""
import base64
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ["XDG_DATA_HOME"] = tempfile.mkdtemp()

from openvpn_gui import protocol  # noqa: E402
from openvpn_gui.rates import RateTracker, human_rate, nice_ceiling  # noqa: E402
from openvpn_gui.profiles import import_profile, load_profiles, parse_ovpn, remove_profile  # noqa: E402

SAMPLE = """client
remote vpn.example.com 1194 udp
remote vpn.example.com 1194 tcp
auth-user-pass
static-challenge "Second factor token" 1
<ca>
-----BEGIN CERTIFICATE-----
remote must.not.be.read 1 udp
-----END CERTIFICATE-----
</ca>
"""


def test_parse():
    info = parse_ovpn(SAMPLE)
    assert info == {"server": "vpn.example.com:1194", "needs_auth": True, "mfa_text": "Second factor token"}


def test_need_auth():
    assert protocol.parse_need_auth("Need 'Auth' username/password SC:1,Second factor token") == ("Second factor token", True)
    assert protocol.parse_need_auth("Need 'Auth' username/password SC:0,Codigo") == ("Codigo", False)
    assert protocol.parse_need_auth("Need 'Auth' username/password") == (None, False)
    assert protocol.parse_need_auth("Need 'Private Key' password") is None


def test_auth_commands():
    user_cmd, pw_cmd = protocol.auth_commands("ana", 'se"nha\\', "123456")
    assert user_cmd == 'username "Auth" "ana"'
    secret = pw_cmd.split('"Auth" ', 1)[1].strip('"').replace('\\\\', '\\').replace('\\"', '"')
    tag, pw64, mfa64 = secret.split(":")
    assert tag == "SCRV1"
    assert base64.b64decode(pw64).decode() == 'se"nha\\'
    assert base64.b64decode(mfa64).decode() == "123456"
    # without MFA the password is sent as-is
    assert protocol.auth_commands("a", "b", None)[1] == 'password "Auth" "b"'
    # a line break must not be able to inject another command
    assert "\n" not in protocol.auth_commands("a\nsignal SIGTERM", "b", None)[0]


def test_state_and_bytecount():
    assert protocol.parse_state("1700000000,CONNECTED,SUCCESS,10.8.0.2,1.2.3.4,1194,,") == ("CONNECTED", "10.8.0.2")
    assert protocol.parse_state("1700000000,AUTH,,,,,,") == ("AUTH", "")
    assert protocol.parse_bytecount("1234,5678") == (1234, 5678)


def test_import_roundtrip():
    src = Path(tempfile.mkdtemp()) / "meu.ovpn"
    src.write_text(SAMPLE)
    p = import_profile(src)
    assert p.name == "meu" and oct(p.path.stat().st_mode & 0o777) == "0o600"
    assert [x.id for x in load_profiles()] == [p.id]
    remove_profile(p)
    assert load_profiles() == []


def test_bad_file():
    bad = Path(tempfile.mkdtemp()) / "x.ovpn"
    bad.write_text("this is not a profile\n")
    try:
        import_profile(bad)
    except ValueError:
        return
    raise AssertionError("should have been rejected")


def test_password_kind():
    k = protocol.password_kind
    assert k("Need 'Auth' username/password SC:1,Token") == "auth"
    assert k("Verification Failed: 'Auth'") == "failed"
    # regression: the auth-token arrives right after CONNECTED and must NOT drop the connection
    assert k("Auth-Token:SESS_ID_abc123") == "token"
    assert k("Need 'Private Key' password") == "unsupported"
    assert k("algo novo") == "other"


def test_rates():
    t = RateTracker(window=3)
    t.add(0, 0, now=0.0)                      # the first sample only sets the baseline
    assert t.latest() == (0.0, 0.0)
    t.add(2000, 1000, now=2.0)
    assert t.latest() == (1000.0, 500.0)
    t.add(500, 100, now=4.0)                  # counters were reset (reconnect) -> 0, never negative
    assert t.latest() == (0.0, 0.0)
    for i in range(5):
        t.add(10_000 * (i + 1), 0, now=6.0 + 2 * i)
    assert len(t.down) == 3                   # sliding window is respected
    t.reset()
    assert t.latest() == (0.0, 0.0)


def test_formatting():
    assert human_rate(512) == "512 B/s"
    assert human_rate(1536) == "1.5 KB/s"
    assert human_rate(5 * 1024 * 1024) == "5.0 MB/s"
    assert nice_ceiling(1126) == 2000
    assert nice_ceiling(1000) == 1000
    assert nice_ceiling(4800) == 5000
    assert nice_ceiling(7_300_000) == 10_000_000


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok ", name)
