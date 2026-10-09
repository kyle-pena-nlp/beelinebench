"""Measure one instance, keep the records, and score a domain.

The rules come from a :class:`~beelinebench.benchmark.Benchmark`:

* The classic arm runs best-first search with :func:`~beelinebench.search.lowest` over
  the heuristic of the domain. The model arm runs the same search with the model
  as the chooser. Each arm stops at ``max_expansions``, solved or not.
* A breadth-first search finds the shortest path. The score of an arm is
  :func:`~beelinebench.search.efficiency`: the explorations of a perfect search
  (``shortest_path + 1``) divided by the explorations of the arm. 1.0 is perfect.
* An oracle arm runs the same search with the true distance to the goal as the
  chooser. Its score is the best that the frontier cap allows, and can be below 1.0.
* ``path_score`` is the shortest path divided by the path that the model arm found.
* An arm that stops unsolved counts at ``max_expansions``. When the model arm
  stops unsolved, the record is ``censored`` (marked ``*``), and the true score
  is lower. When the classic arm stops unsolved, ``baseline_solved`` is false
  (marked ``†``), and the true heuristic score is lower.
* The score of a domain is the geometric mean of the scores of its instances.
"""

from __future__ import annotations

import json
import math
from collections import deque
from collections.abc import Callable
from datetime import datetime, timezone
from dataclasses import asdict, dataclass
from pathlib import Path

from .benchmark import Benchmark
from .rng import Draws
from .search import (Chooser, Problem, Spend, best_first, distances_to_goal, efficiency,
                     lowest, oracle, random_choice)


@dataclass(frozen=True)
class Record:
    #: The official benchmark that the run matched, or ``custom-<name>``.
    benchmark: str
    chooser: str
    model: str
    domain: str
    heuristic: str
    trial: int
    baseline_expansions: int
    baseline_solved: bool
    model_expansions: int | None
    model_solved: bool | None
    #: The model arm stopped at ``max_expansions`` unsolved.
    censored: bool | None
    #: The fewest moves from the start to a solved state.
    shortest_path: int
    oracle_expansions: int
    #: The efficiency of each arm: ``(shortest_path + 1) / expansions``.
    score: float | None
    baseline_score: float
    oracle_score: float
    baseline_path_length: int | None
    model_path_length: int | None
    #: ``shortest_path / model_path_length``, when the model arm solved.
    path_score: float | None
    requests: int
    input_tokens: int
    output_tokens: int
    invalid_answers: int
    # The fields below came after the first records, so they have defaults, and an
    # older record still reads.
    #: When the model arm started and ended, in UTC.
    started_utc: str | None = None
    finished_utc: str | None = None
    #: The models that the API says answered. A hosted name can change its model.
    served_models: tuple[str, ...] = ()
    #: The time of each request of the model arm, from send to answer.
    latencies_ms: tuple[int, ...] = ()
    #: Answers that refused the question. ``requests`` includes the requests asked again.
    refusals: int = 0
    #: The random arm: the same search with a state chosen at random. It is the same for
    #: each model, because its draws come from the domain and the trial only.
    random_expansions: int | None = None
    random_score: float | None = None
    #: Tries of a request that failed with an intermittent error before the answer.
    retries: int = 0
    #: The choices of each arm against the oracle: for ``model``, ``heuristic`` and
    #: ``random``, a :meth:`Tally.result`. ``None`` before ``fill`` adds it.
    choices: dict | None = None


def troubles(record: Record) -> int:
    """The intermittent errors of a trial: refusals, invalid answers, and retries.

    A trial with none is clean. A re-run replaces a trial only if it has fewer.
    """
    return record.refusals + record.invalid_answers + record.retries


def takes_place(old: Record, new: Record, *, old_has_trace: bool, retrace: bool) -> bool:
    """Whether a re-run's result takes the place of the old result of the same trial.

    A re-run made for a trace replaces an old result with no trace. Otherwise the new
    result must have fewer intermittent errors. The score has no part in the choice.
    """
    if retrace and not old_has_trace:
        return True
    return troubles(new) < troubles(old)


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


