import random
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

old_slot: Optional[commands.Command] = None
old_payday: Optional[commands.Command] = None
old_payouts: Optional[commands.Command] = None

MAX_CONCURRENT_SLOTS = 3
JACKPOT_AMOUNT = 100
TRIPLE = 3
DOUBLE = 2

class SlotMachine(Enum):
    cherries = "🍒"
    bell = "🔔"
    clover = "🍀"
    apple = "🍎"
    lemon = "🍋"
    seven = "7️⃣"
    watermelon = "🍉"
    heart = "🩷"
    coin = "🪙"
    grapes = "🍇"

PAYOUTS = {
    (SlotMachine.seven, SlotMachine.seven, SlotMachine.seven): JACKPOT_AMOUNT,
    (SlotMachine.clover, SlotMachine.clover, SlotMachine.clover): 25,
    (SlotMachine.cherries, SlotMachine.cherries, SlotMachine.cherries): 20,
    (SlotMachine.seven, SlotMachine.seven): 5,
    (SlotMachine.clover, SlotMachine.clover): 4,
    (SlotMachine.cherries, SlotMachine.cherries): 3,
    TRIPLE: 10,
    DOUBLE: 2,
}


class EconomyTweaks(commands.Cog):
    """Improves the slot command, adds a configurable bonus for the payday command, and adds slash commands for those two."""

    def __init__(self, bot: Red):
        super().__init__()
        self.bot = bot
        self.concurrent_slots = 0
        default_timer = {
            "last_payday_bonus": 0,
        }
        default_config = {
            "bonus_amount": 1000,
            "bonus_time": 86400,
            "coinfreespin": True,
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
    @commands.hybrid_command(name="payday")
    @commands.guild_only()
    async def payday(self, ctx: commands.Context):
        """
        Get some free currency.
        """
        assert ctx.guild and isinstance(ctx.author, discord.Member)
        guild = ctx.guild
        author = ctx.author
        mention = "" if ctx.interaction else f"{author.mention} "

        if not (economy := await self.get_economy_cog(ctx)):
            return

        cur_time = calendar.timegm(ctx.message.created_at.utctimetuple())
        credits_name = await bank.get_currency_name(guild)
        is_global = await bank.is_global()
        if is_global:
            next_payday = await economy.config.user(author).next_payday() + await economy.config.PAYDAY_TIME()
            bonus_time = await self.config.bonus_time()
            next_payday_bonus = await self.config.user(author).last_payday_bonus() + bonus_time
            payday_amount = await economy.config.PAYDAY_CREDITS()
            bonus_amount = await self.config.bonus_amount()
        else:
            next_payday = await economy.config.member(author).next_payday() + await economy.config.guild(guild).PAYDAY_TIME()
            bonus_time = await self.config.guild(guild).bonus_time()
            next_payday_bonus = await self.config.member(author).last_payday_bonus() + bonus_time
            payday_amount = await economy.config.guild(guild).PAYDAY_CREDITS()
            bonus_amount = await self.config.guild(guild).bonus_amount()

        if cur_time < next_payday:
            relative_time = discord.utils.format_dt(datetime.now(timezone.utc) + timedelta(seconds=next_payday - cur_time), "R")
            relative_bonus = discord.utils.format_dt(datetime.now(timezone.utc) + timedelta(seconds=max(0, next_payday_bonus - cur_time)), "R")
            return await ctx.send(f"{mention}Too soon. Your next payday is {relative_time}. Your next bonus is {relative_bonus}.", ephemeral=True)

        is_bonus = cur_time >= next_payday_bonus and bonus_amount > 0 and bonus_amount > payday_amount
        reward = bonus_amount if is_bonus else payday_amount
        if not is_global:
            for role in author.roles:
                role_reward = await economy.config.role(role).PAYDAY_CREDITS()
                if role_reward > reward:
                    reward = role_reward

        if is_global:
            await economy.config.user(author).next_payday.set(cur_time)
            if is_bonus:
                await self.config.user(author).last_payday_bonus.set(cur_time)
        else:
            await economy.config.member(author).next_payday.set(cur_time)
            if is_bonus:
                await self.config.member(author).last_payday_bonus.set(cur_time)

        try:
            await bank.deposit_credits(author, reward)
        except errors.BalanceTooHigh as exc:
            await bank.set_balance(author, exc.max_balance)
            return await ctx.send(f"{mention}You've reached the maximum amount of {credits_name}!"
                                  f" You currently have {humanize_number(exc.max_balance)} {credits_name}", ephemeral=True)

        pos = await bank.get_leaderboard_position(author)
        position = f"#{humanize_number(pos)}" if pos else "unknown"
        amount = humanize_number(reward)
        new_balance = humanize_number(await bank.get_balance(author))
        if is_bonus:
            relative_time = discord.utils.format_dt(datetime.now(timezone.utc) + timedelta(seconds=bonus_time), "R")
            await ctx.send(f"{mention}Bonus! Take {amount} {credits_name}. You now have {new_balance} {credits_name}!"
                           f"\nYou are currently {position} on the leaderboard."
                           f"\nNext bonus {relative_time}", ephemeral=True)
        else:
            await ctx.send(f"{mention}Here, take {amount} {credits_name}. You now have {new_balance} {credits_name}!"
                           f"\nYou are currently {position} on the leaderboard.", ephemeral=True)


    @commands.command(name="slot")
    @commands.guild_only()
    async def slot_cmd(self, ctx: commands.Context, bid: int):
        """Play the slot machine."""
        try:
            self.concurrent_slots += 1
            await self.slot(ctx, bid)
        finally:
            self.concurrent_slots -= 1

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
        
        if self.concurrent_slots > MAX_CONCURRENT_SLOTS and not ctx.interaction:
            content = f"Too many people are using the slot machine right now. "
            if self.bot.tree.get_command("slots") is None:
                content += "The bot owner could enable the `/slots` slash command, which would allow more people to use it at the same time."
            else:
                content += "Consider using the `/slots` slash command instead, which allows more people to use it at the same time."
            return await ctx.send(content)
        
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
        is_global = await bank.is_global()

        if (cur_time - last_slot) < max(3, slot_time):
            await ctx.send("You're on cooldown, try again in a few seconds.")
            return
        if bid < min_bid:
            await ctx.send(f"Your bid must be at least {min_bid} {currency_name}")
            return
        if bid > max_bid:
            await ctx.send(f"Your bid cannot be greater than {max_bid} {currency_name}")
            return
        if not await bank.can_spend(author, bid):
            await ctx.send("You ain't got enough money, friend.")
            return
        
        if is_global:
            await economy.config.user(author).last_slot.set(cur_time)
        else:
            await economy.config.member(author).last_slot.set(cur_time)

        default_reel = deque(cast(Iterable, SlotMachine))
        reels = []
        for _ in range(3):
            default_reel.rotate(random.randint(-999, 999))  # weeeeee
            new_reel = deque(default_reel, maxlen=3)
            reels.append(new_reel)

        multiplier = PAYOUTS.get((reels[0][1], reels[1][1], reels[2][1]),
                        PAYOUTS.get((reels[0][1], reels[1][1]),
                        PAYOUTS.get((reels[1][1], reels[2][1]))))

        if not multiplier:
            has_three = reels[0][1] == reels[1][1] == reels[2][1]
            has_two = reels[0][1] == reels[1][1] or reels[1][1] == reels[2][1]
            if has_three:
                multiplier = PAYOUTS[TRIPLE]
            elif has_two:
                multiplier = PAYOUTS[DOUBLE]
        
        coinfreespin = await self.config.coinfreespin() if is_global else await self.config.guild(guild).coinfreespin()
        if coinfreespin and not multiplier and SlotMachine.coin in (reels[0][1], reels[1][1], reels[2][1]):
            multiplier = 1

        if multiplier:
            if multiplier == 1:
                phrase = "Free spin"
            else:
                phrase = f"**×{multiplier}**"
                old_balance = await bank.get_balance(author)
                winnings = bid * (multiplier - 1)
                new_balance = old_balance + winnings
                try:
                    await bank.deposit_credits(author, winnings)
                except errors.BalanceTooHigh as exc:
                    await bank.set_balance(author, exc.max_balance)
        else:
            old_balance = await bank.get_balance(author)
            await bank.withdraw_credits(author, bid)
            new_balance = old_balance - bid
            phrase = "*None*"

        embed = discord.Embed(title="Slot Machine", color=await self.bot.get_embed_color(ctx.channel))
        embed.add_field(name="Bid", value=f"{humanize_number(bid)} {currency_name}")

        first = f"┃ {reels[0][0].value} ⬛ ⬛ ┃\n" \
                f"┣ {reels[0][1].value} ⬛ ⬛ ┫\n" \
                f"┃ {reels[0][2].value} ⬛ ⬛ ┃"
        second = f"┃ {reels[0][0].value} {reels[1][0].value} ⬛ ┃\n" \
                 f"┣ {reels[0][1].value} {reels[1][1].value} ⬛ ┫\n" \
                 f"┃ {reels[0][2].value} {reels[1][2].value} ⬛ ┃"
        third = f"┃ {reels[0][0].value} {reels[1][0].value} {reels[2][0].value} ┃\n" \
                f"┣ {reels[0][1].value} {reels[1][1].value} {reels[2][1].value} ┫\n" \
                f"┃ {reels[0][2].value} {reels[1][2].value} {reels[2][2].value} ┃"
        
        def prepare_final_embed():
            nonlocal currency_name, new_balance, phrase
            embed.add_field(name="Winnings", value=phrase)
            embed.add_field(name="Balance", value=f"{humanize_number(new_balance)} {currency_name}")
            if multiplier and multiplier >= JACKPOT_AMOUNT:
                embed.title = "🎆 JACKPOT!!! 🎆"

        if ctx.interaction:
            embed.description = first
            await ctx.interaction.response.send_message(embed=embed)
            await asyncio.sleep(1)
            embed.description = second
            await ctx.interaction.edit_original_response(embed=embed)
            await asyncio.sleep(1)
            embed.description = third
            prepare_final_embed()
            await ctx.interaction.edit_original_response(embed=embed)
        else:
            embed.description = first
            message = await ctx.reply(embed=embed, allowed_mentions=discord.AllowedMentions.none())
            await asyncio.sleep(1)
            embed.description = second
            await message.edit(embed=embed)
            await asyncio.sleep(1)
            embed.description = third
            prepare_final_embed()
            await message.edit(embed=embed)


    @commands.group(name="economytweakset", aliases=["economytweaksset"])  # type: ignore
    @commands.admin_or_permissions(manage_guild=True)
    async def economytweakset(self, ctx: commands.Context):
        """Settings for the economytweaks cog."""
        pass

    @economytweakset.command(name="coinfreespin")
    @bank.is_owner_if_bank_global()
    async def economytweakset_coinfreespin(self, ctx: commands.Context):
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

    @economytweakset.command(name="bonusamount")
    @bank.is_owner_if_bank_global()
    async def economytweakset_bonusamount(self, ctx: commands.Context, creds: Optional[int]):
        """Set the amount earned with each payday bonus, must be greater than the payday amount itself, 0 to disable"""
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

    @economytweakset.command(name="bonustime")
    @bank.is_owner_if_bank_global()
    async def economytweakset_bonustime(self, ctx: commands.Context, *, duration: TimedeltaConverter(default_unit="seconds")):  # type: ignore
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
        await bot.add_cog(EconomyTweaks(bot))
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
            await bot.add_cog(EconomyTweaks(bot))
        _ = asyncio.create_task(add_cog())
