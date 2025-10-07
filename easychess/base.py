import chess
import chess.engine
import discord
from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Tuple, Union
from datetime import datetime
from redbot.core import commands, Config
from redbot.core.bot import Red


class BaseChessCog(commands.Cog):
    def __init__(self, bot: Red):
        self.bot = bot
        self.games: Dict[int, BaseChessGame] = {}
        self.engine: Optional[chess.engine.UciProtocol] = None
        self.config = Config.get_conf(self, identifier=766969962064)
        self.config.register_channel(game=None, players=[])

    @abstractmethod
    async def chess_new(self, ctx: Union[commands.Context, discord.Interaction], opponent: Optional[discord.Member]):
        pass


class BaseChessGame(ABC):
    def __init__(self, cog: BaseChessCog, players: List[discord.Member], channel: discord.TextChannel, initial_state: str = None):
        self.cog = cog
        self.players = players
        self.channel = channel
        self.message: Optional[discord.Message] = None
        self.last_interacted: datetime = datetime.now()
        self.board = chess.Board(initial_state or chess.STARTING_FEN)

    def member(self, color: chess.Color):
        return self.players[1] if color == chess.BLACK else self.players[0]

    @abstractmethod
    def is_finished(self):
        pass

    @abstractmethod
    def is_cancelled(self):
        pass

    @abstractmethod
    def accept(self):
        pass

    @abstractmethod
    async def cancel(self, member: Optional[discord.Member]):
        pass

    @abstractmethod
    async def move_user(self, move: str) -> Tuple[bool, str]:
        pass

    @abstractmethod
    async def move_engine(self):
        pass

    @abstractmethod
    async def update_message(self, interaction: Optional[discord.Interaction] = None):
        pass
