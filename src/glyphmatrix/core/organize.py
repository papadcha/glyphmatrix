"""Physically reorganize a folder of fonts into Vendor/Family/Version/ — the one
place GlyphMatrix moves user files, and only on explicit request.

Layout: <dest>/<Vendor>/<Family>/<Version>/<Family> <Style>.<ext>

- Vendor:  resolved foundry (manufacturer → vendor ID → copyright holder),
           shortened ("Monotype Imaging Inc." → "Monotype"); "Unknown" if none.
- Version: "v<number>" from the version string; if there is none, "©<year>"
           from the latest copyright year; otherwise "No Version".
- Name:    family + style ("Normal" → "Regular"), lower-case extension.

Safety (PROJECT_BRIEF principle #7): plan first, nothing moves without
apply; every move is copy → verify sha256 → delete original; an undo log
records every move; byte-identical duplicates are reported, never deleted.
Anything the rules could only guess at is flagged for review.
"""
from __future__ import annotations

import csv
import hashlib
import os
import re
import shutil
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from glyphmatrix.core.foundry import copyright_years
from glyphmatrix.core.parser import ParsedFont, parse_font_file
from glyphmatrix.core.scanner import scan_directory

CATALOG_NAME = "_Font Catalog.csv"
UNDO_LOG_PREFIX = "_organize-"
UNKNOWN_VENDOR = "Unknown"
NO_VERSION = "No Version"

# Names that differ only by corporate form or division map to one folder.
_VENDOR_ALIASES = {
    "monotype imaging": "Monotype",
    "monotype typography": "Monotype",
    "the monotype corporation": "Monotype",
    "linotype library": "Linotype",
    "linotype-hell": "Linotype",
    "adobe systems": "Adobe",
    "microsoft corp": "Microsoft",
    "google corporation": "Google",
}
_COMPANY_SUFFIX = re.compile(
    r"[,\s]+(inc|incorporated|ltd|limited|corp|corporation|co|company|gmbh|ag|llc|plc|"
    r"s\.a|limited partnership)\.?$",
    re.IGNORECASE,
)
# The number must stand alone: "2peas Sweet Pea" is a name, not version 2.
_VERSION_NUMBER = re.compile(r"^\s*(?:version\s*)?(\d+\.\d+|\d+(?![\w.]))", re.IGNORECASE)
_UNSAFE_CHARS = re.compile(r'[/\\:*?"<>|\x00-\x1f]')
_COPYRIGHT_MARKS = re.compile(r"copyright|copr\.?|\(c\)|©|portions", re.IGNORECASE)
# "Copyright (c)", "(C)Copyright", "Copyright Copr." are one claim, not two.
_COPYRIGHT_RUN = re.compile(r"(?:(?:copyright|copr\.?|\(c\)|©)\s*)+", re.IGNORECASE)
# A trailing pixel/point size, optionally with a short variant tag: "Hibiya 24",
# "Kodenmachou 12 Ki". Only used when several families share the rest.
_SIZE_SUFFIX = re.compile(r"^(.*\S)\s+(\d{1,3}(?:\s+[A-Za-z]{1,3})?)$")


@dataclass
class PlannedMove:
    source: Path
    destination: Path | None  # None: left in place (duplicate or unreadable)
    action: str  # 'move', 'unchanged', 'duplicate', 'error'
    vendor: str = ""
    family: str = ""
    style: str = ""
    version_label: str = ""
    content_hash: str = ""
    flags: list[str] = field(default_factory=list)
    parsed: ParsedFont | None = None


@dataclass
class OrganizeResult:
    moved: int = 0
    unchanged: int = 0
    duplicates: int = 0
    errors: int = 0
    undo_log: Path | None = None
    catalog: Path | None = None


def short_vendor(name: str | None) -> str:
    """Folder-friendly vendor name: no corporate suffix, known aliases merged."""
    if not name or not name.strip():
        return UNKNOWN_VENDOR
    vendor = name.strip()
    # "Keitarou Hiraki, Font Silo" — a person then their foundry: keep the foundry.
    if ", " in vendor and not _COMPANY_SUFFIX.search(vendor):
        vendor = vendor.rsplit(", ", 1)[1]
    previous = None
    while previous != vendor:
        previous = vendor
        vendor = _COMPANY_SUFFIX.sub("", vendor).strip(" ,.")
    return _VENDOR_ALIASES.get(vendor.lower(), vendor) or UNKNOWN_VENDOR


