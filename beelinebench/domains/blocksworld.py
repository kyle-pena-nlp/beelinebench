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


# Other representations of the same states, for the case study of `python -m beelinebench
# case-study`. The benchmark uses the facts. Each one writes a state, and the goal, from
# the same facts, so only the text that the model sees changes.

def stacks(state: State) -> tuple[list[list[str]], str | None]:
    """The towers of ``state``, each from the table up, and the block in the hand."""
    above = {}
    for fact in state:
        if fact.startswith("(on "):
            top, below = fact[4:-1].split()
            above[below] = top
    out = []
    for base in sorted(f[9:-1] for f in state if f.startswith("(ontable ")):
        tower = [base]
        while tower[-1] in above:
            tower.append(above[tower[-1]])
        out.append(tower)
    held = next((f[9:-1] for f in state if f.startswith("(holding ")), None)
    return out, held


def number(block: str) -> str:
    return f"block {block[1:]}"


def sentences(state: State) -> str:
    """For example ``Block 2 is on block 5. Block 5 is on the table. The hand is empty.``"""
    out = []
    for fact in sorted(state):
        words = fact[1:-1].split()
        if words[0] == "on":
            out.append(f"{number(words[1]).capitalize()} is on {number(words[2])}.")
        elif words[0] == "ontable":
            out.append(f"{number(words[1]).capitalize()} is on the table.")
        elif words[0] == "clear":
            out.append(f"Nothing is on {number(words[1])}.")
        elif words[0] == "holding":
            out.append(f"The hand holds {number(words[1])}.")
        else:
            out.append("The hand is empty.")
    return " ".join(out)


def tower_words(state: State) -> str:
    """For example ``a tower of b5, b2 (from the table up); a tower of b1; the hand is empty``."""
    found, held = stacks(state)
    parts = [f"a tower of {', '.join(tower)}" + (" (from the table up)" if len(tower) > 1 else "")
             for tower in found]
    parts.append(f"the hand holds {held}" if held else "the hand is empty")
    return "; ".join(parts)


def brackets(state: State) -> str:
    """For example ``[b5 b2] [b1] hand: -``. Each tower goes from the table up."""
    found, held = stacks(state)
    return " ".join(f"[{' '.join(tower)}]" for tower in found) + f" hand: {held or '-'}"


#: For each representation: how it writes a state, and the context of the model.
REPRESENTATIONS = {
    "facts": (facts, CONTEXT),
    "sentences": (sentences, (
        "A state is a list of sentences that are true. The hand can pick up a block from the "
        "table when nothing is on it, put down the block it holds, stack the block it holds on "
        "a block that has nothing on it, or unstack a block that has nothing on it from the "
        "block under it. The hand holds one block at a time.")),
    "towers": (tower_words, (
        "A state lists the towers of blocks, each from the table up, and what the hand holds. "
        "The hand can pick up the top block of a tower of one block, put down the block it "
        "holds as a new tower, stack the block it holds on the top of a tower, or unstack the "
        "top block of a tower. The hand holds one block at a time.")),
    "brackets": (brackets, (
        "A state lists the towers of blocks in brackets, each from the table up, and then the "
        "block in the hand, or - for none. The hand can pick up a block that is alone in its "
        "brackets, put down the block it holds in new brackets, stack the block it holds on "
        "the top of a tower, or unstack the top block of a tower. The hand holds one block at "
        "a time.")),
}


def represent(problem: Problem, name: str) -> Problem:
    """``problem`` with the states and the goal in representation ``name``."""
    from dataclasses import replace

    render, context = REPRESENTATIONS[name]
    goal = problem.solved.args[0]
    if name == "facts":
        objective = problem.objective
    elif name == "sentences":
        objective = ("reach a state where all of these sentences are true: "
                     + sentences(goal))
    else:
        towers_of_goal = frozenset(goal | {"(handempty)"})
        objective = "reach this state: " + render(towers_of_goal)
    return replace(problem, render=render, context=context, objective=objective)
