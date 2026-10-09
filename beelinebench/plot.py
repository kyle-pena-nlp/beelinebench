"""A forest plot of the scores of an official benchmark.

Each domain is a group of rows, and each row is a chooser: its score (the
geometric mean over its trials) and the 95% bootstrap interval. The rows of a group
are ranked by score, best first. The classic heuristic on the same trials is a row
too, for reference, and so is random choice, drawn with an open circle. The x axis is logarithmic, because
a score is a ratio and the mean is geometric. The line at 1.0 is a perfect search.

``python -m beelinebench plot`` writes the figure. It needs matplotlib: ``uv sync
--extra plot``. ``python -m beelinebench readme`` also writes it, for the README.

The PNG holds a fingerprint of the rows that it shows. :func:`is_current` compares
that fingerprint with the rows of the current results, so CI can find an old figure
without matplotlib.
"""

from __future__ import annotations

import hashlib
import json
import math
import struct
import zlib
from collections.abc import Collection, Mapping
from dataclasses import astuple, dataclass
from pathlib import Path

from .benchmark import Benchmark
from .domains import HEURISTIC_TITLES, TITLES
from .rng import Draws
from .run import geometric_mean, interval, read

#: Greys only. One tone for every mark, so position alone carries the comparison.
MARK = "#333333"
BAND = "#cccccc"
SURFACE = "#ffffff"
TEXT = "#2b2b2b"
MUTED = "#6b6b6b"
GRID = "#ebebeb"
CENTRE = "#5a5a5a"
#: Minor gridlines, lighter than the major ones.
MINOR_GRID = "#f4f4f4"

TICKS = (0.002, 0.005, 0.01, 0.02, 0.05, 0.1, 0.2, 0.5, 1.0)

#: The look of the figures. A change of the look changes this number, so that
#: ``readme`` draws the figures again.
STYLE = 29

#: The PNG text key that holds the fingerprint of the rows.
FINGERPRINT_KEY = "beelinebench-rows"


@dataclass(frozen=True)
class Row:
    label: str
    score: float
    low: float
    high: float
    trials: int
    #: A run that hit the limit unsolved: ``*`` for a model, ``†`` for the heuristic.
    marks: str
    #: A reference arm, not a model: the heuristic (a diamond) or random choice (an open
    #: circle).
    reference: bool = False
    marker: str = "D"
    #: US dollars for one step (one request), from the mean tokens of a request. ``None`` without a price.
    cost_per_step: float | None = None


#: For each chooser, US dollars for a million input and output tokens.
Prices = Mapping[str, tuple[float, float]]


