from __future__ import annotations

import json
import sqlite3
from dataclasses import asdict
from pathlib import Path

import click

from glyphmatrix.core.database import connect, init_schema
from glyphmatrix.core.ingest import ingest_directory
from glyphmatrix.core.query import get_family_detail, list_faces

# V0 command contract per docs/proposal.md. --json is available on every
# command; default output is plain text. Bodies are stubs pending Phase 0
# sign-off on exact output shape (open decision #5).

DEFAULT_DB_PATH = Path.home() / ".glyphmatrix" / "library.db"


@click.group()
@click.option("--db", "db_path", type=click.Path(), default=str(DEFAULT_DB_PATH), show_default=True)
@click.pass_context
def fontctl(ctx: click.Context, db_path: str) -> None:
    ctx.ensure_object(dict)
    ctx.obj["db_path"] = db_path


def _connect(ctx: click.Context) -> sqlite3.Connection:
    db_path = Path(ctx.obj["db_path"])
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = connect(db_path)
    init_schema(conn)
    return conn


@fontctl.command()
@click.argument("directory", type=click.Path(exists=True, file_okay=False))
@click.option("--json", "as_json", is_flag=True)
@click.pass_context
def scan(ctx: click.Context, directory: str, as_json: bool) -> None:
    conn = _connect(ctx)
    result = ingest_directory(conn, directory)
    if as_json:
        click.echo(json.dumps(asdict(result)))
    else:
        click.echo(
            f"scanned {result.files_scanned}  added {result.files_added}  "
            f"changed {result.files_changed}  removed {result.files_removed}  "
            f"errors {result.errors}"
        )


@fontctl.command(name="list")
@click.option("--json", "as_json", is_flag=True)
@click.pass_context
def list_fonts(ctx: click.Context, as_json: bool) -> None:
    conn = _connect(ctx)
    faces = list_faces(conn)

    if as_json:
        click.echo(json.dumps(faces))
        return

    if not faces:
        click.echo("no fonts in the library yet — run `fontctl scan <directory>`")
        return

    for face in faces:
        style = face["style"] or "-"
        weight = str(face["weight"]) if face["weight"] is not None else "-"
        width = face["width"] or "-"
        variable = " variable" if face["is_variable"] else ""
        click.echo(
            f"{face['family']:<24} {style:<14} weight={weight:<5} "
            f"width={width:<16} files={face['file_count']}{variable}"
        )


@fontctl.command()
@click.argument("family")
@click.option("--json", "as_json", is_flag=True)
@click.pass_context
def info(ctx: click.Context, family: str, as_json: bool) -> None:
    conn = _connect(ctx)
    detail = get_family_detail(conn, family)
    if detail is None:
        raise click.ClickException(f"no such family: {family}")

    if as_json:
        click.echo(json.dumps(detail))
        return

    header = detail["family"]
    if detail["foundry"]:
        header += f" ({detail['foundry']})"
    click.echo(header)

    for face in detail["faces"]:
        style = face["style"] or "-"
        weight = str(face["weight"]) if face["weight"] is not None else "-"
        width = face["width"] or "-"
        variable = " variable" if face["is_variable"] else ""
        click.echo(f"  {style}  weight={weight} width={width}{variable}")
        for f in face["files"]:
            click.echo(
                f"    {f['path']}  {f['format']}  v{f['version'] or '?'}  "
                f"glyphs={f['glyph_count']}  source={f['source']}  hash={f['content_hash'][:12]}"
            )


@fontctl.command()
@click.option("--json", "as_json", is_flag=True)
def validate(as_json: bool) -> None:
    raise NotImplementedError


@fontctl.command()
@click.option("--json", "as_json", is_flag=True)
def duplicates(as_json: bool) -> None:
    raise NotImplementedError


@fontctl.command()
@click.argument("family")
def activate(family: str) -> None:
    raise NotImplementedError


@fontctl.command()
@click.argument("family")
def deactivate(family: str) -> None:
    raise NotImplementedError


if __name__ == "__main__":
    fontctl()
