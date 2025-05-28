import logging
import discord
import types
from copy import copy
from typing import Optional
from discord.ui import View
from redbot.core import commands
from redbot.cogs.audio.core import Audio

log = logging.getLogger("red.crab-cogs.audioplayer")


class PlayerView(View):
    def __init__(self, cog):
        super().__init__(timeout=60)
        self.cog = cog
        self.message: Optional[discord.Message] = None

    @discord.ui.button(emoji="🔽", style=discord.ButtonStyle.grey)
    async def queue(self, inter: discord.Interaction, _):
        audio: Optional[Audio] = self.cog.bot.get_cog("Audio")
        ctx = await self.get_context(inter, audio, "queue", ephemeral=True)
        if not await self.can_run_command(ctx, "queue"):
            await inter.response.send_message("You're not allowed to perform this action.")
            return
        try:
            await audio.command_queue(ctx)
        except Exception as error: # user-facing error
            log.error("queue button", exc_info=True)
            await inter.response.send_message("Oops! Try again.")

    @discord.ui.button(emoji="⏪", style=discord.ButtonStyle.grey)
    async def previous(self, inter: discord.Interaction, _):
        audio: Optional[Audio] = self.cog.bot.get_cog("Audio")
        ctx = await self.get_context(inter, audio, "prev", ephemeral=False)
        if not await self.can_run_command(ctx, "prev"):
            await inter.response.send_message("You're not allowed to perform this action.")
            return
        try:
            await audio.command_prev(ctx)
        except Exception as error: # user-facing error
            log.error("previous button", exc_info=True)
            await inter.response.send_message("Oops! Try again.")
        else:
            await self.cog.update_player(ctx.guild, ctx.channel, audio)

    @discord.ui.button(emoji="⏸️", style=discord.ButtonStyle.grey)
    async def pause(self, inter: discord.Interaction, _):
        audio: Optional[Audio] = self.cog.bot.get_cog("Audio")
        ctx = await self.get_context(inter, audio, "pause", ephemeral=True)
        if not await self.can_run_command(ctx, "pause"):
            await inter.response.send_message("You're not allowed to perform this action.")
            return
        try:
            await audio.command_pause(ctx)
        except Exception as error: # user-facing error
            log.error("pause button", exc_info=True)
            await inter.response.send_message("Oops! Try again.")
        else:
            await self.cog.update_player(ctx.guild, ctx.channel, audio)

    @discord.ui.button(emoji="⏩", style=discord.ButtonStyle.grey)
    async def skip(self, inter: discord.Interaction, _):
        audio: Optional[Audio] = self.cog.bot.get_cog("Audio")
        ctx = await self.get_context(inter, audio, "skip", ephemeral=False)
        if not await self.can_run_command(ctx, "skip"):
            await inter.response.send_message("You're not allowed to perform this action.")
            return
        try:
            await audio.command_skip(ctx)
        except Exception as error: # user-facing error
            log.error("skip button", exc_info=True)
            await inter.response.send_message("Oops! Try again.")
        else:
            await self.cog.update_player(ctx.guild, ctx.channel, audio)

    @discord.ui.button(emoji="⏹️", style=discord.ButtonStyle.grey)
    async def stop(self, inter: discord.Interaction, _):
        audio: Optional[Audio] = self.cog.bot.get_cog("Audio")
        ctx = await self.get_context(inter, audio, "stop", ephemeral=False)
        if not await self.can_run_command(ctx, "stop"):
            await inter.response.send_message("You're not allowed to perform this action.")
            return
        try:
            await audio.command_stop(ctx)
        except Exception as error: # user-facing error
            log.error("stop button", exc_info=True)
            await inter.response.send_message("Oops! Try again.")
        else:
            await self.cog.update_player(ctx.guild, ctx.channel, audio)

    async def get_context(self, inter: discord.Interaction, cog: Audio, command_name: str, ephemeral: bool) -> commands.Context:
        prefix = await self.cog.bot.get_prefix(self.message)
        prefix = prefix[0] if isinstance(prefix, list) else prefix
        fake_message = copy(self.message)
        fake_message.content = prefix + command_name
        fake_message.author = inter.user
        ctx: commands.Context = await self.cog.bot.get_context(fake_message)  # noqa
        async def send(self, *args, **kwargs):
            await inter.response.send_message(content=kwargs.get("content"), embed=kwargs.get("embed"), ephemeral=ephemeral)
        ctx.send = types.MethodType(send, ctx)  # prevent pause/skip buttons from sending a message
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