"""Lightweight filesystem context collector for AI prompt injection."""

from __future__ import annotations

import configparser
import os
import shlex
import time

_cache: str = ""
_cache_ts: float = 0.0
_TTL = 300  # 5 minutes

_MAX_DIRS_PER_ROOT = 30

# Markers that indicate a directory is a project
_PROJECT_MARKERS = (
    ".git", "package.json", "pyproject.toml", "Cargo.toml",
    "go.mod", "pom.xml", "build.gradle", "Makefile",
    "CMakeLists.txt", "setup.py", "requirements.txt",
    ".sln", "Gemfile", "pubspec.yaml", "composer.json",
)

# Home subdirectories to skip (system/config dirs, not project containers)
_SKIP_HOME_DIRS = frozenset({
    ".cache", ".config", ".local", ".npm", ".nvm", ".pyenv",
    ".rustup", ".cargo", ".gradle", ".m2", ".maven",
    ".ssh", ".gnupg", ".dbus", ".pki",
    "snap", ".snap", ".flatpak", ".var",
    ".vscode", ".cursor", ".jetbrains", ".java", ".android",
    ".mozilla", ".thunderbird", ".chrome",
    ".oh-my-zsh", ".zsh", ".bash_history",
    "__pycache__", "node_modules",
    ".Trash", ".trash",
})

# Standard freedesktop.org locations for .desktop files
_DESKTOP_DIRS = (
    "/usr/share/applications",
    "/usr/local/share/applications",
    os.path.expanduser("~/.local/share/applications"),
    "/var/lib/snapd/desktop/applications",
    "/var/lib/flatpak/exports/share/applications",
)

# System utilities that aren't useful for workflow generation
_IGNORED_APPS = frozenset({
    "true", "false", "env", "sh", "bash", "xdg-open",
})


def get_system_context() -> str:
    """Return cached filesystem context string, rescan if stale."""
    global _cache, _cache_ts
    now = time.monotonic()
    if _cache and (now - _cache_ts) < _TTL:
        return _cache
    _cache = _build_context()
    _cache_ts = now
    return _cache


def _build_context() -> str:
    home = os.path.expanduser("~")
    parts = [f"HOME={home}"]

    # Discover all usable directories dynamically
    dir_parts: list[str] = []
    for dir_name, subdirs in _discover_home_dirs(home):
        if subdirs:
            dir_parts.append(f"~/{dir_name}:{','.join(subdirs)}")
        else:
            dir_parts.append(f"~/{dir_name}")
    if dir_parts:
        parts.append("DIRS:" + ";".join(dir_parts))

    # Apps
    apps = _detect_apps()
    if apps:
        parts.append("APPS:" + ",".join(apps))

    # IDE run configurations (PyCharm, etc.)
    run_configs = _discover_ide_run_configs(home)
    if run_configs:
        parts.append("IDE_RUN_CONFIGS:\n" + "\n".join(run_configs))

    return "\n".join(parts)


def _is_project(path: str) -> bool:
    """Check if a directory looks like a project (has known markers)."""
    return any(os.path.exists(os.path.join(path, m)) for m in _PROJECT_MARKERS)


def _discover_home_dirs(home: str) -> list[tuple[str, list[str]]]:
    """Scan ~/ to find all usable directories and their notable contents.

    Returns ALL non-hidden, non-system home directories so the LLM can
    reference any of them (Documents, Downloads, Music, etc.), not just
    code project directories.  For dirs that contain projects, the project
    subdirectories are listed too.
    """
    results: list[tuple[str, list[str]]] = []
    try:
        home_entries = os.listdir(home)
    except OSError:
        return results

    for entry in sorted(home_entries):
        if entry.startswith(".") or entry.lower() in _SKIP_HOME_DIRS:
            continue
        entry_path = os.path.join(home, entry)
        if not os.path.isdir(entry_path):
            continue

        # Scan subdirectories — list projects if any, otherwise list all subdirs
        subdirs: list[str] = []
        projects: list[str] = []
        try:
            children = os.listdir(entry_path)
        except OSError:
            # Dir exists but not readable — still include it (no subdirs)
            results.append((entry, []))
            continue

        for sub in sorted(children):
            if sub.startswith("."):
                continue
            sub_path = os.path.join(entry_path, sub)
            if not os.path.isdir(sub_path):
                continue
            subdirs.append(sub)
            if _is_project(sub_path):
                projects.append(sub)

        # If the dir itself is a project, include with no children listed
        if _is_project(entry_path):
            results.append((entry, []))
        # If it contains projects, list those (most useful for the LLM)
        elif projects:
            results.append((entry, projects[:_MAX_DIRS_PER_ROOT]))
        # Otherwise list all subdirectories (e.g. ~/Documents/invoices, ~/Downloads)
        elif subdirs:
            results.append((entry, subdirs[:_MAX_DIRS_PER_ROOT]))
        else:
            # Empty or flat directory — still include it
            results.append((entry, []))

    return results


