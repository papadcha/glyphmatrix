from __future__ import annotations

import json
import sqlite3
from dataclasses import asdict
from pathlib import Path

import click

from glyphmatrix.core.activation_service import (
    ActivationResult,
    activate_family,
    activate_file,
    activate_set,
    deactivate_expired,
    deactivate_family,
    deactivate_file,
    deactivate_set,
    disable_family,
    enable_family,
    restore_active_state,
)
from glyphmatrix.core.backup import backup_database, restore_database
from glyphmatrix.core.catalog import export_catalog
from glyphmatrix.core.doc_fonts import extract_font_names, match_library_families
from glyphmatrix.core.projects import find_project_collection, list_projects, set_project, unset_project
from glyphmatrix.core.gf_config import get_api_key, set_api_key
from glyphmatrix.core.google_fonts import download_family, get_family, search_catalog, get_catalog
from glyphmatrix.core.collections import (
    FAVORITES_COLLECTION_NAME,
    add_face_to_collection,
    create_collection,
    create_smart_collection,
    find_collection_id,
    get_or_create_favorites_collection,
    list_collection_faces,
    list_collections,
    remove_face_from_collection,
)
from glyphmatrix.core.compare import compare_font_files, compare_paths
from glyphmatrix.core.conflicts import list_conflicts
from glyphmatrix.core.database import connect, init_schema
from glyphmatrix.core.duplicates import find_duplicates
from glyphmatrix.core.font_pairing import suggest_pairings
from glyphmatrix.core.glyph_inspector import find_glyphs, glyph_summary
from glyphmatrix.core.ingest import ingest_directory
from glyphmatrix.core.language_coverage import check_script, script_breakdown
from glyphmatrix.core.opentype_features import list_features
from glyphmatrix.core.organize import (
    CASE_MODES,
    apply_organize,
    plan_organize,
    undo_organize,
    write_inventory,
)
from glyphmatrix.core.licenses import classify_license, list_license_conflicts
from glyphmatrix.core.packages import (
    add_document,
    add_file_to_package,
    create_package,
    find_package_id,
    list_documents,
    list_package_files,
    list_packages,
    remove_document,
    remove_file_from_package,
)
from glyphmatrix.core.query import (
    find_face_id,
    find_first_font_file_for_face,
    find_font_file,
    get_family_detail,
    list_faces,
    list_open_issues,
    list_versions,
    search_library,
)
from glyphmatrix.core.specimen import DEFAULT_SAMPLE, export_specimen
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
@click.option("--reparse", is_flag=True,
              help="Re-read unchanged files too (e.g. after a parser update) and update their faces in place.")
@click.option("--json", "as_json", is_flag=True)
@click.pass_context
def scan(ctx: click.Context, directory: str, reparse: bool, as_json: bool) -> None:
    conn = _connect(ctx)
    result = ingest_directory(conn, directory, reparse=reparse)
    if as_json:
        click.echo(json.dumps(asdict(result)))
    else:
        reparsed = f"reparsed {result.files_reparsed}  " if reparse else ""
        click.echo(
            f"scanned {result.files_scanned}  added {result.files_added}  "
            f"changed {result.files_changed}  {reparsed}removed {result.files_removed}  "
            f"errors {result.errors}"
        )


def _existing_db(ctx: click.Context) -> sqlite3.Connection | None:
    """The library DB if it already exists — organize keeps its paths in sync
    but never creates a library just for that."""
    return _connect(ctx) if Path(ctx.obj["db_path"]).exists() else None


def _rel(path: Path, root: Path) -> str:
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)


@fontctl.command()
@click.argument("source", type=click.Path(exists=True, file_okay=False))
@click.option("--dest", type=click.Path(file_okay=False), default=None,
              help="Where to build Vendor/Family/Version/ (default: SOURCE itself).")
@click.option("--apply", "do_apply", is_flag=True,
              help="Actually move files. Without it, only shows the plan.")
@click.option("--vendor", default=None,
              help="Put every font under this vendor (a folder from a single publisher).")
@click.option("--vendor-alias", "vendor_aliases", multiple=True, metavar="OLD=NEW",
              help="Rename a resolved vendor, e.g. 'Two Peas=Two Peas in a Bucket' or "
                   "'Unknown=Acme'. Repeatable; case-insensitive.")
@click.option("--case", "case", type=click.Choice(CASE_MODES), default="as-is", show_default=True,
              help="Casing of family folders and file names: as written in the font, or "
                   "sentence/title/lower case. Vendor folders are not re-cased.")
@click.option("--no-family-grouping", "no_grouping", is_flag=True,
              help="Don't merge fonts in one folder whose names extend each other "
                   "('Flea Market' + 'Flea Market Block') into one family.")
