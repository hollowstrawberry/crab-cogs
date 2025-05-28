from builtins import anext
import time
import types
import logging
import discord
import lavalink
from copy import copy
from typing import Optional

from discord.ui import View
from discord.ext import tasks
from redbot.core import commands, app_commands
from redbot.core.bot import Red, Config
from redbot.core.commands import Cog
from redbot.cogs.audio.core import Audio

log = logging.getLogger("red.crab-cogs.audioplayer")

PLAYER_WIDTH = 15
LINE_SYMBOL = "⎯"
MARKER_SYMBOL = "🔘"


class PlayerView(View):
    def __init__(self, cog: "AudioPlayer", message: discord.Message):
        super().__init__(timeout=60)
        self.cog = cog
        self.message = message

    @discord.ui.button(emoji="⏯️", style=discord.ButtonStyle.grey)
    async def pause(self, inter: discord.Interaction, _):
        audio: Optional[Audio] = self.cog.bot.get_cog("Audio")
        ctx = await self.get_context(inter, audio, "pause")
        if not await self.can_run_command(ctx, "pause"):
            return
        await audio.command_pause(ctx)

    @discord.ui.button(emoji="⏩", style=discord.ButtonStyle.grey)
    async def skip(self, inter: discord.Interaction, _):
        audio: Optional[Audio] = self.cog.bot.get_cog("Audio")
        ctx = await self.get_context(inter, audio, "skip")
        if not await self.can_run_command(ctx, "skip"):
            return
        await audio.command_pause(ctx)

    async def get_context(self, inter: discord.Interaction, cog: Audio, command_name: str) -> commands.Context:
        prefix = await self.cog.bot.get_prefix(self.message)
        fake_message = copy(self.message)
        fake_message.content = prefix + command_name
        fake_message.author = inter.user
        ctx: commands.Context = await self.cog.bot.get_context(fake_message)  # noqa
        ctx.command.cog = cog
        return ctx

    async def can_run_command(self, ctx: commands.Context, command_name: str) -> bool:
        command = ctx.bot.get_command(command_name)
        try:
            can = await command.can_run(ctx, check_all_parents=True, change_permission_state=False)
        except commands.CommandError:
            can = False
        if not can:
            await ctx.send("You do not have permission to do this.", ephemeral=True)
        return can


class AudioPlayer(Cog):
    """Live player for the current song from the audio cog."""

    def __init__(self, bot: Red, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.bot = bot
        self.config = Config.get_conf(self, identifier=772413491)
        self.channel: dict[int, int] = {}
        self.last_player: dict[int, int] = {}
        self.interval: dict[int, int] = {}
        self.config.register_guild(**{
            "channel": 0,
            "interval": 3,
        })

    async def cog_load(self):
        all_config = await self.config.all_guilds()
        for guild_id, config in all_config.items():
            if config["channel"] != 0:
                self.channel[guild_id] = config["channel"]
                self.interval[guild_id] = config["interval"]
        self.player_loop.start()

    async def cog_unload(self):
        self.player_loop.stop()

    @tasks.loop(seconds=1, reconnect=True)
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
            if int(time.time()) % self.interval.get(guild_id, 5) != 0:
                continue
            player = lavalink.get_player(guild_id)
            if not player or not player.current:
                if self.last_player.get(guild_id):
                    message = await channel.fetch_message(self.last_player[guild_id])
                    if message:
                        await message.delete()
                    del self.last_player[guild_id]
                continue
            # Format the player message
            embed = discord.Embed()
            embed.color = await self.bot.get_embed_color(channel)
            icon = "⏸️" if player.paused else "▶️"
            track_name = await audio.get_track_description(player.current, audio.local_folder_current_path)
            embed.title = f"{icon} {track_name}"
            if not player.current.is_stream and player.current.length and player.current.length != 0:
                ratio = player.position / player.current.length
                pos = round(player.position / 1000)
                length = round(player.current.length / 1000)
                line = (round(PLAYER_WIDTH * ratio) * LINE_SYMBOL) + MARKER_SYMBOL + ((PLAYER_WIDTH - 1 - round(PLAYER_WIDTH * ratio)) * LINE_SYMBOL)
                embed.description = f"`{pos//60:02}:{pos%60:02}{line}{length//60:02}:{length%60:02}`"
            else:
                pos = round(player.position / 1000)
                line = ((PLAYER_WIDTH // 2) * LINE_SYMBOL) + MARKER_SYMBOL + ((PLAYER_WIDTH // 2) * LINE_SYMBOL)
                embed.description = f"`{pos//60:02}:{pos%60:02}{line}unknown`"
            view = PlayerView(self)
            # Update the player message
            last_message = await anext(channel.history(limit=1))
            if last_message.id == self.last_player.get(guild_id, 0):
                message = await channel.fetch_message(last_message.id)
                if message:
                    await message.edit(embed=embed, view=view)
                else:
                    message = await channel.send(embed=embed, view=view)
                    self.last_player[guild_id] = message.id
            else:
                if self.last_player.get(guild_id, 0):
                    old_message = await channel.fetch_message(self.last_player[guild_id])
                    if old_message:
                        await old_message.delete()
                message = await channel.send(embed=embed, view=view)
                self.last_player[guild_id] = message.id

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
