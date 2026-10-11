"""Where BeelineBench finds its files.

The working folder holds what a run makes and what a user changes: ``beelinebench.toml``,
``.env``, ``data/``, ``results/``, ``traces/`` and ``.spend/``. It is:

1. the folder of ``BEELINEBENCH_HOME``, if that variable is set;
2. the clone of the repository, if the package runs from one;
3. the current folder, for a package that pip or uv installed.

The official benchmarks come from ``benchmarks.toml`` of the working folder if it has one,
as a clone does. Otherwise they come from the copy in the package.
"""

from __future__ import annotations

import os
from pathlib import Path

#: The folder of the package.
PACKAGE = Path(__file__).resolve().parent


def checkout() -> Path | None:
    """The clone of the repository that the package runs from, or ``None``."""
    root = PACKAGE.parent
    if (root / "pyproject.toml").exists() and (root / "benchmarks.toml").exists():
        return root
    return None


def home() -> Path:
    """The working folder."""
    if os.environ.get("BEELINEBENCH_HOME"):
        return Path(os.environ["BEELINEBENCH_HOME"]).expanduser().resolve()
    return checkout() or Path.cwd()


def official(project: Path) -> Path:
    """The file of the official benchmarks."""
    local = project / "benchmarks.toml"
    return local if local.exists() else PACKAGE / "benchmarks.toml"


def starter_config() -> Path:
    """The ``beelinebench.toml`` that ``init`` copies: that of the clone, or the package's copy."""
    root = checkout()
    return root / "beelinebench.toml" if root else PACKAGE / "beelinebench.toml"
