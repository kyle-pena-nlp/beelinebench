"""A case study of one model on one problem: how the text and the order of the options
change its score.

The ``[case_study]`` table of ``beelinebench.toml`` names the chooser, the domain, the
trials, the representations and the option orders. Each representation runs with the
random option order of the benchmark, and each option order runs with the first
representation. ``python -m beelinebench case-study`` runs the conditions, and ``readme``
draws the figure and writes ``docs/case-study.md``.

The results go to ``results/case-study/<chooser>/<domain>/<condition>.jsonl``, apart from
the benchmark results. The chooser has its own ledger, ``.spend/<chooser>.case-study.json``,
so that the case study can run while the chooser runs the benchmark.
"""

from __future__ import annotations

from collections.abc import Callable, Collection
from dataclasses import dataclass
from pathlib import Path

from .rng import Draws
from .run import geometric_mean, interval, read
from .search import Problem

LABEL = "case-study"


@dataclass(frozen=True)
class CaseStudyConfig:
    chooser: str
    domain: str
    trials: int
    representations: tuple[str, ...]
    orders: tuple[str, ...]


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
    """Each condition: its name, its representation, and its option order."""
    first = study.representations[0]
    out = [(f"representation-{r}", r, "random") for r in study.representations]
    out += [(f"order-{o}", first, o) for o in study.orders if o != "random"]
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

    from dataclasses import replace
    shown = replace(shown, render=remember)
    seed = ("order", model) if order == "random" else ("order", model, order)
    return shown, Arrange(order, Draws(problem.domain, problem.trial, *seed), problem.heuristic,
                          labels)


def results_dir(results: Path, study: CaseStudyConfig) -> Path:
    return results / LABEL / study.chooser / study.domain


@dataclass(frozen=True)
class Line:
    """One row of the case study: a condition or a reference arm."""
    group: str
    label: str
    scores: list[float]
    reference: bool = False
    marker: str = "D"


def lines(study: CaseStudyConfig, results: Path, benchmark: str,
          heuristic: str) -> list[tuple[str, list[Line]]]:
    """The rows of the figure: one group for the representations and one for the orders.

    Each group ends with the reference arms on the same trials. The representation group
    also has the benchmark run of the chooser on the same trials, if there is one, so the
    difference between two runs of the same condition shows.
    """
    folder = results_dir(results, study)
    found = {name: [r for r in read(folder / f"{name}.jsonl") if r.trial <= study.trials]
             for name, _, _ in conditions(study)}
    bench = [r for r in read(results / benchmark / study.chooser / f"{study.domain}.{heuristic}.jsonl")
             if r.trial <= study.trials]
    # The reference arms do not depend on the model, so any record of a trial gives them.
    references: dict = {}
    for records in [bench, *found.values()]:
        for r in records:
            references.setdefault(r.trial, r)
    groups = []
    representation_rows = [
        Line("representation", f"{r}" + (" (the benchmark)" if r == study.representations[0]
                                          else ""),
             [x.score for x in found[f"representation-{r}"]])
        for r in study.representations]
    if bench:
        representation_rows.append(Line("representation", f"{study.representations[0]}, the "
                                        "benchmark run", [r.score for r in bench]))
    order_rows = [Line("order", ORDER_TITLES.get(o, o),
                       [x.score for x in found[f"order-{o}" if o != "random" else
                                               f"representation-{study.representations[0]}"]])
                  for o in study.orders]
    trials = sorted(references)
    refs = [Line("reference", "Heuristic", [references[t].baseline_score for t in trials],
                 reference=True),
            Line("reference", "Random choice", [references[t].random_score for t in trials
                                                if references[t].random_score is not None],
                 reference=True, marker="o")]
    for title, rows in (("Representation (random option order)", representation_rows),
                        (f"Option order ({study.representations[0]})", order_rows)):
        rows = [row for row in rows if row.scores]
        if rows:
            groups.append((title, sorted(rows, key=lambda row: -geometric_mean(row.scores))
                           + [ref for ref in refs if ref.scores]))
    return groups


def summary(line: Line, seed: Collection) -> tuple[float, float, float]:
    """The geometric mean of a row, and its 95% bootstrap interval."""
    low, high = interval(line.scores, Draws("bootstrap", LABEL, *seed))
    return geometric_mean(line.scores), low, high
