
import re
from enum import Enum, IntEnum, auto

POKER_MAX_PLAYERS = 8
POKER_MINIMUM_BET = 10
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
    AllIn = auto()


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


POKER_RULES = """\
* Each player gets 2 cards only they can see.
* The table puts down 3 cards, then 1 card, then 1 card, each being a betting round. At the end, the players compare hands.
* The players automatically make the best poker hand available between their 2 cards and the table's 5 cards (poker hands rankings are shown in the image).
* You win by either having the best poker hand or convincing others to fold.
* Each betting round everyone either has to match the highest bet or fold. The bets go toward a common Pot.
* On your turn you can either Fold (quit, but your bet stays in the pot), Check (pass your turn, if you already matched the highest bet), Call (to match the highest bet), or Raise (to increase the bet).
* If someone doesn't have enough money to Call, they can go All In, but if they win they can only earn a part of the pot.
"""
