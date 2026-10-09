<!-- Made by `python -m beelinebench readme` from docs/model-quirks.template.md. Edit the template, then run the command. -->

# Model quirks

Some behavior of the models and their APIs can change a score. This page describes each behavior, and the rule that BeelineBench uses for it.

## Each answer must come from the requested model

A hosted model name, for example an alias such as `jev-latest`, can point to a different model on a later day. Thus, each response must give the name of the model that `beelinebench.toml` requests. If the name is different or missing, the run stops. BeelineBench does not record that trial.

## OpenAI's Decisions API can refuse a question

The Decisions API can answer a question with the type `refusal` and no choice. OpenAI does not document the cause, and the API has no setting for it.

In benchmark 1.0.0, the API refused 73,727 of 132,240 requests (56%). The refusals are not equal in the domains:

| domain | refused requests | decisions that used the fallback |
|---|---|---|
| 8-puzzle | 4.4% | 0.6% |
| Blocksworld | 0.0% | 0.0% |
| Countdown | 0.6% | 0.1% |
| Word ladder | 14.2% | 3.7% |
| Wikispeedia | 54.9% | 34.1% |
| Rush Hour (50 of 100 trials) | 86.4% | 74.8% |

In Rush Hour, most decisions use the fallback. Thus, the Rush Hour score of GPT-6 Luna measures the fallback more than the model.

One Wikispeedia trial (trial 53) caused 2,521 of the 2,526 Wikispeedia refusals. Two full runs of this trial gave the same result: the same requests, refusals, and invalid answers. Thus, the effect is consistent, not intermittent.

At step 4, the target article was an option, and the model chose a different article. The frontier limit then dropped the target, and the search did not find it again. The first refusal came at step 188, and the API refused 63% of the questions after it. The trial stopped at the limit of 2,500 nodes.

The other models solved this trial with 3 requests. The other 99 Wikispeedia trials had a maximum of two refusals each. The puzzle text of each domain is harmless.

A refusal depends on the exact request. In a test, the API refused the same request five times. The same options in a different order got an answer. A different symbol for the gap, different instructions, or fewer options also got an answer.

When the API refuses a question, the chooser asks once more, with the options in a new seeded order. If the API refuses again, the chooser takes the first option of the second order. Each refusal is a request, so it counts toward the request limit and the input tokens. The `refusals` column gives the share of requests that the API refused.

## OpenRouter answers with a dated model name

OpenRouter takes a model name such as `liquid/d1`, and it answers with a dated name such as `liquid/d1-20260930`. The `served` setting of a chooser gives the dated name that each answer must give. Thus, the run uses one version of the model. If OpenRouter changes the version, the run stops.

## Models that BeelineBench cannot use

These decision models do not accept the question that BeelineBench sends:

| model | reason |
|---|---|
| Upstage Solar Decide (`upstage/solar-decide`) | A choice question can have a maximum of 26 options. The frontier can have 255 states. |
| Respan Span-01 Lite (`respan/span-01-lite`) | It accepts only yes-or-no questions. |
| TypeSafe `jev-preview` | It answers as `jev-1.13.0` now, so its results are the same as Jev 1.13. |

## Errors from the APIs

Some errors are intermittent: a timeout, a dropped connection, the status 408 or 429, or a status from 500 to 599. For these errors, the client sends the request again, a maximum of 8 times. The wait between two tries increases to one minute. If the API gives a `Retry-After` time, the client waits for that time.

Some errors are not intermittent, and the run stops at once:

- OpenAI returns the status 429 when the account has no credits.
- Cloudflare returns the status 429 when the account uses all of its free allocation for the day.
- The answer comes from a model that is different from the requested model.

BeelineBench does not record the trial that was in progress when the run stopped.

## The Claude reference

The `haiku` chooser uses the default temperature of the Anthropic API, and that API has no seed. Thus, identical requests can give different answers. The model can also reason before it answers, and the choice models cannot. Thus, its score does not measure the same ability, and the README does not show it.

[Back to the README](../README.md)
