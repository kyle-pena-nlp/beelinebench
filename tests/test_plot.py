import json

from beelinebench import plot
from tests.test_readme import OFFICIALS, record


def test_each_domain_is_the_heuristic_then_a_row_for_each_chooser(tmp_path):
    for chooser, trials in (("a", (1, 2, 3)), ("b", (1,))):
        path = tmp_path / "1.0.0" / chooser / "tiles.manhattan.jsonl"
        path.parent.mkdir(parents=True)
        path.write_text("".join(json.dumps(record(n, 0.8)) + "\n" for n in trials))
    groups = plot.rows(OFFICIALS["1.0.0"], tmp_path, {"a": "Model A"})
    assert [title for title, _ in groups] == ["8-puzzle"]
    a, b, heuristic = groups[0][1]          # best first: 0.8, 0.8, then the heuristic at 0.5
    assert (heuristic.label, heuristic.trials) == ("Heuristic: Manhattan distance", 3)
    assert abs(heuristic.score - 0.5) < 1e-9 and heuristic.reference
    assert (a.label, a.trials, b.label, b.trials) == ("Model A", 3, "b", 1)
    assert not a.reference and abs(a.low - 0.8) < 1e-9


def test_a_figure_holds_the_fingerprint_of_its_rows(tmp_path):
    import pytest

    pytest.importorskip("matplotlib")
    path = tmp_path / "1.0.0" / "a" / "tiles.manhattan.jsonl"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps(record(1, 0.8)) + "\n")
    png = tmp_path / "figure.png"
    plot.draw(OFFICIALS["1.0.0"], tmp_path, png)
    assert plot.stored_fingerprint(png) == plot.fingerprint(OFFICIALS["1.0.0"], tmp_path)
    assert plot.is_current(png, OFFICIALS["1.0.0"], tmp_path)
    path.write_text(json.dumps(record(1, 0.4)) + "\n")
    assert not plot.is_current(png, OFFICIALS["1.0.0"], tmp_path)


def test_the_frontier_keeps_the_models_that_no_model_beats_on_cost_and_score():
    def row(label, cost, score):
        return plot.Row(label, score, score, score, 1, "", cost_per_step=cost)

    cheap, mid, dear, beaten = row("cheap", 1, 0.1), row("mid", 2, 0.3), row("dear", 4, 0.5), \
        row("beaten", 3, 0.2)
    assert plot.frontier([dear, beaten, mid, cheap]) == [cheap, mid, dear]
    # A cheaper model with a higher score removes a dearer one.
    assert plot.frontier([row("a", 1, 0.5), row("b", 2, 0.3)])[0].label == "a"
    assert len(plot.frontier([row("a", 1, 0.5), row("b", 2, 0.3)])) == 1


def test_the_convex_frontier_runs_from_the_best_score_to_the_cheapest_model():
    def row(label, cost, score):
        return plot.Row(label, score, score, score, 1, "", cost_per_step=cost)

    best, middle, cheap, beaten = row("best", 0.25, 0.21), row("middle", 0.15, 0.13), \
        row("cheap", 0.058, 0.12), row("beaten", 0.58, 0.03)
    # On the page "middle" is outside the straight line from "best" to "cheap", so the
    # convex frontier passes it by.
    assert plot.convex_frontier([beaten, middle, cheap, best]) == [best, cheap]
    # One model that beats the others is the whole frontier.
    assert plot.convex_frontier([row("a", 0.04, 0.46), row("b", 0.05, 0.24)])[0].label == "a"
    assert len(plot.convex_frontier([row("a", 0.04, 0.46), row("b", 0.05, 0.24)])) == 1
