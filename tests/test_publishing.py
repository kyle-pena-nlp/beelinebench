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
    assert len(publishing.publish(official, tmp_path, OFFICIALS)) == 2
    assert publishing.problems(OFFICIALS, tmp_path) == []
    (tmp_path / "1.0.0.md").write_text("edited")
    assert publishing.publish(official, tmp_path, OFFICIALS) == []
    assert (tmp_path / "1.0.0.md").read_text() == "edited"


def test_the_index_links_each_page_and_both_figures():
    text = publishing.index(OFFICIALS)
    assert "| [1.0.0](1.0.0.md) |" in text
    assert "(1.0.0.png)" in text and "(1.0.0-frontier.png)" in text


def test_the_committed_index_is_up_to_date():
    index = PROJECT / "docs" / "benchmarks" / publishing.INDEX
    assert index.read_text() == publishing.index(OFFICIALS)


def test_the_results_part_of_a_page_is_replaced():
    page = publishing.page(OFFICIALS["1.0.0"])
    assert publishing.RESULTS_START in page
    once = publishing.with_results(page, "## Results\n\nnew")
    assert "new" in once and "No results yet" not in once
    assert publishing.with_results(once, "## Results\n\nnewer").count("## Results") == 1
    assert "# Benchmark 1.0.0" in once
