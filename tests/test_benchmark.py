from dataclasses import replace
from pathlib import Path

from beelinebench import benchmark

PROJECT = Path(__file__).parent.parent
OFFICIALS = benchmark.load(PROJECT / "benchmarks.toml")


def test_an_official_benchmark_matches_itself():
    official = OFFICIALS["1.0.0"]
    assert benchmark.matching(official, list(official.domains), OFFICIALS) == "1.0.0"


def test_fewer_trials_or_domains_is_part_of_the_official_run():
    official = OFFICIALS["1.0.0"]
    assert benchmark.matching(replace(official, name="x", trials=5), ["tiles"],
                              OFFICIALS) == "1.0.0"


def test_a_different_setting_is_named():
    official = OFFICIALS["1.0.0"]
    domains = {**official.domains, "tiles": {"heuristic": "manhattan", "scramble": 16}}
    experiment = replace(official, name="x", domains=domains)
    assert benchmark.matching(experiment, ["tiles"], OFFICIALS) is None
    assert benchmark.differences(experiment, ["tiles"], official) == [
        "tiles.scramble is 16, and 12 in 1.0.0"]
    assert benchmark.matching(experiment, ["countdown"], OFFICIALS) == "1.0.0"


def test_every_official_benchmark_still_makes_its_trials():
    """The code keeps every parameter that an official benchmark uses."""
    from beelinebench.__main__ import maker

    for official in OFFICIALS.values():
        for domain, settings in official.domains.items():
            try:
                make = maker(domain, settings)
            except FileNotFoundError:
                continue  # the data of this domain is not downloaded
            problem = make(1)
            assert problem.domain == domain
            assert problem.heuristic_name == settings["heuristic"]


def test_a_master_seed_makes_a_custom_benchmark_with_other_trials():
    import pytest

    from beelinebench.domains import tiles

    official = OFFICIALS["1.0.0"]
    assert official.seed is None and benchmark.seeded(official, None) is official
    seeded = benchmark.seeded(official, 7)
    assert seeded.name == "1.0.0.seed-7" and seeded.seed == 7
    assert benchmark.matching(seeded, list(seeded.domains), OFFICIALS) is None
    settings = official.domains["tiles"]
    plain, other = tiles.problem(1, **settings), tiles.problem(1, **settings, seed=7)
    assert plain.start == tiles.problem(1, **settings, seed=None).start
    assert plain.start != other.start and other.seed == 7
    assert other.draws("evict").random() != plain.draws("evict").random()
    with pytest.raises(ValueError):
        benchmark.parse({"x": {"trials": 1, "max_expansions": 1, "max_frontier": 1,
                               "domains": {}, "seed": "7"}})
