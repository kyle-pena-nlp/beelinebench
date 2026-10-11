# Run Clef on your own GPU

Cloudflare Workers AI hosts Clef and Clef-flash, and the `clef` and `clef-flash` choosers use that service. You can also run the models on your own GPU, with the `clef-local` and `clef-flash-local` choosers. `examples/clef.py` loads the model from Hugging Face and serves it with `beelinebench.serve`.

| model | parameters | memory in bfloat16 | chooser | port |
|---|---|---|---|---|
| Clef | 27B | about 55 GB | `clef-local` | 8001 |
| Clef-flash | 9B | about 19 GB | `clef-flash-local` | 8002 |

The model cards test on one H200 GPU. An 80 GB GPU holds both models. A Mac with 24 GB of memory cannot hold Clef, and Clef-flash on it is slow.

`examples/clef.py` pins the Hugging Face revision of each model, so each machine loads the same weights and code. The labels of the choosers name these revisions:

| model | revision | date |
|---|---|---|
| Clef | `0b331204bb13fbd2ca93a64df1956f5b55478ce5` | 2026-10-09 |
| Clef-flash | `8b2e5fd17c09fd49bc2880b805d5323ec7ff4ff3` | 2026-10-09 |

To use a different revision, change `REVISIONS` in `examples/clef.py` and the labels in `beelinebench.toml` together.

## The length of a request

The model's own `systemone` reads at most 16,384 tokens. Above that, it cuts the state, or it refuses a request whose options are longer. Workers AI reads 65,536 tokens. Some BeelineBench questions are longer than 16,384 tokens: in the hosted pilots, 70 Clef requests and 473 Clef-flash requests were, most of them in Blocksworld, up to about 20,000 tokens. Thus, `examples/clef.py` reads up to 65,536 tokens, so that the local model sees the same request as the hosted model. `CLEF_MAX_LENGTH` changes this length.

## Run the benchmark on a rented GPU

These steps run the full benchmark on the GPU machine itself. An 80 GB GPU, for example an H100, holds one model with room for long requests. Run the two models one after the other.

A search sends one request at a time, so one run keeps the GPU mostly idle. These steps run the seven domains at the same time, and the server answers the requests that come together in one forward pass.

1. On the GPU machine, clone the repository, and install BeelineBench with the Clef dependencies.

   ```bash
   git clone https://github.com/kyle-pena-nlp/beelinebench && cd beelinebench
   uv sync --extra clef
   ```

2. Copy the traces of the hosted pilots from your machine. Git ignores the traces.

   ```bash
   # On your machine:
   rsync -a traces/1.0.0/clef traces/1.0.0/clef-flash <gpu-host>:beelinebench/traces/1.0.0/
   ```

3. Start the server of Clef-flash, one request at a time, for example in `tmux`. The first start downloads the model.

   ```bash
   CLEF_REPO=Cloudflare/clef-flash uv run python -m beelinebench.serve --port 8002 examples.clef:systemone
   ```

4. Compare the local model with the hosted pilot. `agreement` sends each traced question again, with the same options in the same order. It gives the share of questions where the two models chose the same option. Note the requests each second, to estimate the time of a full run.

   ```bash
   uv run python -m beelinebench agreement --chooser clef-flash-local --against clef-flash
   ```

   If the hosted model has the same weights and precision, the share is near 100%. If it is much lower, add the result to [Model quirks](model-quirks.md).

5. Stop the server, and start it again with batches.

   ```bash
   CLEF_REPO=Cloudflare/clef-flash uv run python -m beelinebench.serve --port 8002 --batch 8 examples.clef:systemone_batch
   ```

6. Compare the batched model with the hosted pilot again. Run one `agreement` for each domain at the same time, so that the requests come together and make batches.

   ```bash
   for d in tiles blocksworld countdown word_ladder wikispeedia rush_hour keys_doors; do
     uv run python -m beelinebench agreement --chooser clef-flash-local --against clef-flash --domain $d > agreement-$d.txt &
   done; wait; cat agreement-*.txt
   ```

   If the shares are the same as in step 4, batches do not change the choices. If they are lower, use the server of step 3 for the full run, and accept the longer time.

7. Run the benchmark: one run for each domain, at the same time. A full run takes hours, so run it in `tmux`. The local choosers have no price, so no cost limit stops them. `max_requests` in `beelinebench.toml` still applies.

   ```bash
   for d in tiles blocksworld countdown word_ladder wikispeedia rush_hour keys_doors; do
     uv run python -m beelinebench run --chooser clef-flash-local --domain $d > run-$d.log 2>&1 &
   done; wait
   ```

   If a run stops, run the same command again. It continues from the trials that have a result.

8. Do steps 3 to 7 again for Clef: port 8001, the chooser `clef-local`, the hosted pilot `clef`, and no `CLEF_REPO`.

9. Bring the results back. Commit `results/1.0.0/clef-local/` and `results/1.0.0/clef-flash-local/` on the GPU machine, and push. Git ignores the traces, so copy them to your machine.

   ```bash
   # On your machine:
   git pull
   rsync -a <gpu-host>:beelinebench/traces/1.0.0/clef-local <gpu-host>:beelinebench/traces/1.0.0/clef-flash-local traces/1.0.0/
   uv run python -m beelinebench readme
   ```

## Run the models on one machine and the benchmark on another

The servers listen only on `127.0.0.1`. To run BeelineBench on your machine with the models on the GPU machine, forward the ports over SSH:

```bash
ssh -N -L 8001:localhost:8001 -L 8002:localhost:8002 <gpu-host>
```

`examples/clef.py` uses `cuda` if it is available, then `mps`, then `cpu`. To select a device, set `CLEF_DEVICE`. Clef does not sample, so identical requests give the same probabilities on the same device.

The `haiku` chooser uses the Anthropic API. It is a reference point, not a choice model. It can reason before it answers, and the choice models cannot. Thus, its score does not measure the same ability. The setting `publish = false` in `beelinebench.toml` keeps its results out of the README figure, the results table, and the price estimates. Its results stay in `results/`, and `report` shows them.

Run each command from the root of the repository.
