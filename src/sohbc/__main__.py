"""Command-line interface: python -m sohbc <command>."""

from __future__ import annotations

import argparse
import sys

from . import __version__
from .catalogue import CatalogueError, load
from .fetch import check_source, run_fetch


def _cmd_validate(_args: argparse.Namespace) -> int:
    try:
        sources = load()
    except CatalogueError as exc:
        print(f"INVALID: {exc}")
        return 1
    automated = sum(1 for s in sources if s.automated)
    print(f"OK: {len(sources)} sources ({automated} automated, {len(sources) - automated} manual)")
    return 0


def _cmd_list(_args: argparse.Namespace) -> int:
    sources = load()
    width = max(len(s.key) for s in sources)
    print(f"{'key'.ljust(width)}  {'origin':<13}  {'form':<14}  {'access':<12}  auto")
    for s in sources:
        print(
            f"{s.key.ljust(width)}  {s.origin:<13}  {s.form:<14}  {s.access:<12}  "
            f"{'yes' if s.automated else 'no'}"
        )
    print(f"\n{len(sources)} sources")
    return 0


def _cmd_plan(_args: argparse.Namespace) -> int:
    sources = load()
    for s in sources:
        if s.automated:
            print(f"AUTO   {s.key:<22} {s.download['kind']:<9} {s.download['url']}")
        else:
            print(f"MANUAL {s.key:<22} {s.url}")
    return 0


def _cmd_check(args: argparse.Namespace) -> int:
    sources = load()
    selected = sources if args.all else [s for s in sources if s.key in args.keys]
    if not selected and not args.all:
        print("no sources selected; pass keys or --all")
        return 1
    failures = 0
    for source in selected:
        for result in check_source(source, include_download=args.include_download):
            mark = "ok " if result["reachable"] else "FAIL"
            if not result["reachable"]:
                failures += 1
            print(f"{mark} {result['status']}  {source.key:<22} {result['url']}")
    print(f"\n{failures} unreachable")
    return 1 if failures else 0


def _cmd_fetch(args: argparse.Namespace) -> int:
    keys = list(args.keys)
    if not keys and not args.all:
        print("no sources selected; pass keys or --all")
        return 1
    results = run_fetch(keys=keys, everything=args.all)
    for record in results:
        if record["status"] == "fetched":
            print(f"fetched {record['key']:<22} {record['bytes']} bytes -> {record['path']}")
        else:
            print(f"manual  {record['key']:<22} {record.get('detail', '')}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="sohbc", description="State-of-Health BC data tooling")
    parser.add_argument("--version", action="version", version=f"sohbc {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("validate", help="validate the catalogue schema").set_defaults(func=_cmd_validate)
    sub.add_parser("list", help="list catalogued sources").set_defaults(func=_cmd_list)
    sub.add_parser("plan", help="show automated vs manual retrieval").set_defaults(func=_cmd_plan)

    check = sub.add_parser("check", help="verify source URLs are reachable")
    check.add_argument("keys", nargs="*")
    check.add_argument("--all", action="store_true", help="check every source")
    check.add_argument("--include-download", action="store_true", help="also check download URLs")
    check.set_defaults(func=_cmd_check)

    fetch = sub.add_parser("fetch", help="fetch automated sources into data/raw/")
    fetch.add_argument("keys", nargs="*")
    fetch.add_argument("--all", action="store_true", help="fetch every automated source")
    fetch.set_defaults(func=_cmd_fetch)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except CatalogueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
