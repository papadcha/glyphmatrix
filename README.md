# GlyphMatrix

Local Font Library & Activation Manager. Discover → Organize → Validate →
Activate → Use — local-first, non-destructive, no cloud/account.

Full design rationale, schema, and roadmap: [docs/proposal.md](docs/proposal.md).
Current status: [DONE.md](DONE.md) / [TODO.md](TODO.md).

## Status

All 6 "Πυρήνας v1" must-haves from the proposal are implemented: scan/parse,
duplicate & corruption detection, version/glyph comparison, tags &
collections, preview, and real activation on macOS (verified on hardware —
Windows/Linux activation are still stubs). See DONE.md/TODO.md for the
detailed breakdown.

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
fontctl list
fontctl info <family>
fontctl compare <family> <style> <version_a> <version_b>
fontctl validate
fontctl duplicates
fontctl activate <family>
fontctl deactivate <family>
fontctl tag {add,remove,list,find} ...
fontctl collection {create,add,remove,list,show} ...
fontctl preview <family> <style> [--text] [--size] [--waterfall] [-o]
```

Every command takes `--db <path>` (default `~/.glyphmatrix/library.db`) and
most take `--json` for scriptable output.

## Dev setup

```
pip install -e ".[dev]"
pytest
```
