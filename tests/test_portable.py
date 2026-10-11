"""Trials are the same in every process, whatever Python's hash seed.

Python gives each process its own hash seed, so the order of a set of strings can
change from one run to the next. A trial or a search that depended on that order
would differ between machines. This test makes trials, and runs the classic and
oracle arms on them, in processes with two different hash seeds.
"""

import os
import subprocess
import sys
from pathlib import Path

PROJECT = Path(__file__).parent.parent

SCRIPT = """
from beelinebench.benchmark import load
from beelinebench.domains import blocksworld, countdown, keys_doors, rush_hour, tiles
from beelinebench.run import baseline, best, shortest

rules = load(__import__("pathlib").Path("benchmarks.toml"))["1.0.0"]
for module in (tiles, blocksworld, countdown, rush_hour, keys_doors):
    name = module.__name__.rsplit(".", 1)[1]
    for trial in (1, 2):
        problem = module.problem(trial, **rules.domains[name])
        distance = shortest(problem)
        classic, oracle = baseline(problem, rules), best(problem, rules, distance)
        print(name, trial, problem.render(problem.start), problem.objective,
              distance[problem.start], classic.expansions, classic.path_length,
              oracle.expansions)
problem = keys_doors.problem(3, heuristic="locked_doors", doors=10, min_moves=12)
print(problem.context, shortest(problem)[problem.start], baseline(problem, rules).expansions)
"""


def run_with_hash_seed(seed: str) -> str:
    env = {**os.environ, "PYTHONHASHSEED": seed}
    return subprocess.run([sys.executable, "-c", SCRIPT], cwd=PROJECT, env=env, check=True,
                          capture_output=True, text=True).stdout


def test_trials_and_searches_do_not_depend_on_the_hash_seed():
    first = run_with_hash_seed("1")
    assert first.count("\n") == 11
    assert run_with_hash_seed("2") == first
