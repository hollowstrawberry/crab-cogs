import discord
from abc import ABC, abstractmethod
from typing import List, Optional, Type, Union
from datetime import datetime
from discord.ext import commands


class BaseMinigameCog(commands.Cog):
    @abstractmethod
    async def base_minigame_cmd(self,
                                game_cls: Type["Minigame"],
                                ctx: Union[commands.Context, discord.Interaction],
                                players: List[discord.Member],
                                against_bot: bool):
        pass
        

class Minigame(ABC):
    def __init__(self, cog: BaseMinigameCog, players: List[discord.Member], channel: discord.TextChannel):
        self.cog = cog
        self.players = players
        self.channel = channel
        self.message: Optional[discord.Message] = None
        self.last_interacted: datetime = datetime.now()

    @abstractmethod
    def is_finished(self) -> bool:
        pass

    @abstractmethod
    def is_cancelled(self) -> bool:
        pass

    @abstractmethod
    def end(self, player: discord.Member) -> None:
        pass

    @abstractmethod
    def accept(self, player: discord.Member) -> None:
        pass

    @abstractmethod
    def get_content(self) -> Optional[str]:
        pass

    @abstractmethod
    def get_embed(self) -> discord.Embed:
        pass

    @abstractmethod
    def get_view(self) -> discord.ui.View:
        pass