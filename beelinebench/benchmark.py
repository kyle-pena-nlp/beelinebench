"""Benchmark definitions, and whether a run matches an official one.

``benchmarks.toml`` holds the official definitions. A new version adds a table,
and no table is changed or removed, so every older version can be run again.
``beelinebench.toml`` can define more benchmarks, for experiments. Their names must
not be official names.

A run matches an official benchmark when its rules and the settings of each of
its domains are those of the official one. The trials do not decide the match:
trial ``n`` is the same problem in every run, so a run of fewer trials or fewer
domains is a part of the official run.
"""

from __future__ import annotations

import tomllib
from collections.abc import Sequence
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

RULES = ("max_expansions", "max_frontier", "seed")


@dataclass(frozen=True)
class Benchmark:
    name: str
    trials: int
    #: Both arms stop after this many explorations, solved or not.
    max_expansions: int
    max_frontier: int
    #: For each domain, its heuristic and the parameters of its trials.
    domains: dict[str, dict[str, Any]]
    #: The master seed of every draw: the trials, the option orders and the dropped states.
    #: ``None`` keeps the draws of a benchmark without one, such as 1.0.0.
    seed: int | None = None


def parse(tables: dict[str, Any]) -> dict[str, Benchmark]:
    for name, t in tables.items():
        check_seed(t.get("seed"), f"benchmark {name}")
    return {name: Benchmark(name=name, trials=t["trials"],
                            max_expansions=t["max_expansions"],
                            max_frontier=t["max_frontier"],
                            domains={d: dict(p) for d, p in t["domains"].items()},
                            seed=t.get("seed"))
            for name, t in tables.items()}


def check_seed(seed: Any, where: str) -> None:
    """A seed is an integer. A string such as ``"7"`` would give other draws than ``7``."""
    if seed is not None and (isinstance(seed, bool) or not isinstance(seed, int)):
        raise ValueError(f"{where}: seed must be an integer, not {seed!r}")


def seeded(b: Benchmark, seed: int | None) -> Benchmark:
    """``b`` with the master seed ``seed``, named for it so that its results have their own
    folder, for example ``1.0.0.seed-7``. ``None`` gives ``b``.
    """
    if seed is None or seed == b.seed:
        return b
    check_seed(seed, "--seed")
    return replace(b, name=f"{b.name}.seed-{seed}", seed=seed)


def load(path: Path) -> dict[str, Benchmark]:
    return parse(tomllib.loads(path.read_text()).get("benchmark", {}))


def differences(run: Benchmark, domains: Sequence[str], official: Benchmark) -> list[str]:
    """How the run of ``domains`` under ``run`` differs from ``official``."""
    out = [f"{rule} is {getattr(run, rule)}, and {getattr(official, rule)} in {official.name}"
           for rule in RULES if getattr(run, rule) != getattr(official, rule)]
    for domain in domains:
        if domain not in official.domains:
            out.append(f"{domain} is not a domain of {official.name}")
            continue
        mine, theirs = run.domains[domain], official.domains[domain]
        for key in sorted(set(mine) | set(theirs)):
            if mine.get(key) != theirs.get(key):
                out.append(f"{domain}.{key} is {mine.get(key)}, and {theirs.get(key)} "
                           f"in {official.name}")
    return out


def matching(run: Benchmark, domains: Sequence[str],
             officials: dict[str, Benchmark]) -> str | None:
    """The official benchmark that the run matches, or ``None``. Its own name is tried first."""
    names = sorted(officials, key=lambda name: name != run.name)
    return next((name for name in names
                 if not differences(run, domains, officials[name])), None)
