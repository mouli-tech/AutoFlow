from __future__ import annotations

import subprocess
from typing import Any

from autoflow.actions.base import ActionResult, BaseAction, register_action


@register_action("notify")
class NotifyAction(BaseAction):
    def execute(self, params: dict, context=None) -> ActionResult:
        title = params.get("title", "AutoFlow")
        message = params.get("message", "")
        urgency = params.get("urgency", "normal")
        icon = params.get("icon", "dialog-information")
        timeout_ms = params.get("timeout", 5000)

        # Use StepContext variables for template rendering (backward compat with _context)
        variables = {}
        if context is not None:
            variables = context.variables
        elif "_context" in params:
            variables = params["_context"]
        message = self._render(message, variables)
        title = self._render(title, variables)

        cmd = ["notify-send", "--urgency", urgency, "--icon", icon, "--expire-time", str(timeout_ms), title, message]

        try:
            subprocess.run(cmd, check=True, capture_output=True, text=True)
            return ActionResult(success=True, message=f"Sent: {title}")
        except FileNotFoundError:
            return ActionResult(success=False, message="notify-send not found (apt install libnotify-bin)")
        except subprocess.CalledProcessError as e:
            return ActionResult(success=False, message=f"Failed: {e.stderr}")
        except Exception as e:
            return ActionResult(success=False, message=str(e))

    @staticmethod
    def _render(text: str, context: dict) -> str:
        for key, value in context.items():
            placeholder = "{{ " + key + " }}"
            if placeholder in text:
                if isinstance(value, list):
                    text = text.replace(placeholder, "\n".join(str(v) for v in value))
                else:
                    text = text.replace(placeholder, str(value))
        return text
