"""The command line.

    python -m beelinebench run                    # everything that beelinebench.toml says
    python -m beelinebench run --chooser haiku --domain tiles --trials 3
    python -m beelinebench baseline               # the classic arm alone. Sends nothing.
    python -m beelinebench benchmarks             # the official benchmarks, and those of beelinebench.toml
    python -m beelinebench choosers
    python -m beelinebench probe --chooser luna   # one question of 255 options. Spends a little.
    python -m beelinebench report
    python -m beelinebench fill               # add missing reference arms to old results. Sends nothing.
    python -m beelinebench plot                   # docs/benchmarks/<version>.png, the scores as a figure
    python -m beelinebench download
    python -m beelinebench publish 1.0.0          # the page of a benchmark, and its link
    python -m beelinebench check-docs             # CI: every official benchmark has both
    python -m beelinebench readme                 # README.md from README.template.md
    python -m beelinebench readme --check         # CI: README.md is up to date

``benchmarks.toml`` holds the official benchmarks. ``beelinebench.toml`` says what to
run. Trial ``n`` of a domain is drawn from ``Draws(domain, n)``, so it is the same
on every machine and for every model. ``run`` spends money. It writes each trial
to ``results/<benchmark>/<chooser>/<domain>.<heuristic>.jsonl`` when the trial
ends, and a second run skips the trials already there. When a chooser is done,
``run`` says whether the run matches an official benchmark, and how much of it
the results now hold.
"""

from __future__ import annotations

import argparse
import difflib
import tomllib
import functools
import io
import tarfile
from collections.abc import Callable
from pathlib import Path
from typing import Any

from rich.console import Console
from rich.progress import (BarColumn, MofNCompleteColumn, Progress, TaskID, TextColumn,
                           TimeElapsedColumn)
from rich.table import Table

from . import benchmark, config, paths, publishing, readme
from .benchmark import Benchmark
from .domains import blocksworld, countdown, keys_doors, rush_hour, tiles, wikispeedia, word_ladder
from .rng import Draws
from .run import (Record, Tally, append, baseline, best, from_start, geometric_mean, measure,
                  read, replay, replace, results_file, shortest, summarise, takes_place,
                  trace_file, troubles, wander)
from .search import (BudgetExhausted, ChooserError, Problem, Spend, Wallet, best_first,
                     efficiency)

#: The working folder. See :mod:`beelinebench.paths`.
PROJECT = paths.home()
RESULTS = PROJECT / "results"
#: The steps of each trial of a model arm: traces/<benchmark>/<chooser>/<file>/<trial>.jsonl.gz.
#: Git ignores them.
TRACES = PROJECT / "traces"
#: The total cost of each model over all runs: .spend/<chooser>.json.
SPEND = PROJECT / ".spend"
OFFICIAL = paths.official(PROJECT)
DOCS = PROJECT / "docs" / "benchmarks"

console = Console()


def maker(domain: str, settings: dict[str, Any]) -> Callable[[int], Problem]:
    """The function that makes trial ``n`` of ``domain`` with ``settings``."""
    ensure_data(domain)
    if domain == "wikispeedia":
        graph = wikispeedia.load(PROJECT / wikispeedia.DATA)
        return lambda trial: wikispeedia.problem(trial, graph, **settings)
    if domain == "word_ladder":
        ladder = word_ladder.load(PROJECT / word_ladder.DATA)
        return lambda trial: word_ladder.problem(trial, ladder, **settings)
    problem = {"tiles": tiles.problem, "blocksworld": blocksworld.problem,
               "countdown": countdown.problem, "rush_hour": rush_hour.problem,
               "keys_doors": keys_doors.problem}[domain]
    # A trial can take seconds to make (Rush Hour rejects easy boards), so keep each one.
    return functools.cache(lambda trial: problem(trial, **settings))


def progress() -> Progress:
    return Progress(TextColumn("{task.description}"), BarColumn(), MofNCompleteColumn(),
                    TimeElapsedColumn(), TextColumn("[dim]{task.fields[status]}"),
                    console=console)


def watcher(bars: Progress, task: TaskID, trial: int, spend: Spend | None):
    """An observer that shows the current arm of a trial on ``task``."""

    def observe(arm: str, expansions: int, cap: int, frontier: int) -> None:
        status = f"frontier {frontier:,}"
        if spend is not None:
            status += f" · {spend.requests:,} requests · {spend.input_tokens:,} tokens"
        bars.update(task, description=f"  trial {trial} · {arm}", total=cap,
                    completed=expansions, status=status)

    return observe


def setup(args: argparse.Namespace):
    """The official benchmarks, the config, the benchmark to run, and its domains."""
    officials = benchmark.load(OFFICIAL)
    cfg = config.load(args.config, officials)
    every = {**officials, **cfg.benchmarks}
    name = args.benchmark or cfg.run.benchmark
    if name not in every:
        raise SystemExit(f"no benchmark {name!r}. There are: {', '.join(every)}")
    chosen = every[name]
    domains = args.domain or list(cfg.run.domains or chosen.domains)
    unknown = [d for d in domains if d not in chosen.domains]
    if unknown:
        raise SystemExit(f"{name} has no domain {', '.join(unknown)}. "
                         f"It has: {', '.join(chosen.domains)}")
    return officials, cfg, chosen, domains


def label_of(chosen: Benchmark, domains: list[str], officials: dict[str, Benchmark]) -> str:
    return benchmark.matching(chosen, domains, officials) or f"custom-{chosen.name}"


