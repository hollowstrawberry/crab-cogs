import discord
from redbot.core import commands, bank
from redbot.core.bot import Red

def check_global_setting_admin():
    async def predicate(ctx: commands.Context) -> bool:
        bot: Red = ctx.bot
        if await bank.is_global():
            return await bot.is_owner(ctx.author)

        if not ctx.guild or not isinstance(ctx.author, discord.Member):
            return False
        if await bot.is_owner(ctx.author) or ctx.author == ctx.guild.owner or ctx.channel.permissions_for(ctx.author).manage_guild:
            return True
        
        admin_roles = set(await bot.get_admin_role_ids(ctx.guild.id))
        for role in ctx.author.roles:
            if role.id in admin_roles:
                return True
        return False

    return commands.check(predicate)
