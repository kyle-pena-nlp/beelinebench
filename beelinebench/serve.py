"""Serve a Python function on the Jev protocol, at ``http://localhost:<port>/v1/systemone``.

Some local models come as Python code and not as a server. Clef, for example,
gives a function ``systemone(model, processor, body)``. This module gives such a
model a server, so that a chooser of ``beelinebench.toml`` can call it:

    python -m beelinebench.serve --port 8001 my_clef:systemone

``my_clef:systemone`` is a module and a function. The function takes the body
of a request (a dict) and gives the body of the response (a dict). The server
answers one request at a time, in the order they come.
"""

from __future__ import annotations

import argparse
import importlib
import json
import sys
from collections.abc import Callable
from http.server import BaseHTTPRequestHandler, HTTPServer

PATHS = ("/v1/systemone", "/systemone")


def server(function: Callable[[dict], dict], port: int) -> HTTPServer:
    """A server on ``127.0.0.1:port`` that answers each request with ``function``."""

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:
            if self.path.rstrip("/") not in PATHS:
                self.send_error(404, f"the paths are {', '.join(PATHS)}")
                return
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            try:
                # The client checks that the model that answered is the model it
                # asked for. The function serves the name it is asked for.
                out = json.dumps({"model": body.get("model"), **function(body)}).encode()
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

    return HTTPServer(("127.0.0.1", port), Handler)


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m beelinebench.serve")
    parser.add_argument("function", help="module:function, which takes and gives a body")
    parser.add_argument("--port", type=int, required=True)
    args = parser.parse_args()
    module, name = args.function.split(":")
    sys.path.insert(0, ".")
    function = getattr(importlib.import_module(module), name)
    print(f"serving {args.function} at http://127.0.0.1:{args.port}/v1/systemone")
    server(function, args.port).serve_forever()


if __name__ == "__main__":
    main()
