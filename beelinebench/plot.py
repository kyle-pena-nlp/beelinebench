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
STYLE = 21

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
         hidden: Collection[str] = (), prices: Prices = {}) -> list[tuple[str, list[Row]]]:
    """For each domain of ``b`` with results: a row for the heuristic and for each chooser, best first.

    ``labels`` gives the name of a chooser for a reader. A chooser without one
    keeps its own name. The choosers in ``hidden`` are left out.
    """
    choosers = sorted(p.name for p in (results / b.name).glob("*")
                      if p.is_dir() and p.name not in hidden)
    groups = []
    for domain, settings in b.domains.items():
        heuristic = settings["heuristic"]
        stem = f"{domain}.{heuristic}"
        found, classic = [], {}
        for name in choosers:
            records = [r for r in read(results / b.name / name / f"{stem}.jsonl")
                       if r.score is not None]
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


def score_text(score: float) -> str:
    """Two decimals, or two significant digits for a score below 0.01, for example 0.0041."""
    return f"{score:.2f}" if score >= 0.01 else f"{score:.2g}"


def fingerprint(b: Benchmark, results: Path, labels: Mapping[str, str] = {},
                hidden: Collection[str] = (), prices: Prices = {}, kind: str = "scores") -> str:
    """A hash of everything the figure of ``b`` shows: its rows, and the limit in its notes."""
    groups = [[title, [[round(v, 6) if isinstance(v, float) else v for v in astuple(row)]
                       for row in group]] for title, group in rows(b, results, labels, hidden, prices)]
    data = json.dumps([STYLE, kind, b.name, b.max_expansions, groups], sort_keys=True)
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
               hidden: Collection[str] = (), prices: Prices = {}, kind: str = "scores") -> bool:
    """Whether ``png`` shows the current results of ``b``."""
    return stored_fingerprint(png) == fingerprint(b, results, labels, hidden, prices, kind)


