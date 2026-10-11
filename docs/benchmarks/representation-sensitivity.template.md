# Representation sensitivity: benchmark {{ latest_benchmark }}

A decision model gets each state as text. This study measures how much the text of the states changes the score of each model on one problem. The models are {{ study_models }}. The `[sensitivity]` table of `beelinebench.toml` selects the models, the problem, and the representations. `uv run python -m beelinebench case-study` runs it.

The problem is Blocksworld. Its benchmark representation is a list of PDDL facts. The study compares four representations of the same states:

| representation | example |
|---|---|
| facts (the benchmark) | `(clear b2) (handempty) (on b2 b3) (ontable b3)` |
| sentences | `Nothing is on block 2. The hand is empty. Block 2 is on block 3. Block 3 is on the table.` |
| towers | `a tower of b3, b2 (from the table up); the hand is empty` |
| brackets | `[b3 b2] hand: -` |

Each representation also writes the goal and the rules of the hand in its own form. Each representation uses the same random option order, so only the text changes. [Repeatability]({{ latest_benchmark }}-repeatability.md) shows how much two runs of the same condition differ. Compare a difference here with that variation.

![The score of each model on one problem for each representation of the states, with 95% intervals]({{ latest_benchmark }}-representation-sensitivity.png)

## The figure as text

{{ study representation-sensitivity }}
