# Robustness case study: benchmark {{ latest_benchmark }}

A decision model gets each state as text, and it gets the options of a question in an order. This case study measures how much these two choices change the score of one model on one problem. The `[case_study]` table of `beelinebench.toml` selects the model, the problem, the representations, and the option orders. `uv run python -m beelinebench case-study` runs it.

The problem is Blocksworld. Its benchmark representation is a list of PDDL facts, for example `(on b2 b3)`. The case study compares four representations of the same states:

| representation | example |
|---|---|
| facts (the benchmark) | `(clear b2) (handempty) (on b2 b3) (ontable b3)` |
| sentences | `Nothing is on block 2. The hand is empty. Block 2 is on block 3. Block 3 is on the table.` |
| towers | `a tower of b3, b2 (from the table up); the hand is empty` |
| brackets | `[b3 b2] hand: -` |

Each representation also writes the goal and the rules of the hand in its own form. Each representation uses the same random option order, so only the text changes.

The case study also compares seven option orders, with the facts representation:

- three random orders with different seeds, the first of which is the order of the benchmark;
- the order in which the search found the states, the oldest first, and the reverse of this order;
- the states with the best heuristic value first, and the states with the worst value first.

An order from the heuristic gives the model information that the benchmark does not give. These two orders measure how much the model follows the position of an option.

The representation group also shows the benchmark run of the model on the same trials. This run and "facts" have the same condition. The difference between them shows the variation between two runs, because the API has no seed.

![The score of one model on one problem for each representation of the states and each order of the options, with 95% intervals]({{ latest_benchmark }}-robustness-case-study.png)

## The figure as text

{{ case_study }}

[Back to the README](../../README.md)