def rows(b: Benchmark, results: Path, labels: Mapping[str, str] = {},
         hidden: Collection[str] = (), prices: Prices = {}, trials: int | None = None,
         only: Collection[str] | None = None) -> list[tuple[str, list[Row]]]:
    """For each domain of ``b`` with results: a row for the heuristic and for each chooser, best first.

    ``labels`` gives the name of a chooser for a reader. A chooser without one
    keeps its own name. The choosers in ``hidden`` are left out. With ``trials``, only
    trials 1 to ``trials`` count, and with ``only``, only those choosers: the mini benchmark.
    """
    choosers = sorted(p.name for p in (results / b.name).glob("*")
                      if p.is_dir() and p.name not in hidden
                      and (only is None or p.name in only))
    groups = []
    for domain, settings in b.domains.items():
        heuristic = settings["heuristic"]
        stem = f"{domain}.{heuristic}"
        found, classic = [], {}
        for name in choosers:
            records = [r for r in read(results / b.name / name / f"{stem}.jsonl")
                       if r.score is not None and (trials is None or r.trial <= trials)]
            if not records:
                continue
            for r in records:
                # The reference arms are the same in each model's record of a trial. Keep a
                # record that has the random arm, if there is one.
                if r.trial not in classic or classic[r.trial].random_score is None:
                    classic[r.trial] = r
            scores = [r.score for r in records]
            # The same draws as `report` and the README, so all show the same interval.
            low, high = interval(scores, Draws("bootstrap", b.name, name, stem))
            cost = None
            if name in prices and (requests := sum(r.requests for r in records)):
                price_in, price_out = prices[name]
                cost = (sum(r.input_tokens for r in records) * price_in
                        + sum(r.output_tokens for r in records) * price_out) / 1e6 / requests
            found.append(Row(labels.get(name, name), geometric_mean(scores), low, high,
                             len(records), "*" if any(r.censored for r in records) else "",
                             cost_per_step=cost))
        if not found:
            continue
        scores = [classic[trial].baseline_score for trial in sorted(classic)]
        low, high = interval(scores, Draws("bootstrap", b.name, "heuristic", stem))
        reference = Row(f"Heuristic: {HEURISTIC_TITLES.get(heuristic, heuristic)}",
                        geometric_mean(scores), low, high, len(scores),
                        "†" if any(not r.baseline_solved for r in classic.values()) else "",
                        reference=True)
        references = [reference]
        aimless = [classic[trial].random_score for trial in sorted(classic)
                   if classic[trial].random_score is not None]
        if aimless:
            low, high = interval(aimless, Draws("bootstrap", b.name, "random", stem))
            references.append(Row("Random choice", geometric_mean(aimless), low, high,
                                  len(aimless), "", reference=True, marker="o"))
        # Best first. The reference arms take their places among the models.
        ranked = sorted([*references, *found], key=lambda row: -row.score)
        groups.append((TITLES.get(domain, domain), ranked))
    return groups


def mean_interval(values: list[float], draws: Draws) -> tuple[float, float]:
    """The 95% bootstrap interval of the arithmetic mean of ``values``."""
    means = sorted(sum(draws.choice(values) for _ in values) / len(values) for _ in range(2000))
    return means[49], means[1949]


def share(tally: dict) -> float:
    """The share of the decisions of one arm in one trial that matched the oracle."""
    return tally["optimal"] / tally["decisions"]


def choice_tallies(b: Benchmark, results: Path, labels: Mapping[str, str] = {},
                   hidden: Collection[str] = (), trials: int | None = None,
                   only: Collection[str] | None = None):
    """For each domain with choices: its title, and for each arm its label, whether it is a
    reference arm, its mark, the bootstrap name, and the tally of each trial.

    A trial with no decision, or without choices in its record, is left out. ``trials``
    and ``only`` are as for :func:`rows`.
    """
    choosers = sorted(p.name for p in (results / b.name).glob("*")
                      if p.is_dir() and p.name not in hidden
                      and (only is None or p.name in only))
    out = []
    for domain, settings in b.domains.items():
        heuristic = settings["heuristic"]
        stem = f"{domain}.{heuristic}"
        arms, references = [], {}
        for name in choosers:
            records = [r for r in read(results / b.name / name / f"{stem}.jsonl")
                       if r.choices and (trials is None or r.trial <= trials)]
            for r in records:
                references.setdefault(r.trial, r.choices)
            tallies = [r.choices["model"] for r in records
                       if r.choices.get("model", {}).get("decisions")]
            if tallies:
                arms.append((labels.get(name, name), False, "D", name, tallies))
        if not arms:
            continue
        for arm, label, marker in (
                ("heuristic", f"Heuristic: {HEURISTIC_TITLES.get(heuristic, heuristic)}", "D"),
                ("random", "Random choice", "o")):
            tallies = [c[arm] for _, c in sorted(references.items()) if c[arm]["decisions"]]
            if tallies:
                arms.append((label, True, marker, arm, tallies))
        out.append((TITLES.get(domain, domain), stem, arms))
    return out


