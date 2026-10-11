"""Run BeelineBench on a model that is a Python function: no server, no key, no config.

A lab can test a model that has no public API with one call::

    from beelinebench.api import Question, evaluate

    def decide(question: Question) -> list[float]:
        # One probability for each of question.options, in that order.
        return my_model.score(question.text(), question.options)

    summary = evaluate(decide, name="my-model-2026-10", trials=20)

The model gets the same task, goal, context, instructions and options as a model behind
an API, and the options come in the same seeded random order. The search takes the option
with the highest probability. The results and traces go to the same files as those of
``python -m beelinebench run``, so ``report``, ``readme`` and ``fill`` read them.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path

from .jev import INSTRUCTIONS, MAX_OPTIONS, TASK
from .rng import Draws
from .search import Chooser, Problem, Spend


@dataclass(frozen=True)
class Question:
    """One choice: the state of the search, and the options in the order shown."""

    task: str
    goal: str
    context: str
    instructions: str
    options: tuple[str, ...]

    def text(self) -> str:
        """The question as one text, as OpenAI's Decisions API gets it."""
        return (f"Task: {self.task}\nGoal: {self.goal}\nContext: {self.context}\n"
                f"Instructions: {self.instructions}")


#: Takes a question, and gives one probability (or any score) for each option.
Decide = Callable[[Question], Sequence[float]]


def chooser(decide: Decide, problem: Problem, spend: Spend, order: Draws) -> Chooser:
    """A chooser that asks ``decide`` one question over the whole frontier."""

    def choose(states: Sequence) -> int:
        labels = [problem.render(state) for state in states]
        if len(labels) > MAX_OPTIONS:
            raise ValueError(f"{len(labels)} states, and a question holds {MAX_OPTIONS}")
        shown = list(labels)
        order.shuffle(shown)
        scores = list(decide(Question(TASK, problem.objective, problem.context, INSTRUCTIONS,
                                      tuple(shown))))
        if len(scores) != len(shown) or not all(math.isfinite(s) for s in scores):
            raise ValueError(f"decide gave {len(scores)} scores for {len(shown)} options, "
                             "or a score that is not a number")
        spend.add(input_tokens=0, output_tokens=0, seconds=0.0, served="python")
        by_label = dict(zip(shown, scores))
        spend.probabilities = [float(by_label[label]) for label in labels]
        return max(range(len(labels)), key=lambda i: spend.probabilities[i])

    return choose


def evaluate(decide: Decide, *, name: str, benchmark: str | None = None,
             trials: int | None = None, domains: Sequence[str] | None = None,
             project: Path | None = None) -> list[dict]:
    """Run each domain of an official benchmark with ``decide``, and give the summaries.

    ``name`` names the model in the results: results/<benchmark>/<name>/. Use a new name
    for each version of the model. ``benchmark`` is an official version, the newest by
    default. ``trials`` runs trials 1 to N, for example 20 for a run the size of the mini
    benchmark. A trial with a result is not run again, so a stopped run continues.
    """
    from . import __main__ as cli
    from . import benchmark as benchmarks
    from .run import append, measure, read, results_file, summarise, trace_file

    root = project or cli.PROJECT
    officials = benchmarks.load(cli.OFFICIAL)
    rules = officials[benchmark or list(officials)[-1]]
    chosen = list(domains or rules.domains)
    label = cli.label_of(rules, chosen, officials)
    count = trials or rules.trials
    out = []
    for domain in chosen:
        make = cli.maker(domain, rules.domains[domain])
        path = results_file(root / "results", label, name, make(1))
        done = {r.trial for r in read(path)}
        for trial in range(1, count + 1):
            if trial in done:
                continue
            problem = make(trial)
            spend = Spend(max_requests=10 ** 9, max_input_tokens=10 ** 12)
            choose = chooser(decide, problem, spend, Draws(domain, trial, "order", name))
            record = measure(problem, rules=rules, label=label, choose=choose, chooser=name,
                             model=name, spend=spend,
                             trace=trace_file(root / "traces", label, name, problem))
            append(path, record)
        records = read(path)
        summary = summarise(records, draws=Draws("bootstrap", label, name, path.stem))
        out.append({"benchmark": label, "chooser": name, "domain": domain,
                    "heuristic": rules.domains[domain]["heuristic"], "trials": len(records),
                    **asdict(summary)})
    return out
