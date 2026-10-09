<!-- Made by `python -m beelinebench readme` from CONTRIBUTING.template.md. Edit the template, then run the command. -->

# How to contribute

You can contribute a new model, a new problem (domain), or a new benchmark version. Open a pull request with the code, the results, and the README.

New models and new benchmarks are considered minor semver version increments.
Removals of existing benchmarks or changes in methodology that affect scores are considered major version increments.
Include a description of why your change is an improvement in your PR.  
AI-generated and AI-assisted code is okay, but the description of the PR must be human written and the description must match the PR's contents.
AI-generated summaries or summaries which do not match the content of the PR in a material way will be rejected, regardless of merits.

## What makes a good problem

The best new problem shows a difference between models that the other problems do not show. Before you write the code, compare your idea with this list.

- **It has a clear goal and a clear move.** A model must understand the goal and each state from one line of text. Two states must not have the same text.
- **Its shortest path is known.** The breadth-first search visits each state that the start can reach. Thus, the state space must fit in the memory of one machine. The 8-puzzle has 181,440 states.
- **It has space above and below the heuristic.** A good heuristic score is between 0.1 and 0.8. If the heuristic is near 1.0, models cannot do better. If the heuristic often stops at the limit, the trials are too slow.
- **It is different from the problems that exist.** The problems now test spatial moves, symbolic planning, arithmetic, word changes, and knowledge of Wikipedia. A new kind of planning adds the most.
- **It tests planning, not memory.** A model can know a famous puzzle from its training data. A problem that a computer generates, with names that have no meaning, gives a better test.
- **It is the same on each machine.** Each trial must come from seeded draws. [Add a problem](#add-a-problem) gives the rules.
- **It is cheap to run.** The model gets each frontier state as one option, in each request. Thus, a long state text makes each request expensive.

To examine an idea, write the module. Then add an experiment benchmark with your domain to `beelinebench.toml`:

```toml
[benchmark.my-problem]
trials = 20
max_expansions = 2500
max_frontier = 255

[benchmark.my-problem.domains.<name>]
heuristic = "<heuristic>"
```

Run the heuristic and the oracle alone. This command sends no requests:

```bash
uv run python -m beelinebench baseline --benchmark my-problem
```

Look at the heuristic score, the oracle score, and the time. If the heuristic score is between 0.1 and 0.8 and the oracle score is near 1.0, the problem is a good candidate.

## What makes a good model to add

- **It is a decision model.** It answers a choice question with a probability for each option. A general language model can be a reference, but the README does not show it. [The Claude reference](docs/model-quirks.md#the-claude-reference) gives the reason.
- **It accepts 255 options in one question.** If it accepts fewer options, the frontier limit changes for that model, and its scores are not comparable.
- **It names a fixed version.** Each response must give the name of the model that answered. An alias that changes to a new model makes old results wrong.
- **Other people can use it.** It is a public API or a model with open weights. A private model makes results that nobody can repeat.

## Add a model

A model can use the Jev protocol, OpenAI's Decisions API, or the Anthropic API. If it uses a different API, first do the steps in [Add a protocol](#add-a-protocol).

1. Add a `[chooser.<name>]` table to `beelinebench.toml`. The comments at the top of the file describe each setting.
2. If the API has model versions, set `model` to one version, for example `jev-1.13.0`. Each response must give that name. If the API answers with a different name, for example a dated name, set `served` to that name.
3. Set `price_input` and `price_output` to the list prices of the provider, in US dollars for a million tokens.
4. Put the key in `.env`, with the name that `api_key_env` gives.
5. Send one question with 255 options to the model:

   ```bash
   uv run python -m beelinebench probe --chooser <name>
   ```

   If the command fails, read the error. [Model quirks](docs/model-quirks.md) gives the known errors.
6. Run 5 trials of each domain:

   ```bash
   uv run python -m beelinebench run --chooser <name> --trials 5
   uv run python -m beelinebench report
   ```

7. Look at the input tokens in the report, and calculate the price of a full run. If the price is too high, stop here.
8. Run the full benchmark. The run starts after the trials that are in `results/` already.

   ```bash
   uv run python -m beelinebench run --chooser <name>
   ```

9. Run `uv run python -m beelinebench readme`. Then commit the results, `README.md`, and the figure.

If the total cost of the model gets to the `max_cost` limit of `[run]` ($35 now), the limit stops the run. To change the limit for one model, set `max_cost` in its table. If the model has a behavior that changes its score, add it to [Model quirks](docs/model-quirks.md).

## Add a protocol

A chooser is a function that gets the frontier and returns the index of the state to explore:

```python
def choose(states: Sequence[State]) -> int: ...
```

`beelinebench/jev.py`, `beelinebench/decisions.py`, and `beelinebench/llm.py` are examples. `beelinebench/config.py` selects the chooser from the configuration file. A new chooser must obey these rules:

- Send the full frontier in one request, in the order that the `order` draws give.
- Count each request in the `Spend` object, so that the cost limit and the report are correct.
- Make sure that each response gives the name of the requested model.
- If the model gives no valid answer, count an invalid answer, and take the first state of the shuffled list.

## Add a problem

Before you start, read [What makes a good problem](#what-makes-a-good-problem).

1. Add a module to `beelinebench/domains/`. Give it a function `problem(trial, *, heuristic, ...)` that returns a `Problem`.
2. Make each trial from `Draws("<domain>", trial)` only. Do not use the `random` module, `hash()`, or the order of a set. Then each trial is the same on each machine.
3. Write each state on one line with `render`. Two states must not have the same text.
4. Add the domain to `maker` in `beelinebench/__main__.py`.
5. Add its name and the name of its heuristic to `TITLES` and `HEURISTIC_TITLES` in `beelinebench/domains/__init__.py`.
6. If the domain needs no downloaded data, add it to `tests/test_portable.py`.
7. Add the domain to a new benchmark version. [Add a benchmark version](#add-a-benchmark-version) gives the steps.

The breadth-first search visits each state that the start can reach, to find the shortest path. Thus, the state space must be small enough for the memory of one machine. The 8-puzzle, with 181,440 states, is the largest domain now.

## Add a benchmark version

A new version adds a table to `benchmarks.toml`. Do not change or remove an existing table. Old versions must stay runnable.

1. Add the table for the new version to `benchmarks.toml`.
2. Run `uv run python -m beelinebench publish <version>`. This command writes the page, and writes the index `docs/benchmarks/README.md` again.
3. On the new page, describe what the version changes.
4. When the version has results, write its commentary in `docs/benchmarks/<version>-commentary.md`: the main findings, by hand. `readme` puts it in the README and on the page of the version.
5. Add the change to `CHANGELOG.md`.

Use the version number for the type of change:

| part | change |
|---|---|
| MAJOR | the search, the score, the limits, the frontier, a heuristic, or how trials are made. Scores from two major versions are not comparable. |
| MINOR | the text that the model sees, a new domain, or a new heuristic |
| PATCH | a fix that changes no score |

If you change the text that the model sees, include the scores from the old version and the new version.

## Edit this README

`README.md` is a generated file. Do not edit it. Edit `README.template.md`, then run this command:

```bash
uv run python -m beelinebench readme
```

The command replaces each placeholder in the template with its current value from `benchmarks.toml` and `results/`. It also draws the figure of the results again, if the results changed. The figure needs matplotlib (`uv sync --extra plot`). Run the command again after you add results. Commit `README.md`, the figure, and the template together.

To show a placeholder as text, put a backslash before it: `\{{`.

| placeholder | value |
|---|---|
| `{{ latest_benchmark }}` | the newest official benchmark version |
| `{{ latest_benchmark_link }}` | a link to the page of the newest version. The page shows its figures, and the same data as tables. `{{ latest_benchmark_link 1.0.0 }}` links the page of version 1.0.0. |
| `{{ results_figure }}` | the figure of scores for the newest version, as an image. `{{ results_figure 1.0.0 }}` gives the figure for version 1.0.0. |
| `{{ frontier_figure }}` | the figure of score against the cost of a step, with the efficient frontier, for the newest version. |
| `{{ results }}` | the table of scores for the newest version. `{{ results 1.0.0 }}` gives the table for version 1.0.0. |
| `{{ trials }}` | the number of trials for each domain |
| `{{ max_expansions }}` | the explored-node limit of each run, for example 2,500 |
| `{{ domain_count }}` | the number of domains |
| `{{ refusals luna }}` | the refusals of a chooser in the newest version: the total, and a table for each domain |

## Run the tests

```bash
uv run pytest
uv run python -m beelinebench check-docs
uv run python -m beelinebench readme --check
```

The tests need no API key and no network. CI runs these commands on each push and pull request. If `README.md` is different from the output of the template, `readme --check` fails. It also fails if the figure does not show the current results. CI does not run the benchmarks.

[Back to the README](README.md)
