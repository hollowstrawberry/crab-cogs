import pickle
import copyreg
import logging
import asyncio
import discord
import lavalink
import itertools
from typing import Optional
from base64 import b64encode, b64decode
from discord.ext import tasks
from redbot.core import commands
from redbot.core.bot import Red, Config
from redbot.core.commands import Cog
from redbot.cogs.audio.core import Audio

log = logging.getLogger("red.crab-cogs.audioreconnect")


def pickle_track(track: lavalink.Track):
    state = track.__dict__.copy()
    if isinstance(state.get('requester'), (discord.Member, discord.User)):
        state['requester'] = state['requester'].id
    return (lavalink.Track.__new__, (lavalink.Track,), state)


class AudioReconnect(Cog):
    """Restores the current audio track progress when the bot restarts."""

    def __init__(self, bot: Red, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.bot = bot
        self.unloaded = False
        self.config = Config.get_conf(self, identifier=792413491)
        self.config.register_global(**{
            "current_tracks": {},
        })
        self.config.register_guild(**{
            "channel": 0,
        })

    async def cog_load(self):
        copyreg.pickle(lavalink.Track, pickle_track)
        asyncio.create_task(self.load())

    async def con_unload(self):
        self.unloaded = True
        self.save_current_tracks.stop()

    @tasks.loop(seconds=5)
    async def save_current_tracks(self):
        nodes = lavalink.get_all_nodes()
        players = list(itertools.chain(*[list(node.players) for node in nodes]))
        data = [(player.guild.id, player.current, player.position)
                for player in players
                if player.is_playing and player.current]
        current_tracks = {}
        for guild_id, current, position in data:
            current.start_timestamp = position
            current_tracks[guild_id] = b64encode(pickle.dumps(current)).decode()
        await self.config.current_tracks.set(current_tracks)

    async def wait_for_lavalink(self, audio: Audio):
        await audio.cog_ready_event.wait()
        if not audio.lavalink_connect_task:
            raise RuntimeError
        await audio.lavalink_connect_task
        if audio.lavalink_connection_aborted:
            raise RuntimeError

    async def load(self):
        await self.bot.wait_until_red_ready()
        audio: Optional[Audio] = self.bot.get_cog("Audio")  # type: ignore
        if not audio:
            log.error("Audio cog not loaded")
            return
        try:
            await self.wait_for_lavalink(audio)
        except Exception:
            log.error("Failed to establish lavalink connection")
            return

        reconnect_config = await self.config.all_guilds()
        audio_config = await audio.config.all_guilds()
        auto_deafen = {guild_id: config.get("auto_deafen", True) for guild_id, config in audio_config.items()}
        persist_queue = {guild_id: config.get("persist_queue", True) for guild_id, config in audio_config.items()}
        current_channels = {guild_id: config.get("channel", 0) for guild_id, config in reconnect_config.items()}
        current_tracks = await self.config.current_tracks()
        tasks = [self.reconnect(channel, current_tracks.get(guild_id), auto_deafen.get(guild_id, True))
                 for guild_id, channel_id in current_channels.items()
                 if (guild := self.bot.get_guild(guild_id))
                 and (channel := guild.get_channel(channel_id))
                 and isinstance(channel, discord.channel.VocalGuildChannel)
                 and persist_queue.get(guild_id, True)
                 and (not guild.voice_client or not guild.voice_client.channel)]
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        successes = [res for res in results if not isinstance(res, BaseException)]
        errors = [res for res in results if isinstance(res, BaseException)]
        log.info(f"Reconnected to {len(successes)} guilds")
        if errors:
            log.warning(f"Failed to reconnect to {len(errors)} guilds")
            for error in errors:
                log.warning(f"{error.__class__.__name__}: {error}")
        self.save_current_tracks.start()

    async def reconnect(self, channel: discord.channel.VocalGuildChannel, pickled_current: Optional[str], self_deaf: bool):
        if await self.bot.cog_disabled_in_guild(self, channel.guild):
            return
        player = await channel.connect(cls=lavalink.Player, self_deaf=self_deaf)  # type: ignore
        if not pickled_current:
            return
        current: lavalink.Track = pickle.loads(b64decode(pickled_current))
        if not current:
            return
        if isinstance(current.requester, int):
            current.requester = channel.guild.get_member(current.requester)  # type: ignore
        player.queue.insert(0, current)
        await player.play()
        # the rest of the queue gets populated by audio's persist_queue

    @commands.Cog.listener()
    async def on_voice_state_update(self, member: discord.Member, before: discord.VoiceState, after: discord.VoiceState):
        await asyncio.sleep(1) # the idea is to hopefully prevent manual bot restarts from un-setting the current channel
        if member is not member.guild.me or self.unloaded:
            return
        await self.config.guild(member.guild).channel.set(after.channel.id if after.channel else 0)
