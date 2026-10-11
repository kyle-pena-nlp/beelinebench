# Usage

This page is the reference for running BeelineBench: the steps, the configuration, the commands, the models, and the files that a run writes.

## Run from a clone

These steps run BeelineBench from a clone of the repository. You can also install it as a package, and then run `beelinebench init` in an empty folder. BeelineBench is not on PyPI yet, so install it from GitHub: `pip install "beelinebench[plot] @ git+https://github.com/kyle-pena-nlp/beelinebench"`. [Integrate BeelineBench with your evaluation suite](lab-integration.md) gives the details, and also shows how to run it in a container.

> [!CAUTION]
> `run` sends paid API requests. The model sends one request for each node that it explores.

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

## Run the mini benchmark

The mini benchmark is a small run. By default, it needs one API key, and it runs the first {{ mini_trials }} trials of each domain with two fast models from Perplexity: {{ mini_models }}. Trial n is the same trial as in the full benchmark.

1. Do steps 1 and 2 above.

2. Put your Perplexity key in `.env` as `PERPLEXITY_API_KEY`.

3. Run the mini benchmark, then make the figures and the mini index.

   ```bash
   uv run python -m beelinebench run --mini
   uv run python -m beelinebench readme
   ```

[Price estimates](costs.md) gives the price of a mini run. [The mini benchmarks](benchmarks/mini/README.md) shows the mini results of each version, as figures and as tables.

You can change what the mini benchmark runs. The `[mini]` table of `beelinebench.toml` sets the trials and the models. For example, this table runs 10 trials with two models from OpenRouter:

```toml
[mini]
trials = 10
choosers = ["mercury-decide", "d1"]
```

Each model must have a table in `beelinebench.toml`, and you need the key of its provider. If the models come from more than one provider, you need a key for each provider.

## Configuration

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

## Choosers

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

## Run Clef on your own GPU

[Run Clef on your own GPU](clef-local.md) tells you how to serve Clef and Clef-flash on your own machine and run them with no API key.

## Results files

`run` writes each trial to `results/<benchmark>/<chooser>/<domain>.<heuristic>.jsonl` when the trial ends. If you run again, `run` skips the trials that are already in the file.

If your settings are different from an official benchmark, the results go to `results/custom-<name>/`. `run` lists each setting that is different.

Hosted models can change over time. Each record holds the model name that the API returned (for example `jev-1.13.0`) and the date of the run. A record also holds the scores of the heuristic arm, the oracle arm, and the random arm, and the counts of optimal choices of each arm. For results from before these values existed, `fill` adds them from the traces.

## Trace files

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

## Clean trials

A trial is clean if it has no refusals, no invalid answers, and no retries. To run the trials that are not clean again, use this command:

```bash
uv run python -m beelinebench run --chooser <name> --rerun-unclean
```

The new run replaces the old run only if the new run has fewer refusals, invalid answers, and retries. The score of the new run has no effect on this decision. Thus, the command cannot select good scores.

