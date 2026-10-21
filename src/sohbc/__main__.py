"""Command-line interface: python -m sohbc <command>."""

from __future__ import annotations

import argparse
import sys

from . import __version__
from .associations import (
    CANDIDATE_PAIRS,
    AssociationError,
    build_association,
)
from .catalogue import ROOT, CatalogueError, load
from .fetch import check_source, run_fetch
from .indicators import INDICATORS, IndicatorError, build


def _cmd_validate(_args: argparse.Namespace) -> int:
    try:
        sources = load()
    except CatalogueError as exc:
        print(f"INVALID: {exc}")
        return 1
    automated = sum(1 for s in sources if s.automated)
    print(
        f"OK: {len(sources)} sources ({automated} automated, {len(sources) - automated} manual)"
    )
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
            print(
                f"fetched {record['key']:<22} {record['bytes']} bytes -> {record['path']}"
            )
        else:
            print(f"manual  {record['key']:<22} {record.get('detail', '')}")
    return 0


def _cmd_indicators(_args: argparse.Namespace) -> int:
    width = max(len(k) for k in INDICATORS) if INDICATORS else 0
    for key, spec in INDICATORS.items():
        print(f"{key.ljust(width)}  {spec['domain']:<12}  {spec['title']}")
    print(f"\n{len(INDICATORS)} indicators")
    return 0


def _cmd_build(args: argparse.Namespace) -> int:
    keys = args.keys or list(INDICATORS)
    for key in keys:
        try:
            result = build(key)
        except IndicatorError as exc:
            print(f"FAIL  {key}: {exc}", file=sys.stderr)
            return 1
        print(
            f"built {key:<22} {result['rows']:>5} rows -> "
            f"{result['output'].relative_to(ROOT)}"
        )
        if result.get("dispersion") is not None:
            print(f"      dispersion -> {result['dispersion'].relative_to(ROOT)}")
        if result.get("summary") is not None:
            print(f"      summary -> {result['summary'].relative_to(ROOT)}")
        if result.get("standardised") is not None:
            print(f"      standardised -> {result['standardised'].relative_to(ROOT)}")
        if result.get("standardised_trend") is not None:
            print(
                "      standardised trend -> "
                f"{result['standardised_trend'].relative_to(ROOT)}"
            )
        if result.get("trend") is not None:
            print(f"      trend -> {result['trend'].relative_to(ROOT)}")
        if result.get("by_sex_trend") is not None:
            print(f"      by-sex trend -> {result['by_sex_trend'].relative_to(ROOT)}")
    return 0


def _cmd_associate(args: argparse.Namespace) -> int:
    if not args.keys:
        width = max(len(k) for k in CANDIDATE_PAIRS)
        for key, spec in CANDIDATE_PAIRS.items():
            print(f"{key.ljust(width)}  {spec['domain']:<12}  {spec['title']}")
        print(f"\n{len(CANDIDATE_PAIRS)} candidate associations")
        return 0
    for key in args.keys:
        try:
            built = build_association(key)
        except AssociationError as exc:
            print(f"FAIL  {key}: {exc}", file=sys.stderr)
            return 1
        result = built["result"]
        verdict = result["stability"]["verdict"]
        pooled = result["pooled"]
        print(
            f"assoc {key:<40} {verdict:<12} "
            f"r={pooled['pearson']['r']:+.3f} "
            f"slope={pooled['ols']['slope']:+.4f} "
            f"window={pooled['window']['start']}-{pooled['window']['end']} -> "
            f"{built['output'].relative_to(ROOT)}"
        )
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="sohbc", description="State-of-Health BC data tooling"
    )
    parser.add_argument("--version", action="version", version=f"sohbc {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("validate", help="validate the catalogue schema").set_defaults(
        func=_cmd_validate
    )
    sub.add_parser("list", help="list catalogued sources").set_defaults(func=_cmd_list)
    sub.add_parser("plan", help="show automated vs manual retrieval").set_defaults(
        func=_cmd_plan
    )

    check = sub.add_parser("check", help="verify source URLs are reachable")
    check.add_argument("keys", nargs="*")
    check.add_argument("--all", action="store_true", help="check every source")
    check.add_argument(
        "--include-download", action="store_true", help="also check download URLs"
    )
    check.set_defaults(func=_cmd_check)

    fetch = sub.add_parser("fetch", help="fetch automated sources into data/raw/")
    fetch.add_argument("keys", nargs="*")
    fetch.add_argument(
        "--all", action="store_true", help="fetch every automated source"
    )
    fetch.set_defaults(func=_cmd_fetch)

    sub.add_parser("indicators", help="list defined indicators").set_defaults(
        func=_cmd_indicators
    )

    build_parser = sub.add_parser(
        "build", help="build published indicator datasets from raw sources"
    )
    build_parser.add_argument("keys", nargs="*", help="indicator keys (default: all)")
    build_parser.set_defaults(func=_cmd_build)

    associate = sub.add_parser(
        "associate",
        help="estimate candidate associations with a stability check (M4)",
    )
    associate.add_argument(
        "keys", nargs="*", help="candidate keys (default: list them)"
    )
    associate.set_defaults(func=_cmd_associate)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except (CatalogueError, IndicatorError, AssociationError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
