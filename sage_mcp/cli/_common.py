from pathlib import Path

import typer
from rich.console import Console

from sage_mcp.settings import load_config, resolve_config_path

app = typer.Typer(help="Hybrid semantic search over local knowledge bases and codebases.")
config_app = typer.Typer(help="Manage sage-mcp configuration.")
app.add_typer(config_app, name="config")
console = Console()
err_console = Console(stderr=True)

DEFAULT_CONFIG = resolve_config_path()


def _get_config(config_path: Path, quiet: bool = False):
    if not config_path.exists():
        err_console.print(f"[red]Config not found:[/red] {config_path}")
        raise typer.Exit(1)
    if not quiet:
        err_console.print(f"[dim]Using config:[/dim] {config_path}")
    return load_config(config_path)
