from dataclasses import replace

from beelinebench.rng import Draws
from beelinebench.run import measure, summarise
from beelinebench.benchmark import Benchmark
from beelinebench.search import (Problem, Spend, best_first, distances_to_goal, efficiency,
                             lowest, oracle)

RULES = Benchmark(name="test", trials=1, max_expansions=10000, max_frontier=255, domains={})


def line_moves(n):
    return [m for m in (n - 1, n + 1) if 0 <= m <= 9]


def test_best_first_counts_the_solved_state():
    outcome = best_first(start=0, moves=line_moves, solved=lambda n: n == 3,
                         choose=lowest(lambda n: abs(3 - n)), max_expansions=100,
                         max_frontier=255, evict=Draws("test"))
    assert outcome.solved and outcome.expansions == 4 and outcome.path_length == 3


def test_lowest_takes_the_first_state_on_a_tie():
    assert lowest(lambda n: 0)([5, 6, 7]) == 0


def test_distances_to_goal_go_back_from_the_solved_states():
    distance = distances_to_goal(start=5, moves=line_moves, solved=lambda n: n in (3, 9))
    assert [distance[n] for n in range(10)] == [3, 2, 1, 0, 1, 2, 3, 2, 1, 0]


def test_a_state_that_reaches_no_goal_has_no_distance():
    # One way only: 0 -> 1 -> 2, and the goal is 1.
    distance = distances_to_goal(start=0, moves=lambda n: [n + 1] if n < 2 else [],
                                 solved=lambda n: n == 1)
    assert distance == {0: 1, 1: 0}


def test_the_oracle_scores_one():
    distance = distances_to_goal(start=5, moves=line_moves, solved=lambda n: n == 3)
    outcome = best_first(start=5, moves=line_moves, solved=lambda n: n == 3,
                         choose=oracle(distance), max_expansions=100, max_frontier=255,
                         evict=Draws("test"))
    assert outcome.expansions == 3 and efficiency(distance[5], outcome.expansions) == 1.0


def test_the_classic_chooser_against_itself_scores_the_same():
    from beelinebench.domains import tiles

    problem = tiles.problem(1, heuristic="manhattan", scramble=12)
    record = measure(problem, rules=RULES, label="test", choose=lowest(problem.heuristic), chooser="same", model="same",
                     spend=Spend(max_requests=0, max_input_tokens=0))
    assert record.score == record.baseline_score and not record.censored
    assert record.score == (record.shortest_path + 1) / record.model_expansions
    assert record.oracle_score == 1.0
    assert record.path_score == record.shortest_path / record.model_path_length
    assert record.started_utc and record.finished_utc


def line_problem() -> Problem:
    """From 5 to 3 on the line 0 to 9. The heuristic solves it in 3 explorations."""
    return Problem(domain="line", trial=1, start=5, moves=line_moves, solved=lambda n: n == 3,
                   heuristic=lambda n: abs(3 - n), heuristic_name="distance", render=str,
                   objective="", context="")


def away(states):
    """The worst chooser on the line: always the state farthest from 3."""
    return max(range(len(states)), key=lambda i: abs(3 - states[i]))


def test_a_model_that_reaches_the_limit_is_censored():
    record = measure(line_problem(), rules=replace(RULES, max_expansions=4), label="test",
                     choose=away, chooser="away", model="away",
                     spend=Spend(max_requests=0, max_input_tokens=0))
    assert record.censored and not record.model_solved and record.baseline_solved
    assert record.shortest_path == 2 and record.path_score is None
    assert record.model_expansions == 4 and record.score == 3 / 4
    assert record.baseline_score == 1.0


def test_a_heuristic_that_reaches_the_limit_is_not_skipped():
    record = measure(line_problem(), rules=replace(RULES, max_expansions=2), label="test",
                     choose=away, chooser="away", model="away",
                     spend=Spend(max_requests=0, max_input_tokens=0))
    assert not record.baseline_solved and record.censored
    summary = summarise([record], draws=Draws("test"))
    assert (summary.censored, summary.baseline_censored) == (1, 1)
    assert (summary.marks, summary.baseline_marks) == ("*", "†")


def test_summary_is_a_geometric_mean():
    from beelinebench.run import Record

    def record(score):
        return Record(benchmark="test", chooser="m", model="m", domain="d", heuristic="h", trial=1,
                      baseline_expansions=10, baseline_solved=True, model_expansions=10,
                      model_solved=True, censored=False, shortest_path=1,
                      oracle_expansions=2, score=score, baseline_score=score / 2,
                      oracle_score=1.0, baseline_path_length=1, model_path_length=1,
                      path_score=score, requests=0, input_tokens=0, output_tokens=0,
                      invalid_answers=0)

    summary = summarise([record(0.8), record(0.2)], draws=Draws("test"))
    assert abs(summary.score - 0.4) < 1e-9
    assert summary.coverage == 1.0 and abs(summary.solved_score - 0.4) < 1e-9
    assert abs(summary.baseline_score - 0.2) < 1e-9 and summary.oracle_score == 1.0
    assert abs(summary.path_score - 0.4) < 1e-9
    assert summary.marks == summary.baseline_marks == ""


