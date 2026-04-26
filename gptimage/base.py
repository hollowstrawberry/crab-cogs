import discord
from typing import List, Optional, Dict, Union
from datetime import datetime
from redbot.core import commands, Config
from redbot.core.bot import Red
from openai import AsyncOpenAI


class GptImageBase(commands.Cog):
    """Generate images with OpenAI"""

    def __init__(self, bot: Red):
        super().__init__()
        self.bot = bot
        self.client: Optional[AsyncOpenAI] = None
        self.generating: Dict[int, bool] = {}
        self.user_last_img: Dict[int, datetime] = {}
        self.loading_emoji = ""
        self.config = Config.get_conf(self, identifier=64616665)
        defaults_global = {
            "vip": [],
            "cooldown": 0,
            "model": "gpt-image-2",
            "quality": "low",
        }
        self.config.register_global(**defaults_global)

    async def imagine(self,
                      ctx: Union[discord.Interaction, commands.Context],
                      prompt: str,
                      resolution: str,
                      images: List[bytes]):
        raise NotImplementedError
