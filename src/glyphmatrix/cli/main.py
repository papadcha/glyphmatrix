from __future__ import annotations

import click

# V0 command contract per docs/proposal.md. --json is available on every
# command; default output is plain text. Bodies are stubs pending Phase 0
# sign-off on exact output shape (open decision #5).


@click.group()
def fontctl() -> None:
    pass


@fontctl.command()
@click.argument("directory", type=click.Path(exists=True))
@click.option("--json", "as_json", is_flag=True)
def scan(directory: str, as_json: bool) -> None:
    raise NotImplementedError


@fontctl.command(name="list")
@click.option("--json", "as_json", is_flag=True)
def list_fonts(as_json: bool) -> None:
    raise NotImplementedError


@fontctl.command()
@click.argument("family")
@click.option("--json", "as_json", is_flag=True)
def info(family: str, as_json: bool) -> None:
    raise NotImplementedError


@fontctl.command()
@click.option("--json", "as_json", is_flag=True)
def validate(as_json: bool) -> None:
    raise NotImplementedError


@fontctl.command()
@click.option("--json", "as_json", is_flag=True)
def duplicates(as_json: bool) -> None:
    raise NotImplementedError


@fontctl.command()
@click.argument("family")
def activate(family: str) -> None:
    raise NotImplementedError


@fontctl.command()
@click.argument("family")
def deactivate(family: str) -> None:
    raise NotImplementedError


if __name__ == "__main__":
    fontctl()
