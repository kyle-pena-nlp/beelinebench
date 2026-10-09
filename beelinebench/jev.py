"""A Jev-like model as the chooser of a best-first search.

The protocol is Jev's: ``POST {api_base}/systemone`` with a state and choice
questions. Any model that serves this protocol can be benchmarked, including a
local one at ``http://localhost:<port>/v1``. ``beelinebench.toml`` names the models.

Jev answers a choice question with a probability for each option. A question
holds at most 255 options. A request holds many questions, and Jev answers each
question by itself. Jev charges for input tokens only.

Each frontier state is one option, written by the ``render`` function of the
domain. The search keeps the frontier to 255 states, so each decision is one
question with every option in it. The chooser takes the state with the highest
probability.

To benchmark another model, write a function with the signature of
:data:`beelinebench.search.Chooser` and give it to :func:`beelinebench.run.measure`.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Mapping, Sequence
from typing import Any, NamedTuple

import httpx

from .rng import Draws
from .search import Chooser, ChooserError, Spend, check

MAX_OPTIONS = 255
#: A request with one of these statuses, or any 5xx status, is tried again.
RETRY_STATUS = {408, 429}
#: Tries of one request in all, and the most seconds to wait between two tries.
ATTEMPTS = 8
MAX_WAIT = 120.0

TASK = (
    "A search is looking for a way to reach `goal`. Each option in the question is "
    "a state that the search has found and has not explored yet. The search "
    "explores the state that you choose, and then asks again."
)
INSTRUCTIONS = (
    "Choose the state to explore next: the state from which `goal` can be reached "
    "in the fewest moves."
)


class JevError(ChooserError):
    """A Jev request failed, or a model other than the one asked for answered it."""


def wait(attempt: int, response: httpx.Response | None = None) -> float:
    """Seconds to wait before the next try: the API's ``Retry-After``, or 1, 2, 4 ... 60."""
    if response is not None:
        try:
            return min(MAX_WAIT, max(0.0, float(response.headers.get("retry-after", ""))))
        except ValueError:
            pass
    return min(60.0, 2.0 ** attempt)


def post(http: httpx.Client, url: str, body: dict, headers: dict, *,
         error: type[ChooserError], served: str | None = None) -> tuple[dict, float, int]:
    """POST ``body``, with retries. Give the response body, the seconds of the answered try,
    and the number of tries before it (the retries).

    An intermittent error is tried again, ``ATTEMPTS`` times in all, with a wait that
    grows to a minute or two: a timeout, a dropped connection, a 408 or 429 status, or a
    5xx status. The API's ``Retry-After`` sets the wait when it gives one. A 429 for an
    account with no credits is not intermittent, and stops at once.

    The response must say that ``served`` answered, or ``body["model"]`` when ``served``
    is ``None``. Any other model, or no model, is an ``error``. OpenRouter, for example,
    takes ``liquid/d1`` and answers with the dated name ``liquid/d1-20260930``.
    """
    last = ATTEMPTS - 1
    for attempt in range(ATTEMPTS):
        started = time.monotonic()
        try:
            response = http.post(url, json=body, headers=headers)
        except httpx.TransportError as exc:  # a timeout, or a dropped connection
            if attempt == last:
                raise error(f"{url} did not answer: {type(exc).__name__}: {exc}") from exc
            time.sleep(wait(attempt))
            continue
        if response.status_code < 400:
            seconds = time.monotonic() - started
            payload = response.json()
            if "answers" not in payload and isinstance(payload.get("result"), dict):
                payload = payload["result"]  # Cloudflare's envelope
            expected = served or body["model"]
            answered = payload.get("model")
            if answered != expected:
                raise error(f"asked for model {expected!r}, and the API says "
                            f"{answered!r} answered")
            return payload, seconds, attempt
        # A 429 is usually "slow down". OpenAI also sends it when the account has no
        # credits, and Cloudflare when the free allocation of the day is used up.
        out_of_credits = response.status_code == 429 and any(
            sign in response.text for sign in ("insufficient_quota", "free allocation"))
        intermittent = response.status_code in RETRY_STATUS or response.status_code >= 500
        if not intermittent or out_of_credits or attempt == last:
            raise error(f"{url} returned {response.status_code}: {response.text[:300]}")
        time.sleep(wait(attempt, response))
    raise AssertionError("not reached")


