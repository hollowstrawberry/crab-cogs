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
        if your_captain_bonus < 0 or your_captain_bonus > 35:
            await ctx.send("Captain bonus must be between 0 and 35 (%)")
            return
        if your_ap < 20 or your_ap > 100 or enemy_ap < 20 or enemy_ap > 100:
            await ctx.send("AP must be between 20 and 100 (%)")
            return
        your_speed = int(your_base_speed * (1 + (your_captain_bonus / 100))) + your_bonus_speed
        enemy_speed = int(your_speed / your_ap * enemy_ap)
        enemy_speed_min = int(your_speed / (your_ap if your_ap == 100 else your_ap + 0.5) * (enemy_ap if enemy_ap == 100 else enemy_ap - 0.5))
        enemy_speed_max = int(your_speed / (your_ap if your_ap == 100 else your_ap - 0.5) * (enemy_ap if enemy_ap == 100 else enemy_ap + 0.5))
        enemy_speed_str = f"{enemy_speed} ({enemy_speed_min}~{enemy_speed_max})" if enemy_speed_min != enemy_speed_max else f"{enemy_speed}"
        embed = discord.Embed(title="🕊️ Speed Calculation", color=await ctx.embed_color())
        embed.add_field(name="Your AP", value=f"{your_ap}%", inline=True)
        embed.add_field(name="Enemy AP", value=f"{enemy_ap}%", inline=True)
        embed.add_field(name="Your Speed", value=f"{your_speed}", inline=False)
        embed.add_field(name="Enemy Speed", value=enemy_speed_str, inline=False)
        await ctx.send(embed=embed)

    @commands.guild_only()
    @commands.bot_has_permissions(manage_nicknames=True, manage_roles=True)
    @commands.command()
    async def dislyteverify(self, ctx: commands.Context, username: str, uid: int, role: discord.Role = None):
        """Verify yourself with your Dislyte username, UID, and optionally choosing a role to get."""
        username = username.strip()
        if not username:
            await ctx.send("Invalid username! Please try again.")
            return
        if uid < 0:
            await ctx.send("Invalid UID! Please try again. You can find your UID in your profile in-game.")
            return
        roles = await self.config.guild(ctx.guild).roles()
        author: discord.Member = ctx.author
        if roles:
            if len(roles) == 1:
                role = roles[0]
            if not role or (str(role.id) not in roles and role not in author.roles):
                await ctx.send(f"You must choose a role between: {', '.join(roles.values())}. Please try again.")
                return
        await self.config.member(author).username.set(username)
        await self.config.member(author).uid.set(uid)
        try:
            await author.edit(nick=username)
        except:
            pass
        if role:
            await author.add_roles(role)
        await ctx.send("✅ Verification complete")

    @commands.mod()
    @commands.guild_only()
    @commands.command()
    async def dislyteverifyother(self, ctx: commands.Context, member: discord.Member, uid: int, username: str = None):
        """Manually verify another user as a mod."""
        await self.config.member(member).username.set(username or member.display_name)
        await self.config.member(member).uid.set(uid)
        if username:
            try:
                await member.edit(nick=username)
            except:
                pass
        await ctx.send("✅ Verification complete")

    @commands.guild_only()
    @commands.command()
    async def dislyteinfo(self, ctx: commands.Context, member: discord.Member):
        """View verification info for a member."""
        embed = discord.Embed(description=member.mention, color=await ctx.embed_color())
        embed.add_field(name="Username", value=await self.config.member(member).username())
        embed.add_field(name="UID", value=await self.config.member(member).uid())
        embed.set_thumbnail(url=member.avatar_url)
        await ctx.send(embed=embed)

    @commands.mod()
    @commands.guild_only()
    @commands.group(invoke_without_command=True)
    async def dislyteset(self, ctx: commands.Context):
        """Configuration for [p]dislyteverify"""
        await ctx.send_help()

    @dislyteset.command()
    async def roleadd(self, ctx: commands.Context, role: discord.Role):
        """Add a role a user can choose upon verification"""
        async with self.config.guild(ctx.guild).roles() as roles:
            roles[str(role.id)] = role.name
            if len(roles) == 1:
                await ctx.send(f"{role.name} will now be given to users who verify themselves. "
                               f"Add more roles to let the user choose manually.")
            else:
                await ctx.send(f"Added {role.name} to the roles a user can choose upon verification.")

    @dislyteset.command()
    async def roleremove(self, ctx: commands.Context, role: Union[discord.Role, int, str]):
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

    @dislyteset.command()
    async def rolelist(self, ctx: commands.Context):
        """List roles a user can choose upon verification"""
        roles = await self.config.guild(ctx.guild).roles()
        embed = discord.Embed(title="Verification Roles", color=await ctx.embed_color(),
                              description="\n".join(f"<@&{k}> ({v})" for k, v in roles.items()) or "*None*")
        await ctx.send(embed=embed)

