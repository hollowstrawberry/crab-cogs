import discord
from redbot.core import commands, Config
from typing import Union

class Verify(commands.Cog):
    """Verify yourself."""

    def __init__(self, bot):
        super().__init__()
        self.bot = bot
        self.config = Config.get_conf(self, identifier=6460697574)
        self.config.register_guild(roles={})
        self.config.register_member(username="*None*", uid=0)

    async def red_delete_data_for_user(self, requester: str, user_id: int):
        guilds = await self.config.all_guilds()
        for guild_id in guilds.keys():
            await self.config.member_from_ids(guild_id, user_id).clear()

    # Commands

    @commands.guild_only()
    @commands.bot_has_permissions(manage_nicknames=True, manage_roles=True)
    @commands.command()
    async def verify(self, ctx: commands.Context, username: str, uid: int, role: discord.Role):
        """Verify yourself in this server."""
        username = username.strip()
        if not username:
            await ctx.send("Invalid username! Please try again.")
            return
        if uid < 1:
            await ctx.send("Invalid UID! Please try again. You can find your UID in your profile in-game.")
            return
        roles = await self.config.guild(ctx.guild).roles()
        if not role or role.id not in roles:
            await ctx.send(f"Role must be one of: {', '.join(v for k, v in roles.items())}. Please try again.")
            return
        author: discord.Member = ctx.author
        await self.config.member(author).username.set(username)
        await self.config.member(author).uid.set(uid)
        try:
            await author.edit(nick=username)
        except:
            pass
        await author.add_roles(role)
        await ctx.send("✅ Verification complete")

    @commands.guild_only()
    @commands.command(aliases=["verification"])
    async def profile(self, ctx: commands.Context, member: discord.Member):
        """View verification info for a member."""
        embed = discord.Embed(description=member.mention, color=await ctx.embed_color())
        embed.add_field(name="Username", value=await self.config.member(member).username())
        embed.add_field(name="UID", value=await self.config.member(member).uid())
        await ctx.send(embed=embed)

    @commands.mod()
    @commands.guild_only()
    @commands.group(invoke_without_command=True)
    async def verifyset(self, ctx: commands.Context):
        """Verify configuration"""
        await ctx.send_help()

    @verifyset.group(name="role", invoke_without_command=True)
    async def verifyset_role(self, ctx: commands.Context):
        """Add roles a user can choose upon verification"""
        await ctx.send_help()

    @verifyset_role.command()
    async def add(self, ctx: commands.Context, role: discord.Role):
        """Add a role a user can choose upon verification"""
        async with self.config.guild(ctx.guild).roles() as roles:
            roles[role.id] = role.name
        await ctx.send(f"Added {role.name} to the roles a user can choose upon verification.")

    @verifyset_role.command()
    async def remove(self, ctx: commands.Context, role: Union[discord.Role, int, str]):
        """Remove a role a user can choose upon verification"""
        if isinstance(role, discord.Role):
            role = role.id
        async with self.config.guild(ctx.guild).roles() as roles:
            if role in roles:
                roles.pop(role)
            else:
                for k, v in list(roles.items()):
                    if v == role:
                        roles.pop(k)
        await ctx.send(f"Removed role from verification")

    @verifyset_role.command()
    async def list(self, ctx: commands.Context):
        """List roles a user can choose upon verification"""
        roles = await self.config.guild(ctx.guild).roles()
        embed = discord.Embed(title="Verification Roles", color=await ctx.embed_color(),
                              description="\n".join(f"<@&{k}> ({v})" for k, v in roles.items()) or "*None*")
        await ctx.send(embed=embed)

