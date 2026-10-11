# Repeatability: benchmark {{ latest_benchmark }}

The APIs of the decision models take no seed. Thus, two runs of the same requests can give different answers, and a different choice early in a search changes the remainder of the search. This study runs the same condition more than once, and measures how much the score of each model changes between runs. The models are {{ study_models }}.

The problem is Blocksworld, with the representation and the option order of the benchmark. Each run sends the same first request for each trial. Run 1 is the benchmark run. The `repeats` setting of the `[sensitivity]` table of `beelinebench.toml` sets the number of runs. `uv run python -m beelinebench case-study` runs it.

A difference between two runs here is the variation that the 95% interval of the benchmark does not include. [Representation sensitivity]({{ latest_benchmark }}-representation-sensitivity.md) and [order sensitivity]({{ latest_benchmark }}-order-sensitivity.md) compare their differences with this variation.

![The score of each model on one problem for each run of the same condition, with 95% intervals]({{ latest_benchmark }}-repeatability.png)

## The figure as text

{{ study repeatability }}
