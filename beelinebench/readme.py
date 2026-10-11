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
from .case_study import STUDIES
from .run import geometric_mean, read, summarise

if TYPE_CHECKING:
    from .config import ChooserConfig

TEMPLATE = "README.template.md"
OUTPUT = "README.md"
#: Each page that ``readme`` makes: the template, and the page that it writes. The links
#: and image paths of the placeholders are from the project root, so a page in ``docs/``
#: uses no figure placeholder.
PAGES = ((TEMPLATE, OUTPUT), ("docs/model-quirks.template.md", "docs/model-quirks.md"),
         ("docs/costs.template.md", "docs/costs.md"), ("docs/usage.template.md", "docs/usage.md"),
         *((f"docs/benchmarks/{kind}.template.md", f"docs/benchmarks/{{latest}}-{kind}.md")
           for kind in ("representation-sensitivity", "order-sensitivity", "repeatability")),
         ("CONTRIBUTING.template.md", "CONTRIBUTING.md"))

HEADER = ("<!-- Made by `python -m beelinebench readme` from {}. "
          "Edit the template, then run the command. -->\n\n")

#: The figure of a benchmark, from the project root.
FIGURE = "docs/benchmarks/{}.png"
#: For each figure placeholder, the path of its image, from the project root.
FIGURES = {"results_figure": FIGURE, "frontier_figure": "docs/benchmarks/{}-frontier.png",
           "choices_figure": "docs/benchmarks/{}-choices.png"}

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


def leaderboard(b: Benchmark, results: Path, labels: Mapping[str, str] = {},
                hidden: Collection[str] = ()) -> str:
    """A compact table of ``b``: one row for each model, with its score on each domain.

    The overall score is the geometric mean of the domain scores, so a domain where all
    scores are low counts as much as a domain where all scores are high. Only a model with
    results on every domain gets one. The best model score of each column is bold, as
    rounded. The heuristic and random choice follow the models, in italics.
    """
    from .plot import rows, score_text

    groups = rows(b, results, labels, hidden)
    if not groups:
        return f"No results for benchmark {b.name} yet."
    titles = [title for title, _ in groups]
    table: dict[str, dict[str, object]] = {}
    for title, group in groups:
        for row in group:
            name = ("Heuristic" if row.marker == "D" else "Random choice") if row.reference \
                else row.label
            table.setdefault(name, {})[title] = row
    references = [name for name in ("Heuristic", "Random choice") if name in table]
    models = [name for name in table if name not in references]

    def overall(name: str) -> float | None:
        cells = table[name]
        return (geometric_mean([cells[t].score for t in titles])
                if all(t in cells for t in titles) else None)

    def beats(name: str) -> str:
        wins = sum(1 for t in titles if t in table[name] and "Heuristic" in table
                   and t in table["Heuristic"] and table[name][t].score > table["Heuristic"][t].score)
        return f"{wins} of {len(titles)}"

    # The best text, so that models that round to the same score are all bold.
    best = {t: score_text(max((table[m][t].score for m in models if t in table[m]), default=0))
            for t in titles}
    best["overall"] = score_text(max((s for m in models if (s := overall(m)) is not None),
                                     default=0))

    def cell(text: str, bold: bool, italic: bool) -> str:
        return f"**{text}**" if bold else f"*{text}*" if italic else text

    def line(name: str, italic: bool) -> str:
        cells = table[name]
        total = overall(name)
        marks = "".join(sorted({m for t in titles if t in cells for m in cells[t].marks}))
        out = [cell(name, False, italic),
               "—" if total is None else cell(score_text(total) + marks.replace("*", "\\*"),
                                              not italic and score_text(total) == best["overall"],
                                              italic)]
        for t in titles:
            row = cells.get(t)
            out.append("—" if row is None else cell(
                score_text(row.score) + row.marks.replace("*", "\\*"),
                not italic and score_text(row.score) == best[t], italic))
        out.append("" if italic else beats(name))
        return "| " + " | ".join(out) + " |"

    ranked = sorted(models, key=lambda m: -(overall(m) or 0))
    header = ("| model | overall | " + " | ".join(titles) + " | beats the heuristic |\n"
              "|---|---:|" + "---:|" * len(titles) + ":---:|")
    return "\n".join([header, *(line(m, False) for m in ranked),
                      *(line(r, True) for r in references)])


