from datetime import datetime
import discord
from abc import ABC, abstractmethod
from typing import Any, List, Optional, Union
from redbot.core import Config, commands
from redbot.core.bot import Red

from casino.card import Card
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
        self.deck: List[Card] = []
        self.table: List[Card] = []
        self.state: PokerState = PokerState.WaitingForPlayers
        self.minimum_bet = minimum_bet
        self.current_bet = minimum_bet
        self.pot = 0
        self.turn: Optional[int] = None  # index of current turn
        self.winners: List[int] = []  # indices of winners
        self.all_hands_finished: bool = False
        self.last_played: Optional[float] = None
        self.message: Optional[discord.Message] = None

    # -----------------------
    # Abstract methods (must be implemented)
    # -----------------------
    @abstractmethod
    def is_finished(self) -> bool:
        """Return True if the entire poker session (all hands) is finished."""
        raise NotImplementedError

    @abstractmethod
    def is_cancelled(self) -> bool:
        """Return True if the game was cancelled (surrendered/aborted)."""
        raise NotImplementedError

    @abstractmethod
    async def cancel(self, member: Optional[discord.Member]) -> None:
        """
        Cancel the game, optionally recording which member caused the cancellation.
        Should mark the game finished and persist state.
        """
        raise NotImplementedError

    @abstractmethod
    async def input(
        self,
        ctx_or_interaction: Any,
        input_str: str,
        user_id: int,
        /,
    ) -> bool:
        """
        Handle an input from a player (button/select/command).
        Return True if the input caused a state change that should be considered a 'handled action'
        (e.g. start, fold, call, raise...). Return False if the input was ignored/invalid.
        `ctx_or_interaction` is provided to allow access to ephemeral replies or interaction data.
        """
        raise NotImplementedError

    @abstractmethod
    async def start_hand(self) -> None:
        """
        Begin dealing/starting the current hand (transition from WaitingForPlayers to PreFlop).
        Should perform initial bets (blinds) and persist state.
        """
        raise NotImplementedError

    @abstractmethod
    async def end_hand(self, *winners_indices: int) -> None:
        """
        End the current hand and process winners (indices relative to self.players).
        Should handle distribution of pot (or delegate to economy/transaction service),
        set hand results, persist state, and prepare for possible reset or finish.
        """
        raise NotImplementedError

    @abstractmethod
    async def reset_hand(self) -> None:
        """
        Reset internal hand-related state to prepare for a new hand while keeping
        the same player order (e.g. rotate dealer).
        """
        raise NotImplementedError

    @abstractmethod
    async def save_state(self) -> None:
        """
        Persist any state necessary to restore this game later.
        For a Red cog, use self.cog.config.channel(self.channel).set(...).
        Must also remove the game from the cog's in-memory store when finished.
        """
        raise NotImplementedError