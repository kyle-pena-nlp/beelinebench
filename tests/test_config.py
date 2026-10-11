from pathlib import Path

import httpx
import pytest

from beelinebench import benchmark, config
from beelinebench.jev import JevClient, JevError

PROJECT = Path(__file__).parent.parent


def test_the_config_file_loads(tmp_path):
    path = tmp_path / "beelinebench.toml"
    path.write_text("""
[run]
benchmark = "1.0.0"
choosers = ["remote"]

[chooser.remote]
protocol = "jev"
model = "jev-1.13.0"
api_base = "https://api.typesafe.ai/v1"
api_key_env = "SOME_KEY"
max_requests = 10
max_input_tokens = 1000

[chooser.local]
protocol = "jev"
model = "local"
api_base = "http://localhost:8000/v1"
max_requests = 10
max_input_tokens = 1000
""")
    (tmp_path / ".env").write_text("SOME_KEY=secret\n")
    cfg = config.load(path, {})
    assert cfg.run.choosers == ("remote",) and cfg.run.domains is None
    assert config.key(cfg.choosers["remote"], tmp_path / ".env") == "secret"
    assert config.key(cfg.choosers["local"], tmp_path / ".env") is None


def test_the_project_config_loads():
    officials = benchmark.load(PROJECT / "benchmarks.toml")
    cfg = config.load(PROJECT / "beelinebench.toml", officials)
    assert cfg.choosers["jev-1.13"].protocol == "jev"
    assert cfg.run.benchmark in officials


def test_an_experiment_cannot_take_an_official_name(tmp_path):
    officials = benchmark.load(PROJECT / "benchmarks.toml")
    path = tmp_path / "beelinebench.toml"
    path.write_text("""
[run]
benchmark = "1.0.0"

[benchmark."1.0.0"]
trials = 1
max_expansions = 2500
max_frontier = 255
[benchmark."1.0.0".domains.tiles]
heuristic = "manhattan"
scramble = 16
""")
    with pytest.raises(config.ConfigError):
        config.load(path, officials)


def test_a_local_model_gets_no_key():
    seen = []

    def answer(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"model": "local",
                                         "answers": {"choose": {"probabilities": {}}}})

    client = JevClient(api_key=None, model="local", api_base="http://localhost:8000/v1",
                       http=httpx.Client(transport=httpx.MockTransport(answer)))
    client.ask({}, {"choose": {}})
    assert str(seen[0].url) == "http://localhost:8000/v1/systemone"
    assert "authorization" not in seen[0].headers


def test_each_model_has_its_own_draws():
    from beelinebench.rng import Draws

    assert Draws("tiles", 1, "order", "a").random() != Draws("tiles", 1, "order", "b").random()


def serve(systemone):
    """Ask ``systemone``, served on a free port, one question as model ``stub``."""
    import threading

    from beelinebench.serve import server

    running = server(systemone, 0)
    port = running.server_address[1]
    threading.Thread(target=running.serve_forever, daemon=True).start()
    try:
        client = JevClient(api_key=None, model="stub", api_base=f"http://127.0.0.1:{port}/v1")
        return client.ask({}, {"choose": {"type": "choice", "instructions": "",
                                          "criteria": {"a": None, "b": None}}})
    finally:
        running.shutdown()


def test_a_python_function_can_be_served_on_the_protocol():
    def systemone(body: dict) -> dict:
        options = list(body["questions"]["choose"]["criteria"])
        return {"usage": {"input_tokens": 3},
                "answers": {"choose": {"probabilities": {o: float(o == options[-1])
                                                         for o in options}}}}

    reply = serve(systemone)
    assert reply.answers["choose"]["probabilities"] == {"a": 0.0, "b": 1.0}
    assert reply.served == "stub"


def test_a_served_function_that_names_another_model_is_an_error():
    with pytest.raises(JevError, match="'stub-1' answered"):
        serve(lambda body: {"model": "stub-1", "answers": {}})


def test_a_cloudflare_answer_is_unwrapped_from_its_envelope():
    seen = []

    def answer(request: httpx.Request) -> httpx.Response:
        seen.append(str(request.url))
        return httpx.Response(200, json={"success": True, "errors": [], "messages": [], "result": {
            "model": "clef", "answers": {"choose": {"probabilities": {"a": 1.0}}},
            "usage": {"input_tokens": 9}}})

    client = JevClient(api_key="k", model="clef", endpoint="clef",
                       api_base="https://api.cloudflare.com/client/v4/accounts/123/ai/run/@cf/cloudflare",
                       http=httpx.Client(transport=httpx.MockTransport(answer)))
    reply = client.ask({}, {"choose": {}})
    assert seen == ["https://api.cloudflare.com/client/v4/accounts/123/ai/run/@cf/cloudflare/clef"]
    assert reply.served == "clef" and reply.input_tokens == 9


def test_a_setting_in_an_address_comes_from_the_env_file(tmp_path):
    env = tmp_path / ".env"
    env.write_text("ACCOUNT=abc\n")
    assert config.expand("https://x/accounts/${ACCOUNT}/run", env) == "https://x/accounts/abc/run"
    with pytest.raises(config.ConfigError, match="MISSING"):
        config.expand("${MISSING}", env)


def test_every_hosted_chooser_has_a_price():
    officials = benchmark.load(PROJECT / "benchmarks.toml")
    for c in config.load(PROJECT / "beelinebench.toml", officials).choosers.values():
        hosted = c.api_base is None or not c.api_base.startswith("http://localhost")
        assert (c.price_input is not None) == hosted, c.name


def test_a_key_can_come_from_a_secret_file(tmp_path, monkeypatch):
    from beelinebench.config import setting

    env_file = tmp_path / ".env"
    monkeypatch.delenv("SOME_KEY", raising=False)
    monkeypatch.delenv("SOME_KEY_FILE", raising=False)
    assert setting("SOME_KEY", env_file, secrets=tmp_path / "none") is None
    (tmp_path / "secrets").mkdir()
    (tmp_path / "secrets" / "SOME_KEY").write_text("from-docker-secret\n")
    assert setting("SOME_KEY", env_file, secrets=tmp_path / "secrets") == "from-docker-secret"
    (tmp_path / "key.txt").write_text("from-file-variable")
    monkeypatch.setenv("SOME_KEY_FILE", str(tmp_path / "key.txt"))
    assert setting("SOME_KEY", env_file, secrets=tmp_path / "secrets") == "from-file-variable"
    monkeypatch.setenv("SOME_KEY", "from-environment")
    assert setting("SOME_KEY", env_file, secrets=tmp_path / "secrets") == "from-environment"
