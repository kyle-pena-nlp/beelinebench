"""Random draws that are the same on every machine and every Python version.

``Draws("tiles", 1)`` is the source for trial 1 of the tiles domain. The path is
a list of strings and integers. The seed is the SHA-256 of the path as JSON, so
``"1"`` and ``1`` give different seeds, and the hash seed of the process does
not change anything.

Python keeps the sequence of ``random.Random.random()`` the same across
versions for the same integer seed. It does not keep ``choice``, ``shuffle`` or
``sample`` the same. So this class makes every draw from ``random()``.
"""

from __future__ import annotations

import hashlib
import json
import random
from collections.abc import Sequence
from typing import Any


class Draws:
    def __init__(self, *path: str | int) -> None:
        digest = hashlib.sha256(json.dumps(list(path)).encode()).digest()
        self.source = random.Random(int.from_bytes(digest, "big"))

    def random(self) -> float:
        """A float in [0, 1)."""
        return self.source.random()

    def below(self, n: int) -> int:
        """An integer in [0, n)."""
        return int(self.source.random() * n)

    def choice(self, items: Sequence[Any]) -> Any:
        return items[self.below(len(items))]

    def shuffle(self, items: list[Any]) -> None:
        """Shuffle ``items`` in place (Fisher-Yates)."""
        for i in range(len(items) - 1, 0, -1):
            j = self.below(i + 1)
            items[i], items[j] = items[j], items[i]

    def sample(self, items: Sequence[Any], k: int) -> list[Any]:
        pool = list(items)
        return [pool.pop(self.below(len(pool))) for _ in range(k)]
