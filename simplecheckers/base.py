import draughts
import discord
from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Tuple, Union
from datetime import datetime
from redbot.core import commands, Config, bank
from redbot.core.bot import Red


class BaseCheckersCog(commands.Cog):
    def __init__(self, bot: Red):
        self.bot = bot
        self.games: Dict[int, BaseCheckersGame] = {}
        self.config = Config.get_conf(self, identifier=766969962065)
        default_game = {
            "game": None,
            "message": 0,
            "variant": "english",
            "players": [],
            "time": 0,
            "bet": 0,
        }
        default_currency = {
            "payout": 200,
        }
        self.config.register_channel(**default_game)
        self.config.register_guild(**default_currency)
        self.config.register_global(**default_currency)

    @abstractmethod
    async def is_economy_enabled(self, guild: discord.Guild) -> bool:
        pass

    @abstractmethod
    async def checkers_new(self, ctx: Union[commands.Context, discord.Interaction], opponent: Optional[discord.Member], bet: Optional[int] = 0) -> None:
        pass


class BaseCheckersGame(ABC):
    def __init__(self, cog: BaseCheckersCog, players: List[discord.Member], channel: discord.TextChannel, variant: str, initial_state: str = None, bet: int = 0):
        self.cog = cog
        self.players = players
        self.channel = channel
        self.last_interacted: datetime = datetime.now()
        self.message: Optional[discord.Message] = None
        self.view: Optional[discord.ui.View] = None
        self.board = draughts.Board(variant, initial_state or "startpos")
        self.bet = bet
        self.accepted = initial_state is not None
        self.init_done = initial_state is not None
        self.payout_done = False

    @abstractmethod
    def is_finished(self) -> bool:
        pass

    @abstractmethod
    def is_cancelled(self) -> bool:
        pass

    @abstractmethod
    async def cancel(self, member: Optional[discord.Member]) -> None:
        pass

    @abstractmethod
    async def move_user(self, move: str) -> Tuple[bool, str]:
        pass

    @abstractmethod
    async def move_engine(self) -> None:
        pass

    @abstractmethod
    async def update_message(self, interaction: Optional[discord.Interaction] = None) -> None:
        pass

    @abstractmethod
    async def save_state(self) -> None:
        pass

    def member(self, color: int):
        return self.players[0] if color == draughts.BLACK else self.players[1]
    
    async def start(self) -> None:
        self.accepted = True
        await self._init()
    
    async def _init(self) -> None:
        if self.init_done:
            return
        self.init_done = True
        if not await self.cog.is_economy_enabled(self.channel.guild):
            return
        if all(not player.bot for player in self.players):  # pvp
            for player in self.players:
                await bank.withdraw_credits(player, self.bet)
        await self.save_state()

    async def _on_win(self, winner: Optional[discord.Member]) -> None:
        if self.payout_done:
            return
        self.payout_done = True
        if not await self.cog.is_economy_enabled(self.channel.guild):
            return
        against_bot = any(player.bot for player in self.players)
        if winner is None and against_bot:
            return
        await self._init() # failsafe
        if winner is None:
            for player in self.players:
                await bank.deposit_credits(player, self.bet)
        else:
            if not winner.bot:
                prize = self.bet if against_bot else self.bet * 2
                await bank.deposit_credits(winner, prize)
