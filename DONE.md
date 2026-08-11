# Done

Chronological-ish; see git log for detail and `docs/proposal.md` for the design rationale behind each.

## V0 — Font Engine
- [x] Directory scaffold, frozen SQLite schema v0.1 (`core/schema.sql`)
- [x] `core/scanner.py` — recursive font file discovery
- [x] `core/parser.py` — fontTools-based metadata + per-glyph fingerprint extraction (name/OS2 tables, `RecordingPen` outline hashing, works across glyf/CFF)
- [x] `core/ingest.py` — find-or-create family/face, add/update/unchanged by content_hash, scan_runs logging
- [x] `fontctl scan`, `fontctl list`, `fontctl info` — wired to a real SQLite DB (`~/.glyphmatrix/library.db`)
- [x] `fontctl validate` — missing_file + corrupt checks, idempotent open/resolve against `validation_issues`
- [x] `fontctl duplicates` — byte-identical grouping by content_hash

## V1 — Font Library (the "Πυρήνας v1" must-haves)
- [x] `fontctl compare` — glyph-level version diff (`font_glyphs` table: outline_hash, added after user feedback — this was the original motivating use case)
- [x] Real macOS activation — `platforms/macos.py` (symlink into `~/Library/Fonts`, never a copy), `core/activation_service.py` (OS dispatch, 2-state `installed`/`active` model, per-file error collection), `fontctl activate`/`deactivate`. **Verified on real hardware**: font appeared/disappeared correctly in Font Book.
- [x] `fontctl tag {add,remove,list,find}` — `core/tags.py`
- [x] `fontctl collection {create,add,remove,list,show}` — `core/collections.py`, hierarchical via `parent_id`
- [x] `fontctl preview [--waterfall]` — `core/renderer.py`, Pillow-based raster export

