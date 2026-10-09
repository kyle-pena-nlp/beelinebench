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

from . import benchmark, config, publishing, readme
from .benchmark import Benchmark
from .domains import blocksworld, countdown, rush_hour, tiles, wikispeedia, word_ladder
from .rng import Draws
from .run import (Record, append, baseline, best, geometric_mean, measure, read, results_file,
                  shortest, summarise, wander)
from .search import BudgetExhausted, ChooserError, Problem, Spend, Wallet, efficiency

PROJECT = Path(__file__).resolve().parent.parent
RESULTS = PROJECT / "results"
#: The total cost of each model over all runs: .spend/<chooser>.json.
SPEND = PROJECT / ".spend"
OFFICIAL = PROJECT / "benchmarks.toml"
DOCS = PROJECT / "docs" / "benchmarks"

console = Console()


def maker(domain: str, settings: dict[str, Any]) -> Callable[[int], Problem]:
    """The function that makes trial ``n`` of ``domain`` with ``settings``."""
    if domain == "wikispeedia":
        graph = wikispeedia.load(PROJECT / wikispeedia.DATA)
        return lambda trial: wikispeedia.problem(trial, graph, **settings)
    if domain == "word_ladder":
        ladder = word_ladder.load(PROJECT / word_ladder.DATA)
        return lambda trial: word_ladder.problem(trial, ladder, **settings)
    problem = {"tiles": tiles.problem, "blocksworld": blocksworld.problem,
               "countdown": countdown.problem, "rush_hour": rush_hour.problem}[domain]
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
    names = [args.chooser] if args.chooser else list(cfg.run.choosers)
    for name in names:
        if name not in cfg.choosers:
            raise SystemExit(f"no chooser {name!r} in {args.config}. "
                             f"It has: {', '.join(cfg.choosers)}")
    label = label_of(chosen, domains, officials)
    for name in names:
        chooser = cfg.choosers[name]
        trials = args.trials or chooser.trials or cfg.run.trials or chosen.trials
        finished = run_chooser(chooser, chosen, label, domains, trials,
                               max_requests=args.max_requests or chooser.max_requests,
                               max_input_tokens=args.max_input_tokens or chooser.max_input_tokens,
                               max_cost=chooser.max_cost or cfg.run.max_cost)
        show_match(chooser.name, chosen, label, domains, officials, finished)


def run_chooser(chooser: config.ChooserConfig, chosen: Benchmark, label: str,
                domains: list[str], trials: int, *, max_requests: int,
                max_input_tokens: int, max_cost: float | None = None) -> bool:
    """Run one chooser over ``domains``. False when it stopped at a limit.

    With ``max_cost`` and a price, the run stops before the request that would start
    when the model's cost over all runs is ``max_cost`` or more.
    """
    make_chooser = config.factory(chooser, PROJECT / ".env")
    spend = Spend(max_requests=max_requests, max_input_tokens=max_input_tokens,
                  wallet=wallet_of(chooser, max_cost))
    if spend.wallet is not None:
        console.print(f"{chooser.name} has cost ${spend.wallet.cost:.2f} in all. "
                      f"The limit is ${spend.wallet.max_cost:.2f}.")
    with progress() as bars:
        for domain in domains:
            make = maker(domain, chosen.domains[domain])
            path = results_file(RESULTS, label, chooser.name, make(1))
            done = {record.trial for record in read(path)}
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
                    record = measure(problem, rules=chosen, label=label, choose=choose,
                                     chooser=chooser.name, model=chooser.model, spend=spend,
                                     observe=watcher(bars, current, trial, spend))
                except BudgetExhausted:
                    console.print(f"[red]{chooser.name} stopped at {spend.requests:,} requests "
                                  f"and {spend.input_tokens:,} input tokens. "
                                  f"{domain} trial {trial} is not recorded.")
                    return False
                except ChooserError as error:
                    console.print(f"[red]{chooser.name} stopped: {error}. "
                                  f"{domain} trial {trial} is not recorded.")
                    return False
                append(path, record)
                bars.advance(bench)
                console.print(line_of(record))
            bars.remove_task(current)
    console.print(f"{chooser.name} spent {spend.requests:,} requests, "
                  f"{spend.input_tokens:,} input tokens, {spend.output_tokens:,} output tokens")
    return True


def wallet_of(chooser: config.ChooserConfig, max_cost: float | None) -> Wallet | None:
    """The cost of ``chooser`` over all runs, with its limit. ``None`` without a price or limit.

    A model without a file in .spend/ starts at the tokens of its recorded trials.
    """
    if max_cost is None or chooser.price_input is None:
        return None
    records = [r for path in RESULTS.glob(f"*/{chooser.name}/*.jsonl") for r in read(path)]
    start = (sum(r.input_tokens for r in records), sum(r.output_tokens for r in records),
             sum(r.requests for r in records))
    return Wallet.open(SPEND / f"{chooser.name}.json", price_input=chooser.price_input,
                       price_output=chooser.price_output or 0.0, max_cost=max_cost, start=start)


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
    for path in sorted(RESULTS.glob("*/*/*.jsonl")):
        label, chooser = path.parent.parent.name, path.parent.name
        domain, heuristic = path.stem.split(".")
        records = read(path)
        s = summarise(records, draws=Draws("bootstrap", label, chooser, path.stem))
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
    except ImportError:
        raise SystemExit("plot needs matplotlib. Run `uv sync --extra plot`.")
    except ValueError as error:
        raise SystemExit(str(error))
    console.print(f"wrote {target}")


