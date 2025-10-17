import random
import asyncio
import discord
from typing import List
from redbot.core import bank, errors
from redbot.core.utils.chat_formatting import humanize_number

from casino.base import BaseCasinoCog
from casino.card import Card, CardValue, make_deck
from casino.views.again_view import AgainView


TWENTYONE = 21
DEALER_STAND = 17

EMOJI = {
    CardValue.ACE: "🇦",
    CardValue.TWO: "2️⃣",
    CardValue.THREE: "3️⃣",
    CardValue.FOUR: "4️⃣",
    CardValue.FIVE: "5️⃣",
    CardValue.SIX: "6️⃣",
    CardValue.SEVEN: "7️⃣",
    CardValue.EIGHT: "8️⃣",
    CardValue.NINE: "9️⃣",
    CardValue.TEN: "🔟",
    CardValue.JACK: "🇯",
    CardValue.QUEEN: "🇶",
    CardValue.KING: "🇰",
}

def get_hand_value(hand: List[Card]) -> int:
    total = 0
    aces = 0
    for card in hand:
        if card.value == CardValue.ACE:
            aces += 1
            total += 11  # assume Ace is 11 for now
        else:
            total += min(10, card.value.value)
    while total > 21 and aces > 0:
        total -= 10
        aces -= 1
    return total


class Blackjack(discord.ui.View):
    def __init__(self, cog: BaseCasinoCog, player: discord.Member, channel: discord.TextChannel, bid: int, embed_color: discord.Color):
        super().__init__(timeout=None)
        self.cog = cog
        self.player = player
        self.channel = channel
        self.bid = bid
        self.embed_color = embed_color
        self.dealer: List[Card] = []
        self.hand: List[Card] = []
        self.deck = make_deck()
        random.shuffle(self.deck)
        self.hand.append(self.deck.pop())
        self.hand.append(self.deck.pop())
        self.dealer.append(self.deck.pop())
        self.dealer.append(self.deck.pop())
        self.facedown = True
        self.dealer_turn_started = False
        self.payout_done = False

        self.hit_button = discord.ui.Button(label="Hit", style=discord.ButtonStyle.green)
        self.stand_button = discord.ui.Button(label="Stand", style=discord.ButtonStyle.red)
        self.hit_button.callback = self.hit
        self.stand_button.callback = self.stand
        if get_hand_value(self.hand) < TWENTYONE:
            self.add_item(self.hit_button)
            self.add_item(self.stand_button)
        else:
            self.facedown = False

    def is_over(self) -> bool:
        player_total = get_hand_value(self.hand)
        dealer_total = get_hand_value(self.dealer)
        return player_total > TWENTYONE \
            or dealer_total > TWENTYONE \
            or len(self.hand) == 2 and player_total == TWENTYONE \
            or self.dealer_turn_started and len(self.dealer) == 2 and dealer_total == TWENTYONE \
            or self.dealer_turn_started and dealer_total >= DEALER_STAND

    def is_tie(self) -> bool:
        player_total = get_hand_value(self.hand)
        dealer_total = get_hand_value(self.dealer)
        return player_total <= TWENTYONE and dealer_total <= TWENTYONE and player_total == dealer_total

    def is_win(self) -> bool:
        player_total = get_hand_value(self.hand)
        dealer_total = get_hand_value(self.dealer)
        if player_total > TWENTYONE:
            return False
        if dealer_total > TWENTYONE:
            return True
        return player_total > dealer_total        
        
    def winnings_multiplier(self) -> int:
        return 3 if get_hand_value(self.hand) == TWENTYONE else 2
    
    def payout_amount(self) -> int:
        if self.is_tie():
            return self.bid 
        if not self.is_win():
            return 0
        player_total = get_hand_value(self.hand)
        is_player_natural = len(self.hand) == 2 and player_total == TWENTYONE
        is_dealer_natural = len(self.dealer) == 2 and get_hand_value(self.dealer) == TWENTYONE
        if is_player_natural and not is_dealer_natural:
            return self.bid * 5 // 2
        else:
            return 2 * self.bid

    async def get_embed(self) -> discord.Embed:
        currency_name = await bank.get_currency_name(self.channel.guild)
        dealer_str = " ".join("⬇️" if self.facedown and i == 1 else EMOJI[card.value] for i, card in enumerate(self.dealer))
        hand_str = " ".join(EMOJI[card.value] for card in self.hand)

        embed = discord.Embed(color=self.embed_color)
        embed.add_field(name=f"Dealer ({'?' if self.facedown else get_hand_value(self.dealer)})", value=dealer_str, inline=False)
        embed.add_field(name=f"Hand ({get_hand_value(self.hand)})", value=hand_str, inline=False)
        embed.add_field(name="Bid", value=f"{self.bid} {currency_name}")
        if not self.facedown and self.is_over():
            payout = self.payout_amount()
            embed.add_field(name="Payout", value=f"{humanize_number(payout)} {currency_name}" if self.is_win() or self.is_tie() else "*None*")
            embed.add_field(name="Balance", value=f"{humanize_number(await bank.get_balance(self.player))} {currency_name}")
            if self.is_win():
                embed.title = "🎉 Blackjack (Win)"
            elif self.is_tie():
                embed.title = "👔 Blackjack (Tie)"
            else:
                embed.title = "💀 Blackjack (Lost)"
        else:
            embed.title = "Blackjack"
        return embed
    
    async def dealer_turn(self, interaction: discord.Interaction):
        self.facedown = False
        self.dealer_turn_started = True
        self.hit_button.disabled = True
        self.stand_button.disabled = True
        await self.check_payout()
        currency_name = await bank.get_currency_name(interaction.guild)
        view = AgainView(self.cog.blackjack, self.bid, interaction.message, currency_name) if self.is_over() else self
        await interaction.response.edit_message(embed=await self.get_embed(), view=view)
        while not self.is_over():
            self.dealer.append(self.deck.pop())
            await asyncio.sleep(1)
            await self.check_payout()
            view = AgainView(self.cog.blackjack, self.bid, interaction.message, currency_name) if self.is_over() else self
            await interaction.edit_original_response(embed=await self.get_embed(), view=view)

    async def check_payout(self):
        if not self.payout_done and self.is_over() and (self.is_win() or self.is_tie()):
            self.payout_done = True
            try:
                await bank.deposit_credits(self.player, self.payout_amount())
            except errors.BalanceTooHigh:
                await bank.deposit_credits(self.player, await bank.get_max_balance(self.channel.guild))

    async def hit(self, interaction: discord.Interaction):
        if interaction.user != self.player:
            return await interaction.response.send_message("You're not the one playing!", ephemeral=True)
        self.hand.append(self.deck.pop())
        if get_hand_value(self.hand) >= TWENTYONE:
            await self.dealer_turn(interaction)
        else:
            await interaction.response.edit_message(embed=await self.get_embed())
        
    async def stand(self, interaction: discord.Interaction):
        if interaction.user != self.player:
            return await interaction.response.send_message("You're not the one playing!", ephemeral=True)
        await self.dealer_turn(interaction)
