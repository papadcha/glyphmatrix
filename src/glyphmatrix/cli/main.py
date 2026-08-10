from __future__ import annotations

import json
import sqlite3
from dataclasses import asdict
from pathlib import Path

import click

from glyphmatrix.core.compare import compare_font_files
from glyphmatrix.core.database import connect, init_schema
from glyphmatrix.core.ingest import ingest_directory
from glyphmatrix.core.query import find_font_file, get_family_detail, list_faces, list_versions

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


def _format_glyph_list(names: list[str], limit: int = 10) -> str:
    if not names:
        return "none"
    shown = ", ".join(names[:limit])
    if len(names) > limit:
        shown += f", … (+{len(names) - limit} more)"
    return shown


@fontctl.command()
@click.argument("family")
@click.argument("style")
@click.argument("version_a")
@click.argument("version_b")
@click.option("--json", "as_json", is_flag=True)
@click.pass_context
def compare(
    ctx: click.Context, family: str, style: str, version_a: str, version_b: str, as_json: bool
) -> None:
    conn = _connect(ctx)
    file_a = find_font_file(conn, family, style, version_a)
    file_b = find_font_file(conn, family, style, version_b)

    if file_a is None or file_b is None:
        missing = version_a if file_a is None else version_b
        available = list_versions(conn, family, style)
        available_str = ", ".join(v or "(no version tag)" for v in available) or "none found"
        raise click.ClickException(
            f"no {family} {style} with version '{missing}'. Available versions: {available_str}"
        )

    diff = compare_font_files(conn, file_a["id"], file_b["id"])

    if as_json:
        click.echo(
            json.dumps(
                {
                    "family": family,
                    "style": style,
                    "version_a": version_a,
                    "version_b": version_b,
                    "only_in_a": diff.only_in_a,
                    "only_in_b": diff.only_in_b,
                    "changed": diff.changed,
                    "unchanged_count": diff.unchanged_count,
                }
            )
        )
        return

    click.echo(f"{family} {style}: {version_a} vs {version_b}")
    click.echo(f"  only in {version_a} ({len(diff.only_in_a)}): {_format_glyph_list(diff.only_in_a)}")
    click.echo(f"  only in {version_b} ({len(diff.only_in_b)}): {_format_glyph_list(diff.only_in_b)}")
    click.echo(f"  changed outline ({len(diff.changed)}): {_format_glyph_list(diff.changed)}")
    click.echo(f"  unchanged: {diff.unchanged_count}")


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
