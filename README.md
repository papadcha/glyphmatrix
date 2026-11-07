# GlyphMatrix

Local Font Library & Activation Manager. Discover → Organize → Validate →
Activate → Use — local-first, non-destructive, no cloud/account.

Full design rationale, schema, and roadmap: [docs/proposal.md](docs/proposal.md).
Current status: [DONE.md](DONE.md) / [TODO.md](TODO.md).
OS scheduling setup (cron/launchd/Task Scheduler): [docs/scheduling.md](docs/scheduling.md).

## Status

V1, V1.5, and V2 are complete. All three activation providers (macOS, Windows, Linux)
verified on real hardware. See DONE.md/TODO.md for the detailed breakdown.

## Layout

```
src/glyphmatrix/
    core/       scanner, parser, ingest, query, compare, validator, duplicates,
                tags, collections, renderer, activation(_service), models, database, schema.sql
    platforms/  windows / macos / linux ActivationProvider implementations
    cli/        fontctl entry point
tests/
docs/           proposal.md
```

## CLI

```
fontctl scan <directory>
fontctl organize <directory> [--dest DIR] [--apply]
fontctl organize-undo <undo-log.csv>
fontctl inventory <directory> <output.csv> [--vendor NAME]
fontctl list
fontctl info <family>
fontctl compare <family> <style> <version_a> <version_b>
fontctl compare-files <file_a> <file_b>
fontctl validate
fontctl duplicates
fontctl project set <directory> <collection>
fontctl project activate [--path <dir>] [--doc <file>] [--for DURATION]
fontctl project deactivate [--path <dir>] [--doc <file>]
fontctl project list
fontctl specimen <directory> <output.pdf> [--text TEXT] [--title TITLE]
fontctl catalog <output.pdf> [--text TEXT] [--family FAMILY...]
fontctl gf key <API_KEY>
fontctl gf list [--category CATEGORY] [--subset SUBSET] [--sort alpha|popularity|...]
fontctl gf search <term>
fontctl gf info <family>
fontctl gf download <family> --dest <path>
fontctl activate <family>
fontctl deactivate <family>
fontctl activate-file <path>
fontctl deactivate-file <path>
fontctl tag {add,remove,list,find} ...
fontctl collection {create,add,remove,list,show} ...
fontctl preview <family> <style> [--text] [--size] [--waterfall] [-o]
```

Every command takes `--db <path>` (default `~/.glyphmatrix/library.db`) and
most take `--json` for scriptable output.

## Organizing a folder on disk

`fontctl organize` is the one command that moves user files, and only when
asked. It arranges a folder as `Vendor/Family/Version/Family Style.ext`:

- **Vendor**: Manufacturer (nameID 8) → known vendor ID → copyright holder;
  corporate suffixes dropped ("Monotype Imaging Inc." → "Monotype").
- **Version**: `v1.23`; if the font has no version, `1991` from the latest
  copyright year (plain ASCII, no `©`); otherwise `No Version`.
- Size variants that share a name ("KH Dot Hibiya 24/32") share one folder.
- Fonts in one source folder whose names extend each other ("Flea Market",
  "Flea Market Block Regular") become one family; `--no-family-grouping` turns
  this off.
- `--case sentence|title|lower` re-cases family folders and file names;
  `--vendor` / `--vendor-alias` set vendor folders exactly.

It is a dry run unless `--apply` is given. Moves are copy → verify sha256 →
delete original; identical duplicates are reported and left alone; anything
guessed (vendor from copyright, several copyright holders, version from the
unique ID) is listed for review. `--apply` writes `_Font Catalog.csv` and an
undo log (`_organize-<timestamp>.csv`) into the destination;
`fontctl organize-undo <log>` puts every file back. Library DB paths are
updated if the DB exists.

## Dev setup

```
pip install -e ".[dev]"
pytest
```
