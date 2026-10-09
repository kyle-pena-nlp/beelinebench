import json

import httpx
import pytest

from beelinebench.jev import JevClient, JevError, jev_chooser
from beelinebench.rng import Draws
from beelinebench.search import BudgetExhausted, Spend


def client_that_prefers(favourite: str, sent: list[dict]) -> JevClient:
    """A client whose answers give ``favourite`` the highest probability."""

    def answer(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        sent.append(body)
        answers = {}
        for name, question in body["questions"].items():
            options = list(question["criteria"])
            probabilities = {o: (0.9 if o == favourite else 0.1 / len(options)) for o in options}
            answers[name] = {"probabilities": probabilities}
        return httpx.Response(200, json={"model": body["model"], "answers": answers,
                                         "usage": {"input_tokens": 7}})

    return JevClient(api_key="k", model="jev-test", api_base="https://example.test/v1",
                     http=httpx.Client(transport=httpx.MockTransport(answer)))


def test_the_chooser_takes_the_most_probable_state():
    sent: list[dict] = []
    spend = Spend(max_requests=5, max_input_tokens=10**9)
    choose = jev_chooser(client_that_prefers("s2", sent), objective="o", context="c",
                         render=lambda s: f"s{s}", spend=spend, order=Draws("test"))
    assert choose([0, 1, 2, 3]) == 2
    assert spend.requests == 1 and spend.input_tokens == 7
    assert spend.served == ["jev-test"] and len(spend.latencies_ms) == 1
    assert sorted(sent[0]["questions"]["choose"]["criteria"]) == ["s0", "s1", "s2", "s3"]


def test_a_full_frontier_is_one_question():
    sent: list[dict] = []
    choose = jev_chooser(client_that_prefers("s254", sent), objective="o", context="c",
                         render=lambda s: f"s{s}", spend=Spend(max_requests=5, max_input_tokens=10**9), order=Draws("test"))
    assert choose(list(range(255))) == 254
    assert len(sent) == 1 and len(sent[0]["questions"]["choose"]["criteria"]) == 255


def test_the_budget_stops_the_run():
    choose = jev_chooser(client_that_prefers("s0", []), objective="o", context="c",
                         render=lambda s: f"s{s}", spend=Spend(max_requests=0, max_input_tokens=0), order=Draws("test"))
    with pytest.raises(BudgetExhausted):
        choose([0, 1])


@pytest.mark.parametrize("payload", [{"model": "jev-1.12.0"}, {}])
def test_an_answer_from_another_model_is_an_error(payload):
    def answer(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={**payload, "answers": {}, "usage": {}})

    client = JevClient(api_key="k", model="jev-1.13.0", api_base="https://example.test/v1",
                       http=httpx.Client(transport=httpx.MockTransport(answer)))
    with pytest.raises(JevError, match="asked for model 'jev-1.13.0'"):
        client.ask({}, {})


def test_the_decisions_chooser_asks_one_choice_question():
    from beelinebench.decisions import DecisionsClient, DecisionsError, decisions_chooser

    sent: list[dict] = []

    def answer(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        sent.append(body)
        question = body["questions"][0]
        values = [c["value"] for c in question["choices"]]
        return httpx.Response(200, json={
            "model": body["model"], "usage": {"input_tokens": 11},
            "answers": [{"type": "choice", "name": question["name"], "choice": "s1",
                         "confidence": 0.9,
                         "probabilities": [{"value": v, "probability": 0.9 if v == "s1" else 0.05}
                                           for v in values]}]})

    client = DecisionsClient(api_key="k", model="gpt-6-luna",
                             http=httpx.Client(transport=httpx.MockTransport(answer)))
    assert client.url == "https://api.openai.com/v1/decisions"
    spend = Spend(max_requests=5, max_input_tokens=10**9)
    choose = decisions_chooser(client, objective="o", context="c", render=lambda s: f"s{s}",
                               spend=spend, order=Draws("test"))
    assert choose([0, 1, 2]) == 1
    assert spend.input_tokens == 11 and spend.served == ["gpt-6-luna"]
    question = sent[0]["questions"][0]
    assert question["type"] == "choice" and sorted(c["value"] for c in question["choices"]) \
        == ["s0", "s1", "s2"]
    assert "Goal: o" in sent[0]["input"]

    other = DecisionsClient(api_key="k", model="gpt-6-luna", http=httpx.Client(
        transport=httpx.MockTransport(lambda r: httpx.Response(200, json={
            "model": "gpt-6-luna-2026-09-29", "answers": []}))))
    with pytest.raises(DecisionsError, match="'gpt-6-luna-2026-09-29' answered"):
        other.ask("x", [])


def test_no_credits_is_not_retried():
    from beelinebench.decisions import DecisionsClient, DecisionsError

    calls = []

    def answer(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(429, json={"error": {"type": "insufficient_quota"}})

    client = DecisionsClient(api_key="k", model="gpt-6-luna",
                             http=httpx.Client(transport=httpx.MockTransport(answer)))
    with pytest.raises(DecisionsError, match="429"):
        client.ask("x", [])
    assert len(calls) == 1


def test_two_refusals_take_the_first_state_of_the_last_order():
    from beelinebench.decisions import DecisionsClient, decisions_chooser

    sent: list[dict] = []

    def answer(request: httpx.Request) -> httpx.Response:
        sent.append(json.loads(request.content))
        return httpx.Response(200, json={"model": "gpt-6-luna", "usage": {"input_tokens": 5},
                                         "answers": [{"type": "refusal", "name": "choose"}]})

    client = DecisionsClient(api_key="k", model="gpt-6-luna",
                             http=httpx.Client(transport=httpx.MockTransport(answer)))
    spend = Spend(max_requests=5, max_input_tokens=10**9)
    choose = decisions_chooser(client, objective="o", context="c", render=lambda s: f"s{s}",
                               spend=spend, order=Draws("test"))
    index = choose([0, 1, 2, 3])
    assert (spend.requests, spend.refusals, spend.invalid_answers) == (2, 2, 1)
    assert sent[0]["questions"][0]["choices"] != sent[1]["questions"][0]["choices"]
    assert f"s{index}" == sent[1]["questions"][0]["choices"][0]["value"]


def test_a_refusal_is_asked_again_in_a_new_order():
    from beelinebench.decisions import DecisionsClient, decisions_chooser

    sent: list[list[str]] = []

    def answer(request: httpx.Request) -> httpx.Response:
        values = [c["value"] for c in json.loads(request.content)["questions"][0]["choices"]]
        sent.append(values)
        if len(sent) == 1:
            reply = {"type": "refusal", "name": "choose"}
        else:
            reply = {"type": "choice", "name": "choose", "choice": "s2", "confidence": 0.9,
                     "probabilities": [{"value": v, "probability": float(v == "s2")} for v in values]}
        return httpx.Response(200, json={"model": "gpt-6-luna", "usage": {"input_tokens": 5},
                                         "answers": [reply]})

    client = DecisionsClient(api_key="k", model="gpt-6-luna",
                             http=httpx.Client(transport=httpx.MockTransport(answer)))
    spend = Spend(max_requests=5, max_input_tokens=10**9)
    choose = decisions_chooser(client, objective="o", context="c", render=lambda s: f"s{s}",
                               spend=spend, order=Draws("test"))
    assert choose([0, 1, 2, 3]) == 2
    assert len(sent) == 2 and sent[0] != sent[1] and sorted(sent[0]) == sorted(sent[1])
    assert (spend.requests, spend.refusals, spend.invalid_answers) == (2, 1, 0)


def test_replaced_text_reaches_the_api_and_the_answer_maps_back():
    sent: list[dict] = []
    choose = jev_chooser(client_that_prefers("b|c", sent), objective="reach a/b", context="rows by /",
                         render=lambda s: s, spend=Spend(max_requests=5, max_input_tokens=10**9),
                         order=Draws("test"), replace={"/": "|"})
    assert choose(["a/b", "b/c"]) == 1
    assert sorted(sent[0]["questions"]["choose"]["criteria"]) == ["a|b", "b|c"]
    assert sent[0]["state"]["goal"] == "reach a|b" and sent[0]["state"]["context"] == "rows by |"