def version_label(version: str | None, copyright_text: str | None) -> tuple[str, bool]:
    """('v1.23' | '©1991' | 'No Version', came_from_copyright)."""
    match = _VERSION_NUMBER.match(version or "")
    if match:
        major, _, minor = match.group(1).partition(".")
        return "v" + str(int(major)) + (f".{minor}" if minor else ""), False
    years = copyright_years(copyright_text)
    if years:
        return f"©{max(years)}", True
    return NO_VERSION, False


CASE_MODES = ("as-is", "sentence", "title", "lower")


def apply_case(text: str, mode: str) -> str:
    """Re-case a name regardless of how the font spells it.
    sentence: "2Peas Sweet Pea Regular" -> "2peas sweet pea regular",
              "KH Dot Hibiya 24" -> "Kh dot hibiya 24"
    title:    "MOonbeams Regular" -> "Moonbeams Regular"
    """
    if mode == "as-is":
        return text
    lowered = text.lower()
    if mode == "lower":
        return lowered
    if mode == "sentence":
        return lowered[:1].upper() + lowered[1:]
    if mode == "title":
        return " ".join(word[:1].upper() + word[1:] for word in lowered.split(" "))
    raise ValueError(f"unknown case mode: {mode!r} (expected one of {', '.join(CASE_MODES)})")


def _safe(part: str) -> str:
    part = re.sub(r"\s+", " ", _UNSAFE_CHARS.sub("-", part))
    return part.strip(" .") or "Untitled"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _review_flags(parsed: ParsedFont, version_from_copyright: bool) -> list[str]:
    flags = []
    if parsed.foundry_source == "copyright":
        flags.append("vendor taken from copyright holder")
    elif parsed.foundry_source is None:
        flags.append("vendor unknown")
    if parsed.copyright and len(
        _COPYRIGHT_MARKS.findall(_COPYRIGHT_RUN.sub("© ", parsed.copyright))
    ) >= 2:
        flags.append("copyright names several parties")
    if parsed.metadata and parsed.metadata.get("version_source"):
        flags.append("version taken from unique ID")
    if version_from_copyright:
        flags.append("no version; folder uses copyright year")
    return flags


_VENDOR_FLAGS = ("vendor taken from copyright holder", "vendor unknown")


def _settle_vendors(items: list[PlannedMove], forced: str | None, aliases: dict[str, str]) -> None:
    """Apply --vendor / aliases, then merge spellings that differ only in case
    ("Two Peas In A Bucket" / "Two Peas in a Bucket") into the most common one."""
    lowered_aliases = {k.strip().lower(): v.strip() for k, v in aliases.items()}
    for item in items:
        chosen = forced or lowered_aliases.get(item.vendor.lower())
        if chosen:
            item.vendor = chosen
            item.flags = [f for f in item.flags if f not in _VENDOR_FLAGS]
    spellings: dict[str, dict[str, int]] = {}
    for item in items:
        counts = spellings.setdefault(item.vendor.lower(), {})
        counts[item.vendor] = counts.get(item.vendor, 0) + 1
    for item in items:
        counts = spellings[item.vendor.lower()]
        item.vendor = max(counts, key=lambda name: (counts[name], name))


# Abbreviated weight/width/slope tokens glued onto Windows-style family names
# ("AvantGarGotItcTMedCon" = AvantGarGotItcT Medium Condensed). Longest first.
_STYLE_TOKENS: list[tuple[str, str, int]] = sorted(
    [
        # (token, word, order: 0 weight, 1 width, 2 slope)
        ("UltLig", "Ultra Light", 0), ("ExtLig", "Extra Light", 0), ("XLig", "Extra Light", 0),
        ("XLt", "Extra Light", 0), ("Thi", "Thin", 0), ("Thin", "Thin", 0),
        ("Lig", "Light", 0), ("Lt", "Light", 0), ("Light", "Light", 0),
        ("Boo", "Book", 0), ("Bk", "Book", 0), ("Book", "Book", 0),
        ("Med", "Medium", 0), ("Md", "Medium", 0), ("Medium", "Medium", 0),
        ("Dem", "Demi", 0), ("Demi", "Demi", 0), ("SemBol", "Semibold", 0), ("SmBd", "Semibold", 0),
        ("Bol", "Bold", 0), ("Bd", "Bold", 0), ("Bold", "Bold", 0),
        ("ExtBol", "Extra Bold", 0), ("XBd", "Extra Bold", 0),
        ("Hea", "Heavy", 0), ("Hv", "Heavy", 0), ("Heavy", "Heavy", 0),
        ("Bla", "Black", 0), ("Blk", "Black", 0), ("Black", "Black", 0),
        ("ExtCon", "Extra Condensed", 1), ("XCn", "Extra Condensed", 1),
        ("Con", "Condensed", 1), ("Cn", "Condensed", 1), ("Cond", "Condensed", 1),
        ("Condensed", "Condensed", 1), ("Nar", "Narrow", 1), ("Narrow", "Narrow", 1),
        ("Exp", "Expanded", 1), ("Wid", "Wide", 1), ("Wide", "Wide", 1),
        ("Ita", "Italic", 2), ("It", "Italic", 2), ("Italic", "Italic", 2),
        ("Obl", "Oblique", 2), ("Oblique", "Oblique", 2),
    ],
    key=lambda t: -len(t[0]),
)
_STYLE_ORDER = {word: order for _, word, order in _STYLE_TOKENS}
_STYLE_ORDER.update({"Regular": 0, "Roman": 0})


