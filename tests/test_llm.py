import json
from types import SimpleNamespace

from beelinebench.llm import llm_chooser
from beelinebench.rng import Draws
from beelinebench.search import Spend


class FakeClient:
    """Answers with the number of the line that holds ``favourite``."""

    def __init__(self, favourite: str) -> None:
        self.favourite = favourite
        self.messages = self

    def create(self, **request):
        lines = request["messages"][0]["content"].splitlines()
        number = next(int(line.split(".")[0]) for line in lines
                      if line.endswith(f". {self.favourite}"))
        return SimpleNamespace(
            model="claude-test-1", stop_reason="end_turn",
            usage=SimpleNamespace(input_tokens=11, output_tokens=3),
            content=[SimpleNamespace(type="text", text=json.dumps({"state": number}))])


def test_the_chooser_maps_the_number_back_to_the_state():
    spend = Spend(max_requests=5, max_input_tokens=10**9)
    choose = llm_chooser(FakeClient("s2"), model="m", effort=None, objective="o",
                         context="c", render=lambda s: f"s{s}", spend=spend,
                         order=Draws("test"))
    assert choose([0, 1, 2, 3]) == 2
    assert (spend.requests, spend.input_tokens, spend.output_tokens) == (1, 11, 3)
    assert spend.served == ["claude-test-1"] and len(spend.latencies_ms) == 1
