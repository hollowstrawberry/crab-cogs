
import random
import asyncio
import discord
from enum import Enum
from typing import Iterable, Union, cast
from collections import deque
from redbot.core import commands, bank, errors
from redbot.core.utils.chat_formatting import humanize_number

from casino.base import BaseCasinoCog
from casino.views.again_view import AgainView

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

async def slots(cog: BaseCasinoCog, ctx: Union[discord.Interaction, commands.Context], bid: int):
    author = ctx.author if isinstance(ctx, commands.Context) else ctx.user
    assert ctx.guild and isinstance(author, discord.Member) and isinstance(ctx.channel, discord.TextChannel)
    currency_name = await bank.get_currency_name(ctx.guild)

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
    
    coinfreespin = await cog.config.coinfreespin() if await bank.is_global() else await cog.config.guild(ctx.guild).coinfreespin()
    if coinfreespin and not multiplier and SlotMachine.coin in (reels[0][1], reels[1][1], reels[2][1]):
        multiplier = 1

    if multiplier:
        if multiplier == 1:
            phrase = "Free spin"
            balance = await bank.get_balance(author)
        else:
            phrase = f"**×{multiplier}**"
            old_balance = await bank.get_balance(author)
            winnings = bid * (multiplier - 1)
            balance = old_balance + winnings
            try:
                await bank.deposit_credits(author, winnings)
            except errors.BalanceTooHigh as exc:
                await bank.set_balance(author, exc.max_balance)
    else:
        old_balance = await bank.get_balance(author)
        await bank.withdraw_credits(author, bid)
        balance = old_balance - bid
        phrase = "*None*"

    embed = discord.Embed(title="Slot Machine", color=await cog.bot.get_embed_color(ctx.channel))
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
        nonlocal currency_name, balance, phrase
        embed.add_field(name="Winnings", value=phrase)
        embed.add_field(name="Balance", value=f"{humanize_number(balance)} {currency_name}")
        if multiplier and multiplier >= JACKPOT_AMOUNT:
            embed.title = "🎆 JACKPOT!!! 🎆"

    interaction = ctx if isinstance(ctx, discord.Interaction) else ctx.interaction
    if interaction:
        embed.description = first
        await interaction.response.send_message(embed=embed)
        await asyncio.sleep(1)
        embed.description = second
        await interaction.edit_original_response(embed=embed)
        await asyncio.sleep(1)
        embed.description = third
        prepare_final_embed()
        view = AgainView(cog.slot, bid, await interaction.original_response(), currency_name)
        await interaction.edit_original_response(embed=embed, view=view)
    else:
        embed.description = first
        message = await ctx.reply(embed=embed, allowed_mentions=discord.AllowedMentions.none())  # type: ignore
        await asyncio.sleep(1)
        embed.description = second
        await message.edit(embed=embed)
        await asyncio.sleep(1)
        embed.description = third
        prepare_final_embed()
        view = AgainView(cog.slot, bid, message, currency_name)
        await message.edit(embed=embed, view=view)
