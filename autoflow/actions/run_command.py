from __future__ import annotations

import logging
import os
import subprocess
import xml.etree.ElementTree as ET
from typing import Any

from autoflow.actions.base import ActionResult, BaseAction, register_action

log = logging.getLogger(__name__)


def _load_pycharm_env(env_from: str) -> dict[str, str]:
    """Load environment variables from a PyCharm run configuration.

    Format: "project_path::config_name"
    e.g. "~/Projects/analytics_workspace_app::PROD - UAT"
    """
    if "::" not in env_from:
        log.warning("env_from_pycharm format must be 'project_path::config_name', got: %s", env_from)
        return {}

    project_path, config_name = env_from.split("::", 1)
    project_path = os.path.expanduser(project_path)
    # Try fuzzy resolve if path doesn't exist
    if not os.path.isdir(project_path):
        project_path = _resolve_cwd(project_path)

    workspace_xml = os.path.join(project_path, ".idea", "workspace.xml")
    if not os.path.isfile(workspace_xml):
        log.warning("workspace.xml not found at %s", workspace_xml)
        return {}

    try:
        tree = ET.parse(workspace_xml)
    except Exception as e:
        log.warning("Failed to parse %s: %s", workspace_xml, e)
        return {}

    for conf in tree.getroot().iter("configuration"):
        if conf.get("name", "").strip() == config_name.strip():
            env_vars = {}
            for env_el in conf.iter("env"):
                name = env_el.get("name", "")
                value = env_el.get("value", "")
                if name:
                    # Replace PyCharm variables
                    value = value.replace("$PROJECT_DIR$", project_path)
                    value = value.replace("$USER_HOME$", os.path.expanduser("~"))
                    env_vars[name] = value
            log.info("Loaded %d env vars from PyCharm config '%s'", len(env_vars), config_name)
            return env_vars

    log.warning("PyCharm config '%s' not found in %s", config_name, workspace_xml)
    return {}


def _resolve_cwd(cwd: str) -> str:
    """Resolve a cwd path, falling back to a fuzzy search if it doesn't exist.

    If the exact path doesn't exist, extract the directory basename and search
    common locations (~/ children and their subdirectories) for a match.
    """
    expanded = os.path.expanduser(cwd)
    if os.path.isdir(expanded):
        return expanded

    target = os.path.basename(expanded)
    if not target:
        return expanded

    home = os.path.expanduser("~")
    try:
        home_entries = os.listdir(home)
    except OSError:
        return expanded

    for entry in sorted(home_entries):
        entry_path = os.path.join(home, entry)
        if not os.path.isdir(entry_path):
            continue
        # Direct match: ~/entry == target
        if entry == target:
            log.info("cwd '%s' not found, resolved to '%s'", cwd, entry_path)
            return entry_path
        # Check one level deeper: ~/entry/target
        candidate = os.path.join(entry_path, target)
        if os.path.isdir(candidate):
            log.info("cwd '%s' not found, resolved to '%s'", cwd, candidate)
            return candidate

    return expanded  # fallback to original (will fail with a clear error)


@register_action("run_command")
class RunCommandAction(BaseAction):
    def execute(self, params: dict, context=None) -> ActionResult:
        command = params.get("command")
        if not command:
            return ActionResult(success=False, message="Missing 'command' param")

        use_shell = params.get("shell", True)
        timeout = int(params.get("timeout", 60))
        cwd = params.get("cwd", None)

        # Expand ~ and resolve to real path (with fuzzy fallback)
        if cwd:
            cwd = _resolve_cwd(cwd)

        if isinstance(command, str):
            command = os.path.expanduser(command)
            # Handle redundant "cd <path>" — the cwd already sets the directory.
            # Resolve paths in cd commands so they don't fail on wrong paths.
            stripped = command.strip()
            if stripped.startswith("cd "):
                cd_target = stripped[3:].strip().strip("'\"")
                resolved_target = _resolve_cwd(cd_target)
                if os.path.isdir(resolved_target):
                    # cd is redundant when cwd is set; just update cwd and succeed
                    log.info("Converted 'cd %s' to cwd='%s'", cd_target, resolved_target)
                    return ActionResult(
                        success=True,
                        message=f"Changed directory to {resolved_target}",
                        data={"cwd": resolved_target},
                    )
            # Resolve any paths embedded in the command text
            command = _resolve_paths_in_command(command)

        # Build environment: inherit current env + optional PyCharm config env
        run_env = None
        env_from = params.get("env_from_pycharm")
        if env_from:
            pycharm_env = _load_pycharm_env(env_from)
            if pycharm_env:
                run_env = {**os.environ, **pycharm_env}

        background = params.get("background", False)
        if isinstance(background, str):
            background = background.lower() in ("true", "1", "yes")

        try:
            if background:
                # Launch as detached process (for long-running servers like npm start)
                proc = subprocess.Popen(
                    command, shell=use_shell,
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                    cwd=cwd, env=run_env, start_new_session=True,
                )
                return ActionResult(
                    success=True,
                    message=f"Started in background (pid {proc.pid})",
                    data={"pid": proc.pid},
                )

            result = subprocess.run(
                command, shell=use_shell, capture_output=True,
                text=True, timeout=timeout, cwd=cwd, env=run_env,
            )
            # Build a descriptive message including stderr on failure
            if result.returncode == 0:
                msg = f"Exit code: 0"
            else:
                stderr_snippet = result.stderr.strip()[:200]
                msg = f"Exit code: {result.returncode}"
                if stderr_snippet:
                    msg += f" — {stderr_snippet}"
                elif result.returncode == 127:
                    msg += f" — command not found: {command.split()[0] if command.split() else command}"
            return ActionResult(
                success=result.returncode == 0,
                message=msg,
                data={"stdout": result.stdout.strip(), "stderr": result.stderr.strip(), "returncode": result.returncode},
            )
        except subprocess.TimeoutExpired:
            return ActionResult(success=False, message=f"Timed out after {timeout}s")
        except Exception as e:
            return ActionResult(success=False, message=str(e))


def _resolve_paths_in_command(command: str) -> str:
    """Resolve path-like tokens in a command string using fuzzy matching."""
    import shlex
    try:
        tokens = shlex.split(command)
    except ValueError:
        return command

    changed = False
    for i, token in enumerate(tokens):
        # Only try to resolve tokens that look like absolute or ~ paths
        if not (token.startswith("/") or token.startswith("~")):
            continue
        expanded = os.path.expanduser(token)
        if os.path.exists(expanded):
            continue
        resolved = _resolve_cwd(token)
        if resolved != expanded:
            tokens[i] = resolved
            changed = True

    if changed:
        return " ".join(shlex.quote(t) for t in tokens)
    return command