@click.option("--json", "as_json", is_flag=True)
@click.pass_context
def organize(
    ctx: click.Context,
    source: str,
    dest: str | None,
    do_apply: bool,
    vendor: str | None,
    vendor_aliases: tuple[str, ...],
    case: str,
    no_grouping: bool,
    as_json: bool,
) -> None:
    """Arrange fonts as Vendor/Family/Version/Family Style.ext.

    Dry run by default. With --apply each file is copied, verified and only
    then removed from its old place; an undo log and _Font Catalog.csv are
    written to the destination. Identical duplicates are reported, not moved."""
    aliases = {}
    for alias in vendor_aliases:
        old, sep, new = alias.partition("=")
        if not sep or not old.strip() or not new.strip():
            raise click.BadParameter(f"expected OLD=NEW, got {alias!r}", param_hint="--vendor-alias")
        aliases[old] = new
    source_path = Path(source)
    dest_path = Path(dest) if dest else source_path
    plan = plan_organize(source_path, dest_path, vendor=vendor, vendor_aliases=aliases, case=case,
                        group_families=not no_grouping)

    if do_apply:
        result = apply_organize(plan, source_path, dest_path, conn=_existing_db(ctx))

    if as_json:
        payload = {
            "applied": do_apply,
            "items": [
                {
                    "source": str(i.source),
                    "destination": str(i.destination) if i.destination else None,
                    "action": i.action,
                    "vendor": i.vendor,
                    "family": i.family,
                    "style": i.style,
                    "version": i.version_label,
                    "review": i.flags,
                }
                for i in plan
            ],
        }
        if do_apply:
            payload["result"] = {
                k: str(v) if isinstance(v, Path) else v for k, v in asdict(result).items()
            }
        click.echo(json.dumps(payload, ensure_ascii=False))
        if do_apply and result.failure:
            ctx.exit(1)
        return

    for item in plan:
        if item.action == "unchanged":
            continue
        src = _rel(item.source, source_path)
        if item.destination is None:
            click.echo(f"[{item.action}] {src}")
        else:
            click.echo(f"{src}\n  -> {_rel(item.destination, dest_path)}")
        for flag in item.flags:
            click.echo(f"     ! {flag}")

    counts = {a: sum(1 for i in plan if i.action == a) for a in ("move", "unchanged", "duplicate", "error")}
    review = sum(1 for i in plan if i.flags and i.action == "move")
    click.echo(
        f"\n{counts['move']} to move, {counts['unchanged']} already in place, "
        f"{counts['duplicate']} duplicates, {counts['error']} unreadable, {review} to review"
    )
    if not do_apply:
        click.echo("dry run: nothing moved. Re-run with --apply to move files.")
        return
    click.echo(f"moved {result.moved}, errors {result.errors}")
    if result.undo_log:
        click.echo(f"undo log: {result.undo_log}")
    if result.catalog:
        click.echo(f"catalog: {result.catalog}")
    for warning in result.warnings:
        click.echo(f"warning: {warning}", err=True)
    if result.failure:
        click.echo(f"error: {result.failure}", err=True)
        ctx.exit(1)


@fontctl.command()
@click.argument("directory", type=click.Path(exists=True, file_okay=False))
@click.argument("output", metavar="OUTPUT.pdf", type=click.Path(dir_okay=False))
@click.option("--text", default=DEFAULT_SAMPLE, show_default=True, help="Sample line.")
@click.option("--title", default=None, help="Page header (default: the folder name).")
def specimen(directory: str, output: str, text: str, title: str | None) -> None:
    """PDF list of every font in DIRECTORY: name plus a sample line in that
    font, grouped by folder. Symbol fonts show their own characters."""
    try:
        path, fonts, pages = export_specimen(directory, output, sample_text=text, title=title)
    except ValueError as exc:
        raise click.ClickException(str(exc))
    click.echo(f"wrote {path}  ({fonts} fonts, {pages} page{'' if pages == 1 else 's'})")


@fontctl.command()
@click.argument("directory", type=click.Path(exists=True, file_okay=False))
@click.argument("output", metavar="OUTPUT.csv", type=click.Path(dir_okay=False))
@click.option("--vendor", default=None, help="Write this vendor for every font (single-publisher folder).")
def inventory(directory: str, output: str, vendor: str | None) -> None:
    """Write a CSV catalog of DIRECTORY as it is — nothing is moved.

    For folders arranged by hand (series folders etc.): re-run it after
    adding fonts. Columns match organize's _Font Catalog.csv."""
    path, count = write_inventory(directory, output, vendor=vendor)
    click.echo(f"wrote {path}  ({count} fonts)")


@fontctl.command(name="organize-undo")
@click.argument("log", type=click.Path(exists=True, dir_okay=False))
@click.pass_context
def organize_undo(ctx: click.Context, log: str) -> None:
    """Move files back using an undo log written by 'organize --apply'."""
    restored, problems = undo_organize(log, conn=_existing_db(ctx))
    click.echo(f"restored {restored}")
    for problem in problems:
        click.echo(f"  ! {problem}")


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


def _metadata_lines(metadata: dict | None) -> list[str]:
    """Human-readable lines for format-specific extras (FON, TTC/OTC)."""
    if not metadata:
        return []
    lines = []
    if metadata.get("version_source"):
        lines.append(f"version from unique ID + head (name table says: {metadata.get('version_string')})")
    if metadata.get("copyright_years"):
        lines.append("copyright: " + ", ".join(str(y) for y in metadata["copyright_years"]))
    if metadata.get("description"):
        lines.append(f"description: {metadata['description']}")
    if metadata.get("pixel_sizes"):
        lines.append("bitmap sizes: " + ", ".join(metadata["pixel_sizes"]) + " px")
    if metadata.get("charset"):
        lines.append(f"charset: {metadata['charset']}")
    for member in metadata.get("collection", []):
        lines.append(
            f"collection #{member['index']}: {member['family']} {member['style'] or ''}".rstrip()
        )
    return lines


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
            expiry = f" (expires {f['expires_at']})" if f["expires_at"] else ""
            license_category = classify_license(f["license"]) or "no license info"
            click.echo(
                f"    {f['path']}  {f['format']}  v{f['version'] or '?'}  "
                f"glyphs={f['glyph_count']}  source={f['source']}  hash={f['content_hash'][:12]}  "
                f"license={license_category}  [{f['activation_state']}]{expiry}"
            )
            for line in _metadata_lines(f["metadata"]):
                click.echo(f"      {line}")


