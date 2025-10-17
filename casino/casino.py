import logging
import asyncio
import discord
import calendar
from typing import Optional
from redbot.core import commands, app_commands, bank
from redbot.core.bot import Red
from redbot.cogs.economy.economy import Economy
from redbot.core.utils.chat_formatting import humanize_number

from casino.slots import slots
from casino.base import BaseCasinoCog
from casino.blackjack import Blackjack

log = logging.getLogger("red.crab-cogs.casino")

old_slot: Optional[commands.Command] = None
old_payout: Optional[commands.Command] = None

MAX_CONCURRENT_SLOTS = 3


class Casino(BaseCasinoCog):
    """Improves the builtin slot command and adds blackjack."""

    def __init__(self, bot: Red):
        super().__init__(bot)

    def cog_unload(self):
        global old_slot, old_payout
        if old_slot:
            self.bot.remove_command(old_slot.name)
            self.bot.add_command(old_slot)
        if old_payout:
            self.bot.remove_command(old_payout.name)
            self.bot.add_command(old_payout)

    async def get_economy_cog(self, ctx: commands.Context) -> Optional[Economy]:
        cog: Optional[Economy] = self.bot.get_cog("Economy")  # type: ignore
        if cog:
            return cog
        await ctx.reply("Economy cog not loaded! Contact the bot owner for more information.", ephemeral=True, allowed_mentions=discord.AllowedMentions.none())
    

    @commands.hybrid_command(name="blackjack", aliases=["bj"])
    @app_commands.describe(bid="How much currency to bet.")
    @commands.guild_only()
    async def blackjack_cmd(self, ctx: commands.Context, bid: int):
        """Play Blackjack against the bot. Get as close to 21 as possible!"""
        assert ctx.guild and isinstance(ctx.author, discord.Member) and isinstance(ctx.channel, discord.TextChannel)

        minimum_bid = await self.config.bjmin() if await bank.is_global() else await self.config.guild(ctx.guild).bjmin()
        maximum_bid = await self.config.bjmax() if await bank.is_global() else await self.config.guild(ctx.guild).bjmax()
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


    @commands.hybrid_command(name="slot")
    @commands.guild_only()
    @app_commands.describe(bid="How much currency to put in the slot machine.")
    async def slot_cmd(self, ctx: commands.Context, bid: int):
        """Play the slot machine."""
        try:
            self.concurrent_slots += 1
            await self.slot(ctx, bid)
        finally:
            self.concurrent_slots -= 1

    async def slot(self, ctx: commands.Context, bid: int):
        assert ctx.guild and isinstance(ctx.author, discord.Member)
        guild = ctx.guild
        author = ctx.author

        if not (economy := await self.get_economy_cog(ctx)):
            return

        if self.concurrent_slots > MAX_CONCURRENT_SLOTS and not ctx.interaction:
            content = f"Too many people are using the slot machine right now. "
            if self.bot.tree.get_command("slots") is None:
                content += "The bot owner could enable the `/slots` slash command, which would allow more people to use it at the same time."
            else:
                content += "Consider using the `/slots` slash command instead, which allows more people to use it at the same time."
            return await ctx.send(content)
        
        is_global = await bank.is_global()
        if await bank.is_global():
            min_bid = await economy.config.SLOT_MIN()
            max_bid = await economy.config.SLOT_MAX()
            slot_time = await economy.config.SLOT_TIME()
            last_slot = await economy.config.user(author).last_slot()
        else:
            min_bid = await economy.config.guild(guild).SLOT_MIN()
            max_bid = await economy.config.guild(guild).SLOT_MAX()
            slot_time = await economy.config.guild(guild).SLOT_TIME()
            last_slot = await economy.config.member(author).last_slot()
        
        cur_time = calendar.timegm(ctx.message.created_at.utctimetuple())
        currency_name = await bank.get_currency_name(ctx.guild)

        if (cur_time - last_slot) < max(3, slot_time):
            await ctx.send("You're on cooldown, try again in a few seconds.")
            return
        if bid < min_bid:
            await ctx.send(f"Your bid must be at least {humanize_number(min_bid)} {currency_name}")
            return
        if bid > max_bid:
            await ctx.send(f"Your bid cannot be greater than {humanize_number(max_bid)} {currency_name}")
            return
        if not await bank.can_spend(author, bid):
            await ctx.send("You ain't got enough money, friend.")
            return
        
        if is_global:
            await economy.config.user(author).last_slot.set(cur_time)
        else:
            await economy.config.member(author).last_slot.set(cur_time)

        await slots(self, ctx, bid)


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

    @casinoset.command(name="coinfreespin")
    @bank.is_owner_if_bank_global()
    async def casinoset_coinfreespin(self, ctx: commands.Context):
        """
        Toggles whether a coin in the slot machine will give a free spin.
        This increases the expected player returns from 68% to 91%, which is similar to real slot machines.
        """
        assert ctx.guild
        is_global = await bank.is_global()
        config_value = self.config.coinfreespin if is_global else self.config.guild(ctx.guild).coinfreespin
        value = await config_value()
        await config_value.set(not value)
        if not value:
            await ctx.send(f"Coins will give free spins. Expected player returns: 91%")
        else:
            await ctx.send(f"Coins won't give free spins. Expected player returns: 68%")


async def setup(bot: Red):
    global old_slot, old_payout
    old_slot = bot.get_command("slot")
    old_payout = bot.get_command("payout")
    if old_slot and old_payout:
        bot.remove_command(old_slot.name)
        bot.remove_command(old_payout.name)
        await bot.add_cog(Casino(bot))
    else:
        async def add_cog():
            global old_slot, old_payout
            await asyncio.sleep(1)  # hopefully economy cog has finished loading
            old_slot = bot.get_command("slot")
            old_payout = bot.get_command("payout")
            if old_slot and old_payout:
                bot.remove_command(old_slot.name)
                bot.remove_command(old_payout.name)
            await bot.add_cog(Casino(bot))
        _ = asyncio.create_task(add_cog())
