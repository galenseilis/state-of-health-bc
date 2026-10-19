"""Generate the project's UML class diagram and static call graph.

Writes SVG files to reference/diagrams/ for embedding in the docs.
Requires Graphviz (`dot`) on PATH; pyreverse (from pylint) and pyan3
come from the project's dev dependency group. Run with:

    uv run python scripts/make_diagrams.py
"""

from __future__ import annotations

import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = "sohbc"
SOURCE_ROOT = ROOT / "src"
MODULES = sorted((SOURCE_ROOT / PACKAGE).glob("*.py"))
OUTPUT_DIR = ROOT / "reference" / "diagrams"

EDGE_RE = re.compile(r'^\s*"(?P<src>[^"]+)"\s*->\s*"(?P<dst>[^"]+)"')
NODE_RE = re.compile(r'^\s*"(?P<id>[^"]+)"\s*\[(?P<attrs>.*)\];?\s*$')
TOOLTIP_RE = re.compile(r'tooltip="(?P<tooltip>[^"]*)"')
CALLABLE_KINDS = ("function", "method", "class")


def _run(command: list[str]) -> None:
    """Run a command, exiting with a clear message on failure.

    Args:
        command: Command and arguments to execute.

    Raises:
        SystemExit: If the command is missing or exits non-zero.
    """
    try:
        subprocess.run(command, check=True)
    except FileNotFoundError:
        sys.exit(f"error: {command[0]} not found; install it or use 'uv run'")
    except subprocess.CalledProcessError as exc:
        sys.exit(f"error: {' '.join(command)} exited with {exc.returncode}")


def _parse_dot(
    dot_path: Path,
) -> tuple[dict[str, dict[str, str]], list[tuple[str, str]]]:
    """Parse node and edge records from a pyan3 dot file.

    Args:
        dot_path: Path to the dot file produced by pyan3.

    Returns:
        tuple: Mapping of node id to attributes (fq name, kind), and the
        list of (source, target) edge pairs.
    """
    nodes: dict[str, dict[str, str]] = {}
    edges: list[tuple[str, str]] = []
    for line in dot_path.read_text(encoding="utf-8").splitlines():
        edge = EDGE_RE.match(line)
        if edge:
            edges.append((edge["src"], edge["dst"]))
            continue
        node = NODE_RE.match(line)
        if not node:
            continue
        tooltip = TOOLTIP_RE.search(node["attrs"])
        if not tooltip:
            continue
        lines = tooltip["tooltip"].split("\\n")
        nodes[node["id"]] = {"fq": lines[0], "kind": lines[-1].split()[0]}
    return nodes, edges


def _write_call_graph(
    nodes: dict[str, dict[str, str]],
    edges: list[tuple[str, str]],
    dot_path: Path,
) -> None:
    """Write a styled call graph, keeping only callable and class nodes.

    Args:
        nodes: Node id to attributes (fq name, kind) mapping.
        edges: List of (source, target) edge pairs from pyan3.
        dot_path: Destination for the filtered dot file.
    """
    keep = {
        node_id for node_id, attrs in nodes.items() if attrs["kind"] in CALLABLE_KINDS
    }
    lines = [
        f'digraph "{PACKAGE}-callgraph" {{',
        "    graph [rankdir=TB, splines=polyline, nodesep=0.35, ranksep=0.55];",
        '    node [shape=box, style="rounded,filled", fillcolor="#eef4fb", fontsize=10];',
        '    edge [color="#4a5568", arrowsize=0.7];',
    ]
    for node_id in sorted(keep):
        attrs = nodes[node_id]
        label = attrs["fq"].removeprefix(f"{PACKAGE}.")
        fill = "#fde8e8" if attrs["kind"] == "class" else "#eef4fb"
        lines.append(
            f'    "{node_id}" [label="{label}", tooltip="{attrs["fq"]}",'
            f' fillcolor="{fill}"];'
        )
    for source, target in sorted(
        {(src, dst) for src, dst in edges if src in keep and dst in keep}
    ):
        lines.append(f'    "{source}" -> "{target}";')
    lines.append("}")
    dot_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _uml_class_diagram() -> None:
    """Generate the UML class diagram with pyreverse, saved as uml.svg."""
    _run(
        [
            "pyreverse",
            "-o",
            "svg",
            "-d",
            str(OUTPUT_DIR),
            "--project",
            PACKAGE,
            "--source-roots",
            str(SOURCE_ROOT),
            PACKAGE,
        ]
    )
    (OUTPUT_DIR / f"classes_{PACKAGE}.svg").rename(OUTPUT_DIR / "uml.svg")
    packages = OUTPUT_DIR / f"packages_{PACKAGE}.svg"
    if packages.exists():
        packages.unlink()


def _static_call_graph() -> None:
    """Generate the static call graph with pyan3, saved as callgraph.svg."""
    with tempfile.TemporaryDirectory() as tmp:
        raw = Path(tmp) / "callgraph.dot"
        styled = Path(tmp) / "callgraph-styled.dot"
        _run(
            [
                "pyan3",
                "--dot",
                "--no-defines",
                "--root",
                str(SOURCE_ROOT),
                "--file",
                str(raw),
                *[str(path) for path in MODULES],
            ]
        )
        nodes, edges = _parse_dot(raw)
        _write_call_graph(nodes, edges, styled)
        _run(["dot", "-Tsvg", "-o", str(OUTPUT_DIR / "callgraph.svg"), str(styled)])


def main() -> int:
    """Generate both diagrams into reference/diagrams/.

    Returns:
        int: Zero on success.
    """
    if shutil.which("dot") is None:
        sys.exit("error: Graphviz 'dot' not found; install graphviz first")
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    _uml_class_diagram()
    _static_call_graph()
    for name in ("uml.svg", "callgraph.svg"):
        target = OUTPUT_DIR / name
        print(f"wrote {target.relative_to(ROOT)} ({target.stat().st_size} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
