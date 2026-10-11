from beelinebench.domains import tiles, wikispeedia


def test_tiles():
    assert tiles.manhattan(tiles.SOLVED) == 0
    assert len(list(tiles.slide(tiles.SOLVED))) == 2
    assert tiles.line(tiles.SOLVED) == "1 2 3 | 4 5 6 | 7 8 ·"
    assert tiles.problem(3, heuristic="manhattan", scramble=12).start == tiles.problem(3, heuristic="manhattan", scramble=12).start
    assert tiles.problem(3, heuristic="manhattan", scramble=12).start != tiles.problem(4, heuristic="manhattan", scramble=12).start


def test_category_distance_on_a_small_graph():
    graph = wikispeedia.Graph(
        links={"A": ("B", "C"), "B": ("D",), "C": ()},
        categories={"A": (("subject", "Science"),),
                    "B": (("subject", "Science", "Biology"),),
                    "D": (("subject", "Science", "Biology", "Birds"),)},
        games=(("A", "D"),))
    assert wikispeedia.category_distance(graph, "D", "B") == (1, -1)
    assert wikispeedia.category_distance(graph, "D", "C")[0] == wikispeedia.NO_CATEGORY
    assert wikispeedia.fewest_clicks(graph, "A", "D") == 2


def test_blocksworld():
    from beelinebench.domains import blocksworld

    problem = blocksworld.problem(1, heuristic="h_ff", blocks=7)
    assert problem.heuristic(problem.start) > 0
    assert all("(handempty)" not in s for s in problem.moves(problem.start))
    goal = frozenset({"(on b1 b2)"})
    state = frozenset({"(ontable b1)", "(ontable b2)", "(clear b1)", "(clear b2)",
                       "(handempty)"})
    assert blocksworld.h_ff(2, goal, state) == 2.0


def test_countdown():
    from beelinebench.domains import countdown

    assert set(countdown.moves((2, 3))) == {(5,), (6,), (1,)}
    problem = countdown.problem(1, heuristic="nearest_number", numbers=4, largest_number=25,
                                smallest_target=10, largest_target=100)
    assert len(problem.start) == 4 and not problem.solved(problem.start)


def test_word_ladder(tmp_path):
    from beelinebench.domains import word_ladder

    path = tmp_path / "words.txt"
    path.write_text("cold\ncord\ncard\nward\nwarm\nworm\n")
    ladder = word_ladder.load(path)
    assert ladder["cold"] == ("cord",)
    assert word_ladder.steps_from(ladder, "cold")["warm"] == 4
    assert word_ladder.letters_different("warm", "cold") == 4


def test_keys_doors():
    from beelinebench.domains import keys_doors as kd

    # start holds the red key and the red door; the exit is behind the blue door,
    # in the red room, and the blue key is behind the red door.
    layout = kd.Layout(doors=("red", "blue"), parent={"red": kd.START, "blue": "red"},
                       key_room={"red": kd.START, "blue": "red"}, exit="blue")
    start = (kd.START, frozenset({kd.START}))
    assert list(kd.moves(layout, start)) == [("red", frozenset({kd.START, "red"}))]
    assert kd.locked_doors(layout, start) == 3  # two closed doors, the blue key missing
    assert kd.describe(layout, start) == "in the starting room · keys: red · open doors: none"
    problem = kd.problem(1, heuristic="locked_doors", doors=10, min_moves=12)
    assert not problem.solved(problem.start) and problem.heuristic(problem.start) > 0
    assert "The exit is behind the" in problem.context
