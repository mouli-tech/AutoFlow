# 🚀 AutoFlow — Personal Workflow Automation Engine

A local automation tool that runs on your Linux laptop, letting you define **workflows** (sequences of actions) triggered by **events** — all managed through a sleek web dashboard or YAML config files.

## Features

- **Visual Dashboard** — Create, edit, and run workflows from a beautiful web UI
- **YAML Workflows** — Define workflows as simple YAML files
- **6 Built-in Actions** — Open apps, URLs, run commands, notifications, calendar checks, conditionals
- **Smart Triggers** — Login, cron schedules, intervals, or manual
- **Google Calendar** — Check upcoming meetings and send reminders
- **Execution Logs** — Full history of every workflow run
- **CLI** — Run workflows from the terminal
- **Autostart** — Runs automatically on login via systemd/XDG autostart

## Quick Start

### 1. Install

```bash
cd /home/user/personal-projects/new_one
pip install -e .
```

### 2. Start the Dashboard

```bash
autoflow daemon
```

Open **http://localhost:8000** in your browser.

### 3. Run a Workflow from CLI

```bash
autoflow run morning_routine
```

### 4. List Workflows

```bash
autoflow list
```

## CLI Commands

| Command | Description |
|---------|-------------|
| `autoflow daemon` | Start the server + scheduler |
| `autoflow run <name>` | Run a workflow by name or file path |
| `autoflow list` | List all YAML workflows |
| `autoflow install-autostart` | Auto-start on login |
| `autoflow uninstall-autostart` | Remove autostart |

## Writing Workflows

Create a `.yaml` file in the `workflows/` directory:

```yaml
name: My Workflow
description: What it does
trigger:
  type: cron          # manual, login, cron, interval
  cron: "0 9 * * *"   # every day at 9 AM
steps:
  - action: open_app
    params:
      command: code    # VS Code

  - action: open_url
    params:
      url: https://github.com

  - action: notify
    params:
      title: "Ready!"
      message: "Your workspace is set up"
```

### Available Actions

| Action | Description | Key Params |
|--------|-------------|------------|
| `open_app` | Launch a desktop app | `command`, `args` |
| `open_url` | Open URL in browser | `url` |
| `run_command` | Run a shell command | `command`, `timeout`, `cwd` |
| `notify` | Desktop notification | `title`, `message`, `urgency` |
| `calendar_check` | Check Google Calendar | `calendar_id`, `lookahead_hours` |
| `conditional` | If/else branching | `condition` + `then`/`else` steps |

## Google Calendar Setup

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a project and enable the **Google Calendar API**
3. Create **OAuth 2.0 credentials** (Desktop app type)
4. Download the JSON and save it to:
   ```
   ~/.autoflow/google/client_secret.json
   ```
5. On first calendar check, a browser will open for OAuth authorization

## Autostart on Login

To run AutoFlow automatically when you log in:

```bash
autoflow install-autostart
```

This creates an XDG autostart entry that launches `autoflow daemon` on login.

## Project Structure

```
autoflow/          — Python backend
  engine/          — Workflow engine, executor, registry
  actions/         — Action plugins (open_app, notify, etc.)
  triggers/        — Scheduler, login autostart
  api/             — FastAPI routes & database
  db/              — SQLAlchemy models
dashboard/         — Web UI (HTML/CSS/JS)
workflows/         — YAML workflow definitions
```

## License

MIT
