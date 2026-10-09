<!-- Made by `python -m beelinebench readme` from README.template.md. Edit the template, then run the command. -->

# BeelineBench

**How efficiently do decision models navigate multi-step problems?**

BeelineBench measures how well a decision model "plans ahead" when solving a multi-step problem.  A model that navigates more directly to a solution ("beelines") receives a higher score.

Models are compared against one another and also against classic model-free heuristics and a random-choice baseline.  

Classic state-space search (for example: A*) will almost certainly remain the most sensible and economically efficient technique to solve most of these problem domains.  The purpose of this benchmark is to evaluate the multi-step reasoning abilities of decision models, rather than to suggest that decision models should be used as a substitute for classic techniques.  

## Benchmark (Higher is Better)

Latest: [1.0.0](docs/benchmarks/1.0.0.md)

![The scores of each model and heuristic in benchmark 1.0.0, by domain, with 95% intervals](docs/benchmarks/1.0.0.png)

[All benchmark versions and their score figures](docs/benchmarks/README.md#scores)

### Commentary

These findings come from the partial results of 2026-10-09. Some models have results for some problems only.

**1. GPT-6 Luna refuses many of its questions.** OpenAI's Decisions API refused 86% of the Rush Hour requests of GPT-6 Luna. When the API refuses a question two times, the search takes a fallback state. Thus, 75% of the Rush Hour decisions of Luna are the fallback, and its Rush Hour score measures the fallback more than the model. OpenAI bills each refused request.

The refusals increase with the number of options. In the traces of 2026-10-09, Luna refused 0% to 8% of the Rush Hour questions with 25 options or fewer. It refused 87% of those with 255 options. Wikispeedia, word ladder, and the 8-puzzle show the same increase, at lower rates.

The content of the options does not explain the refusals. When we sent 18 refused questions again, the API refused 15 of them again. Titles such as "Nazism" and "The Holocaust" were on the frontier as frequently for answered questions as for refused questions. Four other formats of the Rush Hour board did not stop the refusals. OpenAI does not document the cause.

In Wikispeedia trial 53, two full runs gave the same 2,521 refusals. At step 4, the target article was an option, and Luna chose a different article. The search did not find the target again, and the refusals started at step 188. The other models solved this trial with 3 requests.

**2. The models do better than the heuristic on Wikispeedia and Countdown.** On Wikispeedia, each model scores above the heuristic. The heuristic compares only the categories of two articles, but a model knows which subjects are related. On Countdown, most models score above the heuristic.

**3. The heuristic does better than the models on the 8-puzzle, Blocksworld, and word ladder.** On these three problems, the heuristic scores above each model. A good distance estimate exists for each of them, and the models do not match it.


### Efficient Frontier for Score and Cost

![The score against the cost of a step for each model in benchmark 1.0.0, by domain, with the efficient frontier](docs/benchmarks/1.0.0-frontier.png)

[All benchmark versions and their score-and-cost figures](docs/benchmarks/README.md#score-and-cost)

### Percent of the time the optimal choice was made

![The share of decisions that matched the oracle for each model and heuristic in benchmark 1.0.0, by domain, with 95% intervals](docs/benchmarks/1.0.0-choices.png)

[All benchmark versions and their choice figures](docs/benchmarks/README.md#choices-against-the-oracle)

The score measures a full search. This figure measures each choice. At each step with two or more open states, a choice matches the oracle when it takes a state with the fewest moves to the goal. The oracle regret of a choice is the extra moves to the goal from the chosen state. The page of each benchmark gives the mean regret for each model and problem.

### Robustness case study

The [robustness case study](docs/benchmarks/1.0.0-robustness-case-study.md) measures how the text of the states and the order of the options change the score of one model on one problem.

## How It Works

BeelineBench uses the model as the ranker of the frontier in a best-first search. At each step, the search sends all open states to the model in one request. The search stops when it finds the goal.

A score of 1.0 is perfect - the model navigated to the solution in a minimum number of steps. A score of 0.1 means that the model explored ten times as many nodes as necessary. The score of a domain is the geometric mean over its trials, with a 95% interval over 100 random trials from the problem domain.

The score is the number of nodes in the shortest path to the solution divided by the number of nodes that the model explores:


```
score = (shortest path + 1) / nodes explored with the model
```

Before the search, a breadth-first search finds a shortest path to the goal.

The table shows three other columns on the same trials:

| column | what it is |
|---|---|
| heuristic score | the same score for the classic heuristic of the domain. A model is better than the heuristic when its score is higher. |
| oracle score | the same score for a chooser that knows the true distance to the goal. It is below 1.0 only when the frontier limit drops a state of the shortest path. |
| random choice | the same score for a chooser that takes a state of the frontier at random. It is the floor: a model below it has choices that carry no information. The figure shows it as an open circle. |
| path score | the shortest path divided by the length of the path that the model found, over the trials that it solved. 1.0 means that the model's path is a shortest path. |
| refusals | the share of the model's requests that it refused. Only OpenAI's Decisions API refuses. The chooser then asks once more with the options in a new order, and if that is refused too, it takes the first option. |

All benchmark evaluations are capped at 2,500 explored nodes. Model-based runs that did not find a solution within 2,500 explored nodes are marked with an asterisk (*) on the score. Heuristic-based runs that did not find a solution within 2,500 explored nodes are marked with an obelus (†) on the heuristic score. A capped run counts as 2,500 explored nodes.

Aggregated statistics that contain at least one run that did not complete within the 2,500 node limit are marked with these symbols, and a matching footnote contains the number of trials that exceeded the limit.

The frontier holds a maximum of 255 states. If it holds more, the search drops states at random. [The frontier limit of 255 states](#the-frontier-limit-of-255-states) gives the details.

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

CAUTION: `run` sends paid API requests. The model sends one request for each node that it explores.

### Run the mini benchmark

The mini benchmark is a small run that needs one API key. It runs the first 20 trials of each domain with two fast models from Perplexity: pplx-decider 1.1 and pplx-decider 1.0. Trial n is the same trial as in the full benchmark.

1. Do steps 1 and 2 above.

2. Put your Perplexity key in `.env` as `PERPLEXITY_API_KEY`.

3. Run the mini benchmark, then make the figures and the mini index.

   ```bash
   uv run python -m beelinebench run --mini
   uv run python -m beelinebench readme
   ```

[Price estimates](docs/costs.md) gives the price of a mini run. [The mini benchmarks](docs/benchmarks/mini/README.md) shows the mini results of each version, as figures and as tables. The `[mini]` table of `beelinebench.toml` sets the trials and the models.

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
| `probe` | Sends one question with 255 options to a chooser, and shows the answer. Spends one or two requests. |
| `report` | Prints the scores, the share of solved trials, the served model, and the request times. |
| `plot` | Draws the scores of a benchmark to `docs/benchmarks/<version>.png`, one row for each model in each domain, with the 95% interval. It also draws the score against the cost of a step to `docs/benchmarks/<version>-frontier.png`. Needs `uv sync --extra plot`. |

### Choosers

| chooser | model | location |
|---|---|---|
| `jev-1.13` | TypeSafe Jev 1.13 (`jev-1.13.0`) | hosted, `api.typesafe.ai` |
| `luna` | OpenAI GPT-6 Luna, through the Decisions API (`gpt-6-luna`) | hosted, OpenAI. Needs `OPENAI_API_KEY`. |
| `pplx-decider` | Perplexity pplx-decider 1.1 (`pplx-decider-v1.1-27b`) | hosted, Perplexity. Needs `PERPLEXITY_API_KEY`. |
| `pplx-decider-1` | Perplexity pplx-decider 1.0 (`pplx-decider-v1-27b`) | hosted, Perplexity. Needs `PERPLEXITY_API_KEY`. |
| `d1` | Liquid d1 (`liquid/d1-20260930`) | hosted, OpenRouter. Needs `OPENROUTER_API_KEY`. |
| `kev-4b` | Kev 4B, open weights (`jaredpalmer/kev-4b-20260924`) | hosted, OpenRouter (SiliconFlow). Needs `OPENROUTER_API_KEY`. |
| `mercury-decide` | Inception Mercury Decide (`inception/mercury-decide-20260930`) | hosted, OpenRouter. Needs `OPENROUTER_API_KEY`. |
| `clef` | Cloudflare Clef, 27B (`clef`) | hosted, Cloudflare Workers AI. Needs `CLOUDFLARE_ACCOUNT_ID` and `CLOUDFLARE_API_TOKEN`. |
| `clef-flash` | Cloudflare Clef-flash, 9B (`clef-flash`) | hosted, Cloudflare Workers AI. Needs the same two values. |
| `haiku` | Claude Haiku 4.5, as a reference. The README does not show its results. | hosted, Anthropic. Needs `ANTHROPIC_API_KEY`. |
| `clef-local`, `clef-flash-local` | Clef and Clef-flash on your own GPU | local, ports 8001 and 8002 |
| `local` | any model that uses the Jev protocol | local, port 8000 |

A choice model uses the Jev protocol or OpenAI's Decisions API. Jev serves the Jev protocol at `{api_base}/systemone`. Perplexity serves it at `/v1/decisions`, Cloudflare serves it at the name of the model, and OpenRouter serves it at `/api/alpha/decisions` for models of many publishers. OpenAI's Decisions API is at `{api_base}/decisions`. Both get one choice question over the whole frontier, and the chooser takes the option with the highest probability. Each response must name the model that was asked for, or the run stops. If your model is a Python function, `beelinebench.serve` puts it on a local port:

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

### Trace files

`run` also writes the steps of each trial to `traces/<benchmark>/<chooser>/<domain>.<heuristic>/<trial>.jsonl.gz`. Git ignores these files. The first line of a file describes the trial. Each other line is one state that the search explored:

| field | what it is |
|---|---|
| `chosen` | the state that the model chose |
| `chosen_distance`, `best_distance` | the number of moves to the goal from the chosen state, and from the best state of the frontier |
| `regret` | `chosen_distance` minus `best_distance`. 0 means that the model chose a best state. |
| `best_rank` | the place of the best state in the model's order of probability. 0 is first. |
| `top` | the 5 states with the highest probability, each with its probability and its distance |
| `requests`, `input_tokens`, `latencies_ms` | the cost of the step |
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
| `rush_hour` | `blocking_cars` | a 6 × 6 board of vehicles | a random board with 10 vehicles and the red car, at least 6 moves from the solution |
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

BeelineBench writes the states of a domain in one fixed form. A different form, for example a board as a grid and not as one line, can give a different score. Thus, a score measures a model together with the form of the states, not the model alone.

### Some APIs have no seed

The Jev protocol accepts only the fields `model`, `state`, and `questions`. It rejects all other fields, for example `seed` or `temperature`. Jev, pplx-decider, Clef, and the models on OpenRouter use this protocol. BeelineBench also sends no seed to OpenAI's Decisions API.

Identical requests can give different probabilities. In one test, the top option of Jev got 0.78, 0.78, and 0.83 in three calls. A different choice early in a search changes the remainder of the search. Thus, a second run of the same trial can give a different score.

BeelineBench fixes its own random values: the trials, the option order, and the dropped states. It cannot fix the answers of the model, so the results are not fully deterministic. The 95% interval does not include this variation.

## Model quirks

Some behavior of the models and their APIs can change a score. [Model quirks](docs/model-quirks.md) describes each behavior, and the rule that BeelineBench uses for it: the served model, refusals, dated model names, models that BeelineBench cannot use, and errors from the APIs.

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
