from __future__ import annotations

import json
import sqlite3
from dataclasses import asdict
from pathlib import Path

import click

from glyphmatrix.core.activation_service import ActivationResult, activate_family, deactivate_family
from glyphmatrix.core.collections import (
    add_face_to_collection,
    create_collection,
    find_collection_id,
    list_collection_faces,
    list_collections,
    remove_face_from_collection,
)
from glyphmatrix.core.compare import compare_font_files
from glyphmatrix.core.database import connect, init_schema
from glyphmatrix.core.duplicates import find_duplicates
from glyphmatrix.core.ingest import ingest_directory
from glyphmatrix.core.query import (
    find_face_id,
    find_first_font_file_for_face,
    find_font_file,
    get_family_detail,
    list_faces,
    list_open_issues,
    list_versions,
)
from glyphmatrix.core.renderer import DEFAULT_TEXT, render_text_preview, render_waterfall_preview
from glyphmatrix.core.tags import add_tags, find_faces_by_tag, list_all_tags, list_tags_for_face, remove_tag
from glyphmatrix.core.validator import validate_library

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
@click.argument("family")
@click.argument("style")
@click.option("--text", default=None, help="Custom text to render (default: a pangram)")
@click.option("--size", default=72, type=int, help="Font size in points (ignored with --waterfall)")
@click.option("--waterfall", is_flag=True, help="Render at multiple sizes stacked vertically")
@click.option("-o", "--output", "output_path", type=click.Path(), default=None)
@click.option("--json", "as_json", is_flag=True)
@click.pass_context
def preview(
    ctx: click.Context,
    family: str,
    style: str,
    text: str | None,
    size: int,
    waterfall: bool,
    output_path: str | None,
    as_json: bool,
) -> None:
    conn = _connect(ctx)
    face_id = find_face_id(conn, family, style)
    if face_id is None:
        raise click.ClickException(f"no such face: {family} {style}")

    font_file = find_first_font_file_for_face(conn, face_id)
    if font_file is None:
        raise click.ClickException(f"{family} {style} has no font files")

    if output_path is None:
        safe_name = f"{family}-{style}".replace(" ", "_")
        suffix = "-waterfall" if waterfall else ""
        output_path = f"{safe_name}{suffix}.png"

    if waterfall:
        out = render_waterfall_preview(font_file["path"], output_path, text=text or DEFAULT_TEXT)
    else:
        out = render_text_preview(font_file["path"], text or DEFAULT_TEXT, output_path, font_size=size)

    if as_json:
        click.echo(json.dumps({"output": str(out)}))
    else:
        click.echo(f"wrote {out}")


@fontctl.command()
@click.option("--json", "as_json", is_flag=True)
@click.pass_context
def validate(ctx: click.Context, as_json: bool) -> None:
    conn = _connect(ctx)
    summary = validate_library(conn)
    issues = list_open_issues(conn)

    if as_json:
        click.echo(
            json.dumps(
                {
                    "checked": summary.checked,
                    "issues_opened": summary.issues_opened,
                    "issues_resolved": summary.issues_resolved,
                    "open_issues": issues,
                }
            )
        )
        return

    click.echo(
        f"checked {summary.checked}  new issues {summary.issues_opened}  "
        f"resolved {summary.issues_resolved}  open issues {len(issues)}"
    )
    for issue in issues:
        click.echo(
            f"  [{issue['severity']}] {issue['family']} {issue['style'] or '-'}: "
            f"{issue['issue_type']} — {issue['path']}"
        )
        if issue["detail"]:
            click.echo(f"      {issue['detail']}")


@fontctl.command()
@click.option("--json", "as_json", is_flag=True)
@click.pass_context
def duplicates(ctx: click.Context, as_json: bool) -> None:
    conn = _connect(ctx)
    groups = find_duplicates(conn)

    if as_json:
        click.echo(json.dumps(groups))
        return

    if not groups:
        click.echo("no duplicate files found")
        return

    for group in groups:
        click.echo(f"{len(group['files'])} copies (hash {group['content_hash'][:12]}):")
        for f in group["files"]:
            click.echo(f"  {f['family']} {f['style'] or '-'}  {f['path']}")


