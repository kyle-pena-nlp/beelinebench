"""OpenAI's Decisions API as the chooser of a best-first search.

The API is ``POST {api_base}/decisions`` (developers.openai.com/api/docs/guides/decisions).
A request has the text to decide on (``input``) and questions. A ``choice``
question names its options, and the answer gives a probability for each. The
chooser asks one choice question over the whole frontier, and takes the state
with the highest probability, as it does with Jev.

The API can refuse a question (an answer of type ``refusal``). A refusal depends
on the exact request: the same request is refused again, and the same options in
another order usually get an answer. So the chooser asks once more, with the
options in a new order from ``order``. If that is refused too, it takes the first
state of the last order, and counts an invalid answer. ``Spend.refusals`` counts
every refusal, and the re-asked request counts as a request.

The model gets the same task, goal, context and instructions as Jev. Jev takes
them as fields of ``state``. This API takes one text, so they are lines of
``input``. The options go in a random order on each call, as for Jev.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Any

import httpx

from .jev import INSTRUCTIONS, MAX_OPTIONS, TASK, Reply, post
from .rng import Draws
from .search import Chooser, ChooserError, Spend, check

DEFAULT_BASE = "https://api.openai.com/v1"


class DecisionsError(ChooserError):
    """A Decisions request failed, or a model other than the one asked for answered it."""


class DecisionsClient:
    """Sends questions to ``POST {api_base}/decisions``.

    Each answer must name the model that answered it, and that model must be
    ``model``. Any other answer is a :class:`DecisionsError`.
    """

    def __init__(self, *, api_key: str, model: str, api_base: str | None = None,
                 http: httpx.Client | None = None) -> None:
        self.model = model
        self.url = (api_base or DEFAULT_BASE).rstrip("/") + "/decisions"
        self.http = http or httpx.Client(timeout=120.0)
        self.headers = {"Authorization": f"Bearer {api_key}"}

    def ask(self, text: str, questions: list[dict]) -> Reply:
        """Send one request. ``answers`` maps each question name to its answer."""
        body = {"model": self.model, "input": text, "questions": questions}
        payload, seconds = post(self.http, self.url, body, self.headers, error=DecisionsError)
        usage = payload.get("usage") or {}
        return Reply({answer["name"]: answer for answer in payload["answers"]},
                     int(usage.get("input_tokens", 0)), payload["model"], seconds)


def decisions_chooser(client: DecisionsClient, *, objective: str, context: str,
                      render: Callable[[Any], str], spend: Spend, order: Draws) -> Chooser:
    """A chooser that asks one choice question over the whole frontier."""
    text = f"Task: {TASK}\nGoal: {objective}\nContext: {context}"

    def choose(states: Sequence[Any]) -> int:
        spend.probabilities = None
        labels = [render(state) for state in states]
        if len(set(labels)) != len(labels):
            raise ValueError("two frontier states have the same rendering")
        if len(labels) > MAX_OPTIONS:
            raise ValueError(f"{len(labels)} states, and a question holds {MAX_OPTIONS}")
        for attempt in range(2):
            shuffled = list(labels)
            order.shuffle(shuffled)
            check(spend)
            reply = client.ask(text, [{"type": "choice", "name": "choose",
                                       "instructions": INSTRUCTIONS,
                                       "choices": [{"value": label} for label in shuffled]}])
            spend.add(input_tokens=reply.input_tokens, output_tokens=0,
                      seconds=reply.seconds, served=reply.served)
            answer = reply.answers.get("choose", {})
            if answer.get("type") == "choice" and "probabilities" in answer:
                break
            spend.refusals += 1
        else:
            spend.invalid_answers += 1
            return labels.index(shuffled[0])
        probabilities = {entry["value"]: float(entry["probability"])
                         for entry in answer["probabilities"]}
        spend.probabilities = [probabilities.get(label, 0.0) for label in labels]
        return max(range(len(labels)), key=lambda i: spend.probabilities[i])

    return choose