def choice_rows(b: Benchmark, results: Path, labels: Mapping[str, str] = {},
                hidden: Collection[str] = (), trials: int | None = None,
                only: Collection[str] | None = None) -> list[tuple[str, list[Row]]]:
    """For each domain: the share of decisions that matched the oracle, best first.

    A row is a model, or the heuristic or random arm. Its score is the mean over trials of
    the share of a trial's decisions that took a state with the fewest moves to the goal,
    so each trial counts the same.
    """
    groups = []
    for title, stem, arms in choice_tallies(b, results, labels, hidden, trials, only):
        found = []
        for label, reference, marker, key, tallies in arms:
            shares = [share(t) for t in tallies]
            low, high = mean_interval(shares, Draws("bootstrap", b.name, key, stem, "choices"))
            found.append(Row(label, sum(shares) / len(shares), low, high, len(shares), "",
                             reference=reference, marker=marker))
        groups.append((title, sorted(found, key=lambda row: -row.score)))
    return groups


def mean_regret(tally: dict) -> float | None:
    """The mean oracle regret of the decisions of one trial that did not take a dead end."""
    counted = tally["decisions"] - tally["dead_ends"]
    return tally["regret"] / counted if counted else None


def score_text(score: float) -> str:
    """Two decimals, or two significant digits for a score below 0.01, for example 0.0041."""
    return f"{score:.2f}" if score >= 0.01 else f"{score:#.2g}"


def fingerprint(b: Benchmark, results: Path, labels: Mapping[str, str] = {},
                hidden: Collection[str] = (), prices: Prices = {}, kind: str = "scores",
                trials: int | None = None, only: Collection[str] | None = None) -> str:
    """A hash of everything the figure of ``b`` shows: its rows, and the limit in its notes."""
    groups = [[title, [[round(v, 6) if isinstance(v, float) else v for v in astuple(row)]
                       for row in group]]
              for title, group in (choice_rows(b, results, labels, hidden, trials, only)
                                   if kind == "choices"
                                   else rows(b, results, labels, hidden, prices, trials, only))]
    data = json.dumps([STYLE, kind, b.name, b.max_expansions, trials, groups], sort_keys=True)
    return hashlib.sha256(data.encode()).hexdigest()[:16]


def stored_fingerprint(png: Path) -> str | None:
    """The fingerprint in the text chunks of ``png``, or ``None``."""
    if not png.exists():
        return None
    data = png.read_bytes()
    at = 8  # after the PNG signature
    while at + 8 <= len(data):
        length, kind = struct.unpack(">I4s", data[at:at + 8])
        body = data[at + 8:at + 8 + length]
        at += 12 + length
        if kind == b"tEXt":
            key, _, value = body.partition(b"\0")
        elif kind == b"zTXt":
            key, _, rest = body.partition(b"\0")
            value = zlib.decompress(rest[1:])
        elif kind == b"iTXt":
            key, _, rest = body.partition(b"\0")
            compressed, rest = rest[0], rest[2:]
            rest = rest.split(b"\0", 2)[2]  # skip the language tag and translated key
            value = zlib.decompress(rest) if compressed else rest
        else:
            continue
        if key.decode("latin-1") == FINGERPRINT_KEY:
            return value.decode("utf-8")
    return None


def is_current(png: Path, b: Benchmark, results: Path, labels: Mapping[str, str] = {},
               hidden: Collection[str] = (), prices: Prices = {}, kind: str = "scores",
               trials: int | None = None, only: Collection[str] | None = None) -> bool:
    """Whether ``png`` shows the current results of ``b``."""
    return stored_fingerprint(png) == fingerprint(b, results, labels, hidden, prices, kind,
                                                  trials, only)


def title_name(b: Benchmark, trials: int | None) -> str:
    """The name of the benchmark in a title: ``1.0.0``, or ``1.0.0 mini``."""
    return b.name if trials is None else f"{b.name} mini"


#: The height in inches above the plot for the title and its subtitle.
TITLE_SPACE = 0.6


def titled(fig, title: str, subtitle: str) -> float:
    """Write the title of the figure at its top. Gives the top of the space for the plot."""
    height = fig.get_figheight()
    fig.text(0.01, 1 - 0.12 / height, title, color=TEXT, fontsize=14, fontweight="bold",
             va="top")
    fig.text(0.01, 1 - 0.38 / height, subtitle, color=MUTED, fontsize=9.5, va="top")
    return 1 - TITLE_SPACE / height


