import re
import logging
import discord
import lavalink
from typing import Optional
from builtins import anext

from discord.ext import tasks
from redbot.core import commands
from redbot.core.bot import Red, Config
from redbot.core.commands import Cog
from redbot.cogs.audio.core import Audio

from audioplayer.playerview import PlayerView

log = logging.getLogger("red.crab-cogs.audioplayer")

PLAYER_WIDTH = 21
LINE_SYMBOL = "⎯"
MARKER_SYMBOL = "💠"


class AudioPlayer(Cog):
    """Live player interface for the audio cog."""

    def __init__(self, bot: Red, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.bot = bot
        self.config = Config.get_conf(self, identifier=772413491)
        self.channel: dict[int, int] = {}
        self.last_player: dict[int, int] = {}
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

    @tasks.loop(seconds=5, reconnect=True)
    async def player_loop(self):
        if not self.channel:
            return
        audio: Optional[Audio] = self.bot.get_cog("Audio")
        if not audio:
            return
        for guild_id, channel_id in self.channel.items():
            guild = self.bot.get_guild(guild_id)
            if not guild:
                continue
            channel = guild.get_channel(channel_id)
            if not channel:
                continue
            try:
                await self.update_player(guild, channel, audio)
            except Exception: # dont kill the task
                log.error("player loop", exc_info=True)
                continue

    async def update_player(self, guild: discord.Guild, channel: discord.TextChannel, audio: Audio):
        try:
            player = lavalink.get_player(guild.id)
        except lavalink.errors.PlayerNotFound:
            player = None
        if not player or not player.current:
            if self.last_player.get(guild.id):
                message = await channel.fetch_message(self.last_player[guild.id])
                if message:
                    await message.delete()
                del self.last_player[guild.id]
            return
        
        # Format the player message
        embed = discord.Embed()
        embed.color = await self.bot.get_embed_color(channel)
        icon = "⏸️" if player.paused else "▶️"
        track_name = await audio.get_track_description(player.current, audio.local_folder_current_path)
        title_match = re.match(r"^\[(.*)\]\((.*)\)$", track_name.strip(" *"))
        if title_match:
            embed.title = f"{icon} {title_match.group(1)}"
            embed.url = title_match.group(2)
        else:
            embed.title = f"{icon} {track_name}"
        embed.description = ""
        if player.current.requester:
            embed.description += f"\n-# Requested by {player.current.requester}\n\n"
        if not player.current.is_stream and player.current.length and player.current.length != 0:
            ratio = player.position / player.current.length
            pos = round(player.position / 1000)
            length = round(player.current.length / 1000)
            line = (round(PLAYER_WIDTH * ratio) * LINE_SYMBOL) + MARKER_SYMBOL + ((PLAYER_WIDTH - 1 - round(PLAYER_WIDTH * ratio)) * LINE_SYMBOL)
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
            embed.description += f"\n\nNo more in queue"
        if player.current.thumbnail:
            embed.set_thumbnail(url=player.current.thumbnail)
        view = PlayerView(self)

        # Update the player message
        last_message = await anext(channel.history(limit=1))
        if last_message.id == self.last_player.get(guild.id, 0):
            message = await channel.fetch_message(last_message.id)
            if message:
                view.message = message
                await message.edit(embed=embed, view=view)
            else:
                message = await channel.send(embed=embed, view=view)
                self.last_player[guild.id] = message.id
                view.message = message
        else:
            if self.last_player.get(guild.id, 0):
                old_message = await channel.fetch_message(self.last_player[guild.id])
                if old_message:
                    await old_message.delete()
            message = await channel.send(embed=embed, view=view)
            self.last_player[guild.id] = message.id
            view.message = message

    @commands.group(name="audioplayer")
    @commands.admin()
    async def command_audioplayer(self, _: commands.Context):
        """Configuration commands for AudioPlayer"""
        pass

    @command_audioplayer.command(name="channel")
    async def command_audioplayer_channel(self, ctx: commands.Context, channel: Optional[discord.TextChannel]):
        """Sets the channel being used for AudioPlayer. Passing no arguments clears the channel, disabling the cog in this server."""
        if self.last_player.get(ctx.guild.id):
            player_channel = ctx.guild.get_channel(self.channel.get(ctx.guild.id, 0))
            if player_channel:
                message = await player_channel.fetch_message(self.last_player[ctx.guild.id])
                if message:
                    await message.delete()
                del self.last_player[ctx.guild.id]
        if not channel:
            channel_id = await self.config.guild(ctx.guild).channel()
            self.channel[ctx.guild.id] = channel.id
            await self.config.guild(ctx.guild).channel.set(0)
            if channel_id == 0:
                await ctx.reply("AudioPlayer is not set to any channel. The player will not appear in this server.")
            else:
                await ctx.reply("AudioPlayer channel cleared. The player will not appear in this server.")
        else:
            await self.config.guild(ctx.guild).channel.set(channel.id)
            self.channel[ctx.guild.id] = channel.id
            await ctx.reply(f"The player will appear in {channel.mention} while audio is playing.")
        audio: Optional[Audio] = self.bot.get_cog("Audio")
        if not audio:
            await ctx.send("Warning: Audio cog is not enabled, contact the bot owner for more information.")
