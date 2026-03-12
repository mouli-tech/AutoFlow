import os
from pathlib import Path

AUTOFLOW_HOME = Path(os.environ.get("AUTOFLOW_HOME", Path.home() / ".autoflow"))

DB_PATH = AUTOFLOW_HOME / "autoflow.db"
DATABASE_URL = f"sqlite:///{DB_PATH}"

WORKFLOWS_DIR = Path(os.environ.get(
    "AUTOFLOW_WORKFLOWS_DIR",
    Path(__file__).resolve().parent.parent / "workflows"
))

GOOGLE_CREDS_DIR = AUTOFLOW_HOME / "google"
GOOGLE_CLIENT_SECRET = GOOGLE_CREDS_DIR / "client_secret.json"
GOOGLE_TOKEN = GOOGLE_CREDS_DIR / "token.json"

DASHBOARD_DIR = Path(__file__).resolve().parent.parent / "dashboard"

LOG_DIR = AUTOFLOW_HOME / "logs"
LOG_FILE = LOG_DIR / "autoflow.log"

HOST = os.environ.get("AUTOFLOW_HOST", "127.0.0.1")
PORT = int(os.environ.get("AUTOFLOW_PORT", "8000"))
PID_FILE = AUTOFLOW_HOME / "autoflow.pid"
AI_SETTINGS_FILE = AUTOFLOW_HOME / "ai_settings.json"


def ensure_dirs():
    for d in [AUTOFLOW_HOME, GOOGLE_CREDS_DIR, LOG_DIR, WORKFLOWS_DIR]:
        d.mkdir(parents=True, exist_ok=True)
