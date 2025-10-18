import random
import discord
from abc import ABC, abstractmethod
from typing import List, Optional, Tuple, Union
from datetime import datetime
from redbot.core import Config, commands
from redbot.core.bot import Red

from casino.card import Card, make_deck
from casino.utils import MAX_PLAYERS, PokerState


class BaseCasinoCog(commands.Cog):
    def __init__(self, bot: Red):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=766962065)
        default_config = {
            "bjmin": 10,
            "bjmax": 1000,
            "bjtime": 5,
            "coinfreespin": True,
        }
        self.config.register_guild(**default_config)
        self.config.register_global(**default_config)

    @abstractmethod
    async def slot(self, ctx: Union[discord.Interaction, commands.Context], bid: int):
        pass

    @abstractmethod
    async def blackjack(self, ctx: Union[discord.Interaction, commands.Context], bid: int):
        pass


class BasePokerGame(ABC):
    def __init__(
        self,
        cog: BaseCasinoCog,
        players: List[discord.Member],
        channel: discord.TextChannel,
        minimum_bet: int = 0,
    ):
        self.cog = cog
        self.players_ids = [p.id for p in players][:MAX_PLAYERS]
        self.channel = channel
        self.deck: List[Card] = make_deck()
        random.shuffle(self.deck)
        self.table: List[Card] = []
        self.state: PokerState = PokerState.WaitingForPlayers
        self.minimum_bet = minimum_bet
        self.current_bet = minimum_bet
        self.pot = 0
        self.turn: Optional[int] = None  # index of current player
        self.winners: List[int] = []  # indices of winners
        self.all_hands_finished: bool = False
        self.last_interacted: Optional[datetime] = None
        self.message: Optional[discord.Message] = None

    @abstractmethod
    async def update_message(self, interaction: Optional[discord.Interaction] = None):
        pass

    @abstractmethod
    async def send_cards(self, interaction: discord.Interaction) -> None:
        pass

    @abstractmethod
    def try_add_player(self, user_id: int) -> Tuple[bool, str]:
        pass

    @abstractmethod
    def try_remove_player(self, user_id: int) -> Tuple[bool, str]:
        pass

    @property
    @abstractmethod
    def can_check(self) -> bool:
        pass

    @abstractmethod
    async def cancel(self, member: Optional[discord.Member]) -> None:
        pass

    @abstractmethod
    async def start_hand(self) -> None:
        pass

    @abstractmethod
    async def fold(self, user_id: int) -> None:
        pass

    @abstractmethod
    async def check(self, user_id: int) -> None:
        pass

    @abstractmethod
    async def call(self, user_id: int) -> None:
        pass

    @abstractmethod
    async def raise_to(self, user_id: int, bet: int) -> None:
        pass

    @abstractmethod
    async def end_hand(self, *winners_indices: int) -> None:
        pass

    @abstractmethod
    async def get_embed(self) -> discord.Embed:
        pass

    @abstractmethod
    async def save_state(self) -> None:
        pass
