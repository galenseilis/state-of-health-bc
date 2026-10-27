"""Generate a dynamic (runtime-traced) call graph for the sohbc tooling.

Unlike the static call graph (scripts/make_diagrams.py), which is derived
from the source, this one traces an offline exercise of the CLI under
cProfile and renders the observed call relationships with gprof2dot and
Graphviz:

    uv run python scripts/make_dynamic_callgraph.py

Output: reference/diagrams/callgraph-dynamic.svg (gitignored — it depends
on the code path exercised, not just on the source).
"""

from __future__ import annotations

import contextlib
import cProfile
import io
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PACKAGE_DIR = ROOT / "src" / "sohbc"
OUTPUT = ROOT / "reference" / "diagrams" / "callgraph-dynamic.svg"

# Offline CLI invocations to trace: no network access, no writes beyond
# the in-memory catalogue. "build" records the raw-data-missing path when
# data/raw/ has not been fetched.
SCENARIOS = (["validate"], ["list"], ["plan"], ["indicators"], ["build"])


def _run_capture(command: list[str]) -> str:
    """Run a command and return its standard output.

    Args:
        command: Command and arguments to execute.

    Returns:
        str: The command's standard output.

    Raises:
        SystemExit: If the command is missing or exits non-zero.
    """
    try:
        result = subprocess.run(command, check=True, capture_output=True, text=True)
    except FileNotFoundError:
        sys.exit(f"error: {command[0]} not found; install it or use 'uv run'")
    except subprocess.CalledProcessError as exc:
        sys.exit(f"error: {' '.join(command)} failed:\n{exc.stderr}")
    return result.stdout


def _trace_cli(stats_path: Path) -> None:
    """Profile the offline CLI scenarios and write cProfile stats.

    The ``build`` scenario is run against a raw-data directory that does
    not exist, so the trace exercises the "not fetched yet" path and never
    touches the network — even when ``data/raw/`` happens to be populated.

    Args:
        stats_path: Destination for the cProfile statistics file.
    """
    from sohbc import indicators
    from sohbc.__main__ import main as cli

    profiler = cProfile.Profile()
    with (
        contextlib.redirect_stdout(io.StringIO()),
        contextlib.redirect_stderr(io.StringIO()),
    ):
        profiler.enable()
        for argv in SCENARIOS:
            try:
                if argv == ["build"]:
                    original_raw = indicators.RAW_DIR
                    indicators.RAW_DIR = Path(tempfile.gettempdir()) / "sohbc-no-raw"
                    try:
                        cli(list(argv))
                    finally:
                        indicators.RAW_DIR = original_raw
                else:
                    cli(list(argv))
            except SystemExit:
                pass
        profiler.disable()
    profiler.dump_stats(stats_path)


def main() -> int:
    """Generate the dynamic call graph into reference/diagrams/.

    Returns:
        int: Zero on success.
    """
    if shutil.which("dot") is None:
        sys.exit("error: Graphviz 'dot' not found; install graphviz first")
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        stats_path = Path(tmp) / "cli.prof"
        _trace_cli(stats_path)
        dot = _run_capture(
            [
                "gprof2dot",
                "-f",
                "pstats",
                "--path",
                str(PACKAGE_DIR),
                "-n",
                "0",
                "-e",
                "0",
                str(stats_path),
            ]
        )
        try:
            subprocess.run(
                ["dot", "-Tsvg", "-o", str(OUTPUT)],
                input=dot,
                text=True,
                check=True,
            )
        except subprocess.CalledProcessError as exc:
            sys.exit(f"error: dot exited with {exc.returncode}")
    print(f"wrote {OUTPUT.relative_to(ROOT)} ({OUTPUT.stat().st_size} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
