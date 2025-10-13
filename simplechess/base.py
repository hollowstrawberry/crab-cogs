import chess
import chess.engine
import discord
from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Tuple, Union
from datetime import datetime
from redbot.core import commands, Config, bank
from redbot.core.bot import Red


class BaseChessCog(commands.Cog):
    def __init__(self, bot: Red):
        self.bot = bot
        self.games: Dict[int, BaseChessGame] = {}
        self.engine: Optional[chess.engine.UciProtocol] = None
        self.config = Config.get_conf(self, identifier=766969962064)
        default_game = {
            "game": None,
            "message": 0,
            "players": [],
            "depth": None,
            "bet": 0,
        }
        default_guild = {
            "payout": 500,
        }
        self.config.register_channel(**default_game)
        self.config.register_guild(**default_guild)
        
    @abstractmethod
    async def is_economy_enabled(self, guild: discord.Guild) -> bool:
        pass

    @abstractmethod
    async def chess_new(self,
                        ctx: Union[commands.Context, discord.Interaction],
                        opponent: Optional[discord.Member],
                        depth: Optional[int] = None,
                        bet: Optional[int] = 0
                        ) -> None:
        pass


class BaseChessGame(ABC):
    def __init__(self,
                 cog: BaseChessCog,
                 players: List[discord.Member],
                 channel: discord.TextChannel,
                 initial_state: str = None,
                 depth: Optional[int] = None,
                 bet: int = 0
                 ):
        self.cog = cog
        self.players = players
        self.channel = channel
        self.last_interacted: datetime = datetime.now()
        self.message: Optional[discord.Message] = None
        self.view: Optional[discord.ui.View] = None
        self.board = chess.Board(initial_state or chess.STARTING_FEN)
        self.limit = chess.engine.Limit(time=1.0, depth=depth)
        self.bet = bet
        self.init_done = False
        self.payout_done = False

    @abstractmethod
    def is_finished(self) -> bool:
        pass

    @abstractmethod
    def is_cancelled(self) -> bool:
        pass

    @abstractmethod
    def accept(self) -> None:
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

    def member(self, color: chess.Color) -> discord.Member:
        return self.players[1] if color == chess.BLACK else self.players[0]
    
    async def init(self) -> None:
        if self.init_done:
            return
        self.init_done = True
        if not await self.cog.is_economy_enabled(self.channel.guild):
            return
        if all(not player.bot for player in self.players):  # pvp
            for player in self.players:
                await bank.withdraw_credits(player, self.bet)
        await self.save_state()

    async def on_win(self, winner: Optional[discord.Member]) -> None:
        if self.payout_done:
            return
        self.payout_done = True
        if not await self.cog.is_economy_enabled(self.channel.guild):
            return
        against_bot = any(player.bot for player in self.players)
        if winner is None and against_bot:
            return
        await self.init() # failsafe
        if winner is None:
            for player in self.players:
                await bank.deposit_credits(player, self.bet)
        else:
            if not winner.bot:
                prize = self.bet if against_bot else self.bet * 2
                await bank.deposit_credits(winner, prize)
