import types
import pickle
import copyreg
import logging
import asyncio
import discord
import lavalink
import itertools
from typing import Optional
from base64 import b64encode, b64decode
from dataclasses import dataclass
from discord.ext import tasks
from redbot.core import commands
from redbot.core.bot import Red, Config
from redbot.core.commands import Cog
from redbot.cogs.audio.core import Audio
from redbot.cogs.audio.apis.persist_queue_wrapper import QueueInterface

log = logging.getLogger("red.crab-cogs.audioreconnect")


def pickle_track(track: lavalink.Track):
    state = track.__dict__.copy()
    if isinstance(state.get('requester'), (discord.Member, discord.User)):
        state['requester'] = state['requester'].id
    return (lavalink.Track.__new__, (lavalink.Track,), state)


async def neuter_persistent_queue(queue_api: QueueInterface):
    async def dummy_fetch(self, *args, **kwargs):
        return []
    dummy = types.MethodType(dummy_fetch, queue_api)
    queue_api.fetch_all = dummy
    queue_api.played = dummy
    queue_api.enqueued = dummy
    queue_api.drop = dummy
    queue_api.delete_scheduled = dummy
    await asyncio.to_thread(queue_api.database.cursor().execute, queue_api.statement.drop_table)
    log.info("disabled builtin persist_queue")


@dataclass
class Queue:
    guild_id: int
    position: int = 0
    queue_id: tuple[int, ...] = ()
    queue_pickle: Optional[str] = None


class AudioReconnect(Cog):
    """Restores the current audio track progress when the bot restarts."""

    def __init__(self, bot: Red, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.bot = bot
        self.unloaded = False
        self.queues: dict[int, Queue] = {}
        self.config = Config.get_conf(self, identifier=792413491)
        self.config.register_global(**{
            "positions": {},
        })
        self.config.register_guild(**{
            "channel": 0,
            "queue": "",
        })

    async def cog_load(self):
        copyreg.pickle(lavalink.Track, pickle_track)
        asyncio.create_task(self.load())

    async def cog_unload(self):
        self.unloaded = True
        self.save_current_tracks.stop()

    @tasks.loop(seconds=5)
    async def save_current_tracks(self):
        nodes = lavalink.get_all_nodes()
        players = list(itertools.chain(*[list(node.players) for node in nodes]))
        for player in players:
            guild_id = player.guild.id
            entry = self.queues.setdefault(guild_id, Queue(guild_id))
            entry.position = player.position
            queue = [player.current] + player.queue
            new_queue_id = tuple(id(track) for track in queue)
            if new_queue_id != entry.queue_id:
                entry.queue_id = new_queue_id
                entry.queue_pickle = b64encode(pickle.dumps(queue)).decode()
                await self.config.guild(player.guild).queue.set(entry.queue_pickle)
                log.info(f"set {len(queue)=}")
        positions = {player.guild.id: player.position for player in players}
        await self.config.positions.set(positions)

    async def wait_for_lavalink(self, audio: Audio):
        await audio.cog_ready_event.wait()
        if not audio.api_interface:
            raise RuntimeError
        await neuter_persistent_queue(audio.api_interface.persistent_queue_api)
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
        queue_pickles = {guild_id: config.get("queue", "") for guild_id, config in reconnect_config.items()}
        positions: dict[str, int] = await self.config.positions()

        tasks = [self.reconnect(channel, queue_pickles.get(guild_id), positions.get(str(guild_id), 0), auto_deafen.get(guild_id, True))
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

    async def reconnect(self, channel: discord.channel.VocalGuildChannel, queue_pickle: Optional[str], position: int, self_deaf: bool):
        player = await channel.connect(cls=lavalink.Player, self_deaf=self_deaf)  # type: ignore
        if not queue_pickle:
            return
        queue: list[lavalink.Track] = pickle.loads(b64decode(queue_pickle))
        log.info(f"restore {channel.guild.id=} {len(queue)=} {position=}")
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
        if member is not member.guild.me:
            return
        await asyncio.sleep(1) # the idea is to hopefully prevent manual bot restarts from un-setting the current channel
        if self.unloaded:
            return
        log.info(f"set channel {after.channel.id if after.channel else 0}")
        await self.config.guild(member.guild).channel.set(after.channel.id if after.channel else 0)
