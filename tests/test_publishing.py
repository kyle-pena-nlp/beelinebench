from pathlib import Path

from beelinebench import benchmark, publishing

PROJECT = Path(__file__).parent.parent
OFFICIALS = benchmark.load(PROJECT / "benchmarks.toml")


def test_every_official_benchmark_has_a_page_and_a_link():
    assert publishing.problems(OFFICIALS, PROJECT / "docs" / "benchmarks") == []


def test_a_missing_page_or_link_is_found(tmp_path):
    (tmp_path / "README.md").write_text("# The benchmarks\n")
    assert publishing.problems(OFFICIALS, tmp_path) == [
        f"{tmp_path / '1.0.0.md'} does not exist",
        f"{tmp_path / 'README.md'} has no link to 1.0.0.md"]


def test_publish_writes_both_once(tmp_path):
    official = OFFICIALS["1.0.0"]
    assert len(publishing.publish(official, tmp_path)) == 2
    assert publishing.problems(OFFICIALS, tmp_path) == []
    (tmp_path / "1.0.0.md").write_text("edited")
    assert publishing.publish(official, tmp_path) == []
    assert (tmp_path / "1.0.0.md").read_text() == "edited"