#: Gets the arm ("classic" or "model"), the explorations, the cap of the arm and
#: the size of the frontier, after each exploration.
Observer = Callable[[str, int, int, int], None]


class Tally:
    """The choices of one arm against the oracle, step by step.

    A decision is a step where the search chose from two or more states, and at least
    one of them reaches the goal. The best states are those with the fewest moves to
    the goal. The oracle regret of a decision is the distance of the chosen state minus
    the best distance, so 0 is an optimal choice. A chosen state that cannot reach the
    goal is a dead end, and it has no regret.

    With ``from_start``, the distance of each state from the start, it also counts the
    choices on a shortest path. A state is on a shortest path when its distance from the
    start plus its distance to the goal is the length of a shortest path. A decision is
    contested when the frontier has a state on a shortest path and a state that is not.
    ``on_path`` counts the contested decisions that took a state on a shortest path.
    """

    def __init__(self, distance: dict, from_start: dict | None = None,
                 shortest: int | None = None) -> None:
        self.distance, self.from_start, self.shortest = distance, from_start, shortest
        self.decisions = self.optimal = self.regret = self.dead_ends = 0
        self.contested = self.on_path = 0

    def __call__(self, states: list, index: int, state, forced: bool) -> None:
        if forced:
            return
        reachable = [d for d in map(self.distance.get, states) if d is not None]
        if reachable:
            self.add(self.distance.get(state), min(reachable))
        if self.from_start is not None:
            on = [self.on_shortest_path(s) for s in states]
            if any(on) and not all(on):
                self.contested += 1
                self.on_path += on[index]

    def on_shortest_path(self, state) -> bool:
        to_goal, so_far = self.distance.get(state), self.from_start.get(state)
        return to_goal is not None and so_far is not None and so_far + to_goal == self.shortest

    def add(self, chosen: int | None, best: int) -> None:
        self.decisions += 1
        if chosen is None:
            self.dead_ends += 1
        else:
            self.regret += chosen - best
            self.optimal += chosen == best

    def result(self) -> dict:
        out = {"decisions": self.decisions, "optimal": self.optimal, "regret": self.regret,
               "dead_ends": self.dead_ends}
        if self.from_start is not None:
            out |= {"contested": self.contested, "on_path": self.on_path}
        return out


def from_start(problem: Problem) -> dict:
    """The fewest moves from the start to each state that it reaches, for :class:`Tally`."""
    seen = {problem.start: 0}
    queue = deque([problem.start])
    while queue:
        state = queue.popleft()
        for child in problem.moves(state):
            if child not in seen:
                seen[child] = seen[state] + 1
                queue.append(child)
    return seen


def tally_trace(steps: list[dict]) -> dict:
    """The :class:`Tally` result of the steps of a trace file."""
    tally = Tally({})
    for s in steps:
        if not s["forced"] and s["best_distance"] is not None:
            tally.add(s["chosen_distance"], s["best_distance"])
    return tally.result()


def both(*steps):
    """One step callback that calls each of ``steps``."""
    live = [s for s in steps if s is not None]
    return lambda *args: [s(*args) for s in live] and None


def baseline(problem: Problem, rules: Benchmark, observe: Observer | None = None,
             step=None):
    def report(expansions: int, frontier: int) -> None:
        if observe is not None:
            observe("classic", expansions, rules.max_expansions, frontier)

    return best_first(start=problem.start, moves=problem.moves, solved=problem.solved,
                      choose=lowest(problem.heuristic),
                      max_expansions=rules.max_expansions,
                      max_frontier=rules.max_frontier,
                      evict=Draws(problem.domain, problem.trial, "evict", "classic"),
                      observe=report, step=step)


def shortest(problem: Problem) -> dict:
    """The distance of each state to the goal. An error when the start reaches no goal."""
    distance = distances_to_goal(start=problem.start, moves=problem.moves, solved=problem.solved)
    if problem.start not in distance:
        raise ValueError(f"{problem.domain} trial {problem.trial} has no solution")
    return distance


