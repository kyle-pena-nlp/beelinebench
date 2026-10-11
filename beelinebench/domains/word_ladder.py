"""Word ladder: change one letter at a time to get from one word to another.

The words are the 5,757 five-letter words of Knuth's Stanford GraphBase
(``www-cs-faculty.stanford.edu/~knuth/sgb-words.txt``). Each step must be a word
of the list. The classic heuristic is the number of letters that differ from the
target.

``python -m beelinebench download`` fetches the list.
"""

from __future__ import annotations

from collections import deque
from collections.abc import Iterable
from functools import partial
from pathlib import Path

from ..rng import Draws
from ..search import Problem, check_heuristic

SOURCE = "https://www-cs-faculty.stanford.edu/~knuth/sgb-words.txt"
#: The SHA-256 of the file at SOURCE. `download` stops if the file has changed.
SHA256 = "52a04f4fb860953c2a29c2769014bd8b12d090a19e7577a460a2a2586bd6d4ce"
DATA = Path("data") / "words" / "sgb-words.txt"

CONTEXT = (
    "Each state is an English word of five letters. A move changes one letter, "
    "and the new word must be a common English word."
)

Ladder = dict[str, tuple[str, ...]]


def load(path: Path) -> Ladder:
    """Each word, and the words one letter away."""
    if not path.exists():
        raise FileNotFoundError(f"no word list at {path}. Run `python -m beelinebench download`.")
    words = sorted({w.strip().lower() for w in path.read_text().split() if w.strip()})
    buckets: dict[str, list[str]] = {}
    for word in words:
        for i in range(len(word)):
            buckets.setdefault(word[:i] + "_" + word[i + 1:], []).append(word)
    return {word: tuple(sorted({other for i in range(len(word))
                                for other in buckets[word[:i] + "_" + word[i + 1:]]
                                if other != word}))
            for word in words}


def neighbours(ladder: Ladder, word: str) -> Iterable[str]:
    return ladder[word]


def reached(target: str, word: str) -> bool:
    return word == target


def letters_different(target: str, word: str) -> int:
    return sum(1 for a, b in zip(word, target) if a != b)


def upper(word: str) -> str:
    return word.upper()


def steps_from(ladder: Ladder, start: str) -> dict[str, int]:
    distance, queue = {start: 0}, deque([start])
    while queue:
        word = queue.popleft()
        for other in ladder[word]:
            if other not in distance:
                distance[other] = distance[word] + 1
                queue.append(other)
    return distance


def problem(trial: int, ladder: Ladder, *, heuristic: str, min_steps: int) -> Problem:
    """Trial ``trial``, drawn from ``Draws("word_ladder", trial)``.

    A random start word, and a random target at least ``min_steps`` steps away.
    """
    check_heuristic("word_ladder", heuristic, ("letters_different",))
    rng = Draws("word_ladder", trial)
    words = sorted(ladder)
    while True:
        start = rng.choice(words)
        far = sorted(w for w, d in steps_from(ladder, start).items() if d >= min_steps)
        if far:
            target = rng.choice(far)
            break
    return Problem(
        domain="word_ladder", trial=trial, start=start, moves=partial(neighbours, ladder),
        solved=partial(reached, target), heuristic=partial(letters_different, target),
        heuristic_name="letters_different",
        render=upper,
        objective=f"reach the word {target.upper()}, changing one letter at a time",
        context=CONTEXT)
