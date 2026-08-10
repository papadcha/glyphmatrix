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

## Infra
- [x] GitHub repo (private): https://github.com/papadcha/glyphmatrix — Windows + Mac sessions collaborating via push/pull
- [x] 89/89 tests passing (synthetic TTFs via `fontTools.fontBuilder`, portable across platforms — no system-font dependency)

## Confirmed decisions
- [x] Open decision #1 (platform): macOS-first
- [x] Open decision #3 (standalone vs. AiMusix module): standalone, confirmed — integration only via API/CLI later, never tight-coupled