def wander(problem: Problem, rules: Benchmark, step=None):
    """The random arm: the search with a state of the frontier chosen at random."""
    return best_first(start=problem.start, moves=problem.moves, solved=problem.solved,
                      choose=random_choice(Draws(problem.domain, problem.trial, "random")),
                      max_expansions=rules.max_expansions, max_frontier=rules.max_frontier,
                      evict=Draws(problem.domain, problem.trial, "evict", "random"), step=step)


def best(problem: Problem, rules: Benchmark, distance: dict):
    """The oracle arm: the search that the frontier cap allows with a perfect chooser."""
    return best_first(start=problem.start, moves=problem.moves, solved=problem.solved,
                      choose=oracle(distance), max_expansions=rules.max_expansions,
                      max_frontier=rules.max_frontier,
                      evict=Draws(problem.domain, problem.trial, "evict", "oracle"))


#: How many of the model's most probable states a trace step keeps.
TOP = 5


class Tracer:
    """The steps of the model arm of one trial, for a trace file.

    A step is one state taken off the frontier. It records the chosen state, its true
    distance to the goal, the best distance of the frontier, and the oracle distance
    regret: the chosen distance minus the best. With the model's probabilities it also
    records the rank of the best state, and the model's ``TOP`` most probable states.
    The cost fields are what the step's request (or requests) used.
    """

    def __init__(self, problem: Problem, distance: dict, spend: Spend) -> None:
        self.problem, self.distance, self.spend = problem, distance, spend
        self.steps: list[dict] = []
        self.mark = self.counters()

    def counters(self) -> tuple:
        s = self.spend
        return (s.requests, s.input_tokens, s.output_tokens, s.refusals, s.invalid_answers,
                len(s.latencies_ms), s.retries)

    def __call__(self, states: list, index: int, state, forced: bool) -> None:
        far = lambda s: self.distance.get(s)  # None: no way to the goal from s
        reachable = [d for d in map(far, states) if d is not None]
        best = min(reachable) if reachable else None
        chosen = far(state)
        now = self.counters()
        before, self.mark = self.mark, now
        step = {"step": len(self.steps) + 1, "frontier": len(states), "forced": forced,
                "chosen": self.problem.render(state), "chosen_distance": chosen,
                "best_distance": best,
                "regret": None if chosen is None or best is None else chosen - best,
                "requests": now[0] - before[0], "input_tokens": now[1] - before[1],
                "output_tokens": now[2] - before[2], "refusals": now[3] - before[3],
                "invalid_answers": now[4] - before[4], "retries": now[6] - before[6],
                "latencies_ms": self.spend.latencies_ms[before[5]:now[5]]}
        probabilities = None if forced else self.spend.probabilities
        if probabilities is not None and len(probabilities) == len(states):
            ranked = sorted(range(len(states)), key=lambda i: -probabilities[i])
            step["p_chosen"] = probabilities[index]
            step["best_rank"] = next((rank for rank, i in enumerate(ranked)
                                      if best is not None and far(states[i]) == best), None)
            step["top"] = [{"p": probabilities[i], "distance": far(states[i])}
                           for i in ranked[:TOP]]
        self.steps.append(step)

    def write(self, path: Path, header: dict) -> None:
        import gzip

        path.parent.mkdir(parents=True, exist_ok=True)
        with gzip.open(path, "wt", encoding="utf-8") as out:
            out.write(json.dumps(header) + "\n")
            for step in self.steps:
                out.write(json.dumps(step) + "\n")


def trace_file(traces: Path, label: str, chooser: str, problem: Problem) -> Path:
    """One file for each trial: traces/<benchmark>/<chooser>/<domain>.<heuristic>/<trial>.jsonl.gz."""
    return (traces / label / chooser / f"{problem.domain}.{problem.heuristic_name}"
            / f"{problem.trial}.jsonl.gz")


