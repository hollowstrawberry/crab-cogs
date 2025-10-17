import discord
from abc import abstractmethod
from typing import Union
from redbot.core import Config, commands
from redbot.core.bot import Red


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