import discord
from abc import ABC, abstractmethod
from typing import List, Optional, Type, Union
from datetime import datetime
from redbot.core import commands
from redbot.core.bot import Red


class BaseChessCog(commands.Cog):
    def __init__(self, bot: Red):
        self.bot = bot

    @abstractmethod
    async def chess_new(self, ctx: Union[commands.Context, discord.Interaction], opponent: Optional[discord.Member]):
        pass

class BaseChessGame(ABC):
    def __init__(self, cog: BaseChessCog, players: List[discord.Member], channel: discord.TextChannel):
        self.cog = cog
        self.players = players
        self.channel = channel
        self.message: Optional[discord.Message] = None
        self.last_interacted: datetime = datetime.now()

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
    def cancel(self):
        pass

    @abstractmethod
    async def update_message(self):
        pass
