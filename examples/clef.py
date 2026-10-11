"""Clef or Clef-flash on the Jev protocol, for ``python -m beelinebench.serve``.

    uv sync --extra clef
    python -m beelinebench.serve --port 8001 examples.clef:systemone
    CLEF_REPO=Cloudflare/clef-flash python -m beelinebench.serve --port 8002 examples.clef:systemone

    # Several requests in one forward pass, for runs that send requests in parallel:
    python -m beelinebench.serve --port 8001 --batch 8 examples.clef:systemone_batch

The model's own ``systemone`` reads at most 16,384 tokens: it cuts the state, and it
refuses a request whose options are longer. Workers AI reads 65,536, and BeelineBench
questions reach about 20,000 tokens. So this module reads ``CLEF_MAX_LENGTH`` tokens,
65,536 by default, to see the same request as the hosted model. ``CLEF_BATCH_TOKENS``
caps the padded tokens of one forward pass of ``systemone_batch``, 65,536 by default.

It loads the model as its model card shows, with ``load_release_model`` and
``systemone`` from the model's own ``joint_schema_model.py``. ``CLEF_REPO`` names
the model. The revision of each model is pinned in ``REVISIONS``, so each run uses the
same weights and code. ``CLEF_REVISION`` selects a different revision. ``CLEF_DEVICE``
names the device. Without it, the device is ``cuda``
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


#: The Hugging Face commit of each model. The labels of the choosers in beelinebench.toml
#: name these commits. Change both together.
REVISIONS = {
    "Cloudflare/clef": "0b331204bb13fbd2ca93a64df1956f5b55478ce5",        # 2026-10-09
    "Cloudflare/clef-flash": "8b2e5fd17c09fd49bc2880b805d5323ec7ff4ff3",  # 2026-10-09
}

repo = os.environ.get("CLEF_REPO", "Cloudflare/clef")
path = snapshot_download(repo, revision=os.environ.get("CLEF_REVISION", REVISIONS.get(repo)))
sys.path.insert(0, path)
from joint_schema_model import (  # noqa: E402
    collate_records, encode_record, load_release_model, systemone as clef_systemone,
    systemone_answer)

model, processor = load_release_model(path, device=device())
MAX_LENGTH = int(os.environ.get("CLEF_MAX_LENGTH", 65536))
MAX_BATCH_TOKENS = int(os.environ.get("CLEF_BATCH_TOKENS", 65536))


def systemone(body: dict) -> dict:
    return clef_systemone(model, processor, body, max_length=MAX_LENGTH)


def systemone_batch(bodies: list[dict]) -> list:
    """The answers to ``bodies``, in their order, with as few forward passes as fit.

    A pass holds requests while its padded length (requests times the longest) stays
    under ``MAX_BATCH_TOKENS``. A request that fails gives its exception in its place, and
    the others still get answers.
    """
    out: list = [None] * len(bodies)
    encoded = {}
    for index, body in enumerate(bodies):
        try:
            # The checks of the model's own systemone, without its forward pass.
            if not isinstance(body.get("model"), str) or "state" not in body:
                raise ValueError("model and state are required")
            if not isinstance(body.get("questions"), dict) or not body["questions"]:
                raise ValueError("at least one question is required")
            encoded[index] = encode_record(processor.tokenizer, body, max_length=MAX_LENGTH,
                                           processor=processor)
        except Exception as error:  # noqa: BLE001 - the error goes back to its caller
            out[index] = error
    device_of_model = next(model.parameters()).device
    waiting = sorted(encoded, key=lambda i: len(encoded[i].input_ids))
    while waiting:
        group = [waiting.pop(0)]
        while waiting and (len(group) + 1) * len(encoded[waiting[0]].input_ids) <= MAX_BATCH_TOKENS:
            group.append(waiting.pop(0))
        try:
            with torch.inference_mode():
                logits = model(collate_records([encoded[i] for i in group],
                                               processor.tokenizer.pad_token_id, device_of_model))
        except Exception as error:  # noqa: BLE001
            for i in group:
                out[i] = error
            continue
        for i, record_logits in zip(group, logits):
            questions = bodies[i]["questions"]
            out[i] = {
                "model": bodies[i]["model"],
                "answers": {
                    q.question_id: systemone_answer(
                        questions[q.question_id],
                        dict(zip(q.option_ids, q_logits.float().softmax(-1).tolist())))
                    for q, q_logits in zip(encoded[i].questions, record_logits)},
                "usage": {"input_tokens": len(encoded[i].input_ids), "output_tokens": 0},
            }
    return out
