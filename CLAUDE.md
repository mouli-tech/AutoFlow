# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

AutoFlow is a personal workflow automation engine for Linux. Users define workflows in YAML, manage them via a FastAPI web dashboard or Click-based CLI, and extend functionality through a plugin system. YAML files are the single source of truth; SQLite serves as a read cache for the dashboard.

## Commands

```bash
# Install (editable)
pip install -e .

# Install with dev dependencies
pip install -e ".[dev]"

# Run daemon (foreground, serves API + dashboard on localhost:8000)
autoflow daemon

# Background start/stop
autoflow start
autoflow stop
autoflow restart

# Run a workflow
autoflow run <workflow_name>

# List workflows
autoflow list

# Run tests
pytest

# Run a single test
pytest tests/test_file.py::test_name
```

## Architecture

### Core flow

CLI (`autoflow/main.py`) or FastAPI (`autoflow/api/app.py`) → `WorkflowService` → `WorkflowExecutor` → Middleware Pipeline → Action plugins

### Plugin system (`autoflow/actions/`)

- Actions extend `BaseAction` and use the `@register_action("name")` decorator
- Discovery is automatic: built-in actions are imported on `registry.discover()`, external actions can be registered via `pyproject.toml` entry points (`autoflow.actions` group)
- Actions receive a typed `StepContext` (not raw params injection) for shared variables, logging, and nested step execution

### Middleware pipeline (`autoflow/engine/middleware.py`)

Cross-cutting concerns are layered as middleware, not embedded in the executor or actions:

```
ErrorBoundary → Logging → Timeout → Retry → Action
```

Each middleware implements `StepMiddleware.__call__(params, context, next_fn, step_config)`.

### Execution modes (`autoflow/engine/executor.py`)

- **Sequential** (default): steps run in order
- **Parallel**: steps listed under `parallel:` run via `ThreadPoolExecutor`
- **DAG**: if any step has `depends_on`, the executor does topological sort

### Service layer (`autoflow/services/workflow_service.py`)

`WorkflowService` is the single CRUD interface. It writes YAML files and syncs to SQLite. Both CLI and API go through this layer.

### Scheduling (`autoflow/triggers/scheduler.py`)

APScheduler wraps cron, interval, and login trigger types. Configured per-workflow in YAML under `trigger:`.

## Commit Message Format

```
[ADD] : <message>    # new features
[FIX] : <message>    # bug fixes
[REFACTOR] : <message>  # refactoring
```

Do not use conventional commit prefixes like `feat:` or `fix:`.

## Key Conventions

- YAML is the source of truth for workflows; the database is a cache (`WorkflowService._sync_to_db`)
- Actions are synchronous; concurrency is handled by threading in the executor
- Step-level config (`timeout`, `retry`, `retry_delay`, `on_failure`) is read by middleware, not by actions
- Workflow variables live in `StepContext.variables` and are shared across steps
- Config paths are in `autoflow/config.py` — user data goes under `~/.autoflow/`
