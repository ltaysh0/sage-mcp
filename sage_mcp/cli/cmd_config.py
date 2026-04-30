from pathlib import Path

import click
import typer

from sage_mcp.cli._common import config_app, console, err_console

_CONFIG_TEMPLATE = """\
# sage-mcp configuration
# Run `sage config schema` to get a JSON Schema for editor validation/autocomplete.

knowledge_bases:
  - name: my-notes
    path: ~/notes
    description: "Personal notes"
    tags: []
    include_extensions: [.md]
    exclude_patterns: []

  # Add more knowledge bases here:
  # - name: work
  #   path: ~/work/docs
  #   tags: [work]

embedding:
  # provider: openai | ollama | litellm
  provider: openai
  model: text-embedding-3-small
  # base_url: null    # Override for Ollama: http://localhost:11434

qdrant:
  # mode: local | server
  mode: local
  # path: null        # Default: ~/.local/share/sage-mcp/qdrant
  collection: kb
  # host: localhost   # Server mode only
  # port: 6333        # Server mode only

search:
  top_k: 10
  hybrid: true
"""


def _write_config_template(dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(_CONFIG_TEMPLATE)


def _run_config_wizard(dest: Path) -> None:
    """Interactive prompts to build a config.yaml."""
    import yaml

    console.print("[bold]sage-mcp config wizard[/bold]")
    console.print(f"Writing to: [cyan]{dest}[/cyan]\n")

    provider = typer.prompt(
        "Embedding provider",
        default="openai",
        type=click.Choice(["openai", "ollama", "litellm"]),
    )
    model_default = {
        "openai": "text-embedding-3-small",
        "ollama": "nomic-embed-text",
        "litellm": "amazon.titan-embed-text-v1",
    }[provider]
    model = typer.prompt("Embedding model", default=model_default)
    base_url = typer.prompt("Base URL (leave blank for default)", default="") or None

    qdrant_mode = typer.prompt(
        "Qdrant mode",
        default="local",
        type=click.Choice(["local", "server"]),
    )
    collection = typer.prompt("Qdrant collection name", default="kb")

    kbs = []
    console.print("\nAdd knowledge bases (empty name to finish):")
    while True:
        name = typer.prompt("KB name (blank to finish)", default="")
        if not name:
            break
        path = typer.prompt(f"  Path for '{name}'")
        description = typer.prompt(f"  Description for '{name}'", default="")
        tags_raw = typer.prompt(f"  Tags for '{name}' (comma-separated)", default="")
        tags = [t.strip() for t in tags_raw.split(",") if t.strip()]
        kbs.append({
            "name": name,
            "path": path,
            "description": description,
            "tags": tags,
            "include_extensions": [".md"],
            "exclude_patterns": [],
        })

    if not kbs:
        console.print("[yellow]No KBs added. Add them manually to the config.[/yellow]")
        kbs = [{
            "name": "my-notes", "path": "~/notes", "description": "", "tags": [],
            "include_extensions": [".md"], "exclude_patterns": [],
        }]

    cfg = {
        "knowledge_bases": kbs,
        "embedding": {"provider": provider, "model": model, "base_url": base_url},
        "qdrant": {"mode": qdrant_mode, "collection": collection},
        "search": {"top_k": 10, "hybrid": True},
    }

    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(yaml.dump(cfg, default_flow_style=False, allow_unicode=True))
    console.print(f"\n[green]✓[/green] Config written to {dest}")
    console.print("Next: [cyan]sage index[/cyan]")


@config_app.command("schema")
def config_schema(
    output: Path | None = typer.Option(None, "--output", "-o", help="Write schema to file"),
):
    """Output JSON Schema for config.yaml."""
    import json as json_mod

    from sage_mcp.settings import Config

    schema = Config.model_json_schema()
    text = json_mod.dumps(schema, indent=2)

    if output:
        output.write_text(text)
        err_console.print(f"[green]✓[/green] Schema written to {output}")
    else:
        print(text)


@config_app.command("init")
def config_init(
    output: Path | None = typer.Option(
        None, "--output", "-o",
        help="Path to write config.yaml (default: XDG config home)"),
    template: bool = typer.Option(
        False, "--template",
        help="Write a commented template without prompting"),
    force: bool = typer.Option(
        False, "--force", "-f",
        help="Overwrite existing config without confirmation"),
):
    """Create a new config.yaml interactively or write a commented template."""
    import sys

    from sage_mcp.settings import resolve_config_path

    dest = output or resolve_config_path()

    if dest.exists() and not force:
        err_console.print(f"[yellow]Config already exists:[/yellow] {dest}")
        err_console.print("Use [cyan]--force[/cyan] to overwrite.")
        raise typer.Exit(1)

    is_tty = sys.stdin.isatty()

    if template or not is_tty:
        _write_config_template(dest)
        err_console.print(f"[green]✓[/green] Template written to {dest}")
    else:
        _run_config_wizard(dest)
