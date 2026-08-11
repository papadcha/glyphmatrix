# TODO

Ordered roughly by the roadmap in `docs/proposal.md`. Nothing here is scheduled — pick items up in whatever order makes sense when picking work back up. Only open items live here — once something is done, it moves to DONE.md and gets removed from this file rather than staying checked off.

## V3 — Ecosystem
- [ ] PDF catalog export
- [ ] Auto-activation per document/project

## V4 — experimental / maybe never
- [ ] AI mood tagging — deprioritized per proposal's own judgment (subjective, needs a model)
- [ ] Visual/image-to-font matcher — deprioritized (needs a large reference dataset)
- [ ] Cloud/team sync

## V1.5 — Activation Manager follow-ups
V1.5 itself (4-state model, activation sets, temporary activation, startup restore, conflict
handling) is done as of 2026-08-11 — see DONE.md. What's left is infra/polish around it:

## GUI
- [ ] Framework decision (Tauri vs Electron) — explicitly deferred until V1.5+, not decided
- [ ] "Font Canvas / Library view" concept noted in docs/proposal.md, not started

## Legacy format support — full parsing (not yet attempted)
User has a real Type 1 / bitmap collection; as of 2026-08-10 these are scanned, hashed, and
deduped (see DONE.md) but not parsed for family/style/glyphs. Wanted next, roughly in order
of feasibility:
- [ ] Type 1 (`.pfb`/`.pfa`) real metadata + glyph parsing via `fontTools.t1Lib.T1Font`.
      `T1Font.getGlyphSet()` returns glyph objects that support `.draw(pen)` — same
      `RecordingPen`/outline_hash approach as SFNT should work in principle. Not attempted
      yet because building a valid test fixture requires hand-constructing Type 1's
      eexec-encrypted charstring bytecode (no `FontBuilder`-equivalent for Type 1 exists in
      fontTools), which couldn't be verified reliably in one sitting — needs either a real
      sample .pfb/.pfa to test against, or careful manual construction of a minimal one.
      Family/style come from `T1Font.font["FontInfo"]` (FamilyName) — no clean numeric
      weight, unlike OS/2.usWeightClass.
- [ ] Legacy bitmap (`.bdf`/`.pcf`/`.fon`/`.dfont`) — fontTools has no support at all for
      these. BDF is at least a text format (could hand-roll a minimal parser for FAMILY/SIZE
      fields); PCF is binary; `.fon`/`.dfont` are container formats (NE/PE resources,
      Mac resource fork) needing their own readers. Realistically separate, smaller
      projects per format — lowest priority of the three legacy-format items.

## Deprioritized — not near-term
- [ ] SVG preview export (vector glyph outlines via `fontTools.pens.SVGPathPen`, alongside the existing PNG raster export) — tech stack section says preview should "export PNG/SVG", but the user judged it out of scope for now on 2026-08-10: revisit much later, not soon