def _parse_style_tokens(suffix: str) -> list[str] | None:
    """'MedCon' -> ['Medium', 'Condensed']; None unless the whole suffix is tokens."""
    words, rest = [], suffix
    while rest:
        for token, word, _ in _STYLE_TOKENS:
            # A token must end at the string end or before the next capital.
            if rest.startswith(token) and (len(rest) == len(token) or rest[len(token)].isupper()):
                words.append(word)
                rest = rest[len(token):]
                break
        else:
            return None
    return words


def _combine_style(extra_words: list[str], style: str) -> str:
    """Merge words from an abbreviated name with the font's own style, ordered
    weight, width, slope: ['Condensed'] + 'Bold' -> 'Bold Condensed'."""
    words = [w for w in extra_words]
    for word in style.split():
        if word.lower() not in ("regular", "roman") and word not in words:
            words.append(word)
    words.sort(key=lambda w: _STYLE_ORDER.get(w, 0))
    return " ".join(words) or "Regular"


def _abbreviated_base(family: str, bases: list[str]) -> tuple[str, list[str]] | None:
    """The longest other family that this one extends by abbreviated style
    tokens only: 'AvantGarGotItcTMedCon' over 'AvantGarGotItcT'."""
    for base in sorted(bases, key=len, reverse=True):
        if len(base) >= len(family) or not family.startswith(base):
            continue
        suffix = family[len(base):]
        if not suffix[0].isupper():
            continue
        words = _parse_style_tokens(suffix)
        if words:
            return base, words
    return None


def _group_by_shared_name(items: list[PlannedMove]) -> None:
    """Within one vendor and one source folder, a font whose family name starts
    with another font's family name joins that family; the rest of its name
    becomes its style: "2Peas Flea Market Block Irregular" next to
    "2Peas Flea Market" -> family "2Peas Flea Market", style "Block Irregular".
    Names equal except for case also merge, and so do Windows-style names
    with abbreviated styles glued on ("AvantGarGotItcTMedCon" joins
    "AvantGarGotItcT" as "Medium Condensed"). The source folder is the signal
    that a publisher packaged them together, so unrelated fonts that merely
    share a prefix elsewhere stay apart."""
    folders: dict[tuple[str, Path], list[PlannedMove]] = {}
    for item in items:
        folders.setdefault((item.vendor.casefold(), item.source.parent), []).append(item)
    for members in folders.values():
        bases = sorted({m.family for m in members}, key=len)
        if len(bases) < 2:
            continue
        for item in members:
            folded = item.family.casefold()
            base = next(
                (b for b in bases
                 if len(b) < len(item.family) and folded.startswith(b.casefold() + " ")),
                None,
            )
            if base is None:
                abbreviated = _abbreviated_base(item.family, bases)
                if abbreviated:
                    base, words = abbreviated
                    item.family, item.style = base, _combine_style(words, item.style)
                    item.flags.append(f"grouped with {base} (abbreviated style in name)")
                    continue
                same = [b for b in bases if b.casefold() == folded]
                if len(same) > 1:
                    # Deterministic pick: the most used spelling, then the one
                    # with more capitals ("Flower Girl" over "flower girl").
                    uses = {b: sum(1 for m in members if m.family == b) for b in same}
                    chosen = min(same, key=lambda b: (-uses[b], -sum(c.isupper() for c in b), b))
                    if item.family != chosen:
                        item.family = chosen
                        item.flags.append(f"grouped with {chosen} (same folder)")
                continue
            extra = item.family[len(base):].strip()
            style = item.style
            if style.lower() == "regular" or style.lower() in extra.lower():
                style = extra
            else:
                style = f"{extra} {style}"
            item.family, item.style = base, style
            item.flags.append(f"grouped with {base} (same folder)")


