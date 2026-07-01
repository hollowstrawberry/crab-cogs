import re
import logging
import asyncio
import discord
import lavalink
from typing import Coroutine, Optional, Union
from datetime import datetime, timezone
from collections import defaultdict

from discord.ext import tasks
from redbot.core import commands
from redbot.core.bot import Red, Config
from redbot.core.commands import Cog
from redbot.cogs.audio.core import Audio

from audioplayer.playerview import AudioPlayerView

log = logging.getLogger("red.crab-cogs.audioplayer")

INTERVAL = 9.9
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
        self.inline_guilds: list[int] = []
        self.designated_channel: dict[int, int] = defaultdict(int)
        self.view: dict[int, Optional[AudioPlayerView]] = defaultdict(lambda: None)
        self.last_message: dict[int, Optional[discord.Message]] = defaultdict(lambda: None)
        self.last_song: dict[int, Optional[lavalink.Track]] = defaultdict(lambda: None)
        self.last_updated: dict[int, datetime] = defaultdict(lambda: datetime.min.replace(tzinfo=timezone.utc))
        self.config.register_guild(**{
            "channel": 0,
            "inline": False,
        })

    async def cog_load(self):
        all_config = await self.config.all_guilds()
        for guild_id, config in all_config.items():
            if config["channel"] != 0:
                self.designated_channel[guild_id] = config["channel"]
            if config["inline"]:
                self.inline_guilds.append(guild_id)
        self.player_loop.start()

    async def cog_unload(self):
        self.player_loop.stop()
        await asyncio.gather(*[msg.delete() for msg in self.last_message.values() if msg is not None], return_exceptions=True)


    @tasks.loop(seconds=1, reconnect=True)
    async def player_loop(self):
        audio: Optional[Audio] = self.bot.get_cog("Audio") # type: ignore
        if not audio:
            return
        
        pending: list[Coroutine] = []
        maybe_orphaned: list[int] = []
        for guild_id in set(self.inline_guilds) | set(self.designated_channel):
            try:
                player = lavalink.get_player(guild_id)
            except lavalink.errors.RedLavalinkException:
                player = None
            if player and all(
                    member.bot or not member.voice or member.voice.deaf or member.voice.self_deaf or member.voice.afk
                    for member in player.channel.members):
                continue
            now = datetime.now(timezone.utc)
            current_song = player.current if player else None
            changed_song = current_song != self.last_song[guild_id]
            update_due = (now - self.last_updated[guild_id]).total_seconds() >= INTERVAL
            if not update_due and not changed_song:
                continue
            self.last_updated[guild_id] = now
            self.last_song[guild_id] = current_song
            if guild_id in self.inline_guilds:
                if player and player.channel:
                    pending.append(self.update_player(player.channel, audio, player))
                else:
                    maybe_orphaned.append(guild_id)
            if channel := self.bot.get_channel(self.designated_channel[guild_id]):
                assert isinstance(channel, discord.TextChannel)
                pending.append(self.update_player(channel, audio, player))

        for view in self.view.values():
            if not view or not view.message or not view.message.guild:
                continue
            channel, guild = view.message.channel, view.message.guild
            if guild.id in maybe_orphaned and self.designated_channel[guild_id] != channel.id:
                assert isinstance(channel, discord.TextChannel)
                pending.append(self.update_player(channel, audio, None))

        results = await asyncio.gather(*pending, return_exceptions=True)
        for result in results:
            if isinstance(result, BaseException):
                log.error(f"{type(result).__name__}: {result}")


    async def update_player(self, channel: Union[discord.TextChannel, discord.VoiceChannel], audio: Audio, player: Optional[lavalink.Player]):
        # Remove orphan player
        if not player or not player.current:
            await self.destroy_player(channel.id)
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

        view = self.view[channel.id] or AudioPlayerView(self)
        self.view[channel.id] = view
        view.set_paused(player.paused)

        # Update the player message
        latest_message = await channel.history(limit=1).__anext__()
        last_message = self.last_message[channel.id]
        if latest_message == last_message:
            await latest_message.edit(embed=embed, view=view)
        else:
            if last_message:
                try:
                    await last_message.delete()
                except discord.DiscordException:
                    pass
            view.message = await channel.send(embed=embed, view=view)
            self.last_message[channel.id] = view.message


    async def destroy_player(self, channel_id: int):
        if last_message := self.last_message.pop(channel_id, None):
            self.view.pop(channel_id, None)
            try:
                await last_message.delete()
            except discord.DiscordException:
                pass


    @commands.group(name="audioplayer")  # type: ignore
    @commands.admin()
    @commands.guild_only()
    async def command_audioplayer(self, _: commands.Context):
        """Configuration commands for AudioPlayer"""
        pass

    @command_audioplayer.command(name="dedicated", aliases=["channel"])
    async def command_audioplayer_dedicated(self, ctx: commands.Context, channel: Optional[discord.TextChannel]):
        """Sets or clears a dedicated channel for the AudioPlayer"""
        assert ctx.guild
        existing_channel_id = self.designated_channel[ctx.guild.id]
        await self.destroy_player(existing_channel_id)

        if not channel:
            self.designated_channel[ctx.guild.id] = 0
            await self.config.guild(ctx.guild).channel.set(0)
            if existing_channel_id == 0:
                await ctx.reply("AudioPlayer is not set to a dedicated channel.\n" \
                                "You could set it to a spam or music channel where people would normally use music commands in your server, " \
                                "or enable `[p]audioplayer auto` for it to appear inside the voice channel itself.")
            else:
                await ctx.reply("AudioPlayer channel cleared. The player will not appear in a dedicated channel")
        else:
            await self.config.guild(ctx.guild).channel.set(channel.id)
            self.designated_channel[ctx.guild.id] = channel.id
            await ctx.reply(f"The player will appear in {channel.mention} while audio is playing.")
        
        audio: Optional[Audio] = self.bot.get_cog("Audio")  # type: ignore
        if not audio:
            await ctx.send("Warning: Audio cog is not enabled, contact the bot owner for more information.")

    @command_audioplayer.command(name="auto", aliases=["inline", "inset", "automatic"])
    async def command_audiplayer_inline(self, ctx: commands.Context):
        """Toggles whether an AudioPlayer will appear inside the voice channel itself."""
        assert ctx.guild
        if ctx.guild.id in self.inline_guilds:
            enabled = False
            self.inline_guilds.remove(ctx.guild.id)
            try:
                player = lavalink.get_player(ctx.guild.id)
            except lavalink.errors.RedLavalinkException:
                player = None
            if player and player.channel:
                await self.destroy_player(player.channel.id)
        else:
            enabled = True
            self.inline_guilds.append(ctx.guild.id)

        await self.config.guild(ctx.guild).inline.set(enabled)
        await ctx.reply(f"An AudioPlayer will {'now' if enabled else 'no longer'} appear inside the voice channel itself.")
        
        audio: Optional[Audio] = self.bot.get_cog("Audio")  # type: ignore
        if not audio:
            await ctx.send("Warning: Audio cog is not enabled, contact the bot owner for more information.")
