<!-- Made by `python -m beelinebench readme` from README.template.md. Edit the template, then run the command. -->

# BeelineBench

**How efficiently do decision models navigate multi-step problems?**

BeelineBench measures how well a choice model guides a best-first search against a state-space representing a classic problem solving domain.  In multi-step problems (like blockworld or sliding tile puzzles), a model that navigates more directly to a solution "plans ahead" better.  This benchmark measures how efficiently Jev and other choice models navigate to a solution, compared to a perfect search along the shortest path.

## Benchmark (Higher is Better)

Scores for benchmark 1.0.0, from the files in `results/1.0.0/`:

![The scores of each model and heuristic in benchmark 1.0.0, by domain, with 95% intervals](docs/benchmarks/1.0.0.png)

For the numbers, run `uv run python -m beelinebench report`.

[`docs/benchmarks/README.md`](docs/benchmarks/README.md) is the index of benchmark versions. Each version has a page with its settings, its changes, and its results.

## Introduction

BeelineBench uses the model as the ranker in a best-first search. At each step, the search sends all open states (the frontier) to the model in one request. The search stops when it finds the goal.

Before the search, a breadth-first search finds the shortest path to the goal. A perfect chooser explores only the states of that path, the start and the goal included. The score is the number of nodes that a perfect chooser explores divided by the number of nodes that the model explores:

```
score = (shortest path + 1) / nodes explored with the model
```

A score of 1.0 is perfect. A score of 0.1 means that the model explored ten times as many nodes as necessary. The score of a domain is the geometric mean over its trials, with a 95% bootstrap interval.

The table shows three other columns on the same trials:

| column | what it is |
|---|---|
| heuristic score | the same score for the classic heuristic of the domain. A model is better than the heuristic when its score is higher. |
| oracle score | the same score for a chooser that knows the true distance to the goal. It is below 1.0 only when the frontier limit drops a state of the shortest path. |
| path score | the shortest path divided by the length of the path that the model found, over the trials that it solved. 1.0 means that the model's path is a shortest path. |
| refusals | the share of the model's requests that it refused. Only OpenAI's Decisions API refuses. The chooser then asks once more with the options in a new order, and if that is refused too, it takes the first option. |

The score measures how many choices the model wasted. The path score measures how good the model's plan is. A model can explore many dead ends and still find a short path, or go directly along a long path.

All benchmark evaluations are capped at 2,500 explored nodes. Model-based runs that did not find a solution within 2,500 explored nodes are marked with an asterisk (*) on the score. Heuristic-based runs that did not find a solution within 2,500 explored nodes are marked with an obelus (†) on the heuristic score. A capped run counts as 2,500 explored nodes.

Aggregated statistics that contain at least one run that did not complete within the 2,500 node limit are marked with these symbols, and a matching footnote contains the number of trials that exceeded the limit.