def _size_groups(entries: list[tuple[str, str, str]]) -> dict[tuple[str, str], tuple[str, str]]:
    """For (vendor, family, style) entries, map size-suffixed families that share
    a base name within one vendor ("KH Dot Hibiya 24" + "KH Dot Hibiya 32") to
    (base family, size as style). Lone families are left alone, so names like
    "Bauhaus 93" are not split."""
    bases: dict[tuple[str, str], set[str]] = {}
    for vendor, family, style in entries:
        match = _SIZE_SUFFIX.match(family)
        if match and style.lower() == "regular":
            bases.setdefault((vendor, match.group(1).lower()), set()).add(family)
    groups = {}
    for (vendor, _), families in bases.items():
        if len(families) < 2:
            continue
        for family in families:
            match = _SIZE_SUFFIX.match(family)
            groups[(vendor, family)] = (match.group(1), match.group(2))
    return groups


class _ExistingFiles:
    """Byte-identical lookup among font files already in the destination
    (outside the source folder). Only files of the same size are hashed, and
    only when asked, so a large library costs little. Names don't matter:
    a file counts as already there only if its content is identical."""

    def __init__(self, dest: Path, exclude: Path):
        self._dest = dest
        self._exclude = exclude.resolve()
        self._by_size: dict[int, list[Path]] | None = None
        self._hashes: dict[Path, str] = {}

    def _index(self) -> dict[int, list[Path]]:
        if self._by_size is None:
            self._by_size = {}
            if self._dest.exists():
                for path in scan_directory(self._dest):
                    resolved = path.resolve()
                    if resolved == self._exclude or self._exclude in resolved.parents:
                        continue
                    self._by_size.setdefault(path.stat().st_size, []).append(path)
        return self._by_size

    def find(self, path: Path, content_hash: str) -> Path | None:
        for candidate in self._index().get(path.stat().st_size, []):
            if candidate not in self._hashes:
                self._hashes[candidate] = _sha256(candidate)
            if self._hashes[candidate] == content_hash:
                try:
                    return candidate.relative_to(self._dest)
                except ValueError:
                    return candidate
        return None


def plan_organize(
    source: str | Path,
    dest: str | Path | None = None,
    vendor: str | None = None,
    vendor_aliases: dict[str, str] | None = None,
    case: str = "as-is",
    group_families: bool = True,
) -> list[PlannedMove]:
    """vendor: put every font under this vendor (a folder from one publisher).
    case: casing of family folders and file names — 'as-is' (as written in
    the font), 'sentence', 'title' or 'lower'. Vendor folders keep their
    spelling (set them exactly with vendor / vendor_aliases).
    group_families: treat fonts in one source folder whose name extends
    another's ("Flea Market" + "Flea Market Block Regular") as one family.
    vendor_aliases: {"Two Peas": "Two Peas in a Bucket", "Unknown": "..."} —
    matched case-insensitively against the resolved vendor."""
    source = Path(source)
    dest = Path(dest) if dest is not None else source
    plan: list[PlannedMove] = []
    by_hash: dict[str, PlannedMove] = {}
    # Compared case-insensitively: macOS and Windows file systems are, so
    # "Foo Regular" and "FOO Regular" would land on the same file.
    taken: set[str] = set()
    pending: list[PlannedMove] = []
    existing = _ExistingFiles(dest, exclude=source)

    for path in sorted(scan_directory(source)):
        try:
            parsed = parse_font_file(path)
        except Exception as exc:  # unreadable: report, leave in place
            plan.append(PlannedMove(path, None, "error", flags=[f"could not read: {exc}"]))
            continue

        if parsed.content_hash in by_hash:
            original = by_hash[parsed.content_hash]
            plan.append(
                PlannedMove(
                    path, None, "duplicate", content_hash=parsed.content_hash,
                    flags=[f"identical to {original.source}"], parsed=parsed,
                )
            )
            continue
        already = existing.find(path, parsed.content_hash)
        if already is not None:
            plan.append(
                PlannedMove(
                    path, None, "duplicate", content_hash=parsed.content_hash,
                    flags=[f"already in destination: {already}"], parsed=parsed,
                )
            )
            continue

        family = parsed.family_name.strip() or path.stem
        style = (parsed.style or "Regular").strip()
        # Some editors write the family name into the style field.
        if style.lower() in ("normal", family.lower()):
            style = "Regular"
        label, from_copyright = version_label(parsed.version, parsed.copyright)
        item = PlannedMove(
            path,
            None,
            "move",
            vendor=short_vendor(parsed.foundry),
            family=family,
            style=style,
            version_label=label,
            content_hash=parsed.content_hash,
            flags=_review_flags(parsed, from_copyright),
            parsed=parsed,
        )
        by_hash[parsed.content_hash] = item
        pending.append(item)
        plan.append(item)

    _settle_vendors(pending, vendor, vendor_aliases or {})
    groups = _size_groups([(i.vendor, i.family, i.style) for i in pending])
    for item in pending:
        if (item.vendor, item.family) in groups:
            item.family, item.style = groups[(item.vendor, item.family)]
    if group_families:
        _group_by_shared_name(pending)

    for item in pending:
        folder = dest / _safe(item.vendor) / _safe(apply_case(item.family, case)) / _safe(item.version_label)
        stem = _safe(apply_case(f"{item.family} {item.style}", case))
        ext = item.source.suffix.lower()
        target = folder / f"{stem}{ext}"
        counter = 2
        while str(target).casefold() in taken or (
            target.exists() and target.resolve() != item.source.resolve()
        ):
            target = folder / f"{stem} ({counter}){ext}"
            counter += 1
        if counter > 2:
            item.flags.append("name already taken; numbered")
        taken.add(str(target).casefold())
        item.destination = target
        if target.resolve() == item.source.resolve():
            item.action = "unchanged"
    return plan


