"""The root ``README.md``, made from ``README.template.md`` and the results.

The template holds placeholders such as ``{{ results }}``. :func:`render` puts
the current values in their place. ``python -m beelinebench readme`` writes the
result to ``README.md``, and ``python -m beelinebench readme --check`` fails when the
committed ``README.md`` is not what the template and the results make. CI runs
the check.

``{{ results_figure }}`` puts in the figure of :mod:`beelinebench.plot`, as an
image. ``readme`` draws each figure that the template uses, and ``readme --check``
fails when a figure does not show the current results.

A placeholder is ``{{ name }}`` or ``{{ name argument }}``. An unknown name is an
error, so a typo cannot reach the README. ``\\{{`` is a literal ``{{``.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Collection, Mapping
from pathlib import Path
from typing import TYPE_CHECKING

from .benchmark import Benchmark
from .rng import Draws
from .run import read, summarise

if TYPE_CHECKING:
    from .config import ChooserConfig

TEMPLATE = "README.template.md"
OUTPUT = "README.md"

HEADER = ("<!-- Made by `python -m beelinebench readme` from README.template.md. "
          "Edit the template, then run the command. -->\n\n")

#: The figure of a benchmark, from the project root.
FIGURE = "docs/benchmarks/{}.png"

PLACEHOLDER = re.compile(r"(?<!\\)\{\{\s*([a-z_]+)(?:\s+([^\s}]+))?\s*\}\}")


def results_table(b: Benchmark, results: Path, hidden: Collection[str] = ()) -> str:
    """A table of the score of each chooser and domain of official benchmark ``b``.

    A score is marked ``*`` when a model run hit ``max_expansions`` unsolved, and a
    heuristic score ``†`` when a heuristic run did. A footnote under the table
    counts those runs.
    """
    rows, model_notes, heuristic_notes = [], [], []
    for chooser_dir in sorted(p for p in (results / b.name).glob("*")
                              if p.is_dir() and p.name not in hidden):
        for domain, settings in b.domains.items():
            heuristic = settings["heuristic"]
            path = chooser_dir / f"{domain}.{heuristic}.jsonl"
            records = read(path)
            if not records:
                continue
            # The same draws as `report`, so the two show the same interval.
            s = summarise(records, draws=Draws("bootstrap", b.name, chooser_dir.name, path.stem))
            where = f"`{chooser_dir.name}` on `{domain}`"
            if s.censored:
                model_notes.append(f"{where}: {s.censored} of {s.instances}")
            if s.baseline_censored:
                heuristic_notes.append(f"{where}: {s.baseline_censored} of {s.instances}")
            rows.append("| " + " | ".join((
                f"`{chooser_dir.name}`", f"`{domain}`", f"`{heuristic}`",
                f"{len(records)} of {b.trials}",
                "—" if s.score is None else f"{s.score:.3f}{s.marks}",
                "—" if s.low is None else f"{s.low:.3f} to {s.high:.3f}",
                "—" if s.baseline_score is None else f"{s.baseline_score:.3f}{s.baseline_marks}",
                "—" if s.oracle_score is None else f"{s.oracle_score:.3f}",
                "—" if s.path_score is None else f"{s.path_score:.2f}",
                "—" if s.coverage is None
                else f"{s.instances - s.censored} of {s.instances}",
                s.refusal_rate,
                ", ".join(s.served_models) or "—",
                "—" if s.first_utc is None else s.first_utc[:10])) + " |")
    if not rows:
        return f"No results for benchmark {b.name} yet."
    limit = f"{b.max_expansions:,}"
    notes = [f"\\* Model runs that did not find a solution within {limit} explored nodes: "
             + "; ".join(model_notes) + "."] if model_notes else []
    notes += [f"† Heuristic runs that did not find a solution within {limit} explored nodes: "
              + "; ".join(heuristic_notes) + "."] if heuristic_notes else []
    return ("| chooser | domain | heuristic | trials | score | 95% interval | heuristic score "
            "| oracle score | path score | solved | refusals | served by | first run (UTC) |\n"
            "|---|---|---|---|---|---|---|---|---|---|---|---|---|\n" + "\n".join(rows)
            + "".join("\n\n" + note for note in notes))


def tokens_per_trial(path: Path) -> tuple[float, float, int] | None:
    """The mean input and output tokens of a trial in ``path``, and the number of trials."""
    records = read(path)
    if not records:
        return None
    return (sum(r.input_tokens for r in records) / len(records),
            sum(r.output_tokens for r in records) / len(records), len(records))


def costs_table(b: Benchmark, results: Path, choosers: Mapping[str, ChooserConfig]) -> str:
    """The estimated price of a full run of ``b`` for each chooser that has a price.

    A full run is ``b.trials`` trials of each domain. The estimate uses the mean
    tokens of a trial that the chooser used. For a domain without results of the
    chooser, it uses those of the chooser with the most trials in that domain and the
    same kind of prompt: a Claude model gets a longer prompt than a choice model.
    """
    def path(name: str, domain: str) -> Path:
        return results / b.name / name / f"{domain}.{b.domains[domain]['heuristic']}.jsonl"

    rows = []
    for c in choosers.values():
        if c.price_input is None or not c.publish:
            continue
        tokens_in = tokens_out = 0.0
        measured, borrowed = 0, set()
        for domain in b.domains:
            found = tokens_per_trial(path(c.name, domain))
            if found is None:
                peers = [(found[2], other.title, found) for other in choosers.values()
                         if (other.protocol == "anthropic") == (c.protocol == "anthropic")
                         and (found := tokens_per_trial(path(other.name, domain)))]
                if not peers:
                    tokens_in = None
                    break
                _, title, found = max(peers)
                borrowed.add(title)
            else:
                measured += found[2]
            tokens_in += found[0] * b.trials
            tokens_out += found[1] * b.trials
        if tokens_in is None:
            rows.append(f"| {c.title} | {price(c)} | — | — | no results to estimate from |")
            continue
        cost = tokens_in / 1e6 * c.price_input + tokens_out / 1e6 * (c.price_output or 0)
        basis = []
        if measured:
            basis.append(f"measured on {measured:,} trials")
        if borrowed:
            basis.append("token counts of " + ", ".join(sorted(borrowed)))
        rows.append(f"| {c.title} | {price(c)} | {amount(tokens_in)} | "
                    f"${cost:,.2f} | {'; '.join(basis)} |")
    if not rows:
        return "No chooser has a price."
    return ("| model | price for a million tokens | input tokens of a full run | estimated price "
            "of a full run | basis |\n|---|---|---|---|---|\n" + "\n".join(rows))


def amount(tokens: float) -> str:
    return f"{tokens / 1e6:,.0f} million" if tokens >= 1e6 else f"{tokens / 1e3:,.0f} thousand"


def dollars(value: float) -> str:
    """At least two decimals, and three for a price such as $0.042."""
    text = f"{value:.3f}"
    return "$" + (text[:-1] if text.endswith("0") else text)


def price(c: ChooserConfig) -> str:
    out = f"{dollars(c.price_output)} output" if c.price_output else "output free"
    return f"{dollars(c.price_input)} input, {out}"


def placeholders(officials: dict[str, Benchmark], results: Path,
                 choosers: Mapping[str, ChooserConfig] | None = None
                 ) -> dict[str, Callable[[str | None], str]]:
    """Each placeholder name, and the function that gives its text."""
    latest = list(officials)[-1]
    hidden = {c.name for c in (choosers or {}).values() if not c.publish}

    def official(argument: str | None) -> Benchmark:
        name = argument or latest
        if name not in officials:
            raise ValueError(f"no official benchmark {name!r}")
        return officials[name]

    return {
        "latest_benchmark": lambda argument: latest,
        "results": lambda argument: results_table(official(argument), results, hidden),
        "results_figure": lambda argument: (
            f"![The scores of each model and heuristic in benchmark {official(argument).name}, "
            f"by domain, with 95% intervals]({FIGURE.format(official(argument).name)})"),
        "trials": lambda argument: str(official(argument).trials),
        "max_expansions": lambda argument: f"{official(argument).max_expansions:,}",
        "domain_count": lambda argument: str(len(official(argument).domains)),
        "costs": lambda argument: costs_table(official(argument), results, choosers or {}),
    }


def figures(template: str, officials: dict[str, Benchmark]) -> list[str]:
    """The benchmarks whose figure the template shows."""
    latest = list(officials)[-1]
    return sorted({match.group(2) or latest for match in PLACEHOLDER.finditer(template)
                   if match.group(1) == "results_figure"})


def render(template: str, officials: dict[str, Benchmark], results: Path,
           choosers: Mapping[str, ChooserConfig] | None = None) -> str:
    known = placeholders(officials, results, choosers)

    def replace(match: re.Match[str]) -> str:
        name, argument = match.group(1), match.group(2)
        if name not in known:
            raise ValueError(f"unknown placeholder {match.group(0)!r}. "
                             f"Known: {', '.join(known)}")
        return known[name](argument)

    return HEADER + PLACEHOLDER.sub(replace, template).replace("\\{{", "{{")
