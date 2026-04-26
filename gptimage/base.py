
import discord
from typing import List, Optional, Dict, Union
from datetime import datetime
from collections import defaultdict
from openai import AsyncOpenAI
from redbot.core import commands, Config
from redbot.core.bot import Red


class GptImageBase(commands.Cog):
    def __init__(self, bot: Red):
        super().__init__()
        self.bot = bot
        self.client: Optional[AsyncOpenAI] = None
        self.generating: Dict[int, bool] = {}
        self.gen_count: dict[int, int] = defaultdict(int)
        self.last_quota = datetime.min
        self.loading_emoji = ""
        self.config = Config.get_conf(self, identifier=64616665)
        defaults_global = {
            "vip": [],
            "quota": 5,
            "cooldown": 0,
            "model": "gpt-image-2",
            "quality": "low",
            "loading_emoji": "⏳",
        }
        defaults_guild = {
            "enabled": False,
            "vip_role": -1,
        }
        self.config.register_global(**defaults_global)
        self.config.register_guild(**defaults_guild)

    async def imagine(self,
                      ctx: Union[discord.Interaction, commands.Context],
                      resolution: str,
                      prompt: str,
                      images: List[bytes]):
        raise NotImplementedError
