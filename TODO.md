# TODO

Ordered roughly by the roadmap in `docs/proposal.md`. Nothing here is scheduled — pick items up in whatever order makes sense when picking work back up. Only open items live here — once something is done, it moves to DONE.md and gets removed from this file rather than staying checked off.

## V2 — Intelligence
All of V2's originally-scoped items are done as of 2026-08-11 (smart collections, license
metadata, glyph inspector, language coverage, OpenType features, PANOSE, font pairing) — see
DONE.md for what each one actually does and how it was verified. One open follow-up remains:
- [ ] License classification is deliberately conservative (`core/licenses.py`, keyword matching against license text — no NLP). A real false positive was already found and fixed on 2026-08-11: "All Rights Reserved" alone was originally treated as a Commercial/Proprietary signal, but that phrase is standard copyright-ownership boilerplate that shows up in plenty of fully permissive licenses too (DejaVu Sans's Bitstream Vera license does this). If more license text patterns turn out unreliable the same way, prefer removing the signature (falling back to "Unknown") over trying to make the matching cleverer — a wrong confident answer is worse than an honest "don't know" for something with real licensing implications.

## V3 — Ecosystem
- [ ] Google Fonts integration
- [ ] PDF catalog export
- [ ] Auto-activation per document/project

## V4 — experimental / maybe never
- [ ] AI mood tagging — deprioritized per proposal's own judgment (subjective, needs a model)
- [ ] Visual/image-to-font matcher — deprioritized (needs a large reference dataset)
- [ ] Cloud/team sync

## V1.5 — Activation Manager follow-ups
V1.5 itself (4-state model, activation sets, temporary activation, startup restore, conflict
handling) is done as of 2026-08-11 — see DONE.md. What's left is infra/polish around it:
- [ ] Per-file activation command — `activate_family`/`activate_set` only operate on whole families/sets, so once a conflict picks a winner (lowest font_file id, deterministic), there's currently no way to activate the *other* file under a conflicting face instead without removing/disabling the winner first. A `fontctl activate-file <path>` (or similar) would let a user deliberately resolve a conflict in favor of the non-default file.

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
