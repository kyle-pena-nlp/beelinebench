"""Serve a Python function on the Jev protocol, at ``http://localhost:<port>/v1/systemone``.

Some local models come as Python code and not as a server. Clef, for example,
gives a function ``systemone(model, processor, body)``. This module gives such a
model a server, so that a chooser of ``beelinebench.toml`` can call it:

    python -m beelinebench.serve --port 8001 my_clef:systemone

``my_clef:systemone`` is a module and a function. The function takes the body
of a request (a dict) and gives the body of the response (a dict). The server
answers one request at a time, in the order they come.

With ``--batch N``, the function takes a list of bodies and gives a list of responses,
in the same order. A response can be an exception, which goes back to its caller only.
The server takes requests on several threads, and it gives the function the requests
that are waiting, up to N at a time. Use it when several runs send requests at the same
time, for example one run for each domain: a GPU answers a batch in about the time of
one request. A batched answer can differ a little from an unbatched one, because of
the padding of the batch.
"""

from __future__ import annotations

import argparse
import importlib
import json
import queue
import sys
import threading
from collections.abc import Callable
from http.server import BaseHTTPRequestHandler, HTTPServer, ThreadingHTTPServer

PATHS = ("/v1/systemone", "/systemone")


class Batcher:
    """Gives the waiting requests to a batch function, up to ``size`` at a time."""

    def __init__(self, function: Callable[[list[dict]], list], size: int,
                 wait: float) -> None:
        self.function, self.size, self.wait = function, size, wait
        self.waiting: queue.Queue = queue.Queue()
        threading.Thread(target=self.work, daemon=True).start()

    def ask(self, body: dict) -> dict:
        """The response to ``body``. It waits for the batch that holds it."""
        done, slot = threading.Event(), {}
        self.waiting.put((body, done, slot))
        done.wait()
        if isinstance(slot["out"], BaseException):
            raise slot["out"]
        return slot["out"]

    def work(self) -> None:
        while True:
            group = [self.waiting.get()]
            # A short wait lets the requests that come at the same time join the batch.
            while len(group) < self.size:
                try:
                    group.append(self.waiting.get(timeout=self.wait))
                except queue.Empty:
                    break
            try:
                outs = self.function([body for body, _, _ in group])
                if len(outs) != len(group):
                    raise ValueError(f"{len(group)} requests and {len(outs)} responses")
            except Exception as error:  # noqa: BLE001 - each caller gets the error
                outs = [error] * len(group)
            for (_, done, slot), out in zip(group, outs):
                slot["out"] = out
                done.set()


def server(function: Callable, port: int, batch: int = 1, wait: float = 0.005) -> HTTPServer:
    """A server on ``127.0.0.1:port`` that answers each request with ``function``.

    With ``batch`` above 1, ``function`` takes a list of bodies; see the module.
    """
    answer = Batcher(function, batch, wait).ask if batch > 1 else function

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:
            if self.path.rstrip("/") not in PATHS:
                self.send_error(404, f"the paths are {', '.join(PATHS)}")
                return
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            try:
                # The client checks that the model that answered is the model it
                # asked for. The function serves the name it is asked for.
                out = json.dumps({"model": body.get("model"), **answer(body)}).encode()
                status = 200
            except Exception as exc:  # the model's error goes back to the caller
                out = json.dumps({"error": f"{type(exc).__name__}: {exc}"}).encode()
                status = 500
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(out)))
            self.end_headers()
            self.wfile.write(out)

        def log_message(self, *args: object) -> None:
            pass

    kind = ThreadingHTTPServer if batch > 1 else HTTPServer
    return kind(("127.0.0.1", port), Handler)


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m beelinebench.serve")
    parser.add_argument("function", help="module:function, which takes and gives a body, or "
                        "with --batch a list of bodies")
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--batch", type=int, default=1,
                        help="the most requests that the function gets at a time. The default, "
                        "1, answers one request at a time")
    parser.add_argument("--wait", type=float, default=0.005,
                        help="seconds that a batch waits for more requests. The default is 0.005")
    args = parser.parse_args()
    module, name = args.function.split(":")
    sys.path.insert(0, ".")
    function = getattr(importlib.import_module(module), name)
    print(f"serving {args.function} at http://127.0.0.1:{args.port}/v1/systemone"
          + (f", up to {args.batch} requests at a time" if args.batch > 1 else ""))
    server(function, args.port, args.batch, args.wait).serve_forever()


if __name__ == "__main__":
    main()
