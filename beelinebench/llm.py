"""A Claude model as the chooser. A reference figure for the Jev score.

The model gets the same objective, context and frontier as Jev, as a numbered
list in a random order. It answers with the number of the state to explore, as
structured output. The search and the score are the same as for Jev.

The model can reason before it answers, and Jev cannot. So this figure shows
what a general model does with the same information. It is not the same test of
one call with no reasoning.
"""

from __future__ import annotations

import json
import time
from collections.abc import Callable, Sequence
from typing import Any

import anthropic

from .rng import Draws
from .search import Chooser, Spend, check

SYSTEM = (
    "A search is looking for a way to reach a goal. You get the states that the "
    "search has found and has not explored yet. Choose the state to explore next: "
    "the state from which the goal can be reached in the fewest moves. The search "
    "explores the state you choose, and then asks again."
)

ANSWER = {
    "type": "json_schema",
    "schema": {
        "type": "object",
        "properties": {"state": {"type": "integer"}},
        "required": ["state"],
        "additionalProperties": False,
    },
}


class LLMError(Exception):
    """The model gave no answer."""


def llm_chooser(client: anthropic.Anthropic, *, model: str, effort: str | None,
                objective: str, context: str, render: Callable[[Any], str],
                spend: Spend, order: Draws) -> Chooser:
    """A chooser that asks ``model`` for the number of one state.

    ``effort`` goes to ``output_config.effort``. ``None`` sends no effort, and the
    model uses its own default.
    """
    output_config: dict[str, Any] = {"format": ANSWER}
    if effort is not None:
        output_config["effort"] = effort

    def choose(states: Sequence[Any]) -> int:
        positions = list(range(len(states)))
        order.shuffle(positions)
        listing = "\n".join(f"{n}. {render(states[i])}" for n, i in enumerate(positions, 1))
        prompt = (f"Goal: {objective}\n\n{context}\n\nStates:\n{listing}\n\n"
                  "Give the number of the state to explore next.")
        check(spend)
        started = time.monotonic()
        response = client.messages.create(
            model=model, max_tokens=16000, system=SYSTEM,
            messages=[{"role": "user", "content": prompt}],
            output_config=output_config)
        spend.add(input_tokens=response.usage.input_tokens,
                  output_tokens=response.usage.output_tokens,
                  seconds=time.monotonic() - started, served=str(response.model))
        if response.stop_reason != "end_turn":
            raise LLMError(f"the model stopped with {response.stop_reason}")
        text = next(block.text for block in response.content if block.type == "text")
        number = json.loads(text)["state"]
        if not 1 <= number <= len(states):
            spend.invalid_answers += 1
            number = 1
        return positions[number - 1]

    return choose
