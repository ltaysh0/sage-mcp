from pathlib import Path

import typer

from sage_mcp.cli._common import DEFAULT_CONFIG, _get_config, app, err_console


@app.command()
def graph(
    config: Path = typer.Option(DEFAULT_CONFIG, "--config", "-c", help="Path to config.yaml"),
    kb: str | None = typer.Option(None, "--kb", help="Limit to this KB name"),
    threshold: float = typer.Option(
        0.75, "--threshold", "-t",
        help="Minimum similarity to include an edge (ignored when --top-k is set)"),
    top_k: int | None = typer.Option(
        1, "--top-k", "-n",
        help="Keep only top N edges per node (0 = disable, use --threshold instead)"),
    format: str = typer.Option(
        "json", "--format", "-f", help="Output format: json, graphml, dot"),
    output: Path | None = typer.Option(
        None, "--output", "-o", help="Write output to file (default: stdout)"),
):
    """Build a file-level semantic similarity graph from existing Qdrant embeddings."""
    try:
        import networkx
        import numpy
        _ = (numpy, networkx)  # validation-only imports
    except ImportError:
        err_console.print("[red]Optional graph dependencies not installed.[/red]")
        err_console.print('Install with: [cyan]pip install -e ".[graph]"[/cyan]')
        raise typer.Exit(1)

    from sage_mcp.graph import build_file_similarity_graph, to_dot, to_graphml, to_json
    from sage_mcp.store import make_qdrant_client

    cfg = _get_config(config)

    if format not in ("json", "graphml", "dot"):
        err_console.print(f"[red]Unknown format:[/red] '{format}' (expected: json, graphml, dot)")
        raise typer.Exit(1)

    client = make_qdrant_client(cfg.qdrant)

    edges = build_file_similarity_graph(
        client,
        cfg.qdrant.collection,
        kb_filter=kb,
        threshold=threshold,
        top_k=top_k if top_k else None,
    )

    files = set()
    for src, tgt, _sim in edges:
        files.add(src)
        files.add(tgt)

    if output:
        if format == "json":
            to_json(edges, str(output))
        elif format == "graphml":
            to_graphml(edges, str(output))
        else:
            to_dot(edges, str(output))
        err_console.print(
            f"[green]✓[/green] {len(edges)} edges between {len(files)} files → {output}"
        )
    else:
        if format == "json":
            print(to_json(edges))
        elif format == "graphml":
            print(to_graphml(edges))
        else:
            print(to_dot(edges))
        err_console.print(f"[green]✓[/green] {len(edges)} edges between {len(files)} files")