def _detect_apps() -> list[str]:
    """Discover installed GUI apps by scanning .desktop files."""
    apps: dict[str, str] = {}  # exec_name -> display_name

    for desktop_dir in _DESKTOP_DIRS:
        try:
            entries = os.listdir(desktop_dir)
        except OSError:
            continue
        for fname in entries:
            if not fname.endswith(".desktop"):
                continue
            path = os.path.join(desktop_dir, fname)
            result = _parse_desktop_file(path)
            if result:
                exec_name, display_name = result
                if exec_name not in apps:
                    apps[exec_name] = display_name

    # Format as "exec_cmd(Display Name)" so the LLM knows both
    return sorted(
        f"{cmd}({name})" if name.lower() != cmd else cmd
        for cmd, name in apps.items()
    )


def _parse_desktop_file(path: str) -> tuple[str, str] | None:
    """Extract executable and display name from a .desktop file."""
    cfg = configparser.ConfigParser(interpolation=None)
    try:
        cfg.read(path, encoding="utf-8")
    except Exception:
        return None

    section = "Desktop Entry"
    if not cfg.has_section(section):
        return None

    # Skip hidden/no-display entries
    if cfg.get(section, "NoDisplay", fallback="").lower() == "true":
        return None
    if cfg.get(section, "Hidden", fallback="").lower() == "true":
        return None
    # Only care about Application type
    if cfg.get(section, "Type", fallback="") != "Application":
        return None

    exec_raw = cfg.get(section, "Exec", fallback="")
    if not exec_raw:
        return None

    # Extract the base command (first token, strip field codes like %U %f)
    try:
        tokens = shlex.split(exec_raw)
    except ValueError:
        tokens = exec_raw.split()
    cmd = os.path.basename(tokens[0]) if tokens else ""
    if not cmd or cmd in _IGNORED_APPS:
        return None

    name = cfg.get(section, "Name", fallback=cmd)
    return cmd, name


def _discover_ide_run_configs(home: str) -> list[str]:
    """Discover IDE run configurations from project .idea/workspace.xml files.

    Scans all project directories for PyCharm/IntelliJ run configurations and
    returns compact descriptions the LLM can use to generate correct steps.
    """
    import xml.etree.ElementTree as ET

    results: list[str] = []

    # Find all .idea/workspace.xml files in project directories
    for entry in os.listdir(home):
        entry_path = os.path.join(home, entry)
        if not os.path.isdir(entry_path) or entry.startswith("."):
            continue
        # Check direct project
        _scan_idea_workspace(entry_path, entry, results, ET)
        # Check one level deeper (project containers)
        try:
            for sub in os.listdir(entry_path):
                sub_path = os.path.join(entry_path, sub)
                if os.path.isdir(sub_path) and not sub.startswith("."):
                    _scan_idea_workspace(sub_path, f"{entry}/{sub}", results, ET)
        except OSError:
            continue

    return results


def _scan_idea_workspace(project_path: str, project_label: str, results: list[str], ET) -> None:
    """Parse a single .idea/workspace.xml for run configurations."""
    workspace_xml = os.path.join(project_path, ".idea", "workspace.xml")
    if not os.path.isfile(workspace_xml):
        return

    try:
        tree = ET.parse(workspace_xml)
    except Exception:
        return

    configs: list[str] = []
    for conf in tree.getroot().iter("configuration"):
        name = conf.get("name", "")
        ctype = conf.get("type", "")
        if conf.get("temporary") == "true" or not name:
            continue

        # Extract the actual command/script
        opts = {opt.get("name", ""): opt.get("value", "") for opt in conf.iter("option")}

        if ctype == "PythonConfigurationType":
            script = opts.get("SCRIPT_NAME", "")
            script = script.replace("$PROJECT_DIR$", project_path)
            wdir = opts.get("WORKING_DIRECTORY", "").replace("$PROJECT_DIR$", project_path)
            # Count env vars (don't expose values — they contain secrets)
            env_count = sum(1 for e in conf.iter("env") if e.get("name"))
            env_str = f" env={env_count}vars" if env_count else ""
            configs.append(f"  '{name}':python {script} cwd={wdir}{env_str}")
        elif ctype == "ShConfigurationType":
            script_text = opts.get("SCRIPT_TEXT", "")
            script_text = script_text.replace("$USER_HOME$", os.path.expanduser("~"))
            wdir = opts.get("SCRIPT_WORKING_DIRECTORY", "").replace("$PROJECT_DIR$", project_path)
            configs.append(f"  '{name}':sh {script_text} cwd={wdir}")
        elif ctype == "js.build_tools.npm":
            cmd = opts.get("run-configuration-script-name", "")
            configs.append(f"  '{name}':npm {cmd}")

    if configs:
        results.append(f"  project=~/{project_label}:")
        results.extend(configs)
