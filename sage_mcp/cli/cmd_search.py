from pathlib import Path

import typer
from rich import box
from rich.table import Table

from sage_mcp.cli._common import DEFAULT_CONFIG, _get_config, app, console
from sage_mcp.settings import env


@app.command()
def search(
    query: str = typer.Argument(help="Search query"),
    config: Path = typer.Option(DEFAULT_CONFIG, "--config", "-c"),
    kb: str | None = typer.Option(None, "--kb", help="Limit search to this KB name"),
    top_k: int | None = typer.Option(None, "--top-k", "-n"),
    filter: list[str] | None = typer.Option(
        None,
        "--filter",
        "-f",
        help="key=value metadata filter, repeatable"),
    no_hybrid: bool = typer.Option(False, "--no-hybrid", help="Use dense-only search"),
    kb_tag: list[str] | None = typer.Option(
        None, "--kb-tag", "-G",
        help="Filter by KB tag (repeatable, OR logic). e.g. --kb-tag work --kb-tag homelab"),
    doc_tag: list[str] | None = typer.Option(
        None, "--doc-tag", "-T",
        help="Filter by document frontmatter tag (repeatable, OR logic)"),
    json_out: bool = typer.Option(False, "--json", help="Output as JSON"),
    markdown_out: bool = typer.Option(
        False,
        "--markdown",
        "-m",
        help="Output as Markdown with full file paths"),
    template: str = typer.Option(
        "blockquote",
        "--template",
        "-t",
        help="Markdown template: built-in name ('blockquote', 'table') or path to a .j2 file"),
    excerpt_length: int = typer.Option(
        120,
        "--excerpt-length",
        "-e",
        help="Max characters for excerpt in table template (0 = unlimited)"),
):
    import json as json_mod

    from sage_mcp.embeddings import make_embed_model
    from sage_mcp.searcher import search as do_search
    from sage_mcp.store import make_qdrant_client

    cfg = _get_config(config, quiet=json_out or markdown_out)

    if cfg.embedding.provider == "openai" and not env.openai_api_key:
        console.print("[red]OPENAI_API_KEY not set.[/red]")
        raise typer.Exit(1)

    k = top_k or cfg.search.top_k
    hybrid = not no_hybrid and cfg.search.hybrid

    metadata_filters = {}
    for f in (filter or []):
        if "=" not in f:
            console.print(f"[red]Invalid filter:[/red] '{f}' (expected key=value)")
            raise typer.Exit(1)
        key, _, value = f.partition("=")
        metadata_filters[key.strip()] = value.strip()

    client = make_qdrant_client(cfg.qdrant)
    embed_model = make_embed_model(cfg.embedding, env.openai_api_key)

    results, duplicates_removed = do_search(
        query,
        client,
        embed_model,
        cfg.qdrant.collection,
        top_k=k,
        hybrid=hybrid,
        kb_filter=kb,
        metadata_filters=metadata_filters or None,
        kb_tags=kb_tag or None,
        doc_tags=doc_tag or None,
    )

    if json_out:
        out = {
            "results": [
                {
                    "score": r.score,
                    "file_path": r.file_path,
                    "kb": r.kb,
                    "text": r.text,
                    "metadata": r.metadata,
                }
                for r in results
            ],
            "duplicates_removed": duplicates_removed,
        }
        print(json_mod.dumps(out, indent=2))
        return

    if not results:
        console.print("[yellow]No results.[/yellow]")
        return

    if markdown_out:
        from importlib.resources import files

        from jinja2 import Environment, FileSystemLoader

        template_path = Path(template)
        if template_path.exists():
            jinja_env = Environment(
                loader=FileSystemLoader(str(template_path.parent)),
                trim_blocks=True,
                lstrip_blocks=True,
                keep_trailing_newline=True,
                autoescape=False,
            )
            tmpl = jinja_env.get_template(template_path.name)
        else:
            builtin_dir = files("sage_mcp.templates")
            tmpl_file = f"{template}.md.j2"
            try:
                tmpl_text = builtin_dir.joinpath(tmpl_file).read_text(encoding="utf-8")
            except FileNotFoundError:
                msg = f"[red]Unknown template:[/red] '{template}' (built-ins: blockquote, table)"
                console.print(msg)
                raise typer.Exit(1)
            jinja_env = Environment(
                trim_blocks=True,
                lstrip_blocks=True,
                keep_trailing_newline=True,
                autoescape=False)
            tmpl = jinja_env.from_string(tmpl_text)

        output = tmpl.render(
            query=query,
            results=[
                {
                    "score": r.score,
                    "file_path": r.file_path,
                    "kb": r.kb,
                    "text": r.text,
                    "text_safe": r.text.replace("\n", " ").replace("|", "\\|"),
                    "metadata": r.metadata,
                }
                for r in results
            ],
            duplicates_removed=duplicates_removed,
            excerpt_length=excerpt_length,
        )
        print(output)
        return

    table = Table(box=box.ROUNDED, show_lines=True, title=f'Results for "{query}"')
    table.add_column("Score", style="cyan", width=6, justify="right")
    table.add_column("KB", style="dim", width=10)
    table.add_column("File", style="green")
    table.add_column("Excerpt", no_wrap=False)

    for r in results:
        limit = excerpt_length or 300
        excerpt = r.text[:limit].replace("\n", " ").strip()
        if len(r.text) > limit:
            excerpt += "…"
        table.add_row(
            f"{r.score:.3f}",
            r.kb,
            Path(r.file_path).name,
            excerpt,
        )

    console.print(table)
    if duplicates_removed:
        console.print(f"[dim]{duplicates_removed} duplicate(s) removed[/dim]")


@app.command()
def list_kbs(
    config: Path = typer.Option(DEFAULT_CONFIG, "--config", "-c"),
    json_out: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    import json as json_mod

    cfg = _get_config(config, quiet=json_out)

    if json_out:
        print(json_mod.dumps(
            [
                {
                    "name": kb.name,
                    "path": str(kb.path),
                    "description": kb.description,
                    "extensions": kb.include_extensions,
                }
                for kb in cfg.knowledge_bases
            ],
            indent=2,
        ))
        return

    table = Table(box=box.SIMPLE, title="Configured Knowledge Bases")
    table.add_column("Name", style="cyan")
    table.add_column("Path", style="green")
    table.add_column("Extensions")
    table.add_column("Description")

    for kb_cfg in cfg.knowledge_bases:
        table.add_row(
            kb_cfg.name,
            str(kb_cfg.path),
            ", ".join(kb_cfg.include_extensions),
            kb_cfg.description,
        )
    console.print(table)