The frontier holds a maximum of 255 states. If it holds more, the search drops states at random. [Model quirks and limits](#model-quirks-and-limits) gives the details.

## How to run

1. Install the dependencies. The `llm` extra adds the Anthropic SDK.

   ```bash
   uv sync --extra llm
   ```

2. Download the data for the `word_ladder` and `wikispeedia` domains.

   ```bash
   uv run python -m beelinebench download
   ```

3. Put your API keys in `.env`, for example `TYPESAFE_API_KEY` and `ANTHROPIC_API_KEY`.

4. Optional: run the heuristic and the oracle alone. This command sends no requests and costs nothing.

   ```bash
   uv run python -m beelinebench baseline
   ```

5. Run the benchmark, then print the report.

   ```bash
   uv run python -m beelinebench run
   uv run python -m beelinebench report
   ```

CAUTION: `run` sends paid API requests. The model sends one request for each state that it explores.

### Configuration

`beelinebench.toml` sets the benchmark version and the models (choosers) that `run` uses:

```toml
[run]
benchmark = "1.0.0"
choosers = ["jev-1.13", "haiku"]

[chooser."jev-1.13"]
protocol = "jev"
model = "jev-1.13.0"
api_base = "https://api.typesafe.ai/v1"
api_key_env = "TYPESAFE_API_KEY"
max_requests = 200000
max_input_tokens = 714000000
```

Command-line flags replace the values in the file for one run:

```bash
uv run python -m beelinebench run --chooser haiku --domain tiles countdown --trials 3
```

Other commands:

| command | what it does |
|---|---|
| `benchmarks` | Lists the official benchmark versions. |
| `choosers` | Lists the choosers in `beelinebench.toml`. |
| `report` | Prints the scores, the share of solved trials, the served model, and the request times. |
| `plot` | Draws the scores of a benchmark to `docs/benchmarks/<version>.png`, one row for each model in each domain, with the 95% interval. Needs `uv sync --extra plot`. |

### Choosers

| chooser | model | location |
|---|---|---|
| `jev-1.13` | TypeSafe Jev 1.13 (`jev-1.13.0`) | hosted, `api.typesafe.ai` |
| `luna` | OpenAI GPT-6 Luna, through the Decisions API (`gpt-6-luna`) | hosted, OpenAI. Needs `OPENAI_API_KEY`. |
| `pplx-decider` | Perplexity pplx-decider 1.1 (`pplx-decider-v1.1-27b`) | hosted, Perplexity. Needs `PERPLEXITY_API_KEY`. |
| `clef` | Cloudflare Clef, 27B (`clef`) | hosted, Cloudflare Workers AI. Needs `CLOUDFLARE_ACCOUNT_ID` and `CLOUDFLARE_API_TOKEN`. |
| `clef-flash` | Cloudflare Clef-flash, 9B (`clef-flash`) | hosted, Cloudflare Workers AI. Needs the same two values. |
| `haiku` | Claude Haiku 4.5, as a reference. The README does not show its results. | hosted, Anthropic. Needs `ANTHROPIC_API_KEY`. |
| `clef-local`, `clef-flash-local` | Clef and Clef-flash on your own GPU | local, ports 8001 and 8002 |
| `local` | any model that uses the Jev protocol | local, port 8000 |

A choice model uses the Jev protocol or OpenAI's Decisions API. Jev serves the Jev protocol at `{api_base}/systemone`. Perplexity serves it at `/v1/decisions`, and Cloudflare serves it at the name of the model. OpenAI's Decisions API is at `{api_base}/decisions`. Both get one choice question over the whole frontier, and the chooser takes the option with the highest probability. Each response must name the model that was asked for, or the run stops. If your model is a Python function, `beelinebench.serve` puts it on a local port:

```bash
python -m beelinebench.serve --port 8001 my_model:systemone
```

The function gets the request body (a dict) and returns the response body (a dict).

### Run Clef on your own GPU

Cloudflare Workers AI hosts Clef and Clef-flash, and the `clef` and `clef-flash` choosers use that service. You can also run the models on your own GPU, with the `clef-local` and `clef-flash-local` choosers. `examples/clef.py` loads the model from Hugging Face and serves it with `beelinebench.serve`.

| model | parameters | memory in bfloat16 | chooser | port |
|---|---|---|---|---|
| Clef | 27B | about 55 GB | `clef-local` | 8001 |
| Clef-flash | 9B | about 19 GB | `clef-flash-local` | 8002 |

The model cards test on one H200 GPU. An 80 GB GPU holds both models. A Mac with 24 GB of memory cannot hold Clef, and Clef-flash on it is slow.

1. On the GPU machine, install BeelineBench with the Clef dependencies.

   ```bash
   uv sync --extra clef
   ```

2. Start one server for each model. The first start downloads the model.

   ```bash
   uv run python -m beelinebench.serve --port 8001 examples.clef:systemone
   CLEF_REPO=Cloudflare/clef-flash uv run python -m beelinebench.serve --port 8002 examples.clef:systemone
   ```

3. If the GPU machine is not the machine that runs BeelineBench, forward the ports over SSH. The servers listen only on `127.0.0.1`.

   ```bash
   ssh -N -L 8001:localhost:8001 -L 8002:localhost:8002 <gpu-host>
   ```

4. Run the benchmark.

   ```bash
   uv run python -m beelinebench run --chooser clef-local
   uv run python -m beelinebench run --chooser clef-flash-local
   ```

`examples/clef.py` uses `cuda` if it is available, then `mps`, then `cpu`. To select a device, set `CLEF_DEVICE`. Clef does not sample, so identical requests give the same probabilities on the same device.

The `haiku` chooser uses the Anthropic API. It is a reference point, not a choice model. It can reason before it answers, and the choice models cannot. Thus, its score does not measure the same ability. The setting `publish = false` in `beelinebench.toml` keeps its results out of the README figure, the results table, and the price estimates. Its results stay in `results/`, and `report` shows them.

### Results files

`run` writes each trial to `results/<benchmark>/<chooser>/<domain>.<heuristic>.jsonl` when the trial ends. If you run again, `run` skips the trials that are already in the file.

If your settings are different from an official benchmark, the results go to `results/custom-<name>/`. `run` lists each setting that is different.

Hosted models can change over time. Each record holds the model name that the API returned (for example `jev-1.13.0`) and the date of the run.

## Price estimates

A full run of benchmark 1.0.0 has 100 trials for each of its 5 domains. The table gives the estimated price of one full run for each hosted model.

| model | price for a million tokens | input tokens of a full run | estimated price of a full run | basis |
|---|---|---|---|---|
| Jev 1.13 | $0.042 input, output free | 119 million | $4.99 | measured on 100 trials |
| GPT-6 Luna (Decisions) | $0.10 input, output free | 111 million | $11.08 | measured on 349 trials; token counts of Jev 1.13 |
| pplx-decider 1.1 | $0.02 input, output free | 158 million | $3.16 | measured on 18 trials; token counts of GPT-6 Luna (Decisions), Jev 1.13 |
| Clef | $0.24 input, output free | 111 million | $26.59 | token counts of GPT-6 Luna (Decisions), Jev 1.13 |
| Clef-flash | $0.09 input, output free | 111 million | $9.97 | token counts of GPT-6 Luna (Decisions), Jev 1.13 |

The estimate uses the mean input tokens and output tokens of a trial in `results/`. If a model has no results for a domain, the estimate uses the token counts of a different model. The basis column gives the source of the token counts.

A borrowed estimate is approximate. A model that explores more states sends more requests, so it uses more tokens. Also, each tokenizer counts the same text differently.

The prices come from `price_input` and `price_output` in `beelinebench.toml`. They are list prices in US dollars from October 2026, and the providers can change them. Workers AI gives each account 10,000 Neurons free each day, so a small run of Clef can cost less.

The table does not include local models. A local model has no price for each token, but it needs a GPU. [Run Clef on your own GPU](#run-clef-on-your-own-gpu) gives the details.

## Benchmarks

Benchmark 1.0.0 has 5 domains. Each domain has one heuristic and 100 trials.

| domain | heuristic | state | trial |
|---|---|---|---|
| `tiles` | `manhattan` | an 8-puzzle board | 12 random moves from the solved board |
| `blocksworld` | `h_ff` | the true facts for 7 blocks and a hand | random start towers and random goal towers |
| `countdown` | `nearest_number` | the numbers that are left | 4 numbers from 1 to 25, and a target from 10 to 100 |
| `word_ladder` | `letters_different` | a five-letter word | a random word, and a target at least 5 steps away |
| `wikispeedia` | `category_distance` | a Wikipedia article title | an article pair from a completed human game, at least 3 clicks apart |

All scores use the same scale, where 1.0 is perfect. But some domains are harder than others, so compare scores from two different domains with care.

`benchmarks.toml` holds the exact settings of each version.

Data sources: [Wikispeedia](https://snap.stanford.edu/data/wikispeedia.html) (West and Leskovec), and the word list of Knuth's Stanford GraphBase.

## Model quirks and limits

Some behavior of the models and their APIs can change a score. This section describes each behavior, and the rule that BeelineBench uses for it.

### The frontier limit of 255 states

A Jev question holds a maximum of 255 options. The search sends the full frontier as one question, so the frontier holds a maximum of 255 states. If the frontier holds more than 255 states, the search drops states at random until 255 states remain. The heuristic arm, the oracle arm, and the model arm use the same rule. Each arm has its own seeded draws, so a trial drops the same states on each machine. The search forgets a dropped state, so it can find that state again later.

The frontier grows with each explored state, so a long search can fill it. A Wikipedia article with many links also fills it quickly. For example, "United States" has 294 links. The limit can drop a state of the shortest path. The oracle score shows this effect. In benchmark 1.0.0, the oracle score is 1.000 for four domains and 0.989 for `wikispeedia`.

OpenAI's Decisions API accepted a question with 255 options in a test on 2026-10-09. Its documentation gives no limit.

### Each answer must come from the requested model

A hosted model name, for example an alias such as `jev-latest`, can point to a different model on a later day. Thus, each response must give the name of the model that `beelinebench.toml` requests. If the name is different or missing, the run stops. BeelineBench does not record that trial.

### The order of the options

Jev prefers options near the start of a list. Thus, the chooser puts the options in a new random order for each question. The order comes from seeded draws for each trial and model, so the order is the same on each machine.

### The Jev API has no seed

The Jev API accepts only the fields `model`, `state`, and `questions`. It rejects all other fields, for example `seed` or `temperature`. Identical requests can give different probabilities. In one test, the top option got 0.78, 0.78, and 0.83 in three calls. A different choice early in a search changes the remainder of the search. Thus, a second run of the same trial can give a different score.

BeelineBench fixes its own random values: the trials, the option order, and the dropped states. It cannot fix the answers of the model. The 95% interval does not include this variation.

### OpenAI's Decisions API can refuse a question

The Decisions API can answer a question with the type `refusal` and no choice. OpenAI does not document the cause, and the API has no setting for it. In a first partial run, the API refused 34 of 746 questions (4.6%) on the 8-puzzle. The puzzle text is harmless.

A refusal depends on the exact request. In a test, the API refused the same request five times. The same options in a different order got an answer. A different symbol for the gap, different instructions, or fewer options also got an answer.

When the API refuses a question, the chooser asks once more, with the options in a new seeded order. If the API refuses again, the chooser takes the first option of the second order. Each refusal is a request, so it counts toward the request limit and the input tokens. The `refusals` column gives the share of requests that the API refused.

### Cloudflare rejects an option that contains a slash

Cloudflare's API for Clef returns the status 400 if an option name contains the character `/`. The error message says that `model`, `state`, and `questions` are missing, but the request contains them. The 8-puzzle uses `/` to divide the rows of a board. Thus, each 8-puzzle question fails.

The `clef` and `clef-flash` choosers send `|` in place of `/`. Only the option names must not contain `/`. The replacement also applies to the goal and the context, so the model sees one notation. The `replace` setting in `beelinebench.toml` controls it. The other choosers send `/`.

### Errors from the APIs

If an API returns the status 429, 500, 502, 503, 504, or 529, the client sends the request again. It sends the request a maximum of five times. If the account has no credits, OpenAI also returns the status 429. Cloudflare returns 429 when the account uses all of its free allocation for the day. For these two errors, the client does not send the request again, and the run stops. BeelineBench does not record the trial that was in progress.

### The Claude reference

The `haiku` chooser uses the default temperature of the Anthropic API, and that API has no seed. Thus, identical requests can give different answers. The model can also reason before it answers, and the choice models cannot. Thus, its score does not measure the same ability, and the README does not show it.

## How to contribute

### Add a benchmark version

A new version adds a table to `benchmarks.toml`. Do not change or remove an existing table. Old versions must stay runnable.

1. Add the table for the new version to `benchmarks.toml`.
2. Run `uv run python -m beelinebench publish <version>`. This command writes the page and adds it to the index.
3. On the new page, describe what the version changes.
4. Add the change to `CHANGELOG.md`.

Use the version number for the type of change:

| part | change |
|---|---|
| MAJOR | the search, the score, the limits, the frontier, a heuristic, or how trials are made. Scores from two major versions are not comparable. |
| MINOR | the text that the model sees, a new domain, or a new heuristic |
| PATCH | a fix that changes no score |

If you change the text that the model sees, include the scores from the old version and the new version.

### Add a domain

A good domain has a reasonable heuristic that is not near perfect. Its frontier must fit in one request (255 states). Its trials must finish in a reasonable time. Put new domains in `beelinebench/domains/`.

### Add a protocol

A chooser is a function that gets the frontier and returns the index of the state to explore:

```python
def choose(states: Sequence[State]) -> int: ...
```

`beelinebench/jev.py` and `beelinebench/llm.py` are examples. `beelinebench/config.py` selects the chooser from the configuration file.

### Edit this README

`README.md` is a generated file. Do not edit it. Edit `README.template.md`, then run this command:

```bash
uv run python -m beelinebench readme
```

The command replaces each placeholder in the template with its current value from `benchmarks.toml` and `results/`. It also draws the figure of the results again, if the results changed. The figure needs matplotlib (`uv sync --extra plot`). Run the command again after you add results. Commit `README.md`, the figure, and the template together.

To show a placeholder as text, put a backslash before it: `\{{`.

| placeholder | value |
|---|---|
| `{{ latest_benchmark }}` | the newest official benchmark version |
| `{{ results_figure }}` | the figure of scores for the newest version, as an image. `{{ results_figure 1.0.0 }}` gives the figure for version 1.0.0. |
| `{{ results }}` | the table of scores for the newest version. `{{ results 1.0.0 }}` gives the table for version 1.0.0. |
| `{{ trials }}` | the number of trials for each domain |
| `{{ max_expansions }}` | the explored-node limit of each run, for example 2,500 |
| `{{ domain_count }}` | the number of domains |

### Run the tests

```bash
uv run pytest
uv run python -m beelinebench check-docs
uv run python -m beelinebench readme --check
```

The tests need no API key and no network. CI runs these commands on each push and pull request. If `README.md` is different from the output of the template, `readme --check` fails. It also fails if the figure does not show the current results. CI does not run the benchmarks.

## Decision Index

The [Decision Index](https://huggingface.co/spaces/multimodalart/jev-decision-index) ([code](https://github.com/apolinario/decision-index), [leaderboard](https://clef-evals.workers-ai-mle.workers.dev/)) measures more than 70 decision models, including Jev and Cloudflare Clef.

The two benchmarks measure different things:

| | Decision Index | BeelineBench |
|---|---|---|
| task | answer one question, or play a game | rank the frontier at each step of a search |
| score | correct answers, or the game result | states explored to reach the goal |
| reference | the correct answers, and chance | the shortest path, and a classic heuristic on the same problem |
| protocol | Jev `systemone`, and the native API of each model | Jev `systemone` |

A model can make good single choices and still lead a search on a long path. Only a sequence of choices shows this difference.

We want to add BeelineBench to the Decision Index, for example as a search track. BeelineBench already has one protocol, fixed seeds, fixed limits, and versioned benchmarks. We can change the score or the report to match the Index. To discuss this, open an issue.
