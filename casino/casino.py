import logging
import discord
from typing import Optional

from redbot.core import commands, app_commands, bank
from redbot.core.bot import Red
from redbot.core.utils.chat_formatting import humanize_number

from casino.base import BaseCasinoCog
from casino.blackjack import Blackjack

log = logging.getLogger("red.crab-cogs.casino")


class Casino(BaseCasinoCog):
    """
    """

    def __init__(self, bot: Red):
        super().__init__(bot)

    async def is_economy_enabled(self, guild: discord.Guild) -> bool:
        economy = self.bot.get_cog("Economy")
        return economy is not None and not await self.bot.cog_disabled_in_guild(economy, guild)
    

    @commands.hybrid_command(name="blackjack", aliases=["bj"])
    @app_commands.describe(bid="How much currency to bet.")
    @commands.guild_only()
    async def blackjack_cmd(self, ctx: commands.Context, bid: int):
        """Play Blackjack against the bot. Get as close to 21 as possible!"""
        assert ctx.guild and isinstance(ctx.author, discord.Member) and isinstance(ctx.channel, discord.TextChannel)

        minimum_bid = await self.config.bjmin() if await bank.is_global() else await self.config.guild(ctx.guild).bjmin()
        maximum_bid = await self.config.bjmin() if await bank.is_global() else await self.config.guild(ctx.guild).bjmin()
        currency_name = await bank.get_currency_name(ctx.guild)
        if bid < 1 or bid < minimum_bid:
            return await ctx.reply(f"Your bid must be at least {minimum_bid} {currency_name}", ephemeral=True)
        elif bid > maximum_bid:
            return await ctx.reply(f"Your bid cannot be greater than {maximum_bid} {currency_name}", ephemeral=True)
        if not await bank.can_spend(ctx.author, bid):
            return await ctx.reply("You ain't got enough money, friend.", ephemeral=True)
        
        await bank.withdraw_credits(ctx.author, bid)
        try:
            blackjack = Blackjack(ctx.author, ctx.channel, bid, await self.bot.get_embed_color(ctx.channel))
            await blackjack.check_payout()
            await ctx.reply(embed=await blackjack.get_embed(), view=discord.ui.View() if blackjack.is_over() else blackjack)
        except Exception:
            await bank.deposit_credits(ctx.author, bid)
            raise
        

    @commands.group(name="casinoset", aliases=["setcasino"])  # type: ignore
    @commands.admin_or_permissions(manage_guild=True)
    @bank.is_owner_if_bank_global()
    async def casinoset(self, ctx: commands.Context):
        """Settings for the Casino cog."""
        pass

    @casinoset.command(name="bjmin", aliases=["blackjackmin"])
    async def casinoset_bjmin(self, ctx: commands.Context, bid: Optional[int]):
        """The minimum bid for blackjack."""
        assert ctx.guild
        is_global = await bank.is_global()
        config_bjmin = self.config.bjmin if is_global else self.config.guild(ctx.guild).bjmin
        currency = await bank.get_currency_name(None if is_global else ctx.guild)
        if bid is None:
            bid = await config_bjmin()
            return await ctx.send(f"Current minimum bid for for Blackjack is {bid} {currency}.")
        if bid < 1:
            return await ctx.send("Bid must be a positive number.")
        await config_bjmin.set(bid)
        await ctx.send(f"New minimum bid for for Blackjack is {bid} {currency}.")

    @casinoset.command(name="bjmax", aliases=["blackjackmax"])
    async def casinoset_bjmax(self, ctx: commands.Context, bid: Optional[int]):
        """The maximum bid for blackjack."""
        assert ctx.guild
        is_global = await bank.is_global()
        config_bjmax = self.config.bjmax if is_global else self.config.guild(ctx.guild).bjmax
        currency = await bank.get_currency_name(None if is_global else ctx.guild)
        if bid is None:
            bid = await config_bjmax()
            return await ctx.send(f"Current maximum bid for for Blackjack is {bid} {currency}.")
        if bid < 1:
            return await ctx.send("Bid must be a positive number.")
        await config_bjmax.set(bid)
        await ctx.send(f"New maximum bid for for Blackjack is {bid} {currency}.")