from __future__ import annotations

import webbrowser
from typing import Any

from autoflow.actions.base import ActionResult, BaseAction, register_action


@register_action("open_url")
class OpenUrlAction(BaseAction):
    def execute(self, params: dict, context=None) -> ActionResult:
        url = params.get("url")
        if not url:
            return ActionResult(success=False, message="Missing 'url' param")

        new_tab = params.get("new_tab", True)
        try:
            webbrowser.open(url, new=2 if new_tab else 0)
            return ActionResult(success=True, message=f"Opened {url}")
        except Exception as e:
            return ActionResult(success=False, message=f"Failed to open URL: {e}")
