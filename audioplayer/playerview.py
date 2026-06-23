import types
import logging
import discord
import lavalink
from copy import copy
from datetime import datetime
from discord.ui import View
from redbot.core import commands
from redbot.cogs.audio.core import Audio

log = logging.getLogger("red.crab-cogs.audioplayer")

ERROR_FORBIDDEN = "You're not allowed to perform this action."
ERROR_UNKNOWN = "Oops! Try again."


class AudioPlayerView(View):
    def __init__(self, cog):
        super().__init__(timeout=None)
        self.cog = cog
        self.message: discord.Message | None = None

    def set_paused(self, paused: bool):
        self.pause.emoji = "▶️" if paused else "⏸️"

    @discord.ui.button(emoji="🇶", style=discord.ButtonStyle.grey)
    async def queue(self, inter: discord.Interaction, _):
        audio: Audio = self.cog.bot.get_cog("Audio")
        ctx = await self.get_context(inter, "queue", ephemeral=True)
        if not await self.can_run_command(ctx, "queue"):
            await inter.response.send_message(ERROR_FORBIDDEN)
            return
        try:
            await audio.command_queue(ctx)
        except Exception: # user-facing error
            log.error("queue button", exc_info=True)
            if not inter.response.is_done():
                await inter.response.send_message(ERROR_UNKNOWN)

    @discord.ui.button(emoji="⏪", style=discord.ButtonStyle.grey)
    async def previous(self, inter: discord.Interaction, _):
        audio: Audio = self.cog.bot.get_cog("Audio")
        ctx = await self.get_context(inter, "prev", ephemeral=False)
        if not await self.can_run_command(ctx, "prev"):
            await inter.response.send_message(ERROR_FORBIDDEN)
            return
        try:
            await audio.command_prev(ctx)
        except Exception: # user-facing error
            log.error("previous button", exc_info=True)
            if not inter.response.is_done():
                await inter.response.send_message(ERROR_UNKNOWN)
        else:
            await self.update_player(ctx, audio)

    @discord.ui.button(style=discord.ButtonStyle.grey)
    async def pause(self, inter: discord.Interaction, _):
        audio: Audio = self.cog.bot.get_cog("Audio")
        ctx = await self.get_context(inter, "pause", ephemeral=True)
        if not await self.can_run_command(ctx, "pause"):
            await inter.response.send_message(ERROR_FORBIDDEN)
            return
        try:
            await audio.command_pause(ctx)
        except Exception: # user-facing error
            log.error("pause button", exc_info=True)
            if not inter.response.is_done():
                await inter.response.send_message(ERROR_UNKNOWN)
        else:
            await self.update_player(ctx, audio)

    @discord.ui.button(emoji="⏩", style=discord.ButtonStyle.grey)
    async def skip(self, inter: discord.Interaction, _):
        audio: Audio = self.cog.bot.get_cog("Audio")
        ctx = await self.get_context(inter, "skip", ephemeral=False)
        if not await self.can_run_command(ctx, "skip"):
            await inter.response.send_message(ERROR_FORBIDDEN)
            return
        try:
            await audio.command_skip(ctx)
        except Exception: # user-facing error
            log.error("skip button", exc_info=True)
            if not inter.response.is_done():
                await inter.response.send_message(ERROR_UNKNOWN)
        else:
            await self.update_player(ctx, audio)

    @discord.ui.button(emoji="⏹️", style=discord.ButtonStyle.grey)
    async def stop(self, inter: discord.Interaction, _):
        audio: Audio = self.cog.bot.get_cog("Audio")
        ctx = await self.get_context(inter, "stop", ephemeral=False)
        if not await self.can_run_command(ctx, "stop"):
            await inter.response.send_message(ERROR_FORBIDDEN)
            return
        try:
            await audio.command_stop(ctx)
        except Exception: # user-facing error
            log.error("stop button", exc_info=True)
            if not inter.response.is_done():
                await inter.response.send_message(ERROR_UNKNOWN)
        else:
            await self.update_player(ctx, audio)

    async def get_context(self, inter: discord.Interaction, command_name: str, ephemeral: bool) -> commands.Context:
        prefix = await self.cog.bot.get_prefix(self.message)
        prefix = prefix[0] if isinstance(prefix, list) else prefix
        assert self.message is not None
        fake_message = copy(self.message)
        fake_message.content = prefix + command_name
        fake_message.author = inter.user
        ctx: commands.Context = await self.cog.bot.get_context(fake_message)

        # convert command responses into interaction responses
        async def send(self, *args, **kwargs):
            content = f"-# {inter.user.mention} pressed a button" if not ephemeral else ""
            new_kwargs = {
                "embed": kwargs.get("embed"),
                "ephemeral": ephemeral,
                "allowed_mentions": discord.AllowedMentions.none(),
            }
            if "view" in kwargs:
                new_kwargs["view"] = kwargs["view"]
            resp = await inter.response.send_message(content, **new_kwargs) # type: ignore
            setattr(resp, "edit", inter.response.edit_message)  # this prevents an error in queue info button
            return resp
        ctx.send = types.MethodType(send, ctx)

        return ctx

    async def can_run_command(self, ctx: commands.Context, command_name: str) -> bool:
        command = ctx.bot.get_command(command_name)
        try:
            can = await command.can_run(ctx, check_all_parents=True, change_permission_state=False)
        except commands.CommandError:
            can = False
        return can
    
    async def update_player(self, ctx: commands.Context, audio: Audio):
        assert ctx.guild is not None
        try:
            player = lavalink.get_player(ctx.guild.id)
        except lavalink.errors.PlayerNotFound:
            pass
        else:
            self.cog.last_updated[ctx.guild.id] = datetime.utcnow()
            self.cog.last_song[ctx.guild.id] = player.current if player else None
            await self.cog.update_player(ctx.guild, ctx.channel, audio, player)
