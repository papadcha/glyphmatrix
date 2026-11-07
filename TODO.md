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
- [ ] (low-medium) Non-Latin names: family/style are read through fontTools `getBestFamilyName`/`getBestSubFamilyName` (Windows English first, then any Windows language, then Mac Roman; checked with CJK, Arabic and Mac-Roman-only fonts) and non-Latin names go into folder and file names as they are. But there is no test with a non-Latin family/style/file name (the only non-ASCII in tests is "©"), and:
      - a style written in another language ("Regular" as Arabic) is not recognised as Regular (size grouping, file names, weight fallback all compare English words);
      - `list`/`info`/`--json` print JSON with `ensure_ascii` on (escaped `\uXXXX`), only `organize --json` uses `ensure_ascii=False`;
      - printing to a Windows console or redirected stdout with a legacy code page (cp1252) may raise `UnicodeEncodeError` — unverified, needs a Windows run;
      - catalog/inventory CSV are `utf-8-sig` (good for Excel); the undo log is plain UTF-8 + surrogateescape.
- [ ] (medium) `write_catalog` is unguarded and runs after every file has moved: a non-UTF-8 file name (`UnicodeEncodeError`; the catalog is strict `utf-8-sig`) or an `OSError` on `os.replace` gives a traceback, no summary and a stray `_Font Catalog.tmp`. Files and DB are safe. Same encoding problem in `write_inventory`. Catch it, write with surrogateescape, report a warning.
- [ ] (medium) macOS/Windows case-insensitive file systems: the "unchanged" test compares `resolve()` case-sensitively while `target.exists()` is not, so re-running `organize --case lower` on an organized folder plans every file as "name already taken; numbered" ("(2)") and `--apply` copies and renames them all. Compare case-insensitively (review finding J).
- [ ] (medium) organize moves only files with font extensions, so Type 1 companions (`.pfm`, `.afm`, `.inf`) and Bitstream `.TDF` sidecars stay behind; they also keep the old folder from being pruned. Move sidecars with their font (match by stem) and flag orphans.
- [ ] (medium) `ingest_directory` swallows any per-file exception, but the face/family mutations in `_resolve_known_face` are not in a savepoint, so a failure afterwards leaves them half-applied and the next commit keeps them. Reproduced: a changed file whose `ingest_font_file` raises leaves family `Beta`/style `Bold` in place of `Alpha`/`Regular` while the file row still has the old hash. Self-heals on the next successful scan (hash differs), but is wrong in between. Wrap each file in a SAVEPOINT and roll back on error.
- [ ] (medium) `scanner.is_skipped` drops every hidden folder below the scan root, so `fontctl scan ~` ignores `~/.fonts` and `~/.local/share/fonts`, and the scan run reports their fonts as removed. Exempt known font folders.
- [ ] (low) `short_vendor("Hoefler & Co.")` gives "Hoefler &": strip a dangling "&"/"and" after the suffix.
- [ ] (low) `version_label`: `_VERSION_NUMBER` takes a bare leading integer ("5-April-96" -> v5, "1996-04-05" -> v1996) and drops the patch ("1.0.1" -> v1.0, so 1.0.1 and 1.0.2 collide).
- [ ] (low) `copyright_years` ignores years before 1970 and takes only the first year of a short range ("1990-92" -> 1990, so the version folder is 1990 not 1992); `_YEARS` in the same module disagrees with it.
- [ ] (low) `scan_directory` walks everything with `rglob` and filters afterwards, so `#recycle`/`@eaDir` are fully traversed; prune with `os.walk`. `specimen.collect` repeats the same filter with its own extension list (already differs on `.dfont`): call `scan_directory`.
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
