# GlyphMatrix

Local Font Library & Activation Manager. Discover → Organize → Validate →
Activate → Use — local-first, non-destructive, no cloud/account.

Full design rationale, schema, and roadmap: [docs/proposal.md](docs/proposal.md).

## Status

Phase 0 (architecture freeze) scaffolding only — directory layout, frozen
SQLite schema, and interface stubs. No functional code yet; see the proposal's
open decisions before implementing `core/` logic.

## Layout

```
src/glyphmatrix/
    core/       scanner, parser, validator, duplicates, activation, renderer, models, database, schema.sql
    platforms/  windows / macos / linux ActivationProvider implementations
    cli/        fontctl entry point
tests/
docs/           proposal.md
```

## CLI (V0 contract)

```
fontctl scan <directory>
fontctl list
fontctl info <family>
fontctl validate
fontctl duplicates
fontctl activate <family>
fontctl deactivate <family>
```

## Dev setup

```
pip install -e ".[dev]"
pytest
```
