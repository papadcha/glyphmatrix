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
fontctl list
fontctl info <family>
fontctl compare <family> <style> <version_a> <version_b>
fontctl validate
fontctl duplicates
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

## Dev setup

```
pip install -e ".[dev]"
pytest
```
