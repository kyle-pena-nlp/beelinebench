<!-- Made by `python -m beelinebench readme` from README.template.md. Edit the template, then run the command. -->

# BeelineBench

**How efficiently do decision models navigate multi-step problems?**

BeelineBench measures how well a decision model "plans ahead" when solving a multi-step problem.  A model that navigates more directly to a solution ("beelines") receives a higher score.

In this benchmark, decision models are compared against one another, against classic model-free heuristics, and against a random-choice baseline.  

Classic state-space search (for example: A*) __will almost certainly remain the most efficient technique to solve most of the included problem domains__.  The purpose of this benchmark is to evaluate the multi-step reasoning abilities of decision models, rather than to suggest that decision models should be used as a substitute for classic techniques.

Beeline Bench is configuration-driven and [ready to integrate with your benchmarking suite](docs/lab-integration.md).

## Beeline Score 1.0.0

![The scores of each model and heuristic in benchmark 1.0.0, by domain, with 95% intervals](docs/benchmarks/1.0.0.png)

[All benchmark versions and their score figures](docs/benchmarks/README.md#scores)

### Efficient Frontier for Score and Cost

![The score against the cost of a step for each model in benchmark 1.0.0, by domain, with the efficient frontier](docs/benchmarks/1.0.0-frontier.png)

[All benchmark versions and their score-and-cost figures](docs/benchmarks/README.md#score-and-cost)

### Percent of the time the optimal choice was made

![The percent of decisions that took a state on a shortest path, for each model and heuristic in benchmark 1.0.0, by domain, with 95% intervals](docs/benchmarks/1.0.0-choices.png)

[All benchmark versions and their figures of optimal choices](docs/benchmarks/README.md#optimal-choices)

### Sensitivity studies

Three studies measure how much the score of pplx-decider 1.1 changes on one problem:

- [Representation sensitivity](docs/benchmarks/1.0.0-representation-sensitivity.md)
- [Order sensitivity](docs/benchmarks/1.0.0-order-sensitivity.md)
- [Repeatability](docs/benchmarks/1.0.0-repeatability.md)

### Commentary on 1.0.0

[Commentary on benchmark 1.0.0](docs/benchmarks/1.0.0-commentary.md)

## How It Works

BeelineBench uses the model as the ranker of the frontier in a best-first search. At each step, the search sends all open states to the model in one request. The search stops when it finds the goal.

A beeline score of 1.0 is perfect - the model navigated to the solution in a minimum number of steps. A score of 0.1 means that the model explored ten times as many nodes as necessary. The score of a domain is the geometric mean over its trials, with a 95% interval over 100 random trials from the problem domain.

The score is the number of nodes in the shortest path to the solution divided by the number of nodes that the model explores:


```
score = (shortest path + 1) / nodes explored with the model
```

Before the search, a breadth-first search finds a shortest path to the goal.

BeelineBench also gives other measures on the same trials:

| measure | what it is | where |
|---|---|---|
| heuristic score | the same score for the classic heuristic of the domain. A model is better than the heuristic when its score is higher. | the score figure, and the page of each benchmark |
| random choice | the same score for a chooser that takes a state of the frontier at random. It is the floor: a model below it has choices that carry no information. The figures show it as an open circle. | the score figure, and the page of each benchmark |
| optimal choices | the percent of decisions that took a state on a shortest path, averaged over the trials. A decision counts when the frontier has a state on a shortest path and a state that is not. | the optimal choices figure, and the page of each benchmark |
| oracle score | the same score for a chooser that knows the true distance to the goal. It is below 1.0 only when the frontier limit drops a state of the shortest path. | `report` |
| path score | the shortest path divided by the length of the path that the model found, over the trials that it solved. 1.0 means that the model's path is a shortest path. | `report` |
| refusals | the share of the model's requests that it refused. Only OpenAI's Decisions API refuses. The chooser then asks once more with the options in a new order. If the API refuses that question too, the chooser takes the first option of the new order. | `report`, and [Model quirks](docs/model-quirks.md) |

All benchmark evaluations are capped at 2,500 explored nodes. Model-based runs that did not find a solution within 2,500 explored nodes are marked with an asterisk (*) on the score. Heuristic-based runs that did not find a solution within 2,500 explored nodes are marked with an obelus (†) on the heuristic score. A capped run counts as 2,500 explored nodes.

Aggregated statistics that contain at least one run that did not complete within the 2,500 node limit are marked with these symbols, and a matching footnote contains the number of trials that exceeded the limit.

The frontier holds a maximum of 255 states. If it holds more, the search drops states at random. [The frontier limit of 255 states](#the-frontier-limit-of-255-states) gives the details.

## How to run

These steps run BeelineBench from a clone of the repository. You can also install it as a package, and then run `beelinebench init` in an empty folder. BeelineBench is not on PyPI yet, so install it from GitHub: `pip install "beelinebench[plot] @ git+https://github.com/kyle-pena-nlp/beelinebench"`. [Integrate BeelineBench with your evaluation suite](docs/lab-integration.md) gives the details, and also shows how to run it in a container.

1. Install the dependencies. The `plot` extra draws the figures. The `llm` extra adds the Anthropic SDK, for the `haiku` reference only.

   ```bash
   uv sync --extra plot
   ```

2. Optional: download the data for the `word_ladder` and `wikispeedia` domains. A run also downloads the data of a domain when it needs it. Each download checks the SHA-256 of the data.

   ```bash
   uv run python -m beelinebench download
   ```

3. Put your API keys in `.env`, for example `TYPESAFE_API_KEY` and `ANTHROPIC_API_KEY`.

4. Optional: run the heuristic and the oracle alone. This command sends no requests and costs nothing.

   ```bash
   uv run python -m beelinebench baseline
   ```

5. Run the mini benchmark, then print the report.

   ```bash
   uv run python -m beelinebench run --mini
   uv run python -m beelinebench report
   ```

CAUTION: `run` sends paid API requests. The model sends one request for each node that it explores.

### Run the mini benchmark

The mini benchmark is a small run. By default, it needs one API key, and it runs the first 20 trials of each domain with two fast models from Perplexity: pplx-decider 1.1 and pplx-decider 1.0. Trial n is the same trial as in the full benchmark.

1. Do steps 1 and 2 above.

2. Put your Perplexity key in `.env` as `PERPLEXITY_API_KEY`.

3. Run the mini benchmark, then make the figures and the mini index.

   ```bash
   uv run python -m beelinebench run --mini
   uv run python -m beelinebench readme
   ```

[Price estimates](docs/costs.md) gives the price of a mini run. [The mini benchmarks](docs/benchmarks/mini/README.md) shows the mini results of each version, as figures and as tables.

NOTE: You can change what the mini benchmark runs. The `[mini]` table of `beelinebench.toml` sets the trials and the models. For example, this table runs 10 trials with two models from OpenRouter:

```toml
[mini]
trials = 10
choosers = ["mercury-decide", "d1"]
```

Each model must have a table in `beelinebench.toml`, and you need the key of its provider. If the models come from more than one provider, you need a key for each provider.

### Configuration

`beelinebench.toml` sets the benchmark version, the models (choosers) that `run` uses, and the cost limits:

```toml
[run]
benchmark = "1.0.0"
choosers = ["jev-1.13", "haiku"]
max_cost = 35.0           # US dollars: the most that one model can cost, over all runs
max_total_cost = 165.0    # US dollars: the most that all models together can cost

[chooser."jev-1.13"]
protocol = "jev"
model = "jev-1.13.0"
api_base = "https://api.typesafe.ai/v1"
api_key_env = "TYPESAFE_API_KEY"
max_requests = 200000
max_input_tokens = 714000000
```

Each run stops before a request that starts above a limit. `.spend/<chooser>.json` holds the cost of each model over all runs.

A chooser table can also have these settings:

| setting | what it does |
|---|---|
| `label` | the name of the model in the figures and tables |
| `endpoint` | the path after `api_base`. The default is `systemone`. |
| `served` | the model name that each answer must give, when the API answers with a different name, for example a dated name |
| `price_input`, `price_output` | US dollars for one million input and output tokens. The cost limits and the price estimates use them. |
| `max_cost` | the cost limit of this model. It replaces `[run] max_cost`. |
| `trials` | the trials of this model, for example 5 for a pilot |
| `publish` | `false` leaves the model out of the README, the figures, and the benchmark pages. Its results stay in `results/`. |

The `[mini]` table sets [the mini benchmark](#run-the-mini-benchmark). The `[sensitivity]` table sets the models, the domain, and the conditions of the sensitivity studies.

Command-line flags replace the values in the file for one run:

```bash
uv run python -m beelinebench run --chooser haiku --domain tiles countdown --trials 3
```

Other commands:

| command | what it does |
|---|---|
| `init` | Writes a `beelinebench.toml` to start from, in the working folder. |
| `download` | Downloads the data of the domains that need it. |
| `baseline` | Runs the heuristic and the oracle alone. Sends no requests. |
| `benchmarks` | Lists the official benchmark versions. |
| `choosers` | Lists the choosers in `beelinebench.toml`. |
| `probe` | Sends one question with 255 options to a chooser, and shows the answer. Spends one or two requests. |
| `report` | Prints the scores, the share of solved trials, the served model, and the request times. `--json` gives the same data as JSON. |
| `fill` | Adds the random arm and the counts of optimal choices to old results, from their traces. Sends no requests. |
| `case-study` | Runs the sensitivity studies of the `[sensitivity]` table. Spends money. |
| `agreement` | Sends the traced questions of one chooser to a second chooser, with the same options in the same order, and compares the choices. Records nothing. |
| `plot` | Draws the figures of a benchmark to `docs/benchmarks/`: the scores, the score against the cost, the optimal choices, and the oracle regret. Needs `uv sync --extra plot`. |
| `readme` | Writes this README, the benchmark pages, and the figures from the templates and the results. Runs only in a clone. |

### Choosers

| chooser | model | location |
|---|---|---|
| `jev-1.13` | TypeSafe Jev 1.13 (`jev-1.13.0`) | hosted, `api.typesafe.ai` |
| `luna` | OpenAI GPT-6 Luna, through the Decisions API (`gpt-6-luna`) | hosted, OpenAI. Needs `OPENAI_API_KEY`. |
| `pplx-decider` | Perplexity pplx-decider 1.1 (`pplx-decider-v1.1-27b`) | hosted, Perplexity. Needs `PERPLEXITY_API_KEY`. |
| `pplx-decider-1` | Perplexity pplx-decider 1.0 (`pplx-decider-v1-27b`) | hosted, Perplexity. Needs `PERPLEXITY_API_KEY`. |
| `d1` | Liquid d1 (`liquid/d1-20260930`) | hosted, OpenRouter. Needs `OPENROUTER_API_KEY`. |
| `kev-4b` | Kev 4B, open weights (`jaredpalmer/kev-4b-20260924`). A pilot, not in the results. | hosted, OpenRouter (SiliconFlow). Needs `OPENROUTER_API_KEY`. |
| `mercury-decide` | Inception Mercury Decide (`inception/mercury-decide-20260930`) | hosted, OpenRouter. Needs `OPENROUTER_API_KEY`. |
| `clef` | Cloudflare Clef, 27B (`clef`). A pilot, not in the results. | hosted, Cloudflare Workers AI. Needs `CLOUDFLARE_ACCOUNT_ID` and `CLOUDFLARE_API_TOKEN`. |
| `clef-flash` | Cloudflare Clef-flash, 9B (`clef-flash`). A pilot, not in the results. | hosted, Cloudflare Workers AI. Needs the same two values. |
| `haiku` | Claude Haiku 4.5, as a reference. The README does not show its results. | hosted, Anthropic. Needs `ANTHROPIC_API_KEY`. |
| `clef-local`, `clef-flash-local` | Clef and Clef-flash on your own GPU, at a fixed revision of the weights | local, ports 8001 and 8002 |
| `local` | any model that uses the Jev protocol | local, port 8000 |

A choice model uses the Jev protocol or OpenAI's Decisions API. Jev serves the Jev protocol at `{api_base}/systemone`. Perplexity serves it at `/v1/decisions`, Cloudflare serves it at the name of the model, and OpenRouter serves it at `/api/alpha/decisions` for models of many publishers. OpenAI's Decisions API is at `{api_base}/decisions`. Both get one choice question over the whole frontier, and the chooser takes the option with the highest probability. Each response must name the model that was asked for, or the run stops. If your model is a Python function, `beelinebench.serve` puts it on a local port:

```bash
python -m beelinebench.serve --port 8001 my_model:systemone
```

The function gets the request body (a dict) and returns the response body (a dict).

### Run Clef on your own GPU

[Run Clef on your own GPU](docs/clef-local.md) tells you how to serve Clef and Clef-flash on your own machine and run them with no API key.

### Results files

`run` writes each trial to `results/<benchmark>/<chooser>/<domain>.<heuristic>.jsonl` when the trial ends. If you run again, `run` skips the trials that are already in the file.

If your settings are different from an official benchmark, the results go to `results/custom-<name>/`. `run` lists each setting that is different.

Hosted models can change over time. Each record holds the model name that the API returned (for example `jev-1.13.0`) and the date of the run. A record also holds the scores of the heuristic arm, the oracle arm, and the random arm, and the counts of optimal choices of each arm. For results from before these values existed, `fill` adds them from the traces.

### Trace files

`run` also writes the steps of each trial to `traces/<benchmark>/<chooser>/<domain>.<heuristic>/<trial>.jsonl.gz`. Git ignores these files. The first line of a file describes the trial: the start, the goal, the shortest path, the result, and the served model names. Each other line is one state that the search explored:

| field | what it is |
|---|---|
| `step`, `frontier` | the number of the step, and the number of states on the frontier |
| `forced` | `true` when the frontier had one state, so the search sent no question |
| `chosen` | the state that the model chose |
| `chosen_distance`, `best_distance` | the number of moves to the goal from the chosen state, and from the best state of the frontier |
| `regret` | `chosen_distance` minus `best_distance`. 0 means that the model chose a best state. |
| `best_rank` | the place of the best state in the model's order of probability. 0 is first. |
| `p_chosen` | the probability that the model gave the chosen state |
| `top` | the 5 states with the highest probability, each with its probability and its distance |
| `requests`, `input_tokens`, `output_tokens`, `latencies_ms` | the cost of the step |
| `refusals`, `invalid_answers`, `retries` | the intermittent errors of the step |

A trial that ran before the trace files existed has no trace. To make the traces, run the trials again:

```bash
uv run python -m beelinebench run --chooser <name> --retrace
```

This command runs each trial that has a result and no trace again. The new result replaces the old result, so that the result and the trace come from the same run. The command spends money.

### Clean trials

A trial is clean if it has no refusals, no invalid answers, and no retries. To run the trials that are not clean again, use this command:

```bash
uv run python -m beelinebench run --chooser <name> --rerun-unclean
```

The new run replaces the old run only if the new run has fewer refusals, invalid answers, and retries. The score of the new run has no effect on this decision. Thus, the command cannot select good scores.

## The problems

- **8-puzzle** ([Wikipedia](https://en.wikipedia.org/wiki/15_puzzle)): the player slides eight numbered tiles on a 3 × 3 board, through one gap, until the tiles are in order.
- **Blocksworld** ([Wikipedia](https://en.wikipedia.org/wiki/Blocks_world)): a robot hand moves blocks, one at a time, until the blocks make the goal towers.
- **Countdown** ([Wikipedia](https://en.wikipedia.org/wiki/Countdown_(game_show))): the player combines four numbers with addition, subtraction, multiplication, and division to make a target number.
- **Word ladder** ([Wikipedia](https://en.wikipedia.org/wiki/Word_ladder)): the player changes one letter at a time to get from a start word to a target word, and each step must be a word.
- **Wikispeedia** ([SNAP](https://snap.stanford.edu/data/wikispeedia.html)): the player clicks links from one Wikipedia article to the next, until the player gets to the target article.
- **Rush Hour** ([Wikipedia](https://en.wikipedia.org/wiki/Rush_Hour_(puzzle))): the player slides cars and trucks on a 6 × 6 board until the red car can leave through the exit. A vehicle moves only along its own direction, and other vehicles block the path of the red car. So the player must often move a vehicle out of the way first, and sometimes move a third vehicle to make space for it. The model gets the board as six rows of letters and dots, divided by `|`. BeelineBench makes these boards at random, and each one has a solution.
- **Keys and doors**: the player walks through the rooms of a building to the exit. Each door has a color, and the key of the same color opens it. The keys are in the rooms, and a key can be behind a different door. So the player must sometimes go into a side room for a key, and then go back. The model gets the building as a list of statements in a random order, for example "The red key is behind the blue door." BeelineBench makes these buildings at random, and each one has a solution.

## Price estimates

[Price estimates](docs/costs.md) gives the estimated price of a run for each hosted model: first a mini run, then a full run.

## Fund the benchmark

Each run of a hosted model costs money. The full runs of the six models in 1.0.0 cost about $120 in API fees. The pilots and the sensitivity studies cost about $30 more. The local Clef runs need a rented GPU. To pay for more models and new versions of the benchmark, [sponsor BeelineBench on GitHub](https://github.com/sponsors/kyle-pena-nlp).

## Benchmarks

Benchmark 1.0.0 has 7 domains. Each domain has one heuristic and 100 trials.

### Settings

| domain | heuristic | state | trial |
|---|---|---|---|
| `tiles` | `manhattan` | an 8-puzzle board | 12 random moves from the solved board |
| `blocksworld` | `h_ff` | the true facts for 7 blocks and a hand | random start towers and random goal towers |
| `countdown` | `nearest_number` | the numbers that are left | 4 numbers from 1 to 25, and a target from 10 to 100 |
| `word_ladder` | `letters_different` | a five-letter word | a random word, and a target at least 5 steps away |
| `wikispeedia` | `category_distance` | a Wikipedia article title | an article pair from a completed human game, at least 3 clicks apart |
| `rush_hour` | `blocking_cars` | a 6 × 6 board of vehicles | a random board with the red car and a maximum of 10 other vehicles, at least 6 moves from the solution |
| `keys_doors` | `locked_doors` | the current room, the keys and the open doors | a random building with 10 doors, at least 12 moves from the exit |

All scores use the same scale, where 1.0 is perfect. But some domains are harder than others, so compare scores from two different domains with care.

`benchmarks.toml` holds the exact settings of each version.

Data sources: [Wikispeedia](https://snap.stanford.edu/data/wikispeedia.html) (West and Leskovec), and the word list of Knuth's Stanford GraphBase.

## Limitations

BeelineBench has three known limitations. Each one can change a score.

### The frontier limit of 255 states

A Jev question holds a maximum of 255 options. The search sends the full frontier as one question, so the frontier holds a maximum of 255 states. When the frontier holds more than 255 states, the search drops states at random until 255 states remain.

The heuristic arm, the oracle arm, and the model arm use the same rule. Each arm has its own seeded draws, so a trial drops the same states on each machine. The search forgets a dropped state, so it can find that state again later.

A long search fills the frontier. A Wikipedia article with many links also fills it quickly. For example, "United States" has 294 links. When the limit drops a state of the shortest path, a perfect chooser explores more states. The oracle score shows this effect. In benchmark 1.0.0, the oracle score is 1.000 for each domain except `wikispeedia`, where it is 0.987.

OpenAI's Decisions API accepted a question with 255 options in a test on 2026-10-09. Its documentation gives no limit. BeelineBench uses the limit of 255 for all models, so that all models get the same questions.

### Decision models are sensitive to the presentation

A decision model can give a different answer when it gets the same options in a different form. Two examples are known:

- **The order of the options.** Jev prefers options near the start of a list. Thus, the chooser puts the options in a new random order for each question. The order comes from seeded draws for each trial and model, so the order is the same on each machine.
- **The text of the options.** [JevChat](https://github.com/kyle-pena-nlp/jevchat) uses Jev to write text one symbol at a time. Its author found that Jev chooses much better when each option is the full text so far, not the next symbol alone.

BeelineBench writes the states of a domain in one fixed form. A different form, for example a board as a grid and not as one line, can give a different score. Thus, a score measures a model together with the form of the states, not the model alone. [Representation sensitivity](docs/benchmarks/1.0.0-representation-sensitivity.md) and [order sensitivity](docs/benchmarks/1.0.0-order-sensitivity.md) measure these effects on one problem.

### Some APIs have no seed

The Jev protocol accepts only the fields `model`, `state`, and `questions`. It rejects all other fields, for example `seed` or `temperature`. Jev, pplx-decider, Clef, and the models on OpenRouter use this protocol. BeelineBench also sends no seed to OpenAI's Decisions API.

Identical requests can give different probabilities. In one test, the top option of Jev got 0.78, 0.78, and 0.83 in three calls. A different choice early in a search changes the remainder of the search. Thus, a second run of the same trial can give a different score.

BeelineBench fixes its own random values: the trials, the option order, and the dropped states. It cannot fix the answers of the model, so the results are not fully deterministic. The 95% interval does not include this variation. [Repeatability](docs/benchmarks/1.0.0-repeatability.md) measures it on one problem.

## Model quirks

Some behavior of the models and their APIs can change a score. [Model quirks](docs/model-quirks.md) describes each behavior, and the rule that BeelineBench uses for it: the served model, refusals, dated model names, a short context, models that BeelineBench cannot use, and errors from the APIs.

## How to contribute

[How to contribute](CONTRIBUTING.md) tells you how to add a model, a problem, a protocol, or a benchmark version. AI-assisted code is okay, but a person must write the description of a pull request, and it must match the contents of the pull request in all material ways.

## Related benchmarks

These benchmarks also measure decision models. Each one asks single questions. BeelineBench asks a sequence of questions, in which each choice changes the next question.

- [Decision Index](https://huggingface.co/spaces/multimodalart/jev-decision-index) ([code](https://github.com/apolinario/decision-index), [Cloudflare's copy](https://clef-evals.workers-ai-mle.workers.dev/)): more than 70 decision models, on single questions and games.
- [S1MB](https://huggingface.co/blog/hotchpotch/system-one-mosaic-benchmark) ([code](https://github.com/hotchpotch/S1MB), [leaderboard](https://huggingface.co/spaces/hotchpotch/S1MB-leaderboard)): 137 benchmarks of yes-or-no, choice and score questions, from NLP datasets. A Borda ranking combines them.
- [AIM-Decision](https://aimultiple.com/decision-models) (AIMultiple): 1,655 classification questions, and 50 browser tasks. It compares decision models with general LLMs.
- [OpenRouter decision model rankings](https://openrouter.ai/rankings/decisions): the number of requests to each model. It does not measure accuracy.

## How to cite

If you use BeelineBench, cite it as follows. Give the benchmark version that you used, because the code and the benchmarks have separate versions.

```bibtex
@software{pena2026beelinebench,
  author  = {Pena, Kyle},
  title   = {{BeelineBench}: How Efficiently Do Decision Models Navigate Multi-Step Problems?},
  year    = {2026},
  version = {1.0.0},
  note    = {Benchmark 1.0.0},
  url     = {https://github.com/kyle-pena-nlp/beelinebench}
}
```

If you publish results on the Wikispeedia domain, also cite the two papers of its dataset: West and Leskovec, "Human Wayfinding in Information Networks" (WWW 2012), and West, Pineau, and Precup, "Wikispeedia: An Online Game for Inferring Semantic Distances between Concepts" (IJCAI 2009).

## License

BeelineBench is licensed under the [Apache License, Version 2.0](LICENSE). [NOTICE](NOTICE) lists the third-party data and its terms:

- The word list of the word ladder domain is from Donald E. Knuth's Stanford GraphBase, which is in the public domain.
- The Wikispeedia data is from the [Stanford Network Analysis Project](https://snap.stanford.edu/data/wikispeedia.html). SNAP gives no license for it. Thus, BeelineBench and its Docker image do not include it. A run fetches it from SNAP when it needs it.
