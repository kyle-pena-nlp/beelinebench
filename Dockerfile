# BeelineBench in a container: the code, its locked dependencies, and the word list of the
# word ladder domain, which is in the public domain. The image does not hold the Wikispeedia
# data: SNAP gives it no license to redistribute, so a run fetches it from SNAP on first use.
# Each fetch checks the SHA-256 of the data, so each machine has the same trials. The image
# holds no key: give the keys at run time.
#
#   docker build -t beelinebench .
#   docker run --rm -v "$PWD/secrets:/run/secrets:ro" -v "$PWD/results:/app/results" \
#     -v beelinebench-wikispeedia:/app/data/wikispeedia beelinebench run --mini
#
# See docs/lab-integration.md.
FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:0.5.2 /uv /uvx /bin/

WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_FROZEN=1 \
    COLUMNS=160

# The dependencies first, so that a change to the code does not install them again.
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --no-install-project --extra plot --extra llm

COPY . .
RUN uv sync --extra plot --extra llm && uv run python -m beelinebench download --domain word_ladder

ENTRYPOINT ["uv", "run", "python", "-m", "beelinebench"]
CMD ["--help"]