def _move_verified(src: Path, dst: Path, expected_hash: str) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)
    if _sha256(dst) != expected_hash:
        dst.unlink()
        raise OSError(f"copy of {src} did not verify; original kept")
    src.unlink()


def _prune_empty_dirs(start: Path, stop: Path) -> None:
    """Remove now-empty folders (ignoring .DS_Store) from start up to stop."""
    current = start.absolute()
    stop = stop.absolute()
    while current != stop and stop in current.parents:
        if not current.exists():  # already pruned for an earlier file
            current = current.parent
            continue
        entries = [e for e in current.iterdir() if e.name != ".DS_Store"]
        if entries:
            return
        for leftover in current.iterdir():
            leftover.unlink()
        current.rmdir()
        current = current.parent


def _update_db_paths(conn: sqlite3.Connection, moves: list[tuple[Path, Path]]) -> None:
    for old, new in moves:
        conn.execute(
            "UPDATE font_files SET path = ?, filename = ? WHERE path = ?",
            (str(new), new.name, str(old)),
        )
    conn.commit()


_CATALOG_FIELDS = [
    "Vendor", "Vendor source", "Designer", "Family", "Style", "Version", "Format", "Characters",
    "Copyright years", "Copyright", "Path", "Original path", "Review",
]


def _catalog_row(item: PlannedMove, dest: Path) -> dict:
    parsed = item.parsed
    return {
        "Vendor": item.vendor,
        "Vendor source": parsed.foundry_source or "",
        "Designer": parsed.designer or "",
        "Family": item.family,
        "Style": item.style,
        "Version": parsed.version or "",
        "Format": parsed.format,
        "Characters": parsed.glyph_count,
        "Copyright years": ", ".join(str(y) for y in copyright_years(parsed.copyright)),
        "Copyright": parsed.copyright or "",
        "Path": str(item.destination.relative_to(dest)),
        "Original path": str(item.source),
        "Review": "; ".join(item.flags),
    }


