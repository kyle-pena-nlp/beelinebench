"""The 8-puzzle. The classic heuristic is Manhattan distance."""

from __future__ import annotations

from collections.abc import Iterator

from ..rng import Draws
from ..search import Problem, check_heuristic

Board = tuple[int, ...]

#: The solved board. 0 is the gap.
SOLVED: Board = (1, 2, 3, 4, 5, 6, 7, 8, 0)

CONTEXT = (
    "A state is a 3 by 3 board, written row by row from the top, with the rows "
    "separated by |. A dot is the gap. A move slides one tile that is next to the "
    "gap into the gap."
)


def slide(board: Board) -> Iterator[Board]:
    """Every board one move away."""
    gap = board.index(0)
    row, column = divmod(gap, 3)
    for dr, dc in ((-1, 0), (1, 0), (0, -1), (0, 1)):
        r, c = row + dr, column + dc
        if 0 <= r < 3 and 0 <= c < 3:
            tiles = list(board)
            tiles[gap], tiles[r * 3 + c] = tiles[r * 3 + c], 0
            yield tuple(tiles)


def is_solved(board: Board) -> bool:
    return board == SOLVED


def manhattan(board: Board) -> int:
    """The sum over tiles of the rows and columns between a tile and its home."""
    total = 0
    for index, tile in enumerate(board):
        if tile:
            home = tile - 1
            total += abs(index // 3 - home // 3) + abs(index % 3 - home % 3)
    return total


def line(board: Board) -> str:
    """The board on one line, for example ``1 2 3 | 4 5 6 | 7 8 ·``.

    The rows are separated by ``|``, not ``/``: Cloudflare's API rejects an option name
    that holds ``/``.
    """
    cells = ["·" if tile == 0 else str(tile) for tile in board]
    return " | ".join(" ".join(cells[r * 3:r * 3 + 3]) for r in range(3))


OBJECTIVE = f"put the tiles in order, with the gap in the bottom right corner: {line(SOLVED)}"


def scrambled(rng: Draws, moves: int) -> Board:
    """A random walk of ``moves`` from the solved board that never steps straight back."""
    previous, board = None, SOLVED
    for _ in range(moves):
        options = [child for child in slide(board) if child != previous]
        previous, board = board, rng.choice(options)
    return board


def problem(trial: int, *, heuristic: str, scramble: int) -> Problem:
    """Trial ``trial``, drawn from ``Draws("tiles", trial)``: ``scramble`` random moves from solved."""
    check_heuristic("tiles", heuristic, ("manhattan",))
    rng = Draws("tiles", trial)
    board = SOLVED
    while board == SOLVED:
        board = scrambled(rng, scramble)
    return Problem(
        domain="tiles", trial=trial, start=board, moves=slide, solved=is_solved,
        heuristic=manhattan, heuristic_name="manhattan", render=line, objective=OBJECTIVE, context=CONTEXT)
