"""State-of-Health BC acquisition and analysis tooling.

Usable as a library (``from sohbc import load``) or through the
``sohbc`` command line interface.
"""

from __future__ import annotations

from .catalogue import ROOT, CatalogueError, Source, load
from .fetch import run_fetch
from .indicators import INDICATORS, IndicatorError, build

__version__ = "0.1.0"

__all__ = [
    "INDICATORS",
    "ROOT",
    "CatalogueError",
    "IndicatorError",
    "Source",
    "__version__",
    "build",
    "load",
    "run_fetch",
]
