import types
import logging
import discord
import lavalink
from copy import copy
from typing import Optional
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
        if not (ctx := await self.get_context(inter, "queue", ephemeral=True)):
            return
        try:
            await audio.command_queue(ctx)
        except Exception: # user-facing error
            log.error("queue button", exc_info=True)
            await inter.followup.send(ERROR_UNKNOWN)

    @discord.ui.button(emoji="⏪", style=discord.ButtonStyle.grey)
    async def previous(self, inter: discord.Interaction, _):
        assert inter.guild
        audio: Audio = self.cog.bot.get_cog("Audio")
        player = lavalink.get_player(inter.guild.id)
        current_song = player.current
        if not current_song:
            await inter.followup.send(ERROR_UNKNOWN)
            return
        action = "seek" if player.position > 10000 else "prev"
        if not (ctx := await self.get_context(inter, action, ephemeral=False)):
            return
        try:
            if action == "seek":
                await audio.command_seek(ctx, -player.position // 1000)
            elif await audio.command_prev(ctx) is None: 
                player.queue.insert(0, current_song)
        except Exception: # user-facing error
            log.error("previous button", exc_info=True)
            await inter.followup.send(ERROR_UNKNOWN)
        else:
            await self.update_player(ctx, audio)

    @discord.ui.button(style=discord.ButtonStyle.grey)
    async def pause(self, inter: discord.Interaction, _):
        audio: Audio = self.cog.bot.get_cog("Audio")
        if not (ctx := await self.get_context(inter, "pause", ephemeral=True)):
            return
        try:
            await audio.command_pause(ctx)
        except Exception: # user-facing error
            log.error("pause button", exc_info=True)
            await inter.followup.send(ERROR_UNKNOWN)
        else:
            await self.update_player(ctx, audio)

    @discord.ui.button(emoji="⏩", style=discord.ButtonStyle.grey)
    async def skip(self, inter: discord.Interaction, _):
        audio: Audio = self.cog.bot.get_cog("Audio")
        if not (ctx := await self.get_context(inter, "skip", ephemeral=False)):
            return
        try:
            await audio.command_skip(ctx)
        except Exception: # user-facing error
            log.error("skip button", exc_info=True)
            await inter.followup.send(ERROR_UNKNOWN)
        else:
            await self.update_player(ctx, audio)

    @discord.ui.button(emoji="⏹️", style=discord.ButtonStyle.grey)
    async def stop(self, inter: discord.Interaction, _):
        audio: Audio = self.cog.bot.get_cog("Audio")
        if not (ctx := await self.get_context(inter, "stop", ephemeral=False)):
            return
        try:
            await audio.command_stop(ctx)
        except Exception: # user-facing error
            log.error("stop button", exc_info=True)
            await inter.followup.send(ERROR_UNKNOWN)
        else:
            await self.update_player(ctx, audio)

    async def get_context(self, inter: discord.Interaction, command_name: str, ephemeral: bool) -> Optional[commands.Context]:
        # spoof a context where the user legitimately called the audio cog's command
        prefix = await self.cog.bot.get_prefix(self.message)
        prefix = prefix[0] if isinstance(prefix, list) else prefix
        assert self.message is not None
        fake_message = copy(self.message)
        fake_message.content = prefix + command_name
        fake_message.author = inter.user
        ctx: commands.Context = await self.cog.bot.get_context(fake_message)
        # permissions
        try:
            command = ctx.bot.get_command(command_name)
            allowed = await command.can_run(ctx, check_all_parents=True, change_permission_state=False)
        except commands.CommandError:
            allowed = False
        if not allowed:
            await inter.response.send_message(ERROR_FORBIDDEN, ephemeral=True)
            return None
        # deferring allows me to only send followups, regular interaction responses cause weird edge cases with my hacky setup
        await inter.response.defer()
        # convert command responses into interaction responses
        async def send(self, *args, **kwargs):
            new_kwargs = {
                "content": f"-# {inter.user.mention} pressed a button" if not ephemeral else "",
                "embed": kwargs.get("embed"),
                "ephemeral": ephemeral,
                "allowed_mentions": discord.AllowedMentions.none(),
            }
            if "view" in kwargs:
                new_kwargs["view"] = kwargs["view"]
            return await inter.followup.send(**new_kwargs)  # type: ignore
        ctx.send = types.MethodType(send, ctx)
        return ctx
    
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
