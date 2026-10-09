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
    heuristic, a, b = groups[0][1]
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
