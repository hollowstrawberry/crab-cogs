import discord
from datetime import datetime
from redbot.core import commands, Config

class VoiceLog(commands.Cog):
    """Logs users joining and leaving a VC, inside the VC chat itself."""

    def __init__(self, bot):
        super().__init__()
        self.bot = bot
        self.allowedguilds = set()
        self.config = Config.get_conf(self, identifier=7669636567)
        self.config.register_guild(enabled=False)

    async def cog_load(self):
        all_config = await self.config.all_guilds()
        self.allowedguilds = set(guild_id for guild_id, conf in all_config.items() if conf['enabled'])

    @commands.Cog.listener()
    async def on_voice_state_update(self, member: discord.Member, before: discord.VoiceState, after: discord.VoiceState):
        guild = member.guild
        if guild.id not in self.allowedguilds:
            return
        if before.channel == after.channel:
            return
        if await self.bot.cog_disabled_in_guild(self, guild):
            return

        embed = discord.Embed(color=member.color, timestamp=datetime.now())
        if not before.channel:
            embed.set_author(name="Connected", icon_url=member.display_avatar.url)
            embed.description = f"{member.mention} has joined {after.channel.mention if after.channel else ''}"
        elif not after.channel:
            embed.set_author(name="Disconnected", icon_url=member.display_avatar.url)
            embed.description = f"{member.mention} has left {before.channel.mention}"
        else:
            embed.set_author(name="Moved", icon_url=member.display_avatar.url)
            embed.description = f"{member.mention} has moved from {before.channel.mention} to {after.channel.mention}"
        
        for channel in [before.channel, after.channel]:
            if not channel:
                continue
            perms = channel.permissions_for(channel.guild.me)
            if not perms.send_messages or not perms.embed_links:
                continue
            await channel.send(embed=embed)

    @commands.group(invoke_without_command=True)  # type: ignore
    @commands.has_permissions(manage_guild=True)
    @commands.guild_only()
    async def voicelog(self, ctx: commands.Context):
        """Voice Log configuration"""
        await ctx.send_help()

    @voicelog.command(name="enable")
    async def voicelog_enable(self, ctx: commands.Context):
        """Enable voice log for the whole guild."""
        assert ctx.guild
        self.allowedguilds.add(ctx.guild.id)
        await self.config.guild(ctx.guild).enabled.set(True)
        await ctx.tick(message="Voice Log enabled")

    @voicelog.command(name="disable")
    async def voicelog_disable(self, ctx: commands.Context):
        """Disable voice log for the whole guild."""
        assert ctx.guild
        self.allowedguilds.remove(ctx.guild.id)
        await self.config.guild(ctx.guild).enabled.set(False)
        await ctx.tick(message="Voice Log disabled")
