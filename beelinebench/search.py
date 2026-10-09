"""Best-first search, and the record of one instance.

Both arms of the benchmark run :func:`best_first`. The one part that changes is
``choose``: the function that picks which frontier state to explore next.
"""

from __future__ import annotations

import math
from collections import deque
from collections.abc import Callable, Hashable, Iterable, Sequence
from dataclasses import dataclass, field
from typing import Any

from .rng import Draws

#: Takes the frontier, in the order the states were found. Gives the index of the
#: state to explore next.
Chooser = Callable[[Sequence[Any]], int]


@dataclass(frozen=True)
class Problem:
    """One instance of a domain.

    ``heuristic`` is the classic estimate, and ``heuristic_name`` names it in the
    results. A lower value is closer to solved, and the value can be any type
    that sorts. ``render`` writes a state on one line for
    the model. ``objective`` and ``context`` are the words the model gets with
    every question.
    """

    domain: str
    trial: int
    start: Hashable
    moves: Callable[[Any], Iterable[Hashable]]
    solved: Callable[[Any], bool]
    heuristic: Callable[[Any], Any]
    heuristic_name: str
    render: Callable[[Any], str]
    objective: str
    context: str


def check_heuristic(domain: str, heuristic: str, known: tuple[str, ...]) -> None:
    if heuristic not in known:
        raise ValueError(f"{domain} has no heuristic {heuristic!r}. It has {known}.")


class ChooserError(Exception):
    """A model request failed, or a model other than the one asked for answered it."""


class BudgetExhausted(Exception):
    """The run used all the requests or input tokens it was given."""


def check(spend: "Spend") -> None:
    if spend.requests >= spend.max_requests or spend.input_tokens >= spend.max_input_tokens:
        raise BudgetExhausted(f"{spend.requests} requests, {spend.input_tokens} input tokens")


@dataclass
class Spend:
    """What a run may send to a model, and what it sent.

    A run stops before a request when it has sent ``max_requests`` requests or
    ``max_input_tokens`` input tokens.

    ``invalid_answers`` counts answers that named no state. The chooser then takes
    the first state of its shuffled list.

    For each request, ``latencies_ms`` holds its time from send to answer, and
    ``served`` holds the model that the API says answered it.
    """

    max_requests: int
    max_input_tokens: int
    requests: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    invalid_answers: int = 0
    #: Answers that refused the question. A chooser can ask again.
    refusals: int = 0
    latencies_ms: list[int] = field(default_factory=list)
    served: list[str] = field(default_factory=list)

    def add(self, *, input_tokens: int, output_tokens: int, seconds: float,
            served: str) -> None:
        """Count one request."""
        self.requests += 1
        self.input_tokens += input_tokens
        self.output_tokens += output_tokens
        self.latencies_ms.append(round(seconds * 1000))
        self.served.append(served)


@dataclass(frozen=True)
class Outcome:
    """The result of one search.

    ``expansions`` counts every state taken off the frontier, the solved state
    included.
    """

    solved: bool
    expansions: int
    path_length: int | None


def best_first(*, start: Hashable, moves: Callable[[Any], Iterable[Hashable]],
               solved: Callable[[Any], bool], choose: Chooser,
               max_expansions: int, max_frontier: int, evict: Draws,
               observe: Callable[[int, int], None] | None = None) -> Outcome:
    """Explore the state that ``choose`` picks, until a state is solved.

    The search tests a state when it takes the state off the frontier. A state
    goes on the frontier once only while it is there. When the frontier holds
    one state, the search takes it and does not call ``choose``.

    The frontier holds at most ``max_frontier`` states. Above that, states drawn
    at random from ``evict`` leave it, and the search forgets them, so it can
    find them again. ``observe`` gets the explorations and the size of the
    frontier after each exploration.
    """
    frontier: list[tuple[Hashable, int]] = [(start, 0)]
    seen = {start}
    expansions = 0
    while frontier and expansions < max_expansions:
        index = 0 if len(frontier) == 1 else choose([state for state, _ in frontier])
        state, depth = frontier.pop(index)
        expansions += 1
        if observe is not None:
            observe(expansions, len(frontier))
        if solved(state):
            return Outcome(solved=True, expansions=expansions, path_length=depth)
        for child in moves(state):
            if child not in seen:
                seen.add(child)
                frontier.append((child, depth + 1))
        while len(frontier) > max_frontier:
            dropped, _ = frontier.pop(evict.below(len(frontier)))
            seen.discard(dropped)
    return Outcome(solved=False, expansions=expansions, path_length=None)


def distances_to_goal(*, start: Hashable, moves: Callable[[Any], Iterable[Hashable]],
                      solved: Callable[[Any], bool]) -> dict[Hashable, int]:
    """The fewest moves from each state that ``start`` reaches to a solved state.

    A breadth-first search finds every state that ``start`` reaches, and a second
    one goes back from the solved states along the moves. A state that reaches no
    solved state is not in the result.
    """
    parents: dict[Hashable, list[Hashable]] = {start: []}
    queue = deque([start])
    while queue:
        state = queue.popleft()
        for child in moves(state):
            if child not in parents:
                parents[child] = []
                queue.append(child)
            parents[child].append(state)
    distance = {state: 0 for state in parents if solved(state)}
    queue = deque(distance)
    while queue:
        state = queue.popleft()
        for parent in parents[state]:
            if parent not in distance:
                distance[parent] = distance[state] + 1
                queue.append(parent)
    return distance


def oracle(distance: dict[Hashable, int]) -> Chooser:
    """The perfect chooser: the state with the fewest moves to a solved state.

    It explores a shortest path, unless the frontier cap drops a state of it. On a
    tie it takes the state that was found first.
    """
    def choose(states: Sequence[Any]) -> int:
        return min(range(len(states)), key=lambda i: distance.get(states[i], math.inf))

    return choose


def efficiency(shortest: int, expansions: int) -> float:
    """The explorations of a perfect search divided by those of this one.

    A perfect search explores the states of a shortest path, the start and the
    solved state included: ``shortest + 1``. So 1.0 is perfect, and 0.1 means ten
    times the explorations.
    """
    return (shortest + 1) / expansions


def lowest(heuristic: Callable[[Any], Any]) -> Chooser:
    """The classic chooser: the state with the lowest heuristic value.

    On a tie it takes the state that was found first.
    """
    values: dict[Hashable, Any] = {}

    def choose(states: Sequence[Any]) -> int:
        for state in states:
            if state not in values:
                values[state] = heuristic(state)
        return min(range(len(states)), key=lambda i: values[states[i]])

    return choose
