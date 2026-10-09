import json
from pathlib import Path

import pytest

from beelinebench import benchmark, readme

PROJECT = Path(__file__).parent.parent
OFFICIALS = benchmark.load(PROJECT / "benchmarks.toml")


def record(trial: int, score: float, censored: bool = False) -> dict:
    return dict(benchmark="1.0.0", chooser="fake", model="fake", domain="tiles",
                heuristic="manhattan", trial=trial, baseline_expansions=10,
                baseline_solved=True, model_expansions=5, model_solved=not censored,
                censored=censored, shortest_path=4, oracle_expansions=5, score=score,
                baseline_score=0.5, oracle_score=1.0, baseline_path_length=4,
                model_path_length=4, path_score=1.0, requests=5, input_tokens=100, output_tokens=0,
                invalid_answers=0, started_utc="2026-10-01T00:00:00Z",
                finished_utc="2026-10-01T00:01:00Z", served_models=["fake-1"])


def test_the_committed_readme_is_up_to_date():
    from beelinebench import config

    template = (PROJECT / readme.TEMPLATE).read_text()
    choosers = config.load(PROJECT / "beelinebench.toml", OFFICIALS).choosers
    made = readme.render(template, OFFICIALS, PROJECT / "results", choosers)
    assert (PROJECT / readme.OUTPUT).read_text() == made, \
        "run `python -m beelinebench readme`"


def test_placeholders_are_replaced(tmp_path):
    path = tmp_path / "1.0.0" / "fake" / "tiles.manhattan.jsonl"
    path.parent.mkdir(parents=True)
    path.write_text("".join(json.dumps(record(n, 0.8)) + "\n" for n in (1, 2)))
    made = readme.render("v{{ latest_benchmark }}, {{trials}} trials\n{{ results 1.0.0 }}",
                         OFFICIALS, tmp_path)
    assert made.startswith(readme.HEADER + "v1.0.0, 100 trials\n| chooser |")
    assert "| `fake` | `tiles` | `manhattan` | 2 of 100 | 0.800 | 0.800 to 0.800 | 0.500 " \
           "| 1.000 | 1.00 | 2 of 2 | 0.0% | fake-1 | 2026-10-01 |" in made


def test_no_results(tmp_path):
    assert readme.render("{{ results }}", OFFICIALS, tmp_path) == \
        readme.HEADER + "No results for benchmark 1.0.0 yet."


def test_an_escaped_placeholder_is_text(tmp_path):
    assert readme.render(r"`\{{ results }}`", OFFICIALS, tmp_path) == \
        readme.HEADER + "`{{ results }}`"


@pytest.mark.parametrize("text", ["{{ result }}", "{{ results 9.9.9 }}"])
def test_a_bad_placeholder_is_an_error(text, tmp_path):
    with pytest.raises(ValueError):
        readme.render(text, OFFICIALS, tmp_path)


def test_the_committed_figure_shows_the_current_results():
    from beelinebench import config, plot

    choosers = config.load(PROJECT / "beelinebench.toml", OFFICIALS).choosers
    labels = {c.name: c.title for c in choosers.values()}
    prices = {c.name: (c.price_input, c.price_output or 0.0)
              for c in choosers.values() if c.price_input is not None}
    for kind, name in readme.figures((PROJECT / readme.TEMPLATE).read_text(), OFFICIALS):
        png = PROJECT / readme.FIGURES[kind].format(name)
        extra = dict(prices=prices, kind="frontier") if kind == "frontier_figure" else {}
        assert plot.is_current(png, OFFICIALS[name], PROJECT / "results", labels,
                               config.unpublished(choosers), **extra), \
            "run `python -m beelinebench readme`"


def test_the_figure_placeholder_is_an_image():
    made = readme.render("{{ results_figure }}", OFFICIALS, PROJECT / "results")
    assert made == readme.HEADER + (
        "![The scores of each model and heuristic in benchmark 1.0.0, by domain, with 95% "
        "intervals](docs/benchmarks/1.0.0.png)")
    assert readme.figures("{{ results_figure }} {{ results_figure 1.0.0 }} {{ frontier_figure }}",
                          OFFICIALS) == [("frontier_figure", "1.0.0"), ("results_figure", "1.0.0")]


def test_a_price_estimate_uses_measured_tokens_or_borrows_them(tmp_path):
    from beelinebench.config import ChooserConfig

    def chooser(name, price_input, price_output=0.0, protocol="jev"):
        return ChooserConfig(name=name, protocol=protocol, model=name, api_base=None,
                             api_key_env=None, effort=None, trials=None, max_requests=1,
                             max_input_tokens=1, label=name.upper(), price_input=price_input,
                             price_output=price_output)

    one = OFFICIALS["1.0.0"]
    for domain, settings in one.domains.items():
        path = tmp_path / "1.0.0" / "a" / f"{domain}.{settings['heuristic']}.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        # record() gives 100 input tokens and no output tokens for each trial
        path.write_text(json.dumps(record(1, 0.8)) + "\n")
    choosers = {"a": chooser("a", 2.0), "b": chooser("b", 4.0), "local": chooser("local", None),
                "c": chooser("c", 1.0, 5.0, protocol="anthropic")}
    table = readme.costs_table(one, tmp_path, choosers)
    # 7 domains x 100 trials x 100 tokens = 70,000 tokens
    assert "| A | $2.00 input, output free | 70 thousand | $0.14 | measured on 7 trials |" in table
    assert "| B | $4.00 input, output free | 70 thousand | $0.28 | token counts of A |" in table
    assert "| C | $1.00 input, $5.00 output | — | — | no results to estimate from |" in table
    assert "LOCAL" not in table


def test_the_latest_benchmark_link_points_to_its_page(tmp_path):
    text = readme.render("{{ latest_benchmark_link }}", OFFICIALS, tmp_path)
    assert text.endswith("[1.0.0](docs/benchmarks/1.0.0.md)")
