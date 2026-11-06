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