def fill(args: argparse.Namespace) -> None:
    """Add the random arm to records that do not have it. Sends no requests.

    Do not fill the files of a chooser while it runs: the run appends to them.
    """
    import dataclasses
    import json

    officials = benchmark.load(OFFICIAL)
    cfg = config.load(args.config, officials)
    every = {**officials, **{f"custom-{name}": b for name, b in cfg.benchmarks.items()}}
    makers: dict = {}
    for path in sorted(RESULTS.glob("*/*/*.jsonl")):
        label, chooser = path.parent.parent.name, path.parent.name
        if args.chooser and chooser not in args.chooser:
            continue
        if label not in every:
            console.print(f"[yellow]skipped {path.relative_to(PROJECT)}: no benchmark {label}")
            continue
        domain = path.stem.split(".")[0]
        records = read(path)
        missing = [r for r in records if r.random_score is None]
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
            filled.append(r)
        temporary = path.with_suffix(".jsonl.filling")
        temporary.write_text("".join(json.dumps(dataclasses.asdict(r)) + "\n" for r in filled))
        temporary.replace(path)
        console.print(f"{path.relative_to(PROJECT)}: added the random arm to {len(missing)} trials")


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
    written = publishing.publish(officials[args.version], DOCS)
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
    return plot.is_current(png, b, RESULTS, labels, hidden)


def draw_figure(kind: str, png: Path, b: Benchmark, labels, hidden, prices) -> None:
    from . import plot

    if kind == "frontier_figure":
        plot.draw_frontier(b, RESULTS, png, labels, hidden, prices)
    else:
        plot.draw(b, RESULTS, png, labels, hidden)


def make_readme(args: argparse.Namespace) -> None:
    from . import plot

    template = PROJECT / readme.TEMPLATE
    target = PROJECT / readme.OUTPUT
    officials = benchmark.load(OFFICIAL)
    choosers = config.load(args.config, officials).choosers
    labels = {c.name: c.title for c in choosers.values()}
    hidden = config.unpublished(choosers)
    prices = price_list(choosers)
    try:
        text = readme.render(template.read_text(), officials, RESULTS, choosers)
        figures = readme.figures(template.read_text(), officials)
    except ValueError as error:
        raise SystemExit(f"{template.name}: {error}")
    current = target.read_text() if target.exists() else ""
    if not args.check:
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
        target.write_text(text)
        console.print(f"wrote {target.name}" if text != current
                      else f"{target.name} is already up to date")
        return
    old = [readme.FIGURES[kind].format(name) for kind, name in figures
           if not figure_is_current(kind, PROJECT / readme.FIGURES[kind].format(name),
                                    officials[name], labels, hidden, prices)]
    if old:
        raise SystemExit(f"{', '.join(old)} does not show the current results. "
                         "Run `python -m beelinebench readme`, and commit the figure.")
    if text != current:
        diff = difflib.unified_diff(current.splitlines(keepends=True),
                                    text.splitlines(keepends=True),
                                    f"{target.name} (committed)", f"{target.name} (made)")
        console.print("".join(diff), markup=False, highlight=False)
        raise SystemExit(f"{target.name} is not what {template.name} and the results make. "
                         "Run `python -m beelinebench readme`, and commit README.md.")
    console.print(f"{target.name} is up to date")


def download(args: argparse.Namespace) -> None:
    import httpx

    def fetch(url: str) -> bytes:
        console.print(f"fetching {url}")
        response = httpx.get(url, follow_redirects=True, timeout=300.0)
        response.raise_for_status()
        return response.content

    target = PROJECT / word_ladder.DATA
    if not target.exists():
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(fetch(word_ladder.SOURCE))
    target = PROJECT / wikispeedia.DATA
    if not (target / "links.tsv").exists():
        target.parent.mkdir(parents=True, exist_ok=True)
        with tarfile.open(fileobj=io.BytesIO(fetch(wikispeedia.SOURCE)), mode="r:gz") as archive:
            archive.extractall(target.parent, filter="data")
    console.print(f"the data is in {PROJECT / 'data'}")


def main() -> None:
    parser = argparse.ArgumentParser(prog="beelinebench")
    parser.add_argument("--config", type=Path, default=PROJECT / "beelinebench.toml",
                        help="what to run, and the choosers. The default is beelinebench.toml")
    commands = parser.add_subparsers(required=True)

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

    commands.add_parser("benchmarks", help="the official benchmarks, and those of the config"
                        ).set_defaults(handler=show_benchmarks)
    commands.add_parser("choosers", help="the choosers of the config"
                        ).set_defaults(handler=choosers)
    command = commands.add_parser("probe", help="send one question with 255 options to a "
                                  "chooser. Spends one or two requests.")
    command.set_defaults(handler=probe)
    command.add_argument("--chooser", required=True)
    command = commands.add_parser("fill", help="add missing reference arms to old results. "
                                  "Sends nothing. Do not use it on a chooser that runs.")
    command.set_defaults(handler=fill)
    command.add_argument("--chooser", nargs="+", help="only these choosers")
    commands.add_parser("report", help="the score of each result file"
                        ).set_defaults(handler=report)
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
    commands.add_parser("download", help="fetch the data of the domains that need it"
                        ).set_defaults(handler=download)

    args = parser.parse_args()
    args.handler(args)


if __name__ == "__main__":
    main()
