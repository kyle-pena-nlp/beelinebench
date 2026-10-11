"""Countdown: combine four numbers with + - × ÷ to make a target.

This is the task of Stream of Search (Gandhi et al., 2024) and LLM-First Search
(Herr et al., 2025). A state is the sorted numbers that are left. The search is
solved when one number is left and it is the target.

The classic heuristic is the distance from the nearest number to the target. On
a tie, the state with fewer numbers goes first.
"""

from __future__ import annotations

from collections.abc import Iterator
from functools import partial

from ..rng import Draws
from ..search import Problem, check_heuristic

Numbers = tuple[int, ...]

CONTEXT = (
    "A state is a list of numbers. A move takes two of the numbers and puts back "
    "one: their sum, their product, the larger minus the smaller if that is not "
    "zero, or the larger divided by the smaller if it divides exactly. The search "
    "is done when one number is left and it is the target."
)


def combinations(a: int, b: int) -> Iterator[int]:
    high, low = max(a, b), min(a, b)
    yield high + low
    yield high * low
    if high != low:
        yield high - low
    if high % low == 0:
        yield high // low


def moves(state: Numbers) -> Iterator[Numbers]:
    for i in range(len(state)):
        for j in range(i + 1, len(state)):
            rest = state[:i] + state[i + 1:j] + state[j + 1:]
            for result in combinations(state[i], state[j]):
                yield tuple(sorted(rest + (result,)))


def reached(target: int, state: Numbers) -> bool:
    return state == (target,)


def nearest(target: int, state: Numbers) -> tuple[int, int]:
    return (min(abs(n - target) for n in state), len(state))


def line(state: Numbers) -> str:
    return " ".join(str(n) for n in state)


def problem(trial: int, *, heuristic: str, numbers: int, largest_number: int,
            smallest_target: int, largest_target: int) -> Problem:
    """Trial ``trial``, drawn from ``Draws("countdown", trial)``.

    ``numbers`` numbers from 1 to ``largest_number``, and a target made from them
    by random moves, so a solution exists. The target is from ``smallest_target``
    to ``largest_target``, and is not one of the numbers.
    """
    check_heuristic("countdown", heuristic, ("nearest_number",))
    rng = Draws("countdown", trial)
    while True:
        start = tuple(sorted(1 + rng.below(largest_number) for _ in range(numbers)))
        state = start
        while len(state) > 1:
            state = rng.choice(list(moves(state)))
        target = state[0]
        if smallest_target <= target <= largest_target and target not in start:
            break
    return Problem(
        domain="countdown", trial=trial, start=start, moves=moves,
        solved=partial(reached, target), heuristic=partial(nearest, target), heuristic_name="nearest_number",
        render=line, objective=f"make {target} from the numbers, using every number",
        context=CONTEXT)
