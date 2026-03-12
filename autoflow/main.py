from __future__ import annotations

import logging
import sys
from pathlib import Path

import click
import os
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich import print as rprint

from autoflow.config import HOST, PORT, WORKFLOWS_DIR, PID_FILE, ensure_dirs

console = Console()

def _setup_logging(verbose=False):
    level = logging.DEBUG if verbose else logging.WARNING
    logging.basicConfig(level=level, format="%(asctime)s [%(levelname)s] %(name)s - %(message)s", datefmt="%H:%M:%S")


@click.group()
@click.option("--verbose", "-v", is_flag=True)
def cli(verbose):
    _setup_logging(verbose)
    ensure_dirs()


@cli.command()
@click.option("--host", default=HOST)
@click.option("--port", default=PORT, type=int)
def daemon(host, port):
    import uvicorn
    console.print(f"Starting AutoFlow daemon on [cyan]http://{host}:{port}[/cyan]")
    uvicorn.run("autoflow.api.app:app", host=host, port=port, log_level="info")

@cli.command()
@click.option("--host", default=HOST)
@click.option("--port", default=PORT, type=int)
def start(host, port):
    import subprocess
    import sys
    import time
    import webbrowser

    if PID_FILE.exists():
        pid = int(PID_FILE.read_text().strip())
        try:
            os.kill(pid, 0)
            console.print(f"[yellow]AutoFlow is already running (PID: {pid})[/yellow]")
            console.print(f"Dashboard: [cyan]http://{host}:{port}[/cyan]")
            return
        except OSError:
            PID_FILE.unlink()

    console.print(f"Starting AutoFlow daemon on [cyan]http://{host}:{port}[/cyan]...")
    
    env = os.environ.copy()
    process = subprocess.Popen(
        [sys.executable, "-m", "autoflow", "daemon", "--host", str(host), "--port", str(port)],
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True
    )
    
    PID_FILE.write_text(str(process.pid))
    
    console.print(Panel(
        f"[bold white]AutoFlow is now running in the background![/bold white]\n\n"
        f"Dashboard: [bold cyan]http://{host}:{port}[/bold cyan]\n"
        f"PID: [dim]{process.pid}[/dim]\n"
        f"Commands:\n"
        f"  [cyan]autoflow stop[/cyan]    - Stop the daemon\n"
        f"  [cyan]autoflow restart[/cyan] - Restart the daemon",
        title="⚡ [bold purple]AutoFlow[/bold purple]",
        border_style="magenta",
        expand=False
    ))
    
    time.sleep(1.5)
    webbrowser.open(f"http://{host}:{port}")

@cli.command()
def stop():
    import signal
    
    if not PID_FILE.exists():
        console.print("[yellow]AutoFlow is not currently running.[/yellow]")
        return
        
    pid = int(PID_FILE.read_text().strip())
    try:
        os.kill(pid, signal.SIGTERM)
        console.print(f"[green]Stopped AutoFlow (PID: {pid})[/green]")
    except OSError:
        console.print("[yellow]AutoFlow was not running (stale PID file removed).[/yellow]")
        
    PID_FILE.unlink(missing_ok=True)

@cli.command()
@click.option("--host", default=HOST)
@click.option("--port", default=PORT, type=int)
@click.pass_context
def restart(ctx, host, port):
    ctx.invoke(stop)
    import time
    time.sleep(1)
    ctx.invoke(start, host=host, port=port)


@cli.command()
@click.argument("workflow_path")
def run(workflow_path):
    from autoflow.engine.executor import WorkflowExecutor
    from autoflow.engine.registry import registry
    from autoflow.engine.workflow import Workflow
    from autoflow.services.workflow_service import WorkflowService

    registry.discover()

    # Try the service first (by name), then fall back to direct file path
    service = WorkflowService()
    workflow = service.get_workflow(workflow_path)

    if workflow is None:
        # Fall back to direct file path
        path = Path(workflow_path)
        if not path.exists():
            path = WORKFLOWS_DIR / f"{workflow_path}.yaml"
            if not path.exists():
                path = WORKFLOWS_DIR / workflow_path
                if not path.exists():
                    click.echo(f"Workflow not found: {workflow_path}")
                    sys.exit(1)
        workflow = Workflow.from_yaml(path)

    console.print(f"Running: [bold]{workflow.name}[/bold] ([cyan]{len(workflow.steps)} steps[/cyan])")

    executor = WorkflowExecutor()
    result = executor.execute(workflow)

    for sr in result.step_results:
        icon = "[bold green]++[/bold green]" if sr.success else "[bold red]xx[/bold red]"
        console.print(f"  {icon} [white]{sr.step_name}[/white] ([dim]{sr.duration_ms:.0f}ms[/dim]) — {sr.message}")

    if result.success:
        console.print(f"\n[bold green]✓ Done in {result.total_duration_ms:.0f}ms[/bold green]")
    else:
        console.print(f"\n[bold red]✗ Completed with errors in {result.total_duration_ms:.0f}ms[/bold red]")
        sys.exit(1)


@cli.command("list")
def list_workflows():
    from autoflow.services.workflow_service import WorkflowService

    console.print(f"\nWorkflows directory: [dim]{WORKFLOWS_DIR}[/dim]\n")

    service = WorkflowService()
    workflows = service.list_workflows()

    if not workflows:
        console.print("  [yellow]No workflows found.[/yellow]")
        return

    table = Table(show_header=True, header_style="bold magenta", box=None)
    table.add_column("Status", style="dim", width=6)
    table.add_column("Name", style="white")
    table.add_column("Trigger", style="cyan")
    table.add_column("Steps", justify="right", style="dim")
    table.add_column("File", style="dim")

    for wf in workflows:
        if "error" in wf:
            table.add_row("[red]err[/red]", f"[red]{wf['source_file']}[/red]", "-", "-", wf["source_file"])
        else:
            status = "[green]on[/green]" if wf["enabled"] else "[red]off[/red]"
            table.add_row(
                status,
                f"[bold]{wf['name']}[/bold]",
                wf["trigger_type"],
                str(wf["steps_count"]),
                wf["source_file"],
            )

    console.print(table)
    console.print()


@cli.command("install-autostart")
def install_autostart():
    from autoflow.triggers.login import install_autostart as _install
    if _install():
        click.echo("Autostart installed.")
    else:
        click.echo("Failed to install autostart.")


@cli.command("uninstall-autostart")
def uninstall_autostart():
    from autoflow.triggers.login import uninstall_autostart as _uninstall
    if _uninstall():
        click.echo("Autostart removed.")
    else:
        click.echo("Failed to remove autostart.")


if __name__ == "__main__":
    cli()
