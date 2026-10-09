# Changelog

The code and the benchmarks have separate versions. The code runs every official
benchmark of `benchmarks.toml`. A new benchmark version adds a table there, and no
table is changed.

## Benchmark 1.0.0

* Greedy best-first search. The model ranks the whole frontier in one question
  at each step.
* The frontier holds at most 255 states. Above that, states leave it at random,
  by the same rule for both arms.
* A breadth-first search finds the shortest path of each trial. The score is
  `(shortest path + 1) / explorations`, so 1.0 is perfect. The model arm, the
  classic arm and an oracle arm (the true distance to the goal as the chooser) get
  this score. The path score is the shortest path divided by the model's path.
* Both arms stop at 2,500 explorations, solved or not. A model run that stops
  unsolved is marked `*`, and a classic run `†`. No trial is skipped.
* 100 trials of seven domains, each with one heuristic: `tiles/manhattan`,
  `blocksworld/h_ff`, `countdown/nearest_number`, `word_ladder/letters_different`,
  `wikispeedia/category_distance`, `rush_hour/blocking_cars`,
  `keys_doors/locked_doors`.

## Code 1.0.0

* Trial `n` of a domain is drawn from `Draws(domain, n)`, the same on every
  machine and for every model. The option order and the eviction of the model
  arm are seeded with the model name.
* `benchmarks.toml` holds the official benchmarks. `beelinebench.toml` says what to
  run: the benchmark, the choosers, and their limits.
* The protocol of a choice model is Jev's, at any `api_base`, local or remote. A
  Claude model is a reference figure.
* When a chooser is done, `run` says whether the run matches an official
  benchmark, and how many of its trials the results hold.
* Each trial records when it ran, the model that the API says answered, and the
  time of each request. `report` shows the served models, the dates, and the
  median and 95th-percentile time of a request.
* `python -m beelinebench.serve` puts a Python model function on the Jev protocol at
  a local port. `beelinebench.toml` has choosers for Cloudflare's Clef and Clef-flash.
