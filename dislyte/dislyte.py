import discord
from redbot.core import commands, Config
from typing import Union

class Dislyte(commands.Cog):
    """Commands for the game Dislyte"""

    def __init__(self, bot):
        super().__init__()
        self.bot = bot
        self.config = Config.get_conf(self, identifier=646973679)
        self.config.register_guild(roles={})
        self.config.register_member(username="*None*", uid=0)

    async def red_delete_data_for_user(self, requester: str, user_id: int):
        guilds = await self.config.all_guilds()
        for guild_id in guilds.keys():
            await self.config.member_from_ids(guild_id, user_id).clear()

    # Commands

    @commands.command()
    async def speed(self, ctx: commands.Context,
                    your_base_speed: int, your_bonus_speed: int, your_captain_bonus: int, your_ap: int, enemy_ap: int):
        """Calculates speed of an enemy esper based on its AP and your own esper's speed."""
        if your_base_speed < 90 or your_base_speed > 110:
            await ctx.send("Base speed must be between 90 and 110")
            return
        if your_bonus_speed < 0 or your_bonus_speed > 300:
            await ctx.send("Bonus speed must be between 0 and 300")
            return
        if your_captain_bonus < 15 or your_captain_bonus > 35:
            await ctx.send("Captain bonus must be between 15 and 35 (%)")
            return
        if your_ap < 0 or your_ap > 100 or enemy_ap < 0 or enemy_ap > 100:
            await ctx.send("AP must be between 0 and 100 (%)")
            return
        your_speed = int(your_base_speed * (1 + (your_captain_bonus / 100)))
        enemy_speed_min = int(your_speed / (your_ap if your_ap == 100 else your_ap + 0.5) * (enemy_ap if enemy_ap == 100 else enemy_ap - 0.5))
        enemy_speed_max = int(your_speed / (your_ap if your_ap == 100 else your_ap - 0.5) * (enemy_ap if enemy_ap == 100 else enemy_ap + 0.5))
        enemy_speed_str = f"{enemy_speed_min}~{enemy_speed_max}" if enemy_speed_min != enemy_speed_max else f"{enemy_speed_min}"
        embed = discord.Embed(title="Speed Calculation", color=await ctx.embed_color())
        embed.add_field(name="Your AP", value=f"{your_ap}%", inline=True)
        embed.add_field(name="Your Speed", value=f"{your_speed}", inline=True)
        embed.add_field(name="Enemy AP", value=f"{enemy_ap}%", inline=True)
        embed.add_field(name="Enemy Speed", value=enemy_speed_str, inline=True)
        await ctx.send(embed=embed)

    @commands.guild_only()
    @commands.bot_has_permissions(manage_nicknames=True, manage_roles=True)
    @commands.command()
    async def verify(self, ctx: commands.Context, username: str, uid: int, role: discord.Role):
        """Verify yourself in this server. Takes in your Dislyte username, UID, and the role you wish to obtain."""
        username = username.strip()
        if not username:
            await ctx.send("Invalid username! Please try again.")
            return
        if uid < 1:
            await ctx.send("Invalid UID! Please try again. You can find your UID in your profile in-game.")
            return
        roles = await self.config.guild(ctx.guild).roles()
        if not role or str(role.id) not in roles:
            await ctx.send(f"Role must be one of: {', '.join(roles.values())}. Please try again.")
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
    @commands.command()
    async def verification(self, ctx: commands.Context, member: discord.Member):
        """View verification info for a member."""
        embed = discord.Embed(description=member.mention, color=await ctx.embed_color())
        embed.add_field(name="Username", value=await self.config.member(member).username())
        embed.add_field(name="UID", value=await self.config.member(member).uid())
        embed.set_thumbnail(url=member.avatar_url)
        await ctx.send(embed=embed)

    @commands.mod()
    @commands.guild_only()
    @commands.group(invoke_without_command=True)
    async def verifyset(self, ctx: commands.Context):
        """Configuration for [p]verify"""
        await ctx.send_help()

    @verifyset.group(name="role", invoke_without_command=True)
    async def verifyset_role(self, ctx: commands.Context):
        """Add roles a user can choose upon verification"""
        await ctx.send_help()

    @verifyset_role.command()
    async def add(self, ctx: commands.Context, role: discord.Role):
        """Add a role a user can choose upon verification"""
        async with self.config.guild(ctx.guild).roles() as roles:
            roles[str(role.id)] = role.name
        await ctx.send(f"Added {role.name} to the roles a user can choose upon verification.")

    @verifyset_role.command()
    async def remove(self, ctx: commands.Context, role: Union[discord.Role, int, str]):
        """Remove a role a user can choose upon verification"""
        if isinstance(role, discord.Role):
            role = role.id
        role = str(role)
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

