# Integrate BeelineBench with your evaluation suite

BeelineBench runs in four ways. Select the way that fits your suite:

| way | use it when | what you need |
|---|---|---|
| [A container](#run-it-in-a-container) | your suite runs jobs in containers, or you want a fixed environment | Docker |
| [The command line](#run-it-from-the-command-line) | you run evaluations on a workstation or in CI | Python 3.11 or later |
| [The Python API](#test-a-model-that-is-a-python-function) | your model has no public API, for example an internal checkpoint | Python, in the process of your model |
| [A local server](#serve-a-model-on-the-jev-protocol) | your model is a service of its own, or it runs on other hardware | an HTTP port |

Each way writes the same files, and `report --json` gives the scores as JSON. [Read the results](#read-the-results) describes the files.

## Run it in a container

The `Dockerfile` makes an image with the code, the locked dependencies (`uv.lock`), and the word list of the word ladder domain. The image does not hold the Wikispeedia data, because SNAP gives no license to redistribute it. The first run that needs it fetches it from SNAP. Each fetch checks the SHA-256 of the data, so each machine has the same trials. The image holds no key and no results.

1. Build the image.

   ```bash
   docker build -t beelinebench .
   ```

2. Give the keys to the container. [Give the keys](#give-the-keys) shows the ways.

3. Run a command of BeelineBench. The arguments after the image name are the arguments of `python -m beelinebench`.

   ```bash
   docker run --rm \
     -v "$PWD/secrets:/run/secrets:ro" \
     -v "$PWD/results:/app/results" -v "$PWD/traces:/app/traces" -v "$PWD/.spend:/app/.spend" \
     -v "$PWD/beelinebench.toml:/app/beelinebench.toml:ro" \
     -v beelinebench-wikispeedia:/app/data/wikispeedia \
     beelinebench run --mini
   ```

Mount `results/`, `traces/`, and `.spend/` from the host. The volume `beelinebench-wikispeedia` keeps the Wikispeedia data between runs. If you do not mount them, they stay in the container and the container deletes them when it stops. Mount your own `beelinebench.toml` to select the models and the limits.

`compose.yaml` does the same with Docker Compose:

```bash
docker compose run --rm beelinebench run --mini
```

`baseline`, `report`, and `readme` send no requests, so they need no key. Use `baseline` to do a test of an image:

```bash
docker run --rm beelinebench baseline --domain countdown --trials 3
```

## Give the keys

BeelineBench reads each key, for example `PERPLEXITY_API_KEY`, from the first of these places that has it:

1. the file `.env` in the project folder;
2. the environment variable, for example `PERPLEXITY_API_KEY`;
3. the file that `PERPLEXITY_API_KEY_FILE` names;
4. the file `/run/secrets/PERPLEXITY_API_KEY`.

In a container, a file is better than an environment variable. `docker inspect` shows the environment of a container, but it does not show the contents of a file.

| platform | how to give a key |
|---|---|
| Docker Compose | a [Compose secret](https://docs.docker.com/compose/how-tos/use-secrets/). `compose.yaml` reads `./secrets/PERPLEXITY_API_KEY`. |
| Docker | mount a folder of key files at `/run/secrets`, as in the `docker run` command above |
| Kubernetes | mount a Secret as files, at `/run/secrets` or at a path that `<NAME>_FILE` names |
| CI, for example GitHub Actions | an environment variable from the secret store of the CI |

Each key goes in its own file, with the name of its variable. For example:

```bash
mkdir -p secrets
printf '%s' "$PERPLEXITY_API_KEY" > secrets/PERPLEXITY_API_KEY
```

CAUTION: Do not put a key in the image. `.dockerignore` keeps `.env` and `secrets/` out of the image. Git ignores them too.

## Run it from the command line

You can install BeelineBench as a package, or run it from a clone of the repository.

### Install the package

1. Install the package. The `plot` extra draws the figures, and the `llm` extra adds the Claude reference.

   ```bash
   pip install "beelinebench[plot]"
   ```

2. In an empty folder, write a `beelinebench.toml` to start from. Then edit its models and limits.

   ```bash
   beelinebench init
   ```

3. Put the keys in `.env`, or in a place of [Give the keys](#give-the-keys).

4. Run the benchmark.

   ```bash
   beelinebench run --mini      # or `run` for the full benchmark
   beelinebench report --json
   ```

The package uses the current folder as its working folder: `beelinebench.toml`, `.env`, `data/`, `results/`, `traces/`, and `.spend/`. To use a different folder, set `BEELINEBENCH_HOME`. The official benchmarks come with the package. A run fetches the data of a domain when it needs it.

### Run it from a clone

1. Clone the repository, and install the dependencies.

   ```bash
   uv sync --extra plot
   uv run python -m beelinebench download
   ```

2. Put the keys in `.env`, or in a place of [Give the keys](#give-the-keys).

3. Run the benchmark.

   ```bash
   uv run python -m beelinebench run --mini      # or `run` for the full benchmark
   uv run python -m beelinebench report --json
   ```

In a clone, the working folder is the clone. The commands that change the docs of the repository, `readme`, `publish`, and `check-docs`, run only in a clone.

## Test a model that is a Python function

`beelinebench.api.evaluate` runs the benchmark on a Python function. It sends no request and needs no key or config. Use it for a model that has no public API.

```python
from beelinebench.api import Question, evaluate

def decide(question: Question) -> list[float]:
    # Give one probability, or any score, for each of question.options, in that order.
    return my_model.score(question.text(), question.options)

summary = evaluate(decide, name="my-model-2026-10", trials=20)
```

The function gets the same task, goal, context, instructions, and options as a model behind an API. The options come in the same seeded random order. The search takes the option with the highest score. `evaluate` writes the results and traces to the usual files, and gives a summary for each domain. Use a new `name` for each version of your model. If a run stops, call `evaluate` again: it does not run a trial that has a result.

## Serve a model on the Jev protocol

If your model is a service, serve it on the Jev protocol. Then add a chooser for it to `beelinebench.toml`. `beelinebench.serve` puts a Python function behind a server:

```bash
python -m beelinebench.serve --port 8001 my_module:systemone
```

The function takes the body of a Jev request, and gives the body of the response. `examples/clef.py` serves Clef this way. [Run Clef on your own GPU](clef-local.md) gives the details.

## Read the results

| file | what it holds |
|---|---|
| `results/<benchmark>/<chooser>/<domain>.<heuristic>.jsonl` | one line for each trial: the scores of each arm, the requests, the tokens, the refusals, and the choices against the oracle |
| `traces/<benchmark>/<chooser>/<domain>.<heuristic>/<trial>.jsonl.gz` | one line for each step of the model arm: the chosen state, its distance to the goal, and the probabilities of the model |
| `.spend/<chooser>.json` | the total tokens and cost of the model over all runs |
| `report --json` | for each results file: the score, its 95% interval, the heuristic score, the oracle score, the path score, the refusals, the latency, and more |

## Reproducibility

- Trial n of a domain is the same on each machine. Seeded draws make the trials, the option order, and the dropped states. On 2026-10-09, macOS and the Linux image gave the same trials and the same searches.
- `uv.lock` fixes the version of each dependency. The SHA-256 of each data file is fixed in the code, and a fetch stops if the source changed.
- [NOTICE](../NOTICE) gives the source and the terms of the third-party data.
- An official benchmark version never changes. `benchmarks.toml` holds each version.
- The model APIs take no seed. Thus, two runs of the same model can give different scores. [Repeatability](benchmarks/1.0.0-repeatability.md) measures this variation.

## Cost limits

`max_cost` limits the cost of one model over all runs, and `max_total_cost` limits the cost of all models. Each run stops before a request that would start above a limit. Set both in `beelinebench.toml` before you run the full benchmark. [Price estimates](costs.md) gives the price of a run for each model.

## Not ready yet

- **The first release on PyPI.** The package is ready, and `.github/workflows/release.yml` publishes a tag such as `v1.0.0`. PyPI must first trust this workflow as a publisher of the project. Until the first release, install from the repository: `pip install "git+https://github.com/kyle-pena-nlp/beelinebench"`.
- **The Inspect Evals Register.** Since May 2026, [Inspect Evals](https://github.com/UKGovernmentBEIS/inspect_evals) lists new evals that live in their own repositories. An Inspect model generates text, and BeelineBench needs a probability for each option. A listing needs an adapter between the two.
