"""Three sensitivity studies of one or more models on one problem.

- Representation sensitivity: the same states in other text.
- Order sensitivity: the same options in other orders.
- Repeatability: the same condition again. The APIs take no seed, so two runs of the same
  requests can differ.

The ``[sensitivity]`` table of ``beelinebench.toml`` names the choosers (an array), the
domain, the trials, the representations, the option orders and the repeats. Each
representation runs with the random option order of the benchmark. Each option order and
each repeat runs with the first representation, which is that of the benchmark.
``python -m beelinebench case-study`` runs the conditions, and ``readme`` draws a figure and
writes a page for each study.

The results go to ``results/case-study/<chooser>/<domain>/<condition>.jsonl``, apart from
the benchmark results. Each chooser has its own ledger, ``.spend/<chooser>.case-study.json``,
so that a study can run while the chooser runs the benchmark.
"""

from __future__ import annotations

from collections.abc import Callable, Collection
from dataclasses import dataclass, replace
from pathlib import Path

from .rng import Draws
from .run import Record, geometric_mean, interval, read
from .search import Problem

LABEL = "case-study"

#: Each study: its name in file names, and its title.
STUDIES = {"representation-sensitivity": "Representation sensitivity",
           "order-sensitivity": "Order sensitivity",
           "repeatability": "Repeatability"}


@dataclass(frozen=True)
class CaseStudyConfig:
    choosers: tuple[str, ...]
    domain: str
    trials: int
    representations: tuple[str, ...]
    orders: tuple[str, ...]
    #: The runs of the benchmark condition in all: the benchmark run, the run of the first
    #: representation, and ``repeats - 2`` more.
    repeats: int = 3


#: Each option order, for a reader.
ORDER_TITLES = {
    "random": "random (the benchmark)",
    "random-2": "random, second seed",
    "random-3": "random, third seed",
    "found": "in the order found (oldest first)",
    "newest-first": "newest first",
    "best-first": "best heuristic value first",
    "worst-first": "worst heuristic value first",
}


class Arrange:
    """Puts the options of a question in one order. A chooser calls ``shuffle``.

    ``labels`` maps the text of an option to its state, so an order can use the heuristic.
    The chooser gets its options in frontier order: the oldest state first.
    """

    def __init__(self, name: str, draws: Draws, heuristic: Callable, labels: dict) -> None:
        self.name, self.draws, self.heuristic, self.labels = name, draws, heuristic, labels

    def shuffle(self, items: list) -> None:
        if self.name.startswith("random"):
            self.draws.shuffle(items)
        elif self.name == "newest-first":
            items.reverse()
        elif self.name in ("best-first", "worst-first"):
            # A stable sort keeps the frontier order between equal values.
            items.sort(key=lambda label: self.heuristic(self.labels[label]),
                       reverse=self.name == "worst-first")
        elif self.name != "found":
            raise ValueError(f"no option order {self.name!r}. There are: {', '.join(ORDER_TITLES)}")


def conditions(study: CaseStudyConfig) -> list[tuple[str, str, str]]:
    """Each condition: its name, its representation, and its option order.

    A repeat has the same representation and order as the benchmark, and the same seed.
    """
    first = study.representations[0]
    out = [(f"representation-{r}", r, "random") for r in study.representations]
    out += [(f"order-{o}", first, o) for o in study.orders if o != "random"]
    out += [(f"repeat-{k}", first, "random") for k in range(3, study.repeats + 1)]
    return out


def prepared(problem: Problem, representation: str, order: str, model: str,
             represent: Callable[[Problem, str], Problem]) -> tuple[Problem, Arrange]:
    """``problem`` in ``representation``, and the arrangement of its options."""
    shown = represent(problem, representation)
    labels: dict = {}
    render = shown.render

    def remember(state) -> str:
        text = render(state)
        labels[text] = state
        return text

    shown = replace(shown, render=remember)
    seed = ("order", model) if order == "random" else ("order", model, order)
    return shown, Arrange(order, Draws(problem.domain, problem.trial, *seed), problem.heuristic,
                          labels)


def results_dir(results: Path, chooser: str, study: CaseStudyConfig) -> Path:
    return results / LABEL / chooser / study.domain


@dataclass(frozen=True)
class Line:
    """One row of a study figure: a condition or a reference arm."""
    label: str
    scores: list[float]
    reference: bool = False
    marker: str = "D"


def lines(study: CaseStudyConfig, kind: str, chooser: str, results: Path, benchmark: str,
          heuristic: str) -> list[Line]:
    """The rows of study ``kind`` for one chooser, best first, then the reference arms.

    The reference arms do not depend on the model, so any record of a trial gives them.
    """
    folder = results_dir(results, chooser, study)

    def runs(name: str) -> list[Record]:
        return [r for r in read(folder / f"{name}.jsonl") if r.trial <= study.trials]

    bench = [r for r in read(results / benchmark / chooser / f"{study.domain}.{heuristic}.jsonl")
             if r.trial <= study.trials]
    first = study.representations[0]
    if kind == "representation-sensitivity":
        rows = [Line(r + (" (the benchmark)" if r == first else ""),
                     [x.score for x in runs(f"representation-{r}")])
                for r in study.representations]
    elif kind == "order-sensitivity":
        rows = [Line(ORDER_TITLES.get(o, o), [x.score for x in runs(
                    f"representation-{first}" if o == "random" else f"order-{o}")])
                for o in study.orders]
    else:
        rows = [Line("run 1 (the benchmark run)", [r.score for r in bench]),
                Line("run 2", [x.score for x in runs(f"representation-{first}")])]
        rows += [Line(f"run {k}", [x.score for x in runs(f"repeat-{k}")])
                 for k in range(3, study.repeats + 1)]
    references: dict = {}
    for name, _, _ in conditions(study):
        for r in [*bench, *runs(name)]:
            references.setdefault(r.trial, r)
    trials = sorted(references)
    refs = [Line("Heuristic", [references[t].baseline_score for t in trials], reference=True),
            Line("Random choice", [references[t].random_score for t in trials
                                   if references[t].random_score is not None],
                 reference=True, marker="o")]
    rows = [row for row in rows if row.scores]
    if kind != "repeatability":
        rows.sort(key=lambda row: -geometric_mean(row.scores))
    return rows + [ref for ref in refs if ref.scores] if rows else []


def summary(line: Line, seed: Collection) -> tuple[float, float, float]:
    """The geometric mean of a row, and its 95% bootstrap interval."""
    low, high = interval(line.scores, Draws("bootstrap", LABEL, *seed))
    return geometric_mean(line.scores), low, high
