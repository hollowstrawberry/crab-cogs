import io
import discord
from datetime import datetime
from redbot.core import commands, Config

IMAGE_TYPES = (".png", ".jpg", ".jpeg", ".gif", ".webp")

class ImageLog(commands.Cog):
    """Logs deleted images for moderation purposes."""

    def __init__(self, bot):
        super().__init__()
        self.bot = bot
        self.logchannels: dict[int, int] = {}
        self.config = Config.get_conf(self, identifier=6961676567)
        self.config.register_guild(channel=0)

    async def load_config(self):
        all_config = await self.config.all_guilds()
        self.logchannels = {guild_id: conf['channel'] for guild_id, conf in all_config.items()}

    async def red_delete_data_for_user(self, requester: str, user_id: int):
        pass

    @commands.Cog.listener(name="on_raw_message_delete")
    async def on_raw_message_delete_listener(self, ctx: discord.RawMessageDeleteEvent):
        message = ctx.cached_message
        if not message or not self.logchannels.get(ctx.guild_id, 0):
            return
        guild = self.bot.get_guild(ctx.guild_id)
        channel = guild.get_channel(ctx.channel_id)
        log_channel = guild.get_channel(self.logchannels[guild.id])
        attachments = [a for a in message.attachments if a.filename.lower().endswith(IMAGE_TYPES)]
        if not log_channel or not attachments:
            return
        if await self.bot.cog_disabled_in_guild(self, guild):
            return
        for attachment in attachments:
            embed = discord.Embed(
                title="Image deleted",
                description=message.content[:1990] if message.content else None,
                color=await ctx.embed_color(),
                timestamp=datetime.utcnow())
            embed.set_author(name=str(message.author), icon_url=str(message.author.avatar_url))
            embed.add_field(f"Channel", channel.mention)
            if channel.permissions_for(guild.me).view_audit_log:
                deleter = None
                async for log in guild.audit_logs(limit=2, action=discord.AuditLogAction.message_delete):
                    if log.target.id == message.author.id and log.extra.channel.id == message.channel.id:
                        deleter = log.user
                        break
                if not deleter:
                    if channel.permissions_for(message.author).manage_messages:
                        return # self delete by mod
                    deleter = message.author
                embed.add_field("Probably deleted by", deleter.mention)
            else:
                embed.add_field("Missing audit log permission", "Oops")
            img = io.BytesIO()
            try:
                await attachment.save(img, use_cached=True)
            except:
                file = None
            else:
                file = discord.File(img, filename=attachment.filename)
            embed.set_image(url=f"attachment://{attachment.filename}")
            await log_channel.send(embed=embed, file=file)

    @commands.group(invoke_without_command=True)
    @commands.has_permissions(manage_guild=True)
    async def imagelog(self, ctx: commands.Context):
        """View the current image log channel."""
        channel_id = await self.logchannels.get(ctx.guild.id, 0)
        if channel_id:
            await ctx.reply(f"Deleted images are currently logged to <#{channel_id}>\nYou can change it or remove it with {ctx.prefix}imagelog setchannel")
        else:
            await ctx.reply(f"Image log disabled. You can assign it to the current channel with {ctx.prefix}imagelog setchannel")

    @imagelog.command(invoke_without_command=True)
    async def setchannel(self, ctx: commands.Context):
        """Sets the image log channel to the current channel."""
        if ctx.channel.id == self.logchannels.get(ctx.guild.id, 0):
            self.logchannels[ctx.guild.id] = 0
            await self.config.guild(ctx.guild).channel.set(0)
            await ctx.reply("Removed image log channel.")
        else:
            self.logchannels[ctx.guild.id] = ctx.channel.id
            await self.config.guild(ctx.guild).channel.set(ctx.channel.id)
            await ctx.reply(f"Set image log channel to {ctx.channel.mention}. Use this command again to remove it.")
