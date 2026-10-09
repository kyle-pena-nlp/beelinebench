"""The pages of the official benchmarks, and the check that CI runs on them.

Each official benchmark of ``benchmarks.toml`` has a page,
``docs/benchmarks/<name>.md``, and the index ``docs/benchmarks/README.md`` links
to it. :func:`problems` lists what is missing. :func:`publish` writes the page of
a benchmark from its definition, and adds the link to the index. It never writes
over a page that exists.
"""

from __future__ import annotations

from pathlib import Path

from .benchmark import Benchmark

INDEX = "README.md"

INDEX_TEXT = """# The benchmarks

Each official benchmark of `benchmarks.toml` has a page here. A new version adds
a page, and no page is removed. CI fails when a benchmark has no page, or when
this list has no link to it.

"""


def page_name(name: str) -> str:
    return f"{name}.md"


def link(name: str) -> str:
    return f"- [Benchmark {name}]({page_name(name)})"


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

## Results

No results yet. Run it with:

```bash
uv run python -m beelinebench run --benchmark {b.name}
uv run python -m beelinebench report
```
"""


def publish(b: Benchmark, docs: Path) -> list[Path]:
    """Write the page of ``b`` and its link in the index, where they are missing."""
    written = []
    docs.mkdir(parents=True, exist_ok=True)
    target = docs / page_name(b.name)
    if not target.exists():
        target.write_text(page(b))
        written.append(target)
    index = docs / INDEX
    text = index.read_text() if index.exists() else INDEX_TEXT
    if f"]({page_name(b.name)})" not in text:
        index.write_text((text if text.endswith("\n") else text + "\n") + link(b.name) + "\n")
        written.append(index)
    return written