def write_catalog(plan: list[PlannedMove], dest: Path) -> Path:
    """Write/merge <dest>/_Font Catalog.csv: rows for this plan replace rows with
    the same path; earlier rows whose file still exists are kept."""
    catalog = dest / CATALOG_NAME
    rows: dict[str, dict] = {}
    if catalog.exists():
        with catalog.open(encoding="utf-8-sig", newline="") as fh:
            for row in csv.DictReader(fh):
                if row.get("Path") and (dest / row["Path"]).exists():
                    rows[row["Path"]] = row
    for item in plan:
        if item.destination is not None and item.parsed is not None:
            row = _catalog_row(item, dest)
            rows[row["Path"]] = row
    tmp = catalog.with_suffix(".tmp")
    with tmp.open("w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=_CATALOG_FIELDS, extrasaction="ignore")
        writer.writeheader()
        for key in sorted(rows, key=str.lower):
            writer.writerow(rows[key])
    os.replace(tmp, catalog)
    return catalog


def apply_organize(
    plan: list[PlannedMove],
    source: str | Path,
    dest: str | Path | None = None,
    conn: sqlite3.Connection | None = None,
) -> OrganizeResult:
    source = Path(source)
    dest = Path(dest) if dest is not None else source
    dest.mkdir(parents=True, exist_ok=True)
    result = OrganizeResult()
    done: list[tuple[Path, Path]] = []

    log_path = dest / f"{UNDO_LOG_PREFIX}{datetime.now():%Y%m%d-%H%M%S}.csv"
    with log_path.open("w", encoding="utf-8", newline="") as fh:
        log = csv.writer(fh)
        log.writerow(["original_path", "new_path", "sha256"])
        for item in plan:
            if item.action == "duplicate":
                result.duplicates += 1
            elif item.action == "error":
                result.errors += 1
            elif item.action == "unchanged":
                result.unchanged += 1
            else:
                try:
                    _move_verified(item.source, item.destination, item.content_hash)
                except OSError as exc:
                    item.flags.append(str(exc))
                    item.action = "error"
                    result.errors += 1
                    continue
                log.writerow([str(item.source), str(item.destination), item.content_hash])
                fh.flush()
                done.append((item.source, item.destination))
                result.moved += 1

    for old, _ in done:
        _prune_empty_dirs(old.parent, source)
    if conn is not None and done:
        _update_db_paths(conn, done)
    result.undo_log = log_path if done else None
    if not done:
        log_path.unlink()
    result.catalog = write_catalog(plan, dest)
    return result


def undo_organize(log_path: str | Path, conn: sqlite3.Connection | None = None) -> tuple[int, list[str]]:
    """Move every file in an undo log back. Returns (restored, problems)."""
    log_path = Path(log_path)
    restored = 0
    problems: list[str] = []
    back: list[tuple[Path, Path]] = []
    with log_path.open(encoding="utf-8", newline="") as fh:
        rows = list(csv.DictReader(fh))
    for row in reversed(rows):
        original, moved = Path(row["original_path"]), Path(row["new_path"])
        if not moved.exists():
            problems.append(f"missing: {moved}")
            continue
        if original.exists():
            problems.append(f"original location occupied: {original}")
            continue
        if _sha256(moved) != row["sha256"]:
            problems.append(f"changed since organize, left alone: {moved}")
            continue
        _move_verified(moved, original, row["sha256"])
        back.append((moved, original))
        restored += 1
    for moved, _ in back:
        _prune_empty_dirs(moved.parent, log_path.parent)
    if conn is not None and back:
        _update_db_paths(conn, back)
    return restored, problems


_INVENTORY_FIELDS = [f for f in _CATALOG_FIELDS if f not in ("Original path", "Review")] + ["Version folder"]


def write_inventory(root: str | Path, output: str | Path, vendor: str | None = None) -> tuple[Path, int]:
    """Catalog a folder as it is — nothing moves. Same columns as the organize
    catalog, so a hand-arranged folder (series folders, renamed families) can
    be re-catalogued after fonts are added. Returns (csv path, font count).

    vendor: write this vendor for every font (a single-publisher folder);
    otherwise the vendor resolved from each font's own data."""
    root = Path(root)
    rows = []
    for path in sorted(scan_directory(root), key=lambda p: str(p).casefold()):
        try:
            parsed = parse_font_file(path)
        except Exception as exc:
            rows.append({"Path": str(path.relative_to(root)), "Format": path.suffix.lower().lstrip("."),
                         "Family": f"(could not read: {exc})"})
            continue
        family = parsed.family_name.strip() or path.stem
        style = (parsed.style or "Regular").strip()
        if style.lower() in ("normal", family.lower()):
            style = "Regular"
        label, _ = version_label(parsed.version, parsed.copyright)
        rows.append({
            "Vendor": vendor or short_vendor(parsed.foundry),
            "Vendor source": "set by --vendor" if vendor else (parsed.foundry_source or ""),
            "Designer": parsed.designer or "",
            "Family": family,
            "Style": style,
            "Version": parsed.version or "",
            "Version folder": label,
            "Format": parsed.format,
            "Characters": parsed.glyph_count,
            "Copyright years": ", ".join(str(y) for y in copyright_years(parsed.copyright)),
            "Copyright": parsed.copyright or "",
            "Path": str(path.relative_to(root)),
        })
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    tmp = output.with_name(output.name + ".tmp")
    with tmp.open("w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=_INVENTORY_FIELDS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    os.replace(tmp, output)
    return output, len(rows)
