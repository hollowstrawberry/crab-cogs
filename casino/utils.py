
import re
from enum import Enum, IntEnum, auto

MAX_PLAYERS = 8
DISCORD_RED = 0XDD2E44
EMPTY_ELEMENT = "\u200b"


def humanize_camel_case(s: str):
    return re.sub(r'([a-z])([A-Z])', r'\1 \2', s).lower().capitalize()


class InsufficientFundsError(Exception):
    pass


class PlayerState(Enum):
    Pending = auto()
    Folded = auto()
    Betted = auto()
    Checked = auto()


class PlayerType(Enum):
    Dealer = 0
    SmallBlind = 1
    BigBlind = 2
    Normal = 3


class HandType(IntEnum):
    NotCalculated = 0
    HighCard = 1
    Pair = 2
    DoublePair = 3
    Triple = 4
    Straight = 5
    Flush = 6
    FullHouse = 7
    Quadruple = 8
    StraightFlush = 9
    RoyalFlush = 10


class PokerState(IntEnum):
    WaitingForPlayers = 0
    PreFlop = 1
    Flop = 2
    Turn = 3
    River = 4
    Showdown = 5
