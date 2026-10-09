"""Wikispeedia: get from one Wikipedia article to another by clicking links.

The graph is real: 4,604 articles and about 120,000 links, from the data of West
and Leskovec (``snap.stanford.edu/data/wikispeedia.html``). Each instance is a
pair of articles that people played to the end.

The classic heuristic uses the subject categories of the data, for example
``subject.Science.Biology.Birds``. The value is the fewest steps in the category
tree between an article and the target. On a tie, the article with more links
goes first, because a hub reaches more of the graph.

``python -m beelinebench download`` fetches the data.
"""

from __future__ import annotations

from collections import deque
from collections.abc import Iterable
from dataclasses import dataclass
from functools import partial
from pathlib import Path
from urllib.parse import unquote

from ..rng import Draws
from ..search import Problem, check_heuristic

SOURCE = "https://snap.stanford.edu/data/wikispeedia/wikispeedia_paths-and-graph.tar.gz"
DATA = Path("data") / "wikispeedia" / "wikispeedia_paths-and-graph"

#: The category distance of an article that has no category.
NO_CATEGORY = 99

CONTEXT = (
    "Each state is the title of a Wikipedia article. A move is a click on a link "
    "in the article, which leads to another article. Articles link to articles on "
    "related subjects, and an article about a broad subject has many links."
)


@dataclass(frozen=True)
class Graph:
    links: dict[str, tuple[str, ...]]
    categories: dict[str, tuple[tuple[str, ...], ...]]
    #: Every (start, target) pair that a person played to the end.
    games: tuple[tuple[str, str], ...]


def rows(path: Path) -> Iterable[list[str]]:
    """The rows of a file of the data: tab-separated, with ``#`` comments."""
    with path.open(encoding="utf-8") as lines:
        for line in lines:
            line = line.rstrip("\n")
            if line and not line.startswith("#"):
                yield line.split("\t")


def load(directory: Path) -> Graph:
    if not (directory / "links.tsv").exists():
        raise FileNotFoundError(f"no Wikispeedia data in {directory}. Run `python -m beelinebench download`.")
    links: dict[str, list[str]] = {}
    for source, target in rows(directory / "links.tsv"):
        links.setdefault(source, []).append(target)
    categories: dict[str, list[tuple[str, ...]]] = {}
    for article, category in rows(directory / "categories.tsv"):
        categories.setdefault(article, []).append(tuple(category.split(".")))
    games = set()
    for row in rows(directory / "paths_finished.tsv"):
        # A game is "a;b;<;c": the articles in order, and "<" for a click on back.
        visited = [step for step in row[3].split(";") if step != "<"]
        if visited[0] != visited[-1]:
            games.add((visited[0], visited[-1]))
    return Graph(
        links={article: tuple(targets) for article, targets in links.items()},
        categories={article: tuple(paths) for article, paths in categories.items()},
        games=tuple(sorted(games)))


def links_from(graph: Graph, article: str) -> tuple[str, ...]:
    return graph.links.get(article, ())


def reached(target: str, article: str) -> bool:
    return article == target


def tree_distance(a: tuple[str, ...], b: tuple[str, ...]) -> int:
    shared = 0
    while shared < min(len(a), len(b)) and a[shared] == b[shared]:
        shared += 1
    return len(a) + len(b) - 2 * shared


def category_distance(graph: Graph, target: str, article: str) -> tuple[int, int]:
    """The fewest category-tree steps to the target, then minus the number of links."""
    pairs = [tree_distance(a, b) for a in graph.categories.get(article, ())
             for b in graph.categories.get(target, ())]
    return (min(pairs) if pairs else NO_CATEGORY, -len(links_from(graph, article)))


def title(article: str) -> str:
    """An article as a reader sees it: ``"%C3%89douard_Manet"`` is "Édouard Manet"."""
    return unquote(article).replace("_", " ")


def fewest_clicks(graph: Graph, start: str, target: str) -> int | None:
    seen, queue = {start: 0}, deque([start])
    while queue:
        article = queue.popleft()
        if article == target:
            return seen[article]
        for linked in links_from(graph, article):
            if linked not in seen:
                seen[linked] = seen[article] + 1
                queue.append(linked)
    return None


def problem(trial: int, graph: Graph, *, heuristic: str, min_clicks: int) -> Problem:
    """Trial ``trial``, drawn from ``Draws("wikispeedia", trial)``.

    A random game that a person finished, of at least ``min_clicks`` clicks.
    """
    check_heuristic("wikispeedia", heuristic, ("category_distance",))
    rng = Draws("wikispeedia", trial)
    start, target = rng.choice(graph.games)
    while (fewest_clicks(graph, start, target) or 0) < min_clicks:
        start, target = rng.choice(graph.games)
    return Problem(
        domain="wikispeedia", trial=trial, start=start,
        moves=partial(links_from, graph), solved=partial(reached, target),
        heuristic=partial(category_distance, graph, target),
        heuristic_name="category_distance", render=title,
        objective=(f'reach the Wikipedia article "{title(target)}" by clicking '
                   "links from one article to the next"),
        context=CONTEXT)
