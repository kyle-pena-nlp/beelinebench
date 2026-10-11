<!-- Made by `python -m beelinebench readme` from benchmarks.toml. Do not edit. -->
# The mini benchmarks

The mini benchmark of a version is its first 20 trials of each domain, with
pplx-decider 1.1, pplx-decider 1.0. These models come from one provider, so a run needs one key.
`uv run python -m beelinebench run --mini` runs it. Trial n is the same trial as in the
full benchmark, so a mini score is the full score of fewer trials, with wider intervals.
[The benchmarks](../README.md) has the full results.

The `[mini]` table of `beelinebench.toml` sets the trials and the models of the mini
benchmark. This index shows the models of that table.

## Benchmark 1.0.0 mini

![The scores of each model and heuristic in benchmark 1.0.0, by domain, with 95% intervals](1.0.0.png)

### Scores as text

The rows of each problem are in the order of the figure, best first. A score is the geometric mean over the trials, and the interval is its 95% bootstrap interval. \* or †: at least one model (\*) or heuristic (†) run did not solve within 2,500 nodes, so the true score is lower.

#### 8-puzzle

| | trials | score | 95% interval |
|---|---|---|---|
| Heuristic: Manhattan distance | 20 | 0.25 | 0.14 to 0.44 |
| pplx-decider 1.1 | 20 | 0.07 | 0.04 to 0.12 |
| pplx-decider 1.0 | 20 | 0.07 | 0.04 to 0.12 |
| Random choice | 20 | 0.0095 | 0.0066 to 0.01 |

#### Blocksworld

| | trials | score | 95% interval |
|---|---|---|---|
| Heuristic: FF relaxed plan | 20 | 0.69 | 0.58 to 0.81 |
| pplx-decider 1.0 | 20 | 0.56 | 0.44 to 0.69 |
| pplx-decider 1.1 | 20 | 0.50 | 0.39 to 0.62 |
| Random choice | 20 | 0.0043 | 0.0037 to 0.0049 |

#### Countdown

| | trials | score | 95% interval |
|---|---|---|---|
| pplx-decider 1.0 | 20 | 0.42 | 0.25 to 0.67 |
| pplx-decider 1.1 | 20 | 0.36 | 0.22 to 0.56 |
| Heuristic: nearest number | 20 | 0.21 | 0.13 to 0.34 |
| Random choice | 20 | 0.05 | 0.04 to 0.06 |

#### Word ladder

| | trials | score | 95% interval |
|---|---|---|---|
| Heuristic: letters different | 20 | 0.36 | 0.27 to 0.47 |
| pplx-decider 1.0 | 20 | 0.16 | 0.09 to 0.24 |
| pplx-decider 1.1 | 20 | 0.15 | 0.09 to 0.26 |
| Random choice | 20 | 0.0057 | 0.0041 to 0.0088 |

#### Wikispeedia

| | trials | score | 95% interval |
|---|---|---|---|
| pplx-decider 1.0 | 20 | 0.83 | 0.75 to 0.92 |
| pplx-decider 1.1 | 20 | 0.75 | 0.63 to 0.87 |
| Heuristic: category distance | 20 | 0.16 | 0.09 to 0.28 |
| Random choice | 20 | 0.0042 | 0.0028 to 0.0066 |

#### Rush Hour

| | trials | score | 95% interval |
|---|---|---|---|
| pplx-decider 1.0 | 20 | 0.07\* | 0.04 to 0.11 |
| pplx-decider 1.1 | 20 | 0.06\* | 0.04 to 0.10 |
| Heuristic: blocking vehicles | 20 | 0.05† | 0.03 to 0.09 |
| Random choice | 20 | 0.01 | 0.0080 to 0.02 |

#### Keys and doors

| | trials | score | 95% interval |
|---|---|---|---|
| pplx-decider 1.0 | 20 | 0.74 | 0.66 to 0.81 |
| pplx-decider 1.1 | 20 | 0.72 | 0.65 to 0.80 |
| Heuristic: locked doors | 20 | 0.55 | 0.46 to 0.65 |
| Random choice | 20 | 0.17 | 0.13 to 0.21 |

![The score against the cost of a step for each model in benchmark 1.0.0, by domain, with the efficient frontier](1.0.0-frontier.png)

### Score and cost as text

A step is one request. Its cost is the mean tokens of a request at the list price of the model. A model on the frontier is on the line of the figure: no other model, and no mix of two models, is both cheaper and better. The rows are best score first.

#### 8-puzzle

| model | score | US dollars for 1,000 steps | on the frontier |
|---|---|---|---|
| pplx-decider 1.1 | 0.07 | $0.070 | yes |
| pplx-decider 1.0 | 0.07 | $0.075 |  |

