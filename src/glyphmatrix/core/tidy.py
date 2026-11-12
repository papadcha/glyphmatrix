"""The "tidy" organizing profile — a second layout next to organize's
Vendor/Family/Version one, built from a real 38,000-font library (RULES.md).

    <Holder>/<Family>/[<format>/]<Family> <Style>.<ext>
    <Holder>/<Family>/[<format>/]_versions/<Family> <Style> (v1.2).<ext>
    _Unknown/_broken/<file>        files that could not be read
    _collections/<file>            .ttc/.otc collections

Differences from the default profile:
- The holder is the one the file itself claims: copyright (nameID 0), then
  designer (9), then manufacturer (8) — not the manufacturer first.
- No version folder. A second version of the same family+style goes to
  _versions/ with its version in the name.
- A format folder (ttf/, otf/, pfb/...) only when a family has several formats.

Moves are ordinary PlannedMove entries, so apply_organize's safety checks
(plan check, manifest, copy-verify-delete, undo log) apply unchanged.
The exceptions are data (tidy_rules.toml), not code.
"""
from __future__ import annotations

import re
import sqlite3
import tempfile
import tomllib
from collections import Counter
from typing import NamedTuple
from importlib import resources
from pathlib import Path

from glyphmatrix.core.extract import (
    collection_extension,
    extract_member,
    is_collection_file,
    member_count,
    member_extension,
)
from glyphmatrix.core.foundries import default_foundries
from glyphmatrix.core.foundry import (
    _COPYRIGHT_MARK,
    clean_designer,
    holder_from_copyright,
    is_tool_default,
)
from glyphmatrix.core.organize import (
    PlannedMove,
    _ExistingFiles,
    _is_active,
    _review_flags,
    _safe,
    _sha256,
    apply_case,
    version_label,
)
from fontTools.ttLib import TTFont

from glyphmatrix.core.parser import parse_font_file, quiet_fonttools
from glyphmatrix.core.scanner import scan_directory

UNKNOWN = "_Unknown"
BROKEN = "_broken"
COLLECTIONS = "_collections"
VERSIONS = "_versions"

_EMAIL = re.compile(r"\S+@\S+")
_URL = re.compile(r"(?:https?://|https?---|www\.)\S*", re.IGNORECASE)
_PHONE = re.compile(r"\+?\d[\d ()./-]{7,}\d")
_MARKS = re.compile("[®™©]")
_BOILERPLATE = re.compile(r"[,.]?\s*(?:all rights reserved|with reserved font name).*$", re.IGNORECASE)
_YEAR_BRACKET = re.compile(r"(\b(?:19|20)\d{2}\s*)\[([^\]]+)\]")


class Rules:
    def __init__(self, data: dict):
        holder = data.get("holder", {})
        catalogue = default_foundries()
        # The catalogue (foundries.toml) first; tidy_rules.toml and --rules entries win over it.
        exact = {**catalogue.tidy_exact(), **{k.casefold(): v for k, v in holder.get("exact", {}).items()}}
        prefix = {**catalogue.tidy_prefix(), **{k.casefold(): v for k, v in holder.get("prefix", {}).items()}}
        self.exact = {k.casefold(): v for k, v in exact.items()}
        self.prefix = sorted(((k.casefold(), v) for k, v in prefix.items()), key=lambda kv: -len(kv[0]))
        self.not_publishers = [re.compile(p, re.IGNORECASE)
                               for p in [*holder.get("not_publishers", []), *catalogue.non_publisher_patterns()]]


def load_rules(extra: str | Path | None = None) -> Rules:
    """The packaged rules, with a user file merged on top (its entries win)."""
    data = tomllib.loads(resources.files("glyphmatrix.core").joinpath("tidy_rules.toml").read_text("utf-8"))
    if extra is not None:
        user = tomllib.loads(Path(extra).read_text("utf-8"))
        holder = data.setdefault("holder", {})
        for key, value in user.get("holder", {}).items():
            if isinstance(value, dict):
                holder.setdefault(key, {}).update(value)
            else:
                holder[key] = list(holder.get(key, [])) + list(value)
    return Rules(data)


