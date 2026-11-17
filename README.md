# OpenVPN GUI for Linux

A simple graphical client for [OpenVPN](https://openvpn.net/) on Linux, built with Python and Qt (PySide6).
Import your `.ovpn` profile, sign in with username, password and an MFA code, and watch your traffic live —
no terminal needed.

> **Disclaimer:** this is an independent community project. It is not affiliated with, endorsed by, or
> sponsored by OpenVPN Inc. It drives the standard `openvpn` binary installed on your system.

<img width="985" height="733" alt="image" src="https://github.com/user-attachments/assets/6673bf46-9edc-45b6-adb1-9dd10068d547" />
<img width="1136" height="783" alt="image" src="https://github.com/user-attachments/assets/dde38e82-355c-4cb9-9b35-b3fc173063bd" />


## Features

- **Import profiles** with a button or by dragging an `.ovpn` file onto the window
- **Username and password**, with an optional *Save* checkbox that stores them in the system keyring
  (GNOME Keyring, KWallet or any Secret Service provider) - never in a plain file
- **MFA support**: the one-time code is requested only when the server asks for it and is never stored
  (OpenVPN `static-challenge`)
- **Live status**, byte counters and a real-time download/upload graph (last ~4 minutes)
- **System tray icon** (grey / orange / green by state): closing the window hides it and the connection keeps
  running; the tray menu offers *Show / hide*, *Disconnect* and *Quit*
- **Single instance**: launching the app again brings the running window to the front
- **Runs unprivileged**: only the `openvpn` process is elevated (via polkit's `pkexec`)

Tested on **Nobara Linux 44** (Fedora-based) with a profile that uses a client certificate, username/password
and an MFA `static-challenge`. The package names for Debian/Ubuntu and openSUSE below come from the distros'
package catalogs but have not been verified on each system - please open an issue if one is wrong.

## Requirements

- Linux with a graphical desktop (KDE, GNOME, XFCE, ...) and Python 3.9+
- `openvpn` installed
- `pkexec` (polkit) and a user allowed to gain administrator rights (OpenVPN must create a network
  interface, which needs root)
- PySide6 (Qt 6) and the Python `keyring` library
- A running keyring service (GNOME Keyring, KWallet, ...) - only needed for the *Save* option

## Installation

Clone the repository (or unpack a release) into a permanent folder - the desktop launcher stores its path:

```bash
git clone https://github.com/dlopescruz/openvpn-gui-linux.git ~/openvpn-gui
cd ~/openvpn-gui
```

### Debian / Ubuntu

Works with the PySide6 wheels from PyPI inside a virtual environment (Debian 12/13, Ubuntu 22.04+):

```bash
sudo apt update
sudo apt install openvpn pkexec python3 python3-venv python3-pip libxcb-cursor0

python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

On older releases without a `pkexec` package (for example Ubuntu 22.04), install `policykit-1` instead.

*Alternative without a venv (Debian 13+, Ubuntu 24.10+)*, using the distribution's per-module PySide6 packages:

```bash
sudo apt install openvpn pkexec python3-pyside6.qtcore python3-pyside6.qtgui \
    python3-pyside6.qtwidgets python3-pyside6.qtnetwork python3-keyring
```

### Fedora (and Nobara)

```bash
sudo dnf install openvpn polkit python3-pyside6 python3-keyring xcb-util-cursor
```

`pkexec` is part of the `polkit` package. To use PySide6 from PyPI instead, create a venv as shown above.

### openSUSE

Tumbleweed (system packages):

```bash
sudo zypper install openvpn polkit python3-pyside6 python3-keyring libxcb-cursor0
```

Leap (or if a package above is missing) - use a venv with PySide6 from PyPI:

```bash
sudo zypper install openvpn polkit python3 python3-pip libxcb-cursor0

python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

On openSUSE the polkit prompt usually asks for the **root** password instead of your own.

### Keyring and system tray

- **GNOME / Ubuntu:** GNOME Keyring is installed by default and unlocked at login.
- **KDE:** KWallet provides the Secret Service.
- **Other desktops:** install `gnome-keyring`, or use KeePassXC with its Secret Service integration enabled.

KDE, XFCE and most desktops show tray icons natively. **GNOME** needs the *AppIndicator and
KStatusNotifierItem Support* extension:

```bash
sudo apt install gnome-shell-extension-appindicator    # Debian/Ubuntu (usually enabled by default on Ubuntu)
sudo dnf install gnome-shell-extension-appindicator    # Fedora
```

Enable it in the *Extensions* app and log out and back in. If no tray is available, closing the window simply
quits the app (after asking for confirmation if a connection is active).

## Running

From the project folder:

```bash
# with a virtual environment
source .venv/bin/activate
python -m openvpn_gui

# with system packages
python3 -m openvpn_gui
```

### Application menu launcher

```bash
bash install-shortcut.sh              # creates the "OpenVPN GUI" launcher and icon
bash install-shortcut.sh --autostart  # same, and also start the app when you log in
bash install-shortcut.sh --remove     # removes the launcher, icon and autostart entry
```

The script uses the project's `.venv` if it exists, otherwise the system `python3`. If you move the folder,
run the script again. The launcher may take a moment (or a re-login) to appear in your menu.

## Usage

1. **Import a profile.** Click *Import profile (.ovpn)* or drag the file onto the window. The profile is copied
   to `~/.local/share/openvpn-gui/profiles/` with owner-only permissions, so the original can be deleted.
2. **Enter your credentials.** Fill in *Username* and *Password*. Tick *Save username and password in the
   system keyring* to keep them; they are only saved after a successful connection.
3. **Connect.** Click *Connect*. The system shows a polkit prompt asking for administrator authorization.
4. **Enter the MFA code** when the *Two-step verification* dialog appears, then press *Confirm* (or Enter).
   The code is never saved.
5. **Monitor the connection.** The status shows *Connected* and your VPN IP, the tray icon turns green, and the
   graph shows download (blue) and upload (orange) speed. The log shows OpenVPN's output.
6. **Run in the background.** Closing the window hides it in the tray; the connection stays up. Click the tray
   icon to show or hide the window. *Quit* in the tray menu exits the app (asking first if connected).
7. **Disconnect** with the *Disconnect* button or from the tray menu.
8. **Remove a profile** (while disconnected): right-click it in the list and choose *Remove profile*. This also
   deletes the saved credentials from the keyring.

If the server rejects your username, password or code, the authentication dialog reopens with a warning and
editable username/password fields, without restarting the connection.

## How it works

```
GUI (your user)  <--- TCP 127.0.0.1:random port + random password --->  openvpn (root, via pkexec)
```

1. The GUI starts: `pkexec openvpn --config <profile> --management 127.0.0.1 <port> <passwordfile>
   --management-query-passwords --management-hold --auth-retry interact --auth-nocache`
2. It connects to OpenVPN's [Management Interface](https://openvpn.net/community-resources/management-interface/)
   on a random local port, protected by a random password stored in a `0600` temporary file.
3. When the server asks for credentials, the GUI answers with `username` / `password` commands
   (using the `SCRV1:` format when a `static-challenge` is present) - nothing sensitive is written to disk or
   put on a command line.
4. State changes and byte counters stream back over the same channel; *Disconnect* sends `signal SIGTERM`.

Project layout:

| Path | Purpose |
| --- | --- |
| `openvpn_gui/app.py` | Main window, authentication dialog, system tray |
| `openvpn_gui/manager.py` | Starts OpenVPN and speaks the Management Interface (Qt) |
| `openvpn_gui/protocol.py` | Pure protocol helpers (no Qt) - unit tested |
| `openvpn_gui/profiles.py` | Parsing, importing and storing `.ovpn` profiles |
| `openvpn_gui/vault.py` | Keyring access for saved credentials |
| `openvpn_gui/rates.py`, `graph.py` | Speed calculation and the traffic graph |
| `openvpn_gui/icons.py` | Tray/window icons generated in code |
| `install-shortcut.sh` | Application-menu launcher installer |
| `tests/test_core.py` | Tests for everything that does not need Qt |

## Security notes

- An imported `.ovpn` usually contains your **private key**. The app keeps it in a folder readable only by your
  user (`~/.local/share/openvpn-gui/`). **Never commit `.ovpn` files to a repository** (they are in `.gitignore`).
- The GUI runs as a regular user; only OpenVPN is elevated, after a polkit authorization.
- Running `openvpn` with an arbitrary profile is equivalent to root access (profiles can run scripts). Only
  import profiles from sources you trust, and **do not add a polkit rule that lets `pkexec` run without a
  password**. A hardened helper that validates the profile (blocking `up`, `down`, `plugin`, `script-security`)
  would be the right way to remove the password prompt.
- Credentials live in the system keyring. The MFA code is never stored.

## Troubleshooting

**Qt "xcb" platform plugin error on start.** Install the Qt cursor library: `libxcb-cursor0` (Debian, Ubuntu,
openSUSE) or `xcb-util-cursor` (Fedora). Run `QT_DEBUG_PLUGINS=1 python -m openvpn_gui` to see exactly which
library is missing.

**`pip` says "externally-managed-environment".** Use a virtual environment (`python3 -m venv .venv`) as shown
in the installation steps instead of installing into the system Python.

**"pkexec (polkit) not found".** Install the polkit package for your distribution (see *Installation*).

**"The system did not authorize running OpenVPN (polkit)".** Your user needs administrator rights (group `sudo`
on Debian/Ubuntu, `wheel` on Fedora), and a polkit authentication agent must be running in your session
(KDE and GNOME provide one).

**"Authorization cancelled".** The polkit prompt was dismissed. Click *Connect* again.

**"Could not save to the keyring".** The keyring is not running or is locked. Unlock it (or install one, see
*Keyring and system tray*) and connect again with *Save* ticked.

**No tray icon on GNOME.** Install and enable the AppIndicator extension (see above).

**Connected but names or internal hosts do not resolve.** Check the log. DNS handling depends on your
distribution's OpenVPN: recent versions apply server-pushed DNS settings automatically; older ones may need an
`up` script in the profile.

**Launcher missing from the menu, or it does nothing.** Reopen the menu or log out and back in. If it still does
nothing, run `python -m openvpn_gui` inside the project folder to see the error, and re-run
`bash install-shortcut.sh` if you moved the folder.

**Launched the app again and nothing happened.** That is expected: only one instance runs, and launching again
raises the window that is hidden in the tray.

## Updating and uninstalling

**Update:** `git pull` (and `pip install -r requirements.txt` again if you use a venv). Your profiles and saved
credentials live outside the project folder and are kept. If the folder moved, re-run `bash install-shortcut.sh`.

**Uninstall:**

```bash
cd ~/openvpn-gui && bash install-shortcut.sh --remove   # launcher, icon, autostart entry
rm -rf ~/.local/share/openvpn-gui                       # imported profiles
rm -rf ~/openvpn-gui                                    # the program itself
```

To remove saved passwords too, open your keyring manager (Passwords and Keys / Seahorse on GNOME, KWalletManager
on KDE) and delete the entries for the `openvpn-gui` service.

## Known limitations

- Dynamic challenge/response (`CRV1`) and password-protected private keys are not supported yet
- No automatic reconnect, and no *Connect* action in the tray menu
- The interface is English only
- Not yet packaged (`.deb` / `.rpm` / Flatpak)

## Development

```bash
python3 tests/test_core.py     # or: pytest tests/
```

The tests cover the profile parser, the Management Interface protocol helpers and the speed calculation.
The Qt parts have no automated tests yet. Contributions and bug reports are welcome - when reporting a
connection problem, please attach the log from the window and **remove any tokens, IP addresses or
certificates you do not want to share**.

## License

Released under the MIT License - see [LICENSE](LICENSE).
