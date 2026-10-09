"""Blocksworld with a hand, as in the planning competitions. The classic heuristic is h_FF.

A state is the set of facts that are true. The four actions are the STRIPS
actions of the competition domain: pick up, put down, stack and unstack.

h_FF (Hoffmann and Nebel, 2001) is the length of a plan of the relaxed problem,
where an action deletes nothing. It is the baseline of Corrêa, Pereira and
Seipp (2025), who compare heuristics in the same greedy best-first search.
"""

from __future__ import annotations

import heapq
import math
from collections.abc import Iterator
from dataclasses import dataclass
from functools import cache, partial

from ..rng import Draws
from ..search import Problem, check_heuristic

State = frozenset[str]

CONTEXT = (
    "A state is the list of facts that are true. (on a b) means block a is on "
    "block b. (ontable a) means a is on the table. (clear a) means nothing is on "
    "a. (holding a) means the hand holds a. (handempty) means the hand holds "
    "nothing. The hand can pick up a clear block from the table, put down the "
    "block it holds, stack the block it holds on a clear block, or unstack a clear "
    "block from the block under it. The hand holds one block at a time."
)


@dataclass(frozen=True)
class Action:
    preconditions: frozenset[str]
    adds: frozenset[str]
    deletes: frozenset[str]


@cache
def actions(blocks: int) -> tuple[Action, ...]:
    names = [f"b{n}" for n in range(1, blocks + 1)]
    out = []
    for x in names:
        out.append(Action(frozenset({f"(clear {x})", f"(ontable {x})", "(handempty)"}),
                          frozenset({f"(holding {x})"}),
                          frozenset({f"(ontable {x})", f"(clear {x})", "(handempty)"})))
        out.append(Action(frozenset({f"(holding {x})"}),
                          frozenset({f"(ontable {x})", f"(clear {x})", "(handempty)"}),
                          frozenset({f"(holding {x})"})))
        for y in names:
            if x != y:
                out.append(Action(frozenset({f"(holding {x})", f"(clear {y})"}),
                                  frozenset({f"(on {x} {y})", f"(clear {x})", "(handempty)"}),
                                  frozenset({f"(holding {x})", f"(clear {y})"})))
                out.append(Action(frozenset({f"(on {x} {y})", f"(clear {x})", "(handempty)"}),
                                  frozenset({f"(holding {x})", f"(clear {y})"}),
                                  frozenset({f"(on {x} {y})", f"(clear {x})", "(handempty)"})))
    return tuple(out)


@cache
def users_of(blocks: int) -> dict[str, tuple[Action, ...]]:
    """For each fact, the actions that need it."""
    users: dict[str, list[Action]] = {}
    for action in actions(blocks):
        for fact in action.preconditions:
            users.setdefault(fact, []).append(action)
    return {fact: tuple(found) for fact, found in users.items()}


def moves(blocks: int, state: State) -> Iterator[State]:
    for action in actions(blocks):
        if action.preconditions <= state:
            yield (state - action.deletes) | action.adds


def reached(goal: frozenset[str], state: State) -> bool:
    return goal <= state


def h_ff(blocks: int, goal: frozenset[str], state: State) -> float:
    """The number of actions in a relaxed plan, from h_add costs."""
    cost = {fact: 0.0 for fact in state}
    achiever: dict[str, Action] = {}
    queue = [(0.0, fact) for fact in state]
    heapq.heapify(queue)
    unmet = {action: len(action.preconditions) for action in actions(blocks)}
    users = users_of(blocks)
    settled: set[str] = set()
    while queue and not goal <= settled:
        value, fact = heapq.heappop(queue)
        if fact in settled:
            continue
        settled.add(fact)
        for action in users.get(fact, ()):
            unmet[action] -= 1
            if unmet[action] == 0:
                step = 1.0 + sum(cost[p] for p in action.preconditions)
                for added in action.adds:
                    if step < cost.get(added, math.inf):
                        cost[added] = step
                        achiever[added] = action
                        heapq.heappush(queue, (step, added))
    if not goal <= settled:
        return math.inf
    plan: set[Action] = set()
    waiting, seen = list(goal), set(goal)
    while waiting:
        action = achiever.get(waiting.pop())
        if action is None or action in plan:
            continue
        plan.add(action)
        for fact in action.preconditions - seen:
            seen.add(fact)
            waiting.append(fact)
    return float(len(plan))


def facts(state: State) -> str:
    return " ".join(sorted(state))


def towers(rng: Draws, blocks: int) -> list[list[str]]:
    """Random towers. Each tower is written from the table up."""
    out: list[list[str]] = []
    for name in rng.sample([f"b{n}" for n in range(1, blocks + 1)], blocks):
        if out and rng.random() < 0.5:
            rng.choice(out).append(name)
        else:
            out.append([name])
    return out


def tower_facts(stacks: list[list[str]]) -> set[str]:
    return ({f"(ontable {tower[0]})" for tower in stacks}
            | {f"(on {above} {below})" for tower in stacks
               for below, above in zip(tower, tower[1:])})


def problem(trial: int, *, heuristic: str, blocks: int) -> Problem:
    """Trial ``trial``, drawn from ``Draws("blocksworld", trial)``. Random start and goal towers."""
    check_heuristic("blocksworld", heuristic, ("h_ff",))
    rng = Draws("blocksworld", trial)
    start = towers(rng, blocks)
    goal = frozenset(tower_facts(towers(rng, blocks)))
    while goal <= tower_facts(start):
        goal = frozenset(tower_facts(towers(rng, blocks)))
    state = frozenset(tower_facts(start) | {f"(clear {tower[-1]})" for tower in start}
                      | {"(handempty)"})
    return Problem(
        domain="blocksworld", trial=trial, start=state, moves=partial(moves, blocks),
        solved=partial(reached, goal), heuristic=partial(h_ff, blocks, goal), heuristic_name="h_ff",
        render=facts, objective=("reach a state where all of these facts are true: "
                                 + " ".join(sorted(goal))),
        context=CONTEXT)
