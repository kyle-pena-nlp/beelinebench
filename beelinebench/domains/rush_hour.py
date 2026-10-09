"""Rush Hour: slide cars and trucks on a 6 × 6 board until the red car can leave.

Each vehicle is 2 cells (a car) or 3 cells (a truck) long, and it moves only along
its own direction. A move slides one vehicle any number of free cells, as in the
puzzle. The red car ``X`` is on the third row, and the search is solved when it is
at the exit on the right edge of that row.

The classic heuristic counts the vehicles between the red car and the exit, plus one
when the red car is not at the exit yet. It is simple and weak.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from functools import partial

from ..rng import Draws
from ..search import Problem, check_heuristic, distances_to_goal

SIZE = 6
#: The row of the red car and the exit, from the top, from 0.
EXIT_ROW = 2
#: The names of the other vehicles, in the order they are placed.
NAMES = "ABCDEFGHIJKLMNOPQRSTUVW"

CONTEXT = (
    "A state is a 6 by 6 board, written row by row from the top, with the rows "
    "separated by /. A dot is an empty cell. Each letter is a vehicle: two cells for a "
    "car, three for a truck. A vehicle moves only along its own direction: a "
    "horizontal vehicle moves left or right, and a vertical vehicle moves up or down. "
    "A move slides one vehicle any number of empty cells. X is the red car, on the "
    "third row. The exit is at the right end of the third row."
)
OBJECTIVE = "move the red car X to the exit at the right end of the third row"


@dataclass(frozen=True)
class Vehicle:
    name: str
    horizontal: bool
    length: int


#: For each vehicle, in the order of the vehicles of the trial: the row and column of
#: its top or left cell.
State = tuple[tuple[int, int], ...]


def cells(vehicle: Vehicle, at: tuple[int, int]) -> list[tuple[int, int]]:
    row, column = at
    return [(row, column + i) if vehicle.horizontal else (row + i, column)
            for i in range(vehicle.length)]


def occupied(vehicles: tuple[Vehicle, ...], state: State) -> dict[tuple[int, int], int]:
    return {cell: n for n, (v, at) in enumerate(zip(vehicles, state)) for cell in cells(v, at)}


def moves(vehicles: tuple[Vehicle, ...], state: State) -> Iterator[State]:
    """Each state one slide away: one vehicle, any number of free cells, either way."""
    taken = occupied(vehicles, state)
    for n, (v, (row, column)) in enumerate(zip(vehicles, state)):
        for step in (-1, 1):
            distance = 1
            while True:
                if v.horizontal:
                    front = column + (v.length - 1 if step > 0 else 0) + step * distance
                    if not 0 <= front < SIZE or (row, front) in taken:
                        break
                    moved = (row, column + step * distance)
                else:
                    front = row + (v.length - 1 if step > 0 else 0) + step * distance
                    if not 0 <= front < SIZE or (front, column) in taken:
                        break
                    moved = (row + step * distance, column)
                yield state[:n] + (moved,) + state[n + 1:]
                distance += 1


def reached(state: State) -> bool:
    """The red car, vehicle 0, is at the right edge of its row."""
    return state[0][1] == SIZE - 2


def blocking_cars(vehicles: tuple[Vehicle, ...], state: State) -> int:
    """The vehicles between the red car and the exit, plus one if the car is not there."""
    if reached(state):
        return 0
    taken = occupied(vehicles, state)
    front = state[0][1] + 2
    return 1 + len({taken[(EXIT_ROW, c)] for c in range(front, SIZE) if (EXIT_ROW, c) in taken})


def board(vehicles: tuple[Vehicle, ...], state: State) -> str:
    """The board on one line, for example ``..AA.. / ..B... / XXB... / ...``."""
    grid = [["."] * SIZE for _ in range(SIZE)]
    for v, at in zip(vehicles, state):
        for row, column in cells(v, at):
            grid[row][column] = v.name
    return " / ".join("".join(row) for row in grid)


def random_board(rng: Draws, count: int) -> tuple[tuple[Vehicle, ...], State]:
    """The red car on the exit row, short of the exit, and up to ``count`` other vehicles."""
    vehicles = [Vehicle("X", True, 2)]
    state = [(EXIT_ROW, rng.below(SIZE - 2))]
    taken = set(cells(vehicles[0], state[0]))
    for name in NAMES[:count]:
        for _ in range(50):  # tries to place this vehicle
            horizontal = rng.random() < 0.5
            length = 3 if rng.random() < 0.25 else 2
            # A horizontal vehicle on the exit row could never let the red car out.
            row = rng.below(SIZE - (0 if horizontal else length - 1))
            column = rng.below(SIZE - (length - 1 if horizontal else 0))
            vehicle = Vehicle(name, horizontal, length)
            spots = cells(vehicle, (row, column))
            if (horizontal and row == EXIT_ROW) or taken & set(spots):
                continue
            vehicles.append(vehicle)
            state.append((row, column))
            taken |= set(spots)
            break
    return tuple(vehicles), tuple(state)


def problem(trial: int, *, heuristic: str, vehicles: int, min_moves: int) -> Problem:
    """Trial ``trial``, drawn from ``Draws("rush_hour", trial)``.

    A random board with up to ``vehicles`` vehicles besides the red car. The board is
    kept if its shortest solution has at least ``min_moves`` moves.
    """
    check_heuristic("rush_hour", heuristic, ("blocking_cars",))
    rng = Draws("rush_hour", trial)
    while True:
        cars, start = random_board(rng, vehicles)
        distance = distances_to_goal(start=start, moves=partial(moves, cars), solved=reached)
        if distance.get(start, 0) >= min_moves:
            break
    return Problem(
        domain="rush_hour", trial=trial, start=start, moves=partial(moves, cars),
        solved=reached, heuristic=partial(blocking_cars, cars), heuristic_name="blocking_cars",
        render=partial(board, cars), objective=OBJECTIVE, context=CONTEXT)
