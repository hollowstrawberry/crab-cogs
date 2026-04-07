import aiohttp
import discord
from typing import Dict, List, Any
from expiringdict import ExpiringDict, Union
from redbot.core import commands
from redbot.core.bot import Red, Config

from gelbooru.constants import HEADERS


class BooruBase(commands.Cog):
    def __init__(self, bot: Red):
        super().__init__()
        self.bot = bot
        self.session = aiohttp.ClientSession(headers=HEADERS)
        self.tag_cache: Dict[str, str] = {}
        self.image_cache: ExpiringDict[int, List[int]] = ExpiringDict(max_len=100, max_age_seconds=24*60*60)
        self.query_cache: ExpiringDict[str, List[Dict[str, Any]]] = ExpiringDict(max_len=100, max_age_seconds=24*60*60)
        self.config = Config.get_conf(self, identifier=62667275)
        self.config.register_global(tag_cache={})

    async def booru(self, ctx: Union[discord.Interaction, commands.Context], query: str):
        raise NotImplementedError()