@fontctl.command()
@click.argument("term")
@click.option("--json", "as_json", is_flag=True)
@click.pass_context
def search(ctx: click.Context, term: str, as_json: bool) -> None:
    conn = _connect(ctx)
    results = search_library(conn, term)

    if as_json:
        click.echo(json.dumps(results))
        return
    if not results:
        click.echo(f"no matches for '{term}'")
        return
    for r in results:
        style = r["style"] or "-"
        click.echo(f"{r['family']:<24} {style}")


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

    if file_a["id"] == file_b["id"]:
        raise click.ClickException(
            f"both versions resolve to the same file ({file_a['path']}). If two files share "
            f"family, style and version, compare them directly: fontctl compare-files A B"
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


@fontctl.command(name="compare-files")
@click.argument("file_a", type=click.Path(exists=True, dir_okay=False))
@click.argument("file_b", type=click.Path(exists=True, dir_okay=False))
@click.option("--json", "as_json", is_flag=True)
def compare_files_cmd(file_a: str, file_b: str, as_json: bool) -> None:
    """Compare two font files directly: metadata and glyph outlines."""
    result = compare_paths(file_a, file_b)
    glyphs = result.glyphs
    if as_json:
        click.echo(json.dumps({
            "identical": result.identical,
            "fields": {k: list(v) for k, v in result.fields.items()},
            "sizes": list(result.sizes),
            "only_in_a": glyphs.only_in_a,
            "only_in_b": glyphs.only_in_b,
            "changed": glyphs.changed,
            "unchanged_count": glyphs.unchanged_count,
        }, ensure_ascii=False))
        return
    click.echo(f"A: {file_a}  ({result.sizes[0]:,} bytes)")
    click.echo(f"B: {file_b}  ({result.sizes[1]:,} bytes)")
    if result.identical:
        click.echo("identical: byte-for-byte the same file")
        return
    for name, (a, b) in result.fields.items():
        click.echo(f"  {name}: {a!r}  vs  {b!r}")
    click.echo(f"  only in A ({len(glyphs.only_in_a)}): {_format_glyph_list(glyphs.only_in_a)}")
    click.echo(f"  only in B ({len(glyphs.only_in_b)}): {_format_glyph_list(glyphs.only_in_b)}")
    click.echo(f"  changed outline ({len(glyphs.changed)}): {_format_glyph_list(glyphs.changed)}")
    click.echo(f"  unchanged: {glyphs.unchanged_count}")


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
    font_file = _resolve_font_file_or_raise(conn, family, style)

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
@click.argument("family")
@click.argument("style")
@click.option("--char", default=None, help="Inspect the glyph for this single character")
@click.option("--codepoint", default=None, help="Inspect by Unicode codepoint, decimal or 0xHEX")
@click.option("--name", "glyph_name", default=None, help="Inspect by exact glyph name")
@click.option("--search", "name_search", default=None, help="Filter glyph names containing this text")
@click.option("-o", "--render", "render_path", type=click.Path(), default=None,
              help="With --char: also render that glyph to this PNG path")
@click.option("--json", "as_json", is_flag=True)
@click.pass_context
def glyphs(
    ctx: click.Context,
    family: str,
    style: str,
    char: str | None,
    codepoint: str | None,
    glyph_name: str | None,
    name_search: str | None,
    render_path: str | None,
    as_json: bool,
) -> None:
    """No filter: shows a summary (glyph count, codepoint/contour range).
    With --char/--codepoint/--name/--search: lists matching glyphs."""
    conn = _connect(ctx)
    font_file = _resolve_font_file_or_raise(conn, family, style)

    resolved_codepoint: int | None = None
    if char is not None:
        if len(char) != 1:
            raise click.ClickException("--char must be exactly one character")
        resolved_codepoint = ord(char)
    elif codepoint is not None:
        try:
            resolved_codepoint = int(codepoint, 0)
        except ValueError:
            raise click.ClickException(f"invalid --codepoint: {codepoint!r}")

    if render_path is not None:
        if char is None:
            raise click.ClickException("--render needs --char (renders that one character)")
        render_text_preview(font_file["path"], char, render_path, font_size=200)
        click.echo(f"rendered '{char}' to {render_path}")

    if resolved_codepoint is not None or glyph_name is not None or name_search is not None:
        matches = find_glyphs(
            conn,
            font_file["id"],
            glyph_name=glyph_name,
            codepoint=resolved_codepoint,
            name_search=name_search,
        )
        if as_json:
            click.echo(json.dumps(matches))
            return
        if not matches:
            click.echo("no matching glyphs")
            return
        for g in matches:
            cp = f"U+{g['unicode_codepoint']:04X}" if g["unicode_codepoint"] is not None else "-"
            click.echo(
                f"{g['glyph_name']:<20} {cp:<10} contours={g['contour_count']} "
                f"advance={g['advance_width']}  outline_hash={g['outline_hash'][:12]}"
            )
        return

    summary = glyph_summary(conn, font_file["id"])
    if as_json:
        click.echo(json.dumps(summary))
        return
    click.echo(f"{family} {style}: {summary['glyph_count']} glyphs")
    if summary["min_codepoint"] is not None:
        click.echo(
            f"  codepoints U+{summary['min_codepoint']:04X}-U+{summary['max_codepoint']:04X} "
            f"({summary['mapped_count']} mapped to a codepoint)"
        )
    click.echo(f"  contours: {summary['min_contours']}-{summary['max_contours']}")
    click.echo("  use --char/--codepoint/--name/--search to inspect specific glyphs")


@fontctl.command()
@click.argument("family")
@click.argument("style")
@click.option("--script", "script_query", default=None,
              help="Check coverage for one script (ISO 15924 code like 'Grek', or a name like 'Greek')")
@click.option("--json", "as_json", is_flag=True)
@click.pass_context
def language(ctx: click.Context, family: str, style: str, script_query: str | None, as_json: bool) -> None:
    """Unicode script coverage, derived from this file's already-parsed glyph
    codepoints. No filter: full breakdown. --script: check one script.

    This reports Unicode *script* coverage (Latin, Greek, Cyrillic...), not
    language — a language like Vietnamese uses the Latin script plus specific
    diacritic combinations, which script-level coverage can't distinguish."""
    conn = _connect(ctx)
    font_file = _resolve_font_file_or_raise(conn, family, style)

    if script_query is not None:
        try:
            result = check_script(conn, font_file["id"], script_query)
        except ValueError as exc:
            raise click.ClickException(str(exc))
        if as_json:
            click.echo(json.dumps(result))
            return
        state = "supported" if result["supported"] else "not supported"
        click.echo(f"{family} {style}: {result['name']} ({result['script']}) — {state}, {result['glyph_count']} glyphs")
        return

    breakdown = script_breakdown(conn, font_file["id"])
    if as_json:
        click.echo(json.dumps(breakdown))
        return
    if not breakdown:
        click.echo("no mapped glyphs found")
        return
    click.echo(f"{family} {style}: {len(breakdown)} scripts")
    for row in breakdown:
        click.echo(f"  {row['name']:<20} ({row['script']})  {row['glyph_count']} glyphs")


@fontctl.command()
@click.argument("family")
@click.argument("style")
@click.option("--json", "as_json", is_flag=True)
@click.pass_context
def features(ctx: click.Context, family: str, style: str, as_json: bool) -> None:
    """OpenType layout features (ligatures, small caps, stylistic sets...)
    read straight from the file's GSUB/GPOS tables — most fonts have none."""
    conn = _connect(ctx)
    font_file = _resolve_font_file_or_raise(conn, family, style)

    result = list_features(font_file["path"])
    if as_json:
        click.echo(json.dumps(result))
        return
    if not result:
        click.echo(f"{family} {style}: no OpenType layout features (no GSUB/GPOS)")
        return
    click.echo(f"{family} {style}: {len(result)} features")
    for row in result:
        click.echo(f"  {row['tag']:<6} {row['name']:<35} ({'/'.join(row['tables'])})")


@fontctl.command()
@click.argument("family")
@click.argument("style")
@click.option("--limit", default=5, type=int, help="Max suggestions to show")
@click.option("--json", "as_json", is_flag=True)
@click.pass_context
def pair(ctx: click.Context, family: str, style: str, limit: int, as_json: bool) -> None:
    """Suggests fonts from your library that pair well with this one, using
    the classic serif/sans/script contrast rule of thumb over the
    sFamilyClass/PANOSE tags already applied at scan time. This is a
    heuristic, not a fact — every suggestion states its reason so you can
    judge it yourself."""
    conn = _connect(ctx)
    face_id = find_face_id(conn, family, style)
    if face_id is None:
        raise click.ClickException(f"no such face: {family} {style}")

    result = suggest_pairings(conn, face_id, limit=limit)
    if as_json:
        click.echo(json.dumps(result))
        return

    if result["source_bucket"] is None:
        click.echo(f"{family} {style}: no serif/sans/script classification tag — can't suggest a pairing")
        return
    if not result["suggestions"]:
        click.echo(f"{family} {style} ({result['source_bucket']}): no contrasting fonts found in your library")
        return
    click.echo(f"{family} {style} ({result['source_bucket']}) pairs well with:")
    for s in result["suggestions"]:
        click.echo(f"  {s['family']:<24} {s['style'] or '-':<12} ({s['bucket']:<6})  {s['reason']}")


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


@fontctl.command()
@click.option("--json", "as_json", is_flag=True)
@click.pass_context
def conflicts(ctx: click.Context, as_json: bool) -> None:
    """Faces (family+style) backed by 2+ files with different content —
    activating more than one at once is refused, since only one can
    represent that family+style to the OS at a time."""
    conn = _connect(ctx)
    found = list_conflicts(conn)

    if as_json:
        click.echo(json.dumps(found))
        return

    if not found:
        click.echo("no conflicts found")
        return

    for c in found:
        click.echo(f"{c['family']} {c['style'] or '-'} — {len(c['files'])} different files claim this:")
        for f in c["files"]:
            click.echo(f"  {f['path']}  v{f['version'] or '?'}  source={f['source']}")


@fontctl.command()
@click.option("--json", "as_json", is_flag=True)
@click.pass_context
def licenses(ctx: click.Context, as_json: bool) -> None:
    """Faces (family+style) whose files disagree on license category —
    e.g. one classifies OFL-1.1, another Commercial/Proprietary. Could be
    legitimate dual-licensing, or a mismatched file worth a second look."""
    conn = _connect(ctx)
    found = list_license_conflicts(conn)

    if as_json:
        click.echo(json.dumps(found))
        return

    if not found:
        click.echo("no license conflicts found")
        return

    for c in found:
        click.echo(f"{c['family']} {c['style'] or '-'} — files disagree on license:")
        for f in c["files"]:
            click.echo(f"  {f['path']}  license={f['license_category'] or 'no license info'}")


def _echo_activation_result(result: ActivationResult, as_json: bool, verb: str) -> None:
    if as_json:
        click.echo(
            json.dumps(
                {
                    "label": result.label,
                    "processed": result.processed,
                    "errors": [{"path": p, "error": e} for p, e in result.errors],
                }
            )
        )
        return

    click.echo(f"{verb} {len(result.processed)} file(s) for {result.label}")
    for path in result.processed:
        click.echo(f"  {path}")
    for path, error in result.errors:
        click.echo(f"  ERROR {path}: {error}")


@fontctl.command()
@click.argument("family")
@click.option("--for", "duration", default=None, metavar="DURATION",
              help="Auto-expire after this long, e.g. 30m/2h/1d. Needs "
                   "`fontctl deactivate-expired` run periodically to take effect.")
@click.option("--json", "as_json", is_flag=True)
@click.pass_context
def activate(ctx: click.Context, family: str, duration: str | None, as_json: bool) -> None:
    conn = _connect(ctx)
    if get_family_detail(conn, family) is None:
        raise click.ClickException(f"no such family: {family}")

    try:
        result = activate_family(conn, family, duration=duration)
    except ValueError as exc:
        raise click.ClickException(str(exc))
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


@fontctl.command(name="activate-file")
@click.argument("path", type=click.Path())
@click.option("--for", "duration", default=None, metavar="DURATION",
              help="Auto-expire after this long, e.g. 30m/2h/1d.")
@click.option("--json", "as_json", is_flag=True)
@click.pass_context
def activate_file_cmd(ctx: click.Context, path: str, duration: str | None, as_json: bool) -> None:
    """Activate a specific font file by path. Unlike `fontctl activate`, this
    deliberately resolves conflicts: if a different file for the same
    family+style is currently active, it is deactivated first so this file
    can take its place."""
    conn = _connect(ctx)
    try:
        result = activate_file(conn, path, duration=duration)
    except ValueError as exc:
        raise click.ClickException(str(exc))
    _echo_activation_result(result, as_json, verb="activated")


@fontctl.command(name="deactivate-file")
@click.argument("path", type=click.Path())
@click.option("--json", "as_json", is_flag=True)
@click.pass_context
def deactivate_file_cmd(ctx: click.Context, path: str, as_json: bool) -> None:
    """Deactivate a specific font file by path."""
    conn = _connect(ctx)
    result = deactivate_file(conn, path)
    _echo_activation_result(result, as_json, verb="deactivated")


@fontctl.command(name="deactivate-expired")
@click.option("--json", "as_json", is_flag=True)
@click.pass_context
def deactivate_expired_cmd(ctx: click.Context, as_json: bool) -> None:
    """Deactivate every temporarily-activated font whose --for duration
    has passed. Not automatic — run this yourself, or via a scheduled
    task/cron, since the tool has no background process of its own."""
    conn = _connect(ctx)
    result = deactivate_expired(conn)
    _echo_activation_result(result, as_json, verb="deactivated")


@fontctl.command()
@click.option("--json", "as_json", is_flag=True)
@click.pass_context
def startup(ctx: click.Context, as_json: bool) -> None:
    """Re-apply every font this library says should be active. Meant to
    run once after login/reboot — mainly matters on Windows, where
    AddFontResourceEx registration doesn't survive one; macOS/Linux
    persist their activation symlinks on their own, so this is a harmless
    no-op there. Wire it into Task Scheduler/launchd/a login script
    yourself — the tool has no background process to do it automatically."""
    conn = _connect(ctx)
    result = restore_active_state(conn)
    _echo_activation_result(result, as_json, verb="restored")


@fontctl.group(name="set")
def activation_set() -> None:
    """Activate/deactivate a whole collection at once — an "activation
    set" is just a collection used this way; build it with
    `fontctl collection create/add`."""


@activation_set.command(name="activate")
@click.argument("name")
@click.option("--for", "duration", default=None, metavar="DURATION",
              help="Auto-expire after this long, e.g. 30m/2h/1d.")
@click.option("--json", "as_json", is_flag=True)
@click.pass_context
def set_activate(ctx: click.Context, name: str, duration: str | None, as_json: bool) -> None:
    conn = _connect(ctx)
    try:
        result = activate_set(conn, name, duration=duration)
    except ValueError as exc:
        raise click.ClickException(str(exc))
    if result is None:
        raise click.ClickException(f"no such set: {name}")
    _echo_activation_result(result, as_json, verb="activated")


@activation_set.command(name="deactivate")
@click.argument("name")
@click.option("--json", "as_json", is_flag=True)
@click.pass_context
def set_deactivate(ctx: click.Context, name: str, as_json: bool) -> None:
    conn = _connect(ctx)
    result = deactivate_set(conn, name)
    if result is None:
        raise click.ClickException(f"no such set: {name}")
    _echo_activation_result(result, as_json, verb="deactivated")


@fontctl.command()
@click.argument("family")
@click.option("--json", "as_json", is_flag=True)
@click.pass_context
def disable(ctx: click.Context, family: str, as_json: bool) -> None:
    """Block a family from being activated until `fontctl enable` — also
    deactivates it first if currently active."""
    conn = _connect(ctx)
    if get_family_detail(conn, family) is None:
        raise click.ClickException(f"no such family: {family}")

    result = disable_family(conn, family)
    _echo_activation_result(result, as_json, verb="disabled")


@fontctl.command()
@click.argument("family")
@click.option("--json", "as_json", is_flag=True)
@click.pass_context
def enable(ctx: click.Context, family: str, as_json: bool) -> None:
    """Clear a family's disabled flag — does not itself activate it."""
    conn = _connect(ctx)
    if get_family_detail(conn, family) is None:
        raise click.ClickException(f"no such family: {family}")

    result = enable_family(conn, family)
    _echo_activation_result(result, as_json, verb="enabled")


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


@collection.command(name="create-smart")
@click.argument("name")
@click.argument("query")
@click.option("--parent", "parent_name", default=None)
@click.pass_context
def collection_create_smart(
    ctx: click.Context, name: str, query: str, parent_name: str | None
) -> None:
    """QUERY: space-separated field:value terms (AND), groups split on
    ' OR ' (OR) — e.g. 'foundry:Adobe style:Regular OR tag:script'.
    Fields: family, style, foundry, tag, weight, width, source, license,
    version. Membership is computed live, not stored."""
    conn = _connect(ctx)
    try:
        create_smart_collection(conn, name, query, parent_name)
    except ValueError as exc:
        raise click.ClickException(str(exc))
    suffix = f" under '{parent_name}'" if parent_name else ""
    click.echo(f"created smart collection '{name}'{suffix}: {query}")


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

    try:
        add_face_to_collection(conn, collection_id, face_id)
    except ValueError as exc:
        raise click.ClickException(str(exc))
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

    try:
        removed = remove_face_from_collection(conn, collection_id, face_id)
    except ValueError as exc:
        raise click.ClickException(str(exc))
    if removed:
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
        smart = " [smart]" if c["is_smart"] else ""
        click.echo(f"{c['name']:<20} {c['face_count']} face(s){parent}{smart}")


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


@fontctl.command(name="favorite")
@click.argument("family")
@click.argument("style")
@click.pass_context
def favorite_add(ctx: click.Context, family: str, style: str) -> None:
    conn = _connect(ctx)
    face_id = find_face_id(conn, family, style)
    if face_id is None:
        raise click.ClickException(f"no such face: {family} {style}")

    collection_id = get_or_create_favorites_collection(conn)
    add_face_to_collection(conn, collection_id, face_id)
    click.echo(f"favorited {family} {style}")


@fontctl.command(name="unfavorite")
@click.argument("family")
@click.argument("style")
@click.pass_context
def favorite_remove(ctx: click.Context, family: str, style: str) -> None:
    conn = _connect(ctx)
    face_id = find_face_id(conn, family, style)
    if face_id is None:
        raise click.ClickException(f"no such face: {family} {style}")

    collection_id = find_collection_id(conn, FAVORITES_COLLECTION_NAME)
    if collection_id is not None and remove_face_from_collection(conn, collection_id, face_id):
        click.echo(f"unfavorited {family} {style}")
    else:
        click.echo(f"{family} {style} was not a favorite")


@fontctl.command(name="favorites")
@click.option("--json", "as_json", is_flag=True)
@click.pass_context
def favorites_list(ctx: click.Context, as_json: bool) -> None:
    conn = _connect(ctx)
    collection_id = find_collection_id(conn, FAVORITES_COLLECTION_NAME)
    faces = list_collection_faces(conn, collection_id) if collection_id is not None else []

    if as_json:
        click.echo(json.dumps(faces))
        return
    if not faces:
        click.echo("no favorites yet")
        return
    for f in faces:
        click.echo(f"{f['family']} {f['style'] or '-'}")


@fontctl.group()
def package() -> None:
    """Track which real-world bundle (e.g. a font pack) a file came from."""


@package.command(name="create")
@click.argument("name")
@click.option("--vendor", default=None)
@click.option("--notes", default=None)
@click.pass_context
def package_create(ctx: click.Context, name: str, vendor: str | None, notes: str | None) -> None:
    conn = _connect(ctx)
    try:
        create_package(conn, name, vendor, notes)
    except ValueError as exc:
        raise click.ClickException(str(exc))
    click.echo(f"created package '{name}'")


def _resolve_font_file_or_raise(conn: sqlite3.Connection, family: str, style: str) -> dict:
    face_id = find_face_id(conn, family, style)
    if face_id is None:
        raise click.ClickException(f"no such face: {family} {style}")
    font_file = find_first_font_file_for_face(conn, face_id)
    if font_file is None:
        raise click.ClickException(f"{family} {style} has no font files")
    return font_file


@package.command(name="add")
@click.argument("package_name", metavar="PACKAGE")
@click.argument("family")
@click.argument("style")
@click.pass_context
def package_add(ctx: click.Context, package_name: str, family: str, style: str) -> None:
    conn = _connect(ctx)
    package_id = find_package_id(conn, package_name)
    if package_id is None:
        raise click.ClickException(f"no such package: {package_name}")
    font_file = _resolve_font_file_or_raise(conn, family, style)

    add_file_to_package(conn, package_id, font_file["id"])
    click.echo(f"added {family} {style} to '{package_name}'")


@package.command(name="remove")
@click.argument("package_name", metavar="PACKAGE")
@click.argument("family")
@click.argument("style")
@click.pass_context
def package_remove(ctx: click.Context, package_name: str, family: str, style: str) -> None:
    conn = _connect(ctx)
    package_id = find_package_id(conn, package_name)
    if package_id is None:
        raise click.ClickException(f"no such package: {package_name}")
    font_file = _resolve_font_file_or_raise(conn, family, style)

    if remove_file_from_package(conn, package_id, font_file["id"]):
        click.echo(f"removed {family} {style} from '{package_name}'")
    else:
        click.echo(f"{family} {style} was not in '{package_name}'")


@package.command(name="list")
@click.option("--json", "as_json", is_flag=True)
@click.pass_context
def package_list(ctx: click.Context, as_json: bool) -> None:
    conn = _connect(ctx)
    packages = list_packages(conn)

    if as_json:
        click.echo(json.dumps(packages))
        return
    if not packages:
        click.echo("no packages yet")
        return
    for p in packages:
        vendor = f" ({p['vendor']})" if p["vendor"] else ""
        click.echo(f"{p['name']:<24}{vendor} files={p['file_count']} docs={p['document_count']}")


@package.command(name="show")
@click.argument("name")
@click.option("--json", "as_json", is_flag=True)
@click.pass_context
def package_show(ctx: click.Context, name: str, as_json: bool) -> None:
    conn = _connect(ctx)
    package_id = find_package_id(conn, name)
    if package_id is None:
        raise click.ClickException(f"no such package: {name}")

    files = list_package_files(conn, package_id)
    docs = list_documents(conn, package_id)

    if as_json:
        click.echo(json.dumps({"files": files, "documents": docs}))
        return

    if not files:
        click.echo(f"'{name}' has no fonts yet")
    for f in files:
        click.echo(f"{f['family']} {f['style'] or '-'}  {f['path']}")
    for d in docs:
        suffix = f" — {d['description']}" if d["description"] else ""
        click.echo(f"doc: {d['path']}{suffix}")


@package.command(name="doc-add")
@click.argument("package_name", metavar="PACKAGE")
@click.argument("path", type=click.Path(exists=True, dir_okay=False))
@click.option("--description", default=None)
@click.pass_context
def package_doc_add(
    ctx: click.Context, package_name: str, path: str, description: str | None
) -> None:
    conn = _connect(ctx)
    package_id = find_package_id(conn, package_name)
    if package_id is None:
        raise click.ClickException(f"no such package: {package_name}")

    add_document(conn, package_id, path, description)
    click.echo(f"added document to '{package_name}': {path}")


@package.command(name="doc-remove")
@click.argument("package_name", metavar="PACKAGE")
@click.argument("path")
@click.pass_context
def package_doc_remove(ctx: click.Context, package_name: str, path: str) -> None:
    conn = _connect(ctx)
    package_id = find_package_id(conn, package_name)
    if package_id is None:
        raise click.ClickException(f"no such package: {package_name}")

    if remove_document(conn, package_id, path):
        click.echo(f"removed document from '{package_name}': {path}")
    else:
        click.echo(f"'{package_name}' had no document at {path}")


@fontctl.command()
@click.argument("output", metavar="OUTPUT.pdf", type=click.Path())
@click.option("--text", default=None, help="Preview text (default: pangram)")
@click.option("--family", "families", multiple=True, metavar="FAMILY",
              help="Include only these families (repeat for multiple). Default: all.")
@click.option("--json", "as_json", is_flag=True)
@click.pass_context
def catalog(
    ctx: click.Context,
    output: str,
    text: str | None,
    families: tuple[str, ...],
    as_json: bool,
) -> None:
    """Export a PDF specimen catalog — one page per font family."""
    conn = _connect(ctx)
    try:
        out = export_catalog(
            conn,
            output,
            preview_text=text or DEFAULT_TEXT,
            families=list(families) or None,
        )
    except ValueError as exc:
        raise click.ClickException(str(exc))

    if as_json:
        click.echo(json.dumps({"output": str(out)}))
    else:
        click.echo(f"wrote {out}")


@fontctl.command()
@click.argument("dest_path", metavar="PATH", type=click.Path())
@click.pass_context
def backup(ctx: click.Context, dest_path: str) -> None:
    conn = _connect(ctx)
    out = backup_database(conn, dest_path)
    click.echo(f"backed up to {out}")


@fontctl.command()
@click.argument("source_path", metavar="PATH", type=click.Path(exists=True, dir_okay=False))
@click.option("--yes", "-y", is_flag=True, help="skip the confirmation prompt")
@click.pass_context
def restore(ctx: click.Context, source_path: str, yes: bool) -> None:
    db_path = ctx.obj["db_path"]
    if not yes:
        click.confirm(
            f"This will overwrite {db_path} with the contents of {source_path}. Continue?",
            abort=True,
        )
    restore_database(source_path, db_path)
    click.echo(f"restored {db_path} from {source_path}")


@fontctl.group()
def project() -> None:
    """Associate directories and documents with font collections for one-command activation."""


@project.command(name="set")
@click.argument("directory", type=click.Path(exists=True, file_okay=False))
@click.argument("collection")
@click.pass_context
def project_set(ctx: click.Context, directory: str, collection: str) -> None:
    """Map a directory to a collection. fontctl project activate will use it."""
    conn = _connect(ctx)
    try:
        set_project(conn, directory, collection)
    except ValueError as exc:
        raise click.ClickException(str(exc))
    click.echo(f"project '{directory}' → '{collection}'")


@project.command(name="unset")
@click.argument("directory", type=click.Path())
@click.pass_context
def project_unset(ctx: click.Context, directory: str) -> None:
    """Remove the collection mapping for a directory."""
    conn = _connect(ctx)
    if unset_project(conn, directory):
        click.echo(f"removed project mapping for '{directory}'")
    else:
        click.echo(f"no mapping found for '{directory}'")


@project.command(name="list")
@click.option("--json", "as_json", is_flag=True)
@click.pass_context
def project_list(ctx: click.Context, as_json: bool) -> None:
    """Show all directory → collection mappings."""
    conn = _connect(ctx)
    mappings = list_projects(conn)
    if as_json:
        click.echo(json.dumps(mappings))
        return
    if not mappings:
        click.echo("no project mappings yet — use `fontctl project set <dir> <collection>`")
        return
    for m in mappings:
        click.echo(f"{m['path']:<50} → {m['collection']}")


@project.command(name="activate")
@click.option("--path", "directory", default=None, type=click.Path(),
              help="Directory to look up (default: current working directory)")
@click.option("--doc", "doc_path", default=None, type=click.Path(exists=True, dir_okay=False),
              help="Document to extract font names from (.pdf, .docx, .odt, .odp)")
@click.option("--for", "duration", default=None, metavar="DURATION",
              help="Auto-expire after this long, e.g. 30m/2h/1d.")
@click.option("--json", "as_json", is_flag=True)
@click.pass_context
def project_activate(
    ctx: click.Context,
    directory: str | None,
    doc_path: str | None,
    duration: str | None,
    as_json: bool,
) -> None:
    """Activate fonts for the current project or a document.

    With --path (or no flags, uses CWD): finds the nearest ancestor directory
    that has a project mapping and activates its collection.

    With --doc: extracts font names from the document and activates any that
    are in your library. Can be combined with --path (project fonts first,
    then document fonts on top).
    """
    import os
    conn = _connect(ctx)
    all_results: list[ActivationResult] = []

    if doc_path is None and directory is None:
        directory = os.getcwd()

    if directory is not None:
        collection_name = find_project_collection(conn, directory)
        if collection_name is None:
            raise click.ClickException(
                f"no project mapping found for '{directory}' or any parent directory"
            )
        try:
            result = activate_set(conn, collection_name, duration=duration)
        except ValueError as exc:
            raise click.ClickException(str(exc))
        if result is None:
            raise click.ClickException(f"collection '{collection_name}' not found")
        all_results.append(result)

    if doc_path is not None:
        try:
            doc_names = extract_font_names(doc_path)
        except ValueError as exc:
            raise click.ClickException(str(exc))
        matched, unmatched = match_library_families(conn, doc_names)
        for family in matched:
            try:
                result = activate_family(conn, family, duration=duration)
            except ValueError as exc:
                raise click.ClickException(str(exc))
            all_results.append(result)
        if unmatched and not as_json:
            click.echo(f"not in library ({len(unmatched)}): {', '.join(unmatched)}")

    if as_json:
        click.echo(json.dumps([
            {"label": r.label, "processed": r.processed,
             "errors": [{"path": p, "error": e} for p, e in r.errors]}
            for r in all_results
        ]))
        return

    for result in all_results:
        _echo_activation_result(result, as_json=False, verb="activated")


@project.command(name="deactivate")
@click.option("--path", "directory", default=None, type=click.Path(),
              help="Directory to look up (default: current working directory)")
@click.option("--doc", "doc_path", default=None, type=click.Path(exists=True, dir_okay=False),
              help="Document whose fonts to deactivate.")
@click.option("--json", "as_json", is_flag=True)
@click.pass_context
def project_deactivate(
    ctx: click.Context,
    directory: str | None,
    doc_path: str | None,
    as_json: bool,
) -> None:
    """Deactivate fonts for the current project or a document."""
    import os
    conn = _connect(ctx)
    all_results: list[ActivationResult] = []

    if doc_path is None and directory is None:
        directory = os.getcwd()

    if directory is not None:
        collection_name = find_project_collection(conn, directory)
        if collection_name is None:
            raise click.ClickException(
                f"no project mapping found for '{directory}' or any parent directory"
            )
        result = deactivate_set(conn, collection_name)
        if result is None:
            raise click.ClickException(f"collection '{collection_name}' not found")
        all_results.append(result)

    if doc_path is not None:
        try:
            doc_names = extract_font_names(doc_path)
        except ValueError as exc:
            raise click.ClickException(str(exc))
        matched, _ = match_library_families(conn, doc_names)
        for family in matched:
            result = deactivate_family(conn, family)
            all_results.append(result)

    if as_json:
        click.echo(json.dumps([
            {"label": r.label, "processed": r.processed,
             "errors": [{"path": p, "error": e} for p, e in r.errors]}
            for r in all_results
        ]))
        return

    for result in all_results:
        _echo_activation_result(result, as_json=False, verb="deactivated")


def _require_api_key() -> str:
    key = get_api_key()
    if not key:
        raise click.ClickException(
            "no Google Fonts API key configured — run `fontctl gf key <YOUR_KEY>` first"
        )
    return key


@fontctl.group()
def gf() -> None:
    """Browse and download fonts from Google Fonts."""


@gf.command(name="key")
@click.argument("api_key")
def gf_key(api_key: str) -> None:
    """Save your Google Fonts API key (stored in ~/.glyphmatrix/config.json)."""
    set_api_key(api_key)
    click.echo("Google Fonts API key saved.")


@gf.command(name="list")
@click.option("--category", default=None,
              help="Filter by category: serif, sans-serif, monospace, display, handwriting")
@click.option("--subset", default=None,
              help="Filter by subset, e.g. 'greek', 'latin-ext'")
@click.option("--sort", default="alpha", show_default=True,
              type=click.Choice(["alpha", "popularity", "date", "trending", "style"]))
@click.option("--json", "as_json", is_flag=True)
def gf_list(category: str | None, subset: str | None, sort: str, as_json: bool) -> None:
    """List all families in the Google Fonts catalog."""
    key = _require_api_key()
    try:
        items = get_catalog(key, sort=sort)
    except RuntimeError as exc:
        raise click.ClickException(str(exc))

    if category:
        items = [f for f in items if f.get("category", "").lower() == category.lower()]
    if subset:
        items = [f for f in items if subset.lower() in [s.lower() for s in f.get("subsets", [])]]

    if as_json:
        click.echo(json.dumps(items))
        return
    if not items:
        click.echo("no families match")
        return
    for f in items:
        variants = len(f.get("variants", []))
        click.echo(f"{f['family']:<32} {f.get('category', '-'):<14} {variants} variant(s)")


@gf.command(name="search")
@click.argument("term")
@click.option("--sort", default="alpha", show_default=True,
              type=click.Choice(["alpha", "popularity", "date", "trending", "style"]))
@click.option("--json", "as_json", is_flag=True)
def gf_search(term: str, sort: str, as_json: bool) -> None:
    """Search the Google Fonts catalog by family name."""
    key = _require_api_key()
    try:
        items = search_catalog(key, term, sort=sort)
    except RuntimeError as exc:
        raise click.ClickException(str(exc))

    if as_json:
        click.echo(json.dumps(items))
        return
    if not items:
        click.echo(f"no families matching '{term}'")
        return
    for f in items:
        variants = len(f.get("variants", []))
        click.echo(f"{f['family']:<32} {f.get('category', '-'):<14} {variants} variant(s)")


@gf.command(name="info")
@click.argument("family")
@click.option("--json", "as_json", is_flag=True)
def gf_info(family: str, as_json: bool) -> None:
    """Show metadata for a specific Google Fonts family."""
    key = _require_api_key()
    try:
        item = get_family(key, family)
    except RuntimeError as exc:
        raise click.ClickException(str(exc))
    if item is None:
        raise click.ClickException(f"family '{family}' not found in Google Fonts catalog")

    if as_json:
        click.echo(json.dumps(item))
        return

    click.echo(f"{item['family']}  ({item.get('category', '-')})")
    click.echo(f"  variants: {', '.join(item.get('variants', []))}")
    click.echo(f"  subsets:  {', '.join(item.get('subsets', []))}")
    click.echo(f"  files:    {len(item.get('files', {}))}")


@gf.command(name="download")
@click.argument("family")
@click.option("--dest", required=True, type=click.Path(), help="Directory to save font files into")
@click.option("--json", "as_json", is_flag=True)
@click.pass_context
def gf_download(ctx: click.Context, family: str, dest: str, as_json: bool) -> None:
    """Download all variants of a Google Fonts family and add them to the library."""
    key = _require_api_key()
    try:
        paths = download_family(key, family, dest)
    except (RuntimeError, ValueError) as exc:
        raise click.ClickException(str(exc))

    conn = _connect(ctx)
    result = ingest_directory(conn, dest)

    if as_json:
        click.echo(json.dumps({
            "downloaded": [str(p) for p in paths],
            "scanned": result.files_scanned,
            "added": result.files_added,
            "changed": result.files_changed,
        }))
        return

    click.echo(f"downloaded {len(paths)} file(s) to {dest}")
    for p in paths:
        click.echo(f"  {p.name}")
    click.echo(
        f"ingested: scanned {result.files_scanned}  added {result.files_added}  "
        f"changed {result.files_changed}  errors {result.errors}"
    )


if __name__ == "__main__":
    fontctl()
