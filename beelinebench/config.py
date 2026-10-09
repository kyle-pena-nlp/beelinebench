"""``beelinebench.toml``: what to run, the choosers, and benchmarks for experiments."""

from __future__ import annotations

import os
import re
import tomllib
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from . import benchmark
from .benchmark import Benchmark
from .rng import Draws
from .search import Chooser, Problem, Spend

PROTOCOLS = ("jev", "openai", "anthropic")


class ConfigError(Exception):
    """``beelinebench.toml`` names something that does not exist."""


@dataclass(frozen=True)
class ChooserConfig:
    name: str
    protocol: str
    model: str
    api_base: str | None
    api_key_env: str | None
    effort: str | None
    #: Trials for this chooser. ``None`` takes the trials of the run.
    trials: int | None
    max_requests: int
    max_input_tokens: int
    #: The name of the model for a reader, for example "Jev 1.13". ``None`` uses ``name``.
    label: str | None = None
    #: jev only: the path after ``api_base``.
    endpoint: str = "systemone"
    #: jev only: text in the options and the framing, and the text that the API gets in its place.
    replace: dict[str, str] = field(default_factory=dict)
    #: The most that this model may cost in all runs. ``None`` takes ``[run] max_cost``.
    max_cost: float | None = None
    #: False leaves the chooser out of the README: its figure, results table and prices.
    publish: bool = True
    #: US dollars for a million input and output tokens. ``None`` for a local model.
    price_input: float | None = None
    price_output: float | None = None

    @property
    def title(self) -> str:
        return self.label or self.name


@dataclass(frozen=True)
class RunConfig:
    benchmark: str
    choosers: tuple[str, ...]
    #: ``None`` runs every domain of the benchmark.
    domains: tuple[str, ...] | None
    #: ``None`` takes the trials of the benchmark.
    trials: int | None
    #: The most that one model may cost in all runs, in US dollars. ``None`` for no limit.
    max_cost: float | None = None


@dataclass(frozen=True)
class Config:
    run: RunConfig
    choosers: dict[str, ChooserConfig]
    #: Benchmarks for experiments. Official ones are in ``benchmarks.toml``.
    benchmarks: dict[str, Benchmark]


def load(path: Path, officials: dict[str, Benchmark]) -> Config:
    data = tomllib.loads(path.read_text())
    choosers = {}
    for name, table in data.get("chooser", {}).items():
        if table.get("protocol") not in PROTOCOLS:
            raise ConfigError(f"chooser {name}: protocol must be one of {PROTOCOLS}")
        if table["protocol"] == "jev" and not table.get("api_base"):
            raise ConfigError(f"chooser {name}: a jev chooser needs api_base")
        if table["protocol"] == "openai" and not table.get("api_key_env"):
            raise ConfigError(f"chooser {name}: an openai chooser needs api_key_env")
        choosers[name] = ChooserConfig(
            name=name, protocol=table["protocol"], model=table["model"],
            api_base=table.get("api_base"), api_key_env=table.get("api_key_env"),
            effort=table.get("effort"), trials=table.get("trials"),
            max_requests=table["max_requests"], max_input_tokens=table["max_input_tokens"],
            label=table.get("label"), endpoint=table.get("endpoint", "systemone"),
            replace=dict(table.get("replace", {})), publish=table.get("publish", True),
            max_cost=table.get("max_cost"),
            price_input=table.get("price_input"), price_output=table.get("price_output"))
    customs = benchmark.parse(data.get("benchmark", {}))
    for name in customs:
        if name in officials:
            raise ConfigError(f"benchmark {name} is official. Give the experiment another name.")
    run = data.get("run", {})
    return Config(
        run=RunConfig(benchmark=run["benchmark"], choosers=tuple(run.get("choosers", ())),
                      domains=tuple(run["domains"]) if "domains" in run else None,
                      trials=run.get("trials"), max_cost=run.get("max_cost")),
        choosers=choosers, benchmarks=customs)


def unpublished(choosers: dict[str, ChooserConfig]) -> set[str]:
    """The choosers that the README leaves out."""
    return {c.name for c in choosers.values() if not c.publish}


def setting(name: str, env_file: Path) -> str | None:
    """A value from ``env_file``, or from the environment."""
    from dotenv import dotenv_values

    return dotenv_values(env_file).get(name) or os.environ.get(name)


def expand(text: str, env_file: Path) -> str:
    """``text`` with each ``${NAME}`` replaced by its value from ``env_file`` or the environment."""
    def value(match: re.Match[str]) -> str:
        found = setting(match.group(1), env_file)
        if not found:
            raise ConfigError(f"{match.group(1)} is not set, and {text} needs it")
        return found

    return re.sub(r"\$\{([A-Z0-9_]+)\}", value, text)


def key(config: ChooserConfig, env_file: Path) -> str | None:
    """The key named by ``api_key_env``, from ``env_file`` or the environment."""
    if config.api_key_env is None:
        return None
    value = setting(config.api_key_env, env_file)
    if not value:
        raise ConfigError(f"chooser {config.name}: {config.api_key_env} is not set")
    return value


def factory(config: ChooserConfig, env_file: Path
            ) -> Callable[[Problem, Spend, Draws], Chooser]:
    """A function from (problem, spend, order) to a chooser for ``config``."""
    if config.protocol == "jev":
        from .jev import JevClient, jev_chooser

        client = JevClient(api_key=key(config, env_file), model=config.model,
                           api_base=expand(config.api_base, env_file), endpoint=config.endpoint)
        return lambda problem, spend, order: jev_chooser(
            client, objective=problem.objective, context=problem.context,
            render=problem.render, spend=spend, order=order, replace=config.replace)
    if config.protocol == "openai":
        from .decisions import DecisionsClient, decisions_chooser

        decisions = DecisionsClient(api_key=key(config, env_file), model=config.model,
                                    api_base=config.api_base)
        return lambda problem, spend, order: decisions_chooser(
            decisions, objective=problem.objective, context=problem.context,
            render=problem.render, spend=spend, order=order)
    import anthropic

    from .llm import llm_chooser

    client = anthropic.Anthropic(api_key=key(config, env_file), base_url=config.api_base)
    return lambda problem, spend, order: llm_chooser(
        client, model=config.model, effort=config.effort, objective=problem.objective,
        context=problem.context, render=problem.render, spend=spend, order=order)