def measure(problem: Problem, *, rules: Benchmark, label: str, choose: Chooser,
            chooser: str, model: str, spend: Spend,
            observe: Observer | None = None, trace: Path | None = None) -> Record:
    """Run both arms on ``problem`` under ``rules``. ``spend`` is what ``choose`` adds to.

    ``label`` is the official benchmark that the run matches, or ``custom-<name>``.
    With ``trace``, the steps of the model arm go to that file (see :class:`Tracer`).
    ``chooser`` is the name in ``beelinebench.toml``. ``model`` is the model name, and
    it seeds the random draws of the model arm.
    """
    distance = shortest(problem)
    d = distance[problem.start]
    perfect = best(problem, rules, distance)
    start = from_start(problem)
    tallies = {arm: Tally(distance, start, d) for arm in ("model", "heuristic", "random")}
    aimless = wander(problem, rules, tallies["random"])
    classic = baseline(problem, rules, observe, tallies["heuristic"])
    before = Spend(**{k: v for k, v in vars(spend).items()
                      if k not in ("latencies_ms", "served")})
    first = len(spend.latencies_ms)
    started = now()
    cap = rules.max_expansions

    def step(expansions: int, frontier: int) -> None:
        if observe is not None:
            observe("model", expansions, cap, frontier)

    tracer = Tracer(problem, distance, spend) if trace is not None else None
    outcome = best_first(start=problem.start, moves=problem.moves, solved=problem.solved,
                         choose=choose, max_expansions=cap,
                         max_frontier=rules.max_frontier,
                         evict=Draws(problem.domain, problem.trial, "evict", "model", model),
                         observe=step, step=both(tracer, tallies["model"]))
    if tracer is not None:
        tracer.write(trace, {"benchmark": label, "chooser": chooser, "model": model,
                             "domain": problem.domain, "heuristic": problem.heuristic_name,
                             "trial": problem.trial, "start": problem.render(problem.start),
                             "objective": problem.objective, "shortest_path": d,
                             "solved": outcome.solved, "expansions": outcome.expansions,
                             "served_models": sorted(set(spend.served[first:]))})
    return Record(
        benchmark=label, chooser=chooser, model=model, domain=problem.domain,
        heuristic=problem.heuristic_name, trial=problem.trial,
        baseline_expansions=classic.expansions, baseline_solved=classic.solved,
        model_expansions=outcome.expansions, model_solved=outcome.solved,
        censored=not outcome.solved,
        shortest_path=d, oracle_expansions=perfect.expansions,
        score=efficiency(d, outcome.expansions),
        baseline_score=efficiency(d, classic.expansions),
        oracle_score=efficiency(d, perfect.expansions),
        random_expansions=aimless.expansions,
        random_score=efficiency(d, aimless.expansions),
        baseline_path_length=classic.path_length,
        model_path_length=outcome.path_length,
        path_score=d / outcome.path_length if outcome.solved else None,
        requests=spend.requests - before.requests,
        input_tokens=spend.input_tokens - before.input_tokens,
        output_tokens=spend.output_tokens - before.output_tokens,
        invalid_answers=spend.invalid_answers - before.invalid_answers,
        refusals=spend.refusals - before.refusals,
        retries=spend.retries - before.retries,
        started_utc=started, finished_utc=now(),
        served_models=tuple(sorted(set(spend.served[first:]))),
        latencies_ms=tuple(spend.latencies_ms[first:]),
        choices={arm: tally.result() for arm, tally in tallies.items()})


def results_file(results: Path, label: str, chooser: str, problem: Problem) -> Path:
    """One file for each benchmark, chooser, domain and heuristic."""
    return results / label / chooser / f"{problem.domain}.{problem.heuristic_name}.jsonl"


def read(path: Path) -> list[Record]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8") as lines:
        return [Record(**json.loads(line)) for line in lines if line.strip()]


def replace(path: Path, record: Record) -> None:
    """Put ``record`` in place of the record of the same trial in ``path``."""
    records = [record if r.trial == record.trial else r for r in read(path)]
    temporary = path.with_suffix(".jsonl.replacing")
    temporary.write_text("".join(json.dumps(asdict(r)) + "\n" for r in records))
    temporary.replace(path)


