# Price estimates

## The mini benchmark

A mini run of benchmark {{ latest_benchmark }} has the first {{ mini_trials }} trials of each of its {{ domain_count }} domains, with the mini models. The table gives the estimated price of one mini run for each mini model.

{{ mini_costs }}

## The full benchmark

A full run of benchmark {{ latest_benchmark }} has {{ trials }} trials for each of its {{ domain_count }} domains. The table gives the estimated price of one full run for each hosted model.

{{ costs }}

The estimate uses the mean input tokens and output tokens of a trial in `results/`. If a model has no results for a domain, the estimate uses the token counts of a different model. The basis column gives the source of the token counts.

A borrowed estimate is approximate. A model that explores more states sends more requests, so it uses more tokens. Also, each tokenizer counts the same text differently.

The prices come from `price_input` and `price_output` in `beelinebench.toml`. They are list prices in US dollars from October 2026, and the providers can change them. Workers AI gives each account 10,000 Neurons free each day, so a small run of Clef can cost less.

A run stops before a request if the total cost of the model is at its limit. `max_cost` in `beelinebench.toml` sets the limit, and the default is $35 for each model. The file `.spend/<chooser>.json` keeps the total cost of each model over all runs. The total includes trials that stopped before they were complete.

The table does not include local models. A local model has no price for each token, but it needs a GPU. [Run Clef on your own GPU](clef-local.md) gives the details.