def _echo_activation_result(result: ActivationResult, as_json: bool, verb: str) -> None:
    if as_json:
        click.echo(
            json.dumps(
                {
                    "family": result.family,
                    "processed": result.processed,
                    "errors": [{"path": p, "error": e} for p, e in result.errors],
                }
            )
        )
        return

    click.echo(f"{verb} {len(result.processed)} file(s) for {result.family}")
    for path in result.processed:
        click.echo(f"  {path}")
    for path, error in result.errors:
        click.echo(f"  ERROR {path}: {error}")


@fontctl.command()
@click.argument("family")
@click.option("--json", "as_json", is_flag=True)
@click.pass_context
def activate(ctx: click.Context, family: str, as_json: bool) -> None:
    conn = _connect(ctx)
    if get_family_detail(conn, family) is None:
        raise click.ClickException(f"no such family: {family}")

    result = activate_family(conn, family)
    _echo_activation_result(result, as_json, verb="activated")


@fontctl.command()
@click.argument("family")
@click.option("--json", "as_json", is_flag=True)
@click.pass_context
def deactivate(ctx: click.Context, family: str, as_json: bool) -> None:
    conn = _connect(ctx)
    if get_family_detail(conn, family) is None:
        raise click.ClickException(f"no such family: {family}")

    result = deactivate_family(conn, family)
    _echo_activation_result(result, as_json, verb="deactivated")


@fontctl.group()
def tag() -> None:
    """Manage tags on font faces."""


@tag.command(name="add")
@click.argument("family")
@click.argument("style")
@click.argument("tag_names", metavar="TAG...", nargs=-1, required=True)
@click.pass_context
def tag_add(ctx: click.Context, family: str, style: str, tag_names: tuple[str, ...]) -> None:
    conn = _connect(ctx)
    face_id = find_face_id(conn, family, style)
    if face_id is None:
        raise click.ClickException(f"no such face: {family} {style}")

    applied = add_tags(conn, face_id, list(tag_names))
    click.echo(f"tagged {family} {style}: {', '.join(applied) if applied else '(no new tags)'}")


@tag.command(name="remove")
@click.argument("family")
@click.argument("style")
@click.argument("tag_name")
@click.pass_context
def tag_remove(ctx: click.Context, family: str, style: str, tag_name: str) -> None:
    conn = _connect(ctx)
    face_id = find_face_id(conn, family, style)
    if face_id is None:
        raise click.ClickException(f"no such face: {family} {style}")

    if remove_tag(conn, face_id, tag_name):
        click.echo(f"removed tag '{tag_name}' from {family} {style}")
    else:
        click.echo(f"{family} {style} was not tagged '{tag_name}'")


@tag.command(name="list")
@click.argument("family", required=False)
@click.argument("style", required=False)
@click.option("--json", "as_json", is_flag=True)
@click.pass_context
def tag_list(ctx: click.Context, family: str | None, style: str | None, as_json: bool) -> None:
    conn = _connect(ctx)

    if family is not None or style is not None:
        if family is None or style is None:
            raise click.ClickException("give both FAMILY and STYLE, or neither to list all tags")
        face_id = find_face_id(conn, family, style)
        if face_id is None:
            raise click.ClickException(f"no such face: {family} {style}")
        face_tags = list_tags_for_face(conn, face_id)
        if as_json:
            click.echo(json.dumps(face_tags))
        else:
            click.echo(", ".join(face_tags) if face_tags else "(no tags)")
        return

    all_tags = list_all_tags(conn)
    if as_json:
        click.echo(json.dumps(all_tags))
        return
    if not all_tags:
        click.echo("no tags yet")
        return
    for t in all_tags:
        click.echo(f"{t['name']:<20} {t['face_count']} face(s)")