def test_the_frontier_never_holds_more_than_the_cap():
    sizes = []
    outcome = best_first(start=0, moves=lambda n: range(n * 1000 + 1, n * 1000 + 301),
                         solved=lambda n: False, choose=lambda states: 0,
                         max_expansions=20, max_frontier=255, evict=Draws("test"),
                         observe=lambda expansions, frontier: sizes.append(frontier))
    assert not outcome.solved and max(sizes) <= 255


def test_a_wallet_stops_the_run_at_its_limit_and_keeps_its_total(tmp_path):
    import pytest

    from beelinebench.search import BudgetExhausted, Wallet, check

    path = tmp_path / "m.json"
    # $2 a million: 1,000,000 tokens are $2.00
    wallet = Wallet.open(path, price_input=2.0, price_output=0.0, max_cost=3.0,
                         start=(1_000_000, 0, 10))
    spend = Spend(max_requests=100, max_input_tokens=10**9, wallet=wallet)
    check(spend)
    spend.add(input_tokens=500_000, output_tokens=0, seconds=0.1, served="m")
    with pytest.raises(BudgetExhausted, match=r"\$3.00 spent"):
        check(spend)
    again = Wallet.open(path, price_input=2.0, price_output=0.0, max_cost=3.0, start=(0, 0, 0))
    assert (again.input_tokens, again.requests, again.cost) == (1_500_000, 11, 3.0)


def test_the_random_arm_is_the_same_for_each_model():
    from beelinebench.domains import tiles

    problem = tiles.problem(1, heuristic="manhattan", scramble=12)
    spend = Spend(max_requests=0, max_input_tokens=0)
    one = measure(problem, rules=RULES, label="test", choose=lowest(problem.heuristic),
                  chooser="a", model="a", spend=spend)
    two = measure(problem, rules=RULES, label="test", choose=lambda states: 0,
                  chooser="b", model="b", spend=spend)
    assert one.random_expansions == two.random_expansions
    assert one.random_score == (one.shortest_path + 1) / one.random_expansions
    assert one.random_score < one.baseline_score


def test_a_trace_has_a_step_for_each_state_the_model_explored(tmp_path):
    import gzip
    import json

    spend = Spend(max_requests=100, max_input_tokens=10**6)

    def toward(states):
        """Prefer the state nearest 3, and say so with probabilities, as a model does."""
        weights = [1.0 / (1 + abs(3 - s)) for s in states]
        spend.probabilities = [w / sum(weights) for w in weights]
        spend.add(input_tokens=10, output_tokens=0, seconds=0.01, served="m")
        return max(range(len(states)), key=lambda i: spend.probabilities[i])

    path = tmp_path / "trace.jsonl.gz"
    record = measure(line_problem(), rules=RULES, label="test", choose=toward, chooser="m",
                     model="m", spend=spend, trace=path)
    lines = [json.loads(line) for line in gzip.open(path, "rt")]
    header, steps = lines[0], lines[1:]
    assert header["trial"] == 1 and header["shortest_path"] == record.shortest_path
    assert len(steps) == record.model_expansions
    assert all(s["regret"] == 0 for s in steps)          # it always took a best state
    chosen = [s for s in steps if not s["forced"]]
    assert all(s["best_rank"] == 0 and len(s["top"]) <= 5 for s in chosen)
    assert sum(s["requests"] for s in steps) == record.requests


def test_replace_puts_a_record_in_place_of_the_same_trial(tmp_path):
    from dataclasses import replace as changed

    from beelinebench.run import Record, append, read, replace

    base = Record(benchmark="t", chooser="m", model="m", domain="d", heuristic="h", trial=1,
                  baseline_expansions=1, baseline_solved=True, model_expansions=1,
                  model_solved=True, censored=False, shortest_path=1, oracle_expansions=2,
                  score=0.5, baseline_score=0.5, oracle_score=1.0, baseline_path_length=1,
                  model_path_length=1, path_score=1.0, requests=0, input_tokens=0,
                  output_tokens=0, invalid_answers=0)
    path = tmp_path / "r.jsonl"
    append(path, base)
    append(path, changed(base, trial=2))
    replace(path, changed(base, score=0.25))
    assert [(r.trial, r.score) for r in read(path)] == [(1, 0.25), (2, 0.5)]
