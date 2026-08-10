from __future__ import annotations

import json
import sqlite3
from dataclasses import asdict
from pathlib import Path

import click

from glyphmatrix.core.database import connect, init_schema
from glyphmatrix.core.ingest import ingest_directory

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
def list_fonts(as_json: bool) -> None:
    raise NotImplementedError


@fontctl.command()
@click.argument("family")
@click.option("--json", "as_json", is_flag=True)
def info(family: str, as_json: bool) -> None:
    raise NotImplementedError


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
