import io
import logging
import discord
from discord.ui import View
from datetime import datetime
from typing import Optional, Dict
from redbot.core import commands, Config

log = logging.getLogger("red.crab-cogs.imagelog")

IMAGE_TYPES = (".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp")


class SetChannelConfirmation(View):
    def __init__(self, cog: "ImageLog"):
        super().__init__(timeout=60)
        self.cog = cog
        self.pressed = False
        self.message: Optional[discord.Message] = None

    @discord.ui.button(label='Accept', style=discord.ButtonStyle.green)
    async def accept(self, ctx: discord.Interaction, _: discord.Button):
        if not ctx.user.resolved_permissions.manage_guild:
            await ctx.response.send_message("You must have the Manage Guild permission to interact with this message", ephemeral=True)
            return
        if self.pressed:
            return
        
        self.pressed = True
        self.cog.logchannels[ctx.guild.id] = ctx.channel.id
        await self.cog.config.guild(ctx.guild).channel.set(ctx.channel.id)
        
        if self.message:
            await self.message.edit(view=None)
        await ctx.response.send_message(f"Set image log channel to {ctx.channel.mention}")

    @discord.ui.button(label='Cancel', style=discord.ButtonStyle.red)
    async def cancel(self, ctx: discord.Interaction, _: discord.Button):
        if not ctx.user.resolved_permissions.manage_guild:
            await ctx.response.send_message("You must have the Manage Guild permission to interact with this message", ephemeral=True)
            return
        if self.pressed:
            return
        
        self.pressed = True

        if self.message:
            await self.message.edit(view=None)
        await ctx.response.send_message("Operation cancelled")

    async def on_timeout(self) -> None:
        if self.message and not self.pressed:
            await self.message.edit(view=None)



class ImageLog(commands.Cog):
    """Logs deleted images for moderation purposes."""

    def __init__(self, bot):
        super().__init__()
        self.bot = bot
        self.logchannels: Dict[int, int] = {}
        self.manual_deleted_by: Dict[int, int] = {}  # may be used by other cogs
        self.config = Config.get_conf(self, identifier=6961676567)
        self.config.register_guild(channel=0, log_moderator_self_deletes=True)

    async def cog_load(self):
        all_config = await self.config.all_guilds()
        self.logchannels = {guild_id: conf['channel'] for guild_id, conf in all_config.items()}

    async def is_valid_red_message(self, message: discord.Message) -> bool:
        return await self.bot.allowed_by_whitelist_blacklist(message.author) \
               and await self.bot.ignored_channel_or_guild(message) \
               and not await self.bot.cog_disabled_in_guild(self, message.guild)


    @commands.Cog.listener()
    async def on_raw_message_delete(self, ctx: discord.RawMessageDeleteEvent):
        message = ctx.cached_message
        if not message or not self.logchannels.get(ctx.guild_id, 0):
            return

        guild = message.guild
        channel = message.channel
        log_channel = guild.get_channel(self.logchannels[guild.id])
        attachments = [a for a in message.attachments if a.filename.lower().endswith(IMAGE_TYPES)]
        if not log_channel or not attachments:
            return
        if not await self.is_valid_red_message(message):
            return

        for i, attachment in enumerate(attachments):
            embed = discord.Embed(
                title="Image deleted" + (f" ({i+1}/{len(attachments)})" if len(attachments) > 1 else ""),
                description=message.content if message.content else "",
                color=message.author.color,
                timestamp=datetime.now())
            embed.set_author(name=str(message.author), icon_url=str(message.author.display_avatar.url))
            embed.add_field(name=f"Channel", value=channel.mention)

            if message.id in self.manual_deleted_by:
                embed.add_field(name="Deleted by", value=f"<@{self.manual_deleted_by.pop(message.id)}>")
            elif channel.permissions_for(guild.me).view_audit_log:
                deleter = None
                async for alog in guild.audit_logs(limit=2, action=discord.AuditLogAction.message_delete):
                    if alog.target.id == message.author.id and alog.extra.channel.id == message.channel.id:
                        deleter = alog.user
                        break
                if not deleter:
                    if channel.permissions_for(message.author).manage_messages and not await self.config.guild(guild).log_moderator_self_deletes():
                        return  # self delete by mod
                    deleter = message.author
                embed.add_field(name="Probably deleted by", value=deleter.mention)
            else:
                embed.add_field(name="Missing audit log permission", value="Oops")

            img = io.BytesIO()
            try:
                await attachment.save(img, use_cached=True)
            except discord.DiscordException:
                log.exception("Trying to save attachment")
                file = None
            else:
                file = discord.File(img, filename=attachment.filename)
                embed.set_image(url=f"attachment://{attachment.filename}")

            await log_channel.send(embed=embed, file=file)


    @commands.group(invoke_without_command=True)
    @commands.has_permissions(manage_guild=True)
    @commands.guild_only()
    async def imagelog(self, ctx: commands.Context):
        """View the current image log channel."""
        channel_id = self.logchannels.get(ctx.guild.id, 0)
        if channel_id:
            await ctx.reply(f"Deleted images are currently logged to <#{channel_id}>\nYou can change it or remove it with {ctx.prefix}imagelog setchannel")
        else:
            await ctx.reply(f"Image log disabled. You can assign it to the current channel with {ctx.prefix}imagelog setchannel")

    @imagelog.command(name="setchannel")
    async def imagelog_setchannel(self, ctx: commands.Context):
        """Sets the image log channel to the current channel."""
        if ctx.channel.id == self.logchannels.get(ctx.guild.id, 0):
            self.logchannels[ctx.guild.id] = 0
            await self.config.guild(ctx.guild).channel.set(0)
            await ctx.reply("Removed image log channel.")
        else:
            content = ":warning: Content saved this way is **not** usable for reporting users to Discord. You may also be liable for keeping content that breaks Discord TOS.\nAre you sure you want to enable image logging?"
            view = SetChannelConfirmation(self)
            message = await ctx.reply(content, view=view)
            view.message = message

    @imagelog.command(name="log_moderator_self_deletes")
    async def imagelog_modselfdeletes(self, ctx: commands.Context, value: Optional[bool]):
        """If disabled, users with Manage Message permission that delete their own image won't be logged. Enabled by default. True or False."""
        if value is not None:
            await self.config.guild(ctx.guild).log_moderator_self_deletes.set(value)
        await ctx.send(f"`log_moderator_self_deletes: {await self.config.guild(ctx.guild).log_moderator_self_deletes()}`")