def show_baseline(args: argparse.Namespace) -> None:
    officials, cfg, chosen, domains = setup(args)
    trials = args.trials or cfg.run.trials or chosen.trials
    table = Table("domain", "heuristic", "trials", "solved", "shortest path: median",
                  "explorations: median", "max", "heuristic score", "oracle score",
                  title=f"classic and oracle arms · {chosen.name}",
                  caption="A score is (shortest path + 1) / explorations. 1.0 is perfect.")
    with progress() as bars:
        for domain in domains:
            make = maker(domain, chosen.domains[domain])
            heuristic = chosen.domains[domain]["heuristic"]
            bench = bars.add_task(f"classic · {domain}/{heuristic}", total=trials, status="")
            current = bars.add_task("", total=None, status="")
            outcomes, shortests, oracles = [], [], []
            for trial in range(1, trials + 1):
                problem = make(trial)
                distance = shortest(problem)
                shortests.append(distance[problem.start])
                oracles.append(best(problem, chosen, distance))
                outcomes.append(baseline(problem, chosen, watcher(bars, current, trial, None)))
                bars.advance(bench)
            bars.remove_task(current)
            solved = [o for o in outcomes if o.solved]
            expansions = sorted(o.expansions for o in outcomes)
            table.add_row(domain, heuristic, str(len(outcomes)), str(len(solved)),
                          str(sorted(shortests)[len(shortests) // 2]),
                          str(expansions[len(expansions) // 2]), str(expansions[-1]),
                          f"{geometric_mean([efficiency(d, o.expansions) for d, o in zip(shortests, outcomes)]):.3f}",
                          f"{geometric_mean([efficiency(d, o.expansions) for d, o in zip(shortests, oracles)]):.3f}")
    console.print(table)


def run(args: argparse.Namespace) -> None:
    officials, cfg, chosen, domains = setup(args)
    mini = cfg.mini if getattr(args, "mini", False) else None
    if getattr(args, "mini", False) and mini is None:
        raise SystemExit(f"--mini needs a [mini] table in {args.config}")
    names = ([args.chooser] if args.chooser else list(mini.choosers) if mini
             else list(cfg.run.choosers))
    for name in names:
        if name not in cfg.choosers:
            raise SystemExit(f"no chooser {name!r} in {args.config}. "
                             f"It has: {', '.join(cfg.choosers)}")
    label = label_of(chosen, domains, officials)
    for name in names:
        chooser = cfg.choosers[name]
        trials = args.trials or (mini.trials if mini else chooser.trials or cfg.run.trials
                                 or chosen.trials)
        finished = run_chooser(chooser, chosen, label, domains, trials,
                               max_requests=args.max_requests or chooser.max_requests,
                               max_input_tokens=args.max_input_tokens or chooser.max_input_tokens,
                               max_cost=chooser.max_cost or cfg.run.max_cost,
                               max_total=cfg.run.max_total_cost,
                               retrace=args.retrace, rerun_unclean=args.rerun_unclean)
        show_match(chooser.name, chosen, label, domains, officials, finished)


def run_chooser(chooser: config.ChooserConfig, chosen: Benchmark, label: str,
                domains: list[str], trials: int, *, max_requests: int,
                max_input_tokens: int, max_cost: float | None = None,
                max_total: float | None = None,
                retrace: bool = False, rerun_unclean: bool = False) -> bool:
    """Run one chooser over ``domains``. False when it stopped at a limit.

    Each trial writes a trace. With ``retrace``, a trial that has a result and no
    trace runs again, and its new result takes the place of the old one, so that the
    result and the trace are of the same run.

    With ``rerun_unclean``, a trial with intermittent errors (refusals, invalid answers
    or retries) runs again. The new result and trace take the place of the old ones only
    if the new run has fewer errors. The score has no part in the choice.

    With ``max_cost`` and a price, the run stops before the request that would start
    when the model's cost over all runs is ``max_cost`` or more.
    """
    make_chooser = config.factory(chooser, PROJECT / ".env")
    spend = Spend(max_requests=max_requests, max_input_tokens=max_input_tokens,
                  wallet=wallet_of(chooser, max_cost, max_total))
    if spend.wallet is not None:
        console.print(f"{chooser.name} has cost ${spend.wallet.cost:.2f} in all. "
                      f"The limit is ${spend.wallet.max_cost:.2f}.")
        if max_total is not None:
            console.print(f"All models have cost ${spend.wallet.total():.2f}. "
                          f"The limit is ${max_total:.2f}.")
    with progress() as bars:
        for domain in domains:
            make = maker(domain, chosen.domains[domain])
            path = results_file(RESULTS, label, chooser.name, make(1))
            old = {record.trial: record for record in read(path)}
            recorded = set(old)
            traced = {t for t in recorded
                      if trace_file(TRACES, label, chooser.name, make(t)).exists()}
            done = set(recorded)
            if retrace:
                done &= traced
            if rerun_unclean:
                done -= {t for t, r in old.items() if troubles(r) > 0}
            bench = bars.add_task(f"{chooser.name} · {domain}/{make(1).heuristic_name}",
                                  total=trials,
                                  completed=len(done & set(range(1, trials + 1))), status="")
            current = bars.add_task("", total=None, status="")
            for trial in range(1, trials + 1):
                if trial in done:
                    continue
                problem = make(trial)
                choose = make_chooser(problem, spend,
                                      Draws(domain, trial, "order", chooser.model))
                try:
                    trace = trace_file(TRACES, label, chooser.name, problem)
                    # A re-run writes a candidate trace, which takes the old one's place only
                    # if the new result does.
                    target = (trace.with_name(trace.name + ".candidate")
                              if trial in recorded else trace)
                    record = measure(problem, rules=chosen, label=label, choose=choose,
                                     chooser=chooser.name, model=chooser.model, spend=spend,
                                     observe=watcher(bars, current, trial, spend),
                                     trace=target)
                except BudgetExhausted:
                    console.print(f"[red]{chooser.name} stopped at {spend.requests:,} requests "
                                  f"and {spend.input_tokens:,} input tokens. "
                                  f"{domain} trial {trial} is not recorded.")
                    return False
                except ChooserError as error:
                    console.print(f"[red]{chooser.name} stopped: {error}. "
                                  f"{domain} trial {trial} is not recorded.")
                    return False
                if trial not in recorded:
                    append(path, record)
                elif takes_place(old[trial], record, old_has_trace=trial in traced,
                                 retrace=retrace):
                    replace(path, record)
                    target.replace(trace)
                    console.print(f"{domain} trial {trial}: the new run takes the place of the "
                                  f"old one ({troubles(old[trial])} intermittent errors, now "
                                  f"{troubles(record)})")
                else:
                    target.unlink(missing_ok=True)
                    console.print(f"{domain} trial {trial}: kept the old run "
                                  f"({troubles(old[trial])} intermittent errors, the new run "
                                  f"{troubles(record)})")
                bars.advance(bench)
                console.print(line_of(record))
            bars.remove_task(current)
    console.print(f"{chooser.name} spent {spend.requests:,} requests, "
                  f"{spend.input_tokens:,} input tokens, {spend.output_tokens:,} output tokens")
    return True


def wallet_of(chooser: config.ChooserConfig, max_cost: float | None,
              max_total: float | None = None) -> Wallet | None:
    """The cost of ``chooser`` over all runs, with its limit. ``None`` without a price or limit.

    A model without a file in .spend/ starts at the tokens of its recorded trials.
    """
    if max_cost is None or chooser.price_input is None:
        return None
    records = [r for path in RESULTS.glob(f"*/{chooser.name}/*.jsonl") for r in read(path)]
    start = (sum(r.input_tokens for r in records), sum(r.output_tokens for r in records),
             sum(r.requests for r in records))
    wallet = Wallet.open(SPEND / f"{chooser.name}.json", price_input=chooser.price_input,
                         price_output=chooser.price_output or 0.0, max_cost=max_cost,
                         start=start, max_total=max_total)
    # The limit of all models comes from the config at each request, so a new limit there
    # takes effect in the runs that go now.
    config_file = PROJECT / "beelinebench.toml"
    wallet.read_limit = lambda: tomllib.loads(config_file.read_text()).get("run", {}).get(
        "max_total_cost")
    return wallet


def show_match(chooser: str, chosen: Benchmark, label: str, domains: list[str],
               officials: dict[str, Benchmark], finished: bool) -> None:
    """Say whether the run matches an official benchmark, and how much of it is done."""
    if label in officials:
        official = officials[label]
        done = 0
        for domain in official.domains:
            path = (RESULTS / label / chooser
                    / f"{domain}.{official.domains[domain]['heuristic']}.jsonl")
            done += len({r.trial for r in read(path)} & set(range(1, official.trials + 1)))
        total = official.trials * len(official.domains)
        state = "complete" if done == total else "partial"
        console.print(f"[bold]{chooser}: matches official benchmark {label}[/] · {state}: "
                      f"{done} of {total} trials in results/{label}/{chooser}")
    else:
        console.print(f"[bold yellow]{chooser}: matches no official benchmark.[/] "
                      f"Results are in results/{label}/{chooser}")
        nearest = officials.get(chosen.name) or next(iter(officials.values()), None)
        if nearest is not None:
            for difference in benchmark.differences(chosen, domains, nearest):
                console.print(f"  {difference}")
    if not finished:
        console.print("[red]  the run stopped at a limit before it was done")


def line_of(record: Record) -> str:
    colour = "green" if record.score >= record.baseline_score else "red"
    classic = f"{record.baseline_expansions}{'' if record.baseline_solved else '†'}"
    model = f"{record.model_expansions}{'*' if record.censored else ''}"
    return (f"{record.domain} trial {record.trial}: [{colour}]score {record.score:.3f}[/]"
            f" · heuristic {record.baseline_score:.3f} · shortest path {record.shortest_path}"
            f" · explorations: classic {classic}, model {model} · {record.requests} requests")


def show_benchmarks(args: argparse.Namespace) -> None:
    officials = benchmark.load(OFFICIAL)
    cfg = config.load(args.config, officials)
    table = Table("benchmark", "kind", "trials", "max explored", "frontier", "domain",
                  "settings")
    for kind, group in (("official", officials), ("experiment", cfg.benchmarks)):
        for b in group.values():
            for n, (domain, settings) in enumerate(b.domains.items()):
                table.add_row(*(b.name, kind, str(b.trials), f"{b.max_expansions:,}",
                                str(b.max_frontier)) if n == 0 else ("",) * 5,
                              domain, ", ".join(f"{k}={v}" for k, v in settings.items()))
    console.print(table)


def probe(args: argparse.Namespace) -> None:
    """Send one question with the most options to a chooser, and show the answer."""
    from types import SimpleNamespace

    from .jev import MAX_OPTIONS

    officials = benchmark.load(OFFICIAL)
    cfg = config.load(args.config, officials)
    if args.chooser not in cfg.choosers:
        raise SystemExit(f"no chooser {args.chooser!r} in {args.config}. "
                         f"It has: {', '.join(cfg.choosers)}")
    chooser = cfg.choosers[args.chooser]
    problem = SimpleNamespace(objective="reach the state with the highest number",
                              context="Each state is a number.", render=lambda n: f"state {n}")
    spend = Spend(max_requests=2, max_input_tokens=10**7,
                  wallet=wallet_of(chooser, chooser.max_cost or cfg.run.max_cost))
    choose = config.factory(chooser, PROJECT / ".env")(problem, spend, Draws("probe"))
    try:
        pick = choose(list(range(1, MAX_OPTIONS + 1)))
    except ChooserError as error:
        raise SystemExit(f"{chooser.name}: {error}")
    console.print(f"{chooser.name}: the API accepted {MAX_OPTIONS} options. "
                  f"Model {', '.join(spend.served)} chose state {pick + 1}. "
                  f"{spend.input_tokens:,} input tokens, {spend.latencies_ms[-1]:,} ms, "
                  f"{spend.refusals} refusals.")


def choosers(args: argparse.Namespace) -> None:
    cfg = config.load(args.config, benchmark.load(OFFICIAL))
    table = Table("chooser", "protocol", "model", "api_base", "key from", "trials",
                  "max requests", "max input tokens", title=str(args.config))
    for c in cfg.choosers.values():
        table.add_row(c.name, c.protocol, c.model, c.api_base or "default",
                      c.api_key_env or "no key", str(c.trials or "run's"),
                      f"{c.max_requests:,}", f"{c.max_input_tokens:,}")
    console.print(table)


def report(args: argparse.Namespace) -> None:
    officials = benchmark.load(OFFICIAL)
    table = Table("benchmark", "chooser", "domain", "heuristic", "trials", "score",
                  "95% interval", "heuristic score", "oracle score", "path score", "solved",
                  "score when solved", "requests", "refusals", "input tokens",
                  "output tokens", "latency ms: median / p95", "served by", "run (UTC)",
                  caption="A score is (shortest path + 1) / explorations, and 1.0 is perfect. "
                  "The oracle score is the best that the frontier cap allows. The path score "
                  "is the shortest path / the model's path, over solved trials. Refusals "
                  "are the requests that the model refused, then asked again. "
                  "* a model run did not solve within the limit, so the true score is lower. "
                  "† a heuristic run did not, so the true heuristic score is lower.")
    rows = []
    for path in sorted(RESULTS.glob("*/*/*.jsonl")):
        label, chooser = path.parent.parent.name, path.parent.name
        domain, heuristic = path.stem.split(".")
        records = read(path)
        s = summarise(records, draws=Draws("bootstrap", label, chooser, path.stem))
        if args.json:
            import dataclasses
            rows.append({"benchmark": label, "chooser": chooser, "domain": domain,
                         "heuristic": heuristic, "trials": len(records),
                         "official_trials": officials[label].trials if label in officials
                         else None, **dataclasses.asdict(s)})
            continue
        of = f" of {officials[label].trials}" if label in officials else ""
        table.add_row(
            label, chooser, domain, heuristic, f"{len(records)}{of}",
            "—" if s.score is None else f"{s.score:.3f}{s.marks}",
            "—" if s.low is None else f"{s.low:.3f} to {s.high:.3f}",
            "—" if s.baseline_score is None else f"{s.baseline_score:.3f}{s.baseline_marks}",
            "—" if s.oracle_score is None else f"{s.oracle_score:.3f}",
            "—" if s.path_score is None else f"{s.path_score:.2f}",
            "—" if s.coverage is None
            else f"{s.instances - s.censored} of {s.instances} ({s.coverage:.0%})",
            "—" if s.solved_score is None else f"{s.solved_score:.3f}",
            f"{s.requests:,}", f"{s.refusals:,} ({s.refusal_rate})", f"{s.input_tokens:,}",
            f"{s.output_tokens:,}",
            "—" if s.latency_ms_median is None
            else f"{s.latency_ms_median:,.0f} / {s.latency_ms_p95:,.0f}",
            ", ".join(s.served_models) or "—",
            "—" if s.first_utc is None else f"{s.first_utc[:10]} to {s.last_utc[:10]}")
    if args.json:
        import json
        print(json.dumps(rows, indent=2))
        return
    console.print(table)


def make_plot(args: argparse.Namespace) -> None:
    officials = benchmark.load(OFFICIAL)
    name = args.benchmark or list(officials)[-1]
    if name not in officials:
        raise SystemExit(f"no official benchmark {name!r}. There are: {', '.join(officials)}")
    try:
        from . import plot
        target = args.out or DOCS / f"{name}.png"
        choosers = config.load(args.config, officials).choosers
        labels = {c.name: c.title for c in choosers.values()}
        plot.draw(officials[name], RESULTS, target, labels, config.unpublished(choosers))
        frontier_png = target.with_name(target.stem + "-frontier.png")
        plot.draw_frontier(officials[name], RESULTS, frontier_png, labels,
                           config.unpublished(choosers), price_list(choosers))
        console.print(f"wrote {frontier_png}")
        # The oracle regret is not in the README or the pages. Only this command draws it.
        regret_png = target.with_name(target.stem + "-regret.png")
        plot.draw_regret(officials[name], RESULTS, regret_png, labels,
                         config.unpublished(choosers))
        console.print(f"wrote {regret_png}")
    except ImportError:
        raise SystemExit("plot needs matplotlib. Run `uv sync --extra plot`.")
    except ValueError as error:
        raise SystemExit(str(error))
    console.print(f"wrote {target}")


def fill(args: argparse.Namespace) -> None:
    """Add the random arm, and the choices of each arm, to records without them.

    It sends no requests. The heuristic and random arms run again here. The model arm runs
    again from the trace file of the trial, so a trial without a trace gets no ``model``
    choices. Do not fill the files of a chooser while it runs: the
    run appends to them.
    """
    import dataclasses
    import gzip
    import json

    officials = benchmark.load(OFFICIAL)
    cfg = config.load(args.config, officials)
    every = {**officials, **{f"custom-{name}": b for name, b in cfg.benchmarks.items()}}
    makers: dict = {}
    references: dict = {}  # (label, domain, trial): the choices of the heuristic and random arms

    def prepared(label, domain, make, trial):
        """The problem, its distances to the goal and from the start, and the shortest path."""
        problem = make(trial)
        distance = shortest(problem)
        return problem, distance, from_start(problem), distance[problem.start]

    def reference_choices(label, domain, rules, make, trial) -> dict:
        key = (label, domain, trial)
        if key not in references:
            problem, distance, start, d = prepared(label, domain, make, trial)
            tallies = {"heuristic": Tally(distance, start, d), "random": Tally(distance, start, d)}
            baseline(problem, rules, step=tallies["heuristic"])
            wander(problem, rules, tallies["random"])
            references[key] = {arm: t.result() for arm, t in tallies.items()}
        return references[key]

    for path in sorted(RESULTS.glob("*/*/*.jsonl")):
        label, chooser = path.parent.parent.name, path.parent.name
        if args.chooser and chooser not in args.chooser:
            continue
        if label not in every:
            console.print(f"[yellow]skipped {path.relative_to(PROJECT)}: no benchmark {label}")
            continue
        domain = path.stem.split(".")[0]
        records = read(path)
        traces = TRACES / label / chooser / path.stem

        def lacks_model(r: Record) -> bool:
            return ((r.choices is None or "contested" not in r.choices.get("model", {}))
                    and (traces / f"{r.trial}.jsonl.gz").exists())

        def lacks_references(r: Record) -> bool:
            return r.choices is None or any("contested" not in r.choices.get(arm, {})
                                            for arm in ("heuristic", "random"))

        missing = [r for r in records if r.random_score is None or lacks_references(r)
                   or lacks_model(r)]
        if not missing:
            continue
        rules = every[label]
        make = makers.setdefault((label, domain), maker(domain, rules.domains[domain]))
        filled = []
        for r in records:
            if r.random_score is None:
                problem = make(r.trial)
                d = shortest(problem)[problem.start]
                aimless = wander(problem, rules)
                r = dataclasses.replace(r, random_expansions=aimless.expansions,
                                        random_score=efficiency(d, aimless.expansions))
            if lacks_references(r) or lacks_model(r):
                choices = {**(r.choices or {}),
                           **reference_choices(label, domain, rules, make, r.trial)}
                trace = traces / f"{r.trial}.jsonl.gz"
                if lacks_model(r):
                    with gzip.open(trace, "rt", encoding="utf-8") as lines:
                        steps = [json.loads(line) for line in lines][1:]  # after the header
                    problem, distance, start, d = prepared(label, domain, make, r.trial)
                    tally = Tally(distance, start, d)
                    if replay(problem, rules, steps, r.model, tally):
                        choices["model"] = tally.result()
                    else:
                        console.print(f"[yellow]{path.relative_to(PROJECT)} trial {r.trial}: "
                                      "the trace does not fit the problem")
                r = dataclasses.replace(r, choices=choices)
            filled.append(r)
        temporary = path.with_suffix(".jsonl.filling")
        temporary.write_text("".join(json.dumps(dataclasses.asdict(r)) + "\n" for r in filled))
        temporary.replace(path)
        console.print(f"{path.relative_to(PROJECT)}: filled {len(missing)} trials")


def run_case_study(args: argparse.Namespace) -> None:
    """Run each condition of the sensitivity studies of the config. Spends money."""
    import dataclasses
    import importlib

    from . import case_study

    officials = benchmark.load(OFFICIAL)
    cfg = config.load(args.config, officials)
    study = cfg.case_study
    if study is None:
        raise SystemExit(f"{args.config} has no [sensitivity] table")
    rules = officials[cfg.run.benchmark]
    represent = getattr(importlib.import_module(f".domains.{study.domain}", __package__),
                        "represent", None)
    if represent is None:
        raise SystemExit(f"{study.domain} has no other representations")
    make = maker(study.domain, rules.domains[study.domain])
    for name in study.choosers:
        chooser = cfg.choosers[name]
        ledger = dataclasses.replace(chooser, name=f"{chooser.name}.{case_study.LABEL}")
        spend = Spend(max_requests=chooser.max_requests,
                      max_input_tokens=chooser.max_input_tokens,
                      wallet=wallet_of(ledger, chooser.max_cost or cfg.run.max_cost,
                                       cfg.run.max_total_cost))
        make_chooser = config.factory(chooser, PROJECT / ".env")
        folder = case_study.results_dir(RESULTS, chooser.name, study)
        for condition, representation, order in case_study.conditions(study):
            path = folder / f"{condition}.jsonl"
            done = {r.trial for r in read(path)}
            for trial in range(1, study.trials + 1):
                if trial in done:
                    continue
                shown, arrange = case_study.prepared(make(trial), representation, order,
                                                     chooser.model, represent)
                choose = make_chooser(shown, spend, arrange)
                trace = (TRACES / case_study.LABEL / chooser.name / study.domain / condition
                         / f"{trial}.jsonl.gz")
                try:
                    record = measure(shown, rules=rules, label=case_study.LABEL, choose=choose,
                                     chooser=chooser.name, model=chooser.model, spend=spend,
                                     trace=trace)
                except (BudgetExhausted, ChooserError) as error:
                    raise SystemExit(f"{name} {condition} trial {trial} is not recorded: {error}")
                append(path, record)
                console.print(f"{name} {condition} trial {trial}: score {record.score:.3f} · "
                              f"heuristic {record.baseline_score:.3f} · {record.requests} requests")
        console.print(f"{name}: the studies are complete: {folder.relative_to(PROJECT)}")


def agreement(args: argparse.Namespace) -> None:
    """Send the questions of the traces of ``--against`` to ``--chooser``, and compare.

    For each traced trial, the search follows the choices of the trace, so each question
    has the same options in the same order as in that run. At each question, the chooser
    under test answers too. The table gives the share of questions where both chose the
    same option, and the mean difference of the probabilities that the two gave that
    option. It sends a request for each question, and records nothing.
    """
    import gzip
    import json

    officials = benchmark.load(OFFICIAL)
    cfg = config.load(args.config, officials)
    rules = officials[args.benchmark or cfg.run.benchmark]
    test, against = cfg.choosers[args.chooser], cfg.choosers[args.against]
    make_chooser = config.factory(test, PROJECT / ".env")
    import time

    table = Table("domain", "trials", "questions", "same choice", "mean |difference| of p",
                  "questions a second",
                  title=f"{test.title} against the traces of {against.title}")
    for domain in args.domain or list(rules.domains):
        make = maker(domain, rules.domains[domain])
        stem = f"{domain}.{rules.domains[domain]['heuristic']}"
        trials = same = questions = 0
        differences: list[float] = []
        started = time.monotonic()
        for trial in range(1, args.trials + 1):
            trace = TRACES / rules.name / against.name / stem / f"{trial}.jsonl.gz"
            if not trace.exists():
                continue
            with gzip.open(trace, "rt", encoding="utf-8") as lines:
                steps = [json.loads(line) for line in lines][1:]
            problem = make(trial)
            spend = Spend(max_requests=10 ** 9, max_input_tokens=10 ** 12)
            # The order draws of the traced run, so each question is the same request.
            ask = make_chooser(problem, spend, Draws(domain, trial, "order", against.model))
            traced = iter(steps)

            def choose(states):
                nonlocal same, questions
                step = next(traced)
                names = [problem.render(s) for s in states]
                chosen = names.index(step["chosen"])
                mine = ask(states)
                questions += 1
                same += mine == chosen
                if spend.probabilities is not None and step.get("p_chosen") is not None:
                    differences.append(abs(spend.probabilities[chosen] - step["p_chosen"]))
                return chosen

            def forced(states, index, state, was_forced):
                if was_forced:
                    next(traced)

            best_first(start=problem.start, moves=problem.moves, solved=problem.solved,
                       choose=choose, max_expansions=len(steps),
                       max_frontier=rules.max_frontier,
                       evict=Draws(domain, trial, "evict", "model", against.model), step=forced)
            trials += 1
        if questions:
            table.add_row(domain, str(trials), f"{questions:,}", f"{same / questions:.1%}",
                          f"{sum(differences) / len(differences):.3f}" if differences else "—",
                          f"{questions / (time.monotonic() - started):.1f}")
    console.print(table)


def check_docs(args: argparse.Namespace) -> None:
    officials = benchmark.load(OFFICIAL)
    found = publishing.problems(officials, DOCS)
    for problem in found:
        console.print(f"[red]{problem}")
    if found:
        raise SystemExit(f"{len(found)} problems. `python -m beelinebench publish <version>` "
                         "writes a missing page and link.")
    console.print(f"every official benchmark has a page and a link: {', '.join(officials)}")


def publish(args: argparse.Namespace) -> None:
    officials = benchmark.load(OFFICIAL)
    if args.version not in officials:
        raise SystemExit(f"{args.version} is not in {OFFICIAL.name}. Add its table first.")
    written = publishing.publish(officials[args.version], DOCS, officials)
    for path in written:
        console.print(f"wrote {path.relative_to(PROJECT)}")
    if not written:
        console.print(f"{args.version} already has a page and a link")


def price_list(choosers: dict[str, config.ChooserConfig]) -> dict[str, tuple[float, float]]:
    return {c.name: (c.price_input, c.price_output or 0.0)
            for c in choosers.values() if c.price_input is not None}


def figure_is_current(kind: str, png: Path, b: Benchmark, labels, hidden, prices) -> bool:
    from . import plot

    if kind == "frontier_figure":
        return plot.is_current(png, b, RESULTS, labels, hidden, prices, kind="frontier")
    if kind == "choices_figure":
        return plot.is_current(png, b, RESULTS, labels, hidden, kind="choices")
    return plot.is_current(png, b, RESULTS, labels, hidden)


def draw_figure(kind: str, png: Path, b: Benchmark, labels, hidden, prices) -> None:
    from . import plot

    if kind == "frontier_figure":
        plot.draw_frontier(b, RESULTS, png, labels, hidden, prices)
    elif kind == "choices_figure":
        plot.draw_choices(b, RESULTS, png, labels, hidden)
    else:
        plot.draw(b, RESULTS, png, labels, hidden)


def make_readme(args: argparse.Namespace) -> None:
    from . import plot

    template = PROJECT / readme.TEMPLATE
    officials = benchmark.load(OFFICIAL)
    cfg = config.load(args.config, officials)
    choosers = cfg.choosers
    labels = {c.name: c.title for c in choosers.values()}
    hidden = config.unpublished(choosers)
    prices = price_list(choosers)
    try:
        built = {PROJECT / out: readme.render((PROJECT / source).read_text(), officials, RESULTS,
                                              choosers, source, cfg.mini, cfg.case_study)
                 for source, out in readme.pages(officials)}
        # The index of the benchmarks shows both figures of every version.
        figures = sorted(set(readme.figures(template.read_text(), officials))
                         | {(kind, name) for kind in readme.FIGURES for name in officials})
    except ValueError as error:
        raise SystemExit(f"{template.name}: {error}")
    index_path, index_text = DOCS / publishing.INDEX, publishing.index(officials)
    # The page of each benchmark shows its figures, and their data as tables.
    pages = {}
    for name, b in officials.items():
        page = DOCS / publishing.page_name(name)
        if page.exists():
            section = readme.results_section(b, RESULTS, labels, hidden, prices)
            notes = readme.commentary(name, officials, RESULTS, choosers, cfg.mini)
            if notes:
                section = (f"## Commentary\n\n[Commentary on benchmark {name}]"
                           f"({name}-commentary.md)\n\n{section}")
                pages[DOCS / f"{name}-commentary.md"] = readme.commentary_page(name, notes)
            pages[page] = publishing.with_results(page.read_text(), section)
    # The mini benchmark: its figures and its index, in docs/benchmarks/mini/.
    minis, mini_path, mini_text = [], DOCS / publishing.MINI / publishing.INDEX, None
    if cfg.mini is not None:
        scope = dict(trials=cfg.mini.trials, only=set(cfg.mini.choosers))
        sections = {name: readme.results_section(b, RESULTS, labels, hidden, prices, **scope)
                    for name, b in officials.items()}
        mini_text = publishing.mini_index(
            officials, cfg.mini.trials, [labels.get(c, c) for c in cfg.mini.choosers], sections)
        for name, b in officials.items():
            if plot.rows(b, RESULTS, labels, hidden, prices, **scope):
                minis += [("scores", b, mini_path.parent / f"{name}.png", scope),
                          ("frontier", b, mini_path.parent / f"{name}-frontier.png", scope)]
            if plot.choice_rows(b, RESULTS, labels, hidden, **scope):
                minis.append(("choices", b, mini_path.parent / f"{name}-choices.png", scope))

    # The figure of each sensitivity study.
    studies = []
    if cfg.case_study is not None:
        from . import case_study as study_module
        latest = officials[list(officials)[-1]]
        if any(any(study_module.results_dir(RESULTS, c, cfg.case_study).glob("*.jsonl"))
               for c in cfg.case_study.choosers):
            studies = [(kind, PROJECT / readme.STUDY_FIGURE.format(latest.name, kind))
                       for kind in study_module.STUDIES]

    def study_is_current(kind, png) -> bool:
        return plot.stored_fingerprint(png) == plot.case_study_fingerprint(
            cfg.case_study, RESULTS, latest, kind, labels)

    def mini_is_current(kind, b, png, scope) -> bool:
        return plot.is_current(png, b, RESULTS, labels, hidden,
                               prices if kind == "frontier" else {}, kind, **scope)

    if not args.check:
        for kind, png in studies:
            if not study_is_current(kind, png):
                plot.draw_case_study(cfg.case_study, RESULTS, png, latest, kind, labels)
                console.print(f"wrote {png.relative_to(PROJECT)}")
        for kind, b, png, scope in minis:
            if mini_is_current(kind, b, png, scope):
                continue
            png.parent.mkdir(parents=True, exist_ok=True)
            if kind == "frontier":
                plot.draw_frontier(b, RESULTS, png, labels, hidden, prices, **scope)
            elif kind == "choices":
                plot.draw_choices(b, RESULTS, png, labels, hidden, **scope)
            else:
                plot.draw(b, RESULTS, png, labels, hidden, **scope)
            console.print(f"wrote {png.relative_to(PROJECT)}")
        if mini_text is not None and (not mini_path.exists() or mini_path.read_text() != mini_text):
            mini_path.write_text(mini_text)
            console.print(f"wrote {mini_path.relative_to(PROJECT)}")
        for kind, name in figures:
            png = PROJECT / readme.FIGURES[kind].format(name)
            if figure_is_current(kind, png, officials[name], labels, hidden, prices):
                continue
            try:
                draw_figure(kind, png, officials[name], labels, hidden, prices)
            except ImportError:
                raise SystemExit("the README shows a figure, and drawing it needs matplotlib. "
                                 "Run `uv sync --extra plot`.")
            console.print(f"wrote {png.relative_to(PROJECT)}")
        if not index_path.exists() or index_path.read_text() != index_text:
            index_path.write_text(index_text)
            console.print(f"wrote {index_path.relative_to(PROJECT)}")
        for page, page_text in pages.items():
            if not page.exists() or page.read_text() != page_text:
                page.write_text(page_text)
                console.print(f"wrote {page.relative_to(PROJECT)}")
        for target, text in built.items():
            current = target.read_text() if target.exists() else ""
            target.write_text(text)
            console.print(f"wrote {target.relative_to(PROJECT)}" if text != current
                          else f"{target.relative_to(PROJECT)} is already up to date")
        return
    old = [readme.FIGURES[kind].format(name) for kind, name in figures
           if not figure_is_current(kind, PROJECT / readme.FIGURES[kind].format(name),
                                    officials[name], labels, hidden, prices)]
    if old:
        raise SystemExit(f"{', '.join(old)} does not show the current results. "
                         "Run `python -m beelinebench readme`, and commit the figure.")
    stale = [str(page.relative_to(PROJECT)) for page, page_text in pages.items()
             if not page.exists() or page.read_text() != page_text]
    stale += [str(png.relative_to(PROJECT)) for kind, b, png, scope in minis
              if not mini_is_current(kind, b, png, scope)]
    stale += [str(png.relative_to(PROJECT)) for kind, png in studies
              if not study_is_current(kind, png)]
    if mini_text is not None and (not mini_path.exists() or mini_path.read_text() != mini_text):
        stale.append(str(mini_path.relative_to(PROJECT)))
    if stale:
        raise SystemExit(f"{', '.join(stale)} does not show the current results. "
                         "Run `python -m beelinebench readme`, and commit it.")
    if not index_path.exists() or index_path.read_text() != index_text:
        raise SystemExit(f"{index_path.relative_to(PROJECT)} is out of date. "
                         "Run `python -m beelinebench readme`, and commit it.")
    for target, text in built.items():
        current = target.read_text() if target.exists() else ""
        if text != current:
            name = target.relative_to(PROJECT)
            diff = difflib.unified_diff(current.splitlines(keepends=True),
                                        text.splitlines(keepends=True),
                                        f"{name} (committed)", f"{name} (made)")
            console.print("".join(diff), markup=False, highlight=False)
            raise SystemExit(f"{name} is not what its template and the results make. "
                             f"Run `python -m beelinebench readme`, and commit {name}.")
    console.print("the README and the pages are up to date")


#: For each domain with downloaded data: the file that shows the data is there, its source,
#: and the SHA-256 of the source.
DATA = {
    "word_ladder": (word_ladder.DATA, word_ladder.SOURCE, word_ladder.SHA256),
    "wikispeedia": (wikispeedia.DATA / "links.tsv", wikispeedia.SOURCE, wikispeedia.SHA256),
}


def ensure_data(domain: str) -> None:
    """Download the data of ``domain`` if it is not in data/ yet. Other domains need none.

    The file must have its SHA-256, so that each machine has the same trials.
    """
    if domain not in DATA:
        return
    marker, url, sha256 = DATA[domain]
    if (PROJECT / marker).exists():
        return
    import hashlib

    import httpx

    console.print(f"fetching the data of {domain} from {url}")
    response = httpx.get(url, follow_redirects=True, timeout=300.0)
    response.raise_for_status()
    found = hashlib.sha256(response.content).hexdigest()
    if found != sha256:
        raise SystemExit(f"{url} has the SHA-256 {found}, not {sha256}. The source changed, "
                         "so its trials would not be those of the benchmark.")
    target = PROJECT / marker
    target.parent.mkdir(parents=True, exist_ok=True)
    if url.endswith(".tar.gz"):
        with tarfile.open(fileobj=io.BytesIO(response.content), mode="r:gz") as archive:
            archive.extractall(target.parent.parent, filter="data")
    else:
        target.write_bytes(response.content)


def download(args: argparse.Namespace) -> None:
    for domain in args.domain or DATA:
        ensure_data(domain)
    console.print(f"the data is in {PROJECT / 'data'}")


def init(args: argparse.Namespace) -> None:
    """Write a ``beelinebench.toml`` to start from, in the working folder."""
    import shutil

    target = args.config
    if target.exists():
        raise SystemExit(f"{target} exists. Edit it, or delete it to start again.")
    shutil.copyfile(paths.starter_config(), target)
    console.print(f"wrote {target}\n"
                  "Next: put the keys of your models in .env, check the limits in the [run] table, "
                  "and run `beelinebench run --mini` or `beelinebench baseline`.")


#: The commands that need no beelinebench.toml.
NO_CONFIG = {"init", "download", "report", "check-docs"}
#: The commands that change the docs of the repository, so they need a clone of it.
MAINTAINER = {"readme", "publish", "check-docs"}


def main() -> None:
    parser = argparse.ArgumentParser(prog="beelinebench")
    parser.add_argument("--config", type=Path, default=PROJECT / "beelinebench.toml",
                        help="what to run, and the choosers. The default is beelinebench.toml")
    commands = parser.add_subparsers(required=True, dest="command")

    for name, handler, help_text in (
            ("run", run, "both arms, for each chooser. Spends money."),
            ("baseline", show_baseline, "the classic arm alone. Sends nothing.")):
        command = commands.add_parser(name, help=help_text)
        command.set_defaults(handler=handler)
        command.add_argument("--benchmark", help="in place of [run] benchmark")
        command.add_argument("--domain", nargs="+", help="in place of [run] domains")
        command.add_argument("--trials", type=int, help="runs trials 1 to N, in place "
                             "of the trials of the config and the benchmark")
        if name == "run":
            command.add_argument("--chooser", help="one chooser, in place of [run] choosers")
            command.add_argument("--max-requests", type=int,
                                 help="in place of the chooser's max_requests")
            command.add_argument("--max-input-tokens", type=int,
                                 help="in place of the chooser's max_input_tokens")
            command.add_argument("--rerun-unclean", action="store_true",
                                 help="run again each trial with refusals, invalid answers or "
                                 "retries. The new run takes the place of the old one only if "
                                 "it has fewer of them, whatever its score")
            command.add_argument("--mini", action="store_true",
                                 help="the mini benchmark: the first trials of each domain, "
                                 "with the choosers of the [mini] table of the config")
            command.add_argument("--retrace", action="store_true",
                                 help="run again each trial that has a result and no trace, "
                                 "and put its new result in place of the old one")

    commands.add_parser("benchmarks", help="the official benchmarks, and those of the config"
                        ).set_defaults(handler=show_benchmarks)
    commands.add_parser("choosers", help="the choosers of the config"
                        ).set_defaults(handler=choosers)
    command = commands.add_parser("probe", help="send one question with 255 options to a "
                                  "chooser. Spends one or two requests.")
    command.set_defaults(handler=probe)
    command.add_argument("--chooser", required=True)
    command = commands.add_parser("agreement", help="send the questions of the traces of one "
                                  "chooser to another, and compare their choices. Sends "
                                  "requests, and records nothing.")
    command.set_defaults(handler=agreement)
    command.add_argument("--chooser", required=True, help="the chooser to test, for example "
                         "clef-local")
    command.add_argument("--against", required=True, help="the chooser of the traces, for "
                         "example clef")
    command.add_argument("--benchmark", help="an official benchmark. The default is [run] benchmark")
    command.add_argument("--domain", nargs="+", help="only these domains")
    command.add_argument("--trials", type=int, default=5, help="trials 1 to N that have a trace")
    command = commands.add_parser("case-study", help="run the case study of the config: one "
                                  "model on one problem, with each representation and option "
                                  "order. Spends money.")
    command.set_defaults(handler=run_case_study)
    command = commands.add_parser("fill", help="add missing reference arms to old results. "
                                  "Sends nothing. Do not use it on a chooser that runs.")
    command.set_defaults(handler=fill)
    command.add_argument("--chooser", nargs="+", help="only these choosers")
    command = commands.add_parser("report", help="the score of each result file")
    command.set_defaults(handler=report)
    command.add_argument("--json", action="store_true",
                         help="print the scores as JSON, one object for each result file, "
                         "for a dashboard or a script")
    command = commands.add_parser("plot", help="the scores of an official benchmark as a "
                                  "figure. Needs `uv sync --extra plot`.")
    command.set_defaults(handler=make_plot)
    command.add_argument("--benchmark", help="an official benchmark. The default is the newest")
    command.add_argument("--out", type=Path, help="the image file. The default is "
                         "docs/benchmarks/<benchmark>.png")
    commands.add_parser("check-docs", help="every official benchmark has a page and a "
                        "link. CI runs this.").set_defaults(handler=check_docs)
    command = commands.add_parser("readme", help="write README.md from README.template.md "
                                  "and the results")
    command.set_defaults(handler=make_readme)
    command.add_argument("--check", action="store_true",
                         help="write nothing. Fail if README.md is out of date. CI runs this.")
    command = commands.add_parser("publish", help="write the page and the link of an "
                                  "official benchmark")
    command.set_defaults(handler=publish)
    command.add_argument("version", help="a benchmark of benchmarks.toml")
    commands.add_parser("init", help="write a beelinebench.toml to start from, in the working "
                        "folder").set_defaults(handler=init)
    command = commands.add_parser("download", help="fetch the data of the domains that need "
                                  "it. A run also fetches it when it needs it.")
    command.set_defaults(handler=download)
    command.add_argument("--domain", nargs="+", choices=sorted(DATA),
                         help="only these domains. The default is each domain that needs data")

    args = parser.parse_args()
    command = args.command
    if command in MAINTAINER and not (PROJECT / readme.TEMPLATE).exists():
        raise SystemExit(f"{command} changes the docs of the repository, so it runs in a clone of "
                         "https://github.com/kyle-pena-nlp/beelinebench.")
    if command not in NO_CONFIG and not args.config.exists():
        raise SystemExit(f"{args.config} does not exist. Run `beelinebench init` to write one.")
    args.handler(args)


if __name__ == "__main__":
    main()
