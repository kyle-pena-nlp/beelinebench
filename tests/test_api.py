"""The Python API runs a model that is a plain function, and writes the usual files."""

from beelinebench.api import Question, evaluate


def test_evaluate_runs_a_python_function(tmp_path):
    asked: list[Question] = []

    def decide(question: Question) -> list[float]:
        asked.append(question)
        # A Countdown option is the numbers that are left. Any fixed rule will do: prefer
        # the option with the smallest first number.
        return [-int(option.split()[0]) for option in question.options]

    first = evaluate(decide, name="fake-model", trials=2, domains=["countdown"], project=tmp_path)
    assert first[0]["benchmark"] == "1.0.0" and first[0]["trials"] == 2
    assert first[0]["score"] is not None
    assert (tmp_path / "results" / "1.0.0" / "fake-model" / "countdown.nearest_number.jsonl").exists()
    assert list((tmp_path / "traces" / "1.0.0" / "fake-model").rglob("*.jsonl.gz"))
    assert asked and asked[0].goal and len(asked[0].options) >= 2
    # A second call finds the trials done, and asks nothing.
    count = len(asked)
    evaluate(decide, name="fake-model", trials=2, domains=["countdown"], project=tmp_path)
    assert len(asked) == count