def draw(b: Benchmark, results: Path, out: Path, labels: Mapping[str, str] = {},
         hidden: Collection[str] = ()) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.ticker import FixedLocator, NullLocator

    groups = rows(b, results, labels, hidden)
    if not groups:
        raise ValueError(f"no results for benchmark {b.name}")
    # Top to bottom: a header line for each domain, its rows, then a gap.
    placed: list[tuple[float, Row]] = []
    headers: list[tuple[float, str]] = []
    y = 0.0
    for title, group in groups:
        headers.append((y, title))
        y += 1
        for row in group:
            placed.append((y, row))
            y += 1
        y += 0.6
    height = y - 0.6

    plt.rcParams.update({"font.size": 10, "font.family": "sans-serif"})
    fig, ax = plt.subplots(figsize=(8.5, 0.27 * height + 1.3), facecolor=SURFACE)
    ax.set_facecolor(SURFACE)
    ax.set_xscale("log")
    lowest = min(row.low for _, row in placed)
    ax.set_xlim(lowest / 1.3, 2.0)
    ax.set_ylim(height - 0.3, -0.7)

    ax.xaxis.set_major_locator(FixedLocator([t for t in TICKS if t >= lowest / 1.3]))
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
        ax.text(row.high * 1.07, y, f"{score_text(row.score)}{row.marks}", color=TEXT, fontsize=9,
                va="center", bbox=dict(boxstyle="square,pad=0.1", facecolor=SURFACE,
                                       edgecolor="none"))

    ax.set_yticks([y for y, _ in placed],
                  [f"{row.label}  ·  n={row.trials}" for _, row in placed], color=TEXT)
    for y, title in headers:
        ax.text(-0.02, y, title, transform=ax.get_yaxis_transform(), ha="right", va="center",
                fontsize=10.5, fontweight="bold", color=TEXT)
    ax.tick_params(axis="y", length=0, pad=8)
    ax.tick_params(axis="x", colors=MUTED, length=0)
    for side in ("top", "right", "left"):
        ax.spines[side].set_visible(False)
    ax.spines["bottom"].set_color(GRID)

    ax.set_xlabel("score = (shortest path + 1) / nodes explored   ·   log scale, higher is "
                  "better", color=MUTED, fontsize=9)
    notes = (f"Benchmark {b.name}. A mark is the geometric mean over n trials, and a band "
             "is its 95% bootstrap interval.\nAn open circle is random choice: a state of the "
             "frontier at random. The vertical line at 1.0 is a perfect search.")
    marks = {mark for _, row in placed for mark in row.marks}
    if "*" in marks or "†" in marks:
        notes += (f"\n* or †: at least one model (*) or heuristic (†) run did not solve within "
                  f"{b.max_expansions:,} nodes, so the true score is lower.")
    fig.tight_layout(rect=(0, 0.02 + 0.016 * (notes.count("\n") + 1), 1, 1))
    fig.text(0.01, 0.008, notes, color=MUTED, fontsize=8, va="bottom")
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=200, facecolor=SURFACE,
                metadata={FINGERPRINT_KEY: fingerprint(b, results, labels, hidden)})
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
MODEL_MARKS = ("D", "o", "s", "^", "v", "P", "X", "h", "<", ">", "*", "p")


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
                  hidden: Collection[str] = (), prices: Prices = {}) -> None:
    """The cost of a step against the score, one panel for each domain, with the frontier.

    A step is one request: the model chooses one state of the frontier. The cost is
    the mean tokens of a request at the model's list price. A low cost and a high
    score are better. The score axis is reversed, so the best models are at the bottom
    left, and the frontier falls from the top left to the bottom right.
    """
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.ticker import FixedLocator, LogLocator, NullFormatter

    groups = [(title, [r for r in group if r.cost_per_step and not r.reference])
              for title, group in rows(b, results, labels, hidden, prices)]
    groups = [(title, models) for title, models in groups if models]
    if not groups:
        raise ValueError(f"no priced results for benchmark {b.name}")
    points = [r for _, models in groups for r in models]
    costs = [r.cost_per_step * 1000 for r in points]
    lowest = min(min(r.score for r in points), 0.05)

    plt.rcParams.update({"font.size": 9, "font.family": "sans-serif"})
    columns = 2
    panels = (len(groups) + columns - 1) // columns
    fig, axes = plt.subplots(panels, columns, figsize=(9, 3.8 * panels), facecolor=SURFACE,
                             sharex=True, sharey=True, squeeze=False)
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
            ax.plot(r.score, r.cost_per_step * 1000, linestyle="none", marker=marks[r.label],
                    markersize=7, zorder=3, color=MARK,
                    markeredgecolor=SURFACE, markeredgewidth=1.0,
                    label=f"{r.label}{r.marks}")
        # Each panel has its own legend, of the models in that panel.
        ax.legend(loc="lower left", ncol=2, fontsize=7, columnspacing=1.0, frameon=True, framealpha=0.92, facecolor=SURFACE,
                  edgecolor=GRID, handletextpad=0.4, borderpad=0.5, labelcolor=TEXT)
        for side in ("top", "right"):
            ax.spines[side].set_visible(False)
        for side in ("left", "bottom"):
            ax.spines[side].set_color(GRID)
        ax.tick_params(colors=MUTED, length=0)
    for ax in cells[len(groups):]:
        ax.axis("off")
    first = cells[0]
    # The score axis runs from 1.0 down, so the frontier falls from the accurate and
    # expensive models at the top left to the cheap ones at the bottom right.
    first.set_xlim(1.0, lowest / 1.3)
    # Nothing is cheaper than the cheapest model, so the band below it is empty in each
    # panel. Make the band tall enough for the legend, which goes there.
    rows_most = math.ceil(max(len(models) for _, models in groups) / 2)  # two columns
    band = min(0.45, 0.07 * rows_most + 0.06)  # the part of the panel's height for the legend
    span = math.log10(max(costs) * 1.6) - math.log10(min(costs))
    first.set_ylim(min(costs) / 10 ** (span * band / (1 - band)), max(costs) * 1.6)
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
        ax.set_ylabel("US dollars for 1,000 steps (log scale)", color=MUTED)
        ax.set_xlabel("score (log scale, reversed)", color=MUTED)
        ax.tick_params(labelbottom=True, labelleft=True)

    notes = ("A mark is a model: its score, the geometric mean over its trials, and the cost of "
             "one step, the mean tokens of a request\nat the model's list price. Each model has "
             "the same mark in each panel.")
    if any("*" in row.marks for row in points):
        notes += (f" *: at least one run did not solve within {b.max_expansions:,} nodes, so the "
                  "true score is lower.")
    fig.tight_layout(rect=(0, 0.035, 1, 1))
    fig.text(0.01, 0.006, notes, color=MUTED, fontsize=8, va="bottom")
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=200, facecolor=SURFACE, metadata={
        FINGERPRINT_KEY: fingerprint(b, results, labels, hidden, prices, kind="frontier")})
    plt.close(fig)