## Legacy format tracking (2026-08-10)
- [x] `fontctl scan` now recognizes Type 1 (`.pfb`/`.pfa`) and legacy bitmap (`.bdf`/`.pcf`/`.fon`/`.dfont`) files — previously invisible to scan entirely. They get a `font_files` row (path/hash/format), so they show up in `list`/`info` and — since `content_hash` is format-agnostic — **duplicate detection works on them** (verified: two identical `.pfb` files under different names were correctly grouped). No family/style/glyph metadata yet (`parser.py`'s `_parse_unsupported` fallback — real parsing needs `fontTools.t1Lib` for Type 1, nothing usable for bitmap). Every such file gets an `unsupported_format` (severity `info`) `validation_issue` so `fontctl validate` makes the gap visible rather than silent.

## Packages & Documentation (2026-08-10)
- [x] `core/packages.py` + `fontctl package {create,add,remove,list,show,doc-add,doc-remove}` — tracks which real-world distribution bundle (e.g. "Adobe Font Folio 11") a font file came from, with vendor/notes metadata and attached document paths (license PDFs, readmes). New `packages`/`package_files`/`package_documents` tables — distinct concept from `collections` (provenance fact vs. user curation preference), membership at the `font_files` level to match `source`'s granularity. Verified end-to-end with the exact motivating scenario: two fonts tagged as belonging to a package, with vendor + a linked EULA PDF.

## Search + Favorites (2026-08-10)
- [x] `fontctl search <term>` — `query.search_library`, simple `LIKE` matching over family name/style/foundry/tags. Deliberately not a query language (that's V2 "smart collections", still on the roadmap) — just cheap keyword search, per the proposal's own "structured tags, not NLP" framing.
- [x] `fontctl favorite`/`unfavorite`/`favorites` — implemented as sugar over `collections`, not a new schema column: a reserved collection named "Favorites" auto-created on first use (`collections.get_or_create_favorites_collection`). Verified `fontctl collection show Favorites` and `fontctl favorites` return identical data — confirmed it's the same underlying data, not a parallel system.

## Classification + Backup/Restore (2026-08-10)
- [x] Automatic sans-serif/serif/script/etc. tagging — extracts `OS/2.sFamilyClass` (the "IBM font class", a standard classification type designers embed in the font) at scan time and auto-applies it as a tag via the existing tags system (e.g. "sans-serif", "oldstyle-serif", "slab-serif", "script"). This is objective metadata already in the file, not AI/ML classification — deliberately distinct from the deprioritized V4 "AI mood tagging" idea. No clean "blackletter/medieval" category exists in this standard; "oldstyle-serif" is the closest objective match. `parser.py`'s `_FAMILY_CLASSES` map covers the ~10 documented top-level classes.
- [x] `fontctl backup <path>` / `fontctl restore <path> [--yes]` — `core/backup.py`, using SQLite's online backup API (`Connection.backup()`), not a raw file copy — safe against an in-use connection. `restore` prompts for confirmation before overwriting the target DB unless `--yes` is passed. Verified round-trip: backed up a library, restored into a fresh DB, all data intact.

## Windows activation (2026-08-11)
- [x] `platforms/windows.py` — real `WindowsActivationProvider` via the GDI `AddFontResourceEx`/`RemoveFontResourceEx` APIs (ctypes, no pywin32 dependency) directly against the original file path — no copy, no registry write, no admin rights needed. Session-wide (not `FR_PRIVATE`) so other apps see it too, but doesn't persist across logoff/reboot, matching the on-demand model. Broadcasts `WM_FONTCHANGE` after each call so already-running apps notice.
- [x] Fixed a real cross-platform correctness gap surfaced while building this: `AddFontResourceEx` is reference-counted (two Add calls need two matching Remove calls), so `activation_service.py`'s `activate_family`/`deactivate_family` now skip the provider call entirely when the DB already records the target state — the DB is the cross-invocation source of truth, not any per-provider state. Regression tests added (`test_activate_family_is_idempotent_against_the_provider` etc.).
- [x] **Verified on real hardware**, and the verification itself surfaced a good lesson: synthetic `FontBuilder` test fonts pass fontTools/Pillow parsing but are rejected by GDI's stricter loader (`AddFontResourceEx` returned 0) — had to test with genuine font files instead. Also found that `System.Drawing.Text.InstalledFontCollection` (GDI+) doesn't reliably reflect classic GDI's `AddFontResourceEx`/`RemoveFontResourceEx` state — verified instead via `EnumFontFamiliesEx` (the same GDI subsystem the provider itself uses): a non-preinstalled font (DejaVu Sans / Inconsolata) went not-found → found → not-found across activate/deactivate through the actual `fontctl` CLI, not just the raw API.
- [x] `platforms/windows.py`'s `is_active()` raises `NotImplementedError` with an explanation — there's no GDI API to query `AddFontResourceEx` registration by path, so it's not implementable honestly; unlike macOS's symlink check, this doesn't block anything since `activation_service.py` never calls `is_active()` (it uses the DB instead).

## Linux activation (2026-08-11)
- [x] `platforms/linux.py` — `LinuxActivationProvider`, same symlink-not-copy design as macOS (`~/.local/share/fonts`, never a copy), plus an `fc-cache -f` refresh after each change since fontconfig doesn't reliably pick up new files the way macOS's Font Book does. All the same safety behavior as macOS: idempotent activate, stale-symlink replacement, refuses to touch an unmanaged real file. Fully unit-tested with `subprocess.run` mocked out — **not yet run against a real Linux machine**, unlike macOS (confirmed on hardware) and Windows (confirmed via `EnumFontFamiliesEx`). Flagged in TODO.md as needing that verification before being fully trusted.

## Infra
- [x] GitHub repo (private): https://github.com/papadcha/glyphmatrix — Windows + Mac sessions collaborating via push/pull
- [x] 154/154 tests passing (synthetic TTFs via `fontTools.fontBuilder`, portable across platforms — no system-font dependency; Windows-activation tests skip on non-Windows via `pytest.mark.skipif`, Linux-activation tests run everywhere since `fc-cache`/symlinks are fully mocked)

## Confirmed decisions
- [x] Open decision #1 (platform): macOS-first
- [x] Open decision #3 (standalone vs. AiMusix module): standalone, confirmed — integration only via API/CLI later, never tight-coupled
- [x] Open decision #4 (schema v0.1 review): done 2026-08-10 after real usage across every module. Fixed 3 real gaps — `families.foundry` existed but was never populated (now extracted from nameID 8), missing indexes on `font_files.path`/`content_hash`, and three UNIQUE constraints (`font_files.path`, `activations(font_file_id, platform)`, `collections.name`) that were only enforced in application code, not the schema. Everything else that looked unused (`axes_json`, `is_smart`/`smart_query`, `metadata_json`) is intentional forecast, not a gap — matches the "predict the field, add logic later" pattern already used for the 4-state activation model. Existing `library.db` files predate these constraints (`CREATE TABLE IF NOT EXISTS` doesn't retrofit them) — delete and rescan.
- [x] Open decision #5 (`fontctl` output format): confirmed — plain text default, `--json` flag per command. Already how every command was built; now explicitly locked rather than just assumed.