#### Blocksworld

| model | score | US dollars for 1,000 steps | on the frontier |
|---|---|---|---|
| pplx-decider 1.0 | 0.56 | $0.055 | yes |
| pplx-decider 1.1 | 0.50 | $0.073 |  |

#### Countdown

| model | score | US dollars for 1,000 steps | on the frontier |
|---|---|---|---|
| pplx-decider 1.0 | 0.42 | $0.015 | yes |
| pplx-decider 1.1 | 0.36 | $0.016 |  |

#### Word ladder

| model | score | US dollars for 1,000 steps | on the frontier |
|---|---|---|---|
| pplx-decider 1.0 | 0.16 | $0.024 | yes |
| pplx-decider 1.1 | 0.15 | $0.026 |  |

#### Wikispeedia

| model | score | US dollars for 1,000 steps | on the frontier |
|---|---|---|---|
| pplx-decider 1.0 | 0.83 | $0.018 | yes |
| pplx-decider 1.1 | 0.75 | $0.020 |  |

#### Rush Hour

| model | score | US dollars for 1,000 steps | on the frontier |
|---|---|---|---|
| pplx-decider 1.0 | 0.07\* | $0.15 | yes |
| pplx-decider 1.1 | 0.06\* | $0.15 |  |

#### Keys and doors

| model | score | US dollars for 1,000 steps | on the frontier |
|---|---|---|---|
| pplx-decider 1.0 | 0.74 | $0.014 | yes |
| pplx-decider 1.1 | 0.72 | $0.014 |  |

![The percent of decisions that took a state on a shortest path, for each model and heuristic in benchmark 1.0.0, by domain, with 95% intervals](1.0.0-choices.png)

### Optimal choices as text

A state is optimal when it is on a shortest path: its moves from the start plus its moves to the goal equal the length of a shortest path. A decision counts when the frontier has an optimal state and a state that is not optimal. The percent is the mean over trials of the percent of the counted decisions that took an optimal state, so each trial counts the same.

#### 8-puzzle

| | trials | chose an optimal state | 95% interval |
|---|---|---|---|
| Heuristic: Manhattan distance | 20 | 46% | 25% to 67% |
| pplx-decider 1.1 | 20 | 11% | 3% to 20% |
| pplx-decider 1.0 | 20 | 9% | 3% to 18% |
| Random choice | 20 | 2% | 1% to 3% |

#### Blocksworld

| | trials | chose an optimal state | 95% interval |
|---|---|---|---|
| Heuristic: FF relaxed plan | 20 | 71% | 60% to 82% |
| pplx-decider 1.0 | 20 | 52% | 37% to 68% |
| pplx-decider 1.1 | 20 | 49% | 35% to 62% |
| Random choice | 20 | 2% | 1% to 2% |

#### Countdown

| | trials | chose an optimal state | 95% interval |
|---|---|---|---|
| pplx-decider 1.0 | 20 | 63% | 45% to 81% |
| pplx-decider 1.1 | 20 | 55% | 38% to 72% |
| Heuristic: nearest number | 20 | 29% | 19% to 39% |
| Random choice | 20 | 10% | 6% to 16% |

#### Word ladder

| | trials | chose an optimal state | 95% interval |
|---|---|---|---|
| Heuristic: letters different | 20 | 37% | 24% to 52% |
| pplx-decider 1.0 | 20 | 20% | 10% to 33% |
| pplx-decider 1.1 | 20 | 18% | 9% to 29% |
| Random choice | 20 | 2% | 1% to 3% |

#### Wikispeedia

| | trials | chose an optimal state | 95% interval |
|---|---|---|---|
| pplx-decider 1.0 | 20 | 78% | 66% to 90% |
| pplx-decider 1.1 | 20 | 69% | 55% to 80% |
| Heuristic: category distance | 20 | 20% | 13% to 27% |
| Random choice | 20 | 1% | 1% to 2% |

#### Rush Hour

| | trials | chose an optimal state | 95% interval |
|---|---|---|---|
| Heuristic: blocking vehicles | 20 | 13% | 9% to 18% |
| pplx-decider 1.0 | 20 | 8% | 4% to 13% |
| pplx-decider 1.1 | 20 | 7% | 3% to 13% |
| Random choice | 20 | 3% | 2% to 4% |

#### Keys and doors

| | trials | chose an optimal state | 95% interval |
|---|---|---|---|
| pplx-decider 1.1 | 20 | 52% | 37% to 67% |
| pplx-decider 1.0 | 20 | 48% | 34% to 63% |
| Heuristic: locked doors | 20 | 45% | 32% to 58% |
| Random choice | 20 | 18% | 12% to 25% |
