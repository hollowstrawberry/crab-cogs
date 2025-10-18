from enum import Enum
from itertools import product
from dataclasses import dataclass, field
from dataclasses_json import DataClassJsonMixin, config


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


class CardSuit(Enum):
    SPADES = "s"
    HEARTS = "h"
    CLUBS = "c"
    DIAMONDS = "d"


CARD_EMOJI = {
    CardValue.ACE: "🇦",
    CardValue.TWO: "2️⃣",
    CardValue.THREE: "3️⃣",
    CardValue.FOUR: "4️⃣",
    CardValue.FIVE: "5️⃣",
    CardValue.SIX: "6️⃣",
    CardValue.SEVEN: "7️⃣",
    CardValue.EIGHT: "8️⃣",
    CardValue.NINE: "9️⃣",
    CardValue.TEN: "🔟",
    CardValue.JACK: "🇯",
    CardValue.QUEEN: "🇶",
    CardValue.KING: "🇰",
}

CARD_VALUE_STR = {
    CardValue.ACE: "A",
    CardValue.TWO: "2",
    CardValue.THREE: "3",
    CardValue.FOUR: "4",
    CardValue.FIVE: "5",
    CardValue.SIX: "6",
    CardValue.SEVEN: "7",
    CardValue.EIGHT: "8",
    CardValue.NINE: "9",
    CardValue.TEN: "10",
    CardValue.JACK: "J",
    CardValue.QUEEN: "Q",
    CardValue.KING: "K",
}


@dataclass(frozen=True)
class Card(DataClassJsonMixin):
    value: CardValue = field(metadata=config(encoder=lambda x: x.value, decoder=CardValue))
    suit: CardSuit = field(metadata=config(encoder=lambda x: x.value, decoder=CardSuit))

    @property
    def poker_value(self):
        return 14 if self.value == CardValue.ACE else self.value.value

    def __str__(self):
        return f"{CARD_VALUE_STR[self.value]}{self.suit.value}"
    
    def __repr__(self):
        return self.__str__()


def make_deck():
    return [Card(value, color) for value, color in product(CardValue, CardSuit)]
