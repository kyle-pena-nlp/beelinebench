from beelinebench.rng import Draws


def test_the_draws_are_the_same_on_every_machine():
    # Recorded on 2026-10-03, Python 3.14, macOS. A change here changes every trial.
    draws = Draws("tiles", 1)
    assert [draws.below(1000) for _ in range(5)] == [563, 218, 627, 973, 891]


def test_each_path_has_its_own_draws():
    assert Draws("tiles", 1).random() != Draws("tiles", 2).random()
    assert Draws("tiles", 1).random() != Draws("tiles", "1").random()


def test_shuffle_and_sample_keep_the_items():
    items = list(range(20))
    Draws("x").shuffle(items)
    assert sorted(items) == list(range(20))
    sample = Draws("x").sample(range(20), 5)
    assert len(set(sample)) == 5


def test_a_master_seed_goes_first_in_the_path():
    assert Draws("tiles", 1, seed=None).random() == Draws("tiles", 1).random()
    assert Draws("tiles", 1, seed=7).random() == Draws(7, "tiles", 1).random()
    assert Draws("tiles", 1, seed=7).random() != Draws("tiles", 1).random()
