import random
import discord
from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Tuple, Union
from datetime import datetime
from redbot.core import Config, commands
from redbot.core.bot import Red

from simplecasino.card import Card, make_deck
from simplecasino.utils import POKER_MAX_PLAYERS, POKER_MINIMUM_BET, PokerState


class BaseCasinoCog(commands.Cog):
    def __init__(self, bot: Red):
        self.bot = bot
        self.poker_games: Dict[int, BasePokerGame] = {}
        self.config = Config.get_conf(self, identifier=766962065)
        default_config = {
            "bjmin": 10,
            "bjmax": 1000,
            "bjtime": 5,
            "pokermin": POKER_MINIMUM_BET,
            "pokermax": 1000,
            "coinfreespin": True,
            "sloteasy": False,
        }
        emojis_config = {
            "emoji_dealer": "(D)",
            "emoji_smallblind": "(SB)",
            "emoji_bigblind": "(BB)",
            "emoji_spades": "♠️",
            "emoji_clubs": "♣️",
        }
        channel_config = {
            "game": {},  # poker
        }
        user_stats = {
            "slotcount": 0,
            "slot2symbolcount": 0,
            "slot3symbolcount": 0,
            "slotfreespincount": 0,
            "slotjackpotcount": 0,
            "slotjackpotwhiffcount": 0,
            "slotprofit": 0,
            "slotbetted": 0,
            "bjcount": 0,
            "bjwincount": 0,
            "bjlosscount": 0,
            "bjtiecount": 0,
            "bj21count": 0,
            "bjnatural21count": 0,
            "bjprofit": 0,
            "bjbetted": 0,
        }
        self.config.register_user(**user_stats)
        self.config.register_member(**user_stats)
        self.config.register_channel(**channel_config)
        self.config.register_guild(**default_config)
        self.config.register_global(**default_config, **emojis_config)

    @abstractmethod
    async def slot(self, ctx: Union[discord.Interaction, commands.Context], bet: int):
        pass

    @abstractmethod
    async def blackjack(self, ctx: Union[discord.Interaction, commands.Context], bet: int):
        pass

    @abstractmethod
    async def poker(self, ctx: Union[discord.Interaction, commands.Context], players: List[discord.Member], starting_bet: int) -> bool:
        pass


class BasePokerGame(ABC):
    def __init__(
        self,
        cog: BaseCasinoCog,
        players: List[discord.Member],
        channel: Union[discord.TextChannel, discord.Thread],
        minimum_bet: int = 0,
    ):
        self.cog = cog
        self.players_ids = [p.id for p in players][:POKER_MAX_PLAYERS]
        self.channel = channel
        self.deck: List[Card] = make_deck()
        random.shuffle(self.deck)
        self.table: List[Card] = []
        self.state: PokerState = PokerState.WaitingForPlayers
        self.minimum_bet = minimum_bet
        self.current_bet = minimum_bet
        self.pot = 0
        self.turn: Optional[int] = None  # index of current player
        self.all_hands_finished: bool = False
        self.last_interacted: datetime = datetime.now()
        self.message: Optional[discord.Message] = None
        self.view: Optional[discord.ui.View] = None
        self.is_cancelled = False

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

    @abstractmethod
    async def cancel(self) -> None:
        pass

    @property
    @abstractmethod
    def can_check(self) -> bool:
        pass

    @property
    @abstractmethod
    def is_finished(self) -> bool:
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
    async def bet(self, user_id: int, bet: int) -> None:
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