@tag.command(name="find")
@click.argument("tag_name")
@click.option("--json", "as_json", is_flag=True)
@click.pass_context
def tag_find(ctx: click.Context, tag_name: str, as_json: bool) -> None:
    conn = _connect(ctx)
    faces = find_faces_by_tag(conn, tag_name)

    if as_json:
        click.echo(json.dumps(faces))
        return
    if not faces:
        click.echo(f"no faces tagged '{tag_name}'")
        return
    for f in faces:
        click.echo(f"{f['family']} {f['style'] or '-'}")


@fontctl.group()
def collection() -> None:
    """Manage font collections."""


@collection.command(name="create")
@click.argument("name")
@click.option("--parent", "parent_name", default=None)
@click.pass_context
def collection_create(ctx: click.Context, name: str, parent_name: str | None) -> None:
    conn = _connect(ctx)
    try:
        create_collection(conn, name, parent_name)
    except ValueError as exc:
        raise click.ClickException(str(exc))
    suffix = f" under '{parent_name}'" if parent_name else ""
    click.echo(f"created collection '{name}'{suffix}")


@collection.command(name="add")
@click.argument("collection_name", metavar="COLLECTION")
@click.argument("family")
@click.argument("style")
@click.pass_context
def collection_add(ctx: click.Context, collection_name: str, family: str, style: str) -> None:
    conn = _connect(ctx)
    collection_id = find_collection_id(conn, collection_name)
    if collection_id is None:
        raise click.ClickException(f"no such collection: {collection_name}")
    face_id = find_face_id(conn, family, style)
    if face_id is None:
        raise click.ClickException(f"no such face: {family} {style}")

    add_face_to_collection(conn, collection_id, face_id)
    click.echo(f"added {family} {style} to '{collection_name}'")


@collection.command(name="remove")
@click.argument("collection_name", metavar="COLLECTION")
@click.argument("family")
@click.argument("style")
@click.pass_context
def collection_remove(ctx: click.Context, collection_name: str, family: str, style: str) -> None:
    conn = _connect(ctx)
    collection_id = find_collection_id(conn, collection_name)
    if collection_id is None:
        raise click.ClickException(f"no such collection: {collection_name}")
    face_id = find_face_id(conn, family, style)
    if face_id is None:
        raise click.ClickException(f"no such face: {family} {style}")

    if remove_face_from_collection(conn, collection_id, face_id):
        click.echo(f"removed {family} {style} from '{collection_name}'")
    else:
        click.echo(f"{family} {style} was not in '{collection_name}'")


@collection.command(name="list")
@click.option("--json", "as_json", is_flag=True)
@click.pass_context
def collection_list(ctx: click.Context, as_json: bool) -> None:
    conn = _connect(ctx)
    collections_ = list_collections(conn)

    if as_json:
        click.echo(json.dumps(collections_))
        return
    if not collections_:
        click.echo("no collections yet")
        return
    for c in collections_:
        parent = f" (in {c['parent_name']})" if c["parent_name"] else ""
        click.echo(f"{c['name']:<20} {c['face_count']} face(s){parent}")


@collection.command(name="show")
@click.argument("name")
@click.option("--json", "as_json", is_flag=True)
@click.pass_context
def collection_show(ctx: click.Context, name: str, as_json: bool) -> None:
    conn = _connect(ctx)
    collection_id = find_collection_id(conn, name)
    if collection_id is None:
        raise click.ClickException(f"no such collection: {name}")

    faces = list_collection_faces(conn, collection_id)
    if as_json:
        click.echo(json.dumps(faces))
        return
    if not faces:
        click.echo(f"'{name}' is empty")
        return
    for f in faces:
        click.echo(f"{f['family']} {f['style'] or '-'}")


if __name__ == "__main__":
    fontctl()
