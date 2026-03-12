from __future__ import annotations

import configparser
import logging
import os
import shlex
import shutil
import subprocess
from typing import Any

from autoflow.actions.base import ActionResult, BaseAction, register_action

log = logging.getLogger(__name__)

# Standard freedesktop.org locations for .desktop files
_DESKTOP_DIRS = (
    "/usr/share/applications",
    "/usr/local/share/applications",
    os.path.expanduser("~/.local/share/applications"),
    "/var/lib/snapd/desktop/applications",
    "/var/lib/flatpak/exports/share/applications",
)


def _build_app_index() -> dict[str, list[str]]:
    """Build a keyword→executables index from installed .desktop files.

    Maps lowercased app names and exec basenames to actual executables,
    so any partial/generic name can resolve to the real binary.
    e.g. "pycharm" → ["pycharm-community"], "chrome" → ["google-chrome-stable"]
    """
    # exec_cmd → set of keywords (lowercase name words + exec basename)
    app_keywords: dict[str, set[str]] = {}

    for desktop_dir in _DESKTOP_DIRS:
        try:
            entries = os.listdir(desktop_dir)
        except OSError:
            continue
        for fname in entries:
            if not fname.endswith(".desktop"):
                continue
            path = os.path.join(desktop_dir, fname)
            cfg = configparser.ConfigParser(interpolation=None)
            try:
                cfg.read(path, encoding="utf-8")
            except Exception:
                continue
            section = "Desktop Entry"
            if not cfg.has_section(section):
                continue
            if cfg.get(section, "Type", fallback="") != "Application":
                continue

            exec_raw = cfg.get(section, "Exec", fallback="")
            if not exec_raw:
                continue
            try:
                tokens = shlex.split(exec_raw)
            except ValueError:
                tokens = exec_raw.split()
            if not tokens:
                continue
            exec_cmd = os.path.basename(tokens[0])
            if not exec_cmd or not shutil.which(exec_cmd):
                continue

            name = cfg.get(section, "Name", fallback="")
            keywords: set[str] = set()
            # Add each word from the display name
            for word in name.lower().split():
                if len(word) > 2:  # skip tiny words like "of", "to"
                    keywords.add(word)
            # Add the exec basename and parts split by dash
            keywords.add(exec_cmd.lower())
            for part in exec_cmd.lower().split("-"):
                if len(part) > 2:
                    keywords.add(part)
            # Add the .desktop filename stem parts
            stem = fname.removesuffix(".desktop").lower()
            for part in stem.replace("_", "-").split("-"):
                if len(part) > 2:
                    keywords.add(part)

            app_keywords[exec_cmd] = keywords

    # Invert: keyword → list of exec commands
    index: dict[str, list[str]] = {}
    for exec_cmd, keywords in app_keywords.items():
        for kw in keywords:
            index.setdefault(kw, []).append(exec_cmd)
    return index


# Build once at import time (cheap — just reads .desktop files)
_APP_INDEX = _build_app_index()


def find_app_alternatives(command: str) -> list[str]:
    """Find installed executables matching a command name."""
    cmd_lower = command.lower()
    candidates = _APP_INDEX.get(cmd_lower, [])
    # Deduplicate while preserving order, exclude the original command
    seen: set[str] = set()
    result: list[str] = []
    for c in candidates:
        if c not in seen and c != command:
            seen.add(c)
            result.append(c)
    return result


@register_action("open_app")
class OpenAppAction(BaseAction):
    def execute(self, params: dict, context=None) -> ActionResult:
        command = params.get("command")
        if not command:
            return ActionResult(success=False, message="Missing 'command' param")

        args = params.get("args", [])
        # Ensure args is always a list (AI may generate a string)
        if isinstance(args, str):
            args = [args] if args else []
        # Expand ~ in args and resolve paths that don't exist
        from autoflow.actions.run_command import _resolve_cwd
        resolved_args = []
        for a in args:
            if isinstance(a, str) and ("/" in a or a.startswith("~")):
                resolved_args.append(_resolve_cwd(a))
            else:
                resolved_args.append(a)
        args = resolved_args

        # Resolve command: try original first, then dynamically find alternatives
        resolved = shutil.which(command)
        if not resolved:
            for alt in find_app_alternatives(command):
                resolved = shutil.which(alt)
                if resolved:
                    log.info("'%s' not found, using fallback '%s'", command, alt)
                    command = alt
                    break

        wait = params.get("wait", False)
        full_cmd = [resolved or command] + args

        try:
            proc = subprocess.Popen(
                full_cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
            if wait:
                proc.wait()
            return ActionResult(success=True, message=f"Launched {command} (pid {proc.pid})", data={"pid": proc.pid})
        except FileNotFoundError:
            tried = [command] + find_app_alternatives(command)
            return ActionResult(success=False, message=f"Not found: {command}. Tried: {', '.join(tried)}")
        except Exception as e:
            return ActionResult(success=False, message=f"Failed to open {command}: {e}")
