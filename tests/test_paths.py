"""The working folder: a clone works as before, and an installed package uses another folder."""

from pathlib import Path

from beelinebench import paths


def test_a_clone_is_its_own_working_folder(monkeypatch):
    monkeypatch.delenv("BEELINEBENCH_HOME", raising=False)
    root = Path(__file__).resolve().parent.parent
    assert paths.checkout() == root
    assert paths.home() == root
    assert paths.official(root) == root / "benchmarks.toml"


def test_beelinebench_home_selects_the_working_folder(monkeypatch, tmp_path):
    monkeypatch.setenv("BEELINEBENCH_HOME", str(tmp_path))
    assert paths.home() == tmp_path.resolve()
    # A folder without benchmarks.toml takes the copy in the package.
    assert paths.official(tmp_path) == paths.PACKAGE / "benchmarks.toml"
