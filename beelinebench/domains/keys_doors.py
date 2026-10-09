"""Keys and doors: walk from room to room, and pick up keys, until you reach the exit.

Each door has a color, and the key of the same color opens it. A door leads from one
room to the room behind it, so the rooms form a tree with the starting room at the
root. The exit is behind one of the doors. A trial is a list of statements, for
example "The red key is behind the blue door." You start in the starting room.

A move goes through one door of the current room, back or forward. You can go
forward through a door after you open it once, or when you hold its key. You pick up
each key in a room when you go in, and you keep it. So a state is the current room and
the rooms you went into: those rooms give the keys you hold and the doors you opened.

The classic heuristic counts the closed doors on the path from the starting room to
the exit, and the keys of those doors that you do not hold yet. It is simple and weak:
it does not see the walk back from a dead end.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from functools import partial

from ..rng import Draws
from ..search import Problem, check_heuristic, distances_to_goal

COLORS = ("red", "blue", "green", "yellow", "purple", "orange", "white", "black",
          "silver", "gold", "pink", "brown")
#: The room that is not behind a door.
START = "start"

CONTEXT = (
    "You are in a building of rooms. Each door has a color, and the key of the same "
    "color opens it. A move goes through one door of the room you are in, forward or "
    "back. You can go forward through a door when you have its key or when it is open. "
    "When you go into a room, you pick up all the keys in it, and you keep them. "
    "A state gives the room you are in, the keys you hold and the doors that are open."
)


@dataclass(frozen=True)
class Layout:
    """The building of one trial.

    ``parent[door]`` is the room that holds ``door``: ``START``, or the color of the
    door in front of that room. A room behind a door has the name of that door.
    ``key_room[color]`` is the room that holds the key of the ``color`` door.
    """

    doors: tuple[str, ...]
    parent: dict[str, str]
    key_room: dict[str, str]
    exit: str


#: The current room, and the rooms you went into (in the order of ``Layout.doors``).
State = tuple[str, frozenset[str]]


def path_to(layout: Layout, room: str) -> list[str]:
    """The doors from the starting room to ``room``, in order."""
    doors = []
    while room != START:
        doors.append(room)
        room = layout.parent[room]
    return doors[::-1]


def moves(layout: Layout, state: State) -> Iterator[State]:
    room, visited = state
    keys = {color for color, at in layout.key_room.items() if at in visited}
    if room != START:
        yield layout.parent[room], visited  # back through the door of this room
    for door in layout.doors:
        if layout.parent[door] == room and (door in visited or door in keys):
            yield door, visited | {door}


def reached(layout: Layout, state: State) -> bool:
    return state[0] == layout.exit


def locked_doors(layout: Layout, state: State) -> int:
    """The closed doors on the path to the exit, plus the keys of them that you lack."""
    _, visited = state
    keys = {color for color, at in layout.key_room.items() if at in visited}
    closed = [door for door in path_to(layout, layout.exit) if door not in visited]
    return len(closed) + sum(door not in keys for door in closed)


def room_name(room: str) -> str:
    return "the starting room" if room == START else f"the room behind the {room} door"


def describe(layout: Layout, state: State) -> str:
    """For example ``in the room behind the red door · keys: blue, red · open doors: red``."""
    room, visited = state
    keys = [c for c in layout.doors if layout.key_room[c] in visited]
    opened = [d for d in layout.doors if d in visited]
    return (f"in {room_name(room)} · keys: {', '.join(keys) or 'none'}"
            f" · open doors: {', '.join(opened) or 'none'}")


def statements(layout: Layout, rng: Draws) -> list[str]:
    """The facts of the building, in a random order."""
    facts = [f"The {door} door is in {room_name(layout.parent[door])}." for door in layout.doors]
    facts += [f"The {color} key is in {room_name(at)}." for color, at in layout.key_room.items()]
    facts.append(f"The exit is behind the {layout.exit} door.")
    rng.shuffle(facts)
    return [fact.replace("is in the room behind", "is behind") for fact in facts]


def random_layout(rng: Draws, count: int) -> Layout:
    """A solvable building with ``count`` doors and their keys.

    Each door goes in a random room that exists already. Then a random order to open the
    doors is drawn, and the key of each door goes in a room that is open before it.
    The exit is behind a door with no doors behind it.
    """
    pool = list(COLORS)
    doors = tuple(rng.sample(pool, count))
    parent = {}
    for i, door in enumerate(doors):
        parent[door] = rng.choice((START,) + doors[:i])
    reachable, key_room = [START], {}
    waiting = [d for d in doors if parent[d] == START]
    while waiting:
        door = waiting.pop(rng.below(len(waiting)))
        key_room[door] = rng.choice(reachable)
        reachable.append(door)
        waiting += [d for d in doors if parent[d] == door]
    leaves = [d for d in doors if d not in parent.values()]
    return Layout(doors, parent, key_room, rng.choice(leaves))


def problem(trial: int, *, heuristic: str, doors: int, min_moves: int) -> Problem:
    """Trial ``trial``, drawn from ``Draws("keys_doors", trial)``. The order of the
    statements is drawn from ``Draws("keys_doors", trial, "statements")``.

    A random building with ``doors`` doors. It is kept if its shortest solution has at
    least ``min_moves`` moves.
    """
    check_heuristic("keys_doors", heuristic, ("locked_doors",))
    rng = Draws("keys_doors", trial)
    while True:
        layout = random_layout(rng, doors)
        start: State = (START, frozenset({START}))
        distance = distances_to_goal(start=start, moves=partial(moves, layout),
                                     solved=partial(reached, layout))
        if distance.get(start, 0) >= min_moves:
            break
    # The statements have their own draws, so a change to the layout draws does not
    # change their order.
    order = Draws("keys_doors", trial, "statements")
    context = CONTEXT + " The building: " + " ".join(statements(layout, order))
    return Problem(
        domain="keys_doors", trial=trial, start=start, moves=partial(moves, layout),
        solved=partial(reached, layout), heuristic=partial(locked_doors, layout),
        heuristic_name="locked_doors", render=partial(describe, layout),
        objective="reach the exit", context=context)
