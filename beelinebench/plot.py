"""A forest plot of the scores of an official benchmark.

Each domain is a group of rows, and each row is a chooser: its score (the
geometric mean over its trials) and the 95% bootstrap interval. The first row of
a group is the classic heuristic on the same trials, for reference, drawn with an
open diamond. The x axis is logarithmic, because a score is a ratio and the mean
is geometric. The line at 1.0 is a perfect search.

``python -m beelinebench plot`` writes the figure. It needs matplotlib: ``uv sync
--extra plot``. ``python -m beelinebench readme`` also writes it, for the README.

The PNG holds a fingerprint of the rows that it shows. :func:`is_current` compares
that fingerprint with the rows of the current results, so CI can find an old figure
without matplotlib.
"""

from __future__ import annotations

import hashlib
import json
import struct
import zlib
from collections.abc import Collection, Mapping
from dataclasses import astuple, dataclass
from pathlib import Path

from .benchmark import Benchmark
from .domains import HEURISTIC_TITLES, TITLES
from .rng import Draws
from .run import geometric_mean, interval, read

#: One colour for every mark, so position alone carries the comparison.
MARK = "#3c5a46"
BAND = "#c5ccc7"
SURFACE = "#ffffff"
TEXT = "#2b2b2b"
MUTED = "#6b6b6b"
GRID = "#ebebeb"
CENTRE = "#5a5a5a"

TICKS = (0.01, 0.02, 0.05, 0.1, 0.2, 0.5, 1.0)

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
    #: The classic heuristic, which is drawn as an open diamond.
    reference: bool = False


def rows(b: Benchmark, results: Path, labels: Mapping[str, str] = {},
         hidden: Collection[str] = ()) -> list[tuple[str, list[Row]]]:
    """For each domain of ``b`` with results: the heuristic row, then a row for each chooser.

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
                classic[r.trial] = r
            scores = [r.score for r in records]
            # The same draws as `report` and the README, so all show the same interval.
            low, high = interval(scores, Draws("bootstrap", b.name, name, stem))
            found.append(Row(labels.get(name, name), geometric_mean(scores), low, high,
                             len(records), "*" if any(r.censored for r in records) else ""))
        if not found:
            continue
        scores = [classic[trial].baseline_score for trial in sorted(classic)]
        low, high = interval(scores, Draws("bootstrap", b.name, "heuristic", stem))
        reference = Row(f"Heuristic: {HEURISTIC_TITLES.get(heuristic, heuristic)}",
                        geometric_mean(scores), low, high, len(scores),
                        "†" if any(not r.baseline_solved for r in classic.values()) else "",
                        reference=True)
        groups.append((TITLES.get(domain, domain), [reference, *found]))
    return groups


def fingerprint(b: Benchmark, results: Path, labels: Mapping[str, str] = {},
                hidden: Collection[str] = ()) -> str:
    """A hash of everything the figure of ``b`` shows: its rows, and the limit in its notes."""
    groups = [[title, [[round(v, 6) if isinstance(v, float) else v for v in astuple(row)]
                       for row in group]] for title, group in rows(b, results, labels, hidden)]
    data = json.dumps([b.name, b.max_expansions, groups], sort_keys=True)
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
               hidden: Collection[str] = ()) -> bool:
    """Whether ``png`` shows the current results of ``b``."""
    return stored_fingerprint(png) == fingerprint(b, results, labels, hidden)


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
        ax.plot(row.score, y, marker="D", markersize=7, markeredgewidth=1.5,
                color=SURFACE if row.reference else MARK, markeredgecolor=MARK)
        # A surface box keeps the label legible where it crosses the line at 1.0.
        ax.text(row.high * 1.07, y, f"{row.score:.2f}{row.marks}", color=TEXT, fontsize=9,
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
    notes = (f"Benchmark {b.name}. A diamond is the geometric mean over n trials, and a band "
             "is its 95% bootstrap interval. An open diamond is the heuristic.\nThe vertical line at 1.0 is "
             "a perfect search, which explores only the states of a shortest path.")
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
