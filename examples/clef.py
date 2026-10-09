"""Clef or Clef-flash on the Jev protocol, for ``python -m beelinebench.serve``.

    uv sync --extra clef
    python -m beelinebench.serve --port 8001 examples.clef:systemone
    CLEF_REPO=Cloudflare/clef-flash python -m beelinebench.serve --port 8002 examples.clef:systemone

It loads the model as its model card shows, with ``load_release_model`` and
``systemone`` from the model's own ``joint_schema_model.py``. ``CLEF_REPO`` names
the model. ``CLEF_DEVICE`` names the device. Without it, the device is ``cuda``
when there is one, then ``mps``, then ``cpu``.

The model cards test on one H200. In bfloat16, Clef (27B) needs about 55 GB of
memory and Clef-flash (9B) about 19 GB, plus room for the frontier.

Clef answers with the softmax of its logits. It does not sample, so the same
request gives the same probabilities, up to floating-point differences between
devices.
"""

import os
import sys

import torch
from huggingface_hub import snapshot_download


def device() -> str:
    if "CLEF_DEVICE" in os.environ:
        return os.environ["CLEF_DEVICE"]
    if torch.cuda.is_available():
        return "cuda"
    if torch.backends.mps.is_available():
        return "mps"
    return "cpu"


path = snapshot_download(os.environ.get("CLEF_REPO", "Cloudflare/clef"))
sys.path.insert(0, path)
from joint_schema_model import load_release_model, systemone as clef_systemone  # noqa: E402

model, processor = load_release_model(path, device=device())


def systemone(body: dict) -> dict:
    return clef_systemone(model, processor, body)