def _lookup(key: str, rules: Rules) -> str | None:
    """Canonical name for an exact or prefix match; "" means 'not a publisher'; None no match."""
    mapped = rules.exact.get(key)
    if mapped is None:
        mapped = next((v for k, v in rules.prefix if key.startswith(k)), None)
    return mapped


def clean_holder(name: str | None, rules: Rules) -> str | None:
    """A publisher name as it should appear as a folder, or None when the text
    is not a publisher (tool, licence, description, leftover). RULES B1/B2/E."""
    if not name:
        return None
    raw = re.sub(r"\s+", " ", name).strip(" -,.;:")
    mapped = _lookup(raw.casefold(), rules)             # "(URW)++", "cleev@o2.pl - ..." need the raw text
    if mapped is not None:
        return mapped or None
    text = _MARKS.sub("", _URL.sub("", _EMAIL.sub("", name)))
    text = _PHONE.sub("", text)
    text = _BOILERPLATE.sub("", text)
    text = re.split(r"[(\[]|,\s*\d", text, maxsplit=1)[0]
    text = re.sub(r"^[\W_]+", "", text)             # "__ Sora Sagano"
    text = re.sub(r"\s+", " ", text).strip(" -,.;:")
    if not text:
        return None
    mapped = _lookup(text.casefold(), rules)
    if mapped is not None:
        return mapped or None
    if is_tool_default(text) or any(p.match(text) for p in rules.not_publishers) or len(text) > 60:
        return None
    return text


def _claim_starts(text: str) -> list[int]:
    """Where each copyright claim begins. 'Copyright (c)' is one claim, and a
    'Portions (C) X' mark is not a claim of its own (RULES B2 #1)."""
    starts: list[int] = []
    last_end = -1
    for match in _COPYRIGHT_MARK.finditer(text):
        if text[max(0, match.start() - 16):match.start()].casefold().count("portions"):
            continue
        if last_end >= 0 and not text[last_end:match.start()].strip():
            last_end = match.end()
            continue
        starts.append(match.start())
        last_end = match.end()
    return starts


def holder_from_claims(copyright_text: str | None, rules: Rules) -> tuple[str | None, int]:
    """(holder, number of claims). The last claim that names a real publisher
    wins: the last modifier in a chain is the holder (RULES B2 #6)."""
    if not copyright_text:
        return None, 0
    # Some fonts carry escaped text ("\\(c\\) 1996 ..."); a bracketed name right
    # after the year ("2003 [T-26] Chicago") is the publisher, not a comment.
    copyright_text = _YEAR_BRACKET.sub(r"\1\2", copyright_text.replace("\\", ""))
    starts = _claim_starts(copyright_text)
    if not starts:
        # a free-form notice ("Freeware! from A. Carr ..."): only the rules may name a holder
        mapped = _lookup(re.sub(r"\s+", " ", copyright_text).strip().casefold(), rules)
        return (mapped or None), 0
    ends = starts[1:] + [len(copyright_text)]
    # each claim on its own: a tool note in one must not discard the others
    for start, end in reversed(list(zip(starts, ends))):
        holder = clean_holder(holder_from_copyright(copyright_text[start:end], keep_suffix=True), rules)
        if holder:
            return holder, len(starts)
    return None, len(starts)


def resolve_holder(parsed, rules: Rules) -> tuple[str | None, str | None, int]:
    """(holder, source, claims): copyright, then designer, then manufacturer."""
    holder, claims = holder_from_claims(parsed.copyright, rules)
    if holder:
        return holder, "copyright", claims
    holder = clean_holder(clean_designer(parsed.designer), rules)
    if holder:
        return holder, "designer", claims
    if parsed.foundry_source in ("manufacturer", "stamp"):
        holder = clean_holder(parsed.foundry, rules)
        if holder:
            return holder, parsed.foundry_source, claims
    return None, None, claims


def _ext(item: PlannedMove) -> str:
    """Extension the file will have: that of the extracted font for a collection member."""
    return item.extension or item.source.suffix.lower()


def _read_head(path: Path) -> tuple[float, str, str | None] | None:
    """(head.fontRevision, style, version string) of a font, read lazily; None if unreadable."""
    try:
        with quiet_fonttools(), TTFont(path, lazy=True, fontNumber=0) as font:
            name = font["name"]
            style = (name.getBestSubFamilyName() or "Regular").strip()
            return round(float(font["head"].fontRevision), 3), style, name.getDebugName(5)
    except Exception:  # noqa: BLE001 — an unreadable neighbour is simply not compared
        return None


