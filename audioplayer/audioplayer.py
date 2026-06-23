import re
import logging
import asyncio
import discord
import lavalink
from typing import Coroutine, Optional
from datetime import datetime

from discord.ext import tasks
from redbot.core import commands
from redbot.core.bot import Red, Config
from redbot.core.commands import Cog
from redbot.cogs.audio.core import Audio

from audioplayer.playerview import AudioPlayerView

log = logging.getLogger("red.crab-cogs.audioplayer")

INTERVAL = 9.5
PLAYER_WIDTH = 19
LINE_SYMBOL = "⎯"
MARKER_SYMBOL = "💠"


class AudioPlayer(Cog):
    """
    Live player interface for the audio cog. Stays at the bottom of chat for as long as there are people listening.
    """

    def __init__(self, bot: Red, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.bot = bot
        self.config = Config.get_conf(self, identifier=772413491)
        self.channel: dict[int, int] = {}
        self.view: dict[int, Optional[AudioPlayerView]] = {}
        self.last_message: dict[int, Optional[discord.Message]] = {}
        self.last_song: dict[int, Optional[lavalink.Track]] = {}
        self.last_updated: dict[int, datetime] = {}
        self.config.register_guild(**{
            "channel": 0,
        })

    async def cog_load(self):
        all_config = await self.config.all_guilds()
        for guild_id, config in all_config.items():
            if config["channel"] != 0:
                self.channel[guild_id] = config["channel"]
        self.player_loop.start()

    async def cog_unload(self):
        self.player_loop.stop()
        await asyncio.gather(*[msg.delete() for msg in self.last_message.values() if msg is not None], return_exceptions=True)

    @tasks.loop(seconds=1, reconnect=True)
    async def player_loop(self):
        if not self.channel:
            return
        audio: Audio | None = self.bot.get_cog("Audio") # type: ignore
        if not audio:
            return
        
        pending: list[Coroutine] = []
        for guild_id, channel_id in self.channel.items():
            guild = self.bot.get_guild(guild_id)
            if not guild:
                continue
            channel = guild.get_channel(channel_id)
            if not channel or not isinstance(channel, discord.TextChannel):
                continue

            try:
                player = lavalink.get_player(guild.id)
            except lavalink.errors.RedLavalinkException:
                player = None
            if not player:
                continue
            if all(member.bot for member in player.channel.members):
                continue

            now = datetime.utcnow()
            current_song = player.current if player else None
            changed_song = current_song != self.last_song.get(guild.id)
            update_due = (now - self.last_updated.get(guild.id, datetime.min)).total_seconds() >= INTERVAL
            if not update_due and not changed_song:
                continue
            self.last_updated[guild.id] = now
            self.last_song[guild.id] = current_song
            pending.append(self.update_player(guild, channel, audio, player))

        results = await asyncio.gather(*pending, return_exceptions=True)
        for result in results:
            if isinstance(result, Exception):
                log.error(f"{type(result).__name__}: {result}")

    async def update_player(self, guild: discord.Guild, channel: discord.TextChannel, audio: Audio, player: Optional[lavalink.Player]):
        # Remove orphan player
        if not player or not player.current:
            last_message = self.last_message.get(guild.id)
            if last_message:
                del self.last_message[guild.id]
                if self.last_song.get(guild.id):
                    del self.last_song[guild.id]
                if self.view.get(guild.id):
                    del self.view[guild.id]
                await last_message.delete()
            return
        
        # Format the player message
        embed = discord.Embed()
        embed.color = await self.bot.get_embed_color(channel)
        icon = "⏸️" if player.paused else "▶️"
        track_name = await audio.get_track_description(player.current, audio.local_folder_current_path) # type: ignore
        title_match = re.match(r"^\[(.*)\]\((.*)\)$", track_name.strip(" *") if track_name else "")
        if title_match:
            embed.title = f"{icon} {title_match.group(1)}"
            embed.url = title_match.group(2)
        else:
            embed.title = f"{icon} {track_name}"
        embed.description = ""
        if player.current.requester:
            embed.description += f"\n-# Requested by {player.current.requester}\n\n"
        if not player.current.is_stream and player.current.length:
            ratio = player.position / player.current.length
            filled = round(PLAYER_WIDTH * ratio) 
            pos = round(player.position / 1000)
            length = round(player.current.length / 1000)
            line = (filled * LINE_SYMBOL) + MARKER_SYMBOL + ((PLAYER_WIDTH - 1 - filled) * LINE_SYMBOL)
            embed.description += f"`{pos//60:02}:{pos%60:02}{line}{length//60:02}:{length%60:02}`"
        else:
            pos = round(player.position / 1000)
            length = 0
            line = ((PLAYER_WIDTH // 2) * LINE_SYMBOL) + MARKER_SYMBOL + ((PLAYER_WIDTH // 2) * LINE_SYMBOL)
            embed.description += f"`{pos//60:02}:{pos%60:02}{line}unknown`"
        if player.queue:
            total_length = round(sum(track.length or 180000 for track in player.queue) / 1000)
            if length > 0:
                total_length += length - pos
            formatted_time = ""
            if total_length // 3600:
                formatted_time += f"{total_length // 3600}:"
            formatted_time += f"{total_length//60%60:02}:{total_length%60:02}"
            embed.description += f"\n\n{len(player.queue)} more in queue ({formatted_time})"
        else:
            embed.description += "\n\nNo more in queue"
        if player.current.thumbnail:
            embed.set_thumbnail(url=player.current.thumbnail)

        view = self.view.get(guild.id) or AudioPlayerView(self)
        self.view[guild.id] = view
        view.set_paused(player.paused)

        # Update the player message
        latest_message = await channel.history(limit=1).__anext__()
        last_message = self.last_message.get(guild.id)
        if latest_message == last_message:
            await latest_message.edit(embed=embed, view=view)
        else:
            if last_message:
                try:
                    await last_message.delete()
                except discord.DiscordException:
                    pass
            message = await channel.send(embed=embed, view=view)
            self.last_message[guild.id] = message
            view.message = message

    @commands.group(name="audioplayer")  # type: ignore
    @commands.admin()
    @commands.guild_only()
    async def command_audioplayer(self, _: commands.Context):
        """Configuration commands for AudioPlayer"""
        pass

    @command_audioplayer.command(name="channel")
    async def command_audioplayer_channel(self, ctx: commands.Context, channel: Optional[discord.TextChannel]):
        """Sets the channel being used for AudioPlayer. Passing no arguments clears the channel, disabling the cog in this server."""
        assert ctx.guild is not None
        if last_message := self.last_message.pop(ctx.guild.id, None):
            try:
                await last_message.delete()
            except discord.DiscordException:
                pass
        if not channel:
            channel_id = await self.config.guild(ctx.guild).channel()
            self.channel[ctx.guild.id] = channel_id
            await self.config.guild(ctx.guild).channel.set(0)
            if channel_id == 0:
                await ctx.reply("AudioPlayer is not set to any channel. The player will not appear in this server.")
            else:
                await ctx.reply("AudioPlayer channel cleared. The player will not appear in this server.")
        else:
            await self.config.guild(ctx.guild).channel.set(channel.id)
            self.channel[ctx.guild.id] = channel.id
            await ctx.reply(f"The player will appear in {channel.mention} while audio is playing.")
        audio: Optional[Audio] = self.bot.get_cog("Audio")  # type: ignore
        if not audio:
            await ctx.send("Warning: Audio cog is not enabled, contact the bot owner for more information.")
