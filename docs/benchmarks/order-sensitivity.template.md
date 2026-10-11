# Order sensitivity: benchmark {{ latest_benchmark }}

A decision model gets the options of each question in an order. This study measures how much that order changes the score of each model on one problem. The models are {{ study_models }}. The `[sensitivity]` table of `beelinebench.toml` selects the models, the problem, and the orders. `uv run python -m beelinebench case-study` runs it.

The problem is Blocksworld, with the benchmark representation. The study compares seven option orders:

- three random orders with different seeds. The first is the order of the benchmark.
- the order in which the search found the states, the oldest first, and the reverse of this order.
- the states with the best heuristic value first, and the states with the worst value first.

An order from the heuristic gives the model information that the benchmark does not give. These two orders measure how much the model follows the position of an option. The three random orders show the variation that comes from the order alone.

![The score of each model on one problem for each order of the options, with 95% intervals]({{ latest_benchmark }}-order-sensitivity.png)

## The figure as text

{{ study order-sensitivity }}
