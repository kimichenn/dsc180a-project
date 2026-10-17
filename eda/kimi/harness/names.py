"""Made-up project codenames: two or three consonant-vowel syllables plus an optional coda (Kavel, Drumo)."""

from __future__ import annotations

import random

_ONSETS = ("b", "d", "f", "g", "k", "l", "m", "n", "p", "r", "s", "t", "v", "z", "br", "dr", "kr", "tr", "st", "th")
_VOWELS = ("a", "e", "i", "o", "u")
_CODAS = ("", "", "", "n", "r", "l", "s", "x")


def codenames(rng: random.Random, count: int, taken: set[str]) -> list[str]:
    """`count` new names of at most 8 letters, none already in `taken` (lowercase); adds them to it."""
    names = []
    while len(names) < count:
        syllables = "".join(rng.choice(_ONSETS) + rng.choice(_VOWELS) for _ in range(rng.choice((2, 2, 3))))
        name = (syllables + rng.choice(_CODAS)).capitalize()
        if len(name) <= 8 and name.lower() not in taken:
            taken.add(name.lower())
            names.append(name)
    return names
