"""The server batches requests that come at the same time, and keeps each answer apart."""

import threading

import httpx

from beelinebench.serve import server


def test_a_batch_server_answers_each_request_and_groups_them():
    sizes: list[int] = []

    def batch(bodies):
        sizes.append(len(bodies))
        return [ValueError("bad request") if body["state"] == "bad"
                else {"answers": {"echo": body["state"]}} for body in bodies]

    running = server(batch, 0, batch=8, wait=0.05)
    port = running.server_address[1]
    threading.Thread(target=running.serve_forever, daemon=True).start()
    states = [f"s{n}" for n in range(6)] + ["bad"]
    replies: dict = {}

    def ask(state):
        replies[state] = httpx.post(f"http://127.0.0.1:{port}/v1/systemone",
                                    json={"model": "m", "state": state}, timeout=10)

    threads = [threading.Thread(target=ask, args=(s,)) for s in states]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    running.shutdown()
    for state in states[:-1]:
        assert replies[state].status_code == 200
        assert replies[state].json() == {"model": "m", "answers": {"echo": state}}
    assert replies["bad"].status_code == 500 and "bad request" in replies["bad"].json()["error"]
    assert sum(sizes) == len(states) and max(sizes) > 1