class Reply(NamedTuple):
    answers: dict
    input_tokens: int
    #: The model that the API says answered. It is always the model asked for.
    served: str
    seconds: float
    #: The tries that failed with an intermittent error before the answer.
    retries: int = 0


class JevClient:
    """Sends questions to ``POST {api_base}/systemone``.

    Each answer must name the model that answered it, and that model must be
    ``model``. Any other answer is a :class:`JevError`, so a result never holds
    answers from a model it does not name.

    ``endpoint`` follows ``api_base``. Jev's is ``systemone``. Perplexity serves the
    same protocol at ``decisions``, and Cloudflare at the name of the model. A
    response in Cloudflare's envelope (``{"result": ...}``) is unwrapped.

    ``api_key`` is ``None`` for an API that takes no key. ``http`` is the HTTP
    client to use. When it is ``None``, the client makes one.
    """

    def __init__(self, *, api_key: str | None, model: str, api_base: str,
                 served: str | None = None,
                 endpoint: str = "systemone", http: httpx.Client | None = None) -> None:
        self.model = model
        self.served = served
        self.url = api_base.rstrip("/") + "/" + endpoint.strip("/")
        self.http = http or httpx.Client(timeout=120.0)
        self.headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}

    def ask(self, state: dict, questions: dict[str, dict]) -> Reply:
        """Send one request. Give the answers, and what the request used.

        ``seconds`` is the time of the attempt that was answered.
        """
        body = {"model": self.model, "state": state, "questions": questions}
        payload, seconds, retries = post(self.http, self.url, body, self.headers,
                                         error=JevError, served=self.served)
        usage = payload.get("usage") or {}
        return Reply(payload["answers"], int(usage.get("input_tokens", 0)), payload["model"],
                     seconds, retries)


def jev_chooser(client: JevClient, *, objective: str, context: str,
                render: Callable[[Any], str], spend: Spend, order: Draws,
                replace: Mapping[str, str] = {}) -> Chooser:
    """A chooser that asks Jev one question over the whole frontier.

    The options go in a random order on each call, because Jev prefers options
    near the start of a list. ``order`` is the source of that order.

    ``replace`` maps text to the text that the API gets in its place, in the options
    and in the framing. Cloudflare's API rejects an option name that holds ``/``.
    """
    def shown(text: str) -> str:
        for old, new in replace.items():
            text = text.replace(old, new)
        return text

    framing = {"task": shown(TASK), "goal": shown(objective), "context": shown(context)}

    def choose(states: Sequence[Any]) -> int:
        spend.probabilities = None
        labels = [shown(render(state)) for state in states]
        if len(set(labels)) != len(labels):
            raise ValueError("two frontier states have the same rendering")
        if len(labels) > MAX_OPTIONS:
            raise ValueError(f"{len(labels)} states, and a question holds {MAX_OPTIONS}")
        shuffled = list(labels)
        order.shuffle(shuffled)
        check(spend)
        reply = client.ask(framing, {"choose": {
            "type": "choice", "instructions": INSTRUCTIONS,
            "criteria": {label: None for label in shuffled}}})
        spend.add(input_tokens=reply.input_tokens, output_tokens=0,
                  seconds=reply.seconds, served=reply.served, retries=reply.retries)
        probabilities = reply.answers["choose"]["probabilities"]
        spend.probabilities = [float(probabilities.get(label, 0.0)) for label in labels]
        return max(range(len(labels)), key=lambda i: spend.probabilities[i])

    return choose