def draw(b: Benchmark, results: Path, out: Path, labels: Mapping[str, str] = {},
         hidden: Collection[str] = (), trials: int | None = None,
         only: Collection[str] | None = None) -> None:
    groups = rows(b, results, labels, hidden, trials=trials, only=only)
    if not groups:
        raise ValueError(f"no results for benchmark {b.name}")
    notes = (f"Benchmark {title_name(b, trials)}. A mark is the geometric mean over n trials, "
             "and a band is its 95% bootstrap interval.\nAn open circle is random choice: a "
             "state of the frontier at random. The vertical line at 1.0 is a perfect search.")
    marks = {mark for _, group in groups for row in group for mark in row.marks}
    if "*" in marks or "†" in marks:
        notes += (f"\n* or †: at least one model (*) or heuristic (†) run did not solve within "
                  f"{b.max_expansions:,} nodes, so the true score is lower.")
    forest(groups, out, title=f"BeelineBench {title_name(b, trials)}",
           subtitle="The score of each model, heuristic and random choice, by problem. "
                    "Higher is better, and 1.0 is a perfect search.",
           xlabel="score = (shortest path + 1) / nodes explored   ·   log scale, higher is "
                  "better", notes=notes, log=True,
           stamp=fingerprint(b, results, labels, hidden, trials=trials, only=only))


def draw_choices(b: Benchmark, results: Path, out: Path, labels: Mapping[str, str] = {},
                 hidden: Collection[str] = (), trials: int | None = None,
                 only: Collection[str] | None = None) -> None:
    """The share of decisions that matched the oracle, for each arm, by domain."""
    groups = choice_rows(b, results, labels, hidden, trials, only)
    if not groups:
        raise ValueError(f"no choices for benchmark {b.name}")
    notes = (f"Benchmark {title_name(b, trials)}. A decision is a step with two or more states "
             "on the frontier.\nIt matches the oracle when it takes a state with the fewest moves "
             "to the goal. A mark is the mean over n trials of the share\nof a trial's decisions "
             "that matched, and a band is its 95% bootstrap interval. An open circle is random "
             "choice.")
    forest(groups, out, title=f"BeelineBench {title_name(b, trials)}: choices against the oracle",
           subtitle="The share of decisions that took a state with the fewest moves to the goal, "
                    "by problem. Higher is better.",
           xlabel="share of decisions that matched the oracle", notes=notes, log=False,
           stamp=fingerprint(b, results, labels, hidden, kind="choices", trials=trials,
                             only=only))


