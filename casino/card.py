from enum import Enum
from typing import NamedTuple
from itertools import product


class CardValue(Enum):
    ACE = 1
    TWO = 2
    THREE = 3
    FOUR = 4
    FIVE = 5
    SIX = 6
    SEVEN = 7
    EIGHT = 8
    NINE = 9
    TEN = 10
    JACK = 11
    QUEEN = 12
    KING = 13


class CardColor(Enum):
    SPADES = 0
    HEARTS = 1
    CLUBS = 2
    DIAMONDS = 3


class Card(NamedTuple):
    value: CardValue
    color: CardColor


def make_deck():
    return [Card(value, color) for value, color in product(CardValue, CardColor)]