def append(path: Path, record: Record) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as out:
        out.write(json.dumps(asdict(record)) + "\n")


@dataclass(frozen=True)
class Summary:
    """The scores of one file. Each is a geometric mean over the trials.

    A trial that an arm did not solve counts at ``max_expansions`` for that arm.
    ``censored`` counts the trials where the model arm did not solve (``*``): the
    true score is lower. ``baseline_censored`` counts those where the classic arm
    did not solve (``†``): the true heuristic score is lower. ``solved_score`` and
    ``path_score`` are over the trials the model solved, and ``coverage`` is their
    share.
    """

    instances: int
    censored: int
    baseline_censored: int
    score: float | None
    #: The 95% bootstrap interval of the geometric mean.
    low: float | None
    high: float | None
    coverage: float | None
    solved_score: float | None
    baseline_score: float | None
    oracle_score: float | None
    path_score: float | None
    requests: int
    #: Answers that refused the question, out of ``requests``.
    refusals: int
    input_tokens: int
    output_tokens: int
    #: The median and the 95th percentile of the time of a request.
    latency_ms_median: float | None
    latency_ms_p95: float | None
    served_models: tuple[str, ...]
    #: The first and the last time a model arm ran, in UTC.
    first_utc: str | None
    last_utc: str | None

    @property
    def refusal_rate(self) -> str:
        """The share of requests that the model refused, for a table."""
        return f"{self.refusals / self.requests:.1%}" if self.requests else "—"

    @property
    def marks(self) -> str:
        """``*`` when a model run hit the limit."""
        return "*" if self.censored else ""

    @property
    def baseline_marks(self) -> str:
        """``†`` when a classic run hit the limit."""
        return "†" if self.baseline_censored else ""


def geometric_mean(values: list[float]) -> float | None:
    return math.exp(sum(math.log(v) for v in values) / len(values)) if values else None


def interval(values: list[float], draws: Draws) -> tuple[float, float]:
    """The 95% bootstrap interval of the geometric mean of ``values``."""
    logs = [math.log(v) for v in values]
    means = sorted(sum(draws.choice(logs) for _ in logs) / len(logs) for _ in range(2000))
    return math.exp(means[49]), math.exp(means[1949])


def summarise(records: list[Record], *, draws: Draws) -> Summary:
    scored = [r for r in records if r.score is not None]
    logs = [math.log(r.score) for r in scored]
    latencies = sorted(ms for r in records for ms in r.latencies_ms)
    times = sorted(t for r in records for t in (r.started_utc, r.finished_utc) if t)
    context = dict(
        requests=sum(r.requests for r in records),
        refusals=sum(r.refusals for r in records),
        input_tokens=sum(r.input_tokens for r in records),
        output_tokens=sum(r.output_tokens for r in records),
        latency_ms_median=latencies[len(latencies) // 2] if latencies else None,
        latency_ms_p95=latencies[min(len(latencies) - 1, int(0.95 * len(latencies)))]
        if latencies else None,
        served_models=tuple(sorted({m for r in records for m in r.served_models})),
        first_utc=times[0] if times else None, last_utc=times[-1] if times else None)
    if not logs:
        return Summary(0, 0, 0, None, None, None, None, None, None, None, None, **context)
    solved = [r.score for r in scored if not r.censored]
    low, high = interval([r.score for r in scored], draws)
    return Summary(
        instances=len(scored),
        censored=sum(1 for r in scored if r.censored),
        baseline_censored=sum(1 for r in scored if not r.baseline_solved),
        score=math.exp(sum(logs) / len(logs)),
        low=low, high=high,
        coverage=len(solved) / len(scored),
        solved_score=geometric_mean(solved),
        baseline_score=geometric_mean([r.baseline_score for r in scored]),
        oracle_score=geometric_mean([r.oracle_score for r in scored]),
        path_score=geometric_mean([r.path_score for r in scored if r.path_score is not None]),
        **context)
