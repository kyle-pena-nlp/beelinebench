<!-- Made by `python -m beelinebench readme` from docs/costs.template.md. Edit the template, then run the command. -->

# Price estimates

## The mini benchmark

A mini run of benchmark 1.0.0 has the first 20 trials of each of its 7 domains, with the mini models. The table gives the estimated price of one mini run for each mini model.

| model | price for a million tokens | input tokens of a mini run | estimated price of a mini run | basis |
|---|---|---|---|---|
| pplx-decider 1.1 | $0.02 input, output free | 96 million | $1.92 | measured on 550 trials; token counts of Jev 1.13 |
| pplx-decider 1.0 | $0.02 input, output free | 133 million | $2.67 | measured on 35 trials |

All the mini models together: about $4.59.

## The full benchmark

A full run of benchmark 1.0.0 has 100 trials for each of its 7 domains. The table gives the estimated price of one full run for each hosted model.

| model | price for a million tokens | input tokens of a full run | estimated price of a full run | basis |
|---|---|---|---|---|
| Jev 1.13 | $0.042 input, output free | 577 million | $24.22 | measured on 700 trials |
| GPT-6 Luna (Decisions) | $0.10 input, output free | 312 million | $31.15 | measured on 550 trials; token counts of Jev 1.13 |
| pplx-decider 1.1 | $0.02 input, output free | 481 million | $9.62 | measured on 550 trials; token counts of Jev 1.13 |
| pplx-decider 1.0 | $0.02 input, output free | 667 million | $13.33 | measured on 35 trials |
| Liquid d1 | $0.04 input, output free | 939 million | $37.55 | measured on 508 trials; token counts of Jev 1.13 |
| Kev 4B | $0.042 input, output free | 1,203 million | $50.53 | measured on 23 trials; token counts of Jev 1.13 |
| Mercury Decide | $0.02 input, output free | 439 million | $8.78 | measured on 525 trials; token counts of Jev 1.13 |
| Clef | $0.24 input, output free | 1,347 million | $323.27 | measured on 35 trials |
| Clef-flash | $0.09 input, output free | 1,978 million | $178.00 | measured on 35 trials |

The estimate uses the mean input tokens and output tokens of a trial in `results/`. If a model has no results for a domain, the estimate uses the token counts of a different model. The basis column gives the source of the token counts.

A borrowed estimate is approximate. A model that explores more states sends more requests, so it uses more tokens. Also, each tokenizer counts the same text differently.

The prices come from `price_input` and `price_output` in `beelinebench.toml`. They are list prices in US dollars from October 2026, and the providers can change them. Workers AI gives each account 10,000 Neurons free each day, so a small run of Clef can cost less.

A run stops before a request if the total cost of the model is at its limit. `max_cost` in `beelinebench.toml` sets the limit, and the default is $35 for each model. The file `.spend/<chooser>.json` keeps the total cost of each model over all runs. The total includes trials that stopped before they were complete.

The table does not include local models. A local model has no price for each token, but it needs a GPU. [Run Clef on your own GPU](../README.md#run-clef-on-your-own-gpu) gives the details.

[Back to the README](../README.md)
