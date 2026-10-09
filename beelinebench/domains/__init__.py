"""The five domains. Each module has a ``problem`` function that makes trial ``n`` from a seed."""

#: The name of each domain, for a reader.
TITLES = {
    "tiles": "8-puzzle",
    "blocksworld": "Blocksworld",
    "countdown": "Countdown",
    "word_ladder": "Word ladder",
    "wikispeedia": "Wikispeedia",
}

#: The name of each heuristic, for a reader.
HEURISTIC_TITLES = {
    "manhattan": "Manhattan distance",
    "h_ff": "FF relaxed plan",
    "nearest_number": "nearest number",
    "letters_different": "letters different",
    "category_distance": "category distance",
}
