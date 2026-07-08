import pickle
import copyreg
import asyncio
import discord
import lavalink
from typing import Optional
from base64 import b64encode, b64decode
from discord.ext import tasks
from redbot.core import commands
from redbot.core.bot import Red, Config
from redbot.core.commands import Cog
from redbot.cogs.audio.core import Audio

from audioreconnect import utils

log = utils.log


class AudioReconnect(Cog):
    """Restores the current audio track progress when the bot restarts."""

    def __init__(self, bot: Red, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.bot = bot
        self.queues: dict[int, utils.QueueState] = {}
        self.config = Config.get_conf(self, identifier=792413491)
        self.config.register_global(**{
            "positions": {},
        })
        self.config.register_guild(**{
            "channel": 0,
            "queue": "",
        })

    async def cog_load(self):
        copyreg.pickle(lavalink.Track, utils.pickle_track)
        asyncio.create_task(self.load())

    async def cog_unload(self):
        self.save_current_tracks.stop()
        if not utils.is_shutting_down(self.bot):
            # cog got manually disabled, clear everything to prevent desyncs
            await self.config.clear_all()
            await utils.heal_persistent_queue()

    @tasks.loop(seconds=5)
    async def save_current_tracks(self):
        # every n seconds, store the positions of all players at the same time
        # and also store any player queues that have changed since the last loop
        players = utils.all_lavalink_players()
        for player in players:
            guild_id = player.guild.id
            entry = self.queues.setdefault(guild_id, utils.QueueState(guild_id))
            entry.position = player.position
            queue = [player.current] + player.queue
            new_queue_id = tuple(track.track_identifier if track else None for track in queue)
            if new_queue_id != entry.queue_id:
                # not computationally expensive even for hundreds of tracks
                # it may even be more overhead than savings if we started a thread for the queue pickle
                # storing the config is usually not significant either, but large bots would probably be using a database instead of json
                entry.queue_id = new_queue_id
                entry.queue_pickle = b64encode(pickle.dumps(queue)).decode()
                await self.config.guild(player.guild).queue.set(entry.queue_pickle)
        positions = {player.guild.id: player.position for player in players}
        await self.config.positions.set(positions)

    async def wait_for_lavalink(self, audio: Audio):
        # the timing is sensitive if we want to prevent the default persist_queue behavior.
        # internally, red (as of 3.5.24) does the following:
        #   [ red_ready -> audio cog apis initialize -> cog_ready_event fires -> lavalink_connect_task starts ]
        # while lavalink is trying to connect, I monkey patch the persistent queue api, such that later restore_players sees no data.
        # after some time passes and lavalink finishes loading, restore_players starts (which now does nothing) and the bot is ready to play audio.
        await audio.cog_ready_event.wait()
        if not audio.api_interface:
            raise RuntimeError("audio cog's api_interface not set")
        await utils.neuter_persistent_queue(audio.api_interface.persistent_queue_api)
        if not audio.lavalink_connect_task:
            raise RuntimeError("audio cog's lavalink_connect_task never started")
        await audio.lavalink_connect_task
        if audio.lavalink_connection_aborted:
            raise RuntimeError("lavalink connection failed")

    async def load(self):
        await self.bot.wait_until_red_ready()
        audio: Optional[Audio] = self.bot.get_cog("Audio")  # type: ignore
        if not audio:
            log.error("Audio cog not loaded")
            return
        try:
            await self.wait_for_lavalink(audio)
        except Exception:
            log.exception("Failed to establish lavalink connection")
            return

        reconnect_config = await self.config.all_guilds()
        audio_config = await audio.config.all_guilds()
        auto_deafen = {guild_id: config.get("auto_deafen", True) for guild_id, config in audio_config.items()}
        persist_queue = {guild_id: config.get("persist_queue", True) for guild_id, config in audio_config.items()}
        current_channels = {guild_id: config.get("channel", 0) for guild_id, config in reconnect_config.items()}
        queue_pickles = {guild_id: config.get("queue", "") for guild_id, config in reconnect_config.items()}
        positions: dict[str, int] = await self.config.positions()
        
        # ngl I love list comprehensions
        tasks = [self.reconnect(channel, queue_pickles.get(guild_id), positions.get(str(guild_id), "0"), auto_deafen.get(guild_id, True))
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

        if all(channel_id == 0 for channel_id in current_channels.values()):
            # cog just got enabled
            players = utils.all_lavalink_players()
            for player in players:
                await self.config.guild(player.guild).channel.set(player.channel.id)
            log.info(f"Cold start of {len(players)} guilds")
        
        self.save_current_tracks.start()

    async def reconnect(self, channel: discord.channel.VocalGuildChannel, queue_pickle: Optional[str], position: int, self_deaf: bool):
        # I chose to replace the existing persist_queue behavior entirely (rather than just managing the current track) because:
        #   * persist_queue does not take into account empty queues
        #   * timing was inconsistent and hard to hook into
        #   * manual actions on the queue (skip, remove, shuffle) don't get stored until the next track starts
        #   * edge cases made queues get duplicated or erased, I couldn't rely on it
        #   * restored queue tracks did not preserve the original requester user (falls back to the bot user)
        player = await channel.connect(cls=lavalink.Player, self_deaf=self_deaf)  # type: ignore
        if not queue_pickle:
            return
        queue: list[lavalink.Track] = pickle.loads(b64decode(queue_pickle))
        if not queue:
            return
        for track in queue:
            if isinstance(track, lavalink.Track) and isinstance(track.requester, int):
                track.requester = channel.guild.get_member(track.requester)  # type: ignore
        player.queue = queue
        if queue[0] is None:
            queue.pop(0)
        else:
            queue[0].start_timestamp = position
            await player.play()

    @commands.Cog.listener()
    async def on_voice_state_update(self, member: discord.Member, before: discord.VoiceState, after: discord.VoiceState):
        if member is not member.guild.me or utils.is_shutting_down(self.bot):
            return
        if after.channel:
            await self.config.guild(member.guild).channel.set(after.channel.id)
        else:
            await self.config.guild(member.guild).channel.set(0)
            await self.config.guild(member.guild).queue.set("")
