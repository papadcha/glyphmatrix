# TODO

Ordered roughly by the roadmap in `docs/proposal.md`. Nothing here is scheduled — pick items up in whatever order makes sense when picking work back up. Only open items live here — once something is done, it moves to DONE.md and gets removed from this file rather than staying checked off.

## V3 — Ecosystem

## V4 — experimental / maybe never
- [ ] AI mood tagging — deprioritized per proposal's own judgment (subjective, needs a model)
- [ ] Visual/image-to-font matcher — deprioritized (needs a large reference dataset)
- [ ] Cloud/team sync

## GUI
- [ ] Framework decision (Tauri vs Electron) — explicitly deferred until V1.5+, not decided
- [ ] "Font Canvas / Library view" concept noted in docs/proposal.md, not started

## Legacy format support — full parsing
Type 1 (`.pfb`/`.pfa`), BDF, PCF, and FON are now fully parsed (see DONE.md). Remaining:
- [ ] Mac resource-fork bitmap (`.dfont`) — Mac resource fork container format needing
      its own reader. Lowest priority.

## Deprioritized — not near-term
- [ ] SVG preview export (vector glyph outlines via `fontTools.pens.SVGPathPen`, alongside the existing PNG raster export) — tech stack section says preview should "export PNG/SVG", but the user judged it out of scope for now on 2026-08-10: revisit much later, not soon

## Next (from real-folder use, 2026-11-06)
- [ ] **Class column in catalogs** (`organize`, `inventory`): design class with its source, so trust is visible.
  1. Bitstream `.TDF` sidecar next to a TTF (`fontid=0648` ↔ `TT0648M_.TTF`, `shortclass=Transitional 801`) — most reliable.
  2. Font's own `OS/2.sFamilyClass` / PANOSE (already parsed: `family_class`, `panose_class`) — often empty in freeware/old fonts, sometimes wrong (KH Dot pixel fonts say "sans-serif").
  3. Measured: monospace (equal advances), pixel (axis-aligned grid outlines), symbol/dingbat/word-art (reuse specimen detection), script (slant + soft terminals), serif vs sans (stem flare at `l`/`I` ends — the hard one).
  4. Name hints (Sans, Serif, Script, Mono, Stencil, Dingbats, Handwritten) only when nothing else.
- [ ] `.TDF` (Bitstream font-pack description files, `(C)BITS.'92`): read as sidecar metadata; never treat as fonts.
- [ ] GUI (Tauri vs Electron decision still open above).
- [ ] (low) catalog: `write_catalog` lists items whose move failed (action `error`) at a destination they never reached — write rows only for `move`/`unchanged`.
- [ ] (low) specimen: all A4 pages are kept in memory (~3.9 MB each) until one `save_all`; render page by page with Pillow `append=True` for folders of thousands of fonts.
- [ ] future: distinguish italic / oblique / slanted (fsSelection, post.italicAngle, slnt axis)
      - Currently only reads style from name table; fsSelection bit 0 (ITALIC), bit 9 (OBLIQUE), macStyle, post.italicAngle and the `slnt` axis are not read for TTF/OTF (only Type 1 and FON read italic)
      - A font with "Oblique" in name but fsSelection bit 0 (ITALIC) is shown as "Oblique"
      - A font with "Regular" in name but slanted (rare) is shown as upright
      - Variable fonts with slnt axis are shown as a single upright face
      - Requires new column (is_italic, is_oblique, italic_angle) or metadata_json
- [ ] Variable fonts: only `fvar` axis ranges are stored; read the default `wght` (cross-check with `usWeightClass`) and the named instances.
- [ ] Weight in the family name ("Foo Black" + style "Regular") is not read. Risky ("Black Chancery"); if done, only when `usWeightClass` is 400 and the style is "Regular".
- [ ] undo_organize: separate failures (exit 1) from warnings (exit 0)
      - Currently 'problems' conflates real failures ('could not restore', 'missing')
        with soft warnings ('replaced stale DB row... Rescan recommended')
      - Both give exit 1, but only failures should
      - Requires changing undo_organize signature (used by tests)
- [ ] organize/undo: DB update per file or per batch, so a kill mid-run cannot leave disk and library out of sync (today `_update_db_paths` runs once at the end).
      - Conflicts with the all-or-nothing rollback added for review finding F: once early batches are committed, a later DB failure can no longer roll them back, so rollback would have to move those files back and revert their rows.
      - Alternative that keeps the single transaction: `fontctl` command (or `scan` rescan) that re-syncs `font_files.path` from an undo log after an interrupted run.
- [ ] future: store resolved paths on ingest (needs migration/rescan strategy for existing libraries)
      - Also fixes G edge case: relative/absolute/symlink mismatch
      - Also fixes performance: no full table scan on fallback
      - Breaking change: requires migration or rescan for existing libraries