def forest(groups: list[tuple[str, list[Row]]], out: Path, *, title: str, subtitle: str,
           xlabel: str, notes: str, log: bool, stamp: str) -> None:
    """Rows of marks and bands, grouped by domain, with a title, notes and a fingerprint."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.ticker import FixedLocator, NullLocator

    # Top to bottom: a header line for each domain, its rows, then a gap.
    placed: list[tuple[float, Row]] = []
    headers: list[tuple[float, str]] = []
    y = 0.0
    for heading, group in groups:
        headers.append((y, heading))
        y += 1
        for row in group:
            placed.append((y, row))
            y += 1
        y += 0.6
    height = y - 0.6

    plt.rcParams.update({"font.size": 10, "font.family": "sans-serif"})
    fig, ax = plt.subplots(figsize=(8.5, 0.27 * height + 1.3 + TITLE_SPACE), facecolor=SURFACE)
    top = titled(fig, title, subtitle)
    ax.set_facecolor(SURFACE)
    if log:
        ax.set_xscale("log")
        lowest = min(row.low for _, row in placed)
        ax.set_xlim(lowest / 1.3, 2.0)
        ax.xaxis.set_major_locator(FixedLocator([t for t in TICKS if t >= lowest / 1.3]))
    else:
        ax.set_xlim(0, 1.15)
        ax.xaxis.set_major_locator(FixedLocator([0, 0.2, 0.4, 0.6, 0.8, 1.0]))
    ax.set_ylim(height - 0.3, -0.7)
    ax.xaxis.set_minor_locator(NullLocator())
    ax.xaxis.set_major_formatter(lambda value, _: f"{value:g}")
    ax.grid(axis="x", color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)
    ax.axvline(1.0, color=CENTRE, linewidth=1.2)

    for y, row in placed:
        ax.plot([row.low, row.high], [y, y], color=BAND, linewidth=2.2,
                solid_capstyle="round")
        ax.plot(row.score, y, marker=row.marker, markersize=7, markeredgewidth=1.5,
                color=SURFACE if row.marker == "o" else MARK, markeredgecolor=MARK)
        # A surface box keeps the label legible where it crosses the line at 1.0.
        ax.text(row.high * 1.07 if log else row.high + 0.015, y,
                f"{score_text(row.score)}{row.marks}", color=TEXT, fontsize=9,
                va="center", bbox=dict(boxstyle="square,pad=0.1", facecolor=SURFACE,
                                       edgecolor="none"))

    ax.set_yticks([y for y, _ in placed],
                  [f"{row.label}  ·  n={row.trials}" for _, row in placed], color=TEXT)
    for y, heading in headers:
        ax.text(-0.02, y, heading, transform=ax.get_yaxis_transform(), ha="right",
                va="center", fontsize=10.5, fontweight="bold", color=TEXT)
    ax.tick_params(axis="y", length=0, pad=8)
    ax.tick_params(axis="x", colors=MUTED, length=0)
    for side in ("top", "right", "left"):
        ax.spines[side].set_visible(False)
    ax.spines["bottom"].set_color(GRID)

    ax.set_xlabel(xlabel, color=MUTED, fontsize=9)
    fig.tight_layout(rect=(0, 0.02 + 0.016 * (notes.count("\n") + 1), 1, top))
    fig.text(0.01, 0.008, notes, color=MUTED, fontsize=8, va="bottom")
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=200, facecolor=SURFACE, metadata={FINGERPRINT_KEY: stamp})
    plt.close(fig)


def frontier(points: list[Row]) -> list[Row]:
    """The rows that no row beats on both cost and score, from the cheapest up."""
    best, out = -1.0, []
    for row in sorted(points, key=lambda r: (r.cost_per_step, -r.score)):
        if row.score > best:
            out.append(row)
            best = row.score
    return out


#: The mark of each model in the frontier plot, in a fixed order. A model keeps its
#: mark in each panel.
#: Only shapes that look different at a small size: no hexagon or pentagon, which look
#: like a circle.
MODEL_MARKS = ("o", "s", "D", "^", "v", "P", "X", "*", "<", ">")


def convex_frontier(points: list[Row]) -> list[Row]:
    """The convex frontier: the convex boundary of the rows on the side of the best corner.

    It is the lower convex hull on the page, where the score axis is reversed and both
    axes are logarithmic. It starts at the row with the best score and ends at the
    cheapest row. A row inside it is not efficient.
    """
    # On the page: x grows as the score falls, and y grows with the cost.
    def where(r: Row) -> tuple[float, float]:
        return (-math.log10(r.score), math.log10(r.cost_per_step))

    def turn(o, a, b) -> float:
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

    hull: list[Row] = []
    for r in sorted(points, key=lambda r: (where(r)[0], where(r)[1])):
        while len(hull) >= 2 and turn(where(hull[-2]), where(hull[-1]), where(r)) <= 0:
            hull.pop()
        hull.append(r)
    # The lower hull runs from the best score to the worst. Keep it down to the cheapest row.
    cheapest = min(range(len(hull)), key=lambda i: where(hull[i])[1])
    return hull[:cheapest + 1]


def draw_frontier(b: Benchmark, results: Path, out: Path, labels: Mapping[str, str] = {},
                  hidden: Collection[str] = (), prices: Prices = {}, trials: int | None = None,
                  only: Collection[str] | None = None) -> None:
    """The cost of a step against the score, one panel for each domain, with the frontier.

    A step is one request: the model chooses one state of the frontier. The cost is
    the mean tokens of a request at the model's list price. A low cost and a high
    score are better. The cost axis is reversed, so the best models are at the top right.
    """
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.ticker import FixedLocator, LogLocator, NullFormatter

    groups = [(title, [r for r in group if r.cost_per_step and not r.reference])
              for title, group in rows(b, results, labels, hidden, prices, trials, only)]
    groups = [(title, models) for title, models in groups if models]
    if not groups:
        raise ValueError(f"no priced results for benchmark {b.name}")
    points = [r for _, models in groups for r in models]
    costs = [r.cost_per_step * 1000 for r in points]
    lowest = min(min(r.score for r in points), 0.05)

    plt.rcParams.update({"font.size": 9, "font.family": "sans-serif"})
    columns = 2
    panels = (len(groups) + columns - 1) // columns
    fig, axes = plt.subplots(panels, columns, figsize=(9, 3.8 * panels + TITLE_SPACE), facecolor=SURFACE,
                             sharex=True, sharey=True, squeeze=False)
    top = titled(fig, f"BeelineBench {title_name(b, trials)}: Efficient Frontier for Score vs. Cost",
                 "The score of each model against its cost per 1,000 steps, by problem. "
                 "Upper right is better.")
    cells = list(axes.flat)
    names = sorted({r.label for r in points})
    marks = {name: MODEL_MARKS[n % len(MODEL_MARKS)] for n, name in enumerate(names)}
    for ax, (title, models) in zip(cells, groups):
        ax.set_facecolor(SURFACE)
        ax.set_xscale("log")
        ax.set_yscale("log")
        ax.set_title(title, loc="left", fontsize=10.5, fontweight="bold", color=TEXT)
        ax.grid(which="major", color=GRID, linewidth=0.8)
        ax.grid(which="minor", color=MINOR_GRID, linewidth=0.5)
        ax.set_axisbelow(True)
        edge = convex_frontier(models)
        # From the top edge down to the model with the best score, along the frontier to
        # the cheapest model, then out to the edge of worse scores.
        frontier_x = ([edge[0].score] + [r.score for r in edge] + [lowest / 1.3])
        # The frontier ends at the cheapest model: the legend band below it stays empty.
        frontier_y = ([max(costs) * 1.6] + [r.cost_per_step * 1000 for r in edge]
                      + [edge[-1].cost_per_step * 1000])
        ax.plot(frontier_x, frontier_y, color=MARK, linewidth=1.4, zorder=2)
        for r in sorted(models, key=lambda r: r.score, reverse=True):
            # A star draws smaller than the other shapes at one size, so it is larger.
            size = 10 if marks[r.label] == "*" else 7
            ax.plot(r.score, r.cost_per_step * 1000, linestyle="none", marker=marks[r.label],
                    markersize=size, zorder=3, color=MARK,
                    markeredgecolor=SURFACE, markeredgewidth=1.0,
                    label=f"{r.label}{r.marks}")
        # Each panel has its own legend, of the models in that panel.
        ax.legend(loc="upper right", ncol=2, fontsize=7, columnspacing=1.0, frameon=True, framealpha=0.92, facecolor=SURFACE,
                  edgecolor=GRID, handletextpad=0.4, borderpad=0.5, labelcolor=TEXT)
        for side in ("top", "right"):
            ax.spines[side].set_visible(False)
        for side in ("left", "bottom"):
            ax.spines[side].set_color(GRID)
        ax.tick_params(colors=MUTED, length=0)
    for ax in cells[len(groups):]:
        ax.axis("off")
    first = cells[0]
    # The score grows to the right, and the cost axis is reversed: cheaper is higher. So the
    # best models are at the top right.
    first.set_xlim(lowest / 1.3, 1.0)
    # Nothing is cheaper than the cheapest model, so the band above it is empty in each
    # panel. Make the band tall enough for the legend, which goes there.
    rows_most = math.ceil(max(len(models) for _, models in groups) / 2)  # two columns
    band = min(0.45, 0.07 * rows_most + 0.06)  # the part of the panel's height for the legend
    span = math.log10(max(costs) * 1.6) - math.log10(min(costs))
    first.set_ylim(max(costs) * 1.6, min(costs) / 10 ** (span * band / (1 - band)))
    first.xaxis.set_major_locator(FixedLocator([t for t in TICKS if t >= lowest / 1.3]))
    # Minor gridlines at 2, 3, ... 9 times each power of ten, on both axes.
    first.xaxis.set_minor_locator(LogLocator(subs=range(2, 10)))
    first.yaxis.set_minor_locator(LogLocator(subs=range(2, 10)))
    first.xaxis.set_minor_formatter(NullFormatter())
    first.yaxis.set_minor_formatter(NullFormatter())
    first.xaxis.set_major_formatter(lambda value, _: f"{value:g}")
    first.yaxis.set_major_formatter(lambda value, _: f"${value:g}")
    # The panels share their limits and scales, and each panel shows its own axes.
    for ax in cells[:len(groups)]:
        ax.set_ylabel("US dollars for 1,000 steps (log scale, reversed)", color=MUTED)
        ax.set_xlabel("score (log scale)", color=MUTED)
        ax.tick_params(labelbottom=True, labelleft=True)

    notes = ("A mark is a model: its score, the geometric mean over its trials, and the cost of "
             "one step, the mean tokens of a request\nat the model's list price. Each model has "
             "the same mark in each panel.")
    if any("*" in row.marks for row in points):
        notes += (f" *: at least one run did not solve within {b.max_expansions:,} nodes, so the "
                  "true score is lower.")
    fig.tight_layout(rect=(0, 0.035, 1, top))
    fig.text(0.01, 0.006, notes, color=MUTED, fontsize=8, va="bottom")
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=200, facecolor=SURFACE, metadata={
        FINGERPRINT_KEY: fingerprint(b, results, labels, hidden, prices, kind="frontier",
                                     trials=trials, only=only)})
    plt.close(fig)


def case_study_rows(study, results: Path, b: Benchmark) -> list[tuple[str, list[Row]]]:
    """The rows of the case study figure: the representations, then the option orders."""
    from .case_study import lines, summary

    heuristic = b.domains[study.domain]["heuristic"]
    groups = []
    for title, found in lines(study, results, b.name, heuristic):
        out = []
        for line in found:
            score, low, high = summary(line, (study.chooser, study.domain, title, line.label))
            label = (f"Heuristic: {HEURISTIC_TITLES.get(heuristic, heuristic)}"
                     if line.label == "Heuristic" else line.label)
            out.append(Row(label, score, low, high, len(line.scores), "",
                           reference=line.reference, marker=line.marker))
        groups.append((title, out))
    return groups


def case_study_fingerprint(study, results: Path, b: Benchmark, model: str) -> str:
    groups = [[title, [[round(v, 6) if isinstance(v, float) else v for v in astuple(row)]
                       for row in group]] for title, group in case_study_rows(study, results, b)]
    data = json.dumps([STYLE, "case-study", b.name, model, groups], sort_keys=True)
    return hashlib.sha256(data.encode()).hexdigest()[:16]


def draw_case_study(study, results: Path, out: Path, b: Benchmark, model: str) -> None:
    """The score of one model on one problem, for each representation and option order."""
    from .domains import TITLES

    groups = case_study_rows(study, results, b)
    if not groups:
        raise ValueError("no case study results")
    problem = TITLES.get(study.domain, study.domain)
    notes = (f"Benchmark {b.name}, {problem}, trials 1 to {study.trials}. A mark is the geometric "
             "mean over n trials, and a band is its 95% bootstrap interval.\nEach representation "
             "uses the random option order of the benchmark, and each option order uses the "
             "first representation.\nThe heuristic and random choice are the same in each group.")
    forest(groups, out, title=f"Case study: {model} on {problem}",
           subtitle="How the text of the states and the order of the options change the score. "
                    "Higher is better, and 1.0 is a perfect search.",
           xlabel="score = (shortest path + 1) / nodes explored   ·   log scale, higher is "
                  "better", notes=notes, log=True,
           stamp=case_study_fingerprint(study, results, b, model))