def _revision_label(revision: float) -> str:
    text = f"{revision:.3f}".rstrip("0")
    return "v" + (text + "0" if text.endswith(".") else text)


def _label_text(version_text: str, revision: float | None) -> str:
    """What goes in a _versions file name: the version number when the font
    has a clean one, else its head revision, else 'unversioned'."""
    if re.fullmatch(r"v\d+(?:\.\d+)?", version_text):
        return version_text
    if revision is not None:
        return _revision_label(revision)
    return version_text if version_text != "No Version" else "unversioned"


def _rank(revision: float | None, version_text: str) -> tuple[float, tuple[int, ...]]:
    """Orders versions of one style: head revision first (it is a number, unlike
    '17.d1e2'), the version string to break ties."""
    return (revision if revision is not None else -1.0, _version_key(version_text))


class _Existing(NamedTuple):
    path: Path
    style: str
    ext: str
    revision: float | None
    version_text: str
    text: str


def _version_key(label: str) -> tuple[int, ...]:
    match = re.fullmatch(r"v(\d+)(?:\.(\d+))?", label)
    return (int(match.group(1)), int(match.group(2) or 0)) if match else (-1,)


def _parts(holder: str) -> list[str]:
    return [_safe(p) for p in holder.split("/") if p.strip()]


def plan_tidy(
    source: str | Path,
    dest: str | Path | None = None,
    rules: Rules | None = None,
    case: str = "as-is",
    conn: sqlite3.Connection | None = None,
    fold_reissues: bool = False,
) -> list[PlannedMove]:
    source = Path(source)
    dest = Path(dest) if dest is not None else source
    rules = rules or load_rules()
    plan: list[PlannedMove] = []
    by_hash: dict[str, PlannedMove] = {}
    existing = _ExistingFiles(dest, exclude=source)
    normal: list[PlannedMove] = []
    fixed: dict[int, Path] = {}      # item id -> folder that is not the Holder/Family one
    active: set[int] = set()

    def duplicate_of(path: Path, content_hash: str) -> PlannedMove | None:
        if content_hash in by_hash:
            return PlannedMove(path, None, "duplicate", content_hash=content_hash,
                               flags=[f"identical to {by_hash[content_hash].source}"])
        already = existing.find(path, content_hash)
        if already is not None:
            return PlannedMove(path, None, "duplicate", content_hash=content_hash,
                               flags=[f"already in destination: {already}"])
        return None

    collections: list[PlannedMove] = []

    def describe(path: Path, parsed, content_hash: str, relative: Path | None, action: str = "move",
                 revision: float | None = None) -> PlannedMove:
        holder, source_kind, claims = resolve_holder(parsed, rules)
        flags = [f for f in _review_flags(parsed, False) if not f.startswith("vendor") and "version" not in f]
        if holder is None and relative is not None and path.suffix.lower() == ".fon" and len(relative.parts) >= 3:
            holder, source_kind = clean_holder(relative.parts[0], rules), "folder"
        if source_kind in ("designer", "manufacturer", "folder"):
            flags.append(f"holder taken from {source_kind}")
        elif source_kind == "stamp":
            flags.append("holder taken from the foundry's stamp in the unique ID")
        if fold_reissues and holder:
            packager = default_foundries().folded_into(holder, parsed.unique_id)
            if packager is not None:
                flags.append(f"folded into {packager.tidy_name} (reissue of {holder})")
                holder = packager.tidy_name
        if holder is None:
            flags.append("holder unknown")
        if claims >= 2:
            flags.append("copyright names several parties")
        family = parsed.family_name.strip() or path.stem
        style = (parsed.style or "Regular").strip()
        if style.lower() in ("normal", family.lower()):
            style = "Regular"
        label, _ = version_label(parsed.version, parsed.copyright)
        return PlannedMove(path, None, action, vendor=holder or UNKNOWN, family=family, style=style,
                           version_label=label, content_hash=content_hash, flags=flags, parsed=parsed,
                           revision=revision)

    for path in sorted(scan_directory(source)):
        relative = path.relative_to(source)         # never split an absolute path (RULES A8)
        ext = path.suffix.lower()
        try:
            content_hash = _sha256(path)
        except OSError as exc:
            plan.append(PlannedMove(path, None, "error", flags=[f"could not read: {exc}"]))
            continue
        dup = duplicate_of(path, content_hash)
        if dup:
            plan.append(dup)
            continue
        item: PlannedMove
        if is_collection_file(path):
            # the collection itself is kept whole in _collections/; its fonts are written out below
            item = PlannedMove(path, None, "move", vendor=COLLECTIONS, family=path.stem,
                               content_hash=content_hash)
            fixed[id(item)] = dest / COLLECTIONS
            collections.append(item)
            if collection_extension(path) != path.suffix.lower():
                item.extension = collection_extension(path)
                item.flags.append(f"is a font collection named {path.suffix}; renamed to {item.extension}")
        else:
            try:
                parsed = parse_font_file(path)
            except Exception as exc:                 # noqa: BLE001 — unreadable goes to _broken
                item = PlannedMove(path, None, "move", vendor=UNKNOWN, family=path.stem,
                                   content_hash=content_hash, flags=[f"unreadable: {exc}"])
                fixed[id(item)] = dest / UNKNOWN / BROKEN
            else:
                head = _read_head(path)
                item = describe(path, parsed, content_hash, relative, revision=head[0] if head else None)
                normal.append(item)
        by_hash[content_hash] = item
        plan.append(item)
        if conn is not None and _is_active(conn, path):
            active.add(id(item))

    # Fonts inside collections, after every plain file has claimed its hash: on a
    # second run the members already extracted are then recognised, not repeated.
    with tempfile.TemporaryDirectory(prefix="glyphmatrix-members-") as tmp:
        for collection in collections:
            skipped = 0
            try:
                count = member_count(collection.source)
            except Exception as exc:                 # noqa: BLE001
                collection.flags.append(f"could not list its fonts: {exc}")
                continue
            for index in range(count):
                try:
                    data = extract_member(collection.source, index)
                    probe = Path(tmp) / f"member{member_extension(data)}"
                    probe.write_bytes(data)
                    parsed = parse_font_file(probe)
                except Exception as exc:             # noqa: BLE001
                    collection.flags.append(f"font {index} could not be read: {exc}")
                    continue
                if parsed.content_hash in by_hash or existing.find(probe, parsed.content_hash) is not None:
                    skipped += 1
                    continue
                head = _read_head(probe)
                member = describe(collection.source, parsed, parsed.content_hash, None, action="extract",
                                  revision=head[0] if head else None)
                member.member, member.extension = index, member_extension(data)
                member.flags.append(f"font {index + 1} of {count} in {collection.source.name}")
                by_hash[parsed.content_hash] = member
                normal.append(member)
                plan.append(member)
            if skipped:
                collection.flags.append(f"{skipped} of {count} fonts already present, not extracted")

    # One spelling per holder, differing only in case: the folder already in
    # the destination wins, otherwise the most common one (RULES E1).
    on_disk = {d.name.casefold(): d.name for d in dest.iterdir() if d.is_dir()} if dest.is_dir() else {}
    spellings: dict[str, Counter] = {}
    for item in normal:
        spellings.setdefault(item.vendor.split("/")[0].casefold(), Counter())[item.vendor] += 1
    for item in normal:
        top = item.vendor.split("/")[0].casefold()
        if top in on_disk:
            rest = item.vendor.split("/", 1)[1:]
            item.vendor = "/".join([on_disk[top], *rest])
        else:
            counts = spellings[top]
            item.vendor = max(counts, key=lambda name: (counts[name], name))

    plan_paths = {i.source.resolve() for i in plan}
    family_cache: dict[Path, tuple[list[_Existing], set[str]]] = {}

    def family_folder(item: PlannedMove) -> Path:
        return dest.joinpath(*_parts(item.vendor), _safe(apply_case(item.family, case)))

    def family_files(folder: Path) -> tuple[list[_Existing], set[str]]:
        """Fonts already in this family's folder in the destination (not part of this
        plan) and their extensions: they take part in the version and format decisions."""
        if folder not in family_cache:
            found: list[_Existing] = []
            exts: set[str] = set()
            if folder.is_dir():
                for path in scan_directory(folder):
                    if path.resolve() in plan_paths:
                        continue
                    exts.add(path.suffix.lower())
                    head = _read_head(path)
                    if head is None:
                        continue
                    revision, style, version = head
                    style = "Regular" if style.lower() == "normal" else style
                    vtext = version_label(version, None)[0]
                    found.append(_Existing(path, style.casefold(), path.suffix.lower(), revision, vtext,
                                           _label_text(vtext, revision)))
            family_cache[folder] = (found, exts)
        return family_cache[folder]

    formats: dict[tuple[str, str], set[str]] = {}
    for item in normal:
        key = (item.vendor.casefold(), item.family.casefold())
        formats.setdefault(key, set()).add(_ext(item))
        formats[key] |= family_files(family_folder(item))[1]
    groups: dict[tuple, list[PlannedMove]] = {}
    for item in normal:
        key = (item.vendor.casefold(), item.family.casefold(), item.style.casefold(), _ext(item))
        groups.setdefault(key, []).append(item)

    taken: set[str] = set()
    vacated: set[str] = set()      # existing files that step aside to _versions in this plan

    def place(item: PlannedMove, folder: Path, stem: str, ext: str) -> Path:
        target = folder / f"{stem}{ext}"
        counter = 2

        def occupied(path: Path) -> bool:
            return str(path).casefold() in taken or (
                path.exists() and path.resolve() != item.source.resolve() and str(path).casefold() not in vacated)

        while occupied(target):
            target = folder / f"{stem} ({counter}){ext}"
            counter += 1
        if counter > 2:
            item.flags.append("name already taken; numbered")
        taken.add(str(target).casefold())
        return target

    def to_versions(item: PlannedMove, folder: Path, stem: str, ext: str, why: str) -> None:
        item.destination = place(item, folder / VERSIONS, f"{stem} ({_label_text(item.version_label, item.revision)})", ext)
        item.flags.append(why)

    for members in groups.values():
        first = members[0]
        ext, fam = _ext(first), family_folder(first)
        base = fam / ext.lstrip(".") if len(formats[(first.vendor.casefold(), first.family.casefold())]) > 1 else fam
        stem = _safe(apply_case(f"{first.family} {first.style}", case))
        same = [e for e in family_files(fam)[0] if e.style == first.style.casefold() and e.ext == ext]
        primaries = sorted((e for e in same if e.path.parent.name != VERSIONS),
                           key=lambda e: _rank(e.revision, e.version_text), reverse=True)
        members.sort(key=lambda i: (_rank(i.revision, i.version_label), str(i.source)), reverse=True)
        newest = members[0]
        library_best = max((_rank(e.revision, e.version_text) for e in same), default=None)
        blocked = conn is not None and any(_is_active(conn, e.path) for e in primaries)
        if library_best is not None and (library_best >= _rank(newest.revision, newest.version_label) or blocked):
            # something at least as new is already in the library: everything new steps aside
            home = primaries[0].path.parent if primaries else base
            for item in members:
                to_versions(item, home, stem, ext,
                            "the library already has an equal or newer version of this style"
                            if not blocked else "the current version is active in the library; kept in _versions")
            continue
        for e in primaries:                     # the library's current files give way to the newer one
            vacated.add(str(e.path).casefold())
        newest.destination = place(newest, base, stem, ext)
        for e in primaries:
            step = PlannedMove(e.path, None, "move", vendor=newest.vendor, family=newest.family,
                               style=newest.style, version_label=e.text, content_hash=_sha256(e.path),
                               revision=e.revision, flags=["older version; a newer one is being added"])
            step.destination = place(step, base / VERSIONS, f"{stem} ({e.text})", ext)
            plan.append(step)
        for item in members[1:]:
            to_versions(item, base, stem, ext, "another version of this style exists; kept in _versions")

    for item in plan:
        if id(item) in fixed:
            folder = fixed[id(item)]
            item.destination = place(item, folder, _safe(item.source.stem), _ext(item))
    for item in plan:
        if item.action != "move" or item.destination is None:
            continue
        if item.destination.resolve() == item.source.resolve():
            item.action = "unchanged"
        elif id(item) in active:
            item.destination = None
            item.action = "active"
            item.flags.append("active in the library: not moved, deactivate it first")
    return plan
