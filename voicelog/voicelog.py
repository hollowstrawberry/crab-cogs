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

    async def load_config(self):
        all_config = await self.config.all_guilds()
        self.logchannels = set(guild_id for guild_id, conf in all_config.items() if conf['enabled'])

    async def red_delete_data_for_user(self, requester: str, user_id: int):
        pass

    @commands.Cog.listener()
    async def on_voice_state_update(self, member: discord.Member, before: discord.VoiceState, after: discord.VoiceState):
        guild = member.guild
        if guild.id not in self.allowedguilds:
            return
        if before.channel == after.channel:
            return
        if await self.bot.cog_disabled_in_guild(self, guild):
            return 
        if after.channel and await self.is_ignored_channel(guild, after.channel):
            return
        if before.channel and await self.is_ignored_channel(guild, before.channel):
            return
        embed = discord.Embed(color=member.color, timestamp=datetime.utcnow())
        if not before.channel:
            embed.set_author(name="Connected", icon_url=str(member.avatar_url))
            embed.description = f"{member.mention} has joined {after.channel.mention}"
        elif not after.channel:
            embed.set_author(name="Disconnected", icon_url=str(member.avatar_url))
            embed.description = f"{member.mention} has left {before.channel.mention}"
        else:
            embed.set_author(name="Moved", icon_url=str(member.avatar_url))
            embed.description = f"{member.mention} has moved from {before.channel.mention} to {after.channel.mention}"
        await (after.channel or before.channel).send(embed=embed)

    @commands.group(invoke_without_command=True)
    @commands.has_permissions(manage_guild=True)
    async def voicelog(self, ctx: commands.Context):
        """Voice Log configuration"""
        await ctx.send_help()

    @voicelog.command()
    async def enable(self, ctx: commands.Context):
        """Enable voice log for the whole guild."""
        self.allowedguilds.update([ctx.guild.id])
        await self.config.guild(ctx.guild).enabled.set(True)
        await ctx.react_quietly('✅')

    @voicelog.command()
    async def disable(self, ctx: commands.Context):
        """Disable voice log for the whole guild."""
        self.allowedguilds.difference_update([ctx.guild.id])
        await self.config.guild(ctx.guild).enabled.set(False)
        await ctx.react_quietly('✅')