def tokens_per_trial(path: Path) -> tuple[float, float, int] | None:
    """The mean input and output tokens of a trial in ``path``, and the number of trials."""
    records = read(path)
    if not records:
        return None
    return (sum(r.input_tokens for r in records) / len(records),
            sum(r.output_tokens for r in records) / len(records), len(records))


def costs_table(b: Benchmark, results: Path, choosers: Mapping[str, ChooserConfig],
                trials: int | None = None, only: Collection[str] | None = None) -> str:
    """The estimated price of a full run of ``b`` for each chooser that has a price.

    A full run is ``b.trials`` trials of each domain. The estimate uses the mean
    tokens of a trial that the chooser used. For a domain without results of the
    chooser, it uses those of the chooser with the most trials in that domain and the
    same kind of prompt: a Claude model gets a longer prompt than a choice model.

    With ``trials`` and ``only``, it is a run of trials 1 to ``trials`` of those choosers:
    the mini benchmark. The token counts still come from all the trials of the results.
    """
    runs = trials or b.trials
    def path(name: str, domain: str) -> Path:
        return results / b.name / name / f"{domain}.{b.domains[domain]['heuristic']}.jsonl"

    rows, estimates = [], []
    for c in choosers.values():
        if c.price_input is None or not c.publish or (only is not None and c.name not in only):
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
            tokens_in += found[0] * runs
            tokens_out += found[1] * runs
        if tokens_in is None:
            rows.append(f"| {c.title} | {price(c)} | — | — | no results to estimate from |")
            continue
        cost = tokens_in / 1e6 * c.price_input + tokens_out / 1e6 * (c.price_output or 0)
        estimates.append(cost)
        basis = []
        if measured:
            basis.append(f"measured on {measured:,} trials")
        if borrowed:
            basis.append("token counts of " + ", ".join(sorted(borrowed)))
        rows.append(f"| {c.title} | {price(c)} | {amount(tokens_in)} | "
                    f"${cost:,.2f} | {'; '.join(basis)} |")
    if not rows:
        return "No chooser has a price."
    run = "a mini run" if trials else "a full run"
    total = ""
    if only is not None:
        total = f"\n\nAll the mini models together: about ${sum(estimates):,.2f}."
    return (f"| model | price for a million tokens | input tokens of {run} | estimated price "
            f"of {run} | basis |\n|---|---|---|---|---|\n" + "\n".join(rows) + total)


def amount(tokens: float) -> str:
    return f"{tokens / 1e6:,.0f} million" if tokens >= 1e6 else f"{tokens / 1e3:,.0f} thousand"


def dollars(value: float) -> str:
    """At least two decimals, and three for a price such as $0.042."""
    text = f"{value:.3f}"
    return "$" + (text[:-1] if text.endswith("0") else text)


def price(c: ChooserConfig) -> str:
    out = f"{dollars(c.price_output)} output" if c.price_output else "output free"
    return f"{dollars(c.price_input)} input, {out}"


#: The page and the figure of each sensitivity study of a benchmark, from the project root.
STUDY_PAGE = "docs/benchmarks/{}-{}.md"
STUDY_FIGURE = "docs/benchmarks/{}-{}.png"


def pages(officials: dict[str, Benchmark]) -> list[tuple[str, str]]:
    """:data:`PAGES`, with the newest benchmark version in the paths that name one."""
    latest = list(officials)[-1]
    return [(source, out.format(latest=latest)) for source, out in PAGES]


def study_table(officials: dict[str, Benchmark], results: Path, study, kind: str,
                labels: Mapping[str, str]) -> str:
    """The rows of the figure of study ``kind`` as tables, one for each model."""
    from .domains import TITLES
    from .plot import case_study_rows, score_text

    if study is None:
        return "The config has no sensitivity studies."
    groups = case_study_rows(study, results, officials[list(officials)[-1]], kind, labels)
    if not any(row.trials for _, group in groups for row in group if not row.reference):
        return "No results yet. Run `uv run python -m beelinebench case-study`."
    out = [f"The problem is {TITLES.get(study.domain, study.domain)}, trials 1 to "
           f"{study.trials}. The rows are in the order of the figure.\n"]
    for title, group in groups:
        lines = [f"#### {title}\n", "| | trials | score | 95% interval |", "|---|---|---|---|"]
        lines += [f"| {row.label} | {row.trials} | {score_text(row.score)} | "
                  f"{score_text(row.low)} to {score_text(row.high)} |" for row in group]
        out.append("\n".join(lines) + "\n")
    return "\n".join(out)


