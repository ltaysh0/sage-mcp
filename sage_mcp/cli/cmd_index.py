from pathlib import Path

import typer
from rich.progress import BarColumn, MofNCompleteColumn, Progress, SpinnerColumn, TextColumn

from sage_mcp.cli._common import DEFAULT_CONFIG, _get_config, app, console
from sage_mcp.settings import env, resolve_cache_dir


@app.command()
def index(
    config: Path = typer.Option(DEFAULT_CONFIG, "--config", "-c", help="Path to config.yaml"),
    kb: str | None = typer.Option(None, "--kb", help="Index only this KB name"),
    force: bool = typer.Option(False, "--force", "-f", help="Re-index all files, ignoring cache"),
    num_threads: int = typer.Option(16, "--num-threads", "-j", help="Threads for filesystem walk"),
    embed_workers: int = typer.Option(
        4, "--workers", "-w",
        help="Number of parallel embedding workers (default: 4)"),
):
    from sage_mcp.embeddings import make_embed_model
    from sage_mcp.indexer import collect_files, index_kb
    from sage_mcp.store import make_qdrant_client

    cfg = _get_config(config)

    if cfg.embedding.provider == "openai" and not env.openai_api_key:
        err = """[red]OPENAI_API_KEY not set.[/red]
        Add it to .env or set the environment variable."""
        console.print(err)
        raise typer.Exit(1)

    client = make_qdrant_client(cfg.qdrant)
    embed_model = make_embed_model(cfg.embedding, env.openai_api_key)

    cache_dir = resolve_cache_dir()
    targets = [k for k in cfg.knowledge_bases if kb is None or k.name == kb]

    if not targets:
        console.print(f"[yellow]No KB named '{kb}' found in config.[/yellow]")
        raise typer.Exit(1)

    for kb_cfg in targets:
        with Progress(
            SpinnerColumn(),
            TextColumn("Walked [cyan]{task.completed}[/cyan] files\u2026"),
            console=console,
            transient=True,
        ) as walk_progress:
            walk_task = walk_progress.add_task("walk", total=None)
            total = len(collect_files(
                kb_cfg,
                on_file=lambda _: walk_progress.advance(walk_task),
                num_threads=num_threads))
        console.print(f"\n[bold]Indexing[/bold] [cyan]{kb_cfg.name}[/cyan] — {total} files")

        with Progress(
            TextColumn("[cyan]{task.fields[filename]}[/cyan]"),
            BarColumn(),
            MofNCompleteColumn(),
            TextColumn("{task.fields[action]}"),
            console=console,
            transient=True,
        ) as progress:
            task = progress.add_task("", total=total, filename="", action="")

            def on_file(path: Path, did_index: bool) -> None:
                progress.update(
                    task,
                    advance=1,
                    filename=path.name,
                    action="[green]indexed[/green]" if did_index else "[dim]skipped[/dim]",
                )

            def on_warning(path: Path, msg: str) -> None:
                progress.console.print(f"[yellow]⚠[/yellow]  {path}: {msg}")

            indexed, skipped, pruned = index_kb(
                kb_cfg, client, embed_model, cfg.qdrant.collection, cache_dir,
                force=force, on_file=on_file, on_warning=on_warning,
                num_threads=num_threads, embed_workers=embed_workers,
            )

        parts = [f"{indexed} indexed", f"{skipped} skipped (unchanged)"]
        if pruned:
            parts.append(f"[red]{pruned} pruned[/red]")
        console.print(f"  [green]✓[/green] {', '.join(parts)}")


@app.command()
def status(
    config: Path = typer.Option(DEFAULT_CONFIG, "--config", "-c", help="Path to config.yaml"),
    kb: str | None = typer.Option(None, "--kb", help="Show status for only this KB name"),
    num_threads: int = typer.Option(16, "--num-threads", "-j", help="Threads for filesystem walk"),
):
    from sage_mcp.indexer import kb_status

    cfg = _get_config(config)
    cache_dir = resolve_cache_dir()
    targets = [k for k in cfg.knowledge_bases if kb is None or k.name == kb]

    if not targets:
        console.print(f"[yellow]No KB named '{kb}' found in config.[/yellow]")
        raise typer.Exit(1)

    for kb_cfg in targets:
        walk_n = [0]
        check_n = [0]

        with Progress(
            SpinnerColumn(),
            TextColumn("{task.description}"),
            console=console,
            transient=True,
        ) as p:
            tid = p.add_task("Walking…", total=None)

            def on_walk(_: Path) -> None:
                walk_n[0] += 1
                p.update(tid, description=f"Walked [cyan]{walk_n[0]}[/cyan] files\u2026")

            def on_check(_: Path) -> None:
                check_n[0] += 1
                desc = f"Checked [cyan]{check_n[0]}[/cyan] of [cyan]{walk_n[0]}[/cyan] files\u2026"
                p.update(tid, description=desc)

            s = kb_status(
                kb_cfg,
                cache_dir,
                on_walk=on_walk,
                on_check=on_check,
                num_threads=num_threads)

        if s.never_indexed:
            console.print(f"\n[bold]{kb_cfg.name}[/bold] [dim]{kb_cfg.path}[/dim]")
            console.print(f"  [yellow]never indexed[/yellow] — {len(s.new)} files pending")
            continue

        total = len(s.unchanged) + len(s.modified) + len(s.new)
        console.print(f"\n[bold]{kb_cfg.name}[/bold] [dim]{kb_cfg.path}[/dim]")
        console.print(
            f"  [green]✓ {len(s.unchanged)} unchanged[/green]"
            f"  [yellow]~ {len(s.modified)} modified[/yellow]"
            f"  [cyan]+ {len(s.new)} new[/cyan]"
            f"  [red]- {len(s.deleted)} deleted[/red]"
            f"  [dim]({total} total)[/dim]"
        )

        kb_root = Path(kb_cfg.path)

        if s.modified:
            console.print("  [yellow]modified:[/yellow]")
            for p in sorted(s.modified):
                console.print(f"    [yellow]~[/yellow] {p.relative_to(kb_root)}")

        if s.new:
            console.print("  [cyan]new:[/cyan]")
            for p in sorted(s.new):
                console.print(f"    [cyan]+[/cyan] {p.relative_to(kb_root)}")

        if s.deleted:
            console.print("  [red]deleted:[/red]")
            for p in sorted(s.deleted):
                console.print(f"    [red]-[/red] {p}")
