import draughts
import discord
from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Tuple, Union
from datetime import datetime
from redbot.core import commands, Config
from redbot.core.bot import Red


class BaseCheckersCog(commands.Cog):
    def __init__(self, bot: Red):
        self.bot = bot
        self.games: Dict[int, BaseCheckersGame] = {}
        self.config = Config.get_conf(self, identifier=766969962065)
        self.config.register_channel(game=None, message=0, variant="english", players=[])

    @abstractmethod
    async def checkers_new(self, ctx: Union[commands.Context, discord.Interaction], opponent: Optional[discord.Member]):
        pass


class BaseCheckersGame(ABC):
    def __init__(self, cog: BaseCheckersCog, players: List[discord.Member], channel: discord.TextChannel, variant: str, initial_state: str = None):
        self.cog = cog
        self.players = players
        self.channel = channel
        self.last_interacted: datetime = datetime.now()
        self.message: Optional[discord.Message] = None
        self.view: Optional[discord.ui.View] = None
        self.board = draughts.Board(variant, initial_state or "startpos")

    def member(self, color: int):
        return self.players[0] if color == draughts.BLACK else self.players[1]

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
