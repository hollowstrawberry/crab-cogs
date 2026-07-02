import pickle
import logging
import asyncio
import discord
import lavalink
from base64 import b64encode, b64decode
from typing import Optional, Any
from redbot.core import commands
from redbot.core.bot import Red, Config
from redbot.core.commands import Cog
from redbot.cogs.audio.core import Audio

log = logging.getLogger("red.crab-cogs.audioreconnect")


class AudioReconnect(Cog):
    """Reconnects to voice channels after restarting the bot."""

    def __init__(self, bot: Red, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.bot = bot
        self.config = Config.get_conf(self, identifier=792413491)
        self.config.register_guild(**{
            "channel": 0,
            "queue": "",
        })

    async def cog_load(self):
        asyncio.create_task(self.load())

    async def cog_unload(self):
        lavalink.unregister_event_listener(self.on_lavalink_event)

    async def reconnect(self, channel: discord.channel.VocalGuildChannel, pickled_queue: Optional[str], self_deaf: bool):
        player = await channel.connect(cls=lavalink.Player, self_deaf=self_deaf)  # type: ignore
        if pickled_queue and (queue := pickle.loads(b64decode(pickled_queue))):
            player.queue = queue
            if player.queue[0] is None:
                player.queue.pop(0)
            else:
                await player.play()

    async def load(self):
        lavalink.register_event_listener(self.on_lavalink_event)
        await self.bot.wait_until_red_ready()
        audio: Optional[Audio] = self.bot.get_cog("Audio")  # type: ignore
        if not audio:
            log.error("Audio cog not loaded")
            return
        reconnect_config = await self.config.all_guilds()
        audio_config = await audio.config.all_guilds()
        tasks = [self.reconnect(channel, config.get("queue"), audio_config.get(guild_id, {}).get("auto_deafen", True))
                 for guild_id, config in reconnect_config.items()
                 if (guild := self.bot.get_guild(guild_id))
                 and (channel := guild.get_channel(config.get("channel", 0)))
                 and isinstance(channel, discord.channel.VocalGuildChannel)
                 and audio_config.get(guild_id, {}).get("persist_queue", True)
                 and (not guild.voice_client or not guild.voice_client.channel)]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        successes = len([res for res in results if not isinstance(res, BaseException)])
        errors = len([res for res in results if isinstance(res, BaseException)])
        if successes:
            log.warning(f"Reconnected to {successes} guilds")
        if errors:
            log.warning(f"Failed to reconnect to {errors} guilds")

    async def on_lavalink_event(self, player: lavalink.Player, event_type: lavalink.LavalinkEvents, arg: Any):
        if "Track" not in event_type.value and "Queue" not in event_type.value:
            return
        if event_type == lavalink.LavalinkEvents.QUEUE_END:
            pickled_queue = ""
        else:
            pickled_queue = b64encode(pickle.dumps([player.current] + player.queue)).decode()
        await self.config.guild(player.guild).channel.set(player.channel.id)
        await self.config.guild(player.guild).queue.set(pickled_queue)

    @commands.Cog.listener()
    async def on_red_audio_audio_disconnect(self, guild: discord.Guild):
        await self.config.guild(guild).channel.set(0)
