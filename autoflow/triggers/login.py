from __future__ import annotations

import sys
from pathlib import Path

AUTOSTART_DIR = Path.home() / ".config" / "autostart"
DESKTOP_FILE = AUTOSTART_DIR / "autoflow.desktop"


def _desktop_entry() -> str:
    return f"""[Desktop Entry]
Type=Application
Name=AutoFlow
Comment=Personal Workflow Automation
Exec={sys.executable} -m autoflow daemon
Hidden=false
NoDisplay=true
X-GNOME-Autostart-enabled=true
StartupNotify=false
Terminal=false
"""


def install_autostart() -> bool:
    try:
        AUTOSTART_DIR.mkdir(parents=True, exist_ok=True)
        DESKTOP_FILE.write_text(_desktop_entry())
        return True
    except Exception:
        return False


def uninstall_autostart() -> bool:
    try:
        if DESKTOP_FILE.exists():
            DESKTOP_FILE.unlink()
        return True
    except Exception:
        return False


def is_autostart_installed() -> bool:
    return DESKTOP_FILE.exists()
