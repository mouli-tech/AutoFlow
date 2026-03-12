from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from autoflow.actions.base import ActionResult, BaseAction, register_action
from autoflow.config import GOOGLE_CLIENT_SECRET, GOOGLE_TOKEN

log = logging.getLogger(__name__)


@register_action("calendar_check")
class CalendarCheckAction(BaseAction):
    def execute(self, params: dict, context=None) -> ActionResult:
        calendar_id = params.get("calendar_id", "primary")
        lookahead_hours = params.get("lookahead_hours", 24)

        try:
            service = self._get_service()
            if service is None:
                return ActionResult(success=False, message="Google Calendar not configured. See README.")

            now = datetime.now(timezone.utc)
            end = now + timedelta(hours=lookahead_hours)

            result = service.events().list(
                calendarId=calendar_id,
                timeMin=now.isoformat(),
                timeMax=end.isoformat(),
                singleEvents=True,
                orderBy="startTime",
            ).execute()

            events = result.get("items", [])
            summaries = []
            for ev in events:
                start = ev["start"].get("dateTime", ev["start"].get("date"))
                summaries.append(f"- {start}: {ev.get('summary', 'No title')}")

            return ActionResult(
                success=True,
                message=f"Found {len(events)} event(s)",
                data={
                    "has_events": len(events) > 0,
                    "event_count": len(events),
                    "calendar_events": events,
                    "event_summary": "\n".join(summaries) or "No upcoming events",
                },
            )
        except Exception as e:
            log.error("Calendar check failed: %s", e)
            return ActionResult(success=False, message=f"Calendar check failed: {e}")

    def _get_service(self):
        try:
            from google.oauth2.credentials import Credentials
            from google_auth_oauthlib.flow import InstalledAppFlow
            from google.auth.transport.requests import Request
            from googleapiclient.discovery import build
        except ImportError:
            return None

        if not GOOGLE_CLIENT_SECRET.exists():
            return None

        SCOPES = ["https://www.googleapis.com/auth/calendar.readonly"]
        creds = None

        if GOOGLE_TOKEN.exists():
            creds = Credentials.from_authorized_user_file(str(GOOGLE_TOKEN), SCOPES)

        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                flow = InstalledAppFlow.from_client_secrets_file(str(GOOGLE_CLIENT_SECRET), SCOPES)
                creds = flow.run_local_server(port=0)

            GOOGLE_TOKEN.parent.mkdir(parents=True, exist_ok=True)
            with open(GOOGLE_TOKEN, "w") as f:
                f.write(creds.to_json())

        return build("calendar", "v3", credentials=creds)