#: The page of a benchmark, from the project root.
PAGE = "docs/benchmarks/{}.md"
#: The hand-written commentary of a benchmark, from the project root, and the page that
#: ``readme`` makes from it. The commentary can hold placeholders. Its links are relative
#: to docs/benchmarks/, where the page is.
COMMENTARY = "docs/benchmarks/{}-commentary.template.md"
COMMENTARY_PAGE = "docs/benchmarks/{}-commentary.md"


def commentary_page(name: str, body: str) -> str:
    """The page of the commentary of benchmark ``name``."""
    return (HEADER.format(COMMENTARY.format(name)) + f"# Commentary: benchmark {name}\n\n"
            f"{body}\n\n[The page of benchmark {name}]({name}.md)\n")


def refusal_share(b: Benchmark, results: Path, argument: str, fallback: bool) -> str:
    """The share of refused requests, or of decisions that used the fallback.

    ``argument`` is ``<chooser>:<domain>``, for example ``luna:rush_hour``.
    """
    chooser, domain = argument.split(":")
    records = read(results / b.name / chooser / f"{domain}.{b.domains[domain]['heuristic']}.jsonl")
    requests = sum(r.requests for r in records)
    if not requests:
        return "—"
    refused = sum(r.refusals for r in records)
    if not fallback:
        return f"{100 * refused / requests:.0f}%"
    invalid = sum(r.invalid_answers for r in records)
    return f"{100 * invalid / (requests - (refused - invalid)):.0f}%"


def interval_text(row) -> str:
    from .plot import score_text
    return f"{score_text(row.low)} to {score_text(row.high)}"


def results_section(b: Benchmark, results: Path, labels: Mapping[str, str] = {},
                    hidden: Collection[str] = (), prices: Mapping = {},
                    trials: int | None = None, only: Collection[str] | None = None) -> str:
    """The results part of the page of ``b``: both figures, and their data as tables.

    The tables hold the rows of the figures, in the same order, so a reader without the
    images gets the same facts.
    """
    from .plot import convex_frontier, rows, score_text

    groups = rows(b, results, labels, hidden, prices, trials, only)
    if not groups:
        return ("## Results\n\nNo results yet. Run it with:\n\n```bash\n"
                f"uv run python -m beelinebench run --benchmark {b.name}\n"
                "uv run python -m beelinebench readme\n```\n")
    limit = f"{b.max_expansions:,}"
    out = [f"## Results\n\n![The scores of each model and heuristic in benchmark {b.name}, by "
           f"domain, with 95% intervals]({b.name}.png)\n\n### Scores as text\n\n"
           "The rows of each problem are in the order of the figure, best first. A score is the "
           "geometric mean over the trials, and the interval is its 95% bootstrap interval. "
           f"\\* or †: at least one model (\\*) or heuristic (†) run did not solve within "
           f"{limit} nodes, so the true score is lower.\n"]
    for title, group in groups:
        lines = [f"#### {title}\n", "| | trials | score | 95% interval |", "|---|---|---|---|"]
        lines += [f"| {row.label} | {row.trials} | {score_text(row.score)}"
                  f"{row.marks.replace('*', chr(92) + '*')} | {interval_text(row)} |"
                  for row in group]
        out.append("\n".join(lines) + "\n")
    priced = [(title, [r for r in group if r.cost_per_step and not r.reference])
              for title, group in groups]
    priced = [(title, models) for title, models in priced if models]
    if priced:
        out.append(f"![The score against the cost of a step for each model in benchmark "
                   f"{b.name}, by domain, with the efficient frontier]({b.name}-frontier.png)"
                   "\n\n### Score and cost as text\n\n"
                   "A step is one request. Its cost is the mean tokens of a request at the list "
                   "price of the model. A model on the frontier is on the line of the figure: no "
                   "other model, and no mix of two models, is both cheaper and better. The rows "
                   "are best score first.\n")
        for title, models in priced:
            efficient = {r.label for r in convex_frontier(models)}
            lines = [f"#### {title}\n",
                     "| model | score | US dollars for 1,000 steps | on the frontier |",
                     "|---|---|---|---|"]
            lines += [f"| {r.label} | {score_text(r.score)}{r.marks.replace('*', chr(92) + '*')} "
                      f"| {dollars_per_thousand(r.cost_per_step * 1000)} | "
                      f"{'yes' if r.label in efficient else ''} |"
                      for r in sorted(models, key=lambda r: -r.score)]
            out.append("\n".join(lines) + "\n")
    out.append(choices_section(b, results, labels, hidden, trials, only))
    return "\n".join(out)


