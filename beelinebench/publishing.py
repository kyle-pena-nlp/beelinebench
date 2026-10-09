"""The pages of the official benchmarks, and the check that CI runs on them.

Each official benchmark of ``benchmarks.toml`` has a page,
``docs/benchmarks/<name>.md``, and the index ``docs/benchmarks/README.md`` links
to it. :func:`problems` lists what is missing. :func:`publish` writes the page of
a benchmark from its definition, and writes the index again. It never writes over a
page that exists.

:func:`index` makes the index from ``benchmarks.toml``: a table of the versions, and
the two figures of each version. ``python -m beelinebench readme`` writes it, and
``readme --check`` fails when it is out of date.
"""

from __future__ import annotations

from pathlib import Path

from .benchmark import Benchmark

INDEX = "README.md"

INDEX_HEADER = ("<!-- Made by `python -m beelinebench readme` from benchmarks.toml. "
                "Do not edit. -->\n")


def page_name(name: str) -> str:
    return f"{name}.md"


#: The results part of a page sits between these lines. ``readme`` writes it again.
RESULTS_START = ("<!-- Results: made by `python -m beelinebench readme`. Do not edit between "
                 "these lines. -->")
RESULTS_END = "<!-- End of results. -->"


def with_results(page_text: str, section: str) -> str:
    """``page_text`` with ``section`` as its results part.

    The part between the markers is replaced. A page without the markers gets them in
    place of its ``## Results`` section, or at its end.
    """
    block = f"{RESULTS_START}\n\n{section.rstrip()}\n\n{RESULTS_END}\n"
    if RESULTS_START in page_text and RESULTS_END in page_text:
        head, rest = page_text.split(RESULTS_START, 1)
        tail = rest.split(RESULTS_END, 1)[1].lstrip("\n")
        return head + block + ("\n" + tail if tail else "")
    if "\n## Results\n" in page_text:
        head = page_text.split("\n## Results\n", 1)[0]
        return head.rstrip("\n") + "\n\n" + block
    return page_text.rstrip("\n") + "\n\n" + block


def index(officials: dict[str, Benchmark]) -> str:
    """The index of all official benchmarks, newest first, with their figures."""
    newest = list(officials)[::-1]
    rows = "\n".join(
        f"| [{name}]({page_name(name)}) | {len(b.domains)} | {b.trials} | "
        f"{b.max_expansions:,} | {b.max_frontier} |"
        for name, b in ((n, officials[n]) for n in newest))
    scores = "\n\n".join(
        f"### Benchmark {name}\n\n![The scores of each model and heuristic in benchmark "
        f"{name}, by domain, with 95% intervals]({name}.png)" for name in newest)
    choices = "\n\n".join(
        f"### Benchmark {name}\n\n![The share of decisions that matched the oracle for each model "
        f"and heuristic in benchmark {name}, by domain, with 95% intervals]({name}-choices.png)"
        for name in newest)
    frontiers = "\n\n".join(
        f"### Benchmark {name}\n\n![The score against the cost of a step for each model in "
        f"benchmark {name}, by domain, with the efficient frontier]({name}-frontier.png)"
        for name in newest)
    return f"""{INDEX_HEADER}# The benchmarks

Each official benchmark of `benchmarks.toml` has a page here. A new version adds a
page, and no page is removed. CI fails when a benchmark has no page, or when this
file is out of date.

| benchmark | domains | trials for each domain | node limit | frontier limit |
|---|---|---|---|---|
{rows}

## Scores

{scores}

## Score and cost

{frontiers}

## Choices against the oracle

{choices}
"""


#: The folder of the mini benchmark in ``docs/benchmarks``: its index and figures.
MINI = "mini"


def mini_index(officials: dict[str, Benchmark], trials: int, models: list[str],
               sections: dict[str, str]) -> str:
    """The index of the mini results: for each version, newest first, its results part.

    ``models`` are the names of the mini choosers for a reader, and ``sections`` the
    results part of each version, from ``readme.results_section``.
    """
    parts = "\n\n".join(sections[name].replace("## Results", f"## Benchmark {name} mini", 1)
                          .rstrip() for name in list(officials)[::-1] if name in sections)
    return f"""{INDEX_HEADER}# The mini benchmarks

The mini benchmark of a version is its first {trials} trials of each domain, with
{", ".join(models)}. These models come from one provider, so a run needs one key.
`uv run python -m beelinebench run --mini` runs it. Trial n is the same trial as in the
full benchmark, so a mini score is the full score of fewer trials, with wider intervals.
[The benchmarks](../{INDEX}) has the full results.

{parts}
"""


def problems(officials: dict[str, Benchmark], docs: Path) -> list[str]:
    """What the pages of ``officials`` lack. An empty list means that all is in place."""
    index = docs / INDEX
    if not index.exists():
        return [f"{index} does not exist"]
    text = index.read_text()
    out = []
    for name in officials:
        if not (docs / page_name(name)).exists():
            out.append(f"{docs / page_name(name)} does not exist")
        if f"]({page_name(name)})" not in text:
            out.append(f"{index} has no link to {page_name(name)}")
    return out


def page(b: Benchmark) -> str:
    """The first text of the page of ``b``, made from its definition."""
    rows = "\n".join(
        f"| `{domain}` | `{settings['heuristic']}` | "
        + ", ".join(f"`{k} = {v}`" for k, v in settings.items() if k != "heuristic")
        + " |"
        for domain, settings in b.domains.items())
    return f"""# Benchmark {b.name}

## Definition

The table `[benchmark."{b.name}"]` of `benchmarks.toml` is the definition. This
page shows it.

| rule | value |
|---|---|
| trials | {b.trials} for each domain |
| `max_expansions` | both arms stop after {b.max_expansions:,} explorations, solved or not |
| `max_frontier` | {b.max_frontier} states |

| domain | heuristic | settings |
|---|---|---|
{rows}

## What changed

Write what this version changes, and why.

{RESULTS_START}

## Results

No results yet. Run it with:

```bash
uv run python -m beelinebench run --benchmark {b.name}
uv run python -m beelinebench readme
```

{RESULTS_END}
"""


def publish(b: Benchmark, docs: Path, officials: dict[str, Benchmark]) -> list[Path]:
    """Write the page of ``b`` where it is missing, and the index of ``officials``."""
    written = []
    docs.mkdir(parents=True, exist_ok=True)
    target = docs / page_name(b.name)
    if not target.exists():
        target.write_text(page(b))
        written.append(target)
    target, text = docs / INDEX, index(officials)
    if not target.exists() or target.read_text() != text:
        target.write_text(text)
        written.append(target)
    return written
