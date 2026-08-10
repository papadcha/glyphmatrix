# TODO

Ordered roughly by the roadmap in `docs/proposal.md`. Nothing here is scheduled — pick items up in whatever order makes sense when picking work back up.

## V1 gaps (mentioned in the roadmap but not in the strict must-have table — not actually built yet)
- [ ] Search across the library (something Quod-Libet-style over tags/metadata, per the proposal's own suggestion — not a real NLP model)
- [ ] Favorites (no schema support yet either — decide: a bool column, or just a built-in "Favorites" collection?)

## V1.5 — Activation Manager
- [ ] 4-state model (`available`/`installed`/`active`/`disabled` — schema already supports this, `activations.state` CHECK constraint already lists all four; only the 2-state V0 logic is implemented)
- [ ] Activation sets (project-based groups of fonts that activate/deactivate together)
- [ ] Temporary activation
- [ ] Startup state restore
- [ ] Conflict handling
- [ ] Windows activation (`platforms/windows.py` — currently a stub with a clear NotImplementedError message)
- [ ] Linux activation (`platforms/linux.py` — same)

## V2 — Intelligence
- [ ] Smart collections (query language over tags/metadata — `collections.is_smart`/`smart_query` columns already exist, unused)
- [ ] License metadata / license conflict detection (`font_files.license` is captured at parse time but nothing does anything with it yet)
- [ ] Glyph inspector (UI-facing; `font_glyphs` already has the per-glyph data `compare` uses)
- [ ] Language coverage checks
- [ ] OpenType features
- [ ] Font pairing suggestions

## V3 — Ecosystem
- [ ] Google Fonts integration
- [ ] PDF catalog export
- [ ] Auto-activation per document/project
- [ ] AiMusix integration (API/CLI bridge, never tight-coupled — see docs/proposal.md "Standalone" section)

## V4 — experimental / maybe never
- [ ] AI mood tagging — deprioritized per proposal's own judgment (subjective, needs a model)
- [ ] Visual/image-to-font matcher — deprioritized (needs a large reference dataset)
- [ ] Cloud/team sync

## GUI
- [ ] Framework decision (Tauri vs Electron) — explicitly deferred until V1.5+, not decided
- [ ] "Font Canvas / Library view" concept noted in docs/proposal.md, not started

## Other gaps found on a full re-read of docs/proposal.md
- [ ] SVG preview export — tech stack section says preview should "export PNG/SVG"; `core/renderer.py` only does PNG (Pillow raster) so far

## Open decisions still unconfirmed
- [ ] Schema v0.1 review (open decision #4): "does it miss anything, or is anything overbuilt?" — never explicitly revisited since the initial 3-round freeze, even though `font_glyphs` was added afterward
- [ ] Standalone vs. AiMusix-integrated module (open decision #3) — went with standalone (separate `glyphmatrix` repo) by just following the proposal's own recommendation; never explicitly confirmed by the user in words
- [ ] `fontctl` output format: currently every command has a `--json` flag alongside plain text — this was assumed as a reasonable default, never explicitly confirmed by the user (proposal open decision #5)
