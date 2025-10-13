import random
import logging
import calendar
import asyncio
import discord
from enum import Enum
from typing import Iterable, Optional, cast
from datetime import datetime, timedelta, timezone
from collections import deque

from redbot.core import Config, commands, app_commands, bank, errors
from redbot.core.bot import Red
from redbot.cogs.economy.economy import Economy
from redbot.core.utils.chat_formatting import humanize_number
from redbot.core.commands.converter import TimedeltaConverter

log = logging.getLogger("red.crab-cogs.economyprettier")

old_slot: Optional[commands.Command] = None
old_payday: Optional[commands.Command] = None
old_payouts: Optional[commands.Command] = None


class SMReel(Enum):
    cherries = "🍒"
    strawberry = "🍓"
    clover = "🍀"
    cyclone = "🌀"
    sunflower = "🌻"
    seven = "7️⃣"
    mushroom = "🍄"
    heart = "❤️"
    snowflake = "❄️"

PAYOUTS = {
    (SMReel.seven, SMReel.seven, SMReel.seven): {
        "payout": lambda x: x * 50,
        "phrase": "JACKPOT! ×50",
    },
    (SMReel.clover, SMReel.clover, SMReel.clover): {
        "payout": lambda x: x * 25,
        "phrase": "×25",
    },
    (SMReel.cherries, SMReel.cherries, SMReel.cherries): {
        "payout": lambda x: x * 20,
        "phrase": "×20",
    },
    (SMReel.seven, SMReel.seven): {
        "payout": lambda x: x * 5,
        "phrase": "×5",
    },
    (SMReel.cherries, SMReel.cherries): {
        "payout": lambda x: x * 3,
        "phrase": "×3",
    },
    "3 symbols": {
        "payout": lambda x: x * 10,
        "phrase": "×10",
    },
    "2 symbols": {
        "payout": lambda x: x * 2,
        "phrase": "×2",
    },
}