def choices_section(b: Benchmark, results: Path, labels: Mapping[str, str] = {},
                    hidden: Collection[str] = (), trials: int | None = None,
                    only: Collection[str] | None = None) -> str:
    """The optimal choices figure of ``b``, and its data as tables."""
    from .plot import choice_rows

    groups = choice_rows(b, results, labels, hidden, trials, only)
    if not groups:
        return ""
    out = [f"![The percent of decisions that took a state on a shortest path, for each model and "
           f"heuristic in benchmark {b.name}, by domain, with 95% intervals]({b.name}-choices.png)"
           "\n\n### Optimal choices as text\n\n"
           "A state is optimal when it is on a shortest path: its moves from the start plus its "
           "moves to the goal equal the length of a shortest path. A decision counts when the "
           "frontier has an optimal state and a state that is not optimal. The percent is the "
           "mean over trials of the percent of the counted decisions that took an optimal state, "
           "so each trial counts the same.\n"]
    for title, group in groups:
        lines = [f"#### {title}\n", "| | trials | chose an optimal state | 95% interval |",
                 "|---|---|---|---|"]
        lines += [f"| {row.label} | {row.trials} | {100 * row.score:.0f}% | "
                  f"{100 * row.low:.0f}% to {100 * row.high:.0f}% |" for row in group]
        out.append("\n".join(lines) + "\n")
    return "\n".join(out)


def dollars_per_thousand(value: float) -> str:
    """Two significant digits, for example $0.042 or $1.3."""
    return f"${value:#.2g}" if value < 10 else f"${value:,.0f}"


def refusals_table(b: Benchmark, results: Path, chooser: str) -> str:
    """The refusals of ``chooser`` in ``b``, in all and for each domain.

    A decision is one choice of the search. A refused question is asked once more, so a
    decision with one refusal takes two requests. After a second refusal, the decision
    takes the fallback, and it counts as an invalid answer.
    """
    from .domains import TITLES

    lines, total_requests, total_refusals = [], 0, 0
    for domain, settings in b.domains.items():
        records = read(results / b.name / chooser / f"{domain}.{settings['heuristic']}.jsonl")
        requests = sum(r.requests for r in records)
        if not requests:
            continue
        refused = sum(r.refusals for r in records)
        fallback = sum(r.invalid_answers for r in records)
        decisions = requests - (refused - fallback)
        total_requests += requests
        total_refusals += refused
        trials = "" if len(records) == b.trials else f" ({len(records)} of {b.trials} trials)"
        lines.append(f"| {TITLES.get(domain, domain)}{trials} | {100 * refused / requests:.1f}% "
                     f"| {100 * fallback / decisions:.1f}% |")
    if not lines:
        return f"No results of `{chooser}` in benchmark {b.name} yet."
    return (f"In benchmark {b.name}, the API refused {total_refusals:,} of {total_requests:,} "
            f"requests ({100 * total_refusals / total_requests:.0f}%). The refusals are not "
            "equal in the domains:\n\n| domain | refused requests | decisions that used the "
            "fallback |\n|---|---|---|\n" + "\n".join(lines))


