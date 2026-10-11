"""How well a choice model ranks the frontier of a best-first search.

The score of a model on one instance is the nodes that a classic heuristic
explores, divided by the nodes that the model explores. ``README.md`` has the
method, and ``CHANGELOG.md`` has what each version changed.
"""

from importlib.metadata import version

#: The version of the code, from ``pyproject.toml``: the one place that sets it. The
#: benchmarks have their own versions, in ``benchmarks.toml``, and the code runs every one
#: of them.
VERSION = version("beelinebench")