class EconomyPrettier(commands.Cog):
    """Replaces the payday and slot commands with slightly prettier versions and adds slash command versions."""

    def __init__(self, bot: Red):
        super().__init__()
        self.bot = bot
        default_timer = {
            "last_payday_bonus": 0,
        }
        default_config = {
            "bonus_amount": 1000,
            "bonus_time": 86400,
        }
        self.config = Config.get_conf(self, identifier=557574777)
        self.config.register_user(**default_timer)
        self.config.register_member(**default_timer)
        self.config.register_global(**default_config)
        self.config.register_guild(**default_config)

    def cog_unload(self):
        global old_slot, old_payday, old_payouts
        if old_slot:
            self.bot.remove_command(old_slot.name)
            self.bot.add_command(old_slot)
        if old_payday:
            self.bot.remove_command(old_payday.name)
            self.bot.add_command(old_payday)
        if old_payouts:
            self.bot.add_command(old_payouts)

    async def get_economy_cog(self, ctx: commands.Context) -> Optional[Economy]:
        cog: Optional[Economy] = self.bot.get_cog("Economy")  # type: ignore
        if cog:
            return cog
        await ctx.reply("Economy cog not loaded! Contact the bot owner for more information.", ephemeral=True, allowed_mentions=discord.AllowedMentions.none())


    # https://github.com/Cog-Creators/Red-DiscordBot/blob/dd3b9a01d3247625ddb5c998ced52c012da352cc/redbot/cogs/economy/economy.py#L291
    @commands.command(name="payday")
    @commands.guild_only()
    async def payday(self, ctx: commands.Context):
        """
        Get some free currency.
        """
        assert ctx.guild and isinstance(ctx.author, discord.Member)
        guild = ctx.guild
        author = ctx.author

        if not (economy := await self.get_economy_cog(ctx)):
            return

        cur_time = calendar.timegm(ctx.message.created_at.utctimetuple())
        credits_name = await bank.get_currency_name(guild)
        if await bank.is_global():
            next_payday = await economy.config.user(author).next_payday() + await economy.config.PAYDAY_TIME()
            next_payday_bonus = await self.config.user(author).last_payday_bonus() + await self.config.bonus_time()
            if cur_time >= next_payday:
                is_bonus = cur_time >= next_payday_bonus
                if is_bonus:
                    reward = await self.config.bonus_amount()
                else:
                    reward = await economy.config.PAYDAY_CREDITS()
                try:
                    await bank.deposit_credits(author, reward)
                except errors.BalanceTooHigh as exc:
                    await bank.set_balance(author, exc.max_balance)
                    await ctx.send(f"{author.mention} You've reached the maximum amount of {credits_name}! You currently have {humanize_number(exc.max_balance)} {credits_name}")
                    return
                await economy.config.user(author).next_payday.set(cur_time)
                await self.config.user(author).last_payday_bonus.set(cur_time)
                pos = await bank.get_leaderboard_position(author)
                position = f"#{humanize_number(pos)}" if pos else "unknown"
                amount = humanize_number(reward)
                new_balance = humanize_number(await bank.get_balance(author))
                if is_bonus:
                    relative_time = discord.utils.format_dt(datetime.now(timezone.utc) + timedelta(seconds=next_payday_bonus - cur_time), "R")
                    await ctx.send(f"{author.mention} Bonus! Take {amount} {credits_name}. You now have {new_balance} {credits_name}! Next bonus in {relative_time}"
                                    f"\nYou are currently {position} on the leaderboard.")
                else:
                    await ctx.send(f"{author.mention} Here, take {amount} {credits_name}. You now have {new_balance} {credits_name}!"
                                    f"\nYou are currently {position} on the leaderboard.")
            else:
                relative_time = discord.utils.format_dt(datetime.now(timezone.utc) + timedelta(seconds=next_payday - cur_time), "R")
                await ctx.send(f"{author.mention} Too soon. Your next payday is {relative_time}")
        else:
            next_payday = await economy.config.member(author).next_payday() + await economy.config.guild(guild).PAYDAY_TIME()
            next_payday_bonus = await self.config.member(author).last_payday_bonus() + await self.config.guild(guild).bonus_time()
            if cur_time >= next_payday:
                is_bonus = cur_time >= next_payday_bonus
                if is_bonus:
                    reward = await self.config.guild(guild).bonus_amount()
                else:
                    reward = await economy.config.guild(guild).PAYDAY_CREDITS()
                    for role in author.roles:
                        role_credits = await economy.config.role(role).PAYDAY_CREDITS()
                        if role_credits > reward:
                            reward = role_credits
                try:
                    await bank.deposit_credits(author, reward)
                except errors.BalanceTooHigh as exc:
                    await bank.set_balance(author, exc.max_balance)
                    await ctx.send(f"{author.mention} You've reached the maximum amount of {credits_name}! You currently have {humanize_number(exc.max_balance)} {credits_name}")
                    return
                await economy.config.member(author).next_payday.set(cur_time)
                await self.config.member(author).last_payday_bonus.set(cur_time)
                pos = await bank.get_leaderboard_position(author)
                position = f"#{humanize_number(pos)}" if pos else "unknown"
                amount = humanize_number(await economy.config.PAYDAY_CREDITS())
                new_balance = humanize_number(await bank.get_balance(author))
                if is_bonus:
                    relative_time = discord.utils.format_dt(datetime.now(timezone.utc) + timedelta(seconds=next_payday_bonus - cur_time), "R")
                    await ctx.send(f"{author.mention} Bonus! Take {amount} {credits_name}. You now have {new_balance} {credits_name}! Next bonus in {relative_time}"
                                    f"\nYou are currently {position} on the leaderboard.")
                else:
                    await ctx.send(f"{author.mention} Here, take {amount} {credits_name}. You now have {new_balance} {credits_name}!"
                                    f"\nYou are currently {position} on the leaderboard.")
            else:
                relative_time = discord.utils.format_dt(datetime.now(timezone.utc) + timedelta(seconds=next_payday - cur_time), "R")
                await ctx.send(f"{author.mention} Too soon. Your next payday is {relative_time}")


    @commands.command(name="slot")
    @commands.guild_only()
    async def slot_cmd(self, ctx: commands.Context, bid: int):
        """Play the slot machine."""
        await self.slot(ctx, bid)

    @app_commands.command(name="slots")
    @app_commands.describe(bid="How much currency to put in the slot machine.")
    @commands.guild_only()
    async def slot_app(self, interaction: discord.Interaction, bid: int):
        """Play the slot machine."""
        ctx = await commands.Context.from_interaction(interaction)
        await self.slot(ctx, bid)

    # https://github.com/Cog-Creators/Red-DiscordBot/blob/dd3b9a01d3247625ddb5c998ced52c012da352cc/redbot/cogs/economy/economy.py#L579
    async def slot(self, ctx: commands.Context, bid: int):
        assert ctx.guild and isinstance(ctx.author, discord.Member)
        guild = ctx.guild
        author = ctx.author

        if not (economy := await self.get_economy_cog(ctx)):
            return
        
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
        
        new_balance = calendar.timegm(ctx.message.created_at.utctimetuple())

        if (new_balance - last_slot) < slot_time:
            await ctx.send("You're on cooldown, try again in a bit.")
            return
        if bid < min_bid:
            await ctx.send(f"Your bid must be at least {min_bid}")
            return
        if bid > max_bid:
            await ctx.send(f"Your bid cannot be greater than {max_bid}")
            return
        if not await bank.can_spend(author, bid):
            await ctx.send("You ain't got enough money, friend.")
            return
        if await bank.is_global():
            await economy.config.user(author).last_slot.set(new_balance)
        else:
            await economy.config.member(author).last_slot.set(new_balance)

        credits_name = await bank.get_currency_name(guild)

        default_reel = deque(cast(Iterable, SMReel))
        reels = []
        for i in range(3):
            default_reel.rotate(random.randint(-999, 999))  # weeeeee
            new_reel = deque(default_reel, maxlen=3)  # we need only 3 symbols
            reels.append(new_reel)  # for each reel

        rows = (
            (reels[0][0], reels[1][0], reels[2][0]),
            (reels[0][1], reels[1][1], reels[2][1]),
            (reels[0][2], reels[1][2], reels[2][2]),
        )

        payout = PAYOUTS.get(rows[1])
        if not payout:
            # Checks for two-consecutive-symbols special rewards
            payout = PAYOUTS.get((rows[1][0], rows[1][1]), PAYOUTS.get((rows[1][1], rows[1][2])))
        if not payout:
            # Still nothing. Let's check for 3 generic same symbols
            # or 2 consecutive symbols
            has_three = rows[1][0] == rows[1][1] == rows[1][2]
            has_two = (rows[1][0] == rows[1][1]) or (rows[1][1] == rows[1][2])
            if has_three:
                payout = PAYOUTS["3 symbols"]
            elif has_two:
                payout = PAYOUTS["2 symbols"]

        pay = 0
        if payout:
            then = await bank.get_balance(author)
            pay = payout["payout"](bid)  # type: ignore
            new_balance = then - bid + pay
            try:
                await bank.set_balance(author, new_balance)
            except errors.BalanceTooHigh as exc:
                await bank.set_balance(author, exc.max_balance)
                await ctx.send(f"{author.mention} You've reached the maximum amount of {credits_name}! You currently have {humanize_number(exc.max_balance)} {credits_name}")
                return
            phrase = f"**{payout['phrase']}**"
        else:
            then = await bank.get_balance(author)
            await bank.withdraw_credits(author, bid)
            new_balance = then - bid
            phrase = "Nothing!"

        embed = discord.Embed(title="Slot Machine", color=await self.bot.get_embed_color(ctx.channel))
        first = f"{reels[0][0].value}⬛⬛\n{reels[0][1].value}⬛⬛\n{reels[0][2].value}⬛⬛"
        second = f"{reels[0][0].value}{reels[1][0].value}⬛\n{reels[0][1].value}{reels[1][1].value}⬛\n{reels[0][2].value}{reels[1][2].value}⬛"
        third = f"{reels[0][0].value}{reels[1][0].value}{reels[2][0].value}\n{reels[0][1].value}{reels[1][1].value}{reels[2][1].value}\n{reels[0][2].value}{reels[1][2].value}{reels[2][2].value}"
        def add_fields():
            nonlocal bid, credits_name, new_balance, phrase
            embed.add_field(name="Bid", value=f"{bid} {credits_name}")
            embed.add_field(name="Winnings", value=phrase)
            embed.add_field(name="Balance", value=f"{new_balance} {credits_name}")

        if ctx.interaction:
            embed.description = first
            await ctx.interaction.response.send_message(embed=embed)
            await asyncio.sleep(1)
            embed.description = second
            await ctx.interaction.edit_original_response(embed=embed)
            await asyncio.sleep(1)
            embed.description = third
            add_fields()
            await ctx.interaction.edit_original_response(embed=embed)
        else:
            embed.description = first
            message = await ctx.reply(embed=embed, allowed_mentions=discord.AllowedMentions.none())
            await asyncio.sleep(1)
            embed.description = second
            await message.edit(embed=embed)
            await asyncio.sleep(1)
            embed.description = third
            add_fields()
            await message.edit(embed=embed)


    @commands.group(name="economyprettierset")  # type: ignore
    @commands.admin_or_permissions(manage_guild=True)
    async def economyprettierset(self, ctx: commands.Context):
        """Settings for the economyprettier cog."""
        pass

    @economyprettierset.command(name="bonusamount")
    @bank.is_owner_if_bank_global()
    async def economyprettierset_bonusamount(self, ctx: commands.Context, creds: Optional[int]):
        """Set the amount earned each with each payday bonus."""
        assert ctx.guild
        is_global = await bank.is_global()
        config_amount = self.config.bonus_amount if is_global else self.config.guild(ctx.guild).bonus_amount
        currency = await bank.get_currency_name(None if is_global else ctx.guild)
        if creds is None:
            creds = await config_amount()
            return await ctx.send(f"Current payday bonus is {creds} {currency}.")
        if creds < 0:
            return await ctx.send("Payout must be a positive number or 0.")
        await config_amount.set(creds)
        await ctx.send(f"Current payday bonus is {creds} {currency}.")

    @economyprettierset.command(name="bonustime")
    @bank.is_owner_if_bank_global()
    async def economyprettierset_bonustime(self, ctx: commands.Context, *, duration: TimedeltaConverter(default_unit="seconds")):  # type: ignore
        """Set the time between each payday bonus. Example: 24 hours"""
        assert ctx.guild
        is_global = await bank.is_global()
        config_time = self.config.bonus_time if is_global else self.config.guild(ctx.guild).bonus_time
        if duration is None:
            seconds = await config_time()
            return await ctx.send(f"Current payday bonus time is {seconds} seconds.")
        seconds = duration.total_seconds()
        await config_time.set(seconds)
        await ctx.send(f"Current payday bonus time is {seconds} seconds.")


async def setup(bot: Red):
    global old_slot, old_payday, old_payouts
    old_slot = bot.get_command("slot")
    old_payday = bot.get_command("payday")
    old_payouts = bot.get_command("payouts")
    if old_slot and old_payday and old_payouts:
        bot.remove_command(old_slot.name)
        bot.remove_command(old_payday.name)
        bot.remove_command(old_payouts.name)
        await bot.add_cog(EconomyPrettier(bot))
    else:
        async def add_cog():
            global old_slot, old_payday, old_payouts
            await asyncio.sleep(1)  # hopefully economy cog has finished loading
            old_slot = bot.get_command("slot")
            old_payday = bot.get_command("payday")
            if old_slot and old_payday and old_payouts:
                bot.remove_command(old_slot.name)
                bot.remove_command(old_payday.name)
                bot.remove_command(old_payouts.name)
            await bot.add_cog(EconomyPrettier(bot))
        _ = asyncio.create_task(add_cog())