def placeholders(officials: dict[str, Benchmark], results: Path,
                 choosers: Mapping[str, ChooserConfig] | None = None, mini=None, study=None
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
        "latest_benchmark_link": lambda argument: (
            f"[{official(argument).name}]({PAGE.format(official(argument).name)})"),
        "results": lambda argument: results_table(official(argument), results, hidden),
        "leaderboard": lambda argument: leaderboard(
            official(argument), results, {c.name: c.title for c in (choosers or {}).values()},
            hidden),
        "results_figure": lambda argument: (
            f"![The scores of each model and heuristic in benchmark {official(argument).name}, "
            f"by domain, with 95% intervals]({FIGURE.format(official(argument).name)})"),
        "choices_figure": lambda argument: (
            f"![The percent of decisions that took a state on a shortest path, for each model and "
            f"heuristic in benchmark {official(argument).name}, by domain, with 95% intervals]"
            f"({FIGURES['choices_figure'].format(official(argument).name)})"),
        "frontier_figure": lambda argument: (
            f"![The score against the cost of a step for each model in benchmark "
            f"{official(argument).name}, by domain, with the efficient frontier]"
            f"({FIGURES['frontier_figure'].format(official(argument).name)})"),
        "trials": lambda argument: str(official(argument).trials),
        "max_expansions": lambda argument: f"{official(argument).max_expansions:,}",
        "domain_count": lambda argument: str(len(official(argument).domains)),
        # The argument is a chooser, for example \{{ refusals luna }}.
        "refusals": lambda argument: refusals_table(official(None), results, argument or "luna"),
        # The argument is <chooser>:<domain>, for example \{{ refused luna:rush_hour }}.
        "refused": lambda argument: refusal_share(official(None), results, argument, False),
        "fallback": lambda argument: refusal_share(official(None), results, argument, True),
        "costs": lambda argument: costs_table(official(argument), results, choosers or {}),
        "mini_costs": lambda argument: costs_table(
            official(argument), results, choosers or {},
            trials=mini.trials if mini else None, only=set(mini.choosers) if mini else set()),
        "mini_trials": lambda argument: str(mini.trials if mini else 0),
        "mini_models": lambda argument: " and ".join(
            (choosers or {})[c].title if choosers and c in choosers else c
            for c in (mini.choosers if mini else ())),
        # The argument is a study, for example \{{ study order-sensitivity }}.
        "study": lambda argument: study_table(
            officials, results, study, argument,
            {c.name: c.title for c in (choosers or {}).values()}),
        "study_links": lambda argument: "\n".join(
            f"- [{title}]({STUDY_PAGE.format(official(None).name, kind)})"
            for kind, title in STUDIES.items()),
        "study_models": lambda argument: ", ".join(
            (choosers or {})[c].title if choosers and c in choosers else c
            for c in (study.choosers if study else ())),
    }


def figures(template: str, officials: dict[str, Benchmark]) -> list[tuple[str, str]]:
    """The figures that the template shows: each placeholder name and its benchmark."""
    latest = list(officials)[-1]
    return sorted({(match.group(1), match.group(2) or latest)
                   for match in PLACEHOLDER.finditer(template) if match.group(1) in FIGURES})


def commentary(name: str, officials: dict[str, Benchmark], results: Path,
               choosers: Mapping[str, ChooserConfig] | None = None, mini=None) -> str:
    """The commentary of benchmark ``name``, with its placeholders replaced. "" if none."""
    path = results.parent / COMMENTARY.format(name)
    if not path.exists():
        return ""
    known = placeholders(officials, results, choosers, mini)
    # A comment at the top is for the author, not the reader.
    text = re.sub(r"\A\s*<!--.*?-->", "", path.read_text(), flags=re.S)
    return PLACEHOLDER.sub(lambda m: known[m.group(1)](m.group(2)),
                           text).replace("\\{{", "{{").strip()


def render(template: str, officials: dict[str, Benchmark], results: Path,
           choosers: Mapping[str, ChooserConfig] | None = None, source: str = TEMPLATE,
           mini=None, study=None) -> str:
    known = placeholders(officials, results, choosers, mini, study)
    latest = list(officials)[-1]
    known["commentary"] = lambda argument: (
        commentary(argument or latest, officials, results, choosers, mini)
        or f"No commentary for benchmark {argument or latest} yet.")
    known["commentary_link"] = lambda argument: (
        f"[Commentary on benchmark {argument or latest}]"
        f"({COMMENTARY_PAGE.format(argument or latest)})"
        if (results.parent / COMMENTARY.format(argument or latest)).exists()
        else f"No commentary for benchmark {argument or latest} yet.")

    def replace(match: re.Match[str]) -> str:
        name, argument = match.group(1), match.group(2)
        if name not in known:
            raise ValueError(f"unknown placeholder {match.group(0)!r}. "
                             f"Known: {', '.join(known)}")
        return known[name](argument)

    return HEADER.format(source) + PLACEHOLDER.sub(replace, template).replace("\\{{", "{{")
